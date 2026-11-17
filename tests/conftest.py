import csv
import os
from pathlib import Path

import pytest

from app import llm
from app.config import config

DADOS = config.dir_dados
VARIAVEIS_DE_CHAVE = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
CHAVE_DO_PROVEDOR = {"gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "anthropic": ("ANTHROPIC_API_KEY",)}


def ler(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(autouse=True)
def unitarios_sem_chave(request, monkeypatch):
    """Garante que os testes unitários rodem sem nenhuma API key (e sem cliente LLM real)."""
    if request.node.get_closest_marker("integracao"):
        yield
        return
    for var in VARIAVEIS_DE_CHAVE:
        monkeypatch.delenv(var, raising=False)
    llm.provedor.cache_clear()
    yield
    llm.provedor.cache_clear()


@pytest.fixture(scope="session")
def lancamentos() -> list[dict]:
    return ler(DADOS / "financeiro" / "lancamentos_financeiros.csv")


@pytest.fixture(scope="session")
def orcamentos() -> list[dict]:
    return ler(DADOS / "financeiro" / "orcamento_mensal.csv")


@pytest.fixture(scope="session")
def banco_disponivel() -> None:
    """Pula testes de integração se o PostgreSQL não estiver acessível e carregado."""
    try:
        from app.db import consultar

        if consultar("SELECT COUNT(*) AS n FROM lancamentos_financeiros")[0]["n"] == 0:
            pytest.skip("banco sem dados: rode python -m scripts.carregar_dados")
    except Exception as exc:
        pytest.skip(f"PostgreSQL indisponível ({type(exc).__name__})")


@pytest.fixture(scope="session")
def chave_llm() -> None:
    """Pula testes de integração com LLM se não houver chave para o provedor configurado."""
    if not any(os.getenv(v) for v in CHAVE_DO_PROVEDOR.get(config.llm_provider, ())):
        pytest.skip(f"sem API key para LLM_PROVIDER={config.llm_provider}")
