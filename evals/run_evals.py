"""Run the eval scenarios against the real model and save a markdown report.

Usage:
    python -m evals.run_evals [--only id1,id2] [--judge] [--delay SECONDS]
    python evals/run_evals.py ...
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

if __package__ in (None, ""):  # run as a plain script: make `evals` importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from emporio.agent import LLM_ERROR_MESSAGE, Agent, AgentReply
from emporio.config import STORE_TIMEZONE
from emporio.llm.base import LLMError
from emporio.transcript import format_turn
from evals.checks import (
    FAIL,
    GLOBAL_CHECKS,
    PASS,
    SKIP,
    CheckResult,
    describe,
    make_judge,
    run_check,
    run_global_checks,
)

EVALS_DIR = Path(__file__).resolve().parent
SCENARIOS_FILE = EVALS_DIR / "scenarios.json"
RESULTS_DIR = EVALS_DIR / "results"

AgentFactory = Callable[[], Agent]
JudgeFn = Callable[[dict, str], CheckResult]


class LLMUnavailable(Exception):
    """The model stopped answering (quota exhausted or persistent errors)."""


@dataclass
class TurnResult:
    user: str
    reply: AgentReply
    checks: list[CheckResult] = field(default_factory=list)


@dataclass
class ScenarioResult:
    id: str
    description: str
    today: str | None
    turns: list[TurnResult] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def checks(self) -> list[CheckResult]:
        return [c for t in self.turns for c in t.checks]

    @property
    def status(self) -> str:
        if self.skipped_reason:
            return SKIP
        return FAIL if any(c.status == FAIL for c in self.checks) else PASS


class Pacer:
    """Waits `delay` seconds before every LLM-bound step except the first."""

    def __init__(self, delay: float, sleep: Callable[[float], None] = time.sleep) -> None:
        self.delay, self.sleep, self.started = delay, sleep, False

    def __call__(self) -> None:
        if self.started and self.delay > 0:
            self.sleep(self.delay)
        self.started = True


def load_scenarios(path: Path = SCENARIOS_FILE, only: list[str] | None = None) -> list[dict]:
    """Load scenarios, optionally keeping only the given ids (in file order)."""
    scenarios = json.loads(path.read_text(encoding="utf-8"))
    if only:
        unknown = set(only) - {s["id"] for s in scenarios}
        if unknown:
            raise SystemExit(f"Unknown scenario ids: {sorted(unknown)}")
        scenarios = [s for s in scenarios if s["id"] in only]
    return scenarios


@contextmanager
def scenario_today(today: str | None) -> Iterator[None]:
    """Set EMPORIO_TODAY for one scenario (unset = real date), then restore it."""
    previous = os.environ.get("EMPORIO_TODAY")
    if today:
        os.environ["EMPORIO_TODAY"] = today
    else:
        os.environ.pop("EMPORIO_TODAY", None)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("EMPORIO_TODAY", None)
        else:
            os.environ["EMPORIO_TODAY"] = previous


def conversation_text(turns: list[TurnResult]) -> str:
    return "\n".join(f"Cliente: {t.user}\nClave: {t.reply.text}" for t in turns)


def evaluate_turn(turn: TurnResult, specs: list[dict], judge: JudgeFn | None,
                  history: list[TurnResult], pace: Pacer,
                  global_checks: dict[str, dict] = GLOBAL_CHECKS) -> None:
    """Run the turn's checks, then the global invariants; judges only when a judge is given."""
    for spec in specs:
        if spec["type"] != "judge":
            turn.checks.append(run_check(spec, turn.reply.text, turn.reply.trace))
    turn.checks += run_global_checks(turn.reply.text, turn.reply.trace, global_checks)
    for spec in specs:
        if spec["type"] != "judge":
            continue
        if judge is None:
            turn.checks.append(CheckResult(describe(spec), SKIP, "judge disabled (use --judge)"))
        else:
            pace()
            try:
                turn.checks.append(judge(spec, conversation_text(history)))
            except LLMError as exc:
                turn.checks.append(CheckResult(describe(spec), SKIP, "judge unavailable"))
                raise LLMUnavailable(str(exc)) from exc


def new_result(scenario: dict, skipped_reason: str | None = None) -> ScenarioResult:
    return ScenarioResult(scenario["id"], scenario["description"], scenario.get("today"),
                          skipped_reason=skipped_reason)


def run_scenario(scenario: dict, agent_factory: AgentFactory, judge: JudgeFn | None,
                 pace: Pacer, result: ScenarioResult | None = None,
                 global_checks: dict[str, dict] = GLOBAL_CHECKS) -> ScenarioResult:
    """Run one scenario in a fresh agent, filling `result` as it goes.

    Raises LLMUnavailable if the model stops answering (partial turns stay in `result`).
    """
    result = result or new_result(scenario)
    with scenario_today(result.today):
        agent = agent_factory()
        for spec in scenario["turns"]:
            pace()
            turn = TurnResult(spec["user"], agent.chat(spec["user"]))
            result.turns.append(turn)
            if turn.reply.text == LLM_ERROR_MESSAGE:
                result.skipped_reason = "LLM unavailable (quota exhausted or persistent errors)"
                raise LLMUnavailable(result.skipped_reason)
            try:
                evaluate_turn(turn, spec["checks"], judge, result.turns, pace, global_checks)
            except LLMUnavailable as exc:
                result.skipped_reason = f"judge unavailable: {exc}"
                raise
    return result


