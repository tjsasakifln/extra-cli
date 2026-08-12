"""Load multi-source observations from PostgreSQL lake + optional file artifacts.

Bridges the operational lake (opportunity_intel, official_acts) into the
EXTRA-MS-OPEN observation model without requiring pre-exported CSVs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from scripts.ops.multi_source_open_pack.events import classify_event
from scripts.ops.multi_source_open_pack.loaders import (
    load_ciga_observations,
    load_sc_compras_observations,
)
from scripts.ops.multi_source_open_pack.models import SourceObservation
from scripts.ops.multi_source_open_pack.textutil import optional_float

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SNAPSHOT_PAGE_SIZE = 1000
DEFAULT_OBSERVATION_MEMORY_BUDGET_BYTES = 512 * 1024 * 1024
MEMORY_OVERHEAD_FACTOR = 4


class SnapshotReconciliationError(RuntimeError):
    """The streamed rows do not exactly match their SQL snapshot."""


class LineageSelectionError(SnapshotReconciliationError):
    """A package row is outside the explicitly selected collection run."""


@dataclass(frozen=True)
class OpportunityLineageSelection:
    """Exact PNCP snapshot authorized to feed one decision package."""

    collection_id: str
    source_run_id: int
    external_run_id: str
    mode: str
    expected_records: int
    freshness_hours: float | None = None
    freshness_sla_hours: float | None = None


def _memory_budget_bytes() -> int:
    value = os.getenv("EXTRA_OBSERVATION_MEMORY_BUDGET_MB")
    if not value:
        return DEFAULT_OBSERVATION_MEMORY_BUDGET_BYTES
    try:
        megabytes = int(value.strip())
    except ValueError as exc:
        raise ValueError(
            "EXTRA_OBSERVATION_MEMORY_BUDGET_MB must be an integer number of MB, "
            f"got {value!r}"
        ) from exc
    return max(1, megabytes) * 1024 * 1024


def _estimate_observation_memory(observations: list[SourceObservation]) -> int:
    return sum(
        len(json.dumps(observation.raw, ensure_ascii=False, default=str).encode("utf-8"))
        * MEMORY_OVERHEAD_FACTOR
        + 2048
        for observation in observations
    )


def _obs_from_row(
    *,
    fonte: str,
    fonte_papel: str,
    id_externo: str,
    orgao: str,
    orgao_cnpj: str,
    municipio: str,
    uf: str,
    objeto: str,
    modalidade: str,
    valor_estimado: Any,
    data_publicacao: str,
    data_abertura: str,
    data_encerramento: str,
    url: str,
    status_fonte: str,
    categoria_ato: str,
    raw: dict[str, Any] | None = None,
) -> SourceObservation:
    oid = f"{fonte}:{id_externo or hash((orgao, (objeto or '')[:80], data_publicacao))}"
    event_type, is_active, excl = classify_event(
        categoria_ato=categoria_ato,
        objeto=objeto or "",
        status_fonte=status_fonte,
        fonte=fonte,
    )
    return SourceObservation(
        observation_id=oid,
        fonte=fonte,
        fonte_papel=fonte_papel,
        id_externo=str(id_externo or ""),
        orgao=orgao or "",
        orgao_cnpj=orgao_cnpj or "",
        municipio=municipio or "",
        uf=uf or "SC",
        objeto=(objeto or "")[:2000],
        modalidade=modalidade or "",
        valor_estimado=optional_float(valor_estimado),
        data_publicacao=str(data_publicacao or ""),
        data_abertura=str(data_abertura or ""),
        data_encerramento=str(data_encerramento or ""),
        url=str(url or ""),
        status_fonte=status_fonte or "",
        categoria_ato=categoria_ato or "",
        raw=raw or {},
        event_type=event_type,
        is_active_dispute=is_active,
        exclusion_reason=excl,
    )


def _q(conn: Any, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def _table_exists(conn: Any, name: str) -> bool:
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


def _fonte_papel(source: str) -> str:
    s = (source or "").lower()
    if s in {"pncp", "pncp_opportunities", "test_batch"}:
        return "required"
    if s in {"ciga_ckan", "ciga", "dom_sc", "ciga_dom"}:
        return "required_municipal"
    if s in {"sc_compras"}:
        return "complementary_estadual"
    if s in {"pcp", "compras_gov", "doe_sc", "tce_sc"}:
        return "complementary"
    return "gap_fill"


def _normalize_source_key(source: str) -> str:
    s = (source or "").strip().lower()
    if s in {"pncp", "pncp_opportunities", "test_batch"}:
        return "pncp"
    if s in {"ciga", "ciga_dom", "dom_sc"}:
        return "ciga_ckan"
    return s or "unknown"


def _stream_snapshot_rows(
    conn: Any,
    sql: str,
    params: tuple[Any, ...],
    *,
    source: str,
    page_size: int,
    memory_budget_bytes: int,
    required_lineage_run_id: int | None = None,
    required_external_run_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch one SQL snapshot in bounded batches and reconcile its exact count."""
    cursor_name = f"extra_{source}_{uuid.uuid4().hex}"
    try:
        cur = conn.cursor(name=cursor_name)
        cursor_mode = "server_side"
    except TypeError:
        cur = conn.cursor()
        cursor_mode = "client_fallback"
    rows: list[dict[str, Any]] = []
    snapshot_id = ""
    eligible_count: int | None = None
    pages_fetched = 0
    estimated_memory_bytes = 0
    seen_ids: set[str] = set()
    try:
        if hasattr(cur, "itersize"):
            cur.itersize = page_size
        cur.execute(sql, params)
        while True:
            batch = cur.fetchmany(page_size)
            if not batch:
                break
            pages_fetched += 1
            for raw_row in batch:
                row = dict(raw_row)
                current_count = int(row.pop("_snapshot_eligible_count", 0) or 0)
                current_snapshot = str(row.pop("_snapshot_id", "") or "")
                present = bool(row.pop("_snapshot_row_present", True))
                if eligible_count is None:
                    eligible_count = current_count
                    snapshot_id = current_snapshot
                elif eligible_count != current_count or snapshot_id != current_snapshot:
                    raise SnapshotReconciliationError(
                        f"{source}: snapshot metadata changed while streaming"
                    )
                if not present:
                    continue
                if required_lineage_run_id is not None:
                    row_lineage = row.get("_lineage_run_id")
                    if row_lineage is None or int(row_lineage) != required_lineage_run_id:
                        raise LineageSelectionError(
                            f"{source}: row id={row.get('id')!r} has lineage "
                            f"{row_lineage!r}, expected run {required_lineage_run_id}"
                        )
                    row_external_run = str(row.get("_lineage_external_run_id") or "")
                    if row_external_run != required_external_run_id:
                        raise LineageSelectionError(
                            f"{source}: row id={row.get('id')!r} has external run "
                            f"{row_external_run!r}, expected {required_external_run_id!r}"
                        )
                row_id = str(row.get("id") or "")
                if not row_id or row_id in seen_ids:
                    raise SnapshotReconciliationError(
                        f"{source}: missing or duplicate stable id {row_id!r}"
                    )
                seen_ids.add(row_id)
                estimated_memory_bytes += (
                    len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
                    * MEMORY_OVERHEAD_FACTOR
                )
                if estimated_memory_bytes > memory_budget_bytes:
                    raise SnapshotReconciliationError(
                        f"{source}: estimated memory {estimated_memory_bytes} exceeds "
                        f"budget {memory_budget_bytes}; use a report-ready projection"
                    )
                rows.append(row)
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()

    if eligible_count is None:
        raise SnapshotReconciliationError(f"{source}: SQL returned no snapshot metadata")
    if not snapshot_id:
        raise SnapshotReconciliationError(f"{source}: SQL returned an empty snapshot id")
    if len(rows) != eligible_count:
        raise SnapshotReconciliationError(
            f"{source}: rows_read={len(rows)} != snapshot_eligible={eligible_count}"
        )
    return rows, {
        "source": source,
        "snapshot_id": snapshot_id,
        "cursor_mode": cursor_mode,
        "stable_order": "id ASC",
        "page_size": page_size,
        "pages_fetched": pages_fetched,
        "eligible_count": eligible_count,
        "rows_read": len(rows),
        "duplicate_ids": 0,
        "complete": True,
        "estimated_memory_bytes": estimated_memory_bytes,
        "memory_budget_bytes": memory_budget_bytes,
        "presentation_truncated": False,
    }


