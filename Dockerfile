# Gerador de Propostas Novetel — imagem com LibreOffice para gerar o PDF no servidor.
FROM python:3.11-slim

# LibreOffice Writer faz a conversao .docx -> .pdf. As fontes cobrem as
# usadas no template (Arial/Calibri/Cambria via equivalentes metricos).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-liberation \
        fonts-dejavu \
        fonts-crosextra-carlito \
        fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HOME gravavel: LibreOffice e Streamlit criam config na 1a execucao.
# Funciona rodando como root ou como uid nao-root (Hugging Face Spaces).
RUN mkdir -p /var/apphome && chmod 777 /var/apphome
ENV HOME=/var/apphome

EXPOSE 7860

CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]
