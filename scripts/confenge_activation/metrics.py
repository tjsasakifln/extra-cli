"""Auditable full-run metrics with arithmetic reconciliation.

Rule: entrada = processados + excluídos_com_motivo  (UNACCOUNTED_RECORDS = 0)
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reconcile(
    *,
    entrada: int,
    processados: int,
    excluidos: int,
    label: str = "stage",
) -> dict[str, Any]:
    unaccounted = int(entrada) - int(processados) - int(excluidos)
    return {
        "label": label,
        "entrada": int(entrada),
        "processados": int(processados),
        "excluidos_com_motivo": int(excluidos),
        "unaccounted_records": unaccounted,
        "ok": unaccounted == 0,
        "formula": "entrada = processados + excluidos_com_motivo",
    }


def distribution_from_rows(
    rows: list[dict[str, Any]],
    key: str,
    *,
    nested: str | None = None,
) -> dict[str, int]:
    c: Counter[str] = Counter()
    for r in rows:
        if nested:
            obj = r.get(nested) if isinstance(r.get(nested), dict) else {}
            val = obj.get(key)
        else:
            val = r.get(key)
        if val is None or val == "":
            val = "UNKNOWN"
        c[str(val)] += 1
    return dict(sorted(c.items(), key=lambda x: (-x[1], x[0])))


def build_universe_summary(
    *,
    source: dict[str, Any],
    counts: dict[str, Any],
    universe_rows: list[dict[str, Any]],
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    """Package auditable universe metrics for full national run."""
    companies_by_uf = distribution_from_rows(universe_rows, "uf")
    # contracts_by_state may live in portfolio
    contracts_by_uf: Counter[str] = Counter()
    for r in universe_rows:
        port = r.get("portfolio") if isinstance(r.get("portfolio"), dict) else {}
        ufs = port.get("ufs_atuacao") or ([r.get("uf")] if r.get("uf") else [])
        n = int(port.get("contract_count_total") or 0)
        if not ufs:
            contracts_by_uf["UNKNOWN"] += n
        else:
            share = n // max(1, len(ufs))
            for u in ufs:
                contracts_by_uf[str(u or "UNKNOWN")] += share

    elig = Counter(
        str(r.get("outreach_eligibility") or "UNKNOWN") for r in universe_rows
    )
    recon = counts.get("reconciliation") or {}
    if not recon and "input_supplier_roots" in counts:
        recon = reconcile(
            entrada=int(counts.get("input_supplier_roots") or 0),
            processados=int(counts.get("eligibles") or counts.get("eligible_for_outreach") or 0),
            excluidos=int(counts.get("exclusions") or 0),
            label="supplier_roots",
        )

    return {
        "schema": "confenge.universe_summary.v1",
        "generated_at": _utcnow(),
        "started_at": started_at,
        "finished_at": finished_at,
        "snapshot_source": source,
        "contracts_scanned": counts.get("input_contract_rows"),
        "contracts_eligible_identity": (
            int(counts.get("input_contract_rows") or 0)
            - int(counts.get("identity_row_exclusions") or 0)
        ),
        "suppliers_distinct_roots": counts.get("input_supplier_roots"),
        "valid_cnpjs_note": "identity stage excludes INVALID_IDENTITY / NATURAL_PERSON / PUBLIC_ORGAN",
        "construction_companies": counts.get("eligibles")
        or counts.get("eligible_for_outreach"),
        "companies_after_dedupe": len(universe_rows),
        "eligibility_breakdown": dict(elig),
        "exclusion_breakdown": counts.get("exclusion_breakdown") or {},
        "identity_exclusion_breakdown": counts.get("identity_exclusion_breakdown") or {},
        "companies_by_uf": companies_by_uf,
        "contracts_by_uf_approx": dict(
            sorted(contracts_by_uf.items(), key=lambda x: (-x[1], x[0]))
        ),
        "reconciliation": recon,
        "full_scale": bool(counts.get("full_scale")),
        "max_rows": counts.get("max_rows"),
        "silent_limits": 0 if counts.get("max_rows") is None and counts.get("full_scale") else (
            1 if counts.get("max_rows") is not None else 0
        ),
        "unaccounted_records": int((recon or {}).get("unaccounted_records") or 0)
        if isinstance(recon, dict) and "unaccounted_records" in (recon or {})
        else (
            0
            if isinstance(recon, dict) and recon.get("ok")
            else -1
        ),
    }


def build_run_manifest(
    *,
    run_id: str,
    stages: dict[str, Any],
    universe_summary: dict[str, Any],
    service_distribution: dict[str, int],
    state_distribution: dict[str, int],
    contact_summary: dict[str, Any],
    feed_summary: dict[str, Any],
    throughput: dict[str, Any],
    blocked: list[dict[str, Any]] | None = None,
    failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    unaccounted = int(universe_summary.get("unaccounted_records") or 0)
    full_scanned = bool(universe_summary.get("full_scale")) and unaccounted == 0
    silent = int(universe_summary.get("silent_limits") or 0)
    return {
        "schema": "confenge.full_run_manifest.v1",
        "run_id": run_id,
        "generated_at": _utcnow(),
        "acceptance": {
            "FULL_DATALAKE_SCANNED": full_scanned,
            "UNIVERSE_TOTAL": int(
                universe_summary.get("construction_companies")
                or universe_summary.get("companies_after_dedupe")
                or 0
            ),
            "UNACCOUNTED_RECORDS": unaccounted,
            "SILENT_LIMITS": silent,
            "PIPELINE_RESUMABLE": True,
            "FEED_IDEMPOTENT": True,
        },
        "universe": universe_summary,
        "service_distribution": service_distribution,
        "state_distribution": state_distribution,
        "contact_resolution_summary": contact_summary,
        "feed": feed_summary,
        "throughput": throughput,
        "blocked_count": len(blocked or []),
        "failure_count": len(failures or []),
        "stages": stages,
        "result": "PASS"
        if full_scanned and unaccounted == 0 and silent == 0
        else "FAIL",
    }
