"""SQLite store for an official registry release (staging / active)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS establishments (
    cnpj14 TEXT PRIMARY KEY,
    cnpj_basico TEXT NOT NULL,
    cnpj_ordem TEXT,
    cnpj_dv TEXT,
    matriz_filial TEXT,
    nome_fantasia TEXT,
    situacao_cadastral TEXT,
    data_situacao TEXT,
    motivo_situacao TEXT,
    data_inicio TEXT,
    cnae_principal TEXT,
    cnaes_secundarios TEXT, -- JSON array
    tipo_logradouro TEXT,
    logradouro TEXT,
    numero TEXT,
    complemento TEXT,
    bairro TEXT,
    cep TEXT,
    uf TEXT,
    municipio_code TEXT,
    municipio TEXT,
    ddd1 TEXT,
    telefone1 TEXT,
    email TEXT,
    raw_reject INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS companies (
    cnpj_basico TEXT PRIMARY KEY,
    razao_social TEXT,
    natureza_juridica TEXT,
    qualificacao_responsavel TEXT,
    capital_social REAL,
    porte TEXT,
    ente_federativo TEXT
);

CREATE TABLE IF NOT EXISTS simples (
    cnpj_basico TEXT PRIMARY KEY,
    opcao_simples TEXT,
    data_opcao_simples TEXT,
    data_exclusao_simples TEXT,
    opcao_mei TEXT,
    data_opcao_mei TEXT,
    data_exclusao_mei TEXT
);

CREATE TABLE IF NOT EXISTS domain_municipio (
    code TEXT PRIMARY KEY,
    name TEXT
);

CREATE TABLE IF NOT EXISTS domain_cnae (
    code TEXT PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS domain_natureza (
    code TEXT PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS domain_motivo (
    code TEXT PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS rejects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT,
    reason TEXT,
    raw_line TEXT
);

CREATE INDEX IF NOT EXISTS idx_est_basico ON establishments(cnpj_basico);
CREATE INDEX IF NOT EXISTS idx_est_situacao ON establishments(situacao_cadastral);
CREATE INDEX IF NOT EXISTS idx_est_cnae ON establishments(cnae_principal);
CREATE INDEX IF NOT EXISTS idx_est_uf ON establishments(uf);
"""


def connect_db(path: Path | str) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA_SQL)
    return conn


def set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value) if not isinstance(value, str) else value),
    )


def get_meta(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    raw = row["value"]
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def count_table(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # noqa: S608
    return int(row["n"] if row else 0)


def upsert_establishments(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    n = 0
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """
            INSERT INTO establishments (
                cnpj14, cnpj_basico, cnpj_ordem, cnpj_dv, matriz_filial, nome_fantasia,
                situacao_cadastral, data_situacao, motivo_situacao, data_inicio,
                cnae_principal, cnaes_secundarios, tipo_logradouro, logradouro, numero,
                complemento, bairro, cep, uf, municipio_code, municipio, ddd1, telefone1, email
            ) VALUES (
                :cnpj14, :cnpj_basico, :cnpj_ordem, :cnpj_dv, :matriz_filial, :nome_fantasia,
                :situacao_cadastral, :data_situacao, :motivo_situacao, :data_inicio,
                :cnae_principal, :cnaes_secundarios, :tipo_logradouro, :logradouro, :numero,
                :complemento, :bairro, :cep, :uf, :municipio_code, :municipio, :ddd1, :telefone1, :email
            )
            ON CONFLICT(cnpj14) DO UPDATE SET
                nome_fantasia=excluded.nome_fantasia,
                situacao_cadastral=excluded.situacao_cadastral,
                data_situacao=excluded.data_situacao,
                cnae_principal=excluded.cnae_principal,
                cnaes_secundarios=excluded.cnaes_secundarios,
                uf=excluded.uf,
                municipio=excluded.municipio,
                email=excluded.email,
                telefone1=excluded.telefone1
            """,
            {
                **{k: r.get(k) for k in (
                    "cnpj14", "cnpj_basico", "cnpj_ordem", "cnpj_dv", "matriz_filial",
                    "nome_fantasia", "situacao_cadastral", "data_situacao", "motivo_situacao",
                    "data_inicio", "cnae_principal", "tipo_logradouro", "logradouro", "numero",
                    "complemento", "bairro", "cep", "uf", "municipio_code", "municipio",
                    "ddd1", "telefone1", "email",
                )},
                "cnaes_secundarios": json.dumps(r.get("cnaes_secundarios") or [], ensure_ascii=False),
            },
        )
        n += 1
    return n


def upsert_companies(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    n = 0
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """
            INSERT INTO companies (
                cnpj_basico, razao_social, natureza_juridica, qualificacao_responsavel,
                capital_social, porte, ente_federativo
            ) VALUES (
                :cnpj_basico, :razao_social, :natureza_juridica, :qualificacao_responsavel,
                :capital_social, :porte, :ente_federativo
            )
            ON CONFLICT(cnpj_basico) DO UPDATE SET
                razao_social=excluded.razao_social,
                natureza_juridica=excluded.natureza_juridica,
                capital_social=excluded.capital_social,
                porte=excluded.porte
            """,
            {
                "cnpj_basico": r.get("cnpj_basico"),
                "razao_social": r.get("razao_social"),
                "natureza_juridica": r.get("natureza_juridica"),
                "qualificacao_responsavel": r.get("qualificacao_responsavel"),
                "capital_social": r.get("capital_social"),
                "porte": r.get("porte"),
                "ente_federativo": r.get("ente_federativo"),
            },
        )
        n += 1
    return n


def upsert_simples(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    n = 0
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """
            INSERT INTO simples (
                cnpj_basico, opcao_simples, data_opcao_simples, data_exclusao_simples,
                opcao_mei, data_opcao_mei, data_exclusao_mei
            ) VALUES (
                :cnpj_basico, :opcao_simples, :data_opcao_simples, :data_exclusao_simples,
                :opcao_mei, :data_opcao_mei, :data_exclusao_mei
            )
            ON CONFLICT(cnpj_basico) DO UPDATE SET
                opcao_simples=excluded.opcao_simples,
                opcao_mei=excluded.opcao_mei
            """,
            {
                "cnpj_basico": r.get("cnpj_basico"),
                "opcao_simples": r.get("opcao_simples"),
                "data_opcao_simples": r.get("data_opcao_simples"),
                "data_exclusao_simples": r.get("data_exclusao_simples"),
                "opcao_mei": r.get("opcao_mei"),
                "data_opcao_mei": r.get("data_opcao_mei"),
                "data_exclusao_mei": r.get("data_exclusao_mei"),
            },
        )
        n += 1
    return n


def lookup_row(conn: sqlite3.Connection, cnpj14: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT e.*, c.razao_social, c.natureza_juridica, c.capital_social, c.porte,
               s.opcao_simples, s.opcao_mei
        FROM establishments e
        LEFT JOIN companies c ON c.cnpj_basico = e.cnpj_basico
        LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico
        WHERE e.cnpj14 = ?
        """,
        (cnpj14,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    secs = d.get("cnaes_secundarios")
    if isinstance(secs, str):
        try:
            d["cnaes_secundarios"] = json.loads(secs)
        except json.JSONDecodeError:
            d["cnaes_secundarios"] = []
    return d
