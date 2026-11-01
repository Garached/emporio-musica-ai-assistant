"""Save chat sessions as markdown transcripts (one file per conversation)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from emporio.agent import AgentReply
from emporio.config import STORE_TIMEZONE
from emporio.data import PROJECT_ROOT
from emporio.formatting import strip_markdown

TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"


def unique_path(directory: Path, started: datetime) -> Path:
    """transcripts/2026-10-31_2130.md, with _2, _3... if that name is taken."""
    stem = started.strftime("%Y-%m-%d_%H%M")
    path, n = directory / f"{stem}.md", 2
    while path.exists():
        path, n = directory / f"{stem}_{n}.md", n + 1
    return path


class Transcript:
    """A markdown transcript, appended after every turn so nothing is lost.

    The file is created on the first turn, so empty sessions leave no file.
    """

    def __init__(
        self, directory: Path, *, model: str, today: datetime, simulated_today: bool,
        started: datetime | None = None,
    ) -> None:
        self.directory = directory
        self.model = model
        self.today = today
        self.simulated_today = simulated_today
        self.started = started or datetime.now(STORE_TIMEZONE)  # real clock, store time
        self.path: Path | None = None

    def add_turn(self, user_message: str, reply: AgentReply) -> Path:
        """Append one customer message and Clave's reply (with its tool calls)."""
        if self.path is None:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.path = unique_path(self.directory, self.started)
            self.path.write_text(self._header(), encoding="utf-8")
        with self.path.open("a", encoding="utf-8") as f:
            f.write(format_turn(user_message, reply))
        return self.path

    def _header(self) -> str:
        today = self.today.strftime("%Y-%m-%d %H:%M")
        if self.simulated_today:
            today += " (simulado com --today / EMPORIO_TODAY)"
        return (
            "# Conversa com a Clave — Empório da Música\n\n"
            f"- Data: {self.started:%Y-%m-%d %H:%M}\n"
            f"- Modelo: {self.model}\n"
            f"- Hoje (horário da loja): {today}\n\n"
            "---\n\n"
        )


def format_turn(user_message: str, reply: AgentReply) -> str:
    """Markdown for one turn; tool calls listed compactly below the reply."""
    lines = [f"**Cliente:** {_hard_breaks(user_message)}", "",
             f"**Clave:** {_hard_breaks(strip_markdown(reply.text))}", ""]
    if reply.trace:
        lines.append("Ferramentas usadas:")
        for t in reply.trace:
            if t.kind != "tool":  # safeguard entries: retry / nudge / grounding
                lines.append(f"- _{t.kind}_: {t.summary}")
                if t.rejected_draft:
                    draft = " / ".join(line.strip() for line in t.rejected_draft.splitlines() if line.strip())
                    lines.append(f"  - rejected draft: «{draft}»")
                continue
            args = json.dumps(t.args, ensure_ascii=False)
            lines.append(f"- `{t.name}` `{args}` → {t.summary} ({t.duration_ms:.0f} ms)")
        lines.append("")
    lines += ["---", "", ""]
    return "\n".join(lines)


def _hard_breaks(text: str) -> str:
    """Keep the chat's line breaks in rendered markdown (two trailing spaces)."""
    return "  \n".join(line.rstrip() for line in text.strip().splitlines())
