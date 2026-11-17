"""Carrega os CSV de Financeiro e Ouvidoria no PostgreSQL, com validação.

Uso: python -m scripts.carregar_dados
Idempotente: limpa e recarrega as tabelas numa única transação. Linhas inválidas são rejeitadas e
listadas; se houver qualquer rejeição a carga é abortada.
"""
import csv
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.config import config
from app.db import conexao

STATUS_FIN = {"Pago", "Pendente", "Atrasado"}
TIPOS_FIN = {"Receita", "Despesa"}
CANAIS = {"Portal", "E-mail", "Telefone", "Chat"}
PADRAO_CC = re.compile(r"^CC\d00$")
PADRAO_PROTOCOLO = re.compile(r"^OUV-\d{4}$")


class LinhaInvalida(ValueError):
    pass


def ler_csv(caminho: Path) -> list[dict]:
    # utf-8-sig remove o BOM presente no cabeçalho dos arquivos fornecidos.
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _data(valor: str, campo: str, obrigatoria: bool = True) -> date | None:
    if not valor:
        if obrigatoria:
            raise LinhaInvalida(f"{campo} vazio")
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise LinhaInvalida(f"{campo} inválida: {valor!r}") from None


def _decimal(valor: str, campo: str) -> Decimal:
    try:
        d = Decimal(valor)
    except InvalidOperation:
        raise LinhaInvalida(f"{campo} não numérico: {valor!r}") from None
    if d < 0 or d != d.quantize(Decimal("0.01")):
        raise LinhaInvalida(f"{campo} inválido: {valor!r}")
    return d


def _enum(valor: str, permitidos: set[str], campo: str) -> str:
    if valor not in permitidos:
        raise LinhaInvalida(f"{campo} fora do domínio: {valor!r}")
    return valor


def _obrigatorio(valor: str, campo: str) -> str:
    if not valor.strip():
        raise LinhaInvalida(f"{campo} vazio")
    return valor.strip()


def validar_lancamento(r: dict) -> dict:
    if not PADRAO_CC.match(r["centro_custo"]):
        raise LinhaInvalida(f"centro_custo inválido: {r['centro_custo']!r}")
    return {
        "id_lancamento": _obrigatorio(r["id_lancamento"], "id_lancamento"),
        "data_competencia": _data(r["data_competencia"], "data_competencia"),
        "data_vencimento": _data(r["data_vencimento"], "data_vencimento"),
        "tipo": _enum(r["tipo"], TIPOS_FIN, "tipo"),
        "categoria": _obrigatorio(r["categoria"], "categoria"),
        "descricao": _obrigatorio(r["descricao"], "descricao"),
        "centro_custo": r["centro_custo"],
        "departamento": _obrigatorio(r["departamento"], "departamento"),
        "contraparte": _obrigatorio(r["contraparte"], "contraparte"),
        "valor_brl": _decimal(r["valor_brl"], "valor_brl"),
        "status": _enum(r["status"], STATUS_FIN, "status"),
        "metodo_pagamento": r["metodo_pagamento"] or None,
        "observacao": r["observacao"] or None,
    }


def validar_orcamento(r: dict) -> dict:
    if not re.fullmatch(r"0[1-9]|1[0-2]", r["mes"]):
        raise LinhaInvalida(f"mes inválido: {r['mes']!r}")
    if not PADRAO_CC.match(r["centro_custo"]):
        raise LinhaInvalida(f"centro_custo inválido: {r['centro_custo']!r}")
    try:
        ano = int(r["ano"])
    except ValueError:
        raise LinhaInvalida(f"ano inválido: {r['ano']!r}") from None
    return {
        "ano": ano,
        "mes": r["mes"],
        "centro_custo": r["centro_custo"],
        "departamento": _obrigatorio(r["departamento"], "departamento"),
        "orcamento_brl": _decimal(r["orcamento_brl"], "orcamento_brl"),
        "versao_orcamento": _obrigatorio(r["versao_orcamento"], "versao_orcamento"),
        "observacao": r["observacao"] or None,
    }


