import os
import tempfile
from datetime import date

import streamlit as st
from docxtpl import DocxTemplate

from lpu_parser import carregar_lpu
from itens_tabela import montar_tabela_itens
from valor_extenso import formatar_moeda_brl, valor_por_extenso, valor_completo
from clientes import obter_abreviacao
from imagens_grid import montar_grid_imagens
from counter import montar_codigo
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "template_proposta.docx")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

st.set_page_config(page_title="Gerador de Propostas - Novetel", layout="wide")


def _senha_configurada():
    try:
        return st.secrets.get("APP_PASSWORD")
    except Exception:
        return None


def _autenticado() -> bool:
    senha_correta = _senha_configurada()
    if not senha_correta:
        return True  # sem senha configurada (uso local) -> nao bloqueia
    if st.session_state.get("autenticado"):
        return True

    st.title("Gerador de Propostas Tecnicas")
    with st.form("login"):
        senha = st.text_input("Senha de acesso", type="password")
        entrar = st.form_submit_button("Entrar")
    if entrar:
        if senha == senha_correta:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    return False


if not _autenticado():
    st.stop()

st.title("Gerador de Propostas Tecnicas")

if not os.path.exists(TEMPLATE_PATH):
    st.error(
        "Template nao encontrado. Rode `python build_template.py` na pasta do projeto "
        "antes de usar o app."
    )
    st.stop()

st.caption(f"Proximo numero sequencial de proposta: **{db.espiar_proximo_numero():04d}**")

with st.expander("Historico de propostas geradas"):
    historico = db.listar_propostas()
    if historico:
        st.dataframe(
            [
                {
                    "Numero": h.numero,
                    "Codigo": h.codigo,
                    "Cliente": h.cliente,
                    "Projeto": h.codigo_projeto,
                    "Local": h.local,
                    "Data": h.data_proposta,
                    "Valor (R$)": h.valor_total,
                    "Criado em": h.criado_em,
                }
                for h in historico
            ],
            use_container_width=True,
        )
        st.divider()
        st.write("**Baixar arquivos de uma proposta anterior**")
        opcoes = {f"{h.codigo} - {h.cliente}": h.numero for h in historico}
        escolha = st.selectbox("Proposta", list(opcoes.keys()))
        if escolha:
            numero_sel = opcoes[escolha]
            col_a, col_b = st.columns(2)
            lpu_arq = db.obter_lpu(numero_sel)
            prop_arq = db.obter_proposta_docx(numero_sel)
            if lpu_arq:
                col_a.download_button(
                    "Baixar LPU original",
                    data=lpu_arq[1],
                    file_name=lpu_arq[0],
                    key=f"lpu_{numero_sel}",
                )
            else:
                col_a.caption("LPU nao disponivel para essa proposta.")
            if prop_arq:
                col_b.download_button(
                    "Baixar proposta gerada",
                    data=prop_arq[1],
                    file_name=prop_arq[0],
                    key=f"prop_{numero_sel}",
                )
            else:
                col_b.caption("Proposta nao disponivel.")
    else:
        st.caption("Nenhuma proposta gerada ainda.")

# ---------- 1. Planilha LPU ----------
st.header("1. Planilha LPU")
lpu_file = st.file_uploader("Selecione a planilha LPU (.xlsx)", type=["xlsx"])

dados_lpu = None
lpu_bytes = None
if lpu_file is not None:
    lpu_bytes = lpu_file.getvalue()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(lpu_bytes)
        tmp_path = tmp.name
    dados_lpu = carregar_lpu(tmp_path, lpu_file.name)
    os.unlink(tmp_path)

    col1, col2, col3 = st.columns(3)
    col1.metric("Codigo do projeto", dados_lpu["codigo_projeto"] or "-")
    col2.metric("Local", dados_lpu["local"] or "-")
    col3.metric("Disciplina", dados_lpu["disciplina"])

    if dados_lpu["valor_total_bdi"] is not None:
        st.metric("Valor total do orcamento (com BDI)", formatar_moeda_brl(dados_lpu["valor_total_bdi"]))
    else:
        st.warning("Nao foi possivel calcular o valor total automaticamente a partir da LPU.")

    st.write(f"**{len(dados_lpu['itens'])} itens** encontrados com quantidade preenchida (serao executados):")
    st.dataframe(
        [
            {
                "Codigo": i["codigo"],
                "Descricao": i["descricao"],
                "Qtd.": i["quantidade"],
                "Unid.": i["unidade"],
            }
            for i in dados_lpu["itens"]
        ],
        use_container_width=True,
        height=250,
    )

    itens_selecionados = []
    with st.expander("Ajustar itens incluidos na proposta (desmarque para excluir)"):
        for idx, item in enumerate(dados_lpu["itens"]):
            incluido = st.checkbox(
                f"{item['codigo']} - {item['descricao']} ({item['quantidade']} {item['unidade']})",
                value=True,
                key=f"item_{idx}",
            )
            if incluido:
                itens_selecionados.append(item)
else:
    itens_selecionados = []
    st.info("Envie a planilha LPU para continuar.")

