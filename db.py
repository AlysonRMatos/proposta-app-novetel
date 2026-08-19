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


def _obter_database_url() -> str:
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass

    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    db_path = os.path.join(BASE_DIR, "data", "propostas.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return f"sqlite:///{db_path}"


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
                    lpu_nome_arquivo, lpu_arquivo, proposta_nome_arquivo, proposta_arquivo
                ) VALUES (
                    :numero, :codigo, :cliente, :abrev,
                    :codigo_projeto, :local, :data_proposta, :valor_total, :criado_em,
                    :lpu_nome, :lpu_arq, :prop_nome, :prop_arq
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


def resetar_banco():
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM propostas"))
        conn.execute(text("UPDATE contador SET valor = 0 WHERE id = 1"))
