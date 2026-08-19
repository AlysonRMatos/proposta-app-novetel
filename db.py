"""
Banco de dados de propostas: guarda o historico e controla o numero
sequencial global de forma atomica (seguro para multiplos usuarios
simultaneos).

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


def registrar_proposta(
    abreviacao_cliente: str,
    cliente: str,
    data_proposta,
    codigo_projeto: str,
    local: str,
    valor_total: float,
) -> tuple[int, str]:
    """Incrementa o contador global e grava a proposta em uma unica
    transacao atomica (segura mesmo com varios usuarios gerando ao
    mesmo tempo)."""
    engine = _get_engine()
    with engine.begin() as conn:
        numero = conn.execute(
            text("UPDATE contador SET valor = valor + 1 WHERE id = 1 RETURNING valor")
        ).scalar()
        codigo = montar_codigo(abreviacao_cliente, numero, data_proposta)
        conn.execute(
            text(
                """
                INSERT INTO propostas (
                    numero, codigo, cliente, abreviacao_cliente,
                    codigo_projeto, local, data_proposta, valor_total, criado_em
                ) VALUES (
                    :numero, :codigo, :cliente, :abrev,
                    :codigo_projeto, :local, :data_proposta, :valor_total, :criado_em
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
            },
        )
    return numero, codigo


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


def resetar_banco():
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM propostas"))
        conn.execute(text("UPDATE contador SET valor = 0 WHERE id = 1"))
