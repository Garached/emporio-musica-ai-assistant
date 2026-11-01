"""CLI tests with a FAKE agent (no network, no API key)."""

import io
from datetime import datetime

import pytest
from rich.console import Console

from emporio.agent import AgentReply, ToolTrace
from emporio.cli import ChatSession, main
from emporio.config import STORE_TIMEZONE, current_datetime
from emporio.transcript import Transcript, format_turn

TRACE = [ToolTrace("search_products", {"query": "takamine gd20"}, "total_found=1, results=1 items", 12.0)]


class FakeAgent:
    instances = 0

    def __init__(self):
        FakeAgent.instances += 1
        self.messages = []

    def chat(self, message):
        self.messages.append(message)
        return AgentReply(f"Resposta para: {message}", TRACE)


@pytest.fixture(autouse=True)
def reset_fake():
    FakeAgent.instances = 0


@pytest.fixture
def console():
    return Console(file=io.StringIO(), width=120, color_system=None)


@pytest.fixture
def session(console, tmp_path):
    return ChatSession(FakeAgent, console, model="fake-model", transcripts_dir=tmp_path)


def output(console):
    return console.file.getvalue()


# --- commands ----------------------------------------------------------------------

def test_message_goes_to_agent_and_reply_is_printed(session, console):
    assert session.handle("Oi") is True
    assert session.agent.messages == ["Oi"]
    assert "Clave: Resposta para: Oi" in output(console)


def test_nova_starts_fresh_agent(session):
    session.handle("Oi")
    first_agent, first_transcript = session.agent, session.transcript
    assert session.handle("/nova") is True
    assert session.agent is not first_agent and session.agent.messages == []
    assert session.transcript is not first_transcript
    assert FakeAgent.instances == 2


def test_debug_toggles_trace_display(session, console):
    session.handle("sem debug")
    assert "search_products" not in output(console)
    session.handle("/debug")
    assert session.debug is True
    session.handle("com debug")
    assert "⚙ search_products(query='takamine gd20') → total_found=1" in output(console)
    session.handle("/debug")
    assert session.debug is False


def test_sair_ends_session(session):
    assert session.handle("/sair") is False
    assert session.handle("/SAIR") is False


def test_unknown_command_shows_help(session, console):
    assert session.handle("/xyz") is True
    text = output(console)
    assert "Comando desconhecido: /xyz" in text
    assert "/ajuda" in text and "/nova" in text and "/debug" in text and "/sair" in text


def test_empty_input_is_ignored(session):
    session.handle("   ")
    assert session.agent.messages == []


def test_run_loop_exits_on_sair_with_goodbye(session, console):
    inputs = iter(["Oi", "/sair", "nunca enviado"])
    session.run(lambda: next(inputs))
    assert session.agent.messages == ["Oi"]
    assert "Até mais!" in output(console)


@pytest.mark.parametrize("exc", [KeyboardInterrupt, EOFError])
def test_ctrl_c_and_ctrl_d_exit_gracefully(session, console, exc):
    def read():
        raise exc
    session.run(read)  # must not raise
    assert "Até mais!" in output(console)


# --- options -----------------------------------------------------------------------

def test_today_option_is_applied(monkeypatch, console):
    monkeypatch.setenv("EMPORIO_TODAY", "")  # restored after the test
    code = main(["--today", "2026-01-30T10:00"], runtime=(FakeAgent, "fake-model"),
                console=console, read_input=lambda: "/sair")
    assert code == 0
    assert current_datetime() == datetime(2026, 1, 30, 10, 0, tzinfo=STORE_TIMEZONE)
    assert "Data simulada: 30/01/2026 10:00" in output(console)


def test_invalid_today_shows_config_error(monkeypatch, console):
    monkeypatch.setenv("EMPORIO_TODAY", "")
    code = main(["--today", "30/01/2026"], runtime=(FakeAgent, "fake-model"), console=console)
    assert code == 1
    assert "Invalid EMPORIO_TODAY" in output(console)


def test_debug_option_starts_in_debug_mode(console, tmp_path):
    inputs = iter(["Oi", "/sair"])
    main(["--debug"], runtime=(FakeAgent, "fake-model"), console=console,
         read_input=lambda: next(inputs), transcripts_dir=tmp_path)
    assert "⚙ search_products" in output(console)


def test_missing_api_key_shows_friendly_error(monkeypatch, console):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    code = main([], console=console, read_input=lambda: "/sair")
    assert code == 1
    assert "GEMINI_API_KEY is not set" in output(console)


# --- transcripts -------------------------------------------------------------------

def test_transcript_written_after_each_message(session, tmp_path):
    session.handle("Quanto custa o GD20?")
    path = session.transcript.path
    first = path.read_text(encoding="utf-8")
    assert first.startswith("# Conversa com a Clave — Empório da Música")
    assert "- Modelo: fake-model" in first
    assert "- Hoje (horário da loja):" in first
    assert "**Cliente:** Quanto custa o GD20?" in first
    assert "**Clave:** Resposta para: Quanto custa o GD20?" in first
    assert '- `search_products` `{"query": "takamine gd20"}` → total_found=1, results=1 items (12 ms)' in first

    session.handle("Obrigado")
    assert "**Cliente:** Obrigado" in path.read_text(encoding="utf-8")
    assert len(list(tmp_path.iterdir())) == 1


def test_nova_starts_a_new_transcript_file(session, tmp_path):
    session.handle("Oi")
    session.handle("/nova")
    session.handle("Oi de novo")
    files = sorted(tmp_path.iterdir())
    assert len(files) == 2
    assert "Oi de novo" in files[1].read_text(encoding="utf-8")
    assert "Oi de novo" not in files[0].read_text(encoding="utf-8")


def test_no_file_for_empty_session(session, tmp_path):
    session.handle("/debug")
    assert list(tmp_path.iterdir()) == []


def test_transcript_name_and_simulated_today(tmp_path):
    started = datetime(2026, 10, 31, 21, 30, tzinfo=STORE_TIMEZONE)
    today = datetime(2026, 1, 30, 10, 0, tzinfo=STORE_TIMEZONE)
    transcript = Transcript(tmp_path, model="m", today=today, simulated_today=True, started=started)
    path = transcript.add_turn("Oi", AgentReply("Olá!"))
    assert path.name == "2026-10-31_2130.md"
    assert "2026-01-30 10:00 (simulado" in path.read_text(encoding="utf-8")


def test_multiline_reply_keeps_line_breaks():
    turn = format_turn("Opções?", AgentReply("Tenho:\n- Violão A\n- Violão B"))
    assert "**Clave:** Tenho:  \n- Violão A  \n- Violão B" in turn
    assert "Ferramentas usadas" not in turn  # no tools, no tool list
