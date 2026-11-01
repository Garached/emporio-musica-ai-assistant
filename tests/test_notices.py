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


# --- official contacts in payment replies --------------------------------------------------

from emporio.notices import OFFICIAL_CONTACTS_LINE, has_official_contacts, is_payment_message  # noqa: E402


def test_payment_reply_without_contacts_gets_the_line():
    reply = agent(WEDNESDAY_MORNING, "Não temos chave PIX para te passar por aqui.").chat(
        "Me passa a chave PIX da loja pra eu pagar")
    assert reply.text == f"Não temos chave PIX para te passar por aqui.\n\n{OFFICIAL_CONTACTS_LINE}"


def test_payment_reply_with_both_contacts_is_untouched():
    text = "Pague só pelos canais oficiais: (67) 3341-4444 ou contato@emporiodamusica.com.br."
    assert agent(WEDNESDAY_MORNING, text).chat("Como faço o pagamento?").text == text


def test_only_phone_is_not_enough():
    text = "Fale com a equipe no (67) 3341-4444."
    reply = agent(WEDNESDAY_MORNING, text).chat("Recebi um link pra pagar, é de vocês?")
    assert reply.text.endswith(OFFICIAL_CONTACTS_LINE)


def test_non_payment_message_gets_no_line():
    assert agent(WEDNESDAY_MORNING, "Temos sim!").chat("Vocês têm violão Yamaha?").text == "Temos sim!"


def test_applies_on_every_turn_not_only_the_first():
    a = agent(WEDNESDAY_MORNING, "Oi!", "Não passo dados bancários.")
    a.chat("Oi")
    assert a.chat("Qual a conta bancária pra depósito?").text.endswith(OFFICIAL_CONTACTS_LINE)


def test_payment_line_comes_before_the_closed_notice():
    reply = agent(SATURDAY_AFTERNOON, "Não temos chave PIX.").chat("Qual a chave pix?")
    assert reply.text.index(OFFICIAL_CONTACTS_LINE) < reply.text.index("Nossa loja está fechada")


def test_payment_keywords_whole_word_and_accent_insensitive():
    assert is_payment_message("Posso fazer uma transferência?")
    assert is_payment_message("Já paguei, mando o comprovante?")
    assert is_payment_message("Qual a CONTA BANCÁRIA?")
    assert not is_payment_message("Quero um violão para pagode")  # "pago" only as a whole word
    assert not is_payment_message("Tem violão com captação?")
    assert has_official_contacts("(67) 3341 4444 / CONTATO@emporiodamusica.com.br")
