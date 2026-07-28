#!/usr/bin/env python3
"""Operational list outputs for DoD §12.2 (first 8 list types).

Produces fail-closed CSV lists + manifest from PostgreSQL:
  1. editais_acionaveis (GO)
  2. editais_revisao (REVIEW)
  3. editais_descartados (NO_GO + motivo)
  4. oportunidades_removidas_snapshot (is_active=false)
  5. entes_sem_cobertura_editais
  6. entes_sem_cobertura_contratos
  7. blockers_por_fonte
  8. runs_stale

Fail-closed contract (ORPT PR1):
  - SQL / rollback / query failures raise OperationalQueryError and yield non-zero exit.
  - Errors are never silently converted into empty trustworthy CSVs.
  - Legitimate zero rows → SUCCESS_ZERO or NOT_READY with documented limitations.

Does not claim 95% coverage or LOCAL_READY.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.opportunity_intel.ranking import compute_ranking  # noqa: E402
from scripts.reports.run_metadata import (  # noqa: E402
    _git_sha_short,
    build_run_metadata,
    new_run_id,
    validate_operational_metadata,
)


class OperationalQueryError(RuntimeError):
    """Raised when a PostgreSQL query fails; must not become empty success CSV."""

    def __init__(self, message: str, *, sql: str | None = None) -> None:
        super().__init__(message)
        self.sql = sql
        self.message = message

LIST_FILES = {
    "editais_acionaveis": "editais_acionaveis.csv",
    "editais_revisao": "editais_revisao.csv",
    "editais_descartados": "editais_descartados.csv",
    "oportunidades_removidas_snapshot": "oportunidades_removidas_snapshot.csv",
    "entes_sem_cobertura_editais": "entes_sem_cobertura_editais.csv",
    "entes_sem_cobertura_contratos": "entes_sem_cobertura_contratos.csv",
    "blockers_por_fonte": "blockers_por_fonte.csv",
    "runs_stale": "runs_stale.csv",
}

EMPTY_HEADERS: dict[str, list[str]] = {
    "editais_acionaveis": [
        "source_id",
        "objeto",
        "orgao_cnpj",
        "orgao_nome",
        "uf",
        "municipio",
        "data_encerramento",
        "link_oficial",
        "ranking",
        "ranking_score",
        "ranking_confianca",
        "motivo",
        "fatores_positivos",
    ],
    "editais_revisao": [
        "source_id",
        "objeto",
        "orgao_cnpj",
        "orgao_nome",
        "uf",
        "municipio",
        "data_encerramento",
        "link_oficial",
        "ranking",
        "ranking_score",
        "ranking_confianca",
        "motivo",
        "fatores_positivos",
    ],
    "editais_descartados": [
        "source_id",
        "objeto",
        "orgao_cnpj",
        "orgao_nome",
        "uf",
        "municipio",
        "data_encerramento",
        "link_oficial",
        "ranking",
        "ranking_score",
        "ranking_confianca",
        "motivo",
        "fatores_positivos",
    ],
    "oportunidades_removidas_snapshot": [
        "source_id",
        "objeto",
        "orgao_cnpj",
        "orgao_nome",
        "uf",
        "municipio",
        "data_encerramento",
        "updated_at",
        "removal_reason",
    ],
    "entes_sem_cobertura_editais": [
        "entity_id",
        "razao_social",
        "cnpj_8",
        "municipio",
        "raio_200km",
        "gap_reason",
    ],
    "entes_sem_cobertura_contratos": [
        "entity_id",
        "razao_social",
        "cnpj_8",
        "municipio",
        "gap_reason",
    ],
    "blockers_por_fonte": ["source", "blocker_type", "n", "last_started", "detail"],
    "runs_stale": [
        "run_id",
        "source",
        "status",
        "started_at",
        "finished_at",
        "records_fetched",
        "stale_reason",
        "error_message",
    ],
}

DEFAULT_STALE_HOURS = 24
DEFAULT_STUCK_RUNNING_HOURS = 2


def _conn(dsn: str):
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _q(conn, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    """Execute SQL fail-closed: raise OperationalQueryError on failure (never {_error} rows)."""
    with conn.cursor() as cur:
        try:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001 — re-raised as typed operational error
            if hasattr(conn, "rollback"):
                conn.rollback()
            raise OperationalQueryError(str(exc), sql=sql[:200]) from exc


def _table_exists(conn, name: str) -> bool:
    rows = _q(
        conn,
        """
        SELECT 1 AS ok
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (name,),
    )
    return bool(rows)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> int:
    """Write CSV. Refuses rows containing ``_error`` (fail-closed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(isinstance(r, dict) and "_error" in r for r in rows):
        raise OperationalQueryError(
            "refusing to write CSV containing _error rows (fail-closed)"
        )
    clean = list(rows)
    if fieldnames is None:
        fieldnames = []
        for r in clean:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)
    if not fieldnames:
        fieldnames = ["note"]
        clean = []
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in clean:
            w.writerow({k: r.get(k) for k in fieldnames})
    return len(clean)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _db_schema_version(conn) -> str | None:
    if not _table_exists(conn, "_migrations"):
        return None
    rows = _q(
        conn,
        "SELECT version FROM _migrations ORDER BY applied_at DESC NULLS LAST LIMIT 1",
    )
    if not rows:
        return None
    return str(rows[0].get("version") or "")


def _dataset_hash(conn, schema_version: str | None) -> str:
    """Stable hash of live table counts + schema (not a market claim)."""
    tables = (
        "pncp_raw_bids",
        "pncp_supplier_contracts",
        "opportunity_intel",
        "sc_public_entities",
        "ingestion_runs",
        "target_universe_entities",
    )
    counts: dict[str, int] = {}
    for t in tables:
        if _table_exists(conn, t):
            rows = _q(conn, f"SELECT COUNT(*) AS n FROM {t}")  # noqa: S608 — allowlisted names
            counts[t] = int((rows[0] or {}).get("n") or 0)
        else:
            counts[t] = -1
    payload = json.dumps(
        {"schema_version": schema_version, "counts": counts},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _motivo_from_ranking(rank: dict[str, Any]) -> str:
    fatores = rank.get("ranking_fatores") or {}
    blocks = fatores.get("bloqueadores") or []
    negs = fatores.get("negativos") or []
    regras = rank.get("ranking_regras") or []
    parts = list(blocks) + list(negs)
    if not parts and regras:
        parts = list(regras)
    if not parts:
        return f"score={rank.get('ranking_score', 0)}; confianca={rank.get('ranking_confianca', 'LOW')}"
    return "; ".join(str(p) for p in parts[:8])


def _as_aware_dt(value: Any) -> datetime | None:
    """Normalize date/datetime/str to timezone-aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    # date (not datetime)
    from datetime import date as date_cls

    if isinstance(value, date_cls):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            return None
    return None


