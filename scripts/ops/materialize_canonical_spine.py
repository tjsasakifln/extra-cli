"""Materialize canonical spine tables for the weekly decision cycle.

Ensures:
  - target_universe_entities (1.093 included / seed snapshot)
  - entity_source_registry (1.093 rows from data/entity_source_registry.jsonl)

Does NOT invent coverage: empty capability_coverage remains empty until real
collection evidence is projected. Registry existence ≠ operational coverage.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_N = 1093


def _q(conn: Any, sql: str, params: tuple | list | None = None) -> list[Any]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        try:
            return list(cur.fetchall())
        except Exception:
            return []


def _table_exists(conn: Any, name: str) -> bool:
    rows = _q(
        conn,
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (name,),
    )
    return bool(rows)


def _count(conn: Any, table: str, where: str = "TRUE") -> int:
    if not _table_exists(conn, table):
        return -1
    # table/where are internal constants only
    rows = _q(conn, f"SELECT COUNT(*)::int AS n FROM {table} WHERE {where}")  # noqa: S608
    if not rows:
        return 0
    r = rows[0]
    if isinstance(r, dict):
        return int(r.get("n") or 0)
    return int(r[0] or 0)


def ensure_target_universe(conn: Any, *, dsn: str | None = None) -> dict[str, Any]:
    """Ensure target_universe_entities is populated from canonical seed."""
    result: dict[str, Any] = {"table": "target_universe_entities", "action": "none"}
    if not _table_exists(conn, "target_universe_entities"):
        result["status"] = "BLOCKED_INFRA"
        result["detail"] = "table missing — run migrations"
        return result

    n = _count(conn, "target_universe_entities")
    result["before"] = n
    if n >= CANONICAL_N:
        result["status"] = "ok"
        result["after"] = n
        result["action"] = "reuse"
        return result

    # Populate via universe_tools snapshot (uses LOCAL_DATALAKE_DSN)
    if dsn:
        os.environ.setdefault("LOCAL_DATALAKE_DSN", dsn)
    try:
        from scripts.universe_tools import (  # noqa: I001
            DEFAULT_SEED_PATH,
            _insert_entity_batch,
            generate_snapshot,
            get_latest_snapshot,
            load_canonical_universe_for_snapshot,
            sha256_file,
        )
    except Exception as exc:  # noqa: BLE001
        result["status"] = "BLOCKED_INFRA"
        result["error"] = f"import universe_tools: {exc}"
        return result

    try:
        snap = generate_snapshot(DEFAULT_SEED_PATH, block_on_change=False)
        result["snapshot"] = {
            k: snap.get(k) for k in ("status", "run_id", "seed_sha256", "total_rows", "included_rows")
        }
    except Exception as exc:  # noqa: BLE001
        result["status"] = "BLOCKED_INFRA"
        result["error"] = f"generate_snapshot: {exc}"
        return result

    n2 = _count(conn, "target_universe_entities")
    if n2 >= CANONICAL_N:
        result["status"] = "ok"
        result["after"] = n2
        result["action"] = "snapshot_or_reuse"
        return result

    # Repair path: run exists but entities empty (partial prior failure)
    latest = get_latest_snapshot(conn)
    run_id = (latest or {}).get("id") or (snap or {}).get("run_id")
    if not run_id:
        result["status"] = "BLOCKED_INFRA"
        result["error"] = "no universe_run_id to attach entities"
        result["after"] = n2
        return result

    try:
        universe = load_canonical_universe_for_snapshot(DEFAULT_SEED_PATH)
        batch: list[tuple] = []
        with conn.cursor() as cur:
            for entity in universe.entities:
                batch.append(
                    (
                        run_id,
                        entity.entity_id,
                        entity.seed_row,
                        entity.cnpj8,
                        entity.razao_social,
                        entity.municipio,
                        entity.codigo_ibge,
                        entity.natureza_juridica,
                        entity.latitude,
                        entity.longitude,
                        entity.distancia_km,
                        entity.radius_decision,
                        entity.duplicate_root,
                        entity.db_entity_id,
                        entity.db_match_method,
                    )
                )
                if len(batch) >= 500:
                    _insert_entity_batch(cur, batch)
                    batch = []
            if batch:
                _insert_entity_batch(cur, batch)
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception as rb_exc:  # noqa: BLE001
            result["rollback_error"] = str(rb_exc)
        result["status"] = "BLOCKED_INFRA"
        result["error"] = f"repair insert: {exc}"
        result["after"] = _count(conn, "target_universe_entities")
        return result

    n3 = _count(conn, "target_universe_entities")
    # Count included (within radius) if column present
    included = _count(
        conn,
        "target_universe_entities",
        "radius_decision IN ('included', 'INCLUDE', 'include') OR radius_decision ILIKE 'in%'",
    )
    result["after"] = n3
    result["included_approx"] = included
    result["seed_sha256"] = sha256_file(DEFAULT_SEED_PATH)
    result["action"] = "repaired_insert"
    result["status"] = "ok" if n3 >= CANONICAL_N else "PARTIAL"
    if n3 < CANONICAL_N:
        result["detail"] = f"entities={n3} < {CANONICAL_N}"
    return result


def ensure_entity_source_registry(conn: Any, *, dsn: str | None = None) -> dict[str, Any]:
    """Ensure entity_source_registry has 1.093 rows from the JSONL authority."""
    result: dict[str, Any] = {"table": "entity_source_registry", "action": "none"}
    if not _table_exists(conn, "entity_source_registry"):
        result["status"] = "BLOCKED_INFRA"
        result["detail"] = "table missing — run migrations (053)"
        return result

    n = _count(conn, "entity_source_registry")
    result["before"] = n
    if n >= CANONICAL_N:
        result["status"] = "ok"
        result["after"] = n
        result["action"] = "reuse"
        result["note"] = "registry existence is not operational coverage"
        return result

    try:
        from scripts.source_registry.builder import load_registry
        from scripts.source_registry.persistence import sync_registry_to_postgres
    except Exception as exc:  # noqa: BLE001
        result["status"] = "BLOCKED_INFRA"
        result["error"] = f"import source_registry: {exc}"
        return result

    try:
        records = load_registry()
        sync = sync_registry_to_postgres(records, dsn=dsn)
        result["sync"] = sync
        result["action"] = "sync_db"
    except Exception as exc:  # noqa: BLE001
        result["status"] = "BLOCKED_INFRA"
        result["error"] = f"sync_registry: {exc}"
        return result

    n2 = _count(conn, "entity_source_registry")
    result["after"] = n2
    result["status"] = "ok" if n2 >= CANONICAL_N else "PARTIAL"
    result["note"] = "registry existence is not operational coverage"
    return result


def materialize_canonical_spine(conn: Any, *, dsn: str | None = None) -> dict[str, Any]:
    """Materialize universe + registry; report capability_coverage honestly."""
    uni = ensure_target_universe(conn, dsn=dsn)
    reg = ensure_entity_source_registry(conn, dsn=dsn)
    cap_n = _count(conn, "capability_coverage") if _table_exists(conn, "capability_coverage") else -1
    return {
        "universe": uni,
        "entity_source_registry": reg,
        "capability_coverage": {
            "count": cap_n,
            "note": (
                "capability_coverage rows are evidence-backed; empty means no "
                "proven operational coverage — not zero success"
            ),
        },
        "claims_forbidden": [
            "registry_exists = operational_coverage",
            "entity_count = multi_source_coverage",
        ],
        "status": (
            "ok"
            if uni.get("status") == "ok" and reg.get("status") == "ok"
            else "PARTIAL"
            if uni.get("status") in {"ok", "PARTIAL"} or reg.get("status") in {"ok", "PARTIAL"}
            else "BLOCKED_INFRA"
        ),
    }


__all__ = [
    "CANONICAL_N",
    "ensure_entity_source_registry",
    "ensure_target_universe",
    "materialize_canonical_spine",
]