def load_opportunity_intel_snapshot(
    conn: Any,
    *,
    statuses: tuple[str, ...] = ("open", "upcoming"),
    page_size: int = DEFAULT_SNAPSHOT_PAGE_SIZE,
    memory_budget_bytes: int | None = None,
    lineage: OpportunityLineageSelection | None = None,
) -> tuple[list[SourceObservation], dict[str, Any]]:
    """Load every eligible opportunity from one reconciled SQL snapshot."""
    if not _table_exists(conn, "opportunity_intel"):
        if lineage is not None:
            raise LineageSelectionError(
                "opportunity_intel: selected lineage cannot be proven; table missing"
            )
        return [], {
            "source": "opportunity_intel",
            "eligible_count": 0,
            "rows_read": 0,
            "complete": True,
            "table_missing": True,
            "presentation_truncated": False,
        }
    placeholders = ",".join(["%s"] * len(statuses))
    if lineage is not None:
        if lineage.source_run_id <= 0:
            raise LineageSelectionError(
                "opportunity_intel: selected source_run_id must be positive"
            )
        if not lineage.external_run_id:
            raise LineageSelectionError(
                "opportunity_intel: selected external_run_id is required"
            )
        if lineage.expected_records < 0:
            raise LineageSelectionError(
                "opportunity_intel: expected_records cannot be negative"
            )
        if not _table_exists(conn, "source_snapshot_membership"):
            raise LineageSelectionError(
                "opportunity_intel: source_snapshot_membership table missing"
            )
    if lineage is None:
        eligible_sql = f"""
            SELECT id, source, source_id, numero_controle_pncp, orgao_cnpj, orgao_nome,
                   municipio, uf, objeto, modalidade, valor_estimado,
                   status_canonico, data_publicacao, data_abertura, data_encerramento,
                   link_edital, source_url, run_id, crawl_batch_id, proveniencia,
                   NULL::bigint AS _lineage_run_id,
                   NULL::text AS _lineage_external_run_id,
                   NULL::text AS _lineage_source_record_id,
                   NULL::text AS _lineage_key
            FROM opportunity_intel
            WHERE COALESCE(is_active, TRUE)
              AND status_canonico IN ({placeholders})
        """  # noqa: S608 — placeholders only
        params: tuple[Any, ...] = tuple(statuses)
    else:
        eligible_sql = f"""
            SELECT oi.id, oi.source, oi.source_id, oi.numero_controle_pncp,
                   oi.orgao_cnpj, oi.orgao_nome, oi.municipio, oi.uf, oi.objeto,
                   oi.modalidade, oi.valor_estimado, oi.status_canonico,
                   oi.data_publicacao, oi.data_abertura, oi.data_encerramento,
                   oi.link_edital, oi.source_url, oi.run_id, oi.crawl_batch_id,
                   oi.proveniencia, membership.source_run_id AS _lineage_run_id,
                   selected_run.external_run_id AS _lineage_external_run_id,
                   membership.source_record_id AS _lineage_source_record_id,
                   membership.canonical_opportunity_key AS _lineage_key
            FROM source_snapshot_membership membership
            JOIN opportunity_runs selected_run
              ON selected_run.id = membership.source_run_id
             AND selected_run.id = %s
             AND selected_run.external_run_id = %s
            JOIN LATERAL (
                SELECT candidate.*
                FROM opportunity_intel candidate
                WHERE candidate.source_id = membership.source_record_id
                   OR candidate.numero_controle_pncp = membership.source_record_id
                   OR candidate.numero_controle_pncp = membership.canonical_opportunity_key
                   OR candidate.content_hash = membership.canonical_opportunity_key
                ORDER BY candidate.id DESC
                LIMIT 1
            ) oi ON TRUE
            WHERE COALESCE(oi.is_active, TRUE)
              AND oi.status_canonico IN ({placeholders})
        """  # noqa: S608 — placeholders only
        params = (lineage.source_run_id, lineage.external_run_id, *statuses)
    rows, snapshot = _stream_snapshot_rows(
        conn,
        f"""
        WITH eligible AS MATERIALIZED (
            {eligible_sql}
        ), snapshot_meta AS (
            SELECT COUNT(*)::bigint AS eligible_count,
                   txid_current_snapshot()::text AS snapshot_id
            FROM eligible
        )
        SELECT eligible.*,
               snapshot_meta.eligible_count AS _snapshot_eligible_count,
               snapshot_meta.snapshot_id AS _snapshot_id,
               (eligible.id IS NOT NULL) AS _snapshot_row_present
        FROM snapshot_meta
        LEFT JOIN eligible ON TRUE
        ORDER BY eligible.id ASC NULLS LAST
        """,  # noqa: S608 — placeholders only
        params,
        source="opportunity_intel",
        page_size=page_size,
        memory_budget_bytes=memory_budget_bytes or _memory_budget_bytes(),
        required_lineage_run_id=lineage.source_run_id if lineage else None,
        required_external_run_id=lineage.external_run_id if lineage else None,
    )
    if lineage is not None:
        if snapshot["rows_read"] != lineage.expected_records:
            raise LineageSelectionError(
                "opportunity_intel: selected run "
                f"{lineage.source_run_id} loaded={snapshot['rows_read']} "
                f"expected={lineage.expected_records}"
            )
        digest_lines = sorted(
            f"{r.get('_lineage_run_id')}:{r.get('_lineage_source_record_id')}:"
            f"{r.get('_lineage_key') or ''}"
            for r in rows
        )
        snapshot["lineage"] = {
            "collection_id": lineage.collection_id,
            "source_run_id": lineage.source_run_id,
            "external_run_id": lineage.external_run_id,
            "mode": lineage.mode,
            "expected_records": lineage.expected_records,
            "loaded_records": snapshot["rows_read"],
            "sha256": hashlib.sha256("\n".join(digest_lines).encode("utf-8")).hexdigest(),
            "freshness_hours": lineage.freshness_hours,
            "freshness_sla_hours": lineage.freshness_sla_hours,
        }
    out: list[SourceObservation] = []
    for r in rows:
        fonte = _normalize_source_key(str(r.get("source") or "pncp"))
        ext = r.get("numero_controle_pncp") or r.get("source_id") or str(r.get("id") or "")
        url = r.get("link_edital") or r.get("source_url") or ""
        if not url and r.get("numero_controle_pncp"):
            # PNCP public portal pattern when only control number is known
            url = f"https://pncp.gov.br/app/editais/{r['numero_controle_pncp']}"
        out.append(
            _obs_from_row(
                fonte=fonte,
                fonte_papel=_fonte_papel(fonte),
                id_externo=str(ext),
                orgao=str(r.get("orgao_nome") or ""),
                orgao_cnpj=str(r.get("orgao_cnpj") or ""),
                municipio=str(r.get("municipio") or ""),
                uf=str(r.get("uf") or "SC"),
                objeto=str(r.get("objeto") or ""),
                modalidade=str(r.get("modalidade") or ""),
                valor_estimado=r.get("valor_estimado"),
                data_publicacao=str(r.get("data_publicacao") or ""),
                data_abertura=str(r.get("data_abertura") or ""),
                data_encerramento=str(r.get("data_encerramento") or ""),
                url=str(url or ""),
                status_fonte=str(r.get("status_canonico") or "open"),
                categoria_ato="edital_aberto",
                raw=dict(r),
            )
        )
    return out, snapshot


