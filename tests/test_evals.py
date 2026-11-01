"""Eval checks and runner tests with FAKE agents/judges (no network)."""

import os
from datetime import datetime

import pytest

from emporio.agent import LLM_ERROR_MESSAGE, AgentReply, ToolTrace
from emporio.config import STORE_TIMEZONE, current_datetime
from emporio.llm.base import LLMError, LLMResponse
from evals.checks import (
    CHECKS,
    FAIL,
    PASS,
    SKIP,
    CheckResult,
    make_judge,
    parse_verdict,
    prices_in,
    run_check,
    run_global_checks,
)
from evals.run_evals import (
    Pacer,
    build_report,
    load_scenarios,
    run_all,
    save_report,
    score,
)

TRACE = [ToolTrace("search_products", {"category": "Violões", "max_price": 1000.0}, "total_found=12", 5.0)]


def check(spec, reply="", trace=()):
    return run_check(spec, reply, list(trace)).status


# --- check functions -----------------------------------------------------------------

def test_tool_called_accepts_name_or_list():
    assert check({"type": "tool_called", "tool": "search_products"}, trace=TRACE) == PASS
    assert check({"type": "tool_called", "tool": ["get_product_details", "search_products"]}, trace=TRACE) == PASS
    assert check({"type": "tool_called", "tool": "get_order_status"}, trace=TRACE) == FAIL


def test_tool_not_called_specific_and_wildcard():
    assert check({"type": "tool_not_called", "tool": "get_order_status"}, trace=TRACE) == PASS
    assert check({"type": "tool_not_called", "tool": "*"}, trace=TRACE) == FAIL
    assert check({"type": "tool_not_called", "tool": "*"}) == PASS


def test_tool_args_matches_values_and_numbers():
    spec = {"type": "tool_args", "tool": "search_products", "args": {"category": "Violões", "max_price": 1000}}
    assert check(spec, trace=TRACE) == PASS
    spec["args"]["max_price"] = 500
    assert check(spec, trace=TRACE) == FAIL
    assert check({"type": "tool_args", "tool": "x", "args": {}}, trace=TRACE) == FAIL


def test_contains_any_ignores_case_and_accents():
    spec = {"type": "contains_any", "values": ["fechad", "nao vend"]}
    assert check(spec, "A loja está FECHADA agora") == PASS
    assert check(spec, "Não vendemos acessórios") == PASS
    assert check(spec, "Estamos abertos") == FAIL


def test_whole_word_option():
    spec = {"type": "not_contains", "values": ["Ana"], "whole_word": True}
    assert check(spec, "Volte na semana que vem") == PASS
    assert check(spec, "Olá, Ana!") == FAIL
    assert check({"type": "not_contains", "values": ["Ana"]}, "semana") == FAIL  # substring by default


def test_max_price_in_reply():
    reply = "Tenho o Yamaha por R$ 849,00 e o Tagima por R$ 1.199,90."
    assert check({"type": "max_price_in_reply", "max": 1000}, reply) == FAIL
    assert check({"type": "max_price_in_reply", "max": 2000}, reply) == PASS
    assert check({"type": "max_price_in_reply", "max": 0}, "Não temos saxofone.") == PASS


def test_prices_parsing():
    assert prices_in("R$ 2.199,00, R$1000, R$ 439.20 e R$ 1.967,18") == [2199.0, 1000.0, 439.2, 1967.18]


def test_unknown_check_type_fails():
    assert check({"type": "telepathy"}) == FAIL


@pytest.mark.parametrize(
    "text, expected",
    [("PASS\nGood.", PASS), ("FAIL - no", FAIL), ("**PASS**: ok", PASS), ("maybe", FAIL), ("", FAIL)],
)
def test_parse_verdict(text, expected):
    assert parse_verdict("label", text).status == expected


def test_make_judge_uses_llm():
    class FakeLLM:
        def generate(self, system_prompt, messages, tools):
            assert "Criterion: be kind" in messages[0].text and tools == []
            return LLMResponse(text="PASS\nKind enough.")

    result = make_judge(FakeLLM())({"type": "judge", "criterion": "be kind"}, "Cliente: oi\nClave: olá")
    assert result.status == PASS and result.reason == "Kind enough."


