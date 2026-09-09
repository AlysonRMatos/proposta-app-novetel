"""
Casamento de itens da LPU com descricoes tecnicas ja aprendidas (glossario
guardado no banco -- ver db.listar_glossario / db.aprender_descricoes).

- normalizar(): forma canonica da descricao do item (minusculo, sem
  pontuacao/acento redundante, espacos colapsados) usada como chave.
- casar(): dado o texto do item e as linhas do glossario, devolve a melhor
  descricao tecnica -- exata primeiro, depois aproximada (difflib), trocando
  a medida (ex.: 200x100 -> 150x50) quando a base tinha uma medida diferente.
"""
import re
import unicodedata
from difflib import SequenceMatcher

LIMIAR_APROXIMADO = 0.82

_MEDIDA = re.compile(r"\d{1,4}\s*[xX]\s*\d{1,4}(?:\s*[xX]\s*\d{1,4})?")
_BITOLA = re.compile(r"\d+(?:[.,]\d+)?\s*mm(?:²|2)?", re.IGNORECASE)


def _sem_acento(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def normalizar(desc: str) -> str:
    s = _sem_acento((desc or "").lower())
    s = re.sub(r"[^a-z0-9x,]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _medida(desc: str) -> str:
    m = _MEDIDA.search(desc or "")
    return re.sub(r"\s+", "", m.group(0)).lower() if m else ""


def _bitola(desc: str) -> str:
    m = _BITOLA.search(desc or "")
    return re.sub(r"\s+", "", m.group(0)).lower() if m else ""


def _trocar_medida(texto: str, de: str, para: str) -> str:
    if de and para and de != para:
        texto = re.sub(re.escape(de), para, texto, flags=re.IGNORECASE)
    return texto


def casar(descricao_lpu: str, glossario: list) -> str | None:
    """glossario: lista de linhas com .descricao_lpu e .texto (ou tuplas
    (chave, descricao_lpu, texto, ...))."""
    if not glossario:
        return None

    def campos(linha):
        if hasattr(linha, "descricao_lpu"):
            return linha.descricao_lpu, linha.texto
        return linha[1], linha[2]

    alvo = normalizar(descricao_lpu)
    if not alvo:
        return None

    # 1. match exato pela chave normalizada
    for linha in glossario:
        base_desc, base_txt = campos(linha)
        if normalizar(base_desc) == alvo:
            return base_txt

    # 2. match aproximado
    melhor, melhor_ratio, melhor_desc = None, 0.0, ""
    for linha in glossario:
        base_desc, base_txt = campos(linha)
        ratio = SequenceMatcher(None, alvo, normalizar(base_desc)).ratio()
        if ratio > melhor_ratio:
            melhor, melhor_ratio, melhor_desc = base_txt, ratio, base_desc

    if melhor is not None and melhor_ratio >= LIMIAR_APROXIMADO:
        texto = _trocar_medida(melhor, _medida(melhor_desc), _medida(descricao_lpu))
        texto = _trocar_medida(texto, _bitola(melhor_desc), _bitola(descricao_lpu))
        return texto
    return None
