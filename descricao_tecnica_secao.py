"""
Monta a secao "Descricao Tecnica" (memorial descritivo) como subdocumento
docxtpl, inserida no lugar do placeholder {{p descricao_tecnica}} -- apenas
na Proposta Tecnica.

Comeca em pagina nova, com titulo estilo Heading 1 e bookmark _Toc190957976
(reaproveitado no template tecnica para a entrada do Sumario). No fim, uma
linha de "Prazo de execucao" (a Tecnica nao tem a pagina de Prazo e Preco).
"""
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips

from revisao_secao import RECUO_ESQUERDO_PADRAO, RECUO_PRIMEIRA_LINHA_PADRAO

FONT_NAME = "Trebuchet MS"
BOOKMARK_NAME = "_Toc190957976"
BOOKMARK_ID = 900


def _envolver_com_bookmark(paragraph, nome=BOOKMARK_NAME, bm_id=BOOKMARK_ID):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bm_id))
    start.set(qn("w:name"), nome)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bm_id))

    p = paragraph._p
    pPr = p.find(qn("w:pPr"))
    if pPr is not None:
        pPr.addnext(start)
    else:
        p.insert(0, start)
    p.append(end)


def montar_secao_descricao_tecnica(subdoc, texto: str, prazo_execucao: str = ""):
    titulo = subdoc.add_paragraph()
    titulo.paragraph_format.page_break_before = True
    titulo.paragraph_format.left_indent = Twips(1701)
    try:
        titulo.style = "Heading 1"
    except KeyError:
        pass
    run_t = titulo.add_run("Descrição Técnica")
    run_t.bold = True
    _envolver_com_bookmark(titulo)

    for linha in (texto or "").split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        p = subdoc.add_paragraph()
        p.paragraph_format.left_indent = RECUO_ESQUERDO_PADRAO
        p.paragraph_format.first_line_indent = RECUO_PRIMEIRA_LINHA_PADRAO
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run(linha)
        run.font.name = FONT_NAME
        run.font.size = Pt(11)

    if prazo_execucao:
        subdoc.add_paragraph()
        p = subdoc.add_paragraph()
        p.paragraph_format.left_indent = RECUO_ESQUERDO_PADRAO
        r1 = p.add_run("Prazo de execução: ")
        r1.bold = True
        r1.font.name = FONT_NAME
        r1.font.size = Pt(11)
        r2 = p.add_run(
            f"{prazo_execucao} a partir do aceite da proposta e mobilização "
            "da equipe e materiais."
        )
        r2.font.name = FONT_NAME
        r2.font.size = Pt(11)
