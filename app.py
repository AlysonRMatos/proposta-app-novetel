import hashlib
import io
import os
import tempfile
from datetime import date

import pandas as pd
import streamlit as st
from docxtpl import DocxTemplate

from lpu_parser import carregar_lpu
from itens_tabela import montar_tabela_itens
from valor_extenso import formatar_moeda_brl, valor_por_extenso, valor_completo
from clientes import obter_abreviacao
from imagens_grid import montar_grid_imagens
from counter import montar_codigo, montar_codigo_revisao
from docx_to_pdf import conversao_disponivel, converter_docx_para_pdf_bytes
from indice_fix import corrigir_indice
from revisao_secao import montar_secao_revisao
from comparar_lpu import comparar_itens
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "template_proposta.docx")

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

if "uploader_version" not in st.session_state:
    st.session_state["uploader_version"] = 0

CAMPOS_LIMPAVEIS = [
    "cliente",
    "abreviacao_cliente",
    "escopo_titulo",
    "cidade",
    "endereco",
    "objeto",
    "prazo_execucao",
    "valor_total_extenso",
    "data_proposta",
    "observacoes_exclusao",
    "_lpu_fingerprint",
    "escolha_revisao",
    "solicitacao_alteracao",
    "_revisao_carregada",
]

col_titulo, col_limpar = st.columns([4, 1])
with col_titulo:
    st.title("Gerador de Propostas Tecnicas")
with col_limpar:
    st.write("")
    if st.button("Limpar todos os campos"):
        for campo in CAMPOS_LIMPAVEIS:
            st.session_state.pop(campo, None)
        st.session_state["uploader_version"] += 1
        st.rerun()

if not os.path.exists(TEMPLATE_PATH):
    st.error(
        "Template nao encontrado. Rode `python build_template.py` na pasta do projeto "
        "antes de usar o app."
    )
    st.stop()

status = db.status_backend()
if status["postgres"]:
    st.caption(f"Banco de dados: Postgres ({status['origem']}) — persistente")
else:
    st.error(
        "ATENCAO: o app nao encontrou DATABASE_URL configurada e esta usando um banco "
        "SQLite local temporario. Os dados vao se perder quando o app reiniciar/dormir. "
        "Configure DATABASE_URL em Settings -> Secrets no Streamlit Cloud."
    )

st.caption(f"Proximo numero sequencial de proposta: **{db.espiar_proximo_numero():04d}**")

historico = db.listar_propostas()

with st.expander("Histórico de propostas geradas"):
    # Consulta leve (sem buscar os arquivos/blobs de cada proposta) para o
    # app continuar rapido pra abrir mesmo com muitas propostas geradas.
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
        # So busca a lista (leve, sem blobs) de revisoes de cada proposta,
        # e so busca os ARQUIVOS de uma revisao quando a proposta realmente
        # tem alguma (subconjunto pequeno) -- mantem o restante do historico
        # rapido mesmo com muitas propostas.
        propostas_com_revisao = [
            (h, db.listar_revisoes(h.numero)) for h in historico
        ]
        propostas_com_revisao = [(h, revs) for h, revs in propostas_com_revisao if revs]

        if propostas_com_revisao:
            st.divider()
            st.write("**Propostas com revisões:**")
            for h, revs in propostas_com_revisao:
                with st.expander(f"🔁 {h.codigo} — {h.cliente} ({len(revs)} revisão(ões))"):
                    for r in revs:
                        st.write(
                            f"RV{r.numero_revisao:02d} — {r.codigo} — "
                            f"{formatar_moeda_brl(r.valor_total) if r.valor_total is not None else '-'} "
                            f"— {r.solicitacao_alteracao or 'sem descrição'}"
                        )
                        col_r1, col_r2 = st.columns(2)
                        rev_docx = db.obter_revisao_docx(h.numero, r.numero_revisao)
                        rev_pdf = db.obter_revisao_pdf(h.numero, r.numero_revisao)
                        if rev_docx:
                            col_r1.download_button(
                                "Baixar revisão (.docx)",
                                data=rev_docx[1],
                                file_name=rev_docx[0],
                                key=f"hist_revdocx_{h.numero}_{r.numero_revisao}",
                            )
                        else:
                            col_r1.caption("Revisão (.docx) nao disponivel.")
                        if rev_pdf:
                            col_r2.download_button(
                                "Baixar revisão (.pdf)",
                                data=rev_pdf[1],
                                file_name=rev_pdf[0],
                                key=f"hist_revpdf_{h.numero}_{r.numero_revisao}",
                            )
                        else:
                            col_r2.caption("Revisão (.pdf) nao disponivel.")
    else:
        st.caption("Nenhuma proposta gerada ainda.")

