---
title: Gerador de Propostas Novetel
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Gerador de Propostas Técnicas — Novetel

App Streamlit que gera propostas técnico-comerciais em `.docx` (e `.pdf`, via
LibreOffice) a partir de uma planilha LPU (`.xlsx`).

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Para gerar PDF localmente é preciso ter o LibreOffice instalado (no servidor
ele vem na imagem Docker).

## Deploy

Produção roda no **Hugging Face Spaces** (SDK Docker): a cada push na branch
`main` o Space reconstrói a imagem a partir do `Dockerfile`.

Segredos necessários no Space (*Settings → Variables and secrets*):

| Chave           | Para que serve                                             |
|-----------------|-----------------------------------------------------------|
| `DATABASE_URL`  | Postgres (Neon) — histórico/contador. Sem ela, cai em SQLite temporário. |
| `APP_PASSWORD`  | Senha de acesso da equipe.                                 |

## Estrutura

- `app.py` — interface Streamlit.
- `db.py` — banco (Postgres em produção, SQLite no dev). Guarda só os dados das propostas, não os arquivos.
- `lpu_parser.py` — leitura da planilha LPU.
- `build_template.py` — gera `templates/template_proposta.docx` a partir do `.docx` original (rodar 1x).
- `itens_tabela.py`, `imagens_grid.py`, `revisao_secao.py` — blocos do documento.
- `docx_to_pdf.py` — conversão `.docx` → `.pdf` (LibreOffice headless).
- `indice_fix.py` — corrige os números de página do Sumário.
