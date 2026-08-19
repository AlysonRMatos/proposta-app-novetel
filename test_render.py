"""Teste rapido: renderiza a proposta com a LPU real e dados fake, sem depender do Streamlit."""
import os
from datetime import date

from docxtpl import DocxTemplate
from lpu_parser import carregar_lpu
from itens_tabela import montar_tabela_itens
from valor_extenso import valor_completo
from counter import montar_codigo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "template_proposta.docx")
LPU_PATH = r"C:\Users\alyso\Downloads\LPU\Template_LPU_civil - Backlog-NOVETEL- FBS-RS3 - Santa Rita-RS-REV.00.xlsx"

dados_lpu = carregar_lpu(LPU_PATH, os.path.basename(LPU_PATH))
print("Codigo projeto:", dados_lpu["codigo_projeto"])
print("Local:", dados_lpu["local"])
print("Disciplina:", dados_lpu["disciplina"])
print("Itens com quantidade > 0:", len(dados_lpu["itens"]))
for it in dados_lpu["itens"][:5]:
    print("  -", it)

from imagens_grid import montar_grid_imagens

IMAGENS_TESTE = [
    r"C:\Users\alyso\AppData\Local\Temp\claude\proposta_extract2\unzipped\word\media\image5.png",
    r"C:\Users\alyso\AppData\Local\Temp\claude\proposta_extract2\unzipped\word\media\image2.png",
    r"C:\Users\alyso\AppData\Local\Temp\claude\proposta_extract2\unzipped\word\media\image3.png",
]

tpl = DocxTemplate(TEMPLATE_PATH)
subdoc = tpl.new_subdoc()
montar_grid_imagens(subdoc, [p for p in IMAGENS_TESTE if os.path.exists(p)])

tabela_subdoc = tpl.new_subdoc()
montar_tabela_itens(tabela_subdoc, dados_lpu["itens"])

context = {
    "codigo_proposta": montar_codigo("SHO", 7, date.today()),
    "cliente": "Cliente Teste",
    "codigo_projeto": dados_lpu["codigo_projeto"],
    "local": dados_lpu["local"],
    "disciplina": dados_lpu["disciplina"],
    "escopo_titulo": "Escopo instalacoes - teste",
    "data_proposta": date.today().strftime("%d/%m/%Y"),
    "endereco": dados_lpu["endereco"],
    "cidade": dados_lpu["local"],
    "objeto": "Objeto de teste",
    "itens_tabela": tabela_subdoc,
    "observacoes_exclusao": "Nenhuma.",
    "prazo_execucao": "10 dias",
    "valor_total_extenso": valor_completo(dados_lpu["valor_total_bdi"]),
    "imagens": subdoc,
}

tpl.render(context)
out_path = os.path.join(BASE_DIR, "output", "teste.docx")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
tpl.save(out_path)
print("Salvo em:", out_path)
