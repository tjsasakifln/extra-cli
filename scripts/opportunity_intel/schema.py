"""PostgreSQL-only schema validation and reproducible fingerprinting."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from typing import Any

import psycopg2

REQUIRED_COLUMNS: dict[str, set[str]] = {
    "coverage_evidence": {
        "canonical_entity_key",
        "applicability",
        "scope_key",
        "checked_at",
        "pages_expected",
        "pages_processed",
        "records_fetched",
        "open_records",
        "freshness_status",
        "evidence_metadata",
    },
    "opportunity_runs": {
        "external_run_id",
        "source_strategy",
        "period_start",
        "period_end",
        "records_expected",
        "scope_complete",
        "completion_reason",
        "error_code",
    },
    "opportunity_intel": {
        "source",
        "numero_controle_pncp",
        "orgao_cnpj",
        "objeto",
        "status_canonico",
        "data_encerramento",
        "last_seen_at",
    },
    "sc_public_entities": {"id", "cnpj_8", "is_active"},
}


@dataclass(frozen=True)
class GitIdentity:
    branch: str
    sha: str


def connect_postgres(dsn: str) -> Any:
    """Connect fail-closed; no SQLite or implicit backend fallback."""
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise ValueError("QW-01 requires a PostgreSQL DSN; SQLite is not a readiness backend")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def validate_qw01_schema(conn: Any) -> dict[str, Any]:
    """Inspect information_schema before any operational SQL."""
    with conn.cursor() as cursor:
        cursor.execute("SELECT version()")
        postgres_version = str(cursor.fetchone()[0])
        cursor.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (list(REQUIRED_COLUMNS),),
        )
        present: dict[str, set[str]] = {table: set() for table in REQUIRED_COLUMNS}
        for table_name, column_name in cursor.fetchall():
            present[str(table_name)].add(str(column_name))
        missing = {
            table: sorted(required - present.get(table, set()))
            for table, required in REQUIRED_COLUMNS.items()
            if required - present.get(table, set())
        }
        cursor.execute(
            "SELECT to_regprocedure('upsert_qw01_pncp_opportunities(jsonb)') IS NOT NULL"
        )
        function_present = bool(cursor.fetchone()[0])
    if missing or not function_present:
        details = {"missing_columns": missing, "upsert_function_present": function_present}
        raise RuntimeError(
            "QW-01 schema migration 029 is not fully applied: "
            + json.dumps(details, ensure_ascii=False, sort_keys=True)
        )
    return {
        "backend": "postgresql",
        "postgres_version": postgres_version,
        "required_tables": sorted(REQUIRED_COLUMNS),
        "migration_029_ready": True,
    }


def schema_fingerprint(conn: Any) -> str:
    """Hash columns, constraints, and indexes in a deterministic order."""
    payload: dict[str, Any] = {}
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name, ordinal_position, column_name, data_type, udt_name,
                   is_nullable, COALESCE(column_default, '')
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        payload["columns"] = cursor.fetchall()
        cursor.execute(
            """
            SELECT conrelid::regclass::text, conname, contype,
                   pg_get_constraintdef(oid, true)
            FROM pg_constraint
            WHERE connamespace = 'public'::regnamespace
            ORDER BY conrelid::regclass::text, conname
            """
        )
        payload["constraints"] = cursor.fetchall()
        cursor.execute(
            """
            SELECT tablename, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname
            """
        )
        payload["indexes"] = cursor.fetchall()
    encoded = json.dumps(payload, default=str, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def git_identity() -> GitIdentity:
    """Read local Git identity without changing repository state."""
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return GitIdentity(branch=branch, sha=sha)
