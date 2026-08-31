"""
Banco de dados de propostas: guarda o historico completo (arquivos, fotos e
todos os campos usados para gerar cada proposta) e controla o numero
sequencial global de forma atomica (seguro para multiplos usuarios
simultaneos). Tambem guarda as revisoes de propostas existentes.

Usa Postgres quando DATABASE_URL esta configurada (producao/online) e
cai para um arquivo SQLite local quando nao esta (desenvolvimento).
"""
import os
from datetime import datetime, timezone

import streamlit as st
from sqlalchemy import create_engine, text

from counter import montar_codigo, montar_codigo_revisao

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


def _adicionar_coluna_se_necessario(engine, tabela: str, coluna: str, tipo: str):
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}"))
    except Exception:
        pass  # coluna ja existe


# Campos "de formulario" que precisam ficar salvos para uma revisao futura
# poder puxar tudo de volta. Compartilhado entre propostas e revisoes.
_CAMPOS_FORMULARIO = [
    ("escopo_titulo", "TEXT"),
    ("objeto", "TEXT"),
    ("endereco", "TEXT"),
    ("cidade", "TEXT"),
    ("prazo_execucao", "TEXT"),
    ("observacoes_exclusao", "TEXT"),
]

_CAMPOS_ARQUIVOS = [
    ("lpu_nome_arquivo", "TEXT"),
    ("lpu_arquivo", "BYTEA"),
    ("proposta_nome_arquivo", "TEXT"),
    ("proposta_arquivo", "BYTEA"),
    ("proposta_pdf_nome_arquivo", "TEXT"),
    ("proposta_pdf_arquivo", "BYTEA"),
]


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
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS proposta_imagens (
                    numero INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    nome_arquivo TEXT,
                    arquivo BYTEA,
                    PRIMARY KEY (numero, ordem)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS revisoes (
                    numero_pai INTEGER NOT NULL,
                    numero_revisao INTEGER NOT NULL,
                    codigo TEXT NOT NULL UNIQUE,
                    cliente TEXT NOT NULL,
                    abreviacao_cliente TEXT NOT NULL,
                    codigo_projeto TEXT,
                    local TEXT,
                    data_proposta TEXT NOT NULL,
                    valor_total DOUBLE PRECISION,
                    solicitacao_alteracao TEXT,
                    criado_em TEXT NOT NULL,
                    PRIMARY KEY (numero_pai, numero_revisao)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS revisao_imagens (
                    numero_pai INTEGER NOT NULL,
                    numero_revisao INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    nome_arquivo TEXT,
                    arquivo BYTEA,
                    PRIMARY KEY (numero_pai, numero_revisao, ordem)
                )
                """
            )
        )

    for coluna, tipo in _CAMPOS_ARQUIVOS + _CAMPOS_FORMULARIO:
        _adicionar_coluna_se_necessario(engine, "propostas", coluna, tipo)
    for coluna, tipo in _CAMPOS_ARQUIVOS + _CAMPOS_FORMULARIO:
        _adicionar_coluna_se_necessario(engine, "revisoes", coluna, tipo)
    _adicionar_coluna_se_necessario(engine, "revisoes", "justificativas_itens", "TEXT")


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            _obter_database_url(),
            # A Neon (free tier) suspende o compute apos alguns minutos
            # ocioso. pool_pre_ping testa a conexao antes de usa-la e
            # reconecta automaticamente se estiver morta (em vez de
            # estourar OperationalError); pool_recycle descarta conexoes
            # antigas preventivamente.
            pool_pre_ping=True,
            pool_recycle=180,
        )
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
    escopo_titulo: str = None,
    objeto: str = None,
    endereco: str = None,
    cidade: str = None,
    prazo_execucao: str = None,
    observacoes_exclusao: str = None,
    lpu_nome_arquivo: str = None,
    lpu_arquivo: bytes = None,
    proposta_nome_arquivo: str = None,
    proposta_arquivo: bytes = None,
    proposta_pdf_nome_arquivo: str = None,
    proposta_pdf_arquivo: bytes = None,
) -> str:
    """Grava o registro completo da proposta (numero ja reservado
    previamente com proximo_numero_atomic), incluindo os arquivos e todos
    os campos do formulario (necessarios para uma revisao futura poder
    puxar tudo de volta)."""
    codigo = montar_codigo(abreviacao_cliente, numero, data_proposta)
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO propostas (
                    numero, codigo, cliente, abreviacao_cliente,
                    codigo_projeto, local, data_proposta, valor_total, criado_em,
                    escopo_titulo, objeto, endereco, cidade, prazo_execucao,
                    observacoes_exclusao,
                    lpu_nome_arquivo, lpu_arquivo, proposta_nome_arquivo, proposta_arquivo,
                    proposta_pdf_nome_arquivo, proposta_pdf_arquivo
                ) VALUES (
                    :numero, :codigo, :cliente, :abrev,
                    :codigo_projeto, :local, :data_proposta, :valor_total, :criado_em,
                    :escopo_titulo, :objeto, :endereco, :cidade, :prazo_execucao,
                    :observacoes_exclusao,
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
                "escopo_titulo": escopo_titulo,
                "objeto": objeto,
                "endereco": endereco,
                "cidade": cidade,
                "prazo_execucao": prazo_execucao,
                "observacoes_exclusao": observacoes_exclusao,
                "lpu_nome": lpu_nome_arquivo,
                "lpu_arq": lpu_arquivo,
                "prop_nome": proposta_nome_arquivo,
                "prop_arq": proposta_arquivo,
                "prop_pdf_nome": proposta_pdf_nome_arquivo,
                "prop_pdf_arq": proposta_pdf_arquivo,
            },
        )
    return codigo


def salvar_imagens_proposta(numero: int, imagens: list):
    """imagens: lista de (nome_arquivo, bytes)."""
    if not imagens:
        return
    engine = _get_engine()
    with engine.begin() as conn:
        for ordem, (nome, dados) in enumerate(imagens):
            conn.execute(
                text(
                    "INSERT INTO proposta_imagens (numero, ordem, nome_arquivo, arquivo) "
                    "VALUES (:n, :o, :nome, :dados)"
                ),
                {"n": numero, "o": ordem, "nome": nome, "dados": dados},
            )


def obter_imagens_proposta(numero: int) -> list:
    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT nome_arquivo, arquivo FROM proposta_imagens "
                "WHERE numero = :n ORDER BY ordem"
            ),
            {"n": numero},
        ).fetchall()
        return [(r[0], bytes(r[1])) for r in rows]


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


def obter_proposta_completa(numero: int):
    """Retorna todos os campos de formulario de uma proposta (para uma
    revisao puxar de volta), como um mapeamento (Row do SQLAlchemy)."""
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT numero, codigo, cliente, abreviacao_cliente, codigo_projeto,
                       local, valor_total, escopo_titulo, objeto, endereco, cidade,
                       prazo_execucao
                FROM propostas WHERE numero = :n
                """
            ),
            {"n": numero},
        ).fetchone()
        return row


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


