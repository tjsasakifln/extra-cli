"""Logical change-data-capture for target-fit dirty queue.

Detects CNPJ-root groups affected by datalake contract changes without full
national scans. Watermark-driven, cheap polling.

ETL never waits on this path.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.confenge_target_fit.company_key import (
    company_key_from_raiz,
    cnpj_raiz_from_cnpj14,
    digits_only,
    is_consortium_contract,
)
from scripts.confenge_target_fit.store import enqueue_dirty, get_control, set_control


def _utcnow() -> datetime:
    return datetime.now(UTC)


def datalake_max_ingested_at(conn: Any) -> datetime | None:
    """Best-effort max change clock on supplier contracts."""
    with conn.cursor() as cur:
        # Prefer ingested_at; fall back to nothing if column missing
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='pncp_supplier_contracts'
            """
        )
        cols = {r["column_name"] for r in (cur.fetchall() or [])}
        if "ingested_at" in cols:
            cur.execute("SELECT MAX(ingested_at) AS m FROM pncp_supplier_contracts")
            row = cur.fetchone()
            return row["m"] if row else None
        if "updated_at" in cols:
            cur.execute("SELECT MAX(updated_at) AS m FROM pncp_supplier_contracts")
            row = cur.fetchone()
            return row["m"] if row else None
    return None


def watermark_str(ts: datetime | None) -> str:
    if ts is None:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.isoformat().replace("+00:00", "Z")


def _cnpj_column(cols: set[str]) -> str | None:
    for c in ("fornecedor_cnpj", "ni_fornecedor"):
        if c in cols:
            return c
    return None


def _ts_column(cols: set[str]) -> str | None:
    for c in ("ingested_at", "updated_at"):
        if c in cols:
            return c
    return None


