"""Modelos de entrada e saída da API."""
from typing import Any, Literal

from pydantic import BaseModel, Field

Dominio = Literal["financeiro", "informacoes_internas", "ouvidoria", "fora_de_escopo"]
Status = Literal["ok", "nao_encontrado", "esclarecimento", "recusado", "fora_de_escopo", "erro"]


class PerguntaEntrada(BaseModel):
    pergunta: str = Field(min_length=3, max_length=1000)


class Classificacao(BaseModel):
    dominio: Dominio
    confianca: float = Field(ge=0, le=1)
    justificativa: str = ""


class Fonte(BaseModel):
    arquivo: str
    ids: list[str] = []
    secao: str | None = None


class ResultadoAgente(BaseModel):
    status: Status
    resposta: str
    fontes: list[Fonte] = []
    dados: dict[str, Any] | None = None
    ferramenta: str | None = None
    parametros: dict[str, Any] | None = None


class RespostaOrquestrador(BaseModel):
    id_requisicao: str
    pergunta: str
    dominio: Dominio | None
    confianca: float
    agente: str | None
    status: Status
    resposta: str
    fontes: list[Fonte] = []
    dados: dict[str, Any] | None = None
    latencia_ms: int
