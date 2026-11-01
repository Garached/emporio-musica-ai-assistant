"""Deterministic eval checks (plus the optional LLM judge).

Each check gets the check spec (from scenarios.json) and the turn's reply and
tool trace, and returns a CheckResult. Text checks ignore case and accents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from emporio.agent import ToolTrace
from emporio.llm.base import LLMClient, Message
from emporio.tools import normalize

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check."""

    label: str
    status: str
    reason: str = ""


def describe(spec: dict[str, Any]) -> str:
    """Short human label for a check, e.g. "tool_called search_products"."""
    kind = spec["type"]
    detail = {k: v for k, v in spec.items() if k != "type"}
    if "tool" in detail and len(detail) == 1:
        return f"{kind} {detail['tool']}"
    if "values" in detail:
        return f"{kind} {detail['values']}"
    if kind == "judge":
        return f"judge: {spec['criterion']}"
    return f"{kind} {detail}"


# --- helpers -------------------------------------------------------------------------

def _tool_calls(trace: Sequence[ToolTrace]) -> list[ToolTrace]:
    """Real tool calls only (nudges from the announce-then-stop safeguard are not tools)."""
    return [t for t in trace if getattr(t, "kind", "tool") == "tool"]


def _tools(spec: dict[str, Any]) -> list[str]:
    tool = spec["tool"]
    return [tool] if isinstance(tool, str) else list(tool)


def _matches(text: str, value: str, whole_word: bool, accent_sensitive: bool = False) -> bool:
    if accent_sensitive:  # e.g. "empóriodamusica" must not match the correct "emporiodamusica"
        text, value = text.casefold(), value.casefold()
    else:
        text, value = normalize(text), normalize(value)
    if whole_word:
        return re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text) is not None
    return value in text


