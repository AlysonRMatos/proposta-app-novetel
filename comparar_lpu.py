"""Compara os itens da LPU antiga com os da LPU nova (numa revisao),
identificando o que mudou de quantidade e o que e novo."""


def comparar_itens(itens_antigos: list, itens_novos: list):
    """Retorna (itens_alterados, itens_adicionados).

    itens_alterados: mesmo codigo nas duas LPUs, mas quantidade diferente.
        Cada item: {codigo, descricao, qtd_antiga, qtd_nova, unidade}
    itens_adicionados: codigo que so existe na LPU nova.
        Cada item: {codigo, descricao, quantidade, unidade}
    """
    mapa_antigos = {i["codigo"]: i for i in (itens_antigos or [])}
    alterados = []
    adicionados = []

    for item in itens_novos or []:
        codigo = item.get("codigo")
        antigo = mapa_antigos.get(codigo)
        if antigo is not None:
            try:
                mudou = float(antigo.get("quantidade", 0)) != float(item.get("quantidade", 0))
            except (TypeError, ValueError):
                mudou = antigo.get("quantidade") != item.get("quantidade")
            if mudou:
                alterados.append(
                    {
                        "codigo": codigo,
                        "descricao": item.get("descricao", ""),
                        "qtd_antiga": antigo.get("quantidade"),
                        "qtd_nova": item.get("quantidade"),
                        "unidade": item.get("unidade", ""),
                    }
                )
        else:
            adicionados.append(
                {
                    "codigo": codigo,
                    "descricao": item.get("descricao", ""),
                    "quantidade": item.get("quantidade"),
                    "unidade": item.get("unidade", ""),
                }
            )

    return alterados, adicionados
