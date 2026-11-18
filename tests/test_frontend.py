"""Frontend estático servido pela API (sem banco e sem chave)."""
from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def test_raiz_serve_pagina_do_chat():
    r = cliente.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert 'id="formulario"' in r.text
    assert "/static/app.js" in r.text


def test_arquivos_estaticos_disponiveis():
    js = cliente.get("/static/app.js")
    css = cliente.get("/static/styles.css")
    assert js.status_code == 200 and "/perguntas" in js.text
    assert css.status_code == 200


def test_frontend_nao_usa_innerhtml():
    # Conteúdo da API é exibido só via textContent, para evitar injeção de HTML.
    assert "innerHTML" not in cliente.get("/static/app.js").text


def test_docs_continua_disponivel():
    assert cliente.get("/docs").status_code == 200
