"""Camada de LLM com provedor configurável (LLM_PROVIDER = gemini | anthropic).

Os agentes usam só duas operações, iguais para os dois provedores:
- gerar_json: resposta em JSON que segue um JSON Schema (saída estruturada);
- escolher_ferramenta: o modelo escolhe UMA ferramenta predefinida e seus parâmetros.

As API keys são lidas pelos SDKs das variáveis de ambiente (GEMINI_API_KEY ou ANTHROPIC_API_KEY);
nunca são passadas no código. Os clientes só são criados na primeira chamada, então importar este
módulo (e rodar os testes unitários) não exige chave.
"""
import json
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Protocol

from app.config import config

# Tokens consumidos na requisição atual, para os logs.
uso_tokens: ContextVar[dict[str, int]] = ContextVar("uso_tokens")


class ErroLLM(Exception):
    pass


def _registrar_uso(entrada: int | None, saida: int | None) -> None:
    try:
        uso = uso_tokens.get()
    except LookupError:
        return
    uso["entrada"] += entrada or 0
    uso["saida"] += saida or 0


def _json(texto: str) -> dict:
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ErroLLM("Resposta do LLM não é um JSON válido.") from exc


class Provedor(Protocol):
    def gerar_json(self, model: str, system: str, mensagem: str, schema: dict, max_tokens: int) -> dict: ...

    def escolher_ferramenta(self, model: str, system: str, mensagem: str, tools: list[dict],
                            max_tokens: int) -> tuple[str, dict] | None: ...


class ProvedorGemini:
    """Google Gemini via SDK oficial `google-genai`."""

    def __init__(self, cliente=None):
        self._cliente = cliente

    @property
    def cliente(self):
        if self._cliente is None:
            from google import genai
            from google.genai import types

            # Repete com backoff exponencial em 408/429/5xx (ex.: 503 de sobrecarga no nível gratuito),
            # como o SDK da Anthropic já faz por padrão.
            self._cliente = genai.Client(http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=config.llm_tentativas)))
        return self._cliente

    def _chamar(self, model: str, mensagem: str, config_geracao):
        from google.genai import errors

        try:
            resposta = self.cliente.models.generate_content(model=model, contents=mensagem, config=config_geracao)
        except errors.APIError as exc:
            raise ErroLLM(f"Falha na chamada ao LLM (Gemini): {type(exc).__name__} {exc.code}") from exc
        uso = resposta.usage_metadata
        if uso:
            _registrar_uso(uso.prompt_token_count, uso.candidates_token_count)
        feedback = resposta.prompt_feedback
        if feedback and feedback.block_reason:
            raise ErroLLM("O modelo recusou a solicitação.")
        return resposta

    def gerar_json(self, model, system, mensagem, schema, max_tokens):
        from google.genai import types

        resposta = self._chamar(model, mensagem, types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_json_schema=schema,
        ))
        return _json(resposta.text)

    def escolher_ferramenta(self, model, system, mensagem, tools, max_tokens):
        from google.genai import types

        declaracoes = [
            types.FunctionDeclaration(name=t["name"], description=t["description"],
                                      parameters_json_schema=t["input_schema"])
            for t in tools
        ]
        resposta = self._chamar(model, mensagem, types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            tools=[types.Tool(function_declarations=declaracoes)],
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO")),
            # O SDK não executa funções sozinho: quem executa é o nosso código, após validar.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ))
        for chamada in resposta.function_calls or []:
            return chamada.name, dict(chamada.args or {})
        return None


class ProvedorAnthropic:
    """Anthropic Claude via SDK oficial `anthropic`."""

    def __init__(self, cliente=None):
        self._cliente = cliente

    @property
    def cliente(self):
        if self._cliente is None:
            import anthropic

            self._cliente = anthropic.Anthropic()
        return self._cliente

    @staticmethod
    def _opcoes_fallback(model: str) -> dict[str, Any]:
        # O fallback do servidor só existe para Sonnet/Opus; o Haiku não tem.
        if config.llm_fallback == "off" or not model.startswith(("claude-sonnet", "claude-opus")):
            return {}
        return {
            "extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
            "extra_body": {"fallbacks": config.llm_fallback},
        }

    def _chamar(self, model: str, **kwargs):
        import anthropic

        try:
            resposta = self.cliente.messages.create(model=model, **kwargs, **self._opcoes_fallback(model))
        except anthropic.APIError as exc:
            raise ErroLLM(f"Falha na chamada ao LLM (Anthropic): {type(exc).__name__}") from exc
        _registrar_uso(resposta.usage.input_tokens, resposta.usage.output_tokens)
        if resposta.stop_reason == "refusal":
            raise ErroLLM("O modelo recusou a solicitação.")
        return resposta

    def gerar_json(self, model, system, mensagem, schema, max_tokens):
        resposta = self._chamar(
            model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": mensagem}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        return _json("".join(b.text for b in resposta.content if b.type == "text"))

    def escolher_ferramenta(self, model, system, mensagem, tools, max_tokens):
        resposta = self._chamar(
            model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": mensagem}],
            tools=[{**t, "strict": True} for t in tools],
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            output_config={"effort": "low"},
        )
        for bloco in resposta.content:
            if bloco.type == "tool_use":
                return bloco.name, dict(bloco.input)
        return None


PROVEDORES: dict[str, type] = {"gemini": ProvedorGemini, "anthropic": ProvedorAnthropic}
PREFIXO_MODELO = {"gemini": "gemini", "anthropic": "claude"}


@lru_cache
def provedor() -> Provedor:
    if config.llm_provider not in PROVEDORES:
        raise ErroLLM(f"LLM_PROVIDER inválido: {config.llm_provider!r} (use: {', '.join(PROVEDORES)})")
    prefixo = PREFIXO_MODELO[config.llm_provider]
    for variavel, modelo in (("LLM_MODEL", config.llm_model), ("LLM_MODEL_ORQUESTRADOR", config.llm_model_orquestrador)):
        if not modelo.startswith(prefixo):
            raise ErroLLM(f"{variavel}={modelo!r} não é um modelo de {config.llm_provider}; "
                          f"deixe vazio para usar o padrão do provedor.")
    return PROVEDORES[config.llm_provider]()


def gerar_json(model: str, system: str, mensagem: str, schema: dict, max_tokens: int = 4000) -> dict:
    return provedor().gerar_json(model, system, mensagem, schema, max_tokens)


def escolher_ferramenta(model: str, system: str, mensagem: str, tools: list[dict],
                        max_tokens: int = 4000) -> tuple[str, dict] | None:
    """Pede ao modelo que escolha UMA ferramenta predefinida. Retorna (nome, parâmetros) ou None."""
    return provedor().escolher_ferramenta(model, system, mensagem, tools, max_tokens)