def load_opportunity_intel_observations(
    conn: Any,
    *,
    statuses: tuple[str, ...] = ("open", "upcoming"),
    page_size: int = DEFAULT_SNAPSHOT_PAGE_SIZE,
    memory_budget_bytes: int | None = None,
) -> list[SourceObservation]:
    observations, _snapshot = load_opportunity_intel_snapshot(
        conn,
        statuses=statuses,
        page_size=page_size,
        memory_budget_bytes=memory_budget_bytes,
    )
    return observations


def load_official_acts_snapshot(
    conn: Any,
    *,
    lookback_days: int = 45,
    page_size: int = DEFAULT_SNAPSHOT_PAGE_SIZE,
    memory_budget_bytes: int | None = None,
) -> tuple[list[SourceObservation], dict[str, Any]]:
    """Load every eligible official act from one reconciled SQL snapshot."""
    if not _table_exists(conn, "official_acts"):
        return [], {
            "source": "official_acts",
            "eligible_count": 0,
            "rows_read": 0,
            "complete": True,
            "table_missing": True,
            "presentation_truncated": False,
        }
    rows, snapshot = _stream_snapshot_rows(
        conn,
        """
        WITH eligible AS MATERIALIZED (
            SELECT id, source, external_id, source_url, title, category,
                   publication_date, orgao_nome, municipio, raw_json, run_id
            FROM official_acts
            WHERE COALESCE(publication_date, ingested_at::date)
                  >= CURRENT_DATE - (%s || ' days')::interval
        ), snapshot_meta AS (
            SELECT COUNT(*)::bigint AS eligible_count,
                   txid_current_snapshot()::text AS snapshot_id
            FROM eligible
        )
        SELECT eligible.*,
               snapshot_meta.eligible_count AS _snapshot_eligible_count,
               snapshot_meta.snapshot_id AS _snapshot_id,
               (eligible.id IS NOT NULL) AS _snapshot_row_present
        FROM snapshot_meta
        LEFT JOIN eligible ON TRUE
        ORDER BY eligible.id ASC NULLS LAST
        """,
        (lookback_days,),
        source="official_acts",
        page_size=page_size,
        memory_budget_bytes=memory_budget_bytes or _memory_budget_bytes(),
    )
    out: list[SourceObservation] = []
    for r in rows:
        fonte = _normalize_source_key(str(r.get("source") or "ciga_ckan"))
        if fonte == "pncp":
            fonte = "ciga_ckan"  # acts table is not PNCP open tenders
        cat = str(r.get("category") or "publicacao_dom")
        out.append(
            _obs_from_row(
                fonte=fonte if fonte != "unknown" else "ciga_ckan",
                fonte_papel="required_municipal",
                id_externo=str(r.get("external_id") or r.get("id") or ""),
                orgao=str(r.get("orgao_nome") or ""),
                orgao_cnpj="",
                municipio=str(r.get("municipio") or ""),
                uf="SC",
                objeto=str(r.get("title") or ""),
                modalidade=cat,
                valor_estimado="",
                data_publicacao=str(r.get("publication_date") or ""),
                data_abertura="",
                data_encerramento="",
                url=str(r.get("source_url") or ""),
                status_fonte="publicacao_dom",
                categoria_ato=cat,
                raw=dict(r),
            )
        )
    return out, snapshot


