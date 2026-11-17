"""Funções SQL contra o PostgreSQL carregado. Valores esperados calculados de forma independente
a partir dos CSV com Decimal (não reutilizam o SQL testado)."""
from collections import defaultdict
from decimal import Decimal

import pytest

from app.agentes import financeiro, ouvidoria

pytestmark = [pytest.mark.integracao, pytest.mark.usefixtures("banco_disponivel")]


def test_t006_despesas_pagas_jan_mar_2025(lancamentos):
    esperado = sum(Decimal(l["valor_brl"]) for l in lancamentos
                   if l["tipo"] == "Despesa" and l["status"] == "Pago"
                   and "2025-01-01" <= l["data_competencia"] <= "2025-03-31")
    r = financeiro.somar_lancamentos(financeiro.ParamsSoma(
        tipo="Despesa", status=["Pago"], data_inicio="2025-01-01", data_fim="2025-03-31"))
    assert Decimal(r.dados["total_brl"]) == esperado
    assert r.fontes[0].arquivo == "lancamentos_financeiros.csv"


def test_t011_receitas_2025(lancamentos):
    esperado = sum(Decimal(l["valor_brl"]) for l in lancamentos
                   if l["tipo"] == "Receita" and l["data_competencia"].startswith("2025"))
    r = financeiro.somar_lancamentos(financeiro.ParamsSoma(
        tipo="Receita", data_inicio="2025-01-01", data_fim="2025-12-31"))
    assert Decimal(r.dados["total_brl"]) == esperado


def test_t007_maior_orcamento_jan_2026(orcamentos):
    por_depto = defaultdict(Decimal)
    for o in orcamentos:
        if o["ano"] == "2026" and o["mes"] == "01":
            por_depto[o["departamento"]] += Decimal(o["orcamento_brl"])
    maior = max(por_depto, key=por_depto.get)
    r = financeiro.consultar_orcamento(financeiro.ParamsOrcamento(ano=2026, mes="01"))
    assert r.dados["orcamentos"][0]["departamento"] == maior
    assert f"O maior orçamento é de {maior}" in r.resposta


def test_t009_protocolo_existente():
    r = ouvidoria.buscar_protocolos(["OUV-0002"])
    assert r.status == "ok"
    assert r.dados["manifestacoes"][0]["status"] == "Aguardando área responsável"


def test_t004_protocolo_inexistente_nao_e_inventado():
    r = ouvidoria.buscar_protocolos(["OUV-9999"])
    assert r.status == "nao_encontrado"
    assert "não foi encontrado" in r.resposta
    assert r.dados == {"manifestacoes": []}


def test_t005_status_validos():
    r = ouvidoria.valores_referencia(ouvidoria.ParamsReferencia(campo="status_validos"))
    assert r.dados["status_validos"] == ["Aberto", "Em análise", "Aguardando área responsável", "Respondido", "Concluído"]


def test_contagem_de_manifestacoes_por_status():
    r = ouvidoria.contar_manifestacoes(ouvidoria.ParamsContar(agrupar_por="status"))
    assert r.dados["total"] == 180
