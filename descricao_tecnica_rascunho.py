"""
Monta um RASCUNHO da descricao tecnica (memorial descritivo) a partir dos
itens da LPU. O texto e so um ponto de partida -- o usuario edita tudo na
tela antes de gerar a proposta.

Cada regra e (funcao_de_teste, funcao_de_frase). A primeira regra que casar
com a descricao do item (em minusculo) define a frase. Para estender:
adicione uma tupla nova em REGRAS (a ordem importa -- mais especifico primeiro).
"""
import re

# ------------------------------------------------------------------ helpers

def _tem(*palavras):
    def teste(desc: str) -> bool:
        return any(p in desc for p in palavras)
    return teste


def _dimensao(desc: str) -> str:
    """'eletrocalha 200x100x50' -> '200x100x50'."""
    m = re.search(r"\d{2,4}\s*[xX]\s*\d{1,4}(?:\s*[xX]\s*\d{1,4})?", desc)
    return re.sub(r"\s*", "", m.group(0)).replace("X", "x") if m else ""


def _bitola(desc: str) -> str:
    """'cabo 4 mm', 'cabo 2,5mm2', '10 mm²' -> '4 mm²' etc."""
    m = re.search(r"\d+(?:[.,]\d+)?\s*mm(?:²|2)?", desc)
    if not m:
        return ""
    b = m.group(0).replace(" ", "")
    b = b.replace("mm2", "mm²")
    if "mm²" not in b:
        b = b.replace("mm", "mm²")
    return b


def _amperagem(desc: str) -> str:
    m = re.search(r"\d{1,3}\s*[aA]\b", desc)
    return re.sub(r"\s*", "", m.group(0)).upper() if m else ""


def _com_dim(desc, base_com, base_sem):
    d = _dimensao(desc)
    return base_com.format(dim=d) if d else base_sem


# ------------------------------------------------------------------ regras
# (teste, frase) -- frase recebe a descricao original do item.

REGRAS = [
    (
        _tem("mobiliza", "servicos preliminares", "serviços preliminares", "canteiro"),
        lambda d: "Serviços preliminares executados a partir da mobilização da "
                  "equipe e dos materiais em campo, incluindo instalação do canteiro, "
                  "sinalização e proteções coletivas.",
    ),
    (
        _tem("eletrocalha"),
        lambda d: _com_dim(
            d,
            "Fornecimento e montagem de eletrocalha {dim}, com suportação, emendas, "
            "acessórios e aterramento, incluindo a passagem dos circuitos e o "
            "lançamento do cabeamento.",
            "Fornecimento e montagem de eletrocalha, com suportação, emendas, "
            "acessórios e aterramento, incluindo a passagem dos circuitos e o "
            "lançamento do cabeamento.",
        ),
    ),
    (
        _tem("perfilado"),
        lambda d: _com_dim(
            d,
            "Montagem de perfilado {dim} com suportes, tirantes e acessórios de fixação.",
            "Montagem de perfilado com suportes, tirantes e acessórios de fixação.",
        ),
    ),
    (
        _tem("eletroduto", "conduite", "conduíte"),
        lambda d: _com_dim(
            d,
            "Instalação de eletroduto {dim}, com curvas, luvas, caixas de passagem "
            "e fixação.",
            "Instalação de eletroduto, com curvas, luvas, caixas de passagem e fixação.",
        ),
    ),
    (
        _tem("leito", "bandeja"),
        lambda d: _com_dim(
            d,
            "Montagem de leito para cabos {dim}, com suportação, curvas e acessórios.",
            "Montagem de leito para cabos, com suportação, curvas e acessórios.",
        ),
    ),
    (
        _tem("cabo", "cabeamento", "condutor", "cabos"),
        lambda d: (
            f"Lançamento de cabeamento {_bitola(d)}, com identificação, "
            "conectorização, arremates e testes."
        ) if _bitola(d) else
        "Lançamento de cabeamento, com identificação, conectorização, arremates e testes.",
    ),
    (
        _tem("tomada", "tug", "tue"),
        lambda d: (
            f"Instalação de tomadas {_amperagem(d)}, com montagem de caixas, "
            "espelhos e ligação dos circuitos."
        ) if _amperagem(d) else
        "Instalação de tomadas, com montagem de caixas, espelhos e ligação dos circuitos.",
    ),
    (
        _tem("interruptor"),
        lambda d: "Instalação de interruptores, com montagem de caixas, espelhos e ligação.",
    ),
    (
        _tem("luminaria", "luminária", "iluminacao", "iluminação", "refletor", "lampada", "lâmpada"),
        lambda d: "Fornecimento e instalação de luminárias, com fixação, ligação "
                  "e teste de funcionamento.",
    ),
    (
        _tem("quadro", "qdc", "qdf", "qgbt", "qd "),
        lambda d: "Montagem e instalação de quadro elétrico, com fixação, barramento, "
                  "identificação dos circuitos e conexão dos alimentadores.",
    ),
    (
        _tem("disjuntor", "dps", "idr", " dr ", "protecao", "proteção"),
        lambda d: "Instalação de dispositivos de proteção (disjuntores, DPS e DR) "
                  "nos quadros, com identificação e testes.",
    ),
    (
        _tem("aterramento", "spda", "malha", "haste"),
        lambda d: "Execução do sistema de aterramento, com hastes, cordoalhas e "
                  "conexões exotérmicas, e medição da resistência de aterramento.",
    ),
    (
        _tem("caixa de passagem", "caixa de inspecao", "caixa de inspeção", "caixa de piso"),
        lambda d: "Instalação de caixas de passagem, com preparo da base, "
                  "nivelamento e vedação.",
    ),
    (
        _tem("infraestrutura", "infra "),
        lambda d: "Execução da infraestrutura elétrica (embutida e/ou aparente), "
                  "com eletrodutos, caixas, fixações e arremates.",
    ),
    (
        _tem("demolicao", "demolição", "remocao", "remoção", "retirada", "demolir"),
        lambda d: f"Remoção e retirada de {d.strip().rstrip('.')}, com destinação "
                  "adequada dos resíduos.",
    ),
]


def _frase_item(item: dict) -> str:
    desc = (item.get("descricao") or "").strip()
    d = desc.lower()
    for teste, frase in REGRAS:
        if teste(d):
            return frase(desc)
    return (
        f"{desc}: fornecimento, montagem e instalação conforme projeto executivo "
        "e normas técnicas vigentes (ABNT NBR)."
    )


INTRO = (
    "Os serviços preliminares terão início a partir da mobilização da equipe e "
    "dos materiais em campo. Todos os serviços serão executados conforme projeto "
    "executivo, normas técnicas vigentes (ABNT NBR) e boas práticas construtivas."
)


def montar_rascunho(itens_selecionados: list, dados_lpu: dict | None = None) -> str:
    """Retorna o texto do rascunho: uma linha (paragrafo) por item, com um
    paragrafo de introducao no topo."""
    linhas = [INTRO, ""]
    vistos = set()
    for item in itens_selecionados or []:
        frase = _frase_item(item)
        if frase in vistos:
            continue
        vistos.add(frase)
        codigo = (item.get("codigo") or "").strip()
        linhas.append(f"{codigo} — {frase}" if codigo else frase)
    return "\n".join(linhas).strip()