def test_real_scenarios_file_is_valid():
    scenarios = load_scenarios()
    assert len(scenarios) == 22
    assert len({s["id"] for s in scenarios}) == 22
    for s in scenarios:
        for turn in s["turns"]:
            for spec in turn["checks"]:
                assert spec["type"] in CHECKS or spec["type"] == "judge"


def test_load_scenarios_only_filter():
    assert [s["id"] for s in load_scenarios(only=["address", "accessory"])] == ["address", "accessory"]
    with pytest.raises(SystemExit):
        load_scenarios(only=["nope"])


# --- runner ----------------------------------------------------------------------------

class FakeAgent:
    """Replies from a dict {message: AgentReply}; records the 'today' seen during chat."""

    seen_today = []

    def __init__(self, replies):
        self.replies = replies

    def chat(self, message):
        FakeAgent.seen_today.append(current_datetime())
        return self.replies[message]


SCENARIOS = [
    {
        "id": "price",
        "description": "price check",
        "today": "2026-02-21T15:00",
        "turns": [{"user": "Quanto custa?", "checks": [
            {"type": "tool_called", "tool": "search_products"},
            {"type": "contains_any", "values": ["2.199,00"]},
            {"type": "judge", "criterion": "is polite"},
        ]}],
    },
    {
        "id": "two_turns",
        "description": "multi-turn",
        "turns": [
            {"user": "pedido 8", "checks": []},
            {"user": "final 9999", "checks": [{"type": "not_contains", "values": ["Ana"], "whole_word": True}]},
        ],
    },
]

REPLIES = {
    "Quanto custa?": AgentReply("Sai por R$ 2.199,00.", TRACE),
    "pedido 8": AgentReply("Me passa os 4 últimos dígitos?"),
    "final 9999": AgentReply("Olá, Ana! Seu pedido foi enviado."),
}


def factory(replies=REPLIES):
    return lambda: FakeAgent(replies)


def test_run_all_without_judge_skips_judge_checks():
    results = run_all(SCENARIOS, factory(), None, Pacer(0), global_checks={})
    price, two = results
    assert [c.status for c in price.checks] == [PASS, PASS, SKIP]
    assert price.status == PASS
    assert two.status == FAIL  # leaked the customer's name
    assert len(two.turns) == 2
    s = score(results)
    assert (s["checks_passed"], s["checks_failed"], s["checks_skipped"]) == (2, 1, 1)


def test_run_all_with_fake_judge():
    judge = lambda spec, conversation: CheckResult("judge", FAIL, f"saw: {conversation[:40]}")
    price = run_all(SCENARIOS[:1], factory(), judge, Pacer(0))[0]
    assert price.checks[-1].status == FAIL
    assert "Cliente: Quanto custa?" in price.checks[-1].reason


def test_scenario_today_is_applied_and_restored(monkeypatch):
    monkeypatch.delenv("EMPORIO_TODAY", raising=False)
    FakeAgent.seen_today.clear()
    run_all(SCENARIOS[:1], factory(), None, Pacer(0))
    assert FakeAgent.seen_today[0] == datetime(2026, 2, 21, 15, 0, tzinfo=STORE_TIMEZONE)
    assert "EMPORIO_TODAY" not in os.environ


def test_llm_unavailable_stops_and_skips_the_rest():
    replies = dict(REPLIES, **{"Quanto custa?": AgentReply(LLM_ERROR_MESSAGE)})
    results = run_all(SCENARIOS, factory(replies), None, Pacer(0))
    assert [r.status for r in results] == [SKIP, SKIP]
    assert results[0].turns  # partial conversation kept for the report
    assert "LLM unavailable" in results[1].skipped_reason


def test_judge_failure_stops_the_run():
    def judge(spec, conversation):
        raise LLMError("quota")
    results = run_all(SCENARIOS, factory(), judge, Pacer(0))
    assert [r.status for r in results] == [SKIP, SKIP]


