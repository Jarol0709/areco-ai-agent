"""API FastAPI do assistente multiagente."""
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from app import orquestrador
from app.db import consultar
from app.schemas import PerguntaEntrada, RespostaOrquestrador

app = FastAPI(title="areco-ai-agent", description="Assistente multiagente da Aurora Serviços Digitais (fictícia).")


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