def detect_dirty_companies(
    conn: Any,
    *,
    since: datetime | None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Return unique company roots with change reasons since watermark.

    SQL aggregates at CNPJ root to avoid millions of row-level events.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='pncp_supplier_contracts'
            """
        )
        cols = {r["column_name"] for r in (cur.fetchall() or [])}
        cnpj_col = _cnpj_column(cols)
        ts_col = _ts_column(cols)
        if not cnpj_col:
            return []

        # Build SELECT with available columns only
        id_expr = "contrato_id" if "contrato_id" in cols else (
            "id::text" if "id" in cols else "NULL"
        )
        obj_expr = "objeto_contrato" if "objeto_contrato" in cols else "NULL"
        nome_expr = (
            "fornecedor_nome"
            if "fornecedor_nome" in cols
            else ("nome_fornecedor" if "nome_fornecedor" in cols else "NULL")
        )
        ts_expr = ts_col if ts_col else "NULL::timestamptz"

        where = f"WHERE {cnpj_col} IS NOT NULL AND length(regexp_replace({cnpj_col}, '\\D', '', 'g')) >= 8"
        params: list[Any] = []
        if since is not None and ts_col:
            where += f" AND {ts_col} > %s"
            params.append(since)

        # Keyset-safe aggregate: distinct roots ordered by max ts
        sql = f"""
            SELECT
                left(regexp_replace({cnpj_col}, '\\D', '', 'g'), 8) AS cnpj_raiz,
                MAX({ts_expr}) AS source_max_updated_at,
                COUNT(*)::int AS change_count,
                MAX({id_expr}) AS sample_source_id,
                MAX({obj_expr}) AS sample_objeto,
                MAX({nome_expr}) AS sample_nome
            FROM pncp_supplier_contracts
            {where}
            GROUP BY left(regexp_replace({cnpj_col}, '\\D', '', 'g'), 8)
            ORDER BY MAX({ts_expr}) DESC NULLS LAST
            LIMIT %s
        """
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall() or []

    out: list[dict[str, Any]] = []
    for r in rows:
        raiz = digits_only(r["cnpj_raiz"])[:8]
        if len(raiz) != 8 or raiz == "00000000":
            continue
        sample = {
            "objeto_contrato": r.get("sample_objeto"),
            "fornecedor_nome": r.get("sample_nome"),
        }
        reason = "contract_changed"
        if is_consortium_contract(sample):
            reason = "consortium_contract_changed"
        out.append(
            {
                "cnpj_raiz": raiz,
                "company_key": company_key_from_raiz(raiz),
                "reason": reason,
                "source_entity": "pncp_supplier_contracts",
                "source_id": r.get("sample_source_id"),
                "source_updated_at": r.get("source_max_updated_at"),
                "change_count": int(r.get("change_count") or 0),
            }
        )
    return out


def priority_for_reason(reason: str, *, in_activation: bool = False) -> int:
    if in_activation:
        return 95
    if reason in {"manual_requeue", "version_bump"}:
        return 90
    if reason.startswith("consortium"):
        return 70
    if reason in {"contract_changed", "new_contract", "contract_status_changed"}:
        return 60
    if reason == "reconcile_drift":
        return 40
    if reason == "version_backfill":
        return 30
    return 50


def run_cdc_enqueue(
    conn: Any,
    *,
    lookback_minutes: int = 180,
    max_companies: int = 5000,
    force_since: datetime | None = None,
) -> dict[str, Any]:
    """Detect dirty companies and enqueue durable work items.

    Advances cdc_watermark only after successful enqueue of the cycle.
    """
    ctrl = get_control(conn, "cdc_watermark")
    prev_wm = ctrl.get("watermark") or ""
    since: datetime | None = force_since
    if since is None and prev_wm:
        try:
            since = datetime.fromisoformat(prev_wm.replace("Z", "+00:00"))
        except ValueError:
            since = _utcnow() - timedelta(minutes=lookback_minutes)
    if since is None:
        since = _utcnow() - timedelta(minutes=lookback_minutes)

    companies = detect_dirty_companies(conn, since=since, limit=max_companies)
    max_ts = datalake_max_ingested_at(conn)
    wm = watermark_str(max_ts)

    enqueued = 0
    skipped = 0
    for c in companies:
        # Idempotency: company + source watermark + reason family
        raw_key = f"{c['company_key']}|{wm}|{c['reason']}"
        idem = "cdc:" + hashlib.sha256(raw_key.encode()).hexdigest()[:32]
        ok = enqueue_dirty(
            conn,
            company_key=c["company_key"],
            cnpj_raiz=c["cnpj_raiz"],
            reason=c["reason"],
            source_entity=c["source_entity"],
            source_id=str(c["source_id"]) if c.get("source_id") is not None else None,
            source_updated_at=c.get("source_updated_at"),
            source_watermark=wm,
            priority=priority_for_reason(c["reason"]),
            idempotency_key=idem,
        )
        if ok:
            enqueued += 1
        else:
            skipped += 1

    set_control(
        conn,
        "cdc_watermark",
        {
            "watermark": wm,
            "observed_at": _utcnow().isoformat(),
            "previous_watermark": prev_wm,
            "companies_seen": len(companies),
            "enqueued": enqueued,
        },
    )
    return {
        "since": since.isoformat() if since else None,
        "watermark": wm,
        "companies_seen": len(companies),
        "enqueued": enqueued,
        "skipped_idempotent": skipped,
    }


def enqueue_version_backfill(
    conn: Any,
    *,
    current_version: str,
    limit: int = 200,
    priority_classes: tuple[str, ...] = (
        "TARGET_CONFIRMED",
        "TARGET_PROBABLE_RESEARCH",
        "TARGET_OUT_OF_SCOPE",
    ),
) -> int:
    """Controlled backfill when classifier version changes — never a 48k burst."""
    from scripts.confenge_target_fit.store import list_stale_versions

    stale = list_stale_versions(conn, current_version=current_version, limit=limit)
    # Re-sort by recommended priority
    rank = {c: i for i, c in enumerate(priority_classes)}
    stale.sort(key=lambda r: rank.get(r.get("target_fit_class") or "", 99))

    n = 0
    for row in stale:
        ck = row["company_key"]
        raiz = str(row["cnpj_raiz"])
        idem = f"version:{current_version}:{ck}"
        if enqueue_dirty(
            conn,
            company_key=ck,
            cnpj_raiz=raiz,
            reason="version_backfill",
            source_entity="classifier",
            source_id=current_version,
            source_updated_at=_utcnow(),
            source_watermark=row.get("source_watermark") or "",
            priority=priority_for_reason("version_backfill"),
            idempotency_key=idem,
        ):
            n += 1
        # Mark operational status
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE confenge_company_target_fit_current
                SET operational_status = 'recompute_required',
                    updated_at = now()
                WHERE company_key = %s
                """,
                (ck,),
            )
    return n


def company_from_any_cnpj(cnpj: str) -> tuple[str, str]:
    raiz = cnpj_raiz_from_cnpj14(cnpj)
    if not raiz:
        raise ValueError(f"invalid cnpj: {cnpj}")
    return company_key_from_raiz(raiz), raiz
