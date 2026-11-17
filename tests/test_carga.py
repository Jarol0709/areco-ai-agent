from decimal import Decimal

import pytest

from scripts.carregar_dados import (
    LinhaInvalida, preparar, validar_arquivo, validar_lancamento, validar_orcamento,
)
from tests.conftest import DADOS


def test_todos_os_arquivos_fornecidos_sao_validos():
    dados = preparar(DADOS)
    contagens = {tabela: len(linhas) for tabela, (linhas, _) in dados.items()}
    erros = {tabela: e for tabela, (_, e) in dados.items() if e}
    assert erros == {}
    # Contagens declaradas em data/manifesto_pacote.json
    assert contagens == {"lancamentos_financeiros": 300, "orcamento_mensal": 144, "manifestacoes_ouvidoria": 180}


def test_valor_convertido_para_decimal(lancamentos):
    linha = validar_lancamento(lancamentos[0])
    assert linha["valor_brl"] == Decimal("16360.63")
    assert isinstance(linha["valor_brl"], Decimal)


@pytest.mark.parametrize("campo, valor", [
    ("tipo", "Transferência"),
    ("status", "Cancelado"),
    ("valor_brl", "abc"),
    ("valor_brl", "-10.00"),
    ("valor_brl", "10.001"),
    ("data_competencia", "2025-13-01"),
    ("centro_custo", "XX1"),
])
def test_lancamento_invalido_e_rejeitado(lancamentos, campo, valor):
    with pytest.raises(LinhaInvalida):
        validar_lancamento({**lancamentos[0], campo: valor})


def test_mes_invalido_no_orcamento(orcamentos):
    with pytest.raises(LinhaInvalida):
        validar_orcamento({**orcamentos[0], "mes": "13"})


def test_validar_arquivo_informa_numero_da_linha(lancamentos):
    linhas = [lancamentos[0], {**lancamentos[1], "status": "X"}]
    validas, erros = validar_arquivo(linhas, validar_lancamento)
    assert len(validas) == 1
    assert erros == ["linha 3: status fora do domínio: 'X'"]
