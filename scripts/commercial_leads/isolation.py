"""Fail-closed isolation for CONFENGE commercial campaign.

Supports dual DSN:
  CONFENGE_COMMERCIAL_SOURCE_DSN — read-only source of contracts
  CONFENGE_COMMERCIAL_STATE_DSN  — ledger / migrations

If source and state are the same physical DB with a restored snapshot, mode must
be RESTORED_SNAPSHOT_SINGLE_DB (never claim source_state_separated=true).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.commercial_leads import (
    CAMPAIGN_ID,
    SOURCE_STATE_RESTORED,
    SOURCE_STATE_SEPARATED,
)

FORBIDDEN_HOST_MARKERS = (
    "ec-prod",
    "netcup",
    "vps",
    "production",
    "prod.extra",
    "extra-prod",
    "extra_prod",
    "/opt/extra-consultoria",
)

FORBIDDEN_PATH_MARKERS = (
    "/opt/extra-consultoria",
    "soak",
    "nfs",
    "HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01",
    "OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01",
    "STRATIFIED-RECALL-SOURCE-RESILIENCE-01",
)

ALLOWED_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
# Exclusive campaign port preferred; other local campaign ports accepted for tests.
ALLOWED_PORTS = (5441, 5433, 5435, 5436, 5437, 5438, 5439)
FORBIDDEN_PORTS = (5432,)


@dataclass
class IsolationResult:
    ok: bool
    production_touched: bool
    soak_touched: bool
    dsn_masked: str
    host: str | None
    port: int | None
    database: str | None
    reasons: list[str] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)
    source_state_mode: str | None = None
    source_dsn_masked: str | None = None
    state_dsn_masked: str | None = None
    source_read_only_enforced: bool | None = None
    source_state_separated: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "production_touched": self.production_touched,
            "soak_touched": self.soak_touched,
            "dsn_masked": self.dsn_masked,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "reasons": self.reasons,
            "forbidden_hits": self.forbidden_hits,
            "campaign_id": CAMPAIGN_ID,
            "source_state_mode": self.source_state_mode,
            "source_dsn_masked": self.source_dsn_masked,
            "state_dsn_masked": self.state_dsn_masked,
            "source_read_only_enforced": self.source_read_only_enforced,
            "source_state_separated": self.source_state_separated,
        }


def mask_dsn(dsn: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", dsn or "")


def parse_dsn(dsn: str) -> tuple[str | None, int | None, str | None]:
    raw = (dsn or "").strip()
    if not raw:
        return None, None, None
    if "://" not in raw:
        raw = "postgresql://" + raw
    u = urlparse(raw)
    return u.hostname, u.port, (u.path or "").lstrip("/") or None


def assert_isolation(
    dsn: str,
    *,
    out_dir: Path | str | None = None,
    require_allowed_port: bool = True,
) -> IsolationResult:
    host, port, db = parse_dsn(dsn)
    reasons: list[str] = []
    hits: list[str] = []
    masked = mask_dsn(dsn)
    production = False
    soak = False

    if not dsn:
        return IsolationResult(
            ok=False,
            production_touched=False,
            soak_touched=False,
            dsn_masked="",
            host=None,
            port=None,
            database=None,
            reasons=["missing_dsn"],
        )

    hay = f"{dsn} {host or ''} {db or ''}".lower()
    for m in FORBIDDEN_HOST_MARKERS:
        if m.lower() in hay:
            hits.append(f"host_marker:{m}")
            production = True
    if port in FORBIDDEN_PORTS:
        hits.append(f"forbidden_port:{port}")
        production = True
    if host and host not in ALLOWED_LOCAL_HOSTS:
        hits.append(f"non_local_host:{host}")
        production = True
    if require_allowed_port and port is not None and port not in ALLOWED_PORTS:
        hits.append(f"port_not_in_allowlist:{port}")
        reasons.append("port_not_allowed_for_campaign")

    if out_dir is not None:
        p = str(Path(out_dir).resolve()).lower()
        for m in FORBIDDEN_PATH_MARKERS:
            if m.lower() in p:
                hits.append(f"path_marker:{m}")
                if "soak" in m.lower() or "historical-contracts" in m.lower() or "open-tenders" in m.lower():
                    soak = True
                else:
                    production = True

    # Env guard
    for key, val in os.environ.items():
        if not val:
            continue
        low = f"{key}={val}".lower()
        if "ec-prod" in low or "extra_prod" in low:
            # only flag if used as DSN-like
            if "postgres" in low or "dsn" in key.lower() or "@" in val:
                hits.append(f"env:{key}")
                production = True

    ok = not hits and not reasons
    if hits:
        reasons.append("isolation_violation")
    return IsolationResult(
        ok=ok,
        production_touched=production,
        soak_touched=soak,
        dsn_masked=masked,
        host=host,
        port=port,
        database=db,
        reasons=reasons,
        forbidden_hits=hits,
    )


def _normalize_dsn_identity(dsn: str) -> str:
    """Host:port/db identity ignoring credentials for separation detection."""
    host, port, db = parse_dsn(dsn)
    return f"{(host or '').lower()}:{(port or '')}/{(db or '').lower()}"


def assert_source_state_isolation(
    *,
    source_dsn: str,
    state_dsn: str,
    out_dir: Path | str | None = None,
    force_mode: str | None = None,
    enforce_source_readonly: bool = True,
) -> IsolationResult:
    """Validate source/state DSNs and declare honest mode.

    force_mode may be RESTORED_SNAPSHOT_SINGLE_DB when intentionally single DB.
    """
    state_res = assert_isolation(state_dsn, out_dir=out_dir)
    source_res = assert_isolation(source_dsn, out_dir=out_dir)

    reasons = list(state_res.reasons) + [f"source:{r}" for r in source_res.reasons]
    hits = list(state_res.forbidden_hits) + [f"source:{h}" for h in source_res.forbidden_hits]
    production = state_res.production_touched or source_res.production_touched
    soak = state_res.soak_touched or source_res.soak_touched

    same = _normalize_dsn_identity(source_dsn) == _normalize_dsn_identity(state_dsn)
    if force_mode == SOURCE_STATE_SEPARATED:
        if same:
            mode = SOURCE_STATE_RESTORED
            separated = False
            reasons.append("claimed_separated_but_same_dsn")
            hits.append("false_source_state_separation")
        else:
            mode = SOURCE_STATE_SEPARATED
            separated = True
    elif force_mode == SOURCE_STATE_RESTORED or same:
        mode = SOURCE_STATE_RESTORED
        separated = False
        if same and force_mode not in (None, SOURCE_STATE_RESTORED, ""):
            pass
    else:
        mode = SOURCE_STATE_SEPARATED
        separated = True

    source_ro: bool | None = None
    snapshot_write_probe: dict[str, Any] | None = None
    if enforce_source_readonly and source_dsn:
        snapshot_write_probe = probe_snapshot_write_denied(source_dsn)
        source_ro = True if snapshot_write_probe.get("ok") else False
        if source_ro is False:
            reasons.append("source_snapshot_table_writable")
            hits.append("snapshot_write_not_denied")
            if snapshot_write_probe.get("residual_probe_rows"):
                hits.append("residual_probe_rows_left_in_snapshot")
        if snapshot_write_probe.get("select") != "ok":
            reasons.append("source_select_failed")
            hits.append("source_select_failed")

    ok = not hits and state_res.ok and source_res.ok
    if hits and "isolation_violation" not in reasons:
        reasons.append("isolation_violation")

    result = IsolationResult(
        ok=ok,
        production_touched=production,
        soak_touched=soak,
        dsn_masked=state_res.dsn_masked,
        host=state_res.host,
        port=state_res.port,
        database=state_res.database,
        reasons=reasons,
        forbidden_hits=hits,
        source_state_mode=mode,
        source_dsn_masked=mask_dsn(source_dsn),
        state_dsn_masked=mask_dsn(state_dsn),
        source_read_only_enforced=source_ro,
        source_state_separated=separated and mode == SOURCE_STATE_SEPARATED,
    )
    if snapshot_write_probe is not None:
        setattr(result, "snapshot_write_probe", snapshot_write_probe)
    return result


def probe_snapshot_write_denied(dsn: str) -> dict[str, Any]:
    """Prove INSERT/UPDATE/DELETE on snapshot table FAIL without mutation flag.

    Does NOT set session readonly first — tests DB-level protection (trigger/role).
    Returns {ok, insert, update, delete, select, residual_probe_rows}.
    """
    import psycopg2

    out: dict[str, Any] = {
        "ok": False,
        "insert": None,
        "update": None,
        "delete": None,
        "select": None,
        "residual_probe_rows": None,
        "method": "live_mutate_pncp_supplier_contracts_expect_fail",
    }
    probe_id = "confenge-isolation-probe-must-fail"
    try:
        conn = psycopg2.connect(dsn, connect_timeout=10)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"connect:{exc}"
        return out
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # SELECT must work
            try:
                cur.execute(
                    "SELECT COUNT(*)::bigint FROM public.pncp_supplier_contracts"
                )
                out["select"] = "ok"
            except Exception as exc:  # noqa: BLE001
                out["select"] = f"fail:{exc}"

            # INSERT must FAIL
            try:
                cur.execute(
                    """
                    INSERT INTO public.pncp_supplier_contracts (contrato_id)
                    VALUES (%s)
                    """,
                    (probe_id,),
                )
                out["insert"] = "UNEXPECTED_SUCCESS"
            except Exception as exc:  # noqa: BLE001
                out["insert"] = f"denied:{type(exc).__name__}"

            # UPDATE must FAIL (even if no matching row — trigger fires per row;
            # if zero rows updated without trigger, still not a successful mutation)
            try:
                cur.execute(
                    """
                    UPDATE public.pncp_supplier_contracts
                    SET objeto_contrato = objeto_contrato
                    WHERE contrato_id = %s
                    """,
                    (probe_id,),
                )
                # If probe insert failed, UPDATE affects 0 rows — still OK if no exception
                # and no residual probe. Require that a broad write is denied when possible.
                out["update"] = "ok_no_row_or_denied"
            except Exception as exc:  # noqa: BLE001
                out["update"] = f"denied:{type(exc).__name__}"

            # Stronger UPDATE probe: touch a real row must fail via trigger
            try:
                cur.execute(
                    """
                    UPDATE public.pncp_supplier_contracts
                    SET objeto_contrato = coalesce(objeto_contrato, '')
                    WHERE contrato_id IN (
                        SELECT contrato_id FROM public.pncp_supplier_contracts
                        ORDER BY contrato_id NULLS LAST LIMIT 1
                    )
                    """
                )
                out["update_real_row"] = "UNEXPECTED_SUCCESS"
            except Exception as exc:  # noqa: BLE001
                out["update_real_row"] = f"denied:{type(exc).__name__}"

            # DELETE must FAIL
            try:
                cur.execute(
                    """
                    DELETE FROM public.pncp_supplier_contracts
                    WHERE contrato_id IN (
                        SELECT contrato_id FROM public.pncp_supplier_contracts
                        ORDER BY contrato_id NULLS LAST LIMIT 1
                    )
                    """
                )
                out["delete"] = "UNEXPECTED_SUCCESS"
            except Exception as exc:  # noqa: BLE001
                out["delete"] = f"denied:{type(exc).__name__}"

            # residual probes
            cur.execute(
                "SELECT COUNT(*)::int FROM public.pncp_supplier_contracts WHERE contrato_id = %s",
                (probe_id,),
            )
            residual = cur.fetchone()
            out["residual_probe_rows"] = int(residual[0]) if residual else 0

        out["ok"] = (
            out.get("select") == "ok"
            and str(out.get("insert", "")).startswith("denied")
            and str(out.get("update_real_row", "")).startswith("denied")
            and str(out.get("delete", "")).startswith("denied")
            and out.get("residual_probe_rows") == 0
        )
        return out
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _probe_source_read_only(dsn: str) -> bool | None:
    """Return True only if snapshot writes are denied at DB level (not session self-set)."""
    report = probe_snapshot_write_denied(dsn)
    if report.get("select") != "ok":
        return None
    return True if report.get("ok") else False


def open_source_connection(dsn: str) -> Any:
    """Open source DB connection with default_transaction_read_only=on (defense in depth).

    Real immutability of snapshot tables is enforced by DB trigger (migration 064).
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dsn, connect_timeout=30)
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
    conn.cursor_factory = RealDictCursor
    return conn
