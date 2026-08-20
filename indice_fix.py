"""
Corrige os numeros de pagina do indice (Sumario) da proposta gerada.

O indice usa campos nativos do Word (TOC + PAGEREF) cujo resultado fica
"congelado" no valor que estava salvo no documento original -- nem
python-docx nem a conversao via LibreOffice recalculam esse valor
automaticamente. Este modulo descobre a pagina real de cada secao
(convertendo o docx para PDF uma primeira vez e localizando cada titulo)
e substitui o texto em cache dos campos PAGEREF pelo numero correto,
sem depender de o usuario abrir o Word e mandar atualizar campos.
"""
import io

from docx import Document
from docx.oxml.ns import qn

# bookmark do indice -> texto exato do titulo da secao no corpo do documento
BOOKMARK_HEADINGS = {
    "_Toc190957971": "Quem somos?",
    "_Toc190957972": "Objetivos",
    "_Toc190957973": "Documentos disponibilizados",
    "_Toc190957974": "Escopo",
    "_Toc190957975": "Especificações",
    "_Toc190957976": "Prazo e Preço",
    "_Toc190957977": "Condições Gerais",
}


def mapear_paginas_por_titulo(pdf_bytes: bytes) -> dict:
    """Abre o PDF e retorna {texto_do_titulo: numero_da_pagina (1-indexado)},
    usando a primeira ocorrencia de cada titulo encontrada apos a pagina do
    proprio indice (que tambem lista o nome de cada secao, e nao pode ser
    confundida com a secao real)."""
    import fitz  # PyMuPDF

    resultado = {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pagina_indice = None
        for pagina_idx in range(doc.page_count):
            if doc[pagina_idx].search_for("Índice"):
                pagina_indice = pagina_idx
                break
        inicio_busca = (pagina_indice + 1) if pagina_indice is not None else 0

        for titulo in BOOKMARK_HEADINGS.values():
            for pagina_idx in range(inicio_busca, doc.page_count):
                if doc[pagina_idx].search_for(titulo):
                    resultado[titulo] = pagina_idx + 1
                    break
    finally:
        doc.close()
    return resultado


def _atualizar_cache_pageref(document_element, mapa_bookmark_pagina: dict):
    for instr in document_element.findall(".//" + qn("w:instrText")):
        texto = (instr.text or "").strip()
        if not texto.startswith("PAGEREF"):
            continue
        partes = texto.split()
        bookmark_name = partes[1] if len(partes) > 1 else None
        pagina = mapa_bookmark_pagina.get(bookmark_name)
        if pagina is None:
            continue

        run_instr = instr.getparent()
        parent = run_instr.getparent()
        siblings = list(parent)
        idx_instr_run = siblings.index(run_instr)

        dentro_do_resultado = False
        ultimo_wt = None
        for el in siblings[idx_instr_run + 1:]:
            fld = el.find(qn("w:fldChar"))
            if fld is not None:
                tipo = fld.get(qn("w:fldCharType"))
                if tipo == "separate":
                    dentro_do_resultado = True
                    continue
                if tipo == "end":
                    break
            if dentro_do_resultado:
                wt = el.find(qn("w:t"))
                if wt is not None:
                    ultimo_wt = wt
        if ultimo_wt is not None:
            ultimo_wt.text = str(pagina)


def corrigir_indice(docx_bytes: bytes, pdf_bytes_primeira_passada: bytes) -> bytes:
    """Recebe os bytes do docx gerado e de uma primeira conversao em PDF
    (usada so para descobrir as paginas reais), e retorna os bytes do docx
    com os numeros do indice corrigidos."""
    mapa_paginas = mapear_paginas_por_titulo(pdf_bytes_primeira_passada)
    mapa_bookmark_pagina = {
        bookmark: mapa_paginas[titulo]
        for bookmark, titulo in BOOKMARK_HEADINGS.items()
        if titulo in mapa_paginas
    }
    if not mapa_bookmark_pagina:
        return docx_bytes

    doc = Document(io.BytesIO(docx_bytes))
    _atualizar_cache_pageref(doc.element.body, mapa_bookmark_pagina)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
