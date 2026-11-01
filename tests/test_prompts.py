"""Tests for the system prompt: rendering, and staying in sync with tools and data."""

import re
from datetime import datetime

import pytest

from emporio.config import STORE_TIMEZONE
from emporio.prompts import build_system_prompt, load_prompt_template
from emporio.tools import get_tools

# Tool names follow a verb_noun convention; fields mentioned in the prompt
# (pix_price, max_price, return_eligibility...) never start with these verbs.
TOOL_NAME_PATTERN = re.compile(r"\b(?:get|list|search|run)_[a-z_]+\b")


@pytest.fixture(scope="module")
def prompt() -> str:
    now = datetime(2026, 3, 21, 14, 5, tzinfo=STORE_TIMEZONE)  # a Saturday
    return build_system_prompt(now)


def test_date_and_time_are_filled(prompt):
    assert "sábado, 21/03/2026, 14:05" in prompt
    assert "{{" not in prompt and "}}" not in prompt


def test_template_has_placeholders():
    template = load_prompt_template()
    for placeholder in ("{{date}}", "{{weekday}}", "{{time}}", "{{store_status}}"):
        assert placeholder in template


def test_utc_time_is_converted_to_store_time():
    now = datetime.fromisoformat("2026-03-21T18:05+00:00")
    assert "14:05" in build_system_prompt(now)


def test_sunday_prompt_says_closed_until_monday():
    sunday = datetime(2026, 3, 22, 10, 0, tzinfo=STORE_TIMEZONE)
    prompt = build_system_prompt(sunday)
    assert "fechada agora; a equipe volta segunda-feira, 23/03, às 09:00" in prompt


def test_weekday_morning_prompt_says_open():
    wednesday = datetime(2026, 3, 18, 10, 0, tzinfo=STORE_TIMEZONE)
    prompt = build_system_prompt(wednesday)
    assert "aberta agora (hoje até as 18:00)" in prompt
    assert "fechada agora; a equipe volta" not in prompt


def test_prompt_and_registry_mention_the_same_tools(prompt):
    mentioned = set(TOOL_NAME_PATTERN.findall(prompt))
    assert mentioned == set(get_tools())


def test_prompt_has_correct_contact_info(prompt):
    assert "(67) 3341-4444" in prompt
    assert "contato@emporiodamusica.com.br" in prompt
    assert "Rua 14 de Maio, 3200" in prompt


def test_prompt_has_no_wrong_contact_info(prompt):
    assert "3321-4500" not in prompt
    assert "empóriodamusica" not in prompt
