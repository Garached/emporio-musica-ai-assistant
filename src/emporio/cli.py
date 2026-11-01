"""Interactive terminal chat with Clave (rich)."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

from emporio.agent import Agent, AgentReply
from emporio.config import ConfigError, load_settings

PROMPT = "[bold cyan]Você:[/] "
GOODBYE = "Até mais! Obrigado por falar com a Empório da Música. 🎸"

AgentFactory = Callable[[], Agent]


def make_console() -> Console:
    """Console with UTF-8 output, so accents and emojis work on Windows."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    return Console()


class ChatSession:
    """One terminal session: reads input, talks to the agent, prints replies."""

    def __init__(self, agent_factory: AgentFactory, console: Console, *, model: str) -> None:
        self.agent_factory = agent_factory
        self.console = console
        self.model = model
        self.agent = agent_factory()

    def run(self, read_input: Callable[[], str]) -> None:
        """Main loop. Ctrl+C / Ctrl+D end the session gracefully."""
        self.show_welcome()
        try:
            while True:
                if not self.handle(read_input()):
                    break
        except (KeyboardInterrupt, EOFError):
            self.console.print()
        self.console.print(GOODBYE, style="bold magenta")

    def handle(self, line: str) -> bool:
        """Process one input line. Returns False when the session should end."""
        line = line.strip()
        if line:
            self.send(line)
        return True

    def send(self, message: str) -> AgentReply:
        """Send a message to the agent and print the reply."""
        with self.console.status("Clave está digitando...", spinner="dots"):
            reply = self.agent.chat(message)
        self.print_reply(reply)
        return reply

    def print_reply(self, reply: AgentReply) -> None:
        """Clave's name in color, then the reply as plain text (no markdown)."""
        self.console.print(Text("Clave: ", style="bold magenta") + Text(reply.text))
        self.console.print()

    def show_welcome(self) -> None:
        body = Text.assemble(
            ("Empório da Música\n", "bold magenta"),
            ("Sua música começa aqui.\n\n", "italic"),
            (f"Atendimento com a Clave, assistente virtual • modelo: {self.model}\n", "dim"),
            ("Comandos: /ajuda /nova /debug /sair", "dim"),
        )
        self.console.print(Panel(body, border_style="magenta", expand=False))


def gemini_agent_factory() -> tuple[AgentFactory, str]:
    """Build the real agent factory (Gemini). Raises ConfigError if config is missing."""
    from emporio.llm.gemini import GeminiClient

    settings = load_settings()
    llm = GeminiClient.from_settings(settings)
    return (lambda: Agent(llm)), settings.gemini_model


def show_config_error(console: Console, error: Exception) -> None:
    console.print(Panel(str(error), title="Configuração", border_style="red", expand=False))


def setup_logging(console: Console) -> None:
    """Show warnings (e.g. retries) discreetly, without tracebacks."""
    handler = RichHandler(console=console, show_time=False, show_path=False, markup=False)
    logging.basicConfig(level=logging.WARNING, handlers=[handler], format="%(message)s", force=True)


def main(
    argv: list[str] | None = None,
    *,
    runtime: tuple[AgentFactory, str] | None = None,
    console: Console | None = None,
    read_input: Callable[[], str] | None = None,
) -> int:
    """CLI entry point. `runtime`, `console` and `read_input` are injectable for tests."""
    argparse.ArgumentParser(prog="emporio").parse_args(argv)
    console = console or make_console()
    setup_logging(console)
    try:
        factory, model = runtime or gemini_agent_factory()
    except ConfigError as exc:
        show_config_error(console, exc)
        return 1
    session = ChatSession(factory, console, model=model)
    session.run(read_input or (lambda: console.input(PROMPT)))
    return 0