# ---------- 2. Dados da proposta ----------
st.header("2. Dados da proposta")
col1, col2 = st.columns(2)
with col1:
    cliente = st.text_input("Cliente", placeholder="Ex: Shopee")
    abreviacao_cliente = st.text_input(
        "Abreviação do cliente (usada no código da proposta)",
        value=obter_abreviacao(cliente),
        placeholder="Ex: SHO",
        max_chars=10,
    ).strip().upper()
    escopo_titulo = st.text_input(
        "Titulo do escopo (linha da capa)",
        placeholder="Ex: Escopo instalacoes - JIRA INFRA 1623+2504",
    )
    cidade = st.text_input(
        "Cidade",
        value=(dados_lpu["local"] if dados_lpu else ""),
    )
    endereco = st.text_area(
        "Endereco",
        value=(dados_lpu["endereco"] if dados_lpu else ""),
        height=80,
    )
with col2:
    objeto = st.text_area("Objeto", height=80, placeholder="Descreva o objeto do servico")
    prazo_execucao = st.text_input(
        "Prazo de execucao (preenchido automaticamente pela LPU, editavel se necessario)",
        value=(dados_lpu["prazo_execucao"] if dados_lpu else ""),
        placeholder="Ex: 10 dias",
    )

    valor_sugerido = ""
    if dados_lpu and dados_lpu["valor_total_bdi"] is not None:
        valor_sugerido = valor_completo(dados_lpu["valor_total_bdi"])
    valor_total_extenso = st.text_input(
        "Valor total (preenchido automaticamente pela LPU, editavel se necessario)",
        value=valor_sugerido,
    )

data_proposta = st.date_input("Data da proposta", value=date.today())

# ---------- 3. Documentos disponibilizados ----------
st.header("3. Documentos disponibilizados (prints do projeto)")
imagens_upload = st.file_uploader(
    "Anexe as imagens/prints do projeto",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

# ---------- 4. Observacoes de itens exclusos ----------
st.header("4. Observacoes")
observacoes_exclusao = st.text_area(
    "Itens exclusos desta proposta (o que NAO esta contemplado)",
    height=100,
    placeholder="Ex: Nao esta incluso o fornecimento de...",
)

# ---------- Gerar ----------
st.header("5. Gerar proposta")
gerar = st.button("Gerar Proposta (.docx)", type="primary", disabled=(dados_lpu is None))

if gerar:
    if not cliente:
        st.error("Preencha o campo Cliente.")
        st.stop()
    if not abreviacao_cliente:
        st.error("Preencha a abreviação do cliente.")
        st.stop()

    numero_proposta = db.proximo_numero_atomic()
    codigo_proposta = montar_codigo(abreviacao_cliente, numero_proposta, data_proposta)

    tpl = DocxTemplate(TEMPLATE_PATH)

    # Imagens: monta um grid padronizado com todas as imagens anexadas
    subdoc = tpl.new_subdoc()
    caminhos_temp = []
    if imagens_upload:
        for img in imagens_upload:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(img.name)[1]) as tmp_img:
                tmp_img.write(img.getbuffer())
                caminhos_temp.append(tmp_img.name)
    montar_grid_imagens(subdoc, caminhos_temp)
    for caminho in caminhos_temp:
        os.unlink(caminho)

    tabela_subdoc = tpl.new_subdoc()
    montar_tabela_itens(tabela_subdoc, itens_selecionados)

    context = {
        "codigo_proposta": codigo_proposta,
        "cliente": cliente,
        "codigo_projeto": dados_lpu["codigo_projeto"],
        "local": dados_lpu["local"],
        "disciplina": dados_lpu["disciplina"],
        "escopo_titulo": escopo_titulo,
        "data_proposta": data_proposta.strftime("%d/%m/%Y"),
        "endereco": endereco,
        "cidade": cidade,
        "objeto": objeto,
        "itens_tabela": tabela_subdoc,
        "observacoes_exclusao": observacoes_exclusao or "Nao ha itens exclusos.",
        "prazo_execucao": prazo_execucao,
        "valor_total_extenso": valor_total_extenso,
        "imagens": subdoc,
    }

    tpl.render(context)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    nome_saida = f"{codigo_proposta}_{dados_lpu['codigo_projeto']}_{cliente}.docx".replace(" ", "_")
    caminho_saida = os.path.join(OUTPUT_DIR, nome_saida)
    tpl.save(caminho_saida)
    with open(caminho_saida, "rb") as f:
        proposta_bytes = f.read()

    db.salvar_proposta(
        numero=numero_proposta,
        abreviacao_cliente=abreviacao_cliente,
        cliente=cliente,
        data_proposta=data_proposta,
        codigo_projeto=dados_lpu["codigo_projeto"],
        local=dados_lpu["local"],
        valor_total=dados_lpu["valor_total_bdi"],
        lpu_nome_arquivo=lpu_file.name,
        lpu_arquivo=lpu_bytes,
        proposta_nome_arquivo=nome_saida,
        proposta_arquivo=proposta_bytes,
    )

    st.success(f"Proposta gerada: {codigo_proposta}")
    st.download_button(
        "Baixar proposta (.docx)",
        data=proposta_bytes,
        file_name=nome_saida,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
