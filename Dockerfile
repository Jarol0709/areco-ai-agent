FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EMBEDDING_CACHE_DIR=/opt/modelos

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baixa o modelo de embeddings (ONNX) no build, para o contêiner não depender de rede ao subir.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding(os.environ['EMBEDDING_MODEL'], cache_dir=os.environ['EMBEDDING_CACHE_DIR'])"

COPY app ./app
COPY scripts ./scripts
COPY data ./data

EXPOSE 8000
CMD ["sh", "-c", "python -m scripts.carregar_dados && python -m scripts.indexar_documentos && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
