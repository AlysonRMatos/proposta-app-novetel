"""Formatacao de valores monetarios em Real (BRL): numerico e por extenso."""
from num2words import num2words


def formatar_moeda_brl(valor: float) -> str:
    txt = f"{valor:,.2f}"
    txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {txt}"


def valor_por_extenso(valor: float) -> str:
    extenso = num2words(valor, lang="pt_BR", to="currency")
    extenso = extenso[0].upper() + extenso[1:]
    return extenso


def valor_completo(valor: float) -> str:
    """Ex: R$ 120.253,37 (Cento e vinte mil, duzentos e cinquenta e tres reais e trinta e sete centavos)"""
    return f"{formatar_moeda_brl(valor)} ({valor_por_extenso(valor)})"
