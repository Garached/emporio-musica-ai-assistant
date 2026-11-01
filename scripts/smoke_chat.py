"""Manual smoke test: a short conversation with the real Gemini model.

Not the final CLI (that is Phase 5). Kept short because the free tier has a
low daily request limit.

Usage:
    python scripts/smoke_chat.py
"""

from __future__ import annotations

import logging
import sys

from emporio.agent import Agent
from emporio.config import load_settings
from emporio.llm.gemini import GeminiClient

MESSAGES = [
    "Oi!",
    "Quanto custa o Takamine GD20?",
    "Vocês vendem palheta?",
]


def main() -> None:
    """Run the scripted conversation and print each reply with its tool trace."""
    sys.stdout.reconfigure(encoding="utf-8")  # accents/emojis on Windows consoles
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    print(f"Model: {settings.gemini_model} (thinking level: {settings.gemini_thinking_level})\n")
    agent = Agent(GeminiClient.from_settings(settings))

    for message in MESSAGES:
        print(f"Cliente: {message}")
        reply = agent.chat(message)
        for t in reply.trace:
            print(f"  [tool] {t.name}({t.args}) -> {t.summary} ({t.duration_ms:.0f} ms)")
        print(f"Clave: {reply.text}\n")


if __name__ == "__main__":
    main()
