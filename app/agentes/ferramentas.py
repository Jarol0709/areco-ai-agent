"""Estrutura comum das funções predefinidas dos agentes Financeiro e Ouvidoria.

O modelo só escolhe uma ferramenta e seus parâmetros. O código valida os parâmetros com
Pydantic e executa a função correspondente, que contém SQL fixo e parametrizado.
"""
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, ValidationError

from app import llm
from app.config import config
from app.schemas import ResultadoAgente


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    parametros: type[BaseModel]
    executar: Callable[[BaseModel], ResultadoAgente]

    def definicao(self) -> dict:
        """Definição neutra; cada provedor em `app.llm` a converte para o seu formato."""
        return {
            "name": self.nome,
            "description": self.descricao,
            "input_schema": schema_estrito(self.parametros),
        }


def schema_estrito(modelo: type[BaseModel]) -> dict:
    """JSON Schema do Pydantic sem metadados extras e com additionalProperties=false."""
    schema = modelo.model_json_schema()

    def limpar(no):
        if isinstance(no, dict):
            no.pop("title", None)
            no.pop("default", None)
            if no.get("type") == "object":
                no["additionalProperties"] = False
            for valor in no.values():
                limpar(valor)
        elif isinstance(no, list):
            for item in no:
                limpar(item)

    limpar(schema)
    return schema


def executar_agente(system: str, pergunta: str, ferramentas: list[Ferramenta]) -> ResultadoAgente:
    por_nome = {f.nome: f for f in ferramentas}
    escolha = llm.escolher_ferramenta(
        config.llm_model, system, pergunta, [f.definicao() for f in ferramentas]
    )
    if escolha is None or escolha[0] not in por_nome:
        return ResultadoAgente(
            status="esclarecimento",
            resposta="Não consegui identificar a consulta. Pode detalhar o período, o tipo ou o filtro desejado?",
        )
    nome, entrada = escolha
    ferramenta = por_nome[nome]
    try:
        params = ferramenta.parametros.model_validate(entrada)
    except ValidationError as exc:
        campos = ", ".join(str(e["loc"][0]) for e in exc.errors() if e["loc"])
        return ResultadoAgente(
            status="esclarecimento",
            resposta=f"Os parâmetros da consulta são inválidos ({campos or 'parâmetros'}). Pode reformular a pergunta?",
            ferramenta=nome,
            parametros=entrada,
        )
    resultado = ferramenta.executar(params)
    resultado.ferramenta = nome
    resultado.parametros = params.model_dump(mode="json", exclude_none=True)
    return resultado