def validar_manifestacao(r: dict, ref: dict) -> dict:
    if not PADRAO_PROTOCOLO.match(r["protocolo"]):
        raise LinhaInvalida(f"protocolo inválido: {r['protocolo']!r}")
    abertura = _data(r["data_abertura"], "data_abertura")
    resposta = _data(r["data_resposta"], "data_resposta", obrigatoria=False)
    if resposta and resposta < abertura:
        raise LinhaInvalida("data_resposta anterior à data_abertura")
    try:
        prazo = int(r["prazo_referencia_dias"])
    except ValueError:
        raise LinhaInvalida(f"prazo_referencia_dias inválido: {r['prazo_referencia_dias']!r}") from None
    return {
        "protocolo": r["protocolo"],
        "data_abertura": abertura,
        "categoria": _enum(r["categoria"], set(ref["categorias"]), "categoria"),
        "assunto": _obrigatorio(r["assunto"], "assunto"),
        "canal_entrada": _enum(r["canal_entrada"], CANAIS, "canal_entrada"),
        "prioridade": _enum(r["prioridade"], set(ref["prioridades_validas"]), "prioridade"),
        "status": _enum(r["status"], set(ref["status_validos"]), "status"),
        "area_responsavel": _obrigatorio(r["area_responsavel"], "area_responsavel"),
        "resumo_manifestacao": _obrigatorio(r["resumo_manifestacao"], "resumo_manifestacao"),
        "data_resposta": resposta,
        "resposta_resumo": r["resposta_resumo"] or None,
        "prazo_referencia_dias": prazo,
        "dados_pessoais": r["dados_pessoais"] or None,
        "observacao": r["observacao"] or None,
    }


def validar_arquivo(linhas: list[dict], validar) -> tuple[list[dict], list[str]]:
    validas, erros = [], []
    for numero, linha in enumerate(linhas, start=2):  # linha 1 = cabeçalho
        try:
            validas.append(validar(linha))
        except (LinhaInvalida, KeyError) as exc:
            erros.append(f"linha {numero}: {exc}")
    return validas, erros


def preparar(dir_dados: Path) -> dict[str, tuple[list[dict], list[str]]]:
    ref = json.loads((dir_dados / "ouvidoria" / "referencia_ouvidoria.json").read_text(encoding="utf-8"))
    return {
        "lancamentos_financeiros": validar_arquivo(
            ler_csv(dir_dados / "financeiro" / "lancamentos_financeiros.csv"), validar_lancamento),
        "orcamento_mensal": validar_arquivo(
            ler_csv(dir_dados / "financeiro" / "orcamento_mensal.csv"), validar_orcamento),
        "manifestacoes_ouvidoria": validar_arquivo(
            ler_csv(dir_dados / "ouvidoria" / "manifestacoes.csv"), lambda r: validar_manifestacao(r, ref)),
    }


def inserir(tabela: str, linhas: list[dict], conn) -> None:
    colunas = list(linhas[0])
    sql = (f"INSERT INTO {tabela} ({', '.join(colunas)}) "
           f"VALUES ({', '.join(f'%({c})s' for c in colunas)})")
    with conn.cursor() as cur:
        cur.executemany(sql, linhas)


def main() -> int:
    dados = preparar(config.dir_dados)
    rejeicoes = {t: e for t, (_, e) in dados.items() if e}
    for tabela, erros in rejeicoes.items():
        print(f"[carga] {tabela}: {len(erros)} linha(s) rejeitada(s)")
        for erro in erros:
            print(f"  - {erro}")
    if rejeicoes:
        print("[carga] abortada: corrija as linhas rejeitadas.")
        return 1
    with conexao() as conn:  # uma transação: ou carrega tudo, ou nada
        conn.execute("TRUNCATE lancamentos_financeiros, orcamento_mensal, manifestacoes_ouvidoria")
        for tabela, (linhas, _) in dados.items():
            inserir(tabela, linhas, conn)
            print(f"[carga] {tabela}: {len(linhas)} linha(s) carregada(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
