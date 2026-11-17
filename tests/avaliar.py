"""Avaliação ponta a ponta com os casos de data/testes/perguntas_avaliacao.json.

Uso: python -m tests.avaliar   (requer banco carregado/indexado e API key do provedor; consome tokens)
Mede acerto de domínio e de fonte; o critério textual é verificado por palavras-chave.
Salva resultados e logs (já mascarados, sem chaves) em resultados/avaliacao_<provedor>.md.
"""
import json
import sys
from datetime import datetime, timezone

from app import logs, orquestrador
from app.config import RAIZ, config

# Palavras-chave mínimas derivadas do campo "criterio" de cada caso.
PALAVRAS_CHAVE = {
    "T001": ["portal", "30 dias"],
    "T002": ["10 dias", "comprovante"],
    "T003": ["liderança", "gerente", "diretoria"],
    "T004": ["não foi encontrado"],
    "T005": ["Aberto", "Em análise", "Aguardando área responsável", "Respondido", "Concluído"],
    "T008": ["seguranca@aurora.example"],
    "T009": ["Aguardando área responsável"],
    "T010": ["Não posso"],
    "T012": ["seguranca@aurora.example"],
}


def dominio_ok(esperado: str, r) -> bool:
    if esperado == "fora_de_escopo_ou_segurança":
        return r.status in ("recusado", "fora_de_escopo")
    return r.dominio == esperado


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def salvar(resultados: list[dict], eventos: list[dict], totais: dict, n: int) -> str:
    destino = RAIZ / "resultados" / f"avaliacao_{config.llm_provider}.md"
    destino.parent.mkdir(exist_ok=True)
    marca = lambda ok: "✅" if ok else "❌"
    linhas = [
        f"# Avaliação — provedor `{config.llm_provider}`",
        "",
        f"- Executada em: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Modelo dos agentes: `{config.llm_model}` · orquestrador: `{config.llm_model_orquestrador}`",
        f"- Embeddings (locais): `{config.embedding_model}`",
        f"- **Domínio {totais['dominio']}/{n} · Fonte {totais['fonte']}/{n} · "
        f"Critério por palavras-chave {totais['criterio']}/{n}**",
        "",
        "Gerado por `python -m tests.avaliar`. Os logs abaixo passam pelo mascaramento de `app/logs.py`",
        "(chaves de API, tokens, e-mail pessoal, CPF e telefone); nenhuma chave é registrada.",
        "",
        "| Caso | Domínio | Fonte | Critério | Previsto (confiança) | Status | Latência | Resposta |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        linhas.append(
            f"| {r['id']} | {marca(r['ok_dominio'])} | {marca(r['ok_fonte'])} | {marca(r['ok_criterio'])} | "
            f"{r['dominio']} ({r['confianca']:.2f}) | {r['status']} | {r['latencia_ms']} ms | {_celula(r['resposta'])} |"
        )
    linhas += ["", "## Logs (JSON Lines)", "", "```jsonl"]
    linhas += [json.dumps(e, ensure_ascii=False, default=str) for e in eventos]
    linhas += ["```", ""]
    destino.write_text("\n".join(linhas), encoding="utf-8")
    return str(destino.relative_to(RAIZ))


def main() -> int:
    casos = json.loads((config.dir_dados / "testes" / "perguntas_avaliacao.json").read_text(encoding="utf-8"))["casos"]
    eventos: list[dict] = []
    logs.assinantes.append(eventos.append)
    resultados, totais = [], {"dominio": 0, "fonte": 0, "criterio": 0}
    for caso in casos:
        r = orquestrador.responder(caso["pergunta"])
        fontes_esperadas = {f.strip() for f in caso["fonte_esperada"].split(";")}
        item = {
            "id": caso["id"],
            "ok_dominio": dominio_ok(caso["dominio_esperado"], r),
            "ok_fonte": fontes_esperadas <= {f.arquivo for f in r.fontes},
            "ok_criterio": all(c.lower() in r.resposta.lower() for c in PALAVRAS_CHAVE.get(caso["id"], [])),
            "dominio": r.dominio, "confianca": r.confianca, "status": r.status,
            "latencia_ms": r.latencia_ms, "resposta": r.resposta,
        }
        for chave in totais:
            totais[chave] += item[f"ok_{chave}"]
        resultados.append(item)
        print(f"{item['id']} dom:{item['ok_dominio']} fonte:{item['ok_fonte']} crit:{item['ok_criterio']} "
              f"[{r.dominio} {r.confianca:.2f} {r.status} {r.latencia_ms}ms] {r.resposta[:120]}")
    n = len(casos)
    arquivo = salvar(resultados, eventos, totais, n)
    print(f"\nDomínio {totais['dominio']}/{n} | Fonte {totais['fonte']}/{n} | Critério {totais['criterio']}/{n}")
    print(f"Resultados e logs salvos em {arquivo}")
    return 0 if totais["dominio"] == n and totais["fonte"] == n else 1


if __name__ == "__main__":
    sys.exit(main())
