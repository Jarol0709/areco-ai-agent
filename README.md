# areco-ai-agent

Sistema multiagente de IA para a empresa fictícia **Aurora Serviços Digitais S.A.**, que responde
perguntas sobre três domínios: **Financeiro**, **Informações internas** e **Ouvidoria**.

> Todos os dados deste repositório são sintéticos e não representam registros reais.

## Arquitetura

```
POST /perguntas ─► Orquestrador ─┬─ regra: protocolo OUV-NNNN ──────────► Agente Ouvidoria (sem LLM)
                                 ├─ regra: credencial de terceiros ─────► recusa (fontes 04 e 09)
                                 └─ LLM (orquestrador) classifica domínio + confiança
                                      ├─ confiança < 0,6 ─► pede esclarecimento
                                      ├─ fora_de_escopo ──► explica o escopo
                                      ├─ financeiro ──────► Agente Financeiro  (funções SQL predefinidas)
                                      ├─ ouvidoria ───────► Agente Ouvidoria   (funções SQL predefinidas)
                                      └─ informacoes_internas ► Agente RAG (pgvector + LLM)
```

| Componente | Escolha |
|---|---|
| API | FastAPI (`app/main.py`) |
| Frontend | HTML/CSS/JS sem frameworks (`app/static/`), servido pela API em `/` |
| Banco | PostgreSQL 16 + pgvector (imagem `pgvector/pgvector:pg16`): dados tabulares e vetores no mesmo banco |
| Provedor de LLM | `LLM_PROVIDER`: `gemini` (padrão) ou `anthropic` |
| LLM dos agentes (`LLM_MODEL`) | Gemini: `gemini-3.8-flash` · Anthropic: `claude-sonnet-5-5` |
| LLM do orquestrador (`LLM_MODEL_ORQUESTRADOR`) | Gemini: `gemini-3.5-flash-lite` · Anthropic: `claude-haiku-5-5` |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (384 dim.) via fastembed/ONNX, **sempre locais**, sem API key, independentemente do provedor |

**Sem SQL livre:** nos agentes Financeiro e Ouvidoria o LLM apenas escolhe uma função predefinida
(tool com schema estrito) e seus parâmetros. O código valida os parâmetros (Pydantic, enums e
período) e executa SQL fixo e parametrizado. Os valores são `NUMERIC`/`Decimal` e a resposta é
montada por template, então os números nunca passam pelo modelo.

| Agente | Funções |
|---|---|
| Financeiro | `somar_lancamentos`, `agrupar_lancamentos`, `consultar_orcamento`, `execucao_orcamentaria`, `inadimplencia_recebiveis` |
| Ouvidoria | `buscar_protocolo` (direto, sem LLM), `contar_manifestacoes`, `listar_manifestacoes`, `valores_referencia` |
| Informações internas | busca vetorial (top-4, limiar 0,40) + resposta do LLM restrita aos trechos; fontes vêm dos metadados |

### Saída

```json
{
  "id_requisicao": "uuid",
  "pergunta": "Qual o status do protocolo OUV-0002?",
  "dominio": "ouvidoria",
  "confianca": 1.0,
  "agente": "agente_ouvidoria",
  "status": "ok",
  "resposta": "Protocolo OUV-0002: status \"Aguardando área responsável\", ...",
  "fontes": [{"arquivo": "manifestacoes.csv", "ids": ["OUV-0002"], "secao": null}],
  "dados": {"manifestacoes": [{"protocolo": "OUV-0002", "status": "Aguardando área responsável"}]},
  "latencia_ms": 42
}
```

`status`: `ok`, `nao_encontrado`, `esclarecimento`, `recusado`, `fora_de_escopo` ou `erro`.

### Logs
Cada pergunta gera uma linha JSON no stdout e um registro na tabela `logs_consultas` com timestamp,
pergunta (com e-mail, CPF e telefone mascarados), domínio previsto, confiança, agente, função e
parâmetros, fontes/IDs, latência, tokens, status e erro. Segredos nunca são registrados.

## Provedor de LLM

O provedor é escolhido pela variável `LLM_PROVIDER`. Os dois implementam as mesmas duas operações
(`app/llm.py`): saída JSON com schema (classificação e resposta do RAG) e escolha de uma função
predefinida (agentes Financeiro e Ouvidoria). O restante do sistema não muda.

### Obter uma chave gratuita do Gemini
1. Acesse o **Google AI Studio** em <https://aistudio.google.com/apikey> e entre com uma conta Google.
2. Clique em **Create API key** (ou "Criar chave de API") e escolha ou crie um projeto do Google Cloud.
   Projetos sem faturamento ativado usam o nível gratuito.
3. Copie a chave e coloque-a no `.env` como `GEMINI_API_KEY=...`. Nunca a versione nem a cole em
   issues ou logs.

O nível gratuito tem limites por minuto e por dia que o Google altera com frequência; os limites
atuais do seu projeto aparecem em <https://aistudio.google.com/rate-limit>. Os modelos Flash-Lite
costumam ter cota diária maior, por isso são o padrão do orquestrador. No nível gratuito, o Google
pode usar os dados enviados para melhorar seus produtos; como a base é sintética, isso não expõe
dados reais.

### Status de validação por provedor

| Provedor | Testes unitários (clientes falsos) | Integração e avaliação com a API real |
|---|---|---|
| Gemini (padrão) | ✅ | ✅ 13 testes de integração; avaliação 12/12 (`resultados/avaliacao_gemini.md`) |
| Anthropic | ✅ | ⚠️ não executados, por limitação da chave de API disponível |

O adaptador Anthropic segue a mesma interface e passa nos testes unitários, mas não foi exercitado
contra a API real. Quem tiver uma chave pode validá-lo com `LLM_PROVIDER=anthropic`,
`python -m pytest -m integracao` e `python -m tests.avaliar`, que gera
`resultados/avaliacao_anthropic.md`.

