"""Gate P0 — aditividade estrutural (AC1) e evidencia de nao-interferencia (AC2).

**Estado de AC2 nesta story: BLOCKED-PENDING-AUTHORIZATION.**

O protocolo de dois bracos exigido pelo AC2 compara ``queue_counts()``, que le
``confenge_target_fit_dirty``. Para a comparacao ser nao-trivial, ``run_pipeline()``
precisa ESCREVER nessa tabela — escrita expressamente proibida ao @dev nesta
missao (lista de tabelas somente-SELECT). Alem disso, o banco de teste esta
vazio: com seed nulo os dois bracos retornariam ``{}`` e o teste passaria sem
provar nada. Ambos os motivos estao registrados na story e no ADR-040.

O que este arquivo entrega, integralmente e sem depender daquela autorizacao:

* **AC1 (P0, bloqueante)** — asserção estatica POR STATEMENT sobre o texto da
  migration 104: nenhum ``ALTER``/``DROP``/``CREATE OR REPLACE`` alcanca objeto
  outbound.
* **Evidencia parcial de AC2** — prova estatica de que nenhum modulo outbound
  importa ou referencia ``confenge_live_intelligence`` (ver tambem
  ``tests/confenge_live_intelligence/test_no_outbound_dml_static.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.ops.apply_migrations import is_executable, split_sql

REPO_ROOT = Path(__file__).resolve().parents[1]

# LI-W2 Task 11 — a 105 e coberta ESTENDENDO este arquivo, nunca criando um
# terceiro. Um arquivo novo seria um SEGUNDO instrumento para a MESMA proposicao
# ("nenhum statement alcanca objeto outbound") — a classe de defeito que a story
# ja rejeita em identidade e em allowlist.
MIGRATIONS = (
    REPO_ROOT / "db" / "migrations" / "104_confenge_live_intelligence_v1.sql",
    REPO_ROOT / "db" / "migrations" / "105_confenge_live_intelligence_company_ref.sql",
)
ROLLBACKS = (
    REPO_ROOT / "db" / "rollback" / "104_confenge_live_intelligence_v1_rollback.sql",
    REPO_ROOT / "db" / "rollback" / "105_confenge_live_intelligence_company_ref_rollback.sql",
)
ALL_SQL_PATHS = (*MIGRATIONS, *ROLLBACKS)
ALL_SQL_IDS = ("migration-104", "migration-105", "rollback-104", "rollback-105")
MIGRATION_IDS = ("migration-104", "migration-105")

# Compatibilidade: modulos externos importam estes nomes por referencia.
MIGRATION = MIGRATIONS[0]
ROLLBACK = ROLLBACKS[0]

# §8.2 do impact-analysis — objetos outbound protegidos.
PROTECTED_OBJECTS = (
    "opportunity_intel",
    "confenge_company_target_fit_current",
    "confenge_company_target_fit_history",
    "confenge_target_fit_dirty",
    "confenge_target_fit_events",
    "pncp_supplier_contracts",
    "canonical_public_snapshots",
    "canonical_snapshot_dossiers",
    "canonical_snapshot_source_watermarks",
    "confenge_company_sector_current",
    "confenge_company_sector_history",
    "v_open_opportunities_canonical",
    "v_contracts_canonical_v2",
    "pncp_raw_bids",
    "sc_public_entities",
)

MUTATING = re.compile(r"\b(ALTER\s+TABLE|ALTER\s+VIEW|DROP\s+TABLE|DROP\s+VIEW|CREATE\s+OR\s+REPLACE)\b", re.IGNORECASE)
DML = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\b", re.IGNORECASE)


def _executable_statements(path: Path) -> list[str]:
    statements = [s for s in split_sql(path.read_text(encoding="utf-8")) if is_executable(s)]
    assert statements, f"{path.name}: nenhum statement executavel — parser ou arquivo quebrado"
    return statements


def _strip_comments(statement: str) -> str:
    body = re.sub(r"--[^\n]*", "", statement)
    return re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)


@pytest.mark.parametrize("path", ALL_SQL_PATHS, ids=ALL_SQL_IDS)
def test_migration_files_exist(path: Path) -> None:
    assert path.is_file(), f"{path.name} ausente"


@pytest.mark.parametrize("path", ALL_SQL_PATHS, ids=ALL_SQL_IDS)
def test_no_mutating_statement_touches_outbound_object(path: Path) -> None:
    """AC1 — asserção POR STATEMENT.

    Por arquivo produziria falso positivo: o corpo de
    ``live_open_opportunities_as_of`` legitimamente NOMEIA ``pncp_raw_bids`` em
    um SELECT, e o arquivo contem ``DROP FUNCTION`` sobre a propria funcao nova.
    """
    for statement in _executable_statements(path):
        body = _strip_comments(statement)
        if not MUTATING.search(body):
            continue
        for obj in PROTECTED_OBJECTS:
            assert not re.search(rf"\b{re.escape(obj)}\b", body), (
                f"{path.name}: statement mutante alcanca objeto outbound {obj!r}\n{body[:300]}"
            )


@pytest.mark.parametrize("path", ALL_SQL_PATHS, ids=ALL_SQL_IDS)
def test_no_dml_over_outbound_object(path: Path) -> None:
    for statement in _executable_statements(path):
        body = _strip_comments(statement)
        if not DML.search(body):
            continue
        for obj in PROTECTED_OBJECTS:
            assert not re.search(rf"\b{re.escape(obj)}\b", body), (
                f"{path.name}: DML alcanca objeto outbound {obj!r}\n{body[:300]}"
            )


@pytest.mark.parametrize("path", MIGRATIONS, ids=MIGRATION_IDS)
def test_no_trigger_over_outbound_object(path: Path) -> None:
    """Nenhum CREATE TRIGGER sobre tabela outbound, em nenhuma circunstancia."""
    for statement in _executable_statements(path):
        body = _strip_comments(statement)
        if "CREATE TRIGGER" not in body.upper():
            continue
        for obj in PROTECTED_OBJECTS:
            assert obj not in body, f"trigger sobre objeto outbound {obj!r}"


@pytest.mark.parametrize("path", MIGRATIONS, ids=MIGRATION_IDS)
def test_migration_does_not_create_dedicated_schema(path: Path) -> None:
    """Decisao 8, §8.4 — schema dedicado foi avaliado e rejeitado nesta wave."""
    for statement in _executable_statements(path):
        assert "CREATE SCHEMA" not in _strip_comments(statement).upper()


def test_outbound_files_absent_from_story_scope() -> None:
    """Marcador ``OUTBOUND_CADENCE_REDUCED=NO`` — nenhuma unit systemd no escopo."""
    deploy = REPO_ROOT / "deploy" / "systemd"
    if not deploy.exists():
        pytest.skip("deploy/systemd inexistente neste checkout")
    # A story nao cria nem altera nenhuma unit; a asserção e de escopo de arquivo
    # e o @qa confere o diff no fechamento.
    assert not list(deploy.glob("*live*intel*")), "unit systemd do motor inbound criada fora de escopo"
