"""Integração com o provedor de LLM configurado (requer API key; consome tokens)."""
import pytest

from app import orquestrador
from app.agentes import financeiro, ouvidoria
from app.agentes.ferramentas import executar_agente

pytestmark = [pytest.mark.integracao, pytest.mark.usefixtures("chave_llm")]


@pytest.mark.parametrize("pergunta, dominio", [
    ("Como solicito férias?", "informacoes_internas"),
    ("Qual foi a soma de todas as receitas registradas em 2025?", "financeiro"),
    ("Quais status podem aparecer na ouvidoria?", "ouvidoria"),
    ("Qual a previsão do tempo para amanhã em São Paulo?", "fora_de_escopo"),
])
def test_classificacao(pergunta, dominio):
    c = orquestrador.classificar(pergunta)
    assert c.dominio == dominio
    assert 0 <= c.confianca <= 1


def test_escolha_de_ferramenta_financeira(monkeypatch):
    capturado = {}

    def falso(p):
        capturado["p"] = p
        return financeiro.ResultadoAgente(status="ok", resposta="ok")

    ferramentas = [f if f.nome != "somar_lancamentos" else
                   financeiro.Ferramenta(f.nome, f.descricao, f.parametros, falso) for f in financeiro.FERRAMENTAS]
    r = executar_agente(financeiro.SYSTEM,
                        "Quanto foi gasto em despesas pagas no período de janeiro a março de 2025?", ferramentas)
    assert r.ferramenta == "somar_lancamentos"
    p = capturado["p"]
    assert (p.tipo, p.status, str(p.data_inicio), str(p.data_fim)) == ("Despesa", ["Pago"], "2025-01-01", "2025-03-31")


def test_escolha_de_ferramenta_ouvidoria():
    r = executar_agente(ouvidoria.SYSTEM, "Quais status podem aparecer na ouvidoria?",
                        [f for f in ouvidoria.FERRAMENTAS if f.nome == "valores_referencia"])
    assert r.ferramenta == "valores_referencia"
    assert r.parametros == {"campo": "status_validos"}
