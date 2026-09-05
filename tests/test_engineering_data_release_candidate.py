"""Candidate read surface: shipped view, grants, fail-closed #545, adversarial cases.

Drives public.v_recent_engineering_wins and related persist functions — not a
reimplementation. Real Postgres via apply_migrations / LOCAL_DATALAKE_DSN.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.contracts.engineering_class import (
    attach_engineering_class,
    classify_engineering_class,
    stamp_engineering_class_labels,
)
from scripts.crawl.pncp_contract_terms import map_pncp_term
from scripts.crawl.pncp_procurement_results import map_pncp_item_result
from scripts.testing.real_db_guard import canonical_dsn

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads(
    (ROOT / "docs/contracts/commercial-read/v1/commercial_read_v1.json").read_text(encoding="utf-8")
)
SQL_115 = (ROOT / "db/migrations/115_commercial_read_v1.sql").read_text(encoding="utf-8")
SQL_116 = (ROOT / "db/migrations/116_engineering_data_release_candidate.sql").read_text(
    encoding="utf-8"
)
PREFIX = "EDRC-"
CNPJ = "11222333000181"


def test_candidate_sql_has_one_class_authority_and_fail_closed_results() -> None:
    assert "contract_engineering_class" in SQL_116
    assert "ILIKE" not in SQL_116
    assert "NOLOGIN" in SQL_115
    assert "password" not in SQL_115.lower()
    assert "password" not in SQL_116.lower()
    assert "GRANT INSERT" not in SQL_115
    assert "GRANT UPDATE" not in SQL_115
    assert "GRANT INSERT" not in SQL_116
    for forbidden in ("RESULT_PUBLISHED", "ADJUDICATED", "HOMOLOGATED"):
        assert f"THEN '{forbidden}'" not in SQL_116.split("AS trigger_type")[0]
    assert "procurement_result_status" in SQL_116
    assert "COALESCE(result_evt.procurement_result_status, 'UNKNOWN')" in SQL_116
    assert "tipo_contrato_nome" in SQL_116
    assert "categoria_processo_nome" in SQL_116
    assert "regime_execucao_nome" in SQL_116
    assert "decision_maker" not in SQL_116.lower()
    assert "decisor" not in SQL_116.lower()
    for col in CONTRACT["columns"]:
        assert col in SQL_116
    for col in CONTRACT["candidate_additive_columns"]:
        assert col in SQL_116


def test_migration_versions_107_to_116_are_unique() -> None:
    files = sorted((ROOT / "db" / "migrations").glob("1*.sql"))
    versions = [p.name.split("_", 1)[0] for p in files if p.name[:3].isdigit() and int(p.name[:3]) >= 107]
    assert versions == [f"{n:03d}" for n in range(107, 117)], versions


def test_cadastral_contact_view_is_not_decision_maker() -> None:
    sql = (ROOT / "db/migrations/109_engineering_supplier_registry.sql").read_text(encoding="utf-8")
    assert "v_supplier_cadastral_contact" in sql
    assert "Not decision-maker discovery" in sql
    assert "cadastral_email" in sql
    for banned in ("decision_maker", "decisor", "nome_decisor"):
        assert banned not in sql.lower()


def _dsn() -> str:
    return os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()


def _connect():
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)


def _cleanup(cur) -> None:
    cur.execute("DELETE FROM public.contract_terms WHERE contrato_id LIKE %s", (PREFIX + "%",))
    cur.execute(
        "DELETE FROM public.pncp_procurement_results WHERE result_id LIKE %s OR parent_procurement_id LIKE %s",
        (PREFIX + "%", PREFIX + "%"),
    )
    cur.execute(
        "DELETE FROM public.contract_engineering_class WHERE contrato_id LIKE %s",
        (PREFIX + "%",),
    )
    cur.execute(
        "DELETE FROM public.pncp_supplier_contracts WHERE contrato_id LIKE %s",
        (PREFIX + "%",),
    )
    cur.execute("DELETE FROM public.enriched_entities WHERE cnpj LIKE %s", (PREFIX + "%",))
    cur.execute(
        "DELETE FROM public.supplier_registry WHERE cnpj14 LIKE %s OR source = %s",
        (PREFIX + "%", "edrc-test"),
    )


def _upsert(cur, record: dict) -> None:
    cur.execute(
        "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
        (json.dumps([record], default=str),),
    )
    cur.fetchall()
    if record.get("parent_procurement_id"):
        cur.execute(
            "UPDATE public.pncp_supplier_contracts SET parent_procurement_id = %s WHERE contrato_id = %s",
            (record["parent_procurement_id"], record["contrato_id"]),
        )


def _base_contract(suffix: str, objeto: str, **extra: object) -> dict:
    cid = f"{PREFIX}{suffix}"
    rec: dict = {
        "contrato_id": cid,
        "orgao_cnpj": "12345678000199",
        "orgao_nome": extra.pop("orgao_nome", "Prefeitura de Florianopolis"),
        "fornecedor_cnpj": extra.pop("fornecedor_cnpj", CNPJ),
        "fornecedor_nome": extra.pop("fornecedor_nome", "Construtora Exemplo Ltda"),
        "supplier_id_type": "UNKNOWN",
        "supplier_identifier": extra.get("fornecedor_cnpj", CNPJ),
        "objeto_contrato": objeto,
        "valor_total": extra.pop("valor_total", "250000"),
        "data_assinatura": extra.pop("data_assinatura", "2026-08-20"),
        "data_publicacao_fonte": extra.pop("data_publicacao_fonte", "2026-08-21"),
        "data_publicacao": extra.pop("data_publicacao", "2026-08-21"),
        "uf": extra.pop("uf", "SC"),
        "municipio": extra.pop("municipio", "Florianopolis"),
        "source": "pncp",
        "source_id": cid,
        "tipo_contrato_id": extra.pop("tipo_contrato_id", "1"),
        "tipo_contrato_nome": extra.pop("tipo_contrato_nome", "Contrato"),
        "categoria_processo_id": extra.pop("categoria_processo_id", "1"),
        "categoria_processo_nome": extra.pop("categoria_processo_nome", "Obras"),
        "modalidade_id": extra.pop("modalidade_id", "8"),
        "modalidade_nome": extra.pop("modalidade_nome", "Dispensa de licitacao"),
        "regime_execucao_id": extra.pop("regime_execucao_id", None),
        "regime_execucao_nome": extra.pop("regime_execucao_nome", None),
        "srp": extra.pop("srp", False),
        "parent_procurement_id": extra.pop("parent_procurement_id", None),
    }
    rec.update(extra)
    attach_engineering_class(rec)
    return rec


def _stamp(conn, rec: dict) -> None:
    stamped = stamp_engineering_class_labels(conn, [rec])
    assert stamped == 1


def _win(cur, contrato_id: str):
    cur.execute(
        "SELECT * FROM public.v_recent_engineering_wins WHERE contract_id = %s",
        (contrato_id,),
    )
    return cur.fetchone()


@pytest.mark.real_db
@pytest.mark.database
def test_candidate_view_class_dates_lifecycle_identity_clocks_and_adversarial() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.views WHERE table_name = 'v_recent_engineering_wins'"
            )
            if cur.fetchone() is None:
                pytest.fail("v_recent_engineering_wins missing — apply candidate migrations")
            _cleanup(cur)

            projeto = _base_contract(
                "projeto",
                "Elaboracao de projeto executivo de engenharia para escola municipal",
                parent_procurement_id=f"{PREFIX}proc-projeto",
            )
            assert projeto["engineering_class"] == "PROJETO_ENGENHARIA"
            _upsert(cur, projeto)
            _stamp(conn, projeto)

            publicidade = _base_contract(
                "publicidade",
                "Fiscalizacao de campanha de publicidade e propaganda institucional",
                categoria_processo_nome="Compras",
            )
            assert publicidade["engineering_class"] == "NAO_ENGENHARIA"
            _upsert(cur, publicidade)
            _stamp(conn, publicidade)

            fundacao = _base_contract(
                "fundacao",
                "Projeto de pesquisa aplicada em ciencias sociais",
                fornecedor_nome="Fundacao de Amparo a Pesquisa do Estado",
                categoria_processo_nome="Compras",
            )
            assert fundacao["engineering_class"] == "NAO_ENGENHARIA"
            _upsert(cur, fundacao)
            _stamp(conn, fundacao)

            medico = _base_contract(
                "medico",
                "Manutencao de equipamentos medicos e respiradores hospitalares",
                categoria_processo_nome="Compras",
            )
            assert medico["engineering_class"] == "NAO_ENGENHARIA"
            _upsert(cur, medico)
            _stamp(conn, medico)

            integrado = _base_contract(
                "integrado",
                "Construcao de unidade de saude com 12 salas",
                regime_execucao_id="1",
                regime_execucao_nome="Contratacao integrada",
                categoria_processo_nome="Obras",
            )
            assert integrado["engineering_class"] == "OBRA_COM_PROJETO"
            _upsert(cur, integrado)
            _stamp(conn, integrado)

            absurd = _base_contract(
                "absurd",
                "Execucao de obra de pavimentacao asfaltica urbana",
                data_assinatura="8406-05-16",
                data_publicacao_fonte="8406-05-16",
                data_publicacao="8406-05-16",
            )
            _upsert(cur, absurd)
            _stamp(conn, absurd)

            revoked = _base_contract(
                "revoked",
                "Execucao de obra de drenagem urbana",
                data_assinatura="2026-08-25",
                data_publicacao_fonte="2026-08-26",
            )
            _upsert(cur, revoked)
            _stamp(conn, revoked)
            term = map_pncp_term(
                {
                    "numeroControlePNCP": revoked["contrato_id"],
                    "tipoTermoNome": "Revogacao",
                    "numeroTermo": "1",
                    "dataAssinatura": "2026-08-28",
                }
            )
            cur.execute(
                "SELECT action FROM apply_contract_terms(%s::jsonb)",
                (json.dumps([term], default=str),),
            )
            cur.fetchall()

            result_payload = {
                "numeroControlePNCPCompra": f"{PREFIX}proc-projeto",
                "numeroItem": 1,
                "niFornecedor": CNPJ,
                "nomeRazaoSocialFornecedor": "Construtora Exemplo Ltda",
                "valorNegociado": 250000.0,
                "situacao": "Homologado",
                "dataResultado": "2026-08-10",
                "dataPublicacaoPncp": "2026-08-11",
            }
            mapped = map_pncp_item_result(result_payload)
            mapped["result_id"] = f"{PREFIX}res-1"
            mapped["parent_procurement_id"] = f"{PREFIX}proc-projeto"
            cur.execute(
                "SELECT action FROM apply_pncp_procurement_results(%s::jsonb)",
                (json.dumps([mapped], default=str),),
            )
            first_actions = [r["action"] for r in cur.fetchall()]
            cur.execute(
                "SELECT action FROM apply_pncp_procurement_results(%s::jsonb)",
                (json.dumps([mapped], default=str),),
            )
            second_actions = [r["action"] for r in cur.fetchall()]

            win = _win(cur, projeto["contrato_id"])
            assert win is not None
            assert win["engineering_class"] == "PROJETO_ENGENHARIA"
            assert win["trigger_type"] == "PROJETO"
            assert win["trigger_type"] not in {
                "RESULT_PUBLISHED",
                "ADJUDICATED",
                "HOMOLOGATED",
            }
            assert win["tipo_contrato_nome"] == "Contrato"
            assert win["categoria_processo_nome"] == "Obras"
            assert win["procurement_result_status"] == "HOMOLOGATED"
            assert win["lifecycle_status"] == "UNKNOWN"
            assert win["commercial_actionability"] in {
                "HOT",
                "WARM",
                "ACTIVE",
                "LATE",
                "COLD",
            }
            assert win["data_freshness"] is not None or win["first_seen_at"] is not None
            assert win["commercial_age_days"] is not None
            rows = [_win(cur, projeto["contrato_id"]) for _ in range(100)]
            keys = {
                (
                    r["company_cnpj"],
                    r["contract_id"],
                    r["engineering_class"],
                    r["procurement_result_status"],
                )
                for r in rows
            }
            assert len(keys) == 1
            assert rows[0]["contract_id"] == projeto["contrato_id"]

            assert _win(cur, publicidade["contrato_id"]) is None
            assert _win(cur, fundacao["contrato_id"]) is None
            assert _win(cur, medico["contrato_id"]) is None

            integ = _win(cur, integrado["contrato_id"])
            assert integ is not None
            assert integ["engineering_class"] == "OBRA_COM_PROJETO"
            assert integ["trigger_type"] == "OBRA_INTEGRADA"
            assert integ["regime_execucao_nome"] == "Contratacao integrada"
            assert integ["procurement_result_status"] == "UNKNOWN"

            assert _win(cur, absurd["contrato_id"]) is None
            cur.execute(
                "SELECT quality_state, data_assinatura FROM pncp_supplier_contracts WHERE contrato_id = %s",
                (absurd["contrato_id"],),
            )
            q = cur.fetchone()
            assert q["quality_state"] == "QUARANTINED"
            assert q["data_assinatura"] is None
            cur.execute(
                """
                SELECT MAX(data_assinatura) AS mx
                FROM pncp_supplier_contracts
                WHERE contrato_id LIKE %s
                """,
                (PREFIX + "%",),
            )
            mx = cur.fetchone()["mx"]
            assert mx is None or mx.year < 8000

            rev = _win(cur, revoked["contrato_id"])
            assert rev is not None
            assert rev["lifecycle_status"] == "REVOGACAO"
            assert rev["commercial_actionability"] == "NOT_ACTIONABLE"
            assert rev["commercial_actionability"] not in {"HOT", "WARM", "ACTIVE"}

            assert first_actions == ["inserted"]
            assert second_actions == ["updated"]
            cur.execute(
                "SELECT count(*) AS n FROM pncp_procurement_results WHERE result_id = %s",
                (mapped["result_id"],),
            )
            assert cur.fetchone()["n"] == 1

            cur.execute(
                "INSERT INTO supplier_registry (cnpj14, razao_social, source, source_version, source_date) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (cnpj14) DO NOTHING",
                (CNPJ, "Construtora Exemplo Ltda", "edrc-test", "test", "2026-09-05"),
            )
            cur.execute(
                "SELECT has_cadastral_contact, cadastral_email FROM v_supplier_cadastral_contact WHERE cnpj14 = %s",
                (CNPJ,),
            )
            contact = cur.fetchone()
            assert contact is not None
            assert contact["has_cadastral_contact"] is False
            assert contact["cadastral_email"] is None

            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'v_recent_engineering_wins'
                ORDER BY ordinal_position
                """
            )
            cols = [r["column_name"] for r in cur.fetchall()]
            assert cols[: len(CONTRACT["columns"])] == CONTRACT["columns"]
            for col in CONTRACT["candidate_additive_columns"]:
                assert col in cols
            assert "decision_maker" not in cols
            assert "decisor" not in cols

            cur.execute(
                """
                SELECT rolname, rolcanlogin, rolsuper
                FROM pg_roles WHERE rolname = 'confenge_commercial_read_v1'
                """
            )
            role = cur.fetchone()
            assert role is not None
            assert role["rolcanlogin"] is False
            assert role["rolsuper"] is False
            cur.execute(
                """
                SELECT privilege_type
                FROM information_schema.role_table_grants
                WHERE grantee = 'confenge_commercial_read_v1'
                  AND table_name = 'v_recent_engineering_wins'
                """
            )
            privs = {r["privilege_type"] for r in cur.fetchall()}
            assert "SELECT" in privs
            assert "INSERT" not in privs
            assert "UPDATE" not in privs
            assert "DELETE" not in privs

        conn.commit()
    finally:
        try:
            with conn.cursor() as cur:
                _cleanup(cur)
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()