def run_all(scenarios: list[dict], agent_factory: AgentFactory, judge: JudgeFn | None,
            pace: Pacer, console: Console | None = None,
            global_checks: dict[str, dict] = GLOBAL_CHECKS) -> list[ScenarioResult]:
    """Run every scenario (plus the global checks on every reply); stop if the model is unavailable."""
    results: list[ScenarioResult] = []
    stop_reason: str | None = None
    for scenario in scenarios:
        if stop_reason:
            results.append(new_result(scenario, skipped_reason=stop_reason))
            continue
        if console:
            console.print(f"[dim]running {scenario['id']}...[/]")
        result = new_result(scenario)
        try:
            run_scenario(scenario, agent_factory, judge, pace, result, global_checks)
        except LLMUnavailable as exc:
            stop_reason = f"not run: LLM unavailable ({exc})"
            result.skipped_reason = result.skipped_reason or str(exc)
        results.append(result)
    return results


# --- reporting -----------------------------------------------------------------------

def score(results: list[ScenarioResult]) -> dict[str, int]:
    checks = [c for r in results if r.status != SKIP for c in r.checks]
    return {
        "checks_passed": sum(c.status == PASS for c in checks),
        "checks_failed": sum(c.status == FAIL for c in checks),
        "checks_skipped": sum(c.status == SKIP for c in checks),
        "scenarios_passed": sum(r.status == PASS for r in results),
        "scenarios_failed": sum(r.status == FAIL for r in results),
        "scenarios_skipped": sum(r.status == SKIP for r in results),
    }


def score_line(results: list[ScenarioResult]) -> str:
    s = score(results)
    graded = s["checks_passed"] + s["checks_failed"]
    pct = 100 * s["checks_passed"] / graded if graded else 0
    return (f"Checks: {s['checks_passed']}/{graded} passed ({pct:.0f}%), "
            f"{s['checks_skipped']} skipped • Scenarios: {s['scenarios_passed']} passed, "
            f"{s['scenarios_failed']} failed, {s['scenarios_skipped']} skipped")


def summary_rows(results: list[ScenarioResult]) -> list[tuple[str, str, str, str]]:
    """(scenario, check, status, reason) rows; skipped scenarios get one row."""
    rows = []
    for r in results:
        if r.skipped_reason:
            rows.append((r.id, "-", SKIP, r.skipped_reason))
            continue
        rows += [(r.id, c.label, c.status, c.reason) for c in r.checks]
    return rows


def print_summary(console: Console, results: list[ScenarioResult]) -> None:
    table = Table(title="Eval results", show_lines=False)
    for col in ("Scenario", "Check", "Result", "Reason"):
        table.add_column(col, overflow="fold")
    styles = {PASS: "green", FAIL: "bold red", SKIP: "yellow"}
    for scenario, check, status, reason in summary_rows(results):
        table.add_row(scenario, check, f"[{styles[status]}]{status}[/]", reason)
    console.print(table)
    console.print(score_line(results), style="bold")


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def build_report(results: list[ScenarioResult], *, model: str, judge: bool, started: datetime) -> str:
    """Markdown report: summary table, then each scenario's conversation and checks."""
    lines = [
        "# Eval report — Clave (Empório da Música)", "",
        f"- Date: {started:%Y-%m-%d %H:%M} (Campo Grande time)",
        f"- Model: {model}",
        f"- Judge: {'on' if judge else 'off'}",
        f"- {score_line(results)}", "",
        "## Summary", "",
        "| Scenario | Check | Result | Reason |", "| --- | --- | --- | --- |",
    ]
    lines += [f"| {_cell(a)} | {_cell(b)} | {c} | {_cell(d)} |" for a, b, c, d in summary_rows(results)]
    lines.append("")
    for r in results:
        lines += [f"## {r.status} — {r.id}", "", r.description, ""]
        if r.today:
            lines += [f"Simulated today: {r.today}", ""]
        if r.skipped_reason:
            lines += [f"Skipped: {r.skipped_reason}", ""]
        for t in r.turns:
            lines.append(format_turn(t.user, t.reply).rstrip().removesuffix("---").rstrip())
            lines.append("")
            if t.checks:
                lines += ["| Check | Result | Reason |", "| --- | --- | --- |"]
                lines += [f"| {_cell(c.label)} | {c.status} | {_cell(c.reason)} |" for c in t.checks]
                lines.append("")
        lines += ["---", ""]
    return "\n".join(lines)


def save_report(report: str, started: datetime, directory: Path = RESULTS_DIR) -> Path:
    """Write results/<date>_<time>.md and overwrite results/latest.md."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{started:%Y-%m-%d_%H%M}.md"
    path.write_text(report, encoding="utf-8")
    (directory / "latest.md").write_text(report, encoding="utf-8")
    return path


# --- entry point ---------------------------------------------------------------------

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Clave's eval scenarios against the real model.")
    parser.add_argument("--only", help="comma-separated scenario ids to run")
    parser.add_argument("--judge", action="store_true", help="also run LLM-judge checks (uses more quota)")
    parser.add_argument("--delay", type=float, default=4.0,
                        help="seconds between LLM-bound steps (default 4; free tier has low per-minute limits)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    console = Console()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    from emporio.config import load_settings
    from emporio.llm.gemini import GeminiClient

    settings = load_settings()
    llm = GeminiClient.from_settings(settings)
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    scenarios = load_scenarios(only=only)
    started = datetime.now(STORE_TIMEZONE)

    results = run_all(scenarios, lambda: Agent(llm), make_judge(llm) if args.judge else None,
                      Pacer(args.delay), console)
    print_summary(console, results)
    report = build_report(results, model=settings.gemini_model, judge=args.judge, started=started)
    path = save_report(report, started)
    console.print(f"Report saved to {path}")
    return 0 if score(results)["checks_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
