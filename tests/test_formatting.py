"""Tests for stripping markdown from replies before display."""

import io

import pytest
from rich.console import Console

from emporio.agent import AgentReply
from emporio.cli import ChatSession
from emporio.formatting import strip_markdown
from emporio.transcript import format_turn


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("O **Takamine GD20** é ótimo", "O Takamine GD20 é ótimo"),
        ("Sai por **R$ 2.199,00** no cartão", "Sai por R$ 2.199,00 no cartão"),
        ("Um *violão* leve", "Um violão leve"),
        ("__Atenção__: estoque baixo", "Atenção: estoque baixo"),
        ("## Opções\n- A", "Opções\n- A"),
        ("* Yamaha\n* Tagima", "- Yamaha\n- Tagima"),
    ],
)
def test_emphasis_and_headings_are_removed(raw, expected):
    assert strip_markdown(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Conta: 2 * 3 = 6",
        "contato@emporiodamusica.com.br",
        "campo pix_price e max_price",
        "- item normal",
        "Sem formatação nenhuma 🎸",
    ],
)
def test_plain_text_is_untouched(text):
    assert strip_markdown(text) == text


def test_cli_and_transcript_show_stripped_text(tmp_path):
    console = Console(file=io.StringIO(), width=120, color_system=None)

    class FakeAgent:
        def chat(self, message):
            return AgentReply("O **GD20** sai por **R$ 2.199,00**.")

    session = ChatSession(FakeAgent, console, model="m", transcripts_dir=tmp_path)
    session.handle("Preço?")
    assert "Clave: O GD20 sai por R$ 2.199,00." in console.file.getvalue()
    assert "**Clave:** O GD20 sai por R$ 2.199,00." in session.transcript.path.read_text(encoding="utf-8")
    assert "**GD20**" not in format_turn("x", AgentReply("**GD20**"))
