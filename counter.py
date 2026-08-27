"""Formatacao do codigo da proposta.

Formato: NOV-{ABREVIACAO_CLIENTE}-{NUMERO}-{MES}{ANO}
Ex: NOV-SHE-0001-0826 (Shopee, proposta 1, agosto/2026)

Revisoes de uma proposta existente usam:
NOV-{ABREVIACAO_CLIENTE}-{NUMERO_PAI}-RV{NUMERO_REVISAO}-{MES}{ANO}
Ex: NOV-SHE-0016-RV01-0826, NOV-SHE-0016-RV02-0826, ...

Os numeros sequenciais em si sao controlados pelo banco de dados (db.py),
nao por este modulo.
"""


def montar_codigo(abrev_cliente: str, numero: int, data_proposta) -> str:
    mes_ano = data_proposta.strftime("%m%y")
    return f"NOV-{abrev_cliente}-{numero:04d}-{mes_ano}"


def montar_codigo_revisao(abrev_cliente: str, numero_pai: int, numero_revisao: int, data_proposta) -> str:
    mes_ano = data_proposta.strftime("%m%y")
    return f"NOV-{abrev_cliente}-{numero_pai:04d}-RV{numero_revisao:02d}-{mes_ano}"
