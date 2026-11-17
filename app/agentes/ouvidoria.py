"""Agente de Ouvidoria: funções SQL predefinidas e parametrizadas (sem SQL gerado pelo modelo).

Regras de `data/ouvidoria/referencia_ouvidoria.json`: nunca inventar protocolo, não inferir identidade,
prazo de 10 dias é fictício, diferenciar abertura de resposta e Respondido de Concluído.
"""
import json
import re
from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agentes.ferramentas import Ferramenta, executar_agente
from app.config import config
from app.db import consultar
from app.formatacao import data_br, serializavel
from app.schemas import Fonte, ResultadoAgente

FONTE_MANIFESTACOES = "manifestacoes.csv"
FONTE_REFERENCIA = "referencia_ouvidoria.json"
PADRAO_PROTOCOLO = re.compile(r"\bOUV-\d{4}\b", re.IGNORECASE)
AVISO_PRAZO = "O prazo de referência de 10 dias é um parâmetro fictício de demonstração, não prazo legal."

StatusOuv = Literal["Aberto", "Em análise", "Aguardando área responsável", "Respondido", "Concluído"]
Prioridade = Literal["Baixa", "Média", "Alta", "Crítica"]
CategoriaOuv = Literal["Cobrança", "Atendimento", "Produto ou serviço", "Cancelamento", "Reembolso",
                       "Privacidade", "Elogio", "Sugestão"]
Canal = Literal["Portal", "E-mail", "Telefone", "Chat"]


@lru_cache
def referencia() -> dict:
    caminho = config.dir_dados / "ouvidoria" / FONTE_REFERENCIA
    return json.loads(caminho.read_text(encoding="utf-8"))


