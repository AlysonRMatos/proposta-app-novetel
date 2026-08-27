"""Monta a secao "Revisao" do documento (subdocumento docxtpl), usada
apenas quando a proposta atual e uma revisao de uma proposta existente.
Quando nao e revisao, o subdoc fica vazio e a secao nao aparece."""
from docx.shared import Pt

from itens_tabela import montar_tabela_itens

FONT_NAME = "Trebuchet MS"
HEADING_COLOR_HEX = "1F497D"


def montar_secao_revisao(
    subdoc,
    ativa: bool,
    codigo_pai: str = None,
    numero_revisao: int = None,
    solicitacao_alteracao: str = None,
    itens_antigos: list = None,
    itens_novos: list = None,
):
    if not ativa:
        return

    from docx.shared import RGBColor

    def add_heading(texto, size=20):
        p = subdoc.add_paragraph()
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(10)
        run = p.add_run(texto)
        run.font.name = "Arial Narrow"
        run.font.size = Pt(size)
        run.font.bold = True
        run.font.color.rgb = RGBColor.from_string(HEADING_COLOR_HEX)

    def add_body(texto, bold=False, space_after=8):
        p = subdoc.add_paragraph()
        p.paragraph_format.space_after = Pt(space_after)
        run = p.add_run(texto)
        run.font.name = FONT_NAME
        run.font.size = Pt(11)
        run.font.bold = bold

    add_heading(f"Revisão RV{numero_revisao:02d}")
    if codigo_pai:
        add_body(f"Referente à proposta original: {codigo_pai}", space_after=10)

    add_body("Solicitação de alteração desta revisão:", bold=True, space_after=4)
    add_body(solicitacao_alteracao or "Não informado.", space_after=14)

    if itens_antigos:
        add_body("Itens da versão anterior (referência):", bold=True, space_after=6)
        montar_tabela_itens(subdoc, itens_antigos)
        subdoc.add_paragraph()

    if itens_novos:
        add_body("Itens desta revisão (atual):", bold=True, space_after=6)
        montar_tabela_itens(subdoc, itens_novos)
