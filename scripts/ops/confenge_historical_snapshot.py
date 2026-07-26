#!/usr/bin/env python3
"""Build and verify CONFENGE historical contract snapshots (≥365d preferred ≥730d).

Source: canonical local datalake (pncp_supplier_contracts). Copies ALL contracts
in the observation window (active + closed), applies explicit status normalization,
and writes reconciliation artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.dbutil import connect, fetch_all  # noqa: E402
from scripts.ops.confenge_contract_status import (  # noqa: E402
    lifecycle_gate_ok,
    normalize_contract_status,
    reconcile_status_counts,
)

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
DEFAULT_SOURCE_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/pncp_datalake"
DEFAULT_TARGET_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/confenge_commercial"
MIN_DAYS = 365
PREFERRED_DAYS = 730


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_target_schema(conn: Any) -> None:
    """Create commercial snapshot table with status columns (idempotent)."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS public.pncp_supplier_contracts (
            id                  BIGSERIAL PRIMARY KEY,
            contrato_id         TEXT UNIQUE,
            orgao_cnpj          TEXT,
            orgao_nome          TEXT,
            fornecedor_cnpj     TEXT,
            fornecedor_nome     TEXT,
            objeto_contrato     TEXT,
            valor_total         NUMERIC(18,2),
            data_inicio         DATE,
            data_fim            DATE,
            data_publicacao     DATE,
            uf                  TEXT,
            municipio           TEXT,
            source              TEXT NOT NULL DEFAULT 'pncp',
            source_id           TEXT,
            ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_active           BOOLEAN,
            source_status       TEXT,
            normalized_status   TEXT,
            status_reason       TEXT,
            status_source       TEXT,
            status_observed_at  TIMESTAMPTZ
        );
        """
    )
    # Add columns if table pre-existed without them
    for col, typ in (
        ("is_active", "BOOLEAN"),
        ("source_status", "TEXT"),
        ("normalized_status", "TEXT"),
        ("status_reason", "TEXT"),
        ("status_source", "TEXT"),
        ("status_observed_at", "TIMESTAMPTZ"),
        ("municipio", "TEXT"),
    ):
        cur.execute(
            f"""
            DO $$ BEGIN
              ALTER TABLE public.pncp_supplier_contracts ADD COLUMN IF NOT EXISTS {col} {typ};
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
            """
        )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_psc_hist_forn ON public.pncp_supplier_contracts "
        "(fornecedor_cnpj, data_publicacao DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_psc_hist_status ON public.pncp_supplier_contracts "
        "(normalized_status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_psc_hist_active ON public.pncp_supplier_contracts "
        "(is_active)"
    )
    conn.commit()


def _window_bounds(source_conn: Any, preferred_days: int) -> tuple[date, date, int]:
    rows = fetch_all(
        source_conn,
        "SELECT MIN(data_publicacao)::date AS mn, MAX(data_publicacao)::date AS mx "
        "FROM public.pncp_supplier_contracts WHERE data_publicacao IS NOT NULL",
    )
    if not rows or rows[0]["mn"] is None:
        raise SystemExit("source has no contracts with data_publicacao")
    mn = rows[0]["mn"]
    mx = rows[0]["mx"]
    if isinstance(mn, datetime):
        mn = mn.date()
    if isinstance(mx, datetime):
        mx = mx.date()
    span = (mx - mn).days
    # Prefer last preferred_days if available; otherwise full span
    if span >= preferred_days:
        start = mx - timedelta(days=preferred_days)
        if start < mn:
            start = mn
    else:
        start = mn
    days = (mx - start).days
    return start, mx, days


def build_historical_snapshot(
    *,
    source_dsn: str,
    target_dsn: str,
    preferred_days: int = PREFERRED_DAYS,
    min_days: int = MIN_DAYS,
    as_of: date | None = None,
) -> dict[str, Any]:
    source = connect(source_dsn)
    target = connect(target_dsn)
    try:
        start, end, days = _window_bounds(source, preferred_days)
        as_of = as_of or end
        _ensure_target_schema(target)

        # Clear target table for rebuild (snapshot rebuild is intentional)
        cur = target.cursor()
        cur.execute("SET LOCAL app.allow_snapshot_mutation = 'on'")
        cur.execute("TRUNCATE public.pncp_supplier_contracts RESTART IDENTITY")
        target.commit()

        src_rows = fetch_all(
            source,
            """
            SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
                   objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
                   uf, municipio, source, source_id, ingested_at
            FROM public.pncp_supplier_contracts
            WHERE data_publicacao IS NOT NULL
              AND data_publicacao::date >= %s
              AND data_publicacao::date <= %s
            ORDER BY data_publicacao, contrato_id
            """,
            (start, end),
        )

        insert_sql = """
            INSERT INTO public.pncp_supplier_contracts (
              contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
              objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
              uf, municipio, source, source_id, ingested_at,
              is_active, source_status, normalized_status, status_reason,
              status_source, status_observed_at
            ) VALUES (
              %(contrato_id)s, %(orgao_cnpj)s, %(orgao_nome)s, %(fornecedor_cnpj)s,
              %(fornecedor_nome)s, %(objeto_contrato)s, %(valor_total)s, %(data_inicio)s,
              %(data_fim)s, %(data_publicacao)s, %(uf)s, %(municipio)s, %(source)s,
              %(source_id)s, %(ingested_at)s, %(is_active)s, %(source_status)s,
              %(normalized_status)s, %(status_reason)s, %(status_source)s,
              %(status_observed_at)s
            )
            ON CONFLICT (contrato_id) DO UPDATE SET
              is_active = EXCLUDED.is_active,
              source_status = EXCLUDED.source_status,
              normalized_status = EXCLUDED.normalized_status,
              status_reason = EXCLUDED.status_reason,
              status_source = EXCLUDED.status_source,
              status_observed_at = EXCLUDED.status_observed_at
        """
        normalized_rows: list[dict[str, Any]] = []
        cur = target.cursor()
        cur.execute("SET LOCAL app.allow_snapshot_mutation = 'on'")
        batch = 0
        for r in src_rows:
            row = dict(r)
            st = normalize_contract_status(row, as_of=as_of, allow_data_fim_inference=True)
            payload = {
                "contrato_id": row.get("contrato_id"),
                "orgao_cnpj": row.get("orgao_cnpj"),
                "orgao_nome": row.get("orgao_nome"),
                "fornecedor_cnpj": row.get("fornecedor_cnpj"),
                "fornecedor_nome": row.get("fornecedor_nome"),
                "objeto_contrato": row.get("objeto_contrato"),
                "valor_total": row.get("valor_total"),
                "data_inicio": row.get("data_inicio"),
                "data_fim": row.get("data_fim"),
                "data_publicacao": row.get("data_publicacao"),
                "uf": row.get("uf"),
                "municipio": row.get("municipio"),
                "source": row.get("source") or "pncp",
                "source_id": row.get("source_id"),
                "ingested_at": row.get("ingested_at") or datetime.now(UTC),
                "is_active": st["is_active"],
                "source_status": st.get("source_status"),
                "normalized_status": st["normalized_status"],
                "status_reason": st["status_reason"],
                "status_source": st["status_source"],
                "status_observed_at": st["status_observed_at"],
            }
            cur.execute(insert_sql, payload)
            normalized_rows.append(
                {
                    "normalized_status": st["normalized_status"],
                    "is_active": st["is_active"],
                    "status_reason": st["status_reason"],
                }
            )
            batch += 1
            if batch % 2000 == 0:
                target.commit()
                cur.execute("SET LOCAL app.allow_snapshot_mutation = 'on'")
        target.commit()

        recon = reconcile_status_counts(normalized_rows)
        life = lifecycle_gate_ok(recon)
        suppliers = fetch_all(
            target,
            """
            SELECT COUNT(DISTINCT right(regexp_replace(coalesce(fornecedor_cnpj,''), '\\D', '', 'g'), 14))::int AS n
            FROM public.pncp_supplier_contracts
            WHERE length(regexp_replace(coalesce(fornecedor_cnpj,''), '\\D', '', 'g')) >= 14
            """,
        )
        supplier_count = int(suppliers[0]["n"]) if suppliers else 0

        # reason distribution for auditability
        reason_counts: dict[str, int] = {}
        for r in normalized_rows:
            k = r.get("status_reason") or "none"
            reason_counts[k] = reason_counts.get(k, 0) + 1

        window_ok = days >= min_days
        report = {
            "ok": bool(window_ok and life["ok"]),
            "status": (
                "PASS"
                if window_ok and life["ok"]
                else (
                    "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW"
                    if not window_ok
                    else life.get("block") or "FAIL"
                )
            ),
            "built_at": utc_now(),
            "source_dsn_hash": hashlib.sha256(source_dsn.encode()).hexdigest()[:16],
            "target_dsn_hash": hashlib.sha256(target_dsn.encode()).hexdigest()[:16],
            "snapshot_min_date": start.isoformat(),
            "snapshot_max_date": end.isoformat(),
            "snapshot_observation_days": days,
            "minimum_observation_window_days": min_days,
            "preferred_observation_window_days": preferred_days,
            "as_of": as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of),
            "supplier_count": supplier_count,
            "status_reason_distribution": reason_counts,
            "normalization_rules": [
                "source_feed_field first",
                "data_fim_before_as_of_v1 → COMPLETED",
                "data_fim_null_or_future_v1 → ACTIVE",
                "never invent CANCELLED/TERMINATED without source token",
            ],
            **recon,
            **life,
            "source_row_count": len(src_rows),
            "note": (
                "Historical snapshot includes ALL contracts in window (not active-only). "
                "Status classes derived with explicit rules; CLOSED rows are not fabricated."
            ),
        }
        ART.mkdir(parents=True, exist_ok=True)
        (ART / "historical-snapshot-build.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        # Also refresh historical-window-gate artifact when build succeeds window-wise
        window_report = {
            "snapshot_min_date": start.isoformat(),
            "snapshot_max_date": end.isoformat(),
            "snapshot_observation_days": days,
            "strong_observable": days >= 180,
            "strong_status": None if days >= 180 else "STRONG_NOT_OBSERVABLE_IN_CURRENT_WINDOW",
            "minimum_observation_window_days": min_days,
            "strong_min_time_span_days": 180,
            "block": None if window_ok else "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW",
            "ok": window_ok,
            "status": "PASS" if window_ok else "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW",
            "strong_not_observable_declared": days < 180,
            "source": "historical_snapshot_build",
        }
        (ART / "historical-window-gate.json").write_text(
            json.dumps(window_report, indent=2) + "\n", encoding="utf-8"
        )
        return report
    finally:
        source.close()
        target.close()


def verify_historical_snapshot(*, target_dsn: str, min_days: int = MIN_DAYS) -> dict[str, Any]:
    conn = connect(target_dsn)
    try:
        rows = fetch_all(
            conn,
            """
            SELECT MIN(data_publicacao)::text AS mn, MAX(data_publicacao)::text AS mx,
                   COUNT(*)::int AS n
            FROM public.pncp_supplier_contracts
            """,
        )
        status_rows = fetch_all(
            conn,
            """
            SELECT coalesce(normalized_status, 'UNKNOWN') AS st, COUNT(*)::int AS n
            FROM public.pncp_supplier_contracts
            GROUP BY 1
            """,
        )
        by = {str(r["st"]).upper(): int(r["n"]) for r in status_rows}
        recon = {
            "snapshot_total_contracts": int(rows[0]["n"]) if rows else 0,
            "snapshot_active_contracts": by.get("ACTIVE", 0),
            "snapshot_completed_contracts": by.get("COMPLETED", 0),
            "snapshot_cancelled_contracts": by.get("CANCELLED", 0),
            "snapshot_terminated_contracts": by.get("TERMINATED", 0),
            "snapshot_suspended_contracts": by.get("SUSPENDED", 0),
            "snapshot_unknown_status_contracts": by.get("UNKNOWN", 0),
        }
        recon["status_sum"] = sum(
            recon[k]
            for k in (
                "snapshot_active_contracts",
                "snapshot_completed_contracts",
                "snapshot_cancelled_contracts",
                "snapshot_terminated_contracts",
                "snapshot_suspended_contracts",
                "snapshot_unknown_status_contracts",
            )
        )
        recon["status_sum_matches_total"] = (
            recon["status_sum"] == recon["snapshot_total_contracts"]
        )
        life = lifecycle_gate_ok(recon)
        mn = rows[0]["mn"] if rows else None
        mx = rows[0]["mx"] if rows else None
        days = None
        if mn and mx:
            d0 = date.fromisoformat(str(mn)[:10])
            d1 = date.fromisoformat(str(mx)[:10])
            days = (d1 - d0).days
        window_ok = days is not None and days >= min_days
        suppliers = fetch_all(
            conn,
            """
            SELECT COUNT(DISTINCT right(regexp_replace(coalesce(fornecedor_cnpj,''), '\\D', '', 'g'), 14))::int AS n
            FROM public.pncp_supplier_contracts
            """,
        )
        report = {
            "ok": bool(window_ok and life["ok"] and recon["status_sum_matches_total"]),
            "status": (
                "PASS"
                if window_ok and life["ok"]
                else (
                    "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW"
                    if not window_ok
                    else life.get("block") or "FAIL"
                )
            ),
            "snapshot_min_date": mn,
            "snapshot_max_date": mx,
            "snapshot_observation_days": days,
            "minimum_observation_window_days": min_days,
            "supplier_count": int(suppliers[0]["n"]) if suppliers else 0,
            "status_distribution": by,
            **recon,
            **life,
            "verified_at": utc_now(),
            "method": "live_db_status_recount",
        }
        (ART / "historical-snapshot-verify.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
        (ART / "contract-status-reconciliation.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
        return report
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--source-dsn", default=os.environ.get("CONFENGE_SOURCE_DSN", DEFAULT_SOURCE_DSN))
    b.add_argument("--target-dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN", DEFAULT_TARGET_DSN))
    b.add_argument("--preferred-days", type=int, default=PREFERRED_DAYS)
    b.add_argument("--min-days", type=int, default=MIN_DAYS)
    v = sub.add_parser("verify")
    v.add_argument("--target-dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN", DEFAULT_TARGET_DSN))
    v.add_argument("--min-days", type=int, default=MIN_DAYS)
    r = sub.add_parser("reconcile")
    r.add_argument("--target-dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN", DEFAULT_TARGET_DSN))
    args = ap.parse_args(argv)
    if args.cmd == "build":
        rep = build_historical_snapshot(
            source_dsn=args.source_dsn,
            target_dsn=args.target_dsn,
            preferred_days=args.preferred_days,
            min_days=args.min_days,
        )
        print(json.dumps(rep, indent=2, default=str))
        return 0 if rep.get("ok") else 2
    if args.cmd in {"verify", "reconcile"}:
        rep = verify_historical_snapshot(target_dsn=args.target_dsn, min_days=args.min_days)
        print(json.dumps(rep, indent=2, default=str))
        return 0 if rep.get("ok") else 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