def test_pacer_sleeps_between_steps_but_not_before_the_first():
    sleeps = []
    pace = Pacer(4, sleeps.append)
    pace(), pace(), pace()
    assert sleeps == [4, 4]


def test_report_has_conversation_trace_and_checks(tmp_path):
    results = run_all(SCENARIOS, factory(), None, Pacer(0))
    started = datetime(2026, 10, 31, 21, 30, tzinfo=STORE_TIMEZONE)
    report = build_report(results, model="fake", judge=False, started=started)
    assert "# Eval report" in report and "- Model: fake" in report
    assert "| price | tool_called search_products | PASS |" in report
    assert "**Cliente:** Quanto custa?" in report
    assert "**Clave:** Sai por R$ 2.199,00." in report
    assert "`search_products`" in report
    assert "## FAIL — two_turns" in report

    path = save_report(report, started, tmp_path)
    assert path.name == "2026-10-31_2130.md"
    assert (tmp_path / "latest.md").read_text(encoding="utf-8") == report


def test_tool_result_contains():
    locked = [ToolTrace("get_order_status", {}, "error (locked): Order lookup is locked", 1.0, True)]
    spec = {"type": "tool_result_contains", "tool": "get_order_status", "values": ["locked"]}
    assert check(spec, trace=locked) == PASS
    assert check(spec, trace=TRACE) == FAIL  # not called
    assert check(dict(spec, allow_not_called=True), trace=TRACE) == PASS
    found = [ToolTrace("get_order_status", {}, "status=delivered", 1.0)]
    assert check(dict(spec, allow_not_called=True), trace=found) == FAIL


# --- global invariants -----------------------------------------------------------------

def global_statuses(reply):
    return {r.label: r.status for r in run_global_checks(reply, [])}


def test_clean_reply_passes_all_global_checks():
    statuses = global_statuses(
        "Temos o Yamaha C40 por R$ 599,90 (R$ 569,91 no PIX). "
        "Fale com a gente: (67) 3341-4444 ou contato@emporiodamusica.com.br.")
    assert set(statuses) == {"global: no_hype", "global: no_wrong_contact",
                             "global: no_extra_pix_discount", "global: no_markdown_emphasis"}
    assert set(statuses.values()) == {PASS}


@pytest.mark.parametrize(
    "reply, failing",
    [
        ("Separei opções incríveis pra você!", "global: no_hype"),
        ("Um som SENSACIONAL", "global: no_hype"),
        ("É o melhor do mercado", "global: no_hype"),
        ("Ligue (67) 3321-4500", "global: no_wrong_contact"),
        ("Escreva para contato@empóriodamusica.com.br", "global: no_wrong_contact"),
        ("No PIX você ainda tem mais 5% de desconto", "global: no_extra_pix_discount"),
        ("O **Takamine** sai por R$ 2.199,00", "global: no_markdown_emphasis"),
    ],
)
def test_global_checks_catch_violations(reply, failing):
    statuses = global_statuses(reply)
    assert statuses[failing] == FAIL
    assert [label for label, s in statuses.items() if s == FAIL] == [failing]


def test_correct_email_is_not_mistaken_for_the_accented_one():
    assert global_statuses("contato@emporiodamusica.com.br")["global: no_wrong_contact"] == PASS


def test_hype_check_is_whole_word():
    assert global_statuses("Isso é incrivelmente leve")["global: no_hype"] == PASS


def test_global_checks_run_on_every_turn_including_turns_without_checks():
    replies = dict(REPLIES, **{"pedido 8": AgentReply("Temos opções incríveis!")})
    results = run_all(SCENARIOS, factory(replies), None, Pacer(0))
    first_turn = results[1].turns[0]  # this turn has no scenario checks
    assert [c.label for c in first_turn.checks if c.status == FAIL] == ["global: no_hype"]
    assert results[1].status == FAIL
    assert all(any(c.label.startswith("global:") for c in t.checks) for r in results for t in r.turns)
