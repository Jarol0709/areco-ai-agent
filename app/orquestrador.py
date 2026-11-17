"""Orquestrador: regras determinísticas, depois classificação pelo LLM e roteamento ao agente."""
import re
import time
import uuid
from datetime import datetime, timezone

from app import llm, logs
from app.agentes import financeiro, informacoes_internas, ouvidoria
from app.config import config
from app.schemas import Classificacao, Fonte, RespostaOrquestrador, ResultadoAgente

AGENTES = {
    "financeiro": ("agente_financeiro", financeiro.responder),
    "informacoes_internas": ("agente_informacoes_internas", informacoes_internas.responder),
    "ouvidoria": ("agente_ouvidoria", ouvidoria.responder),
}

PADRAO_CREDENCIAL = re.compile(r"\b(senhas?|credenciais?|tokens?|chaves? de api|login)\b", re.IGNORECASE)
PADRAO_TERCEIRO = re.compile(
    r"\b(outr[oa]s?|colegas?|colaborador(?:a|es|as)?|terceir[oa]s?|funcion[áa]ri[oa]s?|chefe|gestor[a]?|"
    r"diretor[a]?|cliente|dele|dela|fulano)\b",
    re.IGNORECASE,
)

RESPOSTA_RECUSA = (
    "Não posso informar senhas, tokens ou credenciais de outras pessoas. Credenciais são pessoais e não "
    "devem ser compartilhadas por e-mail ou chat, e o agente não revela dados de outros colaboradores. "
    "Para acesso a sistemas, abra um chamado no portal de TI com aprovação da liderança; suspeitas de "
    "incidente devem ser reportadas a seguranca@aurora.example."
)
FONTES_RECUSA = [Fonte(arquivo="04_seguranca_da_informacao.md"), Fonte(arquivo="09_politica_privacidade.md")]

RESPOSTA_FORA_ESCOPO = (
    "Esta pergunta está fora do escopo do assistente. Posso ajudar apenas com: Financeiro (lançamentos e "
    "orçamento), Informações internas (políticas e procedimentos) e Ouvidoria (manifestações e protocolos)."
)
RESPOSTA_ESCLARECIMENTO = (
    "Não tenho certeza sobre o assunto da pergunta. Ela se refere a dados financeiros, a políticas e "
    "procedimentos internos ou a manifestações da ouvidoria? Se puder, inclua mais detalhes (período, "
    "protocolo ou documento)."
)

SYSTEM_CLASSIFICACAO = """Classifique a pergunta de um colaborador da Aurora Serviços Digitais S.A. (empresa fictícia) em UM domínio:
- financeiro: valores, somas, receitas, despesas, lançamentos, orçamento, execução orçamentária, inadimplência, centros de custo e departamentos (dados numéricos da base financeira).
- informacoes_internas: políticas e procedimentos internos (férias, reembolso, aprovação de compras, segurança da informação, acessos a sistemas, home office, incidentes, RH, privacidade, fechamento financeiro como processo).
- ouvidoria: manifestações, reclamações, protocolos OUV-NNNN, status/categorias/prioridades/canais da ouvidoria.
- fora_de_escopo: qualquer outro assunto.
Atenção: "como funciona o reembolso" é informacoes_internas; "quanto foi gasto" é financeiro; "manifestações de reembolso" é ouvidoria.
confianca é um número de 0 a 1 que indica sua certeza. Use menos de 0.6 quando a pergunta for ambígua entre domínios ou vaga demais."""

SCHEMA_CLASSIFICACAO = {
    "type": "object",
    "properties": {
        "dominio": {"type": "string", "enum": ["financeiro", "informacoes_internas", "ouvidoria", "fora_de_escopo"]},
        "confianca": {"type": "number"},
        "justificativa": {"type": "string"},
    },
    "required": ["dominio", "confianca", "justificativa"],
    "additionalProperties": False,
}


def pede_credencial_de_terceiro(pergunta: str) -> bool:
    return bool(PADRAO_CREDENCIAL.search(pergunta) and PADRAO_TERCEIRO.search(pergunta))


def classificar(pergunta: str) -> Classificacao:
    if ouvidoria.PADRAO_PROTOCOLO.search(pergunta):
        return Classificacao(dominio="ouvidoria", confianca=1.0, justificativa="regra: protocolo OUV-NNNN")
    saida = llm.gerar_json(config.llm_model_orquestrador, SYSTEM_CLASSIFICACAO, pergunta,
                           SCHEMA_CLASSIFICACAO, max_tokens=2000)
    saida["confianca"] = min(max(float(saida["confianca"]), 0.0), 1.0)
    return Classificacao.model_validate(saida)


def responder(pergunta: str) -> RespostaOrquestrador:
    inicio = time.perf_counter()
    id_requisicao = str(uuid.uuid4())
    uso = {"entrada": 0, "saida": 0}
    token_uso = llm.uso_tokens.set(uso)
    dominio, confianca, agente, erro = None, 0.0, None, None
    try:
        if pede_credencial_de_terceiro(pergunta):
            dominio, confianca, agente = "fora_de_escopo", 1.0, "regra_seguranca"
            resultado = ResultadoAgente(status="recusado", resposta=RESPOSTA_RECUSA, fontes=FONTES_RECUSA)
        else:
            c = classificar(pergunta)
            dominio, confianca = c.dominio, c.confianca
            if c.dominio == "fora_de_escopo":
                resultado = ResultadoAgente(status="fora_de_escopo", resposta=RESPOSTA_FORA_ESCOPO)
            elif c.confianca < config.limiar_confianca:
                resultado = ResultadoAgente(status="esclarecimento", resposta=RESPOSTA_ESCLARECIMENTO)
            else:
                agente, executar = AGENTES[c.dominio]
                resultado = executar(pergunta)
    except Exception as exc:
        erro = f"{type(exc).__name__}: {exc}"
        resultado = ResultadoAgente(status="erro", resposta="Não foi possível processar a pergunta agora. Tente novamente.")
    finally:
        llm.uso_tokens.reset(token_uso)

    latencia_ms = int((time.perf_counter() - inicio) * 1000)
    resposta = RespostaOrquestrador(
        id_requisicao=id_requisicao, pergunta=pergunta, dominio=dominio, confianca=confianca, agente=agente,
        status=resultado.status, resposta=resultado.resposta, fontes=resultado.fontes, dados=resultado.dados,
        latencia_ms=latencia_ms,
    )
    logs.registrar({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "id_requisicao": id_requisicao,
        "pergunta": pergunta,
        "dominio_previsto": dominio,
        "confianca": confianca,
        "agente": agente,
        "ferramenta": resultado.ferramenta,
        "parametros": resultado.parametros,
        "fontes": [f.model_dump() for f in resultado.fontes],
        "latencia_ms": latencia_ms,
        "tokens_entrada": uso["entrada"],
        "tokens_saida": uso["saida"],
        "provedor_llm": config.llm_provider,
        "status": resultado.status,
        "erro": erro,
    })
    return resposta