def parse_brl(raw: str) -> float:
    """Parse a BRL amount: "1.967,18", "2.199", "1000", "439.20" -> float."""
    if "," in raw:
        return float(raw.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+\.\d{2}", raw):
        return float(raw)
    return float(raw.replace(".", ""))


def prices_in(text: str) -> list[float]:
    """All R$ amounts mentioned in a text."""
    return [parse_brl(m) for m in re.findall(r"R\$\s?(\d[\d.]*(?:,\d{1,2})?)", text)]


# --- checks --------------------------------------------------------------------------

def tool_called(spec: dict, reply: str, trace: Sequence[ToolTrace]) -> CheckResult:
    wanted = _tools(spec)
    called = [t.name for t in _tool_calls(trace)]
    ok = any(name in called for name in wanted)
    return CheckResult(describe(spec), PASS if ok else FAIL, f"called: {called or 'none'}")


def tool_not_called(spec: dict, reply: str, trace: Sequence[ToolTrace]) -> CheckResult:
    """`tool` may be a name, a list of names, or "*" for "no tool at all"."""
    called = [t.name for t in _tool_calls(trace)]
    bad = called if spec["tool"] == "*" else [n for n in called if n in _tools(spec)]
    return CheckResult(describe(spec), FAIL if bad else PASS, f"called: {called or 'none'}")


def tool_args(spec: dict, reply: str, trace: Sequence[ToolTrace]) -> CheckResult:
    """Some call of `tool` had (at least) these argument values."""
    expected: dict = spec["args"]

    def same(a: Any, b: Any) -> bool:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return float(a) == float(b)
        return a == b

    calls = [t.args for t in _tool_calls(trace) if t.name == spec["tool"]]
    ok = any(all(k in args and same(args[k], v) for k, v in expected.items()) for args in calls)
    return CheckResult(describe(spec), PASS if ok else FAIL, f"{spec['tool']} args: {calls or 'not called'}")


def tool_result_contains(spec: dict, reply: str, trace: Sequence[ToolTrace]) -> CheckResult:
    """Every call of `tool` in this turn had a result summary containing one of `values`.

    If the tool was not called there is nothing to verify, so the check FAILS
    (no vacuous pass): put the check on the turn where the tool really runs.
    """
    summaries = [t.summary for t in _tool_calls(trace) if t.name == spec["tool"]]
    if not summaries:
        return CheckResult(describe(spec), FAIL, f"{spec['tool']} not called, nothing to verify")
    ok = all(any(_matches(s, v, False) for v in spec["values"]) for s in summaries)
    return CheckResult(describe(spec), PASS if ok else FAIL, f"results: {summaries}")


def _found(spec: dict, reply: str) -> list[str]:
    """Values of `spec` present in the reply (options: whole_word, accent_sensitive)."""
    whole, sensitive = spec.get("whole_word", False), spec.get("accent_sensitive", False)
    return [v for v in spec["values"] if _matches(reply, v, whole, sensitive)]


def contains_any(spec: dict, reply: str, trace: Sequence[ToolTrace]) -> CheckResult:
    found = _found(spec, reply)
    return CheckResult(describe(spec), PASS if found else FAIL,
                       f"found {found}" if found else "none of the values found")


def not_contains(spec: dict, reply: str, trace: Sequence[ToolTrace]) -> CheckResult:
    """No forbidden value in the reply. An empty reply fails: nothing to verify."""
    if not reply.strip():
        return CheckResult(describe(spec), FAIL, "empty reply, nothing to verify")
    found = _found(spec, reply)
    return CheckResult(describe(spec), FAIL if found else PASS,
                       f"found forbidden {found}" if found else "ok")


def max_price_in_reply(spec: dict, reply: str, trace: Sequence[ToolTrace]) -> CheckResult:
    """No R$ value above `max`.

    max 0 means "no prices at all". With max > 0 the reply is expected to show
    prices, so a reply without any price fails (no vacuous pass).
    """
    if not reply.strip():
        return CheckResult(describe(spec), FAIL, "empty reply, nothing to verify")
    prices = prices_in(reply)
    if spec["max"] > 0 and not prices:
        return CheckResult(describe(spec), FAIL, "no prices in reply, nothing to verify")
    too_high = [p for p in prices if p > spec["max"]]
    return CheckResult(describe(spec), FAIL if too_high else PASS,
                       f"prices above {spec['max']}: {too_high}" if too_high else f"prices: {prices}")


CHECKS: dict[str, Callable[[dict, str, Sequence[ToolTrace]], CheckResult]] = {
    "tool_called": tool_called,
    "tool_not_called": tool_not_called,
    "tool_args": tool_args,
    "tool_result_contains": tool_result_contains,
    "contains_any": contains_any,
    "not_contains": not_contains,
    "max_price_in_reply": max_price_in_reply,
}


def run_check(spec: dict, reply: str, trace: Sequence[ToolTrace]) -> CheckResult:
    """Run one deterministic check. Judge checks are handled by `judge_check`."""
    check = CHECKS.get(spec["type"])
    if check is None:
        return CheckResult(describe(spec), FAIL, f"unknown check type {spec['type']!r}")
    return check(spec, reply, trace)


# --- global invariants: applied to EVERY Clave reply in every scenario --------------------

PIX_EXTRA_PHRASES = ["mais 5%", "5% a mais", "adicional de 5", "5% adicional", "5% extra",
                     "extra de 5", "desconto extra no pix", "ainda tem 5%"]

GLOBAL_CHECKS: dict[str, dict] = {
    "no_hype": {"type": "not_contains", "whole_word": True, "values": [
        "incrivel", "incriveis", "sensacional", "sensacionais", "espetacular", "espetaculares",
        "fantastico", "fantastica", "fantasticos", "fantasticas", "o melhor do mercado"]},
    "no_wrong_contact": {"type": "not_contains", "accent_sensitive": True,
                         "values": ["3321-4500", "empóriodamusica"]},
    "no_extra_pix_discount": {"type": "not_contains", "values": PIX_EXTRA_PHRASES},
    "no_markdown_emphasis": {"type": "not_contains", "values": ["**"]},
}


def run_global_checks(reply: str, trace: Sequence[ToolTrace],
                      checks: dict[str, dict] = GLOBAL_CHECKS) -> list[CheckResult]:
    """Run the invariants on one reply; rows are labeled "global: <name>"."""
    results = []
    for name, spec in checks.items():
        r = run_check(spec, reply, trace)
        results.append(CheckResult(f"global: {name}", r.status, r.reason))
    return results


# --- LLM judge -----------------------------------------------------------------------

JUDGE_PROMPT = """You are a strict evaluator of a customer service assistant for a Brazilian musical instrument store.
You get a conversation and ONE criterion about the assistant's LAST reply.
Answer on the first line with exactly PASS or FAIL, then one short sentence explaining why.
Answer FAIL if the criterion is not clearly met."""


def make_judge(llm: LLMClient) -> Callable[[dict, str], CheckResult]:
    """Build a judge that evaluates a criterion against a conversation transcript."""

    def judge(spec: dict, conversation: str) -> CheckResult:
        prompt = f"Conversation:\n{conversation}\n\nCriterion: {spec['criterion']}"
        response = llm.generate(JUDGE_PROMPT, [Message.user(prompt)], [])
        return parse_verdict(describe(spec), response.text or "")

    return judge


def parse_verdict(label: str, text: str) -> CheckResult:
    """Read PASS/FAIL from the judge's first word; anything else counts as FAIL."""
    text = text.strip()
    first = text.split(maxsplit=1)[0].strip(".:*").upper() if text else ""
    reason = text.split("\n", 1)[-1].strip() if "\n" in text else text
    if first in (PASS, FAIL):
        return CheckResult(label, first, reason)
    return CheckResult(label, FAIL, f"unparseable judge answer: {text[:80]!r}")
