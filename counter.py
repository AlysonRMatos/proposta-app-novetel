"""Formatacao do codigo da proposta.

Formato: NOV-{ABREVIACAO_CLIENTE}-{NUMERO}-{MES}{ANO}
Ex: NOV-SHE-0001-0826 (Shopee, proposta 1, agosto/2026)

O numero sequencial em si e controlado pelo banco de dados (db.py),
nao por este modulo.
"""


def montar_codigo(abrev_cliente: str, numero: int, data_proposta) -> str:
    mes_ano = data_proposta.strftime("%m%y")
    return f"NOV-{abrev_cliente}-{numero:04d}-{mes_ano}"
