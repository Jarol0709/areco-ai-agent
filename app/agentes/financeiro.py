"""Agente Financeiro: funções SQL predefinidas e parametrizadas (sem SQL gerado pelo modelo).

Regras de `data/financeiro/indicadores_e_regras.json`:
- valores em NUMERIC/Decimal, nunca float;
- despesas realizadas = tipo Despesa e status Pago; incorridas = todos os status (critério explícito);
- filtros de período usam data_competencia, não data_vencimento.
"""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agentes.ferramentas import Ferramenta, executar_agente
from app.db import consultar
from app.formatacao import brl, data_br, percentual, serializavel
from app.schemas import Fonte, ResultadoAgente

INICIO_DADOS = date(2025, 1, 1)
FIM_DADOS = date(2026, 12, 31)
FONTE_LANCAMENTOS = "lancamentos_financeiros.csv"
FONTE_ORCAMENTO = "orcamento_mensal.csv"

Tipo = Literal["Receita", "Despesa"]
StatusFin = Literal["Pago", "Pendente", "Atrasado"]
Departamento = Literal["Comercial", "Financeiro", "Marketing", "Operações", "Recursos Humanos", "Tecnologia"]
CentroCusto = Literal["CC100", "CC200", "CC300", "CC400", "CC500", "CC600"]
Categoria = Literal[
    "Impostos e taxas", "Infraestrutura cloud", "Marketing", "Material de escritório",
    "Receita de serviços", "Salários e encargos", "Serviços profissionais",
    "Software e licenças", "Treinamento", "Viagens",
]
Mes = Literal["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Periodo(_Base):
    data_inicio: date = Field(description="Início do período de competência (AAAA-MM-DD).")
    data_fim: date = Field(description="Fim do período de competência (AAAA-MM-DD), inclusivo.")

    @model_validator(mode="after")
    def _validar_periodo(self):
        if self.data_inicio > self.data_fim:
            raise ValueError("data_inicio maior que data_fim")
        if self.data_inicio < INICIO_DADOS or self.data_fim > FIM_DADOS:
            raise ValueError("período fora da base (2025-01-01 a 2026-12-31)")
        return self


class ParamsSoma(_Periodo):
    tipo: Tipo
    status: list[StatusFin] | None = Field(
        None, description="Filtrar status. Use ['Pago'] para valores efetivamente pagos/realizados; omita para incorridos."
    )
    departamento: Departamento | None = None
    centro_custo: CentroCusto | None = None
    categoria: Categoria | None = None


class ParamsAgrupar(_Periodo):
    tipo: Tipo
    agrupar_por: Literal["departamento", "categoria", "centro_custo", "status", "mes"]
    status: list[StatusFin] | None = None


class ParamsOrcamento(_Base):
    ano: Literal[2025, 2026]
    mes: Mes | None = Field(None, description="Mês com dois dígitos; omita para o ano inteiro.")
    departamento: Departamento | None = None


class ParamsExecucao(_Base):
    ano: Literal[2025, 2026]
    mes: Mes | None = Field(None, description="Mês com dois dígitos; omita para o ano inteiro.")
    centro_custo: CentroCusto | None = None


class ParamsInadimplencia(_Periodo):
    pass


def _filtros_texto(p: BaseModel) -> str:
    partes = []
    for campo in ("status", "departamento", "centro_custo", "categoria"):
        valor = getattr(p, campo, None)
        if valor:
            partes.append(f"{campo} = {', '.join(valor) if isinstance(valor, list) else valor}")
    return f" ({'; '.join(partes)})" if partes else ""


SQL_SOMA = """
SELECT COALESCE(SUM(valor_brl), 0) AS total, COUNT(*) AS quantidade
FROM lancamentos_financeiros
WHERE tipo = %(tipo)s
  AND data_competencia BETWEEN %(data_inicio)s AND %(data_fim)s
  AND (%(status)s::text[] IS NULL OR status = ANY(%(status)s::text[]))
  AND (%(departamento)s::text IS NULL OR departamento = %(departamento)s)
  AND (%(centro_custo)s::text IS NULL OR centro_custo = %(centro_custo)s)
  AND (%(categoria)s::text IS NULL OR categoria = %(categoria)s)
"""


def somar_lancamentos(p: ParamsSoma) -> ResultadoAgente:
    linha = consultar(SQL_SOMA, p.model_dump())[0]
    total, qtd = linha["total"], linha["quantidade"]
    criterio = "status Pago (realizado)" if p.status == ["Pago"] else (
        f"status {', '.join(p.status)}" if p.status else "todos os status (incorrido)"
    )
    resposta = (
        f"O total de lançamentos do tipo {p.tipo} com competência entre {data_br(p.data_inicio)} e "
        f"{data_br(p.data_fim)}{_filtros_texto(p)} é {brl(total)}, em {qtd} lançamento(s). "
        f"Critério: tipo = {p.tipo}, {criterio}, filtro por data de competência."
    )
    return ResultadoAgente(
        status="ok" if qtd else "nao_encontrado",
        resposta=resposta if qtd else "Não há lançamentos que atendam aos filtros informados.",
        fontes=[Fonte(arquivo=FONTE_LANCAMENTOS)],
        dados=serializavel({"total_brl": total, "quantidade": qtd}),
    )


# Colunas de agrupamento permitidas: mapeamento fixo, nunca texto vindo do modelo.
COLUNAS_AGRUPAMENTO = {
    "departamento": "departamento",
    "categoria": "categoria",
    "centro_custo": "centro_custo",
    "status": "status",
    "mes": "to_char(data_competencia, 'YYYY-MM')",
}

SQL_AGRUPAR = """
SELECT {coluna} AS grupo, SUM(valor_brl) AS total, COUNT(*) AS quantidade
FROM lancamentos_financeiros
WHERE tipo = %(tipo)s
  AND data_competencia BETWEEN %(data_inicio)s AND %(data_fim)s
  AND (%(status)s::text[] IS NULL OR status = ANY(%(status)s::text[]))
GROUP BY 1
ORDER BY total DESC
"""


def agrupar_lancamentos(p: ParamsAgrupar) -> ResultadoAgente:
    sql = SQL_AGRUPAR.format(coluna=COLUNAS_AGRUPAMENTO[p.agrupar_por])
    linhas = consultar(sql, p.model_dump())
    if not linhas:
        return ResultadoAgente(status="nao_encontrado", resposta="Não há lançamentos que atendam aos filtros informados.",
                               fontes=[Fonte(arquivo=FONTE_LANCAMENTOS)])
    itens = "; ".join(f"{l['grupo']}: {brl(l['total'])} ({l['quantidade']})" for l in linhas)
    resposta = (
        f"Lançamentos do tipo {p.tipo} entre {data_br(p.data_inicio)} e {data_br(p.data_fim)}{_filtros_texto(p)}, "
        f"por {p.agrupar_por} (maior para menor): {itens}."
    )
    return ResultadoAgente(status="ok", resposta=resposta, fontes=[Fonte(arquivo=FONTE_LANCAMENTOS)],
                           dados={"grupos": serializavel(linhas)})


SQL_ORCAMENTO = """
SELECT departamento, centro_custo, SUM(orcamento_brl) AS orcamento
FROM orcamento_mensal
WHERE ano = %(ano)s
  AND (%(mes)s::text IS NULL OR mes = %(mes)s)
  AND (%(departamento)s::text IS NULL OR departamento = %(departamento)s)
GROUP BY departamento, centro_custo
ORDER BY orcamento DESC
"""


def consultar_orcamento(p: ParamsOrcamento) -> ResultadoAgente:
    linhas = consultar(SQL_ORCAMENTO, p.model_dump())
    periodo = f"{p.mes}/{p.ano}" if p.mes else str(p.ano)
    if not linhas:
        return ResultadoAgente(status="nao_encontrado", resposta=f"Não há orçamento registrado para {periodo}.",
                               fontes=[Fonte(arquivo=FONTE_ORCAMENTO)])
    maior = linhas[0]
    itens = "; ".join(f"{l['departamento']} ({l['centro_custo']}): {brl(l['orcamento'])}" for l in linhas)
    resposta = f"Orçamento aprovado em {periodo}, do maior para o menor: {itens}."
    if len(linhas) > 1:
        resposta += f" O maior orçamento é de {maior['departamento']}, com {brl(maior['orcamento'])}."
    return ResultadoAgente(status="ok", resposta=resposta, fontes=[Fonte(arquivo=FONTE_ORCAMENTO)],
                           dados={"orcamentos": serializavel(linhas)})


SQL_EXECUCAO = """
WITH orc AS (
    SELECT centro_custo, departamento, SUM(orcamento_brl) AS orcamento
    FROM orcamento_mensal
    WHERE ano = %(ano)s
      AND (%(mes)s::text IS NULL OR mes = %(mes)s)
      AND (%(centro_custo)s::text IS NULL OR centro_custo = %(centro_custo)s)
    GROUP BY centro_custo, departamento
), desp AS (
    SELECT centro_custo, SUM(valor_brl) AS despesas
    FROM lancamentos_financeiros
    WHERE tipo = 'Despesa' AND status = 'Pago'
      AND EXTRACT(YEAR FROM data_competencia) = %(ano)s
      AND (%(mes)s::text IS NULL OR to_char(data_competencia, 'MM') = %(mes)s)
    GROUP BY centro_custo
)
SELECT orc.centro_custo, orc.departamento, orc.orcamento, COALESCE(desp.despesas, 0) AS despesas
FROM orc LEFT JOIN desp USING (centro_custo)
ORDER BY orc.centro_custo
"""


def execucao_orcamentaria(p: ParamsExecucao) -> ResultadoAgente:
    linhas = consultar(SQL_EXECUCAO, p.model_dump())
    periodo = f"{p.mes}/{p.ano}" if p.mes else str(p.ano)
    if not linhas:
        return ResultadoAgente(status="nao_encontrado", resposta=f"Não há orçamento registrado para {periodo}.",
                               fontes=[Fonte(arquivo=FONTE_ORCAMENTO)])
    for l in linhas:
        l["execucao"] = (l["despesas"] / l["orcamento"]) if l["orcamento"] else None
    itens = "; ".join(
        f"{l['departamento']} ({l['centro_custo']}): {brl(l['despesas'])} de {brl(l['orcamento'])}"
        f" = {percentual(l['execucao']) if l['execucao'] is not None else 'n/d'}"
        for l in linhas
    )
    resposta = (f"Execução orçamentária em {periodo} (despesas pagas ÷ orçamento aprovado, "
                f"por centro de custo): {itens}.")
    return ResultadoAgente(status="ok", resposta=resposta,
                           fontes=[Fonte(arquivo=FONTE_LANCAMENTOS), Fonte(arquivo=FONTE_ORCAMENTO)],
                           dados={"execucao": serializavel(linhas)})


SQL_INADIMPLENCIA = """
SELECT COALESCE(SUM(valor_brl), 0) AS total_receitas,
       COALESCE(SUM(valor_brl) FILTER (WHERE status = 'Atrasado'), 0) AS receitas_atrasadas
FROM lancamentos_financeiros
WHERE tipo = 'Receita' AND data_competencia BETWEEN %(data_inicio)s AND %(data_fim)s
"""


def inadimplencia_recebiveis(p: ParamsInadimplencia) -> ResultadoAgente:
    l = consultar(SQL_INADIMPLENCIA, p.model_dump())[0]
    if not l["total_receitas"]:
        return ResultadoAgente(status="nao_encontrado", resposta="Não há receitas registradas no período.",
                               fontes=[Fonte(arquivo=FONTE_LANCAMENTOS)])
    taxa = l["receitas_atrasadas"] / l["total_receitas"]
    resposta = (
        f"Inadimplência de recebíveis entre {data_br(p.data_inicio)} e {data_br(p.data_fim)}: {percentual(taxa)} "
        f"(receitas com status Atrasado {brl(l['receitas_atrasadas'])} ÷ total de receitas {brl(l['total_receitas'])})."
    )
    return ResultadoAgente(status="ok", resposta=resposta, fontes=[Fonte(arquivo=FONTE_LANCAMENTOS)],
                           dados=serializavel({**l, "taxa": taxa}))


FERRAMENTAS = [
    Ferramenta("somar_lancamentos",
               "Soma o valor e conta lançamentos financeiros de um tipo (Receita/Despesa) num período de competência, com filtros opcionais.",
               ParamsSoma, somar_lancamentos),
    Ferramenta("agrupar_lancamentos",
               "Totaliza lançamentos de um tipo num período, agrupados por departamento, categoria, centro de custo, status ou mês.",
               ParamsAgrupar, agrupar_lancamentos),
    Ferramenta("consultar_orcamento",
               "Lista o orçamento aprovado por departamento/centro de custo para um ano ou mês, do maior para o menor.",
               ParamsOrcamento, consultar_orcamento),
    Ferramenta("execucao_orcamentaria",
               "Calcula a execução orçamentária (despesas pagas ÷ orçamento aprovado) por centro de custo num ano ou mês.",
               ParamsExecucao, execucao_orcamentaria),
    Ferramenta("inadimplencia_recebiveis",
               "Calcula a inadimplência de recebíveis (receitas Atrasado ÷ total de receitas) num período.",
               ParamsInadimplencia, inadimplencia_recebiveis),
]

SYSTEM = """Você é o agente Financeiro da Aurora Serviços Digitais S.A. (empresa fictícia).
Escolha exatamente UMA ferramenta e preencha os parâmetros a partir da pergunta.
- A base cobre competências de 2025-01-01 a 2026-12-31.
- "Gasto", "pago", "realizado" ou "efetivamente pago" => status ["Pago"]. Sem essa indicação, omita status.
- Períodos como "janeiro a março de 2025" => data_inicio 2025-01-01 e data_fim 2025-03-31. Um ano inteiro => 01-01 a 12-31.
- Não invente filtros que a pergunta não pede.
- Se a pergunta não puder ser respondida por nenhuma ferramenta ou faltar o período, não chame ferramenta e explique o que falta."""


def responder(pergunta: str) -> ResultadoAgente:
    return executar_agente(SYSTEM, pergunta, FERRAMENTAS)
