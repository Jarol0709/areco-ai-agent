# CLAUDE.md — areco-ai-agent

## Contexto do projeto
Sistema multiagente de IA (FastAPI + PostgreSQL + RAG) sobre bases sintéticas da empresa fictícia
**Aurora Serviços Digitais S.A.**, com três domínios:

| Domínio | Dados | Estratégia |
|---|---|---|
| Financeiro | `data/financeiro/*.csv`, `indicadores_e_regras.json` | Funções SQL predefinidas e parametrizadas (`NUMERIC(14,2)`, nunca float) |
| Informações internas | `data/informacoes_internas/*.md`, `faq_interno.json` | RAG com pgvector (citar o arquivo-fonte) |
| Ouvidoria | `data/ouvidoria/manifestacoes.csv`, `referencia_ouvidoria.json` | Funções SQL predefinidas: busca exata por protocolo + filtros |

Os dados fornecidos ficam em `data/` e não devem ser alterados. Referências:
`data/documentacao/dicionario_de_dados.md`, `data/documentacao/ingestao_e_uso.md`, `data/sql/schema.sql`,
`data/testes/perguntas_avaliacao.json`.

LLM configurável por `LLM_PROVIDER` (`gemini`, padrão, ou `anthropic`); embeddings sempre locais
(fastembed/ONNX).

