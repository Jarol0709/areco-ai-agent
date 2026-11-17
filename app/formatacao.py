"""Formatação determinística de valores para as respostas."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def brl(valor: Decimal) -> str:
    """Formata Decimal no padrão brasileiro: R$ 1.234,56."""
    q = Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    texto = f"{q:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def percentual(valor: Decimal) -> str:
    q = (Decimal(valor) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q}".replace(".", ",") + "%"


def data_br(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime("%d/%m/%Y")


def serializavel(valor):
    """Converte Decimal/date em texto para o JSON de saída, sem perder precisão."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: serializavel(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [serializavel(v) for v in valor]
    return valor