def _status_from_bid(row: dict[str, Any], now: datetime) -> str:
    enc = _as_aware_dt(row.get("data_encerramento"))
    if enc is not None and enc <= now:
        return "closed"
    situacao = str(row.get("situacao_compra") or "").lower()
    if any(x in situacao for x in ("revogad", "anulad", "cancelad", "fracassad")):
        return "revoked" if "revogad" in situacao else "closed"
    if row.get("is_active"):
        return "open"
    return "unknown"


def classify_bids(rows: list[dict[str, Any]], now: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    """Classify active bid rows into GO / REVIEW / NO_GO using compute_ranking."""
    now = now or datetime.now(UTC)
    out: dict[str, list[dict[str, Any]]] = {"GO": [], "REVIEW": [], "NO_GO": []}
    for row in rows:
        if isinstance(row, dict) and "_error" in row:
            raise OperationalQueryError(
                f"cannot classify rows with _error: {row.get('_error')}"
            )
        status = _status_from_bid(row, now)
        valor = row.get("valor_total_estimado")
        try:
            valor_f = float(valor) if valor is not None else None
        except (TypeError, ValueError):
            valor_f = None
        rank = compute_ranking(
            status_canonico=status,
            orgao_cnpj=row.get("orgao_cnpj"),
            objeto=row.get("objeto_compra") or row.get("objeto"),
            valor_estimado=valor_f,
            modalidade=row.get("modalidade_nome") or row.get("modalidade"),
            data_abertura=_as_aware_dt(row.get("data_abertura")),
            data_encerramento=_as_aware_dt(row.get("data_encerramento")),
            data_publicacao=_as_aware_dt(row.get("data_publicacao")),
            uf=row.get("uf"),
            municipio=row.get("municipio"),
            link_edital=row.get("link_pncp") or row.get("link_edital"),
            has_match_entity=bool(row.get("matched_entity_id")),
            dentro_raio=bool(row.get("matched_entity_id")),
            fonte_confiavel=True,
        )
        tier = rank["ranking"]
        rec = {
            "source_id": row.get("pncp_id") or row.get("source_id"),
            "objeto": (row.get("objeto_compra") or row.get("objeto") or "")[:200],
            "orgao_cnpj": row.get("orgao_cnpj"),
            "orgao_nome": row.get("orgao_razao_social") or row.get("orgao_nome"),
            "uf": row.get("uf"),
            "municipio": row.get("municipio"),
            "data_encerramento": str(row.get("data_encerramento") or ""),
            "link_oficial": row.get("link_pncp") or row.get("link_edital") or "",
            "ranking": tier,
            "ranking_score": rank.get("ranking_score"),
            "ranking_confianca": rank.get("ranking_confianca"),
            "motivo": _motivo_from_ranking(rank) if tier == "NO_GO" else "",
            "fatores_positivos": "; ".join((rank.get("ranking_fatores") or {}).get("positivos") or []),
        }
        out.setdefault(tier, []).append(rec)
    return out


def fetch_active_bids(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "pncp_raw_bids"):
        return []
    return _q(
        conn,
        """
        SELECT pncp_id, objeto_compra, valor_total_estimado, modalidade_nome,
               uf, municipio, orgao_razao_social, orgao_cnpj,
               data_publicacao, data_abertura, data_encerramento,
               link_pncp, is_active, matched_entity_id, situacao_compra, source
        FROM pncp_raw_bids
        WHERE is_active IS TRUE
        ORDER BY data_publicacao DESC NULLS LAST
        LIMIT 2000
        """,
    )


def fetch_from_opportunity_intel(conn) -> dict[str, list[dict[str, Any]]] | None:
    if not _table_exists(conn, "opportunity_intel"):
        return None
    rows = _q(
        conn,
        """
        SELECT source_id, objeto, orgao_cnpj, orgao_nome, uf, municipio,
               data_encerramento, link_edital, ranking, ranking_score,
               ranking_confianca, ranking_fatores, ranking_regras, is_active
        FROM opportunity_intel
        WHERE is_active IS TRUE
        ORDER BY ranking_score DESC NULLS LAST
        LIMIT 2000
        """,
    )
    if not rows:
        return None
    out: dict[str, list[dict[str, Any]]] = {"GO": [], "REVIEW": [], "NO_GO": []}
    for row in rows:
        tier = (row.get("ranking") or "REVIEW").upper()
        if tier not in out:
            tier = "REVIEW"
        fatores = row.get("ranking_fatores") or {}
        if isinstance(fatores, str):
            try:
                fatores = json.loads(fatores)
            except json.JSONDecodeError:
                fatores = {}
        motivo = ""
        if tier == "NO_GO":
            blocks = (fatores or {}).get("bloqueadores") or (fatores or {}).get("negativos") or []
            motivo = "; ".join(str(b) for b in blocks) if blocks else "NO_GO sem fatores"
        out[tier].append(
            {
                "source_id": row.get("source_id"),
                "objeto": (row.get("objeto") or "")[:200],
                "orgao_cnpj": row.get("orgao_cnpj"),
                "orgao_nome": row.get("orgao_nome"),
                "uf": row.get("uf"),
                "municipio": row.get("municipio"),
                "data_encerramento": str(row.get("data_encerramento") or ""),
                "link_oficial": row.get("link_edital") or "",
                "ranking": tier,
                "ranking_score": row.get("ranking_score"),
                "ranking_confianca": row.get("ranking_confianca"),
                "motivo": motivo,
                "fatores_positivos": "; ".join((fatores or {}).get("positivos") or []),
            }
        )
    return out


def fetch_removed_snapshot(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "pncp_raw_bids"):
        return []
    return _q(
        conn,
        """
        SELECT pncp_id AS source_id, objeto_compra AS objeto, orgao_cnpj,
               orgao_razao_social AS orgao_nome, uf, municipio,
               data_encerramento, updated_at, 'is_active=false' AS removal_reason
        FROM pncp_raw_bids
        WHERE is_active IS FALSE
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 2000
        """,
    )


def fetch_entities_without_tender_coverage(conn) -> list[dict[str, Any]]:
    """Entities in universe (or sc_public_entities) without any matched active bid."""
    if _table_exists(conn, "sc_public_entities") and _table_exists(conn, "pncp_raw_bids"):
        rows = _q(
            conn,
            """
            SELECT e.id AS entity_id, e.razao_social, e.cnpj_8, e.municipio,
                   e.raio_200km, 'no_matched_active_bid' AS gap_reason
            FROM sc_public_entities e
            WHERE e.is_active IS TRUE
              AND NOT EXISTS (
                SELECT 1 FROM pncp_raw_bids b
                WHERE b.matched_entity_id = e.id AND b.is_active IS TRUE
              )
            ORDER BY e.municipio NULLS LAST, e.razao_social
            LIMIT 5000
            """,
        )
        if rows and "_error" not in rows[0]:
            return rows
    if _table_exists(conn, "entity_coverage"):
        rows = _q(
            conn,
            """
            SELECT entity_id, source, total_bids, is_covered, last_seen_at,
                   'entity_coverage.is_covered=false' AS gap_reason
            FROM entity_coverage
            WHERE is_covered IS FALSE
            ORDER BY entity_id
            LIMIT 5000
            """,
        )
        if rows and "_error" not in rows[0]:
            return rows
    return []


def fetch_entities_without_contract_coverage(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "sc_public_entities"):
        return []
    if not _table_exists(conn, "pncp_supplier_contracts"):
        return _q(
            conn,
            """
            SELECT e.id AS entity_id, e.razao_social, e.cnpj_8, e.municipio,
                   'pncp_supplier_contracts_missing_or_empty' AS gap_reason
            FROM sc_public_entities e
            WHERE e.is_active IS TRUE
            ORDER BY e.razao_social
            LIMIT 5000
            """,
        )
    return _q(
        conn,
        """
        SELECT e.id AS entity_id, e.razao_social, e.cnpj_8, e.municipio,
               'no_contract_for_org_cnpj_prefix' AS gap_reason
        FROM sc_public_entities e
        WHERE e.is_active IS TRUE
          AND NOT EXISTS (
            SELECT 1 FROM pncp_supplier_contracts c
            WHERE LEFT(REGEXP_REPLACE(COALESCE(c.orgao_cnpj, ''), '[^0-9]', '', 'g'), 8)
                  = e.cnpj_8
               OR c.orgao_cnpj = e.cnpj_8
          )
        ORDER BY e.municipio NULLS LAST, e.razao_social
        LIMIT 5000
        """,
    )


def fetch_blockers_by_source(conn) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if _table_exists(conn, "ingestion_runs"):
        rows = _q(
            conn,
            """
            SELECT source, status, COUNT(*) AS n_runs,
                   MAX(started_at) AS last_started,
                   MAX(error_message) AS sample_error
            FROM ingestion_runs
            WHERE status IN ('failed', 'error', 'partial')
               OR (error_message IS NOT NULL AND error_message <> '')
            GROUP BY source, status
            ORDER BY source, status
            """,
        )
        for r in rows:
            if "_error" in r:
                continue
            blockers.append(
                {
                    "source": r.get("source"),
                    "blocker_type": f"ingestion_{r.get('status')}",
                    "n": r.get("n_runs"),
                    "last_started": str(r.get("last_started") or ""),
                    "detail": (r.get("sample_error") or "")[:300],
                }
            )
    if _table_exists(conn, "opportunity_runs"):
        rows = _q(
            conn,
            """
            SELECT source, status, COUNT(*) AS n
            FROM opportunity_runs
            WHERE status IN ('failed', 'error')
            GROUP BY source, status
            """,
        )
        for r in rows:
            if "_error" in r:
                continue
            blockers.append(
                {
                    "source": r.get("source"),
                    "blocker_type": f"opportunity_run_{r.get('status')}",
                    "n": r.get("n"),
                    "last_started": "",
                    "detail": "",
                }
            )
    return blockers


def fetch_stale_runs(
    conn,
    *,
    stale_hours: int = DEFAULT_STALE_HOURS,
    stuck_running_hours: int = DEFAULT_STUCK_RUNNING_HOURS,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    if not _table_exists(conn, "ingestion_runs"):
        return []
    stale_cut = now - timedelta(hours=stale_hours)
    stuck_cut = now - timedelta(hours=stuck_running_hours)
    rows = _q(
        conn,
        """
        SELECT id, source, started_at, finished_at, status,
               records_fetched, records_upserted, error_message
        FROM ingestion_runs
        ORDER BY started_at DESC
        LIMIT 500
        """,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        if "_error" in r:
            continue
        started = r.get("started_at")
        finished = r.get("finished_at")
        status = r.get("status")
        reason = None
        if status == "running" and started is not None:
            st = started if getattr(started, "tzinfo", None) else started.replace(tzinfo=UTC)
            if st < stuck_cut:
                reason = f"stuck_running_gt_{stuck_running_hours}h"
        elif finished is not None:
            ft = finished if getattr(finished, "tzinfo", None) else finished.replace(tzinfo=UTC)
            # completed runs older than stale window are "stale success" only if no newer completed for source
            # Mark runs still "running" already handled; also mark failed old ones
            if status in ("failed", "error", "partial") and ft < stale_cut:
                reason = f"failed_stale_gt_{stale_hours}h"
        elif status == "running":
            reason = "running_no_finish"
        if reason:
            out.append(
                {
                    "run_id": r.get("id"),
                    "source": r.get("source"),
                    "status": status,
                    "started_at": str(started or ""),
                    "finished_at": str(finished or ""),
                    "records_fetched": r.get("records_fetched"),
                    "stale_reason": reason,
                    "error_message": (r.get("error_message") or "")[:200],
                }
            )
    # Also: if latest completed per source is older than stale_hours, flag it
    latest = _q(
        conn,
        """
        SELECT DISTINCT ON (source)
               id, source, started_at, finished_at, status, records_fetched
        FROM ingestion_runs
        WHERE status = 'completed'
        ORDER BY source, finished_at DESC NULLS LAST
        """,
    )
    for r in latest:
        if "_error" in r:
            continue
        finished = r.get("finished_at") or r.get("started_at")
        if finished is None:
            continue
        ft = finished if getattr(finished, "tzinfo", None) else finished.replace(tzinfo=UTC)
        if ft < stale_cut:
            rid = r.get("id")
            if any(x.get("run_id") == rid for x in out):
                continue
            out.append(
                {
                    "run_id": rid,
                    "source": r.get("source"),
                    "status": r.get("status"),
                    "started_at": str(r.get("started_at") or ""),
                    "finished_at": str(finished or ""),
                    "records_fetched": r.get("records_fetched"),
                    "stale_reason": f"latest_completed_older_than_{stale_hours}h",
                    "error_message": "",
                }
            )
    return out


def build_operational_lists(
    conn,
    *,
    stale_hours: int = DEFAULT_STALE_HOURS,
    stuck_running_hours: int = DEFAULT_STUCK_RUNNING_HOURS,
) -> dict[str, Any]:
    """Build all 8 lists + counts + limitations.

    Query failures raise OperationalQueryError (fail-closed). Legitimate empty
    results are preserved with limitations — never invents GO rows.
    """
    limitations: list[str] = []
    errors: list[str] = []
    schema_version = _db_schema_version(conn)
    dataset_hash = _dataset_hash(conn, schema_version)

    oi = fetch_from_opportunity_intel(conn)
    if oi is not None and sum(len(v) for v in oi.values()) > 0:
        classified = oi
        source_of_ranking = "opportunity_intel"
    else:
        bids = fetch_active_bids(conn)
        classified = classify_bids(bids)
        source_of_ranking = "pncp_raw_bids+compute_ranking"
        if not bids:
            limitations.append(
                "No active pncp_raw_bids / opportunity_intel; GO/REVIEW/NO_GO lists empty (SUCCESS_ZERO)"
            )

    removed = fetch_removed_snapshot(conn)

    gap_editais = fetch_entities_without_tender_coverage(conn)
    if not gap_editais:
        # Distinguish empty universe vs all covered
        if _table_exists(conn, "sc_public_entities"):
            n_ent = _q(conn, "SELECT COUNT(*) AS n FROM sc_public_entities")
            n = int((n_ent[0] or {}).get("n") or 0) if n_ent else 0
            if n == 0:
                limitations.append(
                    "sc_public_entities empty — gap lists cannot enumerate universe entities"
                )
        else:
            limitations.append("sc_public_entities missing — gap lists empty")

    gap_contratos = fetch_entities_without_contract_coverage(conn)

    blockers = fetch_blockers_by_source(conn)
    # Drop any accidental error-shaped rows (should not appear after fail-closed _q)
    blockers = [r for r in blockers if "_error" not in r]
    stale = fetch_stale_runs(
        conn, stale_hours=stale_hours, stuck_running_hours=stuck_running_hours
    )
    stale = [r for r in stale if "_error" not in r]

    counts = {
        "GO": len(classified.get("GO", [])),
        "REVIEW": len(classified.get("REVIEW", [])),
        "NO_GO": len(classified.get("NO_GO", [])),
        "removed": len(removed),
        "gap_editais": len(gap_editais),
        "gap_contratos": len(gap_contratos),
        "blockers": len(blockers),
        "stale_runs": len(stale),
    }
    total_ranked = counts["GO"] + counts["REVIEW"] + counts["NO_GO"]
    status = "SUCCESS" if total_ranked > 0 else "SUCCESS_ZERO"
    if limitations and total_ranked == 0:
        status = "SUCCESS_ZERO"
    reliability = "READY" if total_ranked > 0 and not limitations else (
        "NOT_READY" if total_ranked == 0 else "PARTIAL"
    )
    # Legacy aliases kept for existing consumers/tests
    reliability_legacy = (
        "TRUSTED"
        if reliability == "READY"
        else ("DEGRADED" if reliability == "PARTIAL" else "UNTRUSTED")
    )

    return {
        "editais_acionaveis": classified.get("GO", []),
        "editais_revisao": classified.get("REVIEW", []),
        "editais_descartados": classified.get("NO_GO", []),
        "oportunidades_removidas_snapshot": removed,
        "entes_sem_cobertura_editais": gap_editais,
        "entes_sem_cobertura_contratos": gap_contratos,
        "blockers_por_fonte": blockers,
        "runs_stale": stale,
        "meta": {
            "ranking_source": source_of_ranking,
            "limitations": limitations,
            "errors": errors,
            "counts": counts,
            "status": status,
            "reliability": reliability,
            "reliability_legacy": reliability_legacy,
            "schema_version": schema_version,
            "dataset_hash": dataset_hash,
            "source": source_of_ranking,
            "period": {
                "as_of_date": datetime.now(UTC).date().isoformat(),
                "data_window": "all_active",
            },
            "parameters": {
                "stale_hours": stale_hours,
                "stuck_running_hours": stuck_running_hours,
            },
        },
    }


def write_lists(
    out_dir: Path,
    payload: dict[str, Any],
    *,
    run_id: str | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or new_run_id("ops-lists")
    code_sha = _git_sha_short()
    meta = payload.get("meta") or {}
    files: dict[str, dict[str, Any]] = {}
    artifact_hashes: dict[str, str] = {}
    for key, filename in LIST_FILES.items():
        rows = payload.get(key) or []
        path = out_dir / filename
        rows_list = rows if isinstance(rows, list) else []
        headers = EMPTY_HEADERS.get(key)
        if rows_list:
            n = _write_csv(path, rows_list, fieldnames=None)
        else:
            n = _write_csv(path, [], fieldnames=headers)
        digest = _file_sha256(path)
        artifact_hashes[filename] = digest
        files[key] = {
            "path": str(path),
            "rows": n,
            "bytes": path.stat().st_size,
            "sha256": digest,
        }

    counts = meta.get("counts") or {}
    total_ranked = int(counts.get("GO") or 0) + int(counts.get("REVIEW") or 0) + int(
        counts.get("NO_GO") or 0
    )
    status = meta.get("status") or ("SUCCESS" if total_ranked > 0 else "SUCCESS_ZERO")
    reliability = meta.get("reliability") or (
        "READY" if total_ranked > 0 else "NOT_READY"
    )
    reliability_legacy = meta.get("reliability_legacy") or (
        "TRUSTED"
        if reliability == "READY"
        else ("DEGRADED" if reliability == "PARTIAL" else "UNTRUSTED")
    )
    limitations = list(meta.get("limitations") or [])
    errors = list(meta.get("errors") or [])

    shared = build_run_metadata(
        run_id=rid,
        artifact_kind="operational_lists",
        script="scripts/reports/operational_outputs.py",
        code_sha=code_sha,
        db_schema_version=meta.get("schema_version"),
        universe_version=None,
        dataset_hash=meta.get("dataset_hash"),
        source=meta.get("source") or meta.get("ranking_source"),
        capability="operational_lists_12_2",
        period=meta.get("period"),
        parameters=meta.get("parameters"),
        reliability=reliability,
        limitations=limitations,
        errors=errors,
        duration_seconds=duration_seconds,
        artifact_hashes=artifact_hashes,
        stats={
            "go_count": counts.get("GO"),
            "review_count": counts.get("REVIEW"),
            "no_go_count": counts.get("NO_GO"),
            "raw_bids_count": total_ranked,
        },
    )

    manifest = {
        **shared,
        "section": "12.2",
        "lists": files,
        "counts": counts,
        "ranking_source": meta.get("ranking_source"),
        "status": status,
        "reliability": reliability,
        "reliability_legacy": reliability_legacy,
        # Keep prior key name for tests that assert DEGRADED/UNTRUSTED when empty
        "claims": {
            "allowed": [
                "Eight operational list CSVs generated from PostgreSQL",
                "Active bids classified into GO/REVIEW/NO_GO when data present",
                "Empty gap lists documented when universe not seeded",
                "SUCCESS_ZERO when zero rows with documented limitations",
            ],
            "forbidden": [
                "LOCAL_READY",
                "operational coverage 95%",
                "PRE_VPS_FINAL_READY",
                "PROJECT_DONE",
                "empty CSV after SQL error as success",
            ],
        },
    }
    missing = validate_operational_metadata(manifest)
    if missing:
        limitations.append(f"metadata_incomplete:{','.join(missing)}")
        manifest["limitations"] = limitations
        manifest["reliability"] = "PARTIAL" if reliability == "READY" else reliability

    man_path = out_dir / "manifest.json"
    man_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    manifest["manifest_path"] = str(man_path)
    manifest["artifact_hashes"]["manifest.json"] = _file_sha256(man_path)
    return manifest


def run(dsn: str, out_dir: Path, **kwargs: Any) -> dict[str, Any]:
    """Run operational lists. Raises OperationalQueryError on SQL failure."""
    t0 = time.perf_counter()
    conn = _conn(dsn)
    try:
        payload = build_operational_lists(conn, **kwargs)
    finally:
        conn.close()
    duration = time.perf_counter() - t0
    return write_lists(out_dir, payload, duration_seconds=round(duration, 4))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD §12.2 operational list outputs")
    p.add_argument("--dsn", default=os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL"))
    p.add_argument("--out", type=Path, default=Path("output/operational-lists"))
    p.add_argument("--stale-hours", type=int, default=DEFAULT_STALE_HOURS)
    p.add_argument("--stuck-running-hours", type=int, default=DEFAULT_STUCK_RUNNING_HOURS)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Connect and classify only; write nothing under --out",
    )
    args = p.parse_args(argv)
    if not args.dsn:
        print("ERROR: --dsn or LOCAL_DATALAKE_DSN required", file=sys.stderr)
        return 2
    try:
        if args.dry_run:
            conn = _conn(args.dsn)
            try:
                payload = build_operational_lists(
                    conn,
                    stale_hours=args.stale_hours,
                    stuck_running_hours=args.stuck_running_hours,
                )
            finally:
                conn.close()
            meta = payload.get("meta") or {}
            summary = {
                "dry_run": True,
                "counts": meta.get("counts"),
                "ranking_source": meta.get("ranking_source"),
                "limitations": meta.get("limitations"),
                "errors": meta.get("errors"),
                "status": meta.get("status"),
                "reliability": meta.get("reliability"),
                "would_write": str(args.out),
            }
            print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
            return 0
        manifest = run(
            args.dsn,
            args.out,
            stale_hours=args.stale_hours,
            stuck_running_hours=args.stuck_running_hours,
        )
    except OperationalQueryError as exc:
        err = {
            "ok": False,
            "error": str(exc),
            "error_type": "OperationalQueryError",
            "exit_code": 1,
        }
        print(json.dumps(err, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        err = {
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "exit_code": 1,
        }
        print(json.dumps(err, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    else:
        print(
            f"run_id={manifest['run_id']} status={manifest.get('status')} "
            f"reliability={manifest['reliability']}"
        )
        for k, v in (manifest.get("counts") or {}).items():
            print(f"  {k}: {v}")
        print(f"manifest: {manifest.get('manifest_path')}")
    # SUCCESS_ZERO is still exit 0 (legitimate empty), SQL failure is 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