**Status atual:** implementado e validado com Gemini (entrada #06): Docker no ar, 52 testes unitários e
13 de integração passando, avaliação 12/12 em `resultados/avaliacao_gemini.md`. O provedor Anthropic
está implementado e coberto por testes unitários, mas **fora do escopo da avaliação** por limitação da
chave de API (entrada #07).

---

## Regras para o Claude (obrigatórias)

1. **Idioma**: toda a documentação do projeto — esta bitácora, o `CLAUDE.md`, o `README.md` e demais
   arquivos de documentação — deve ser escrita e mantida em **português do Brasil**, mesmo que o
   usuário escreva os prompts em outro idioma. Prompts citados podem ser traduzidos ou mantidos no
   original, indicando o idioma.
2. **Registro contínuo**: ao concluir cada tarefa ou mudança relevante, adicionar uma entrada na
   [Bitácora de desenvolvimento](#bitácora-de-desenvolvimento) (a mais recente no final), usando o modelo.
3. **O que registrar**: prompt do usuário (resumido ou literal), decisões técnicas e sua justificativa,
   problemas encontrados e suas soluções, código aceito ou descartado (com motivo) e testes executados
   com o resultado real (se falharem, registrar que falharam).
4. **Nunca incluir segredos**: nada de API keys, tokens, senhas, connection strings com credenciais
   nem conteúdo do `.env`. Se um prompt ou saída os contiver, substituí-los por `<REDACTED>`.
   Credenciais são lidas apenas de variáveis de ambiente (`.env` está no `.gitignore`).
5. Não registrar dados pessoais; os protocolos fictícios do dataset podem aparecer.
6. Manter as entradas concisas: referenciar arquivos como `caminho:linha` em vez de colar código longo.
7. **Aprovação antes de implementar**: não escrever código de implementação enquanto o usuário não
   aprovar explicitamente a arquitetura proposta. Mudanças de arquitetura posteriores também exigem
   proposta e aprovação antes de serem implementadas.
8. **Sem SQL livre**: os agentes Financeiro e de Ouvidoria só executam funções SQL predefinidas e
   parametrizadas; o modelo escolhe a função e os parâmetros, nunca gera SQL.

---

## Modelo de entrada

```markdown
### [AAAA-MM-DD] #NN — Título curto
**Prompt:** <resumo ou citação do pedido do usuário, sem segredos>
**Decisões técnicas:**
- <decisão> — <motivo>
**Problemas e soluções:**
- Problema: <...> → Solução: <...>
**Código:**
- ✅ Aceito: <arquivo/função> — <o que faz>
- ❌ Descartado: <abordagem> — <por quê>
**Testes:**
- <comando ou caso> → <resultado: OK / FALHA + detalhe>
**Pendências:** <próximos passos>
```

---

## Bitácora de desenvolvimento

### [2026-11-16] #01 — Configuração do registro de desenvolvimento
**Prompt (original em espanhol):** "No arquivo CLAUDE.md quero registrar de forma contínua o processo
de desenvolvimento: prompts, decisões técnicas, problemas e soluções, código aceito ou descartado, e
testes. Não quero que você inclua API keys."
**Decisões técnicas:**
- Usar o `CLAUDE.md` como bitácora única com modelo fixo — o Claude Code o carrega em cada sessão,
  então as regras de registro são aplicadas automaticamente.
- Ordem cronológica crescente com numeração `#NN` — facilita referenciar entradas.
- Política explícita de ocultação de segredos (`<REDACTED>`).
**Problemas e soluções:**
- Nenhum.
**Código:**
- ✅ Aceito: `CLAUDE.md` — contexto, regras, modelo e primeira entrada.
**Testes:**
- Não se aplica (apenas documentação). Verificado que `.env` está no `.gitignore`.
**Pendências:** definir a arquitetura (FastAPI, orquestrador, agentes por domínio) e a ingestão de dados.

### [2026-11-16] #02 — Padronização do idioma em português
**Prompt (original em espanhol):** "Pode modificar a bitácora para que fique em português e também
para que esse idioma se mantenha definido no futuro, assim como o README."
**Decisões técnicas:**
- Português do Brasil como idioma oficial da documentação — coerente com os dados, o dicionário de
  dados e os documentos internos do dataset, todos em pt-BR.
- Regra de idioma adicionada como regra nº 1, válida mesmo quando os prompts vierem em outro idioma.
**Problemas e soluções:**
- Nenhum.
**Código:**
- ✅ Aceito: `CLAUDE.md` traduzido para português; `README.md` com descrição em português.
**Testes:**
- Não se aplica (apenas documentação).
**Pendências:** as mesmas da entrada #01.

### [2026-11-16] #03 — Leitura dos requisitos e proposta de arquitetura
**Prompt:** ler `ingestao_e_uso.md`, `dicionario_de_dados.md`, `schema.sql` e `perguntas_avaliacao.json`
antes de escrever código; propor arquitetura (pastas, orquestrador, saídas com domínio e confiança,
agentes, carga no PostgreSQL, LLM, banco vetorial, logs); manter simples; agentes Financeiro e
Ouvidoria com funções SQL predefinidas, sem SQL livre; pgvector se simplificar o Docker; documentação
em português; **não implementar nada até aprovação** e registrar esta decisão.
**Decisões técnicas (propostas, aguardando aprovação):**
- **Nada é implementado até o usuário aprovar** — registrado como regra nº 7.
- Python 3.12 + FastAPI; Docker Compose com 2 serviços: `db` (imagem `pgvector/pgvector:pg16`) e `api`
  — um único PostgreSQL serve dados tabulares e vetores, sem banco vetorial separado.
- Orquestrador em duas etapas: (1) regras determinísticas (protocolo `OUV-NNNN` → Ouvidoria com
  confiança 1.0; pedido de senha/credencial de terceiros → recusa); (2) classificação pelo LLM com
  saída estruturada (domínio, confiança, justificativa). Confiança < 0,6 → pedir esclarecimento.
- Saída única `RespostaOrquestrador`: pergunta, domínio, confiança, agente, resposta, fontes, dados,
  status (`ok`, `nao_encontrado`, `esclarecimento`, `recusado`, `fora_de_escopo`, `erro`),
  id da requisição e latência.
- Financeiro/Ouvidoria: o LLM só escolhe uma função (tool com schema estrito e enums) e seus
  parâmetros; o código valida, executa SQL parametrizado e monta a resposta por template, então os
  números nunca passam pelo modelo.
- Informações internas: chunks por seção `##` dos Markdown + 1 chunk por item do FAQ, com metadados
  `dominio`, `fonte`, `versao`; embeddings locais multilíngues (sem segunda API key); top-k com limiar
  de similaridade; fontes vêm dos metadados, não do texto do modelo.
- LLM: Claude via SDK oficial `anthropic`, modelo configurável por variável de ambiente
  (padrão `claude-opus-5-5`). API key apenas em `.env` (fora do Git).
- Carga: script Python que lê os CSV (`utf-8-sig`), valida datas/enums/`Decimal` e insere em transação,
  de forma idempotente; o `schema.sql` original é reaproveitado sem alterações.
- Logs: uma linha JSON por pergunta no stdout + tabela `logs_consultas`, com os campos exigidos em
  `ingestao_e_uso.md`; sem segredos e com mascaramento simples de dados pessoais.
**Problemas e soluções:**
- Problema: os arquivos de dados foram movidos para `data/` durante a sessão → Solução: caminhos
  atualizados neste arquivo e no `README.md`.
- Problema: os CSV têm BOM UTF-8 no cabeçalho → Solução (prevista): ler com `encoding="utf-8-sig"`.
- Problema: T010 espera recusa citando `04_seguranca_da_informacao.md` e `09_politica_privacidade.md`
  → Solução (prevista): regra de segurança no orquestrador com resposta de recusa e fontes fixas.
**Código:**
- Nenhum código escrito (aguardando aprovação).
**Testes:**
- Não se aplica ainda. Planejado: pytest para funções SQL (valores esperados calculados de forma
  independente a partir dos CSV), testes das regras do orquestrador e script de avaliação com os
  12 casos de `perguntas_avaliacao.json`.
**Pendências:** aprovação do usuário para a arquitetura proposta.

### [2026-11-16] #04 — Aprovação da arquitetura e implementação inicial
**Prompt:** "1. Utilizarei sonnet para modelo padrão, e Haiku para ser o orquestrador, sempre configurável
pela variável de ambiente LLM_MODEL para manter um custo baixo. 2. Utilizarei o modelo de embeddings
que seja leve e multilíngue via fastembed/ONNX para não exigir uma segunda API Key, documenta o
tamanho da imagem do docker no readme."
**Decisões técnicas:**
- Resposta tratada como aprovação da arquitetura da entrada #03 (as duas pendências foram decididas
  e o pedido de medir a imagem Docker pressupõe implementação).
- Modelos: `LLM_MODEL=claude-sonnet-5-5` (agentes) e `LLM_MODEL_ORQUESTRADOR=claude-haiku-5-5`
  (classificação) — duas variáveis, para os dois papéis continuarem configuráveis de forma independente.
- Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dim., ~0,22 GB),
  baixado no build da imagem para não depender de rede ao subir.
- Classificação via structured outputs (`output_config.format` com JSON Schema); agentes via tools
  com `strict: true` e `tool_choice: auto` (Sonnet 5.5 não aceita tool forçada); `effort: low`.
- Fallback do servidor da Anthropic em recusas (`fallbacks: "default"`) habilitado para Sonnet/Opus;
  desativável com `LLM_FALLBACK=off`. O Haiku não tem fallback.
- SQL fixo com filtros opcionais no padrão `(%(x)s::tipo IS NULL OR coluna = %(x)s)`; colunas de
  agrupamento vêm de dicionário fixo, nunca do modelo.
- Chunking por seção `##` (documentos curtos; 20 trechos no total), sem índice vetorial (varredura
  sequencial é suficiente para esse volume).
- Limiar de similaridade 0,40: medido localmente — perguntas do domínio têm 1º trecho entre 0,57 e
  0,82; perguntas fora do tema ficam ≤ 0,35.
- `pytest`/`httpx` em `requirements-dev.txt`, fora da imagem de produção.
**Problemas e soluções:**
- Problema: no Windows, `open()` usa cp1252 por padrão → Solução: `encoding` explícito em toda leitura.
- Problema: psycopg não infere o tipo de parâmetro `NULL` em `%s IS NULL` → Solução: casts explícitos
  (`::text`, `::date`, `::text[]`).
- Problema: Docker Desktop não está ativo e não há `.env` → build da imagem, testes de integração e
  avaliação ponta a ponta ainda não executados; tamanho da imagem marcado como "a medir" no README.
**Código:**
- ✅ Aceito: `app/` (config, db, schemas, formatacao, llm, logs, orquestrador, main, agentes/*),
  `scripts/carregar_dados.py`, `scripts/indexar_documentos.py`, `db/init/*.sql`, `Dockerfile`,
  `docker-compose.yml`, `.env.example`, `tests/*`.
- ❌ Descartado: chunks de tamanho fixo (400–800 tokens) — os documentos têm 10–20 linhas, a divisão
  por seção preserva o contexto de cada regra.
- ❌ Descartado: índice HNSW/IVFFlat — desnecessário para ~20 vetores.
- ❌ Descartado: LLM redigindo respostas numéricas — risco de alterar valores; templates determinísticos.
**Testes:**
- `python -m pytest` → 37 passed, 7 skipped (integração pulada: PostgreSQL indisponível).
- Smoke test com `TestClient`: `/saude` → `degradado` sem banco; T010 → `recusado` com fontes 04 e 09;
  pergunta com 1 caractere → HTTP 422.
- Recuperação RAG (sem banco, similaridade em memória): documento esperado em 1º lugar para T001,
  T002, T003, T008 e T012.
**Pendências:** iniciar o Docker Desktop e criar o `.env` para: `docker compose up --build`, medir e
documentar o tamanho das imagens, rodar `pytest -m integracao` e `python -m tests.avaliar`.

### [2026-11-16] #05 — Provedor de LLM configurável (Gemini padrão + Anthropic)
**Prompt:** trocar o provedor de LLM por variável de ambiente (`LLM_PROVIDER`), com suporte a Gemini e
Anthropic e Gemini como padrão no `.env.example`; manter os embeddings locais; documentar no README
como obter chave gratuita do Gemini e como trocar de provedor; garantir que os testes unitários
rodem sem chave (só integração e avaliação precisam); salvar resultados e logs da avaliação em
arquivo no repositório, sem chaves nem dados sensíveis.
**Decisões técnicas:**
- `app/llm.py` virou uma camada com interface única (`gerar_json`, `escolher_ferramenta`) e dois
  adaptadores: `ProvedorGemini` (SDK oficial `google-genai`) e `ProvedorAnthropic` (SDK `anthropic`).
  Agentes e orquestrador não mudaram.
- Gemini: saída estruturada com `response_mime_type="application/json"` + `response_json_schema`;
  funções com `FunctionDeclaration(parameters_json_schema=...)`, modo `AUTO` e
  `automatic_function_calling` desativado (quem executa é o nosso código, após validação Pydantic).
- Definição de ferramenta neutra (`name`, `description`, `input_schema`); `strict: true` é
  adicionado só no adaptador da Anthropic.
- Modelos padrão por provedor quando `LLM_MODEL`/`LLM_MODEL_ORQUESTRADOR` estão vazios. Gemini:
  `gemini-3.8-flash` (agentes) e `gemini-3.5-flash-lite` (orquestrador), escolhidos entre os modelos
  marcados como estáveis na documentação do Google em 2026-11-16 (`gemini-2.5-flash` está
  descontinuado). Anthropic: `claude-sonnet-5-5` e `claude-haiku-5-5`.
- Validação de coerência: modelo que não pertence ao provedor (ex.: `gemini` + `claude-*`) gera erro
  claro, em vez de uma chamada inválida à API.
- Clientes dos SDKs criados só na primeira chamada: importar o código não exige chave.
- `app/config.py` lê o `.env` local sem sobrescrever o ambiente, para scripts e testes fora do Docker.
- Logs: novo campo `provedor_llm`; mascaramento ampliado para chaves (`AIza…`, `sk-ant-…`,
  `api_key=`/`token=`/`senha=`) também no campo `erro`; `logs.assinantes` permite à avaliação
  coletar os eventos já mascarados.
- Avaliação grava `resultados/avaliacao_<provedor>.md` (tabela por caso, totais e logs em JSON Lines).
- Embeddings continuam locais (`paraphrase-multilingual-MiniLM-L12-v2`): trocar de provedor não
  exige reindexar.
**Problemas e soluções:**
- Problema: o `.env` local foi criado a partir do exemplo antigo (sem `LLM_PROVIDER`/`GEMINI_API_KEY`
  e com `LLM_MODEL` da Anthropic) → Solução: validação de coerência provedor/modelo e instrução para
  recriar o `.env` a partir do novo `.env.example`. O `.env` do usuário não foi alterado nem lido
  (só os nomes das variáveis foram verificados).
- Problema: testes de integração ficavam ~4 min presos tentando conectar ao banco indisponível →
  Solução: `connect_timeout=5` em `app/db.py` (suíte completa caiu para ~14 s).
- Problema: os testes unitários poderiam usar uma chave presente no `.env` → Solução: fixture
  `autouse` em `tests/conftest.py` remove as variáveis de chave em todo teste sem a marca
  `integracao`; um teste verifica isso.
- Problema: Docker Desktop responde "Internal Server Error" na API do daemon → build, integração e
  avaliação continuam pendentes.
**Código:**
- ✅ Aceito: `app/llm.py` (adaptadores), `app/config.py` (provedor, padrões, leitura do `.env`),
  `app/logs.py`, `tests/test_llm.py`, `tests/test_integracao_llm.py`, `tests/conftest.py`,
  `tests/avaliar.py` (gravação dos resultados), `.env.example`, `README.md`, `requirements.txt`
  (`google-genai==2.33.0`), `db/init/02_rag_e_logs.sql` (coluna `provedor_llm`).
- ❌ Descartado: camada genérica de terceiros (LangChain/LiteLLM) — dependência grande para só duas
  operações; os SDKs oficiais bastam.
- ❌ Descartado: modo `ANY` (função forçada) no Gemini — o agente precisa poder não chamar função
  quando a pergunta não é respondível.
**Testes:**
- `python -m pytest -m "not integracao"` → 51 passed, sem nenhuma chave no ambiente.
- `python -m pytest` → 51 passed, 13 skipped (7 por PostgreSQL indisponível; 6 por falta de
  `GEMINI_API_KEY`).
- Avaliação dos 12 casos: não executada (sem banco e sem chave); `resultados/` ainda não gerado.
**Pendências:** recriar o `.env` a partir do `.env.example` com `GEMINI_API_KEY`; reiniciar o Docker
Desktop; `docker compose up --build`; medir as imagens; rodar `pytest -m integracao` e
`python -m tests.avaliar` e versionar `resultados/avaliacao_gemini.md`.

### [2026-11-17] #06 — Build Docker, testes de integração e avaliação com Gemini
**Prompt:** "Modifiquei aqui o .env e também rodei um build"
**Decisões técnicas:**
- Retentativas no adaptador Gemini via `HttpRetryOptions` do próprio SDK (`LLM_TENTATIVAS`, padrão 4,
  backoff exponencial em 408/429/5xx) — o SDK da Anthropic já faz isso por padrão.
- Avaliação e testes rodados localmente contra o banco do Docker (`DATABASE_URL` do `.env`), com o
  mesmo modelo de embeddings da imagem.
**Problemas e soluções:**
- Problema: 1ª execução da avaliação teve 11/12 em domínio e 10/12 em fonte — T006 e T008 terminaram
  em `status=erro` com `ServerError 503` do Gemini (sobrecarga transitória, não erro de lógica) →
  Solução: retentativas com backoff; 2ª execução 12/12.
- Problema: `curl` no Git Bash enviou o JSON com acentos em codificação inválida (resposta sem
  `dominio`) → não é defeito da API; o mesmo pedido via `httpx` em UTF-8 funcionou.
**Código:**
- ✅ Aceito: retentativas em `app/llm.py`, `LLM_TENTATIVAS` em `app/config.py` e `.env.example`,
  teste `test_cliente_gemini_configura_retentativas`, tamanhos das imagens no `README.md`.
**Testes:**
- Contêineres: carga 300/144/180 linhas, 20 trechos indexados de 10 documentos, `/saude` → ok.
- `pytest -m "not integracao"` → 52 passed (sem chave). `pytest -m integracao` → 13 passed
  (SQL no PostgreSQL real + classificação e escolha de função com Gemini).
- `python -m tests.avaliar` (gemini-3.8-flash / gemini-3.5-flash-lite) → domínio 12/12, fonte 12/12,
  critério por palavras-chave 12/12; latência de 0 ms (regras) a ~18 s (RAG). Resultado e logs em
  `resultados/avaliacao_gemini.md`; verificado que o arquivo não contém a chave do `.env`, nem
  credenciais do banco, nem e-mails além do fictício `seguranca@aurora.example`.
- Conferência independente pelos CSV: T006 = R$ 305.937,01; T011 = R$ 275.727,70; "manifestações de
  Cobrança com status Aberto" = 7 — iguais às respostas da API.
- Imagens: `areco-ai-agent-api` 1,11 GB em disco (366 MB compactada); `pgvector/pgvector:pg16`
  647 MB (162 MB).
**Pendências:** commit. (Avaliação com Anthropic: ver entrada #07.)

### [2026-11-17] #07 — Anthropic fora do escopo da avaliação
**Prompt:** "A avaliação com LLM_PROVIDER=anthropic não será avaliada por uma limitação da chave da API"
**Decisões técnicas:**
- A avaliação oficial do projeto é a do Gemini (`resultados/avaliacao_gemini.md`, 12/12). O suporte a
  Anthropic permanece no código (`ProvedorAnthropic`), coberto apenas por testes unitários com cliente
  falso; não foi validado contra a API real.
- Nenhum código removido: a troca de provedor continua disponível para quem tiver chave, e o README
  indica como validar (`pytest -m integracao` e `python -m tests.avaliar`).
**Problemas e soluções:**
- Problema: a chave de API da Anthropic disponível não permite executar a avaliação → Solução:
  limitação documentada no README (tabela "Status de validação por provedor") e neste arquivo.
**Código:**
- ✅ Aceito: seção "Status de validação por provedor" no `README.md`; status atualizado no `CLAUDE.md`.
**Testes:**
- Nenhum teste novo. Os testes de integração com LLM rodam contra o provedor configurado e são
  pulados se não houver chave, então a ausência da chave da Anthropic não quebra a suíte.
**Pendências:** commit.
