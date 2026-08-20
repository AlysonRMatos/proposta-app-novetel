"""
Banco de dados de propostas: guarda o historico (incluindo os arquivos da
LPU enviada e da proposta .docx gerada) e controla o numero sequencial
global de forma atomica (seguro para multiplos usuarios simultaneos).

Usa Postgres quando DATABASE_URL esta configurada (producao/online) e
cai para um arquivo SQLite local quando nao esta (desenvolvimento).
"""
import os
from datetime import datetime, timezone

import streamlit as st
from sqlalchemy import create_engine, text

from counter import montar_codigo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_engine = None
_origem_url = None  # "secrets", "env" ou "sqlite_local" -- para diagnostico


def _obter_database_url() -> str:
    global _origem_url

    try:
        if "DATABASE_URL" in st.secrets:
            valor = st.secrets["DATABASE_URL"]
            if valor and valor.strip():
                _origem_url = "secrets"
                return valor
    except Exception:
        pass

    url = os.environ.get("DATABASE_URL")
    if url and url.strip():
        _origem_url = "env"
        return url

    _origem_url = "sqlite_local"
    db_path = os.path.join(BASE_DIR, "data", "propostas.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return f"sqlite:///{db_path}"


def status_backend() -> dict:
    """Diagnostico: qual banco esta realmente sendo usado."""
    _get_engine()  # garante que _origem_url foi resolvido
    return {
        "origem": _origem_url,
        "postgres": _origem_url in ("secrets", "env"),
    }


def _adicionar_coluna_se_necessario(engine, coluna: str, tipo: str):
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE propostas ADD COLUMN {coluna} {tipo}"))
    except Exception:
        pass  # coluna ja existe


def _criar_tabelas(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS contador (
                    id INTEGER PRIMARY KEY,
                    valor INTEGER NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO contador (id, valor) VALUES (1, 0) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS propostas (
                    numero INTEGER PRIMARY KEY,
                    codigo TEXT NOT NULL UNIQUE,
                    cliente TEXT NOT NULL,
                    abreviacao_cliente TEXT NOT NULL,
                    codigo_projeto TEXT,
                    local TEXT,
                    data_proposta TEXT NOT NULL,
                    valor_total DOUBLE PRECISION,
                    criado_em TEXT NOT NULL
                )
                """
            )
        )

    for coluna, tipo in [
        ("lpu_nome_arquivo", "TEXT"),
        ("lpu_arquivo", "BYTEA"),
        ("proposta_nome_arquivo", "TEXT"),
        ("proposta_arquivo", "BYTEA"),
        ("proposta_pdf_nome_arquivo", "TEXT"),
        ("proposta_pdf_arquivo", "BYTEA"),
    ]:
        _adicionar_coluna_se_necessario(engine, coluna, tipo)


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_obter_database_url())
        _criar_tabelas(_engine)
    return _engine


def espiar_proximo_numero() -> int:
    engine = _get_engine()
    with engine.connect() as conn:
        valor = conn.execute(text("SELECT valor FROM contador WHERE id = 1")).scalar()
        return (valor or 0) + 1


def proximo_numero_atomic() -> int:
    """Incrementa e retorna o numero sequencial global de forma atomica."""
    engine = _get_engine()
    with engine.begin() as conn:
        numero = conn.execute(
            text("UPDATE contador SET valor = valor + 1 WHERE id = 1 RETURNING valor")
        ).scalar()
        return numero


def salvar_proposta(
    numero: int,
    abreviacao_cliente: str,
    cliente: str,
    data_proposta,
    codigo_projeto: str,
    local: str,
    valor_total: float,
    lpu_nome_arquivo: str = None,
    lpu_arquivo: bytes = None,
    proposta_nome_arquivo: str = None,
    proposta_arquivo: bytes = None,
    proposta_pdf_nome_arquivo: str = None,
    proposta_pdf_arquivo: bytes = None,
) -> str:
    """Grava o registro completo da proposta (numero ja reservado
    previamente com proximo_numero_atomic), incluindo os arquivos."""
    codigo = montar_codigo(abreviacao_cliente, numero, data_proposta)
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO propostas (
                    numero, codigo, cliente, abreviacao_cliente,
                    codigo_projeto, local, data_proposta, valor_total, criado_em,
                    lpu_nome_arquivo, lpu_arquivo, proposta_nome_arquivo, proposta_arquivo,
                    proposta_pdf_nome_arquivo, proposta_pdf_arquivo
                ) VALUES (
                    :numero, :codigo, :cliente, :abrev,
                    :codigo_projeto, :local, :data_proposta, :valor_total, :criado_em,
                    :lpu_nome, :lpu_arq, :prop_nome, :prop_arq,
                    :prop_pdf_nome, :prop_pdf_arq
                )
                """
            ),
            {
                "numero": numero,
                "codigo": codigo,
                "cliente": cliente,
                "abrev": abreviacao_cliente,
                "codigo_projeto": codigo_projeto,
                "local": local,
                "data_proposta": data_proposta.strftime("%Y-%m-%d"),
                "valor_total": valor_total,
                "criado_em": datetime.now(timezone.utc).isoformat(),
                "lpu_nome": lpu_nome_arquivo,
                "lpu_arq": lpu_arquivo,
                "prop_nome": proposta_nome_arquivo,
                "prop_arq": proposta_arquivo,
                "prop_pdf_nome": proposta_pdf_nome_arquivo,
                "prop_pdf_arq": proposta_pdf_arquivo,
            },
        )
    return codigo


def listar_propostas(limite: int = 100):
    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT numero, codigo, cliente, codigo_projeto, local,
                       data_proposta, valor_total, criado_em
                FROM propostas
                ORDER BY numero DESC
                LIMIT :lim
                """
            ),
            {"lim": limite},
        ).fetchall()
        return rows


def obter_lpu(numero: int):
    """Retorna (nome_arquivo, bytes) da LPU enviada nessa proposta, ou None."""
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT lpu_nome_arquivo, lpu_arquivo FROM propostas WHERE numero = :n"),
            {"n": numero},
        ).fetchone()
        if row and row[1] is not None:
            return row[0], bytes(row[1])
        return None


def obter_proposta_docx(numero: int):
    """Retorna (nome_arquivo, bytes) do .docx gerado nessa proposta, ou None."""
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT proposta_nome_arquivo, proposta_arquivo FROM propostas WHERE numero = :n"),
            {"n": numero},
        ).fetchone()
        if row and row[1] is not None:
            return row[0], bytes(row[1])
        return None


def obter_proposta_pdf(numero: int):
    """Retorna (nome_arquivo, bytes) do .pdf gerado nessa proposta, ou None."""
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT proposta_pdf_nome_arquivo, proposta_pdf_arquivo FROM propostas WHERE numero = :n"),
            {"n": numero},
        ).fetchone()
        if row and row[1] is not None:
            return row[0], bytes(row[1])
        return None


def resetar_banco(confirmar: bool = False):
    """Apaga todas as propostas e zera o contador.

    Trava de seguranca: se o banco em uso for o Postgres de producao,
    exige confirmar=True explicitamente. Evita zerar dados reais por
    engano durante testes/scripts."""
    status = status_backend()
    if status["postgres"] and not confirmar:
        raise RuntimeError(
            "Recusado: isso apagaria o banco de PRODUCAO (Postgres). "
            "Se e realmente isso que voce quer, chame resetar_banco(confirmar=True)."
        )

    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM propostas"))
        conn.execute(text("UPDATE contador SET valor = 0 WHERE id = 1"))
