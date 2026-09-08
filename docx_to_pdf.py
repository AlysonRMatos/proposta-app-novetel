"""Conversao de .docx para .pdf usando LibreOffice headless.

Funciona tanto localmente (Windows, se o LibreOffice estiver instalado)
quanto no servidor (imagem Docker com libreoffice-writer -- ver Dockerfile).
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CAMINHOS_WINDOWS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


def _localizar_soffice():
    encontrado = shutil.which("soffice") or shutil.which("soffice.exe")
    if encontrado:
        return encontrado
    for caminho in CAMINHOS_WINDOWS:
        if os.path.exists(caminho):
            return caminho
    return None


def conversao_disponivel() -> bool:
    return _localizar_soffice() is not None


def converter_docx_para_pdf_bytes(docx_bytes: bytes) -> bytes:
    """Converte bytes de um .docx para bytes de .pdf. Levanta RuntimeError
    se o LibreOffice nao estiver disponivel ou a conversao falhar."""
    soffice = _localizar_soffice()
    if not soffice:
        raise RuntimeError("LibreOffice (soffice) nao encontrado neste ambiente.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        docx_path = os.path.join(tmp_dir, "proposta.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        # Perfil de usuario proprio e descartavel para o LibreOffice, dentro
        # do tmp_dir. Sem isso ele tenta escrever em ~/.config e falha em
        # containers onde o HOME nao e gravavel (ex: Hugging Face Spaces).
        perfil_lo = (Path(tmp_dir) / "lo_profile").as_uri()

        resultado = subprocess.run(
            [
                soffice,
                "--headless",
                "--norestore",
                "--nolockcheck",
                f"-env:UserInstallation={perfil_lo}",
                "--convert-to",
                "pdf",
                "--outdir",
                tmp_dir,
                docx_path,
            ],
            capture_output=True,
            timeout=120,
        )

        pdf_path = os.path.join(tmp_dir, "proposta.pdf")
        if resultado.returncode != 0 or not os.path.exists(pdf_path):
            raise RuntimeError(
                f"Falha ao converter para PDF: {resultado.stderr.decode(errors='ignore')}"
            )

        with open(pdf_path, "rb") as f:
            return f.read()