# ---------------------------------------------------------------------
# Revisoes de propostas existentes
# ---------------------------------------------------------------------

def proximo_numero_revisao(numero_pai: int) -> int:
    """Proximo numero de revisao (RV01, RV02, ...) para essa proposta pai."""
    engine = _get_engine()
    with engine.connect() as conn:
        valor = conn.execute(
            text("SELECT COALESCE(MAX(numero_revisao), 0) FROM revisoes WHERE numero_pai = :p"),
            {"p": numero_pai},
        ).scalar()
        return (valor or 0) + 1


def salvar_revisao(
    numero_pai: int,
    numero_revisao: int,
    abreviacao_cliente: str,
    cliente: str,
    data_proposta,
    codigo_projeto: str,
    local: str,
    valor_total: float,
    solicitacao_alteracao: str = None,
    escopo_titulo: str = None,
    objeto: str = None,
    endereco: str = None,
    cidade: str = None,
    prazo_execucao: str = None,
    observacoes_exclusao: str = None,
    lpu_nome_arquivo: str = None,
    lpu_arquivo: bytes = None,
    proposta_nome_arquivo: str = None,
    proposta_arquivo: bytes = None,
    proposta_pdf_nome_arquivo: str = None,
    proposta_pdf_arquivo: bytes = None,
    justificativas_itens: dict = None,
) -> str:
    import json

    codigo = montar_codigo_revisao(abreviacao_cliente, numero_pai, numero_revisao, data_proposta)
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO revisoes (
                    numero_pai, numero_revisao, codigo, cliente, abreviacao_cliente,
                    codigo_projeto, local, data_proposta, valor_total,
                    solicitacao_alteracao, criado_em,
                    escopo_titulo, objeto, endereco, cidade, prazo_execucao,
                    observacoes_exclusao, justificativas_itens,
                    lpu_nome_arquivo, lpu_arquivo, proposta_nome_arquivo, proposta_arquivo,
                    proposta_pdf_nome_arquivo, proposta_pdf_arquivo
                ) VALUES (
                    :numero_pai, :numero_revisao, :codigo, :cliente, :abrev,
                    :codigo_projeto, :local, :data_proposta, :valor_total,
                    :solicitacao, :criado_em,
                    :escopo_titulo, :objeto, :endereco, :cidade, :prazo_execucao,
                    :observacoes_exclusao, :justificativas,
                    :lpu_nome, :lpu_arq, :prop_nome, :prop_arq,
                    :prop_pdf_nome, :prop_pdf_arq
                )
                """
            ),
            {
                "numero_pai": numero_pai,
                "numero_revisao": numero_revisao,
                "codigo": codigo,
                "cliente": cliente,
                "abrev": abreviacao_cliente,
                "codigo_projeto": codigo_projeto,
                "local": local,
                "data_proposta": data_proposta.strftime("%Y-%m-%d"),
                "valor_total": valor_total,
                "solicitacao": solicitacao_alteracao,
                "criado_em": datetime.now(timezone.utc).isoformat(),
                "escopo_titulo": escopo_titulo,
                "objeto": objeto,
                "endereco": endereco,
                "cidade": cidade,
                "prazo_execucao": prazo_execucao,
                "observacoes_exclusao": observacoes_exclusao,
                "justificativas": json.dumps(justificativas_itens or {}, ensure_ascii=False),
                "lpu_nome": lpu_nome_arquivo,
                "lpu_arq": lpu_arquivo,
                "prop_nome": proposta_nome_arquivo,
                "prop_arq": proposta_arquivo,
                "prop_pdf_nome": proposta_pdf_nome_arquivo,
                "prop_pdf_arq": proposta_pdf_arquivo,
            },
        )
    return codigo


def salvar_imagens_revisao(numero_pai: int, numero_revisao: int, imagens: list):
    if not imagens:
        return
    engine = _get_engine()
    with engine.begin() as conn:
        for ordem, (nome, dados) in enumerate(imagens):
            conn.execute(
                text(
                    "INSERT INTO revisao_imagens (numero_pai, numero_revisao, ordem, nome_arquivo, arquivo) "
                    "VALUES (:p, :r, :o, :nome, :dados)"
                ),
                {"p": numero_pai, "r": numero_revisao, "o": ordem, "nome": nome, "dados": dados},
            )


def listar_revisoes(numero_pai: int):
    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT numero_revisao, codigo, cliente, valor_total,
                       solicitacao_alteracao, criado_em
                FROM revisoes WHERE numero_pai = :p
                ORDER BY numero_revisao DESC
                """
            ),
            {"p": numero_pai},
        ).fetchall()
        return rows


