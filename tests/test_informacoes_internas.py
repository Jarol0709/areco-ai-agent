from app.agentes.informacoes_internas import carregar_chunks, dividir_markdown
from tests.conftest import DADOS

DIR = DADOS / "informacoes_internas"


def test_chunk_por_secao_com_versao():
    chunks = dividir_markdown(DIR / "01_politica_ferias.md")
    assert [c.secao for c in chunks] == ["Regras", "Limites do agente"]
    regras = next(c for c in chunks if c.secao == "Regras")
    assert regras.versao == "1.2 — 10/01/2026"
    assert "30 dias corridos" in regras.conteudo
    assert regras.texto_indexado().startswith("Política de férias")


def test_documento_sem_secoes_vira_um_chunk():
    chunks = dividir_markdown(DIR / "04_seguranca_da_informacao.md")
    assert len(chunks) == 1
    assert "seguranca@aurora.example" in chunks[0].conteudo


def test_todos_os_documentos_e_faq_indexados():
    chunks = carregar_chunks(DIR)
    fontes = {c.fonte for c in chunks}
    assert {f"{p.name}" for p in DIR.glob("*.md")} <= fontes
    faq = [c for c in chunks if c.ids]
    assert len(faq) == 7  # faq_itens em manifesto_pacote.json
    assert all(c.fonte.endswith(".md") for c in faq)  # FAQ aponta para o documento de origem
