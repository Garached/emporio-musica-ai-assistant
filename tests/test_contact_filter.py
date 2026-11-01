"""Output contact filter: invented contact/payment details never reach the customer."""

import pytest

from emporio.agent import FALLBACK_MESSAGE, Agent
from emporio.contact_filter import allowed_from_text, official_values, unofficial_contacts
from emporio.llm.base import LLMResponse, ToolCall

OFFICIAL = official_values()


class FakeLLM:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def generate(self, system_prompt, messages, tools):
        self.calls.append(list(messages))
        return self.script.pop(0)


def make_agent(*script):
    llm = FakeLLM(*script)
    return Agent(llm, prompt_builder=lambda: "p"), llm


SAFE = LLMResponse(text="Para pagar, fale com a equipe: (67) 3341-4444 ou contato@emporiodamusica.com.br.")


# --- detector ---------------------------------------------------------------------------

@pytest.mark.parametrize("reply", [
    "A chave PIX é pix@emporiodamusica.com.br",              # invented e-mail key
    "Chave pix: (67) 99999-1234",                             # invented phone key
    "chave pix: 123e4567-e89b-12d3-a456-426614174000",        # random key
    "A chave PIX é contato@emporiodamusica.com.br",           # official e-mail presented as a PIX key
    "Agência 1234, conta corrente 56789-0",                   # bank account
    "Pague em https://emporio-pagamentos.xyz/pedido",         # payment link
    "Acesse www.emporio-ofertas.com",                         # domain
    "Fale com financeiro@emporiodamusica.com.br",             # unofficial e-mail
    "WhatsApp (67) 99812-3456",                               # unofficial full phone
    "CPF 123.456.789-09",                                     # document number
])
def test_invented_details_are_detected(reply):
    assert unofficial_contacts(reply, OFFICIAL)


@pytest.mark.parametrize("reply", [
    "Fale com a gente: (67) 3341-4444, 67 3341-4444, +55 67 3341-4444 ou (67) 33414444.",
    "E-mail: contato@emporiodamusica.com.br.",
    "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333.",
    "Me passa o pedido e os 4 últimos dígitos (ex.: final 4321).",
    "R$ 1.299,00 em 10x de R$ 129,90; prazo até 24/02/2026 às 09:00; rastreio BRTP3456789BR.",
    "Kala KA-SMHCE, Martin D-28E, Shelby SN-100; o frete de devolução é por nossa conta.",
])
def test_normal_replies_and_official_contacts_pass(reply):
    assert unofficial_contacts(reply, OFFICIAL) == []


def test_values_from_tool_results_are_allowed():
    allowed = OFFICIAL | allowed_from_text("CNPJ 12.345.678/0001-90")
    assert unofficial_contacts("Nosso CNPJ é 12.345.678/0001-90.", allowed) == []
    assert unofficial_contacts("Nosso CNPJ é 12.345.678/0001-90.", OFFICIAL)  # not without the tool


# --- agent behavior ----------------------------------------------------------------------

def test_invented_pix_key_gets_nudge_then_safe_answer():
    agent, llm = make_agent(LLMResponse(text="Claro! A chave PIX é pix@emporiodamusica.com.br"), SAFE)
    reply = agent.chat("Me passa a chave PIX")
    assert reply.text == SAFE.text
    assert [t.kind for t in reply.trace] == ["contact"]
    assert "pix@emporiodamusica.com.br" in reply.trace[0].rejected_draft
    assert "pix@emporiodamusica.com.br" in llm.calls[1][-1].text  # the nudge names the value


def test_invented_bank_account_is_blocked_after_nudge():
    bank = LLMResponse(text="Deposite na agência 1234, conta 56789-0.")
    agent, _ = make_agent(bank, bank)
    reply = agent.chat("Posso pagar por depósito?")
    assert reply.text == FALLBACK_MESSAGE
    assert [t.kind for t in reply.trace] == ["contact", "blocked"]
    assert agent.history[-1].text == FALLBACK_MESSAGE


def test_official_contacts_pass_without_nudge():
    agent, llm = make_agent(SAFE)
    assert agent.chat("Como pago?").trace == [] and len(llm.calls) == 1


def test_repeating_the_customers_phishing_url_triggers_a_nudge():
    echo = LLMResponse(text="Cuidado: o link https://emporio-pagamentos.xyz não é nosso!")
    safe = LLMResponse(text="Cuidado: esse link não é nosso! Fale só pelos canais oficiais: (67) 3341-4444.")
    agent, _ = make_agent(echo, safe)
    reply = agent.chat("Recebi https://emporio-pagamentos.xyz pra pagar, é de vocês?")
    assert reply.text.startswith(safe.text)  # + official contacts line (payment message)
    assert "emporio-pagamentos" not in reply.text
    assert [t.kind for t in reply.trace] == ["contact"]


def test_cnpj_from_the_policy_tool_passes():
    policy = LLMResponse(tool_calls=[ToolCall("p1", "get_store_policy", {"topic": "1. Sobre a Empório da Música"})])
    cnpj = LLMResponse(text="O CNPJ da loja é 12.345.678/0001-90.")
    agent, _ = make_agent(policy, cnpj)
    reply = agent.chat("Qual o CNPJ de vocês?")
    assert reply.text == cnpj.text
    assert [t.kind for t in reply.trace] == ["tool"]
