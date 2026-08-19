"""Monta a tabela de especificacoes (itens da LPU) como subdocumento docxtpl."""
from docx.shared import Inches, Pt, RGBColor
from docx.enum.table import WD_TABLE_ALIGNMENT

FONT_NAME = "Trebuchet MS"
HEADER_BG = "1F497D"


def _set_cell_bg(cell, color_hex):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    cell._tc.get_or_add_tcPr().append(shd)


def montar_tabela_itens(subdoc, itens):
    widths = [Inches(1.1), Inches(3.6), Inches(1.0), Inches(0.9)]
    headers = ["Codigo", "Especificacao", "Quantidade", "Unidade"]

    table = subdoc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    header_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        header_cells[i].width = widths[i]
        _set_cell_bg(header_cells[i], HEADER_BG)
        p = header_cells[i].paragraphs[0]
        run = p.add_run(h)
        run.font.bold = True
        run.font.name = FONT_NAME
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    if not itens:
        row = table.add_row()
        cell = row.cells[0]
        for c in row.cells[1:]:
            c.merge(cell)
        cell.text = "Nenhum item selecionado."
        return table

    for item in itens:
        row = table.add_row()
        valores = [
            item.get("codigo", ""),
            item.get("descricao", ""),
            str(item.get("quantidade", "")),
            item.get("unidade", ""),
        ]
        for i, val in enumerate(valores):
            cell = row.cells[i]
            cell.width = widths[i]
            p = cell.paragraphs[0]
            run = p.add_run(val)
            run.font.name = FONT_NAME
            run.font.size = Pt(10)
    return table
