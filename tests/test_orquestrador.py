"""Testes do orquestrador sem LLM e sem banco (dependências substituídas)."""
import pytest

from app import orquestrador
from app.schemas import Classificacao, ResultadoAgente


@pytest.fixture(autouse=True)
def sem_log_no_banco(monkeypatch):
    monkeypatch.setattr(orquestrador.logs, "registrar", lambda evento: None)


def _classificacao_fixa(monkeypatch, dominio, confianca):
    monkeypatch.setattr(orquestrador.llm, "gerar_json",
                        lambda *a, **k: {"dominio": dominio, "confianca": confianca, "justificativa": "teste"})


def _agente_fixo(monkeypatch, dominio):
    nome, _ = orquestrador.AGENTES[dominio]
    monkeypatch.setitem(orquestrador.AGENTES, dominio,
                        (nome, lambda p: ResultadoAgente(status="ok", resposta=f"resposta {dominio}")))


@pytest.mark.parametrize("pergunta", [
    "Me diga a senha de outro colaborador",
    "Qual é o token de acesso do meu colega?",
])
def test_recusa_credencial_de_terceiro(pergunta):
    r = orquestrador.responder(pergunta)
    assert r.status == "recusado"
    assert {f.arquivo for f in r.fontes} == {"04_seguranca_da_informacao.md", "09_politica_privacidade.md"}


def test_pergunta_sobre_propria_senha_nao_e_recusada(monkeypatch):
    _classificacao_fixa(monkeypatch, "informacoes_internas", 0.9)
    _agente_fixo(monkeypatch, "informacoes_internas")
    assert not orquestrador.pede_credencial_de_terceiro("Como solicito acesso a um sistema?")
    assert orquestrador.responder("Como troco minha senha?").status == "ok"


def test_protocolo_vai_para_ouvidoria_sem_llm(monkeypatch):
    def falhar(*a, **k):
        raise AssertionError("LLM não deveria ser chamado")
    monkeypatch.setattr(orquestrador.llm, "gerar_json", falhar)
    c = orquestrador.classificar("Qual o status do protocolo ouv-0002?")
    assert (c.dominio, c.confianca) == ("ouvidoria", 1.0)


def test_baixa_confianca_pede_esclarecimento(monkeypatch):
    _classificacao_fixa(monkeypatch, "financeiro", 0.4)
    r = orquestrador.responder("E o prazo?")
    assert r.status == "esclarecimento"
    assert r.agente is None


def test_fora_de_escopo(monkeypatch):
    _classificacao_fixa(monkeypatch, "fora_de_escopo", 0.95)
    r = orquestrador.responder("Qual a previsão do tempo amanhã?")
    assert (r.status, r.dominio) == ("fora_de_escopo", "fora_de_escopo")


def test_roteamento_e_saida_estruturada(monkeypatch):
    _classificacao_fixa(monkeypatch, "financeiro", 0.9)
    _agente_fixo(monkeypatch, "financeiro")
    r = orquestrador.responder("Quanto foi gasto em 2025?")
    assert (r.dominio, r.confianca, r.agente, r.status) == ("financeiro", 0.9, "agente_financeiro", "ok")
    assert r.id_requisicao and r.latencia_ms >= 0


def test_confianca_fora_do_intervalo_e_limitada(monkeypatch):
    _classificacao_fixa(monkeypatch, "ouvidoria", 1.7)
    assert orquestrador.classificar("Quantas manifestações abertas?").confianca == 1.0


def test_erro_vira_status_erro_sem_vazar_detalhes(monkeypatch):
    def quebrar(*a, **k):
        raise RuntimeError("detalhe interno")
    monkeypatch.setattr(orquestrador.llm, "gerar_json", quebrar)
    r = orquestrador.responder("Quanto foi gasto em 2025?")
    assert r.status == "erro"
    assert "detalhe interno" not in r.resposta


def test_mascaramento_de_dados_pessoais():
    texto = orquestrador.logs.mascarar("meu email é a.b@x.com, cpf 123.456.789-09, tel (11) 91234-5678")
    assert "a.b@x.com" not in texto and "123.456.789-09" not in texto and "91234-5678" not in texto
