"""API FastAPI do assistente multiagente."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import orquestrador
from app.db import consultar
from app.schemas import PerguntaEntrada, RespostaOrquestrador

DIR_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="areco-ai-agent", description="Assistente multiagente da Aurora Serviços Digitais (fictícia).")
app.mount("/static", StaticFiles(directory=DIR_STATIC), name="static")


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    """Página do chat (HTML/CSS/JS sem frameworks), servida pela própria API."""
    return FileResponse(DIR_STATIC / "index.html")


@app.post("/perguntas", response_model=RespostaOrquestrador)
async def perguntar(entrada: PerguntaEntrada) -> RespostaOrquestrador:
    return await run_in_threadpool(orquestrador.responder, entrada.pergunta)


@app.get("/saude")
def saude() -> dict:
    try:
        consultar("SELECT 1")
        return {"status": "ok", "banco": "ok"}
    except Exception:
        return {"status": "degradado", "banco": "indisponível"}
