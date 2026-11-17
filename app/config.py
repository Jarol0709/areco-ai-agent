"""Configurações lidas de variáveis de ambiente (nenhum segredo fica no código)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def carregar_env(caminho: Path = RAIZ / ".env") -> None:
    """Carrega o .env local (se existir) sem sobrescrever variáveis já definidas no ambiente."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


carregar_env()

# Modelos padrão por provedor: (agentes, orquestrador).
MODELOS_PADRAO = {
    "gemini": ("gemini-3.8-flash", "gemini-3.5-flash-lite"),
    "anthropic": ("claude-sonnet-5-5", "claude-haiku-5-5"),
}
PROVEDOR = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
_PADRAO_AGENTES, _PADRAO_ORQUESTRADOR = MODELOS_PADRAO.get(PROVEDOR, ("", ""))


@dataclass(frozen=True)
class Config:
    database_url: str = os.getenv("DATABASE_URL", "")
    llm_provider: str = PROVEDOR
    # Modelo dos agentes e modelo do orquestrador (classificação); vazios = padrão do provedor.
    llm_model: str = os.getenv("LLM_MODEL") or _PADRAO_AGENTES
    llm_model_orquestrador: str = os.getenv("LLM_MODEL_ORQUESTRADOR") or _PADRAO_ORQUESTRADOR
    # Tentativas por chamada ao Gemini (inclui a primeira) em erros transitórios.
    llm_tentativas: int = int(os.getenv("LLM_TENTATIVAS", "4"))
    # Só Anthropic: "default" ativa o fallback do servidor em recusas (Sonnet/Opus); "off" desativa.
    llm_fallback: str = os.getenv("LLM_FALLBACK", "default")
    limiar_confianca: float = float(os.getenv("LIMIAR_CONFIANCA", "0.6"))
    limiar_similaridade: float = float(os.getenv("LIMIAR_SIMILARIDADE", "0.40"))
    top_k: int = int(os.getenv("RAG_TOP_K", "4"))
    # Embeddings sempre locais (fastembed/ONNX), independentemente do provedor de LLM.
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    embedding_cache_dir: str | None = os.getenv("EMBEDDING_CACHE_DIR") or None
    dir_dados: Path = field(default_factory=lambda: Path(os.getenv("DIR_DADOS", str(RAIZ / "data"))))


config = Config()
