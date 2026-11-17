"""Acesso ao PostgreSQL. Todas as consultas usam parâmetros; nenhum SQL vem do modelo."""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.config import config


@contextmanager
def conexao():
    if not config.database_url:
        raise RuntimeError("DATABASE_URL não definida.")
    with psycopg.connect(config.database_url, row_factory=dict_row, connect_timeout=5) as conn:
        yield conn


def consultar(sql: str, params: dict | None = None) -> list[dict]:
    with conexao() as conn:
        return conn.execute(sql, params or {}).fetchall()
