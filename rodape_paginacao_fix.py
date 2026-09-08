"""
Conserta a posicao do numero de pagina nas secoes finais do template.

O documento original tem 5 secoes. As duas ultimas (corpo principal:
Escopo, Especificacoes, Prazo e Preco, Condicoes Gerais -- "pagina 5 em
diante") vem com margem esquerda/direita ZERO e sem rodape proprio, entao
herdam o rodape com o numero de pagina da secao anterior. Como a margem e
zero, o numero (alinhado a direita) cola no canto da folha.

Correcao: cria um footer4.xml (igual ao footer3, mas com recuo direito de
1134 twips) e aponta as duas ultimas secoes para ele. Assim o numero fica
na mesma distancia da borda que nas paginas de margem normal, sem mexer
nas margens (o que deslocaria as formas decorativas ancoradas a margem).

Idempotente: rodar de novo nao duplica nada.
"""
import re
import shutil
import zipfile

REL_ID = "rId100"
FOOTER_NAME = "footer4.xml"

_FOOTER4_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"><w:p w14:paraId="4FD304D1" w14:textId="77777777" w:rsidR="005B6664" w:rsidRDefault="005B6664"><w:pPr><w:pStyle w:val="Rodap"/><w:ind w:right="1134"/><w:jc w:val="right"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>PAGE   \\* MERGEFORMAT</w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>2</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p><w:p w14:paraId="6D6C6D31" w14:textId="77777777" w:rsidR="005B6664" w:rsidRDefault="005B6664"><w:pPr><w:pStyle w:val="Rodap"/></w:pPr></w:p></w:ftr>"""

_CT_OVERRIDE = (
    '<Override PartName="/word/footer4.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
)
_REL = (
    f'<Relationship Id="{REL_ID}" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
    'Target="footer4.xml"/>'
)
_FOOTER_REF = f'<w:footerReference w:type="default" r:id="{REL_ID}"/>'

# As duas ultimas secoes: identificadas pela margem zero + fim de sectPr.
_SECOES_ALVO = [
    (
        '<w:sectPr w:rsidR="00737A27" w:rsidRPr="00B57975"><w:pgSz w:w="11910" w:h="16850"/>'
        '<w:pgMar w:top="1940" w:right="0" w:bottom="280" w:left="0" w:header="360" w:footer="360" w:gutter="0"/>'
        '<w:cols w:space="720"/></w:sectPr>'
    ),
    (
        '<w:sectPr w:rsidR="00737A27" w:rsidRPr="00B57975"><w:pgSz w:w="11910" w:h="16850"/>'
        '<w:pgMar w:top="1940" w:right="0" w:bottom="0" w:left="0" w:header="360" w:footer="360" w:gutter="0"/>'
        '<w:cols w:space="720"/></w:sectPr>'
    ),
]


def corrigir_rodape_paginacao(caminho_docx: str) -> bool:
    """Aplica a correcao no .docx indicado (no lugar). Retorna True se
    alterou, False se ja estava corrigido / nao reconheceu a estrutura."""
    with zipfile.ZipFile(caminho_docx) as z:
        nomes = z.namelist()
        partes = {n: z.read(n) for n in nomes}

    if f"word/{FOOTER_NAME}" in partes:
        return False  # ja aplicado

    doc = partes["word/document.xml"].decode("utf-8")
    ct = partes["[Content_Types].xml"].decode("utf-8")
    rels = partes["word/_rels/document.xml.rels"].decode("utf-8")

    alteracoes = 0
    for sec in _SECOES_ALVO:
        if sec in doc:
            novo = sec.replace(
                '<w:sectPr w:rsidR="00737A27" w:rsidRPr="00B57975">',
                '<w:sectPr w:rsidR="00737A27" w:rsidRPr="00B57975">' + _FOOTER_REF,
                1,
            )
            doc = doc.replace(sec, novo, 1)
            alteracoes += 1

    if alteracoes == 0:
        return False

    ct = ct.replace("</Types>", _CT_OVERRIDE + "</Types>", 1)
    rels = rels.replace("</Relationships>", _REL + "</Relationships>", 1)

    partes["word/document.xml"] = doc.encode("utf-8")
    partes["[Content_Types].xml"] = ct.encode("utf-8")
    partes["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    partes[f"word/{FOOTER_NAME}"] = _FOOTER4_XML.encode("utf-8")

    tmp = caminho_docx + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml primeiro, por convencao
        z.writestr("[Content_Types].xml", partes.pop("[Content_Types].xml"))
        for nome, dados in partes.items():
            z.writestr(nome, dados)
    shutil.move(tmp, caminho_docx)
    return True


if __name__ == "__main__":
    import os
    alvo = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "templates", "template_proposta.docx")
    print("Alterado." if corrigir_rodape_paginacao(alvo) else "Nada a fazer (ja corrigido).")
