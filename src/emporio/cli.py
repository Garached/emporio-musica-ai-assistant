"""Interactive terminal chat with Clave (rich)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Callable

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

from emporio.agent import Agent, AgentReply
from emporio.config import STORE_TIMEZONE, ConfigError, load_settings, parse_today

PROMPT = "[bold cyan]Você:[/] "
GOODBYE = "Até mais! Obrigado por falar com a Empório da Música. 🎸"
COMMANDS = {
    "/ajuda": "mostra os comandos",
    "/nova": "começa uma nova conversa",
    "/debug": "liga/desliga o modo debug (mostra as ferramentas usadas)",
    "/sair": "encerra o chat",
}

AgentFactory = Callable[[], Agent]


def make_console() -> Console:
    """Console with UTF-8 output, so accents and emojis work on Windows."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    return Console()


class ChatSession:
    """One terminal session: reads input, talks to the agent, prints replies."""

    def __init__(
        self, agent_factory: AgentFactory, console: Console, *, model: str, debug: bool = False
    ) -> None:
        self.agent_factory = agent_factory
        self.console = console
        self.model = model
        self.debug = debug
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
        if not line:
            return True
        if line.startswith("/"):
            return self.run_command(line.split()[0].lower())
        self.send(line)
        return True

    def run_command(self, command: str) -> bool:
        """Run a slash command. Returns False for /sair."""
        if command == "/sair":
            return False
        if command == "/nova":
            self.new_conversation()
        elif command == "/debug":
            self.debug = not self.debug
            state = "ligado" if self.debug else "desligado"
            self.console.print(f"Modo debug {state}.", style="yellow")
        elif command == "/ajuda":
            self.show_help()
        else:
            self.console.print(f"Comando desconhecido: {command}", style="yellow")
            self.show_help()
        return True

    def new_conversation(self) -> None:
        """Start over with a fresh agent (empty history)."""
        self.agent = self.agent_factory()
        self.console.print("Nova conversa iniciada. ✨", style="yellow")

    def show_help(self) -> None:
        for name, description in COMMANDS.items():
            self.console.print(Text.assemble((f"  {name:<8}", "bold"), description))

    def send(self, message: str) -> AgentReply:
        """Send a message to the agent and print the reply."""
        with self.console.status("Clave está digitando...", spinner="dots"):
            reply = self.agent.chat(message)
        self.print_reply(reply)
        return reply

    def print_reply(self, reply: AgentReply) -> None:
        """Clave's name in color, then the reply as plain text (no markdown)."""
        self.console.print(Text("Clave: ", style="bold magenta") + Text(reply.text))
        if self.debug:
            self.print_trace(reply)
        self.console.print()

    def print_trace(self, reply: AgentReply) -> None:
        """Debug view: which tools were called, with what, and how long they took."""
        if not reply.trace:
            self.console.print("  ⚙ nenhuma ferramenta usada", style="dim")
        for t in reply.trace:
            self.console.print(
                Text(f"  ⚙ {t.name}({format_args(t.args)}) → {t.summary} ({t.duration_ms:.0f} ms)"),
                style="dim red" if t.error else "dim",
            )

    def show_welcome(self) -> None:
        body = Text.assemble(
            ("Empório da Música\n", "bold magenta"),
            ("Sua música começa aqui.\n\n", "italic"),
            (f"Atendimento com a Clave, assistente virtual • modelo: {self.model}\n", "dim"),
            ("Comandos: /ajuda /nova /debug /sair", "dim"),
        )
        self.console.print(Panel(body, border_style="magenta", expand=False))


def format_args(args: dict) -> str:
    """Render tool args compactly: query='nylon', limit=5."""
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="emporio", description="Chat com a Clave, da Empório da Música.")
    parser.add_argument("--debug", action="store_true", help="começa com o modo debug ligado")
    parser.add_argument("--today", metavar="YYYY-MM-DD[THH:MM]",
                        help='simula a data/hora "de hoje" (mesmo efeito de EMPORIO_TODAY)')
    return parser.parse_args(argv)


def apply_today(value: str) -> None:
    """Override "today" for this session. Raises ConfigError if the value is invalid."""
    parse_today(value, datetime.now(STORE_TIMEZONE))  # validate before applying
    os.environ["EMPORIO_TODAY"] = value


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
    args = parse_args(argv)
    console = console or make_console()
    setup_logging(console)
    try:
        if args.today:
            apply_today(args.today)
        factory, model = runtime or gemini_agent_factory()
    except ConfigError as exc:
        show_config_error(console, exc)
        return 1
    session = ChatSession(factory, console, model=model, debug=args.debug)
    session.run(read_input or (lambda: console.input(PROMPT)))
    return 0