class _Filtros(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: StatusOuv | None = None
    categoria: CategoriaOuv | None = None
    prioridade: Prioridade | None = None
    canal_entrada: Canal | None = None
    data_inicio: date | None = Field(None, description="Início do período de abertura (AAAA-MM-DD).")
    data_fim: date | None = Field(None, description="Fim do período de abertura (AAAA-MM-DD), inclusivo.")

    @model_validator(mode="after")
    def _validar_periodo(self):
        if self.data_inicio and self.data_fim and self.data_inicio > self.data_fim:
            raise ValueError("data_inicio maior que data_fim")
        return self

    def descricao(self) -> str:
        partes = [f"{c} = {v}" for c, v in self.model_dump(exclude_none=True).items()
                  if c not in ("data_inicio", "data_fim", "agrupar_por", "limite")]
        if self.data_inicio or self.data_fim:
            ini = data_br(self.data_inicio) if self.data_inicio else "o início"
            fim = data_br(self.data_fim) if self.data_fim else "hoje"
            partes.append(f"abertura entre {ini} e {fim}")
        return "; ".join(partes) if partes else "sem filtros"


class ParamsContar(_Filtros):
    agrupar_por: Literal["status", "categoria", "prioridade", "canal_entrada", "area_responsavel", "mes"] | None = None


class ParamsListar(_Filtros):
    limite: int = Field(10, ge=1, le=20)


class ParamsReferencia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campo: Literal["status_validos", "prioridades_validas", "categorias", "regras", "protocolo_format"]


FILTROS_SQL = """
  (%(status)s::text IS NULL OR status = %(status)s)
  AND (%(categoria)s::text IS NULL OR categoria = %(categoria)s)
  AND (%(prioridade)s::text IS NULL OR prioridade = %(prioridade)s)
  AND (%(canal_entrada)s::text IS NULL OR canal_entrada = %(canal_entrada)s)
  AND (%(data_inicio)s::date IS NULL OR data_abertura >= %(data_inicio)s::date)
  AND (%(data_fim)s::date IS NULL OR data_abertura <= %(data_fim)s::date)
"""

SQL_PROTOCOLOS = """
SELECT protocolo, data_abertura, categoria, assunto, canal_entrada, prioridade, status,
       area_responsavel, resumo_manifestacao, data_resposta, resposta_resumo, prazo_referencia_dias
FROM manifestacoes_ouvidoria
WHERE protocolo = ANY(%(protocolos)s::text[])
"""


def buscar_protocolos(protocolos: list[str]) -> ResultadoAgente:
    """Busca exata por protocolo; chamada diretamente pelo orquestrador, sem LLM."""
    protocolos = list(dict.fromkeys(p.upper() for p in protocolos))[:5]
    encontrados = {l["protocolo"]: l for l in consultar(SQL_PROTOCOLOS, {"protocolos": protocolos})}
    partes = []
    for p in protocolos:
        l = encontrados.get(p)
        if not l:
            partes.append(f"O protocolo {p} não foi encontrado na base da ouvidoria.")
            continue
        texto = (f"Protocolo {p}: status \"{l['status']}\", categoria {l['categoria']} ({l['assunto']}), "
                 f"prioridade {l['prioridade']}, aberto em {data_br(l['data_abertura'])} via {l['canal_entrada']}, "
                 f"área responsável: {l['area_responsavel']}.")
        if l["data_resposta"]:
            texto += f" Respondido em {data_br(l['data_resposta'])}: {l['resposta_resumo']}"
        else:
            texto += " Ainda sem resposta registrada."
        if l["status"] == "Respondido":
            texto += " Observação: \"Respondido\" não significa necessariamente \"Concluído\"."
        partes.append(texto)
    return ResultadoAgente(
        status="ok" if encontrados else "nao_encontrado",
        resposta=" ".join(partes),
        fontes=[Fonte(arquivo=FONTE_MANIFESTACOES, ids=list(encontrados))],
        dados={"manifestacoes": serializavel(list(encontrados.values()))},
        ferramenta="buscar_protocolo",
        parametros={"protocolos": protocolos},
    )


COLUNAS_AGRUPAMENTO = {
    "status": "status",
    "categoria": "categoria",
    "prioridade": "prioridade",
    "canal_entrada": "canal_entrada",
    "area_responsavel": "area_responsavel",
    "mes": "to_char(data_abertura, 'YYYY-MM')",
}


def contar_manifestacoes(p: ParamsContar) -> ResultadoAgente:
    params = p.model_dump()
    if p.agrupar_por:
        sql = (f"SELECT {COLUNAS_AGRUPAMENTO[p.agrupar_por]} AS grupo, COUNT(*) AS quantidade "
               f"FROM manifestacoes_ouvidoria WHERE {FILTROS_SQL} GROUP BY 1 ORDER BY quantidade DESC, grupo")
        linhas = consultar(sql, params)
        total = sum(l["quantidade"] for l in linhas)
        itens = "; ".join(f"{l['grupo']}: {l['quantidade']}" for l in linhas)
        resposta = f"Manifestações ({p.descricao()}) por {p.agrupar_por}: {itens or 'nenhuma'}. Total: {total}."
        dados = {"grupos": linhas, "total": total}
    else:
        total = consultar(f"SELECT COUNT(*) AS quantidade FROM manifestacoes_ouvidoria WHERE {FILTROS_SQL}",
                          params)[0]["quantidade"]
        resposta = f"Há {total} manifestação(ões) com {p.descricao()}."
        dados = {"total": total}
    return ResultadoAgente(status="ok" if total else "nao_encontrado", resposta=resposta,
                           fontes=[Fonte(arquivo=FONTE_MANIFESTACOES)], dados=serializavel(dados))


def listar_manifestacoes(p: ParamsListar) -> ResultadoAgente:
    sql = (f"SELECT protocolo, data_abertura, categoria, assunto, prioridade, status, area_responsavel "
           f"FROM manifestacoes_ouvidoria WHERE {FILTROS_SQL} ORDER BY data_abertura DESC, protocolo "
           f"LIMIT %(limite)s")
    linhas = consultar(sql, p.model_dump())
    if not linhas:
        return ResultadoAgente(status="nao_encontrado", resposta=f"Nenhuma manifestação encontrada com {p.descricao()}.",
                               fontes=[Fonte(arquivo=FONTE_MANIFESTACOES)])
    itens = "; ".join(f"{l['protocolo']} ({data_br(l['data_abertura'])}, {l['categoria']}, {l['status']})" for l in linhas)
    return ResultadoAgente(
        status="ok",
        resposta=f"Manifestações mais recentes com {p.descricao()} (até {p.limite}): {itens}.",
        fontes=[Fonte(arquivo=FONTE_MANIFESTACOES, ids=[l["protocolo"] for l in linhas])],
        dados={"manifestacoes": serializavel(linhas)},
    )


ROTULOS_REFERENCIA = {
    "status_validos": "Status possíveis na ouvidoria",
    "prioridades_validas": "Prioridades possíveis",
    "categorias": "Categorias de manifestação",
    "regras": "Regras da ouvidoria",
    "protocolo_format": "Formato do protocolo",
}


def valores_referencia(p: ParamsReferencia) -> ResultadoAgente:
    valor = referencia()[p.campo]
    texto = "; ".join(valor) if isinstance(valor, list) else str(valor)
    resposta = f"{ROTULOS_REFERENCIA[p.campo]}: {texto}."
    if p.campo == "status_validos":
        resposta += " Observação: \"Respondido\" não é necessariamente igual a \"Concluído\"."
    return ResultadoAgente(status="ok", resposta=resposta, fontes=[Fonte(arquivo=FONTE_REFERENCIA)],
                           dados={p.campo: valor})


FERRAMENTAS = [
    Ferramenta("contar_manifestacoes",
               "Conta manifestações da ouvidoria com filtros opcionais (status, categoria, prioridade, canal, período de abertura), podendo agrupar.",
               ParamsContar, contar_manifestacoes),
    Ferramenta("listar_manifestacoes",
               "Lista até 20 manifestações mais recentes que atendem aos filtros.",
               ParamsListar, listar_manifestacoes),
    Ferramenta("valores_referencia",
               "Retorna os valores oficiais da ouvidoria: status válidos, prioridades, categorias, regras ou formato do protocolo.",
               ParamsReferencia, valores_referencia),
]

SYSTEM = """Você é o agente de Ouvidoria da Aurora Serviços Digitais S.A. (empresa fictícia).
Escolha exatamente UMA ferramenta e preencha os parâmetros a partir da pergunta.
- As manifestações têm data de abertura entre 2026-01-05 e 2026-10-11.
- Perguntas sobre quais status, prioridades ou categorias existem => valores_referencia.
- Não invente filtros que a pergunta não pede. Não tente identificar pessoas: a base não tem dados pessoais.
- Se nenhuma ferramenta servir, não chame ferramenta."""


def responder(pergunta: str) -> ResultadoAgente:
    protocolos = PADRAO_PROTOCOLO.findall(pergunta)
    if protocolos:
        return buscar_protocolos(protocolos)
    resultado = executar_agente(SYSTEM, pergunta, FERRAMENTAS)
    if resultado.ferramenta in ("contar_manifestacoes", "listar_manifestacoes") and "prazo" in pergunta.lower():
        resultado.resposta += " " + AVISO_PRAZO
    return resultado
