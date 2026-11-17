import pytest
from pydantic import ValidationError

from app.agentes import financeiro, ouvidoria
from app.formatacao import brl, percentual


@pytest.mark.parametrize("ferramenta", financeiro.FERRAMENTAS + ouvidoria.FERRAMENTAS, ids=lambda f: f.nome)
def test_definicao_da_ferramenta_e_estrita(ferramenta):
    definicao = ferramenta.definicao()
    assert set(definicao) == {"name", "description", "input_schema"}
    assert definicao["input_schema"]["additionalProperties"] is False
    assert "title" not in definicao["input_schema"]


def test_parametro_desconhecido_e_rejeitado():
    with pytest.raises(ValidationError):
        financeiro.ParamsSoma.model_validate(
            {"tipo": "Despesa", "data_inicio": "2025-01-01", "data_fim": "2025-03-31", "sql": "DROP TABLE x"})


@pytest.mark.parametrize("inicio, fim", [("2024-01-01", "2024-12-31"), ("2025-03-31", "2025-01-01")])
def test_periodo_invalido_e_rejeitado(inicio, fim):
    with pytest.raises(ValidationError):
        financeiro.ParamsSoma.model_validate({"tipo": "Despesa", "data_inicio": inicio, "data_fim": fim})


def test_enum_invalido_e_rejeitado():
    with pytest.raises(ValidationError):
        ouvidoria.ParamsContar.model_validate({"status": "Fechado"})


def test_formatacao_brl():
    from decimal import Decimal
    assert brl(Decimal("1234567.891")) == "R$ 1.234.567,89"
    assert brl(Decimal("0")) == "R$ 0,00"
    assert percentual(Decimal("0.12345")) == "12,35%"
