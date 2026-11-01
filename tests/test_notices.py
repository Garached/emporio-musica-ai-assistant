"""Closed-store notice on the first reply (policy 7.1), enforced in code."""

from datetime import datetime

from emporio.agent import FALLBACK_MESSAGE, Agent
from emporio.config import STORE_TIMEZONE
from emporio.llm.base import LLMResponse
from emporio.notices import closed_notice, mentions_reopening
from emporio.tools import get_store_hours_status

SATURDAY_AFTERNOON = get_store_hours_status(now=datetime(2026, 2, 21, 15, 0, tzinfo=STORE_TIMEZONE))
SUNDAY_EVENING = get_store_hours_status(now=datetime(2026, 2, 22, 19, 0, tzinfo=STORE_TIMEZONE))
WEDNESDAY_MORNING = get_store_hours_status(now=datetime(2026, 2, 18, 10, 0, tzinfo=STORE_TIMEZONE))


class FakeLLM:
    def __init__(self, *texts):
        self.texts = list(texts)

    def generate(self, system_prompt, messages, tools):
        return LLMResponse(text=self.texts.pop(0))


def agent(status, *texts):
    return Agent(FakeLLM(*texts), prompt_builder=lambda: "p", hours_status=lambda: status)


def test_notice_appended_when_closed_and_missing():
    reply = agent(SATURDAY_AFTERNOON, "Olá! Sou a Clave. Como posso ajudar?").chat("Oi!")
    assert reply.text.startswith("Olá! Sou a Clave. Como posso ajudar?")
    assert reply.text.endswith(
        "Nossa loja está fechada agora e a equipe volta segunda-feira, 23/02, às 09:00. "
        "Enquanto isso, sigo te ajudando por aqui.")


def test_no_duplicate_when_reply_already_says_when_it_reopens():
    text = "Oi! A loja está fechada, a equipe volta segunda às 9h. Posso ajudar?"
    assert agent(SATURDAY_AFTERNOON, text).chat("Oi!").text == text


def test_only_on_the_first_reply():
    a = agent(SATURDAY_AFTERNOON, "Oi! Como posso ajudar?", "Temos violões, sim.")
    assert "fechada" in a.chat("Oi!").text
    assert a.chat("Tem violão?").text == "Temos violões, sim."


def test_no_notice_when_open():
    assert agent(WEDNESDAY_MORNING, "Oi!").chat("Oi").text == "Oi!"


def test_fallback_reply_gets_no_notice_and_does_not_count_as_first():
    a = agent(SATURDAY_AFTERNOON, "", "", "Oi! Como posso ajudar?")  # empty twice -> fallback
    assert a.chat("Oi").text == FALLBACK_MESSAGE
    assert "fechada" in a.chat("Oi de novo").text


def test_mentions_reopening_variants():
    assert mentions_reopening("Voltamos amanhã às 09:00", SUNDAY_EVENING)  # Monday is tomorrow
    assert mentions_reopening("A equipe retorna em 23/02, 9h", SATURDAY_AFTERNOON)
    assert not mentions_reopening("Voltamos segunda", SATURDAY_AFTERNOON)  # no time
    assert not mentions_reopening("Voltamos às 9h", SATURDAY_AFTERNOON)  # no day
    assert closed_notice(WEDNESDAY_MORNING) is None
