// Frontend do chat: envia a pergunta para POST /perguntas e mostra resposta, domínio e fontes.
// Todo conteúdo vindo da API é inserido com textContent, nunca interpretado como HTML.
"use strict";

const ENDPOINT = "/perguntas";

const NOMES_DOMINIO = {
  financeiro: "Financeiro",
  informacoes_internas: "Informações internas",
  ouvidoria: "Ouvidoria",
  fora_de_escopo: "Fora de escopo",
};

const CLASSE_STATUS = {
  ok: "status-ok",
  nao_encontrado: "status-aviso",
  esclarecimento: "status-aviso",
  fora_de_escopo: "status-aviso",
  recusado: "status-erro",
  erro: "status-erro",
};

const mensagens = document.getElementById("mensagens");
const formulario = document.getElementById("formulario");
const campo = document.getElementById("pergunta");
const botao = document.getElementById("enviar");

function elemento(tag, classe, texto) {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

function adicionar(el) {
  mensagens.appendChild(el);
  mensagens.scrollTop = mensagens.scrollHeight;
  return el;
}

function etiqueta(texto, classe) {
  return elemento("span", "etiqueta" + (classe ? " " + classe : ""), texto);
}

function renderizarResposta(r) {
  const caixa = elemento("div", "msg assistente");
  caixa.appendChild(elemento("div", "texto", r.resposta || "(sem resposta)"));

  const meta = elemento("div", "meta");
  const dominio = r.dominio ? (NOMES_DOMINIO[r.dominio] || r.dominio) : "sem domínio";
  meta.appendChild(etiqueta("Domínio: " + dominio, "dominio"));
  meta.appendChild(etiqueta("Confiança: " + Math.round((r.confianca || 0) * 100) + "%"));
  meta.appendChild(etiqueta("Status: " + r.status, CLASSE_STATUS[r.status]));
  if (r.agente) meta.appendChild(etiqueta("Agente: " + r.agente));
  if (typeof r.latencia_ms === "number") meta.appendChild(etiqueta(r.latencia_ms + " ms"));
  caixa.appendChild(meta);

  const fontes = elemento("div", "fontes");
  if (r.fontes && r.fontes.length) {
    fontes.appendChild(elemento("strong", null, "Fontes:"));
    const lista = elemento("ul");
    for (const f of r.fontes) {
      const item = elemento("li");
      item.appendChild(elemento("code", null, f.arquivo));
      if (f.secao) item.appendChild(document.createTextNode(" — " + f.secao));
      if (f.ids && f.ids.length) item.appendChild(document.createTextNode(" (" + f.ids.join(", ") + ")"));
      lista.appendChild(item);
    }
    fontes.appendChild(lista);
  } else {
    fontes.textContent = "Fontes: nenhuma";
  }
  caixa.appendChild(fontes);
  return caixa;
}

function mensagemDeErro(status, corpo) {
  if (status === 422) return "Pergunta inválida: use entre 3 e 1000 caracteres.";
  const detalhe = corpo && typeof corpo.detail === "string" ? " " + corpo.detail : "";
  return "Erro ao consultar a API (HTTP " + status + ")." + detalhe;
}

async function enviar(pergunta) {
  const boasVindas = mensagens.querySelector(".boas-vindas");
  if (boasVindas) boasVindas.remove();

  adicionar(elemento("div", "msg usuario", pergunta));
  const carregando = adicionar(elemento("div", "msg assistente carregando", "Consultando…"));
  botao.disabled = true;

  try {
    const resp = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({ pergunta }),
    });
    const corpo = await resp.json().catch(() => null);
    carregando.remove();
    if (!resp.ok || !corpo) {
      adicionar(elemento("div", "msg assistente", mensagemDeErro(resp.status, corpo)));
    } else {
      adicionar(renderizarResposta(corpo));
    }
  } catch (e) {
    carregando.remove();
    adicionar(elemento("div", "msg assistente", "Não foi possível conectar à API."));
  } finally {
    botao.disabled = false;
    campo.focus();
  }
}

formulario.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const pergunta = campo.value.trim();
  if (pergunta.length < 3 || botao.disabled) return;
  campo.value = "";
  enviar(pergunta);
});

campo.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    formulario.requestSubmit();
  }
});

for (const b of document.querySelectorAll(".exemplo")) {
  b.addEventListener("click", () => enviar(b.textContent));
}
