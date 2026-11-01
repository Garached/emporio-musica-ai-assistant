"""The example recorder runs the eval invariants and the grounding check (no network)."""

import sys
from pathlib import Path

from emporio.agent import FALLBACK_MESSAGE, AgentReply, ToolTrace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from record_examples import RecordedTurn, check_reply, checks_section  # noqa: E402


def test_clean_grounded_reply_has_no_problems():
    assert check_reply(AgentReply("O Yamaha C40 sai por R$ 599,90."), [599.9]) == []


def test_flags_invariants_ungrounded_values_and_fallback():
    problems = check_reply(AgentReply("Opções incríveis: Giannini Cerrado por R$ 428,00!"), [599.9])
    assert any(p.startswith("global: no_hype") for p in problems)
    assert any("grounding" in p and "R$ 428,00" in p for p in problems)
    assert check_reply(AgentReply(FALLBACK_MESSAGE), []) == ["fallback reply sent to the customer"]


def test_section_lists_failures_and_safeguards():
    nudge = ToolTrace("grounding", {}, "values not returned by tools: R$ 428,00", 0.0, kind="grounding")
    turns = [RecordedTurn("oi", AgentReply("ok", [nudge]), []),
             RecordedTurn("e?", AgentReply("x"), ["global: no_hype: found forbidden ['incrivel']"])]
    section = checks_section(turns)
    assert "⚠️ 1 falha(s)" in section and "Turno 2: global: no_hype" in section
    assert "Turno 1: grounding: values not returned by tools" in section
    assert "✅ Nenhuma falha." in checks_section([RecordedTurn("oi", AgentReply("ok"), [])])
