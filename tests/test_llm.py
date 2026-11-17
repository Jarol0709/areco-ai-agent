"""Adaptadores de LLM com clientes falsos: sem rede e sem API key."""
import os
from types import SimpleNamespace

import pytest
from google.genai import types

from app import llm
from tests.conftest import VARIAVEIS_DE_CHAVE

FERRAMENTA = {"name": "somar", "description": "Soma.",
              "input_schema": {"type": "object", "properties": {"a": {"type": "integer"}},
                               "required": ["a"], "additionalProperties": False}}


class GeminiFalso:
    def __init__(self, resposta):
        self.resposta, self.chamadas = resposta, []
        self.models = self

    def generate_content(self, **kwargs):
        self.chamadas.append(kwargs)
        return self.resposta


def resposta_gemini(*partes):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(partes)))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=10, candidates_token_count=5),
    )


class AnthropicFalso:
    def __init__(self, resposta):
        self.resposta, self.chamadas = resposta, []
        self.messages = self

    def create(self, **kwargs):
        self.chamadas.append(kwargs)
        return self.resposta


def resposta_anthropic(*blocos, stop_reason="end_turn"):
    return SimpleNamespace(content=list(blocos), stop_reason=stop_reason,
                           usage=SimpleNamespace(input_tokens=7, output_tokens=3))


def test_testes_unitarios_rodam_sem_chave():
    assert not any(os.getenv(v) for v in VARIAVEIS_DE_CHAVE)


def test_gemini_gerar_json_usa_schema_e_conta_tokens():
    falso = GeminiFalso(resposta_gemini(types.Part(text='{"dominio": "ouvidoria"}')))
    uso = {"entrada": 0, "saida": 0}
    token = llm.uso_tokens.set(uso)
    try:
        saida = llm.ProvedorGemini(falso).gerar_json("gemini-x", "sys", "msg", {"type": "object"}, 100)
    finally:
        llm.uso_tokens.reset(token)
    assert saida == {"dominio": "ouvidoria"}
    cfg = falso.chamadas[0]["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema == {"type": "object"}
    assert cfg.system_instruction == "sys"
    assert uso == {"entrada": 10, "saida": 5}


def test_gemini_escolher_ferramenta():
    falso = GeminiFalso(resposta_gemini(types.Part(function_call=types.FunctionCall(name="somar", args={"a": 2}))))
    assert llm.ProvedorGemini(falso).escolher_ferramenta("gemini-x", "sys", "msg", [FERRAMENTA], 100) == ("somar", {"a": 2})
    cfg = falso.chamadas[0]["config"]
    declaracao = cfg.tools[0].function_declarations[0]
    assert declaracao.name == "somar"
    assert declaracao.parameters_json_schema == FERRAMENTA["input_schema"]
    assert cfg.automatic_function_calling.disable is True


def test_gemini_sem_chamada_de_ferramenta_retorna_none():
    falso = GeminiFalso(resposta_gemini(types.Part(text="Falta o período.")))
    assert llm.ProvedorGemini(falso).escolher_ferramenta("gemini-x", "sys", "msg", [FERRAMENTA], 100) is None


def test_gemini_json_invalido_vira_erro_llm():
    falso = GeminiFalso(resposta_gemini(types.Part(text="não é json")))
    with pytest.raises(llm.ErroLLM):
        llm.ProvedorGemini(falso).gerar_json("gemini-x", "sys", "msg", {"type": "object"}, 100)


def test_anthropic_escolher_ferramenta_adiciona_strict():
    falso = AnthropicFalso(resposta_anthropic(SimpleNamespace(type="tool_use", name="somar", input={"a": 1})))
    resultado = llm.ProvedorAnthropic(falso).escolher_ferramenta("claude-haiku-5-5", "sys", "msg", [FERRAMENTA], 100)
    assert resultado == ("somar", {"a": 1})
    assert falso.chamadas[0]["tools"][0]["strict"] is True


def test_anthropic_gerar_json_e_recusa():
    falso = AnthropicFalso(resposta_anthropic(SimpleNamespace(type="text", text='{"ok": true}')))
    assert llm.ProvedorAnthropic(falso).gerar_json("claude-haiku-5-5", "s", "m", {"type": "object"}, 100) == {"ok": True}
    recusa = AnthropicFalso(resposta_anthropic(stop_reason="refusal"))
    with pytest.raises(llm.ErroLLM):
        llm.ProvedorAnthropic(recusa).gerar_json("claude-haiku-5-5", "s", "m", {"type": "object"}, 100)


def test_fallback_so_para_sonnet_e_opus():
    assert llm.ProvedorAnthropic._opcoes_fallback("claude-haiku-5-5") == {}
    assert "extra_body" in llm.ProvedorAnthropic._opcoes_fallback("claude-sonnet-5-5")


def _configurar(monkeypatch, provedor, agentes, orquestrador):
    monkeypatch.setattr(llm, "config", SimpleNamespace(
        llm_provider=provedor, llm_model=agentes, llm_model_orquestrador=orquestrador))
    llm.provedor.cache_clear()


@pytest.mark.parametrize("nome, modelos, classe", [
    ("gemini", ("gemini-3.8-flash", "gemini-3.5-flash-lite"), llm.ProvedorGemini),
    ("anthropic", ("claude-sonnet-5-5", "claude-haiku-5-5"), llm.ProvedorAnthropic),
])
def test_selecao_de_provedor(monkeypatch, nome, modelos, classe):
    _configurar(monkeypatch, nome, *modelos)
    assert isinstance(llm.provedor(), classe)


def test_provedor_invalido(monkeypatch):
    _configurar(monkeypatch, "openai", "gpt", "gpt")
    with pytest.raises(llm.ErroLLM, match="LLM_PROVIDER inválido"):
        llm.provedor()


def test_modelo_de_outro_provedor_e_rejeitado(monkeypatch):
    _configurar(monkeypatch, "gemini", "claude-sonnet-5-5", "gemini-3.5-flash-lite")
    with pytest.raises(llm.ErroLLM, match="LLM_MODEL='claude-sonnet-5-5' não é um modelo de gemini"):
        llm.provedor()


def test_cliente_gemini_configura_retentativas(monkeypatch):
    from google import genai
    capturado = {}
    monkeypatch.setattr(genai, "Client", lambda **kwargs: capturado.update(kwargs) or object())
    llm.ProvedorGemini().cliente
    assert capturado["http_options"].retry_options.attempts == llm.config.llm_tentativas >= 2


def test_criar_provedor_nao_exige_chave():
    # O cliente real só é criado na primeira chamada; instanciar o adaptador não precisa de chave.
    llm.ProvedorGemini()
    llm.ProvedorAnthropic()


def test_mascaramento_de_segredos_nos_logs():
    from app.logs import mascarar
    texto = mascarar("chave AIza" + "x" * 35 + " e sk-ant-api03-abc_DEF e api_key=12345")
    assert "AIza" not in texto and "sk-ant" not in texto and "12345" not in texto
