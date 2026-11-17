"""Indexa os Markdown e o FAQ de Informações internas no pgvector.

Uso: python -m scripts.indexar_documentos
Idempotente: remove os trechos do domínio e reindexa.
"""
import sys

from app.agentes.informacoes_internas import DOMINIO, carregar_chunks, gerar_embeddings, vetor_sql
from app.config import config
from app.db import conexao

SQL_INSERIR = """
INSERT INTO documentos_chunks (dominio, fonte, titulo, versao, secao, conteudo, ids, embedding)
VALUES (%(dominio)s, %(fonte)s, %(titulo)s, %(versao)s, %(secao)s, %(conteudo)s, %(ids)s, %(embedding)s::vector)
"""


def main() -> int:
    chunks = carregar_chunks(config.dir_dados / "informacoes_internas")
    vetores = gerar_embeddings([c.texto_indexado() for c in chunks])
    with conexao() as conn:
        conn.execute("DELETE FROM documentos_chunks WHERE dominio = %s", (DOMINIO,))
        with conn.cursor() as cur:
            cur.executemany(SQL_INSERIR, [
                {"dominio": DOMINIO, "fonte": c.fonte, "titulo": c.titulo, "versao": c.versao,
                 "secao": c.secao, "conteudo": c.conteudo, "ids": c.ids, "embedding": vetor_sql(v)}
                for c, v in zip(chunks, vetores)
            ])
    print(f"[indexação] {len(chunks)} trecho(s) indexado(s) de {len({c.fonte for c in chunks})} documento(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