def obter_revisao_docx(numero_pai: int, numero_revisao: int):
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT proposta_nome_arquivo, proposta_arquivo FROM revisoes "
                "WHERE numero_pai = :p AND numero_revisao = :r"
            ),
            {"p": numero_pai, "r": numero_revisao},
        ).fetchone()
        if row and row[1] is not None:
            return row[0], bytes(row[1])
        return None


def obter_revisao_pdf(numero_pai: int, numero_revisao: int):
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT proposta_pdf_nome_arquivo, proposta_pdf_arquivo FROM revisoes "
                "WHERE numero_pai = :p AND numero_revisao = :r"
            ),
            {"p": numero_pai, "r": numero_revisao},
        ).fetchone()
        if row and row[1] is not None:
            return row[0], bytes(row[1])
        return None


def resetar_banco(confirmar: bool = False):
    """Apaga todas as propostas/revisoes e zera o contador.

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
        conn.execute(text("DELETE FROM revisao_imagens"))
        conn.execute(text("DELETE FROM revisoes"))
        conn.execute(text("DELETE FROM proposta_imagens"))
        conn.execute(text("DELETE FROM propostas"))
        conn.execute(text("UPDATE contador SET valor = 0 WHERE id = 1"))


def limpar_arquivos_grandes(confirmar: bool = False) -> dict:
    """Remove (poe NULL) a LPU, o .docx e o .pdf ja guardados em TODAS as
    propostas/revisoes existentes, mantendo apenas os dados (endereco,
    preco, etc). Usado para reclamar espaco de registros salvos antes dessa
    mudanca de politica de armazenamento -- os campos de dados nao sao
    tocados, apenas os arquivos binarios.

    Trava de seguranca igual a resetar_banco: exige confirmar=True quando
    o banco em uso for o Postgres de producao."""
    status = status_backend()
    if status["postgres"] and not confirmar:
        raise RuntimeError(
            "Recusado: isso alteraria o banco de PRODUCAO (Postgres). "
            "Se e realmente isso que voce quer, chame "
            "limpar_arquivos_grandes(confirmar=True)."
        )

    engine = _get_engine()
    with engine.begin() as conn:
        r1 = conn.execute(
            text(
                "UPDATE propostas SET lpu_arquivo = NULL, proposta_arquivo = NULL, "
                "proposta_pdf_arquivo = NULL WHERE lpu_arquivo IS NOT NULL "
                "OR proposta_arquivo IS NOT NULL OR proposta_pdf_arquivo IS NOT NULL"
            )
        )
        r2 = conn.execute(
            text(
                "UPDATE revisoes SET lpu_arquivo = NULL, proposta_arquivo = NULL, "
                "proposta_pdf_arquivo = NULL WHERE lpu_arquivo IS NOT NULL "
                "OR proposta_arquivo IS NOT NULL OR proposta_pdf_arquivo IS NOT NULL"
            )
        )
    return {"propostas_limpas": r1.rowcount, "revisoes_limpas": r2.rowcount}
