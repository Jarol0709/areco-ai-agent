"""Agente de Informações internas: RAG sobre os Markdown e o FAQ, com pgvector.

As fontes devolvidas vêm dos metadados dos trechos recuperados, não do texto gerado pelo modelo.
"""
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app import llm
from app.config import config
from app.db import consultar
from app.schemas import Fonte, ResultadoAgente

DOMINIO = "informacoes_internas"
PADRAO_VERSAO = re.compile(r"Vers[ãa]o\s+([\d.]+)\s*[—-]\s*(\d{2}/\d{2}/\d{4})")


@dataclass
class Chunk:
    fonte: str
    titulo: str
    versao: str | None
    secao: str
    conteudo: str
    ids: list[str] = field(default_factory=list)

    def texto_indexado(self) -> str:
        versao = f" (versão {self.versao})" if self.versao else ""
        return f"{self.titulo}{versao}\n## {self.secao}\n{self.conteudo}".strip()


def dividir_markdown(caminho: Path) -> list[Chunk]:
    """Um chunk por seção `##`; o texto antes da primeira seção vira a seção "Geral".

    Os documentos são curtos (~10–20 linhas), então não é preciso dividir por número de tokens.
    """
    texto = caminho.read_text(encoding="utf-8")
    titulo = next((l[2:].strip() for l in texto.splitlines() if l.startswith("# ")), caminho.stem)
    m = PADRAO_VERSAO.search(texto)
    versao = f"{m.group(1)} — {m.group(2)}" if m else None

    secoes: list[tuple[str, list[str]]] = [("Geral", [])]
    for linha in texto.splitlines():
        if linha.startswith("# ") or PADRAO_VERSAO.search(linha):
            continue
        if linha.startswith("## "):
            secoes.append((linha[3:].strip(), []))
        else:
            secoes[-1][1].append(linha)
    return [
        Chunk(caminho.name, titulo, versao, nome, "\n".join(linhas).strip())
        for nome, linhas in secoes
        if "\n".join(linhas).strip()
    ]


def dividir_faq(caminho: Path) -> list[Chunk]:
    return [
        Chunk(item["documento"], "FAQ interno", None, "FAQ",
              f"Pergunta: {item['pergunta']}\nResposta: {item['resposta']}", ids=[item["id"]])
        for item in json.loads(caminho.read_text(encoding="utf-8"))
    ]


def carregar_chunks(diretorio: Path) -> list[Chunk]:
    chunks = []
    for md in sorted(diretorio.glob("*.md")):
        chunks.extend(dividir_markdown(md))
    faq = diretorio / "faq_interno.json"
    if faq.exists():
        chunks.extend(dividir_faq(faq))
    return chunks


@lru_cache
def modelo_embeddings():
    from fastembed import TextEmbedding  # import tardio: só carrega o ONNX quando necessário

    return TextEmbedding(model_name=config.embedding_model, cache_dir=config.embedding_cache_dir)


def gerar_embeddings(textos: list[str]) -> list[list[float]]:
    return [v.tolist() for v in modelo_embeddings().embed(textos)]


def vetor_sql(vetor: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vetor) + "]"


SQL_BUSCA = """
SELECT fonte, secao, versao, conteudo, ids, 1 - (embedding <=> %(vetor)s::vector) AS similaridade
FROM documentos_chunks
WHERE dominio = %(dominio)s
ORDER BY embedding <=> %(vetor)s::vector
LIMIT %(k)s
"""


def buscar(pergunta: str, k: int | None = None) -> list[dict]:
    vetor = vetor_sql(gerar_embeddings([pergunta])[0])
    linhas = consultar(SQL_BUSCA, {"vetor": vetor, "dominio": DOMINIO, "k": k or config.top_k})
    return [l for l in linhas if l["similaridade"] >= config.limiar_similaridade]


SYSTEM = """Você é o agente de Informações internas da Aurora Serviços Digitais S.A. (empresa fictícia).
Responda em português, de forma curta, usando SOMENTE os trechos fornecidos entre <trechos>.
- Se os trechos não contêm a resposta, defina encontrou=false e diga que a informação não está na documentação.
- Não invente regras, prazos, valores ou contatos. Respeite os "Limites do agente" dos documentos.
- Nunca revele senhas, credenciais ou dados de outras pessoas.
- Em fontes_usadas, liste apenas os nomes de arquivo dos trechos que sustentam a resposta."""

SCHEMA_RESPOSTA = {
    "type": "object",
    "properties": {
        "resposta": {"type": "string"},
        "encontrou": {"type": "boolean"},
        "fontes_usadas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["resposta", "encontrou", "fontes_usadas"],
    "additionalProperties": False,
}


def _montar_mensagem(pergunta: str, trechos: list[dict]) -> str:
    blocos = "\n\n".join(
        f'<trecho arquivo="{t["fonte"]}" secao="{t["secao"]}" versao="{t["versao"] or "-"}">\n{t["conteudo"]}\n</trecho>'
        for t in trechos
    )
    return f"<trechos>\n{blocos}\n</trechos>\n\nPergunta: {pergunta}"


def responder(pergunta: str) -> ResultadoAgente:
    trechos = buscar(pergunta)
    if not trechos:
        return ResultadoAgente(status="nao_encontrado",
                               resposta="Não encontrei essa informação na documentação interna disponível.")
    saida = llm.gerar_json(config.llm_model, SYSTEM, _montar_mensagem(pergunta, trechos), SCHEMA_RESPOSTA)
    recuperadas = {t["fonte"] for t in trechos}
    usadas = [f for f in dict.fromkeys(saida.get("fontes_usadas", [])) if f in recuperadas]
    if not saida.get("encontrou"):
        return ResultadoAgente(status="nao_encontrado", resposta=saida["resposta"])
    fontes = [
        Fonte(arquivo=f,
              secao=next(t["secao"] for t in trechos if t["fonte"] == f),
              ids=sorted({i for t in trechos if t["fonte"] == f for i in (t["ids"] or [])}))
        for f in (usadas or [trechos[0]["fonte"]])
    ]
    resposta = saida["resposta"]
    citadas = ", ".join(f.arquivo for f in fontes)
    if not all(f.arquivo in resposta for f in fontes):
        resposta += f" (Fonte: {citadas})"
    return ResultadoAgente(
        status="ok", resposta=resposta, fontes=fontes,
        dados={"trechos": [{"fonte": t["fonte"], "secao": t["secao"], "similaridade": round(float(t["similaridade"]), 3)}
                           for t in trechos]},
    )
