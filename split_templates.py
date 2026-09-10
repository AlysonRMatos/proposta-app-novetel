"""
Deriva os dois templates de proposta do master `template_proposta.docx`:

  template_tecnica.docx   -> tudo menos a pagina "Prazo e Preco"; a entrada
                             "Prazo e Preco" do Sumario vira "Descricao Tecnica"
                             (a secao em si e montada em tempo de render).
  template_comercial.docx -> sem "Especificacoes", sem a tabela de itens, sem
                             Observacoes e sem a Descricao Tecnica; mantem a
                             pagina "Prazo e Preco".

Cirurgia direta no word/document.xml (mesma tecnica de rodape_paginacao_fix).
Idempotente.
"""
import copy
import os
import zipfile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(tag):
    return f"{{{W}}}{tag}"


def _texto(p):
    return "".join(t.text or "" for t in p.iter(_q("t")))


def _pstyle(p):
    pPr = p.find(_q("pPr"))
    if pPr is None:
        return ""
    st = pPr.find(_q("pStyle"))
    return st.get(_q("val")) if st is not None else ""


def _is_h1(p):
    return _pstyle(p) in ("Ttulo1", "Heading1")


def _is_h2(p):
    return _pstyle(p) in ("Ttulo2", "Heading2")


def _remove(el):
    el.getparent().remove(el)


def _vazio(p):
    """Paragrafo sem texto, sem imagem e sem sectPr -- so ocupa espaco."""
    if _texto(p).strip():
        return False
    if p.find(".//" + _q("drawing")) is not None or p.find(".//" + _q("pict")) is not None:
        return False
    pPr = p.find(_q("pPr"))
    return not (pPr is not None and pPr.find(_q("sectPr")) is not None)


def _definir_titulo_capa(root, texto):
    """Troca o titulo da capa ("Proposta Tecnica Comercial") pelo `texto`."""
    for p in root.iter(_q("p")):
        if _texto(p).strip() == "Proposta Técnica Comercial":
            ts = list(p.iter(_q("t")))
            if ts:
                ts[0].text = texto
                for t in ts[1:]:
                    t.text = ""
            return


def _quebra_pagina_antes(p):
    pPr = p.find(_q("pPr"))
    if pPr is None:
        pPr = etree.Element(_q("pPr"))
        p.insert(0, pPr)
    if pPr.find(_q("pageBreakBefore")) is None:
        pPr.insert(0, etree.Element(_q("pageBreakBefore")))


def _mapa_bookmarks(root):
    return {
        bm.get(_q("id")): bm.get(_q("name"))
        for bm in root.iter(_q("bookmarkStart"))
        if bm.get(_q("name"))
    }


def _reparar_bookmarks_orfaos(root, id_para_nome):
    """Depois de apagar paragrafos, um <w:bookmarkStart> pode ter sumido e
    deixado o <w:bookmarkEnd> (referenciado por um PAGEREF do Sumario)
    orfao -> "Erro! Indicador nao definido". Recria um start de tamanho
    zero imediatamente antes do end."""
    starts = {bm.get(_q("id")) for bm in root.iter(_q("bookmarkStart"))}
    for end in list(root.iter(_q("bookmarkEnd"))):
        bid = end.get(_q("id"))
        if bid in starts or bid not in id_para_nome:
            continue
        novo = etree.Element(_q("bookmarkStart"))
        novo.set(_q("id"), bid)
        novo.set(_q("name"), id_para_nome[bid])
        end.addprevious(novo)
        starts.add(bid)


# ----------------------------------------------------------- master placeholder

PLACEHOLDER = "{{p descricao_tecnica}}"


def _garantir_placeholder(root):
    """Insere o paragrafo {{p descricao_tecnica}} logo antes de
    {{p secao_revisao}} (que fica logo apos o bloco de Observacoes)."""
    body = root.find(_q("body"))
    for p in body.findall(_q("p")):
        if _texto(p).strip() == PLACEHOLDER:
            return False  # ja existe
    alvo = None
    for p in body.findall(_q("p")):
        if _texto(p).strip() == "{{p secao_revisao}}":
            alvo = p
            break
    if alvo is None:
        raise RuntimeError("placeholder {{p secao_revisao}} nao encontrado no master")
    novo = etree.SubElement(body, _q("p"))
    r = etree.SubElement(novo, _q("r"))
    t = etree.SubElement(r, _q("t"))
    t.text = PLACEHOLDER
    alvo.addprevious(novo)
    return True


# ----------------------------------------------------------------- variantes

