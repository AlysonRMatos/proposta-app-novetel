"""Abreviacoes conhecidas de clientes, usadas no codigo da proposta."""

ABREVIACOES_CLIENTES = {
    "shopee": "SHE",
    "mercado livre": "MELI",
    "meli": "MELI",
}


def obter_abreviacao(nome_cliente: str) -> str:
    if not nome_cliente:
        return ""
    return ABREVIACOES_CLIENTES.get(nome_cliente.strip().lower(), "")