### Trocar de provedor
No `.env`:

```bash
# Gemini (padrão)
LLM_PROVIDER=gemini
GEMINI_API_KEY=<sua-chave>

# Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<sua-chave>
```

Deixe `LLM_MODEL` e `LLM_MODEL_ORQUESTRADOR` vazios para usar os modelos padrão do provedor, ou
defina modelos do mesmo provedor. Se um modelo não corresponder ao provedor (por exemplo,
`LLM_PROVIDER=gemini` com `LLM_MODEL=claude-sonnet-5-5`), a API responde com `status=erro` e o log
mostra o motivo. Depois de trocar, reinicie com `docker compose up -d api`. Os embeddings e o
índice vetorial não mudam, então não é preciso reindexar.

## Como executar

1. Copie `.env.example` para `.env` e preencha a chave do provedor escolhido e `POSTGRES_PASSWORD`
   (o `.env` está no `.gitignore`).
2. Suba os serviços:
   ```bash
   docker compose up --build
   ```
   Na inicialização, o contêiner `api` carrega os CSV (com validação), indexa os documentos no
   pgvector e sobe a API em `http://localhost:8000` (documentação em `/docs`).
3. Abra o chat no navegador: **<http://localhost:8000/>** (ver [Frontend](#frontend)), ou pergunte
   direto à API:
   ```bash
   curl -X POST http://localhost:8000/perguntas -H "Content-Type: application/json" \
        -d '{"pergunta": "Quanto foi gasto em despesas pagas de janeiro a março de 2025?"}'
   ```

### Frontend
Chat simples em HTML, CSS e JavaScript puro (sem frameworks), em `app/static/`, servido pela própria
API — sem contêiner extra e sem CORS, porque página e API estão na mesma origem:

| Endereço | Conteúdo |
|---|---|
| <http://localhost:8000/> | página do chat |
| `http://localhost:8000/static/*` | `app.js` e `styles.css` |
| <http://localhost:8000/docs> | documentação interativa da API |

A página envia a pergunta para `POST /perguntas` e mostra, para cada resposta, o texto, o
**domínio classificado**, a confiança, o status, o agente, a latência e a lista de **fontes**
(arquivo, seção e IDs). O conteúdo da API é inserido só com `textContent`, nunca como HTML. Ao
alterar os arquivos de `app/static/`, rode `docker compose up -d --build api`, porque eles fazem
parte da imagem.

### Tamanho da imagem Docker
Medido em 2026-11-17 (Docker Desktop 27.2, Windows):

| Imagem | Em disco (`docker images`) | Compactada (`docker image inspect --format '{{.Size}}'`) |
|---|---|---|
| `areco-ai-agent-api` (Python 3.12-slim + dependências + modelo ONNX) | 1,11 GB | 366 MB |
| `pgvector/pgvector:pg16` | 647 MB | 162 MB |

O modelo de embeddings (~0,22 GB) é baixado durante o build, para que o contêiner não dependa de
rede ao iniciar. A maior parte do restante da imagem da API vem do `onnxruntime` (usado pelo
fastembed) e dos dois SDKs de LLM.

## Testes

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Linux/macOS: .venv/bin/pip
python -m pytest -m "not integracao"                # unitários: sem chave, sem banco, sem rede
python -m pytest -m integracao                      # integração: banco e/ou chave do provedor
python -m tests.avaliar                             # 12 casos de data/testes (banco + chave)
```

Os scripts e testes locais leem o `.env` automaticamente (sem sobrescrever variáveis já definidas).

| Tipo | Precisa de chave? | Precisa de banco? | O que cobre |
|---|---|---|---|
| Unitários | **Não** (as chaves são removidas do ambiente durante esses testes) | Não | frontend servido em `/`, carga e validação dos CSV, chunking, schemas das ferramentas, adaptadores Gemini/Anthropic com clientes falsos, regras e roteamento do orquestrador, mascaramento de logs |
| Integração SQL (`test_integracao_sql.py`) | Não | Sim | funções SQL com valores esperados calculados de forma independente a partir dos CSV (T004–T007, T009, T011) |
| Integração LLM (`test_integracao_llm.py`) | Sim | Não | classificação e escolha de função com o provedor real |
| Avaliação (`tests/avaliar.py`) | Sim | Sim | os 12 casos: acerto de domínio, fonte e palavras-chave dos critérios |

Testes de integração sem banco ou sem chave são **pulados**, com o motivo, em vez de falhar.

### Resultados da avaliação
`python -m tests.avaliar` grava `resultados/avaliacao_<provedor>.md`, com a tabela por caso, os
totais e os logs de cada pergunta em JSON Lines. Os logs passam pelo mesmo mascaramento de
`app/logs.py`: chaves de API (`AIza…`, `sk-ant-…`, `api_key=`/`token=`), e-mail, CPF e telefone.
Nenhuma chave nem header é registrado. O arquivo pode ser versionado.

## Estrutura

```
app/            API, orquestrador, cliente LLM, logs e agentes
app/static/     frontend do chat (HTML/CSS/JS sem frameworks)
scripts/        carregar_dados.py (CSV → PostgreSQL) e indexar_documentos.py (→ pgvector)
db/init/        extensão pgvector e tabelas de RAG e logs (o data/sql/schema.sql original é reutilizado)
tests/          pytest e script de avaliação
resultados/     resultados e logs da avaliação (gerados por tests/avaliar.py)
data/           dados fornecidos (não alterados)
```

A documentação do projeto é mantida em português do Brasil. O histórico de desenvolvimento está em
[`CLAUDE.md`](CLAUDE.md).