def _tecnica(root):
    body = root.find(_q("body"))

    _definir_titulo_capa(root, "Proposta Técnica")

    # 1. apaga a secao "Prazo e Preco" (do Heading 2 ate antes de "Condicoes Gerais")
    apagando = False
    for filho in list(body):
        if filho.tag != _q("p"):
            if apagando:
                _remove(filho)
            continue
        txt = _texto(filho).strip()
        if not apagando and _is_h2(filho) and txt.startswith("Prazo e Pre"):
            apagando = True
        if apagando and _is_h1(filho) and "Condi" in txt and "es Gerais" in txt:
            apagando = False
            continue
        if apagando:
            _remove(filho)

    # 2. tira marcas remanescentes do bookmark 6 (a secao de render recria)
    for bm in root.iter(_q("bookmarkStart")):
        if bm.get(_q("name")) == "_Toc190957976":
            _remove(bm)
    for bm in list(root.iter(_q("bookmarkEnd"))):
        if bm.get(_q("id")) == "6":
            _remove(bm)

    # 3. Sumario: "Prazo e Preco" -> "Descricao Tecnica", nivel 2 -> nivel 1
    for hl in root.iter(_q("hyperlink")):
        if hl.get(_q("anchor")) != "_Toc190957976":
            continue
        for t in hl.iter(_q("t")):
            if t.text and "Prazo e Pre" in t.text:
                t.text = "Descrição Técnica"
        p = hl.getparent()
        while p is not None and p.tag != _q("p"):
            p = p.getparent()
        if p is not None:
            pPr = p.find(_q("pPr"))
            st = pPr.find(_q("pStyle")) if pPr is not None else None
            if st is not None:
                st.set(_q("val"), "Sumrio1")
            ind = pPr.find(_q("ind")) if pPr is not None else None
            if ind is not None:
                _remove(ind)


def _comercial(root):
    body = root.find(_q("body"))

    _definir_titulo_capa(root, "Proposta Comercial")

    alvos_txt = {
        "{{p itens_tabela}}",
        "Observações - itens exclusos desta proposta:",
        "{{ observacoes_exclusao }}",
        "{{p descricao_tecnica}}",
    }
    for p in list(body.findall(_q("p"))):
        txt = _texto(p).strip()
        if txt in alvos_txt:
            _remove(p)
        elif _is_h1(p) and "specifica" in txt.lower():
            _remove(p)

    # Sem "Especificacoes" / tabela / Observacoes / Descricao Tecnica sobra um
    # monte de paragrafo vazio entre "Escopo" e "Prazo e Preco" -> pagina em
    # branco. Remove os vazios e poe a quebra de pagina no proprio "Prazo e
    # Preco" (mantendo {{p secao_revisao}}, que ainda renderiza em revisoes).
    for p in body.findall(_q("p")):
        if _is_h2(p) and _texto(p).strip().startswith("Prazo e Pre"):
            _quebra_pagina_antes(p)
            for anterior in list(p.itersiblings(preceding=True)):
                if anterior.tag != _q("p"):
                    break
                if _texto(anterior).strip() == "{{p secao_revisao}}":
                    continue
                if _vazio(anterior):
                    _remove(anterior)
                    continue
                break
            break

    # (o start orfao do bookmark 6, perdido junto com o heading Especificacoes,
    #  e recriado por _reparar_bookmarks_orfaos)

    # Sumario: remove a linha "Especificacoes"
    for hl in list(root.iter(_q("hyperlink"))):
        if hl.get(_q("anchor")) == "_Toc190957975":
            p = hl.getparent()
            while p is not None and p.tag != _q("p"):
                p = p.getparent()
            _remove(p if p is not None else hl)


# ----------------------------------------------------------------- escrita

def _reescrever(master_path, saida_path, doc_xml_bytes):
    with zipfile.ZipFile(master_path) as z:
        partes = [(i.filename, z.read(i.filename)) for i in z.infolist()]
    tmp = saida_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, dados in partes:
            z.writestr(nome, doc_xml_bytes if nome == "word/document.xml" else dados)
    os.replace(tmp, saida_path)


def gerar_variantes(master_path: str, dir_templates: str) -> None:
    parser = etree.XMLParser(remove_blank_text=False)
    with zipfile.ZipFile(master_path) as z:
        doc_root = etree.fromstring(z.read("word/document.xml"), parser)

    if _garantir_placeholder(doc_root):
        _reescrever(master_path, master_path,
                    etree.tostring(doc_root, xml_declaration=True,
                                   encoding="UTF-8", standalone=True))

    def _fresh():
        with zipfile.ZipFile(master_path) as z:
            return etree.fromstring(z.read("word/document.xml"), parser)

    r = _fresh()
    mapa = _mapa_bookmarks(r)
    _tecnica(r)
    _reparar_bookmarks_orfaos(r, mapa)
    _reescrever(master_path, os.path.join(dir_templates, "template_tecnica.docx"),
                etree.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True))

    r = _fresh()
    mapa = _mapa_bookmarks(r)
    _comercial(r)
    _reparar_bookmarks_orfaos(r, mapa)
    _reescrever(master_path, os.path.join(dir_templates, "template_comercial.docx"),
                etree.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True))


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    gerar_variantes(os.path.join(base, "template_proposta.docx"), base)
    print("template_tecnica.docx e template_comercial.docx gerados.")
