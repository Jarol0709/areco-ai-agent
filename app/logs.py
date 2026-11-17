"""Logs estruturados: uma linha JSON no stdout e um registro em `logs_consultas`.

Não registra segredos: mascara chaves de API/tokens e dados pessoais (e-mail, CPF, telefone)
na pergunta e na mensagem de erro.
"""
import json
import logging
import re
import sys
from typing import Callable

from app.db import conexao

logger = logging.getLogger("areco")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

MASCARAS = [
    # Segredos primeiro, para não serem parcialmente consumidos pelas outras máscaras.
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "<segredo>"),
    (re.compile(r"sk-ant-[0-9A-Za-z_\-]+"), "<segredo>"),
    (re.compile(r"(?i)\b(api[_-]?key|token|senha|password|secret)\b(\s*[:=]\s*)\S+"), r"\1\2<segredo>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "<cpf>"),
    (re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b"), "<telefone>"),
]

# Funções extras que recebem cada evento já mascarado (ex.: o script de avaliação grava em arquivo).
assinantes: list[Callable[[dict], None]] = []

SQL_LOG = """
INSERT INTO logs_consultas (id_requisicao, criado_em, pergunta, dominio_previsto, confianca, agente,
    ferramenta, parametros, fontes, latencia_ms, tokens_entrada, tokens_saida, provedor_llm, status, erro)
VALUES (%(id_requisicao)s, %(timestamp)s, %(pergunta)s, %(dominio_previsto)s, %(confianca)s, %(agente)s,
    %(ferramenta)s, %(parametros)s, %(fontes)s, %(latencia_ms)s, %(tokens_entrada)s, %(tokens_saida)s,
    %(provedor_llm)s, %(status)s, %(erro)s)
"""


def mascarar(texto: str | None) -> str | None:
    if texto is None:
        return None
    for padrao, substituto in MASCARAS:
        texto = padrao.sub(substituto, texto)
    return texto


def registrar(evento: dict) -> None:
    evento = {**evento, "pergunta": mascarar(evento["pergunta"]), "erro": mascarar(evento.get("erro"))}
    logger.info(json.dumps(evento, ensure_ascii=False, default=str))
    for assinante in assinantes:
        assinante(evento)
    try:
        with conexao() as conn:
            conn.execute(SQL_LOG, {
                **evento,
                "parametros": json.dumps(evento.get("parametros"), ensure_ascii=False, default=str),
                "fontes": json.dumps(evento.get("fontes"), ensure_ascii=False),
            })
    except Exception as exc:  # o log no banco nunca deve derrubar a resposta
        logger.warning(json.dumps({"aviso": "falha ao gravar log no banco", "erro": type(exc).__name__}))