def load_official_acts_observations(
    conn: Any,
    *,
    lookback_days: int = 45,
    page_size: int = DEFAULT_SNAPSHOT_PAGE_SIZE,
    memory_budget_bytes: int | None = None,
) -> list[SourceObservation]:
    observations, _snapshot = load_official_acts_snapshot(
        conn,
        lookback_days=lookback_days,
        page_size=page_size,
        memory_budget_bytes=memory_budget_bytes,
    )
    return observations


def discover_ciga_jsonl(search_roots: list[Path] | None = None) -> Path | None:
    """Return newest CIGA publications.jsonl under known output paths."""
    roots = search_roots or [
        PROJECT_ROOT / "output" / "ciga_dom",
        PROJECT_ROOT / "output" / "ciga-ckan",
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(root.glob("**/publications.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def discover_sc_compras_jsonl(search_roots: list[Path] | None = None) -> Path | None:
    roots = search_roots or [
        PROJECT_ROOT / "output" / "sc_compras",
        PROJECT_ROOT / "output" / "resilience",
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(root.glob("**/*sc_compras*.jsonl"))
        candidates.extend(root.glob("**/open*.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def export_pncp_csv(observations: list[SourceObservation], path: Path) -> Path:
    """Write PNCP-shaped CSV for multi_source pack loaders (interop)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "numero_controle_pncp",
        "source_id",
        "orgao_nome",
        "orgao_cnpj",
        "municipio",
        "uf",
        "objeto",
        "modalidade",
        "valor_estimado",
        "data_publicacao",
        "data_abertura",
        "data_encerramento",
        "link_edital",
        "source_url",
        "status_canonico",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for o in observations:
            if o.fonte != "pncp":
                continue
            w.writerow(
                {
                    "numero_controle_pncp": o.id_externo,
                    "source_id": o.id_externo,
                    "orgao_nome": o.orgao,
                    "orgao_cnpj": o.orgao_cnpj,
                    "municipio": o.municipio,
                    "uf": o.uf,
                    "objeto": o.objeto,
                    "modalidade": o.modalidade,
                    "valor_estimado": o.valor_estimado if o.valor_estimado is not None else "",
                    "data_publicacao": o.data_publicacao,
                    "data_abertura": o.data_abertura,
                    "data_encerramento": o.data_encerramento,
                    "link_edital": o.url,
                    "source_url": o.url,
                    "status_canonico": o.status_fonte or "open",
                }
            )
    return path


def load_all_lake_observations(
    conn: Any,
    *,
    as_of: date | None = None,
    ciga_path: Path | None = None,
    sc_path: Path | None = None,
    ciga_lookback_days: int = 45,
    snapshot_page_size: int = DEFAULT_SNAPSHOT_PAGE_SIZE,
    memory_budget_bytes: int | None = None,
    auto_discover_files: bool = True,
    opportunity_lineage: OpportunityLineageSelection | None = None,
    collection_isolated: bool = False,
) -> tuple[list[SourceObservation], dict[str, Any]]:
    """Combine lake + optional file artifacts into one observation list."""
    as_of = as_of or date.today()
    meta: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "sources_loaded": {},
        "file_artifacts": {},
        "snapshots": {},
    }
    rows: list[SourceObservation] = []
    effective_memory_budget = memory_budget_bytes or _memory_budget_bytes()

    opp, opp_snapshot = load_opportunity_intel_snapshot(
        conn,
        page_size=snapshot_page_size,
        memory_budget_bytes=effective_memory_budget,
        lineage=opportunity_lineage,
    )
    rows.extend(opp)
    meta["sources_loaded"]["opportunity_intel"] = len(opp)
    meta["snapshots"]["opportunity_intel"] = opp_snapshot
    if opportunity_lineage is not None:
        persisted = (
            opportunity_lineage.expected_records
            if opportunity_lineage.mode == "persisted"
            else 0
        )
        reused = (
            opportunity_lineage.expected_records
            if opportunity_lineage.mode == "reused"
            else 0
        )
        meta["lineage_reconciliation"] = {
            "collection_id": opportunity_lineage.collection_id,
            "selected_source_run_id": opportunity_lineage.source_run_id,
            "persisted_records": persisted,
            "reused_records": reused,
            "expected_total": persisted + reused,
            "loaded_total": len(opp),
            "exact": len(opp) == persisted + reused,
            "reuse_proof": (
                opp_snapshot.get("lineage")
                if opportunity_lineage.mode == "reused"
                else None
            ),
        }

    if collection_isolated:
        acts, acts_snapshot = [], {
            "source": "official_acts",
            "eligible_count": 0,
            "rows_read": 0,
            "complete": True,
            "excluded": "no selected collection lineage",
            "presentation_truncated": False,
        }
        auto_discover_files = False
    else:
        acts, acts_snapshot = load_official_acts_snapshot(
            conn,
            lookback_days=ciga_lookback_days,
            page_size=snapshot_page_size,
            memory_budget_bytes=effective_memory_budget,
        )
    rows.extend(acts)
    meta["sources_loaded"]["official_acts"] = len(acts)
    meta["snapshots"]["official_acts"] = acts_snapshot

    if ciga_path is None and auto_discover_files:
        ciga_path = discover_ciga_jsonl()
    if ciga_path and ciga_path.is_file():
        ciga_rows = load_ciga_observations(ciga_path, as_of, ciga_lookback_days)
        rows.extend(ciga_rows)
        meta["sources_loaded"]["ciga_file"] = len(ciga_rows)
        meta["file_artifacts"]["ciga"] = str(ciga_path)
        meta["snapshots"]["ciga_file"] = {
            "eligible_count": len(ciga_rows),
            "rows_read": len(ciga_rows),
            "complete": True,
            "presentation_truncated": False,
            "estimated_memory_bytes": _estimate_observation_memory(ciga_rows),
        }
    else:
        meta["file_artifacts"]["ciga"] = None

    if sc_path is None and auto_discover_files:
        sc_path = discover_sc_compras_jsonl()
    if sc_path and sc_path.is_file():
        sc_rows = load_sc_compras_observations(sc_path, as_of)
        rows.extend(sc_rows)
        meta["sources_loaded"]["sc_compras_file"] = len(sc_rows)
        meta["file_artifacts"]["sc_compras"] = str(sc_path)
        meta["snapshots"]["sc_compras_file"] = {
            "eligible_count": len(sc_rows),
            "rows_read": len(sc_rows),
            "complete": True,
            "presentation_truncated": False,
            "estimated_memory_bytes": _estimate_observation_memory(sc_rows),
        }
    else:
        meta["file_artifacts"]["sc_compras"] = None

    meta["total_observations"] = len(rows)
    meta["eligible_observations"] = sum(
        int(snapshot.get("eligible_count") or 0)
        for snapshot in meta["snapshots"].values()
    )
    meta["reconciled"] = meta["total_observations"] == meta["eligible_observations"]
    if not meta["reconciled"]:
        raise SnapshotReconciliationError(
            f"combined rows={meta['total_observations']} != eligible={meta['eligible_observations']}"
        )
    meta["estimated_memory_bytes"] = sum(
        int(snapshot.get("estimated_memory_bytes") or 0)
        for snapshot in meta["snapshots"].values()
    )
    meta["memory_budget_bytes"] = effective_memory_budget
    meta["within_memory_budget"] = (
        meta["estimated_memory_bytes"] <= effective_memory_budget
    )
    if not meta["within_memory_budget"]:
        raise SnapshotReconciliationError(
            f"combined estimated memory={meta['estimated_memory_bytes']} exceeds "
            f"budget={effective_memory_budget}"
        )
    by_fonte: dict[str, int] = {}
    for o in rows:
        by_fonte[o.fonte] = by_fonte.get(o.fonte, 0) + 1
    meta["by_fonte"] = by_fonte
    return rows, meta


__all__ = [
    "discover_ciga_jsonl",
    "discover_sc_compras_jsonl",
    "export_pncp_csv",
    "load_all_lake_observations",
    "load_official_acts_observations",
    "load_official_acts_snapshot",
    "load_opportunity_intel_observations",
    "load_opportunity_intel_snapshot",
    "LineageSelectionError",
    "OpportunityLineageSelection",
    "SnapshotReconciliationError",
]