st.subheader("Baixar proposta anterior")
if historico:
    opcoes = {f"{h.codigo} - {h.cliente}": h.numero for h in historico}
    escolha = st.selectbox("Proposta", list(opcoes.keys()), key="escolha_download_historico")
    if escolha:
        numero_sel = opcoes[escolha]
        col_a, col_b, col_c = st.columns(3)
        lpu_arq = db.obter_lpu(numero_sel)
        prop_arq = db.obter_proposta_docx(numero_sel)
        prop_pdf_arq = db.obter_proposta_pdf(numero_sel)
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
                "Baixar proposta (.docx)",
                data=prop_arq[1],
                file_name=prop_arq[0],
                key=f"prop_{numero_sel}",
            )
        else:
            col_b.caption("Proposta (.docx) nao disponivel.")
        if prop_pdf_arq:
            col_c.download_button(
                "Baixar proposta (.pdf)",
                data=prop_pdf_arq[1],
                file_name=prop_pdf_arq[0],
                key=f"proppdf_{numero_sel}",
            )
        else:
            col_c.caption("Proposta (.pdf) nao disponivel.")

        if lpu_arq and st.checkbox("Visualizar itens da LPU", key=f"ver_lpu_{numero_sel}"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_hist:
                tmp_hist.write(lpu_arq[1])
                tmp_hist_path = tmp_hist.name
            dados_lpu_hist = carregar_lpu(tmp_hist_path, lpu_arq[0])
            os.unlink(tmp_hist_path)

            col_h1, col_h2, col_h3 = st.columns(3)
            col_h1.metric("Codigo do projeto", dados_lpu_hist["codigo_projeto"] or "-")
            col_h2.metric("Local", dados_lpu_hist["local"] or "-")
            col_h3.metric("Disciplina", dados_lpu_hist["disciplina"])
            st.dataframe(
                [
                    {
                        "Codigo": i["codigo"],
                        "Descricao": i["descricao"],
                        "Qtd.": i["quantidade"],
                        "Unid.": i["unidade"],
                    }
                    for i in dados_lpu_hist["itens"]
                ],
                use_container_width=True,
                height=250,
            )

        # Revisoes: tambem so busca a lista leve; os arquivos da revisao so
        # sao buscados depois que uma revisao especifica e selecionada.
        revisoes_da_proposta = db.listar_revisoes(numero_sel)
        if revisoes_da_proposta:
            opcoes_rev = {
                f"RV{r.numero_revisao:02d} - {r.solicitacao_alteracao or 'sem descrição'}": r.numero_revisao
                for r in revisoes_da_proposta
            }
            escolha_rev = st.selectbox(
                f"Revisões de {escolha} ({len(revisoes_da_proposta)})",
                list(opcoes_rev.keys()),
                key=f"escolha_rev_{numero_sel}",
            )
            if escolha_rev:
                numero_rev_sel = opcoes_rev[escolha_rev]
                col_r1, col_r2 = st.columns(2)
                rev_docx = db.obter_revisao_docx(numero_sel, numero_rev_sel)
                rev_pdf = db.obter_revisao_pdf(numero_sel, numero_rev_sel)
                if rev_docx:
                    col_r1.download_button(
                        "Baixar revisão (.docx)",
                        data=rev_docx[1],
                        file_name=rev_docx[0],
                        key=f"revdocx_{numero_sel}_{numero_rev_sel}",
                    )
                else:
                    col_r1.caption("Revisão (.docx) nao disponivel.")
                if rev_pdf:
                    col_r2.download_button(
                        "Baixar revisão (.pdf)",
                        data=rev_pdf[1],
                        file_name=rev_pdf[0],
                        key=f"revpdf_{numero_sel}_{numero_rev_sel}",
                    )
                else:
                    col_r2.caption("Revisão (.pdf) nao disponivel.")

# ---------- 1. Planilha LPU ----------
st.header("1. Planilha LPU")
lpu_file = st.file_uploader(
    "Selecione a planilha LPU (.xlsx)",
    type=["xlsx"],
    key=f"lpu_uploader_{st.session_state.uploader_version}",
)

dados_lpu = None
lpu_bytes = None
if lpu_file is not None:
    lpu_bytes = lpu_file.getvalue()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(lpu_bytes)
        tmp_path = tmp.name
    dados_lpu = carregar_lpu(tmp_path, lpu_file.name)
    os.unlink(tmp_path)

    # Sempre que uma LPU NOVA (ou diferente) e carregada, atualiza os campos
    # dependentes dela. Sem isso, os widgets "travam" no primeiro valor
    # carregado e ignoram uploads seguintes (comportamento padrao do
    # Streamlit quando o widget ja tem uma key com valor em session_state).
    fingerprint = hashlib.md5(lpu_bytes).hexdigest()
    if st.session_state.get("_lpu_fingerprint") != fingerprint:
        st.session_state["_lpu_fingerprint"] = fingerprint
        st.session_state["cidade"] = dados_lpu["local"] or ""
        st.session_state["endereco"] = dados_lpu["endereco"] or ""
        st.session_state["prazo_execucao"] = dados_lpu["prazo_execucao"] or ""
        st.session_state["valor_total_extenso"] = (
            valor_completo(dados_lpu["valor_total_bdi"])
            if dados_lpu["valor_total_bdi"] is not None
            else ""
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Codigo do projeto", dados_lpu["codigo_projeto"] or "-")
    col2.metric("Local", dados_lpu["local"] or "-")
    col3.metric("Disciplina", dados_lpu["disciplina"])

    if dados_lpu["valor_total_bdi"] is not None:
        st.metric("Valor total do orcamento (com BDI)", formatar_moeda_brl(dados_lpu["valor_total_bdi"]))
    else:
        st.warning("Nao foi possivel calcular o valor total automaticamente a partir da LPU.")

    itens_selecionados = []
    if dados_lpu["itens"]:
        st.write(
            f"**{len(dados_lpu['itens'])} itens** encontrados com quantidade preenchida "
            "(serao executados). Voce pode editar descricao/quantidade/unidade ou desmarcar "
            "'Incluir' para excluir um item da proposta:"
        )
        df_itens = pd.DataFrame(
            [
                {
                    "Incluir": True,
                    "Codigo": item["codigo"],
                    "Descricao": item["descricao"],
                    "Qtd.": item["quantidade"],
                    "Unid.": item["unidade"],
                }
                for item in dados_lpu["itens"]
            ]
        )
        df_editado = st.data_editor(
            df_itens,
            use_container_width=True,
            height=300,
            num_rows="fixed",
            disabled=["Codigo"],
            key=f"itens_editor_{st.session_state.uploader_version}",
            column_config={"Incluir": st.column_config.CheckboxColumn("Incluir")},
        )
        itens_selecionados = [
            {
                "codigo": row["Codigo"],
                "descricao": row["Descricao"],
                "quantidade": row["Qtd."],
                "unidade": row["Unid."],
            }
            for _, row in df_editado.iterrows()
            if row["Incluir"]
        ]
    else:
        st.warning("Nenhum item com quantidade preenchida foi encontrado na LPU.")
else:
    itens_selecionados = []
    st.info("Envie a planilha LPU para continuar.")


# ---------- REVISÃO de proposta existente ----------
st.header("REVISÃO")
propostas_existentes = db.listar_propostas()
numero_pai_revisao = None
codigo_pai_revisao = None
solicitacao_alteracao = ""
itens_antigos_revisao = []
imagens_antigas_revisao = []
itens_alterados_revisao = []
itens_adicionados_revisao = []
justificativas_itens = {}

with st.expander("Revisar uma proposta existente (opcional)"):
    opcoes_revisao = ["Nenhuma (proposta nova)"] + [
        f"{h.codigo} - {h.cliente}" for h in propostas_existentes
    ]
    escolha_revisao = st.selectbox(
        "Selecione a proposta original para revisar",
        opcoes_revisao,
        key="escolha_revisao",
    )

    # Mesmo padrao ja comprovado usado para a LPU: detecta mudanca de
    # selecao e forca um rerun, em vez de depender de on_change (que se
    # mostrou pouco confiavel para atualizar outros widgets neste caso).
    if st.session_state.get("_revisao_carregada") != escolha_revisao:
        st.session_state["_revisao_carregada"] = escolha_revisao
        if escolha_revisao and not escolha_revisao.startswith("Nenhuma"):
            for h in propostas_existentes:
                if f"{h.codigo} - {h.cliente}" == escolha_revisao:
                    dados_antigos = db.obter_proposta_completa(h.numero)
                    if dados_antigos:
                        st.session_state["cliente"] = dados_antigos.cliente
                        st.session_state["abreviacao_cliente"] = dados_antigos.abreviacao_cliente
                        st.session_state["escopo_titulo"] = dados_antigos.escopo_titulo or ""
                        st.session_state["objeto"] = dados_antigos.objeto or ""
                        st.session_state["endereco"] = dados_antigos.endereco or ""
                        st.session_state["cidade"] = dados_antigos.cidade or ""
                    break
        st.rerun()

    if escolha_revisao and not escolha_revisao.startswith("Nenhuma"):
        for h in propostas_existentes:
            if f"{h.codigo} - {h.cliente}" == escolha_revisao:
                numero_pai_revisao = h.numero
                codigo_pai_revisao = h.codigo
                break

    if numero_pai_revisao is not None:
        proximo_numero_revisao_preview = db.proximo_numero_revisao(numero_pai_revisao)
        st.info(
            f"Cliente, escopo, objeto, endereço, cidade e fotos de **{codigo_pai_revisao}** "
            f"já foram puxados abaixo. Esta proposta será registrada como revisão "
            f"**RV{proximo_numero_revisao_preview:02d}** de **{codigo_pai_revisao}**."
        )
        solicitacao_alteracao = st.text_area(
            "O que foi solicitado alterar nesta revisão? (fica registrado no documento e no banco)",
            key="solicitacao_alteracao",
            height=80,
        )

        try:
            lpu_antiga = db.obter_lpu(numero_pai_revisao)
        except Exception as e:
            lpu_antiga = None
            st.warning(f"Não foi possível recuperar a LPU da proposta original: {e}")

        if lpu_antiga:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_old:
                    tmp_old.write(lpu_antiga[1])
                    tmp_old_path = tmp_old.name
                dados_lpu_antiga = carregar_lpu(tmp_old_path, lpu_antiga[0])
                os.unlink(tmp_old_path)
                itens_antigos_revisao = dados_lpu_antiga["itens"]
                st.caption(
                    f"LPU anterior ({lpu_antiga[0]}): {len(itens_antigos_revisao)} itens — "
                    "vão aparecer como referência na seção 'Revisão' do documento."
                )
            except Exception as e:
                itens_antigos_revisao = []
                st.warning(
                    f"Não foi possível ler os itens da LPU anterior como referência "
                    f"(o restante dos dados foi puxado normalmente): {e}"
                )
        else:
            st.caption("Não há LPU salva na proposta original para usar como referência.")

        try:
            imagens_antigas_revisao = db.obter_imagens_proposta(numero_pai_revisao)
        except Exception as e:
            imagens_antigas_revisao = []
            st.warning(f"Não foi possível recuperar as fotos da proposta original: {e}")

        if imagens_antigas_revisao:
            st.caption(
                f"{len(imagens_antigas_revisao)} foto(s) da proposta anterior serão "
                "reaproveitadas (além de qualquer foto nova que você anexar abaixo)."
            )

        # Compara a LPU antiga (referencia) com a LPU nova ja carregada na
        # secao 1, e pede o motivo de cada quantidade alterada ou item novo.
        itens_alterados_revisao, itens_adicionados_revisao = comparar_itens(
            itens_antigos_revisao, itens_selecionados
        )
        if itens_alterados_revisao or itens_adicionados_revisao:
            st.write(
                "**A LPU nova tem itens com quantidade diferente ou itens que não "
                "existiam na LPU anterior. Diga o motivo de cada um (vai para o "
                "documento e para o banco):**"
            )
        for item in itens_alterados_revisao:
            justificativas_itens[item["codigo"]] = st.text_input(
                f"{item['codigo']} - {item['descricao']}: "
                f"{item['qtd_antiga']} → {item['qtd_nova']} {item['unidade']} "
                "— motivo da alteração",
                key=f"motivo_{item['codigo']}",
            )
        for item in itens_adicionados_revisao:
            justificativas_itens[item["codigo"]] = st.text_input(
                f"NOVO: {item['codigo']} - {item['descricao']} "
                f"({item['quantidade']} {item['unidade']}) — motivo da inclusão",
                key=f"motivo_novo_{item['codigo']}",
            )

# ---------- 2. Dados da proposta ----------
st.header("2. Dados da proposta")
col1, col2 = st.columns(2)
def _atualizar_abreviacao_sugerida():
    st.session_state["abreviacao_cliente"] = obter_abreviacao(st.session_state.get("cliente", ""))


with col1:
    cliente = st.text_input(
        "Cliente",
        placeholder="Ex: Shopee",
        key="cliente",
        on_change=_atualizar_abreviacao_sugerida,
    )
    abreviacao_cliente = st.text_input(
        "Abreviação do cliente (usada no código da proposta)",
        placeholder="Ex: SHO",
        max_chars=10,
        key="abreviacao_cliente",
    ).strip().upper()
    escopo_titulo = st.text_input(
        "Titulo do escopo (linha da capa)",
        placeholder="Ex: Escopo instalacoes - JIRA INFRA 1623+2504",
        key="escopo_titulo",
    )
    cidade = st.text_input("Cidade", key="cidade")
    endereco = st.text_area("Endereco", height=80, key="endereco")
with col2:
    objeto = st.text_area(
        "Objeto", height=80, placeholder="Descreva o objeto do servico", key="objeto"
    )
    prazo_execucao = st.text_input(
        "Prazo de execucao (preenchido automaticamente pela LPU, editavel se necessario)",
        placeholder="Ex: 10 dias",
        key="prazo_execucao",
    )
    valor_total_extenso = st.text_input(
        "Valor total (preenchido automaticamente pela LPU, editavel se necessario)",
        key="valor_total_extenso",
    )

data_proposta = st.date_input("Data da proposta", value=date.today(), key="data_proposta")

# ---------- 3. Documentos disponibilizados ----------
st.header("3. Documentos disponibilizados (prints do projeto)")
imagens_upload = st.file_uploader(
    "Anexe as imagens/prints do projeto",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key=f"imagens_uploader_{st.session_state.uploader_version}",
)

# ---------- 4. Observacoes de itens exclusos ----------
st.header("4. Observacoes")
observacoes_exclusao = st.text_area(
    "Itens exclusos desta proposta (o que NAO esta contemplado)",
    height=100,
    placeholder="Ex: Nao esta incluso o fornecimento de...",
    key="observacoes_exclusao",
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

    revisao_ativa = numero_pai_revisao is not None

    if revisao_ativa:
        numero_revisao_atual = db.proximo_numero_revisao(numero_pai_revisao)
        codigo_proposta = montar_codigo_revisao(
            abreviacao_cliente, numero_pai_revisao, numero_revisao_atual, data_proposta
        )
    else:
        numero_proposta = db.proximo_numero_atomic()
        codigo_proposta = montar_codigo(abreviacao_cliente, numero_proposta, data_proposta)

    tpl = DocxTemplate(TEMPLATE_PATH)

    # Imagens: fotos da proposta anterior (se for revisao) + as novas anexadas,
    # em um unico grid padronizado. Tambem guarda (nome, bytes) de tudo para
    # salvar no banco.
    imagens_para_salvar = []
    caminhos_temp = []
    for nome_antiga, bytes_antiga in imagens_antigas_revisao:
        sufixo = os.path.splitext(nome_antiga)[1] or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp_img:
            tmp_img.write(bytes_antiga)
            caminhos_temp.append(tmp_img.name)
        imagens_para_salvar.append((nome_antiga, bytes_antiga))
    if imagens_upload:
        for img in imagens_upload:
            dados_img = bytes(img.getbuffer())
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(img.name)[1]) as tmp_img:
                tmp_img.write(dados_img)
                caminhos_temp.append(tmp_img.name)
            imagens_para_salvar.append((img.name, dados_img))

    subdoc = tpl.new_subdoc()
    montar_grid_imagens(subdoc, caminhos_temp)
    for caminho in caminhos_temp:
        os.unlink(caminho)

    tabela_subdoc = tpl.new_subdoc()
    montar_tabela_itens(tabela_subdoc, itens_selecionados)

    secao_revisao_subdoc = tpl.new_subdoc()
    montar_secao_revisao(
        secao_revisao_subdoc,
        ativa=revisao_ativa,
        codigo_pai=codigo_pai_revisao,
        numero_revisao=numero_revisao_atual if revisao_ativa else None,
        solicitacao_alteracao=solicitacao_alteracao,
        itens_antigos=itens_antigos_revisao,
        itens_novos=itens_selecionados,
        itens_alterados=itens_alterados_revisao,
        itens_adicionados=itens_adicionados_revisao,
        justificativas_itens=justificativas_itens,
    )

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
        "secao_revisao": secao_revisao_subdoc,
    }

    tpl.render(context)

    nome_saida = f"{codigo_proposta}_{dados_lpu['codigo_projeto']}_{cliente}.docx".replace(" ", "_")
    buffer_docx = io.BytesIO()
    tpl.save(buffer_docx)
    proposta_bytes = buffer_docx.getvalue()

    nome_saida_pdf = None
    proposta_pdf_bytes = None
    if conversao_disponivel():
        try:
            # 1a passada: só para descobrir em qual pagina cada secao caiu
            pdf_rascunho = converter_docx_para_pdf_bytes(proposta_bytes)
            # corrige os numeros do indice (cache de campo PAGEREF) com as
            # paginas reais descobertas na 1a passada
            proposta_bytes = corrigir_indice(proposta_bytes, pdf_rascunho)
            # 2a passada: gera o PDF final ja com o indice correto
            proposta_pdf_bytes = converter_docx_para_pdf_bytes(proposta_bytes)
            nome_saida_pdf = nome_saida.replace(".docx", ".pdf")
        except Exception as e:
            st.warning(f"Nao foi possivel gerar o PDF automaticamente: {e}")
    else:
        st.info("Conversor de PDF nao disponivel neste ambiente; apenas o .docx foi gerado.")

    campos_comuns = dict(
        abreviacao_cliente=abreviacao_cliente,
        cliente=cliente,
        data_proposta=data_proposta,
        codigo_projeto=dados_lpu["codigo_projeto"],
        local=dados_lpu["local"],
        valor_total=dados_lpu["valor_total_bdi"],
        escopo_titulo=escopo_titulo,
        objeto=objeto,
        endereco=endereco,
        cidade=cidade,
        prazo_execucao=prazo_execucao,
        observacoes_exclusao=observacoes_exclusao,
        lpu_nome_arquivo=lpu_file.name,
        lpu_arquivo=lpu_bytes,
        proposta_nome_arquivo=nome_saida,
        proposta_arquivo=proposta_bytes,
        proposta_pdf_nome_arquivo=nome_saida_pdf,
        proposta_pdf_arquivo=proposta_pdf_bytes,
    )

    if revisao_ativa:
        db.salvar_revisao(
            numero_pai=numero_pai_revisao,
            numero_revisao=numero_revisao_atual,
            solicitacao_alteracao=solicitacao_alteracao,
            justificativas_itens=justificativas_itens,
            **campos_comuns,
        )
        db.salvar_imagens_revisao(numero_pai_revisao, numero_revisao_atual, imagens_para_salvar)
    else:
        db.salvar_proposta(numero=numero_proposta, **campos_comuns)
        db.salvar_imagens_proposta(numero_proposta, imagens_para_salvar)

    st.success(f"Proposta gerada: {codigo_proposta}")
    col_docx, col_pdf = st.columns(2)
    col_docx.download_button(
        "Baixar proposta (.docx)",
        data=proposta_bytes,
        file_name=nome_saida,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    if proposta_pdf_bytes:
        col_pdf.download_button(
            "Baixar proposta (.pdf)",
            data=proposta_pdf_bytes,
            file_name=nome_saida_pdf,
            mime="application/pdf",
        )
