-- Tabelas do RAG (pgvector) e dos logs. Complementa data/sql/schema.sql, que não é alterado.

-- 384 dimensões = sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2.
-- Se EMBEDDING_MODEL mudar, ajuste a dimensão e recrie o volume do banco.
CREATE TABLE IF NOT EXISTS documentos_chunks (
    id SERIAL PRIMARY KEY,
    dominio VARCHAR(30) NOT NULL,
    fonte VARCHAR(120) NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    versao VARCHAR(40),
    secao VARCHAR(200) NOT NULL,
    conteudo TEXT NOT NULL,
    ids TEXT[] NOT NULL DEFAULT '{}',
    embedding vector(384) NOT NULL
);
-- Sem índice vetorial: com ~30 trechos a varredura sequencial é mais rápida que HNSW/IVFFlat.

CREATE TABLE IF NOT EXISTS logs_consultas (
    id_requisicao UUID PRIMARY KEY,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    pergunta TEXT NOT NULL,
    dominio_previsto VARCHAR(30),
    confianca NUMERIC(4,3),
    agente VARCHAR(40),
    ferramenta VARCHAR(60),
    parametros JSONB,
    fontes JSONB,
    latencia_ms INTEGER NOT NULL,
    tokens_entrada INTEGER,
    tokens_saida INTEGER,
    provedor_llm VARCHAR(20),
    status VARCHAR(20) NOT NULL,
    erro TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_criado_em ON logs_consultas (criado_em);
