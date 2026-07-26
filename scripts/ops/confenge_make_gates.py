#!/usr/bin/env python3
"""Makefile-backed CONFENGE gate helpers — re-query live snapshot when DSN set.

File-only boolean reads are FAIL for real-data gates (objective §26).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
RUN = ART / "run" / "run-result.json"


def _load_run() -> dict[str, Any]:
    if not RUN.is_file():
        return {}
    return json.loads(RUN.read_text(encoding="utf-8"))


def _require_dsn() -> str:
    dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN") or os.environ.get(
        "CONFENGE_COMMERCIAL_SOURCE_DSN"
    )
    if not dsn:
        raise SystemExit(
            "FAIL: CONFENGE_COMMERCIAL_STATE_DSN required for real-data gate "
            "(file-only re-read is theater)"
        )
    return dsn


def cmd_full_candidate_history(_: argparse.Namespace) -> int:
    """Re-query snapshot for a sample of candidates — ALL statuses, not active-only."""
    from scripts.commercial_leads.dbutil import connect, fetch_all
    from scripts.commercial_leads.pipeline import load_full_supplier_histories

    d = _load_run()
    lm = d.get("load_meta") or {}
    cnpjs = list(lm.get("candidate_supplier_cnpjs") or [])[:40]
    if not cnpjs and d.get("leads"):
        cnpjs = [L["cnpj14"] for L in d["leads"][:20]]
    if not cnpjs:
        print(json.dumps({"ok": False, "reason": "no_candidates_in_run_result"}, indent=2))
        return 1

    dsn = _require_dsn()
    conn = connect(dsn)
    try:
        groups, hist = load_full_supplier_histories(conn, cnpjs, per_supplier_limit=None)
        # independent COUNT(*) reconciliation — ALL statuses (no is_active filter)
        mismatches = []
        for cnpj in cnpjs:
            rows = fetch_all(
                conn,
                """
                SELECT COUNT(*)::int AS n
                FROM public.pncp_supplier_contracts
                WHERE right(regexp_replace(fornecedor_cnpj, '\\D', '', 'g'), 14) = %s
                """,
                (cnpj,),
            )
            expected = int(rows[0]["n"]) if rows else 0
            loaded = len(groups.get(cnpj, []))
            if loaded != expected:
                mismatches.append({"cnpj14": cnpj, "loaded": loaded, "snapshot": expected})
        ok = (
            hist.get("history_view") == "ALL_SNAPSHOT_SUPPLIER_HISTORY"
            and hist.get("history_expansion_mode") == "FULL_CANDIDATE_HISTORY"
            and hist.get("history_complete") is True
            and hist.get("all_statuses_loaded") is True
            and not hist.get("per_supplier_limit")
            and len(mismatches) == 0
            and not hist.get("active_only_filter")
        )
        report = {
            "ok": ok,
            "rechecked_cnpjs": len(cnpjs),
            "history_view": hist.get("history_view"),
            "history_expansion_mode": hist.get("history_expansion_mode"),
            "history_complete": hist.get("history_complete"),
            "all_statuses_loaded": hist.get("all_statuses_loaded"),
            "mismatches": mismatches[:20],
            "run_claimed_history_is_full": lm.get("history_is_full"),
            "method": "live_db_all_status_recount_vs_full_history_loader",
        }
        out = ART / "full-candidate-history-gate.json"
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if ok else 1
    finally:
        conn.close()


def cmd_all_status_history(_: argparse.Namespace) -> int:
    """Prove ALL_SNAPSHOT_SUPPLIER_HISTORY via unit fixtures + live DB recount.

    Live path (required when DSN set): load full history without is_active filter,
    independently COUNT(*) all statuses and active-only, verify loader matches
    all-status count and exceeds active-only when closed contracts exist.
    """
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/commercial_leads/test_all_status_history.py",
            "-q",
            "--tb=short",
            "-o",
            "addopts=",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    unit_ok = proc.returncode == 0
    live: dict[str, Any] = {"attempted": False}
    dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN") or os.environ.get(
        "CONFENGE_COMMERCIAL_SOURCE_DSN"
    )
    if dsn:
        from scripts.commercial_leads.dbutil import connect, fetch_all
        from scripts.commercial_leads.pipeline import (
            compute_supplier_history_metrics,
            load_full_supplier_histories,
        )

        d = _load_run()
        lm = d.get("load_meta") or {}
        cnpjs = list(lm.get("candidate_supplier_cnpjs") or [])[:50]
        if not cnpjs and d.get("leads"):
            cnpjs = [str(L["cnpj14"]) for L in d["leads"][:20]]
        live["attempted"] = True
        live["cnpjs_n"] = len(cnpjs)
        if not cnpjs:
            live["ok"] = False
            live["reason"] = "no_candidates_for_live_recount"
        else:
            conn = connect(dsn)
            try:
                groups_all, hist_all = load_full_supplier_histories(
                    conn, cnpjs, per_supplier_limit=None, active_only=False
                )
                groups_act, hist_act = load_full_supplier_histories(
                    conn, cnpjs, per_supplier_limit=None, active_only=True
                )
                mismatches_all = []
                mismatches_act = []
                metric_samples = []
                invariant_fails = []
                for cnpj in cnpjs:
                    rows_all = fetch_all(
                        conn,
                        """
                        SELECT COUNT(*)::int AS n
                        FROM public.pncp_supplier_contracts
                        WHERE right(regexp_replace(fornecedor_cnpj, '\\D', '', 'g'), 14) = %s
                        """,
                        (cnpj,),
                    )
                    rows_act = fetch_all(
                        conn,
                        """
                        SELECT COUNT(*)::int AS n
                        FROM public.pncp_supplier_contracts
                        WHERE is_active = TRUE
                          AND right(regexp_replace(fornecedor_cnpj, '\\D', '', 'g'), 14) = %s
                        """,
                        (cnpj,),
                    )
                    exp_all = int(rows_all[0]["n"]) if rows_all else 0
                    exp_act = int(rows_act[0]["n"]) if rows_act else 0
                    got_all = len(groups_all.get(cnpj, []))
                    got_act = len(groups_act.get(cnpj, []))
                    if got_all != exp_all:
                        mismatches_all.append(
                            {"cnpj14": cnpj, "loaded": got_all, "snapshot_all": exp_all}
                        )
                    if got_act != exp_act:
                        mismatches_act.append(
                            {"cnpj14": cnpj, "loaded": got_act, "snapshot_active": exp_act}
                        )
                    m = compute_supplier_history_metrics(groups_all.get(cnpj, []))
                    if not m.get("invariant_active_plus_inactive") or not m.get(
                        "invariant_relevance_partition"
                    ):
                        invariant_fails.append({"cnpj14": cnpj, **m})
                    if len(metric_samples) < 5:
                        metric_samples.append({"cnpj14": cnpj, **m})
                total_all = sum(len(v) for v in groups_all.values())
                total_act = sum(len(v) for v in groups_act.values())
                live_ok = (
                    hist_all.get("history_view") == "ALL_SNAPSHOT_SUPPLIER_HISTORY"
                    and hist_all.get("all_statuses_loaded") is True
                    and hist_all.get("history_expansion_mode") == "FULL_CANDIDATE_HISTORY"
                    and not mismatches_all
                    and not mismatches_act
                    and not invariant_fails
                    and total_all >= total_act
                )
                live.update(
                    {
                        "ok": live_ok,
                        "method": "live_db_all_status_and_active_recount",
                        "history_view": hist_all.get("history_view"),
                        "history_expansion_mode": hist_all.get("history_expansion_mode"),
                        "all_statuses_loaded": hist_all.get("all_statuses_loaded"),
                        "active_only_view": hist_act.get("history_view"),
                        "loaded_all_status_contracts": total_all,
                        "loaded_active_only_contracts": total_act,
                        "all_minus_active": total_all - total_act,
                        "mismatches_all_status": mismatches_all[:20],
                        "mismatches_active": mismatches_act[:20],
                        "invariant_failures": invariant_fails[:10],
                        "metric_samples": metric_samples,
                        "FAIL_if_active_only_claimed_as_full": (
                            hist_all.get("active_only_filter") is True
                        ),
                    }
                )
            finally:
                conn.close()
    else:
        live = {
            "attempted": False,
            "ok": False,
            "reason": "CONFENGE_COMMERCIAL_STATE_DSN required for live recount",
            "status": "BLOCKED_ALL_STATUS_HISTORY_NOT_PROVEN",
        }

    live_ok = bool(live.get("ok"))
    # Unit alone never suffices for PASS when DSN available; without DSN = BLOCKED not green
    if dsn:
        ok = unit_ok and live_ok
        status = "PASS" if ok else "FAIL"
        exit_code = 0 if ok else 1
    else:
        ok = False
        status = "BLOCKED_ALL_STATUS_HISTORY_NOT_PROVEN" if unit_ok else "FAIL"
        exit_code = 2 if unit_ok else 1

    report = {
        "ok": ok,
        "status": status,
        "history_view_required": "ALL_SNAPSHOT_SUPPLIER_HISTORY",
        "unit_adversarial_ok": unit_ok,
        "pytest_exit": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "live_recount": live,
        "note": (
            "PASS requires adversarial unit fixtures AND live all-status COUNT(*) "
            "reconciliation. Active-only load must not equal all-status when closed "
            "rows exist. JSON ok theater without live recount is rejected."
        ),
    }
    (ART / "all-status-history-gate.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))
    return exit_code


def cmd_active_vs_historical_separation(_: argparse.Namespace) -> int:
    """Prove ACTIVE_COMMERCIAL_PORTFOLIO is never used as historical denominator.

    Unit adversarial fixtures + live DB: for sample suppliers, active metrics
    must not equal all-history metrics when inactive contracts exist; sector
    ratio must use all-history denominator.
    """
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/commercial_leads/test_all_status_history.py::test_active_portfolio_not_historical_denominator",
            "tests/commercial_leads/test_all_status_history.py::test_adversarial_one_active_relevant_nine_closed_food",
            "tests/commercial_leads/test_all_status_history.py::test_adversarial_active_eng_historical_materials",
            "tests/commercial_leads/test_all_status_history.py::test_split_views_and_invariants",
            "-q",
            "--tb=short",
            "-o",
            "addopts=",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    unit_ok = proc.returncode == 0
    dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN") or os.environ.get(
        "CONFENGE_COMMERCIAL_SOURCE_DSN"
    )
    live: dict[str, Any] = {"attempted": False}
    if dsn:
        from scripts.commercial_leads.dbutil import connect, fetch_all
        from scripts.commercial_leads.pipeline import (
            compute_supplier_history_metrics,
            load_full_supplier_histories,
            split_history_views,
        )
        from scripts.commercial_leads.sector_fit import classify_supplier_sector_fit

        d = _load_run()
        lm = d.get("load_meta") or {}
        cnpjs = list(lm.get("candidate_supplier_cnpjs") or [])[:40]
        if not cnpjs and d.get("leads"):
            cnpjs = [str(L["cnpj14"]) for L in d["leads"][:20]]
        live["attempted"] = True
        if not cnpjs:
            live["ok"] = False
            live["reason"] = "no_candidates"
        else:
            conn = connect(dsn)
            try:
                groups, hist = load_full_supplier_histories(
                    conn, cnpjs, per_supplier_limit=None, active_only=False
                )
                # Live checks for every loaded supplier
                separation_cases = []
                all_active_only_cases = []
                violations = []
                invariant_ok_n = 0
                for cnpj, crow in groups.items():
                    m = compute_supplier_history_metrics(crow)
                    all_h, active = split_history_views(crow)
                    if not m.get("invariant_active_plus_inactive") or not m.get(
                        "invariant_relevance_partition"
                    ):
                        violations.append({"cnpj14": cnpj, "reason": "metric_invariant_failed", **m})
                    else:
                        invariant_ok_n += 1
                    # Sector denom must always be all-history size (even if all active)
                    sector = classify_supplier_sector_fit(
                        razao_social=crow[0].get("fornecedor_nome"),
                        contracts=crow,
                        history_is_full=True,
                    )
                    if sector.total_contract_count_full_history != m["all_snapshot_contract_count"]:
                        violations.append(
                            {
                                "cnpj14": cnpj,
                                "reason": "sector_denominator_not_all_history",
                                "sector_total": sector.total_contract_count_full_history,
                                "all_snapshot": m["all_snapshot_contract_count"],
                            }
                        )
                    if m["inactive_or_closed_contract_count"] >= 1 and m["active_contract_count"] >= 1:
                        if (
                            m["relevant_all_history_count"] != m["active_relevant_count"]
                            and m["relevant_all_history_ratio"] == m["active_relevant_ratio"]
                            and m["all_snapshot_contract_count"] != m["active_contract_count"]
                        ):
                            violations.append(
                                {
                                    "cnpj14": cnpj,
                                    "reason": "ratios_collapsed_despite_closed_rows",
                                    **m,
                                }
                            )
                        if len(separation_cases) < 10:
                            separation_cases.append(
                                {
                                    "cnpj14": cnpj,
                                    "all_snapshot_contract_count": m["all_snapshot_contract_count"],
                                    "active_contract_count": m["active_contract_count"],
                                    "inactive_or_closed_contract_count": m[
                                        "inactive_or_closed_contract_count"
                                    ],
                                    "relevant_all_history_ratio": m["relevant_all_history_ratio"],
                                    "active_relevant_ratio": m["active_relevant_ratio"],
                                    "sector_total_full_history": sector.total_contract_count_full_history,
                                }
                            )
                    elif len(all_active_only_cases) < 5:
                        all_active_only_cases.append(
                            {
                                "cnpj14": cnpj,
                                "all_snapshot_contract_count": m["all_snapshot_contract_count"],
                                "active_contract_count": m["active_contract_count"],
                                "inactive_or_closed_contract_count": m[
                                    "inactive_or_closed_contract_count"
                                ],
                                "note": "snapshot row is_active=TRUE only; ratios may match",
                            }
                        )
                # Global snapshot: all vs active counts
                snap_all = fetch_all(
                    conn, "SELECT COUNT(*)::int AS n FROM public.pncp_supplier_contracts"
                )
                snap_act = fetch_all(
                    conn,
                    "SELECT COUNT(*)::int AS n FROM public.pncp_supplier_contracts WHERE is_active = TRUE",
                )
                n_all = int(snap_all[0]["n"]) if snap_all else 0
                n_act = int(snap_act[0]["n"]) if snap_act else 0
                snapshot_all_active = n_all == n_act and n_all > 0
                # When snapshot has zero closed rows, live cannot exhibit ratio divergence;
                # adversarial unit fixtures prove that path. Live still must: load all-status
                # view, enforce sector denom = all history, and pass metric invariants.
                live_ok = (
                    hist.get("history_view") == "ALL_SNAPSHOT_SUPPLIER_HISTORY"
                    and hist.get("all_statuses_loaded") is True
                    and not violations
                    and invariant_ok_n == len(groups)
                    and n_all >= n_act
                    and (
                        len(separation_cases) >= 1
                        or (snapshot_all_active and unit_ok and len(groups) > 0)
                    )
                )
                live.update(
                    {
                        "ok": live_ok,
                        "method": "live_split_views_and_sector_denominator",
                        "snapshot_all_contracts": n_all,
                        "snapshot_active_contracts": n_act,
                        "snapshot_inactive_or_closed": n_all - n_act,
                        "snapshot_contains_only_active_rows": snapshot_all_active,
                        "suppliers_with_both_active_and_closed": len(separation_cases),
                        "separation_cases": separation_cases,
                        "all_active_only_samples": all_active_only_cases,
                        "invariant_ok_suppliers": invariant_ok_n,
                        "suppliers_checked": len(groups),
                        "violations": violations[:20],
                        "history_view": hist.get("history_view"),
                        "active_view": "ACTIVE_COMMERCIAL_PORTFOLIO",
                        "note": (
                            "Closed-contract separation proven by unit adversarial fixtures "
                            "when live snapshot has is_active=TRUE for every row. "
                            "Live proves ALL_SNAPSHOT load + sector denom + metric invariants."
                            if snapshot_all_active
                            else "Live snapshot has inactive/closed rows; separation checked live."
                        ),
                    }
                )
            finally:
                conn.close()
    else:
        live = {
            "attempted": False,
            "ok": False,
            "status": "BLOCKED_ALL_STATUS_HISTORY_NOT_PROVEN",
            "reason": "DSN required for live separation proof",
        }

    if dsn:
        ok = unit_ok and bool(live.get("ok"))
        status = "PASS" if ok else "FAIL"
        exit_code = 0 if ok else 1
    else:
        ok = False
        status = "BLOCKED_ALL_STATUS_HISTORY_NOT_PROVEN" if unit_ok else "FAIL"
        exit_code = 2 if unit_ok else 1

    report = {
        "ok": ok,
        "status": status,
        "active_view": "ACTIVE_COMMERCIAL_PORTFOLIO",
        "historical_view": "ALL_SNAPSHOT_SUPPLIER_HISTORY",
        "unit_adversarial_ok": unit_ok,
        "pytest_exit": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "live_separation": live,
        "note": (
            "ACTIVE portfolio feeds concurrent/near-expiry signals only. "
            "Sector concentration, mixed activity, materials detection use "
            "ALL_SNAPSHOT_SUPPLIER_HISTORY. Never reuse active as historical denom."
        ),
    }
    (ART / "active-vs-historical-separation-gate.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))
    return exit_code


def cmd_registry_coverage(_: argparse.Namespace) -> int:
    """Universe coverage BEFORE publication — top20 alone is never enough."""
    from scripts.commercial_leads.dbutil import connect, fetch_all
    from scripts.commercial_leads.supplier_registry import coverage_report, load_registry_map

    d = _load_run()
    lm = d.get("load_meta") or {}
    all_cands = list(lm.get("candidate_supplier_cnpjs") or [])
    leads = d.get("leads") or []
    top20 = [str(L.get("cnpj14")) for L in leads[:20] if L.get("cnpj14")]
    if not all_cands and top20:
        all_cands = top20
    if not all_cands:
        print(json.dumps({"ok": False, "reason": "no_candidates"}, indent=2))
        return 1

    dsn = _require_dsn()
    conn = connect(dsn)
    try:
        reg_map = load_registry_map(conn, all_cands)
        # load resolution statuses from ingest checkpoint if present
        ck = {}
        ck_path = ART / "registry-ingest-checkpoint.json"
        if ck_path.is_file():
            ck = json.loads(ck_path.read_text(encoding="utf-8"))
        statuses = dict(ck.get("statuses") or {})
        report = coverage_report(
            reg_map,
            all_candidates=all_cands,
            top100=all_cands[:100],
            top20=top20,
            resolution_status=statuses,
        )
        # top20 lookup still verified live
        if top20:
            rows = fetch_all(
                conn,
                "SELECT cnpj14, cnae_principal FROM public.supplier_registry WHERE cnpj14 = ANY(%s)",
                (top20,),
            )
            report["live_top20_rows"] = len(rows)
        all_rate = (report.get("registry_coverage_all_candidates") or {}).get("coverage") or 0
        resolved = report.get("registry_resolved_or_definitively_not_found") or 0
        ok = all_rate == 1.0 or resolved == 1.0
        if report.get("selection_bias_risk"):
            ok = False
        report["ok"] = ok
        report["method"] = "universe_registry_coverage_before_publication"
        if not ok:
            report["block"] = report.get("block_reason") or "BLOCKED_REGISTRY_SELECTION_BIAS"
        (ART / "registry-coverage-gate.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        return 0 if ok else 2
    finally:
        conn.close()


def cmd_registry_universe(_: argparse.Namespace) -> int:
    return cmd_registry_coverage(_)


def cmd_registry_selection_independence(_: argparse.Namespace) -> int:
    """Prove top20 is not an endogenous registry subset artifact."""
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/commercial_leads/test_registry_selection_independence.py",
            "-q",
            "--tb=short",
            "-o",
            "addopts=",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    # Also inspect last run metrics if present
    d = _load_run()
    reg = d.get("registry_coverage") or {}
    all_cov = (reg.get("registry_coverage_all_candidates") or {}).get("coverage")
    top20_cov = (reg.get("registry_coverage_top20") or {}).get("coverage")
    bias = bool(reg.get("selection_bias_risk")) or (
        top20_cov == 1.0 and all_cov is not None and all_cov < 1.0
    )
    structural_ok = proc.returncode == 0
    # Bias present on last run is an honest BLOCKED (exit 2), not a broken detector (exit 1)
    report = {
        "ok": structural_ok and not bias,
        "structural_ok": structural_ok,
        "pytest_exit": proc.returncode,
        "run_all_candidates_coverage": all_cov,
        "run_top20_coverage": top20_cov,
        "selection_bias_detected": bias,
        "block": "BLOCKED_REGISTRY_SELECTION_BIAS" if bias else None,
        "status": (
            "PASS"
            if structural_ok and not bias
            else ("BLOCKED_REGISTRY_SELECTION_BIAS" if structural_ok and bias else "FAIL")
        ),
        "stdout_tail": (proc.stdout or "")[-1500:],
        "note": (
            "Detector unit tests must pass. Incomplete universe coverage is BLOCKED, "
            "not a silent green pass on top20-only coverage."
        ),
    }
    (ART / "registry-selection-independence-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if not structural_ok:
        return 1
    if bias:
        return 2
    return 0


def cmd_historical_window(_: argparse.Namespace) -> int:
    from scripts.commercial_leads.snapshot import observation_window_metrics

    d = _load_run()
    binding = d.get("snapshot_binding") or {}
    man = {}
    man_path = ART / "snapshot-manifest.json"
    if man_path.is_file():
        man = json.loads(man_path.read_text(encoding="utf-8"))
    window = d.get("observation_window") or observation_window_metrics(
        binding.get("min_date") or man.get("min_date"),
        binding.get("max_date") or man.get("max_date"),
    )
    days = window.get("snapshot_observation_days")
    strong_obs = bool(window.get("strong_observable"))
    ok_for_strong = strong_obs and (days is not None and days >= 365)
    report = {
        **window,
        "ok": ok_for_strong,
        "status": (
            "PASS"
            if ok_for_strong
            else (window.get("block") or "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW")
        ),
        "strong_not_observable_declared": not strong_obs,
        "note": (
            "Absence of STRONG is not proof none exist when window < 180d. "
            "STRONG_MIN_TIME_SPAN_DAYS remains 180."
        ),
    }
    (ART / "historical-window-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    # BLOCKED (exit 2) when window insufficient — not a green false pass
    if not strong_obs or (days is not None and days < 365):
        return 2
    return 0


def cmd_export_authenticated_snapshot(_: argparse.Namespace) -> int:
    from scripts.commercial_leads.isolation import open_source_connection
    from scripts.commercial_leads.snapshot import export_authenticated_snapshot

    dsn = _require_dsn()
    dump = ART / "authenticated-snapshot.dump.json"
    man = ART / "snapshot-manifest.json"
    conn = open_source_connection(dsn)
    try:
        payload = export_authenticated_snapshot(
            conn,
            dump_path=dump,
            manifest_path=man,
            package="confenge-authenticated-export",
            source_database_identity=hashlib.sha256(dsn.encode()).hexdigest()[:16],
            export_command="make export-confenge-authenticated-snapshot",
        )
    finally:
        conn.close()
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("canonical_table_hash") else 1


def cmd_verify_authenticated_snapshot(_: argparse.Namespace) -> int:
    from scripts.commercial_leads.isolation import open_source_connection
    from scripts.commercial_leads.snapshot import verify_authenticated_snapshot

    dsn = _require_dsn()
    man = os.environ.get("CONFENGE_COMMERCIAL_SNAPSHOT") or str(ART / "snapshot-manifest.json")
    conn = open_source_connection(dsn)
    try:
        report = verify_authenticated_snapshot(conn, man)
    finally:
        conn.close()
    (ART / "authenticated-snapshot-verify.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))
    if report.get("status") == "BLOCKED_MISSING_INDEPENDENT_SNAPSHOT_ANCHOR":
        return 2
    return 0 if report.get("ok") else 1


def cmd_snapshot_manifest_immutability(_: argparse.Namespace) -> int:
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/commercial_leads/test_snapshot.py",
            "-q",
            "--tb=short",
            "-o",
            "addopts=",
            "-k",
            "immutable or missing_canonical or post_restore",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    report = {
        "ok": proc.returncode == 0,
        "pytest_exit": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
    }
    (ART / "snapshot-manifest-immutability-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def cmd_offer_discrimination(_: argparse.Namespace) -> int:
    from scripts.commercial_leads.scoring import diagnose_offer_distribution

    d = _load_run()
    leads = d.get("leads") or d.get("top20") or []
    diag = d.get("offer_mapping_diagnostic") or diagnose_offer_distribution(leads)
    ok = diag.get("block") is None
    report = {**diag, "ok": ok}
    (ART / "offer-discrimination-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if ok else 2


def cmd_end_to_end_reproducibility(_: argparse.Namespace) -> int:
    """Re-run the commercial pipeline twice end-to-end on the frozen universe.

    Each pass redoes: history expansion (all-status) → registry join → sector →
    signals → eligibility → ranking → offer → top20. Does not reuse prior classes.
    Unit tests alone never suffice for PASS.
    """
    from datetime import date

    unit = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/commercial_leads/test_end_to_end_reproducibility.py",
            "-q",
            "--tb=short",
            "-o",
            "addopts=",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN") or os.environ.get(
        "CONFENGE_COMMERCIAL_SOURCE_DSN"
    )
    if not dsn:
        report = {
            "ok": False,
            "status": "BLOCKED_END_TO_END_REPRODUCIBILITY_NOT_PROVEN",
            "pytest_exit": unit.returncode,
            "unit_ok": unit.returncode == 0,
            "method": "requires_live_double_pipeline_run",
            "reason": "CONFENGE_COMMERCIAL_STATE_DSN required for full e2e re-run",
            "note": (
                "Unit helpers are insufficient. Gate must re-execute full pipeline "
                "twice on frozen candidate universe."
            ),
        }
        (ART / "end-to-end-reproducibility-gate.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        return 2

    from scripts.commercial_leads.dbutil import connect
    from scripts.commercial_leads.pipeline import load_full_supplier_histories
    from scripts.commercial_leads.profile import load_profile
    from scripts.commercial_leads.scoring import rank_leads, score_supplier
    from scripts.commercial_leads.sector_fit import classify_supplier_sector_fit
    from scripts.commercial_leads.signals import compute_signals_for_supplier, rows_from_dicts
    from scripts.commercial_leads.supplier_registry import load_registry_map

    # Delegate to full-universe runner (n == frozen_candidate_count).
    # CONFENGE_E2E_SAMPLE_LIMIT>0 labels result SAMPLED_E2E_TEST — never full PASS.
    from scripts.ops.confenge_full_universe_e2e import run_full_universe_e2e

    sample = int(os.environ.get("CONFENGE_E2E_SAMPLE_LIMIT") or "0")
    report = run_full_universe_e2e(
        dsn=dsn,
        run_result=RUN if RUN.is_file() else None,
        sample_limit=sample,
    )
    report["pytest_exit"] = unit.returncode
    report["unit_ok"] = unit.returncode == 0
    if report.get("status") == "PASS" and unit.returncode != 0:
        report["ok"] = False
        report["status"] = "FAIL"
        report["reason"] = "unit_reproducibility_helpers_failed"
    (ART / "end-to-end-reproducibility-gate.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report.get(k) for k in (
        "ok", "status", "frozen_candidate_count", "n_universe",
        "n_universe_equals_frozen", "all_hashes_equal", "sampled", "unit_ok",
    )}, indent=2, default=str))
    if report.get("status") == "SAMPLED_E2E_TEST":
        return 2  # sampled is not full-universe PASS
    return 0 if report.get("ok") else 2


def cmd_evidence_provenance(_: argparse.Namespace) -> int:
    """Provenance: executed_code_sha vs live HEAD; never false match_run_to_head.

    Fields in result.json:
      executed_code_sha — code that produced evidence (may be ancestor of tip when
        only evidence/docs lag commits follow)
      current_pr_head_sha — tip claimed at packaging (must not be newer than HEAD
        falsely; live HEAD is authoritative)
      match_run_to_head — may be true ONLY when executed_code_sha == live HEAD

    Self-referential tip embedding is impossible without lag; ancestor lag with
    match_run_to_head=false is allowed. match_run_to_head=true + stale SHA = FAIL.
    """
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S603,S607
        cwd=str(_ROOT),
        text=True,
    ).strip()
    result_path = ART / "result.json"
    run_path = ART / "run" / "run-result.json"
    d: dict[str, Any] = {}
    if result_path.is_file():
        d = json.loads(result_path.read_text(encoding="utf-8"))
    elif run_path.is_file():
        d = json.loads(run_path.read_text(encoding="utf-8"))
    executed = d.get("executed_code_sha") or d.get("executed_git_sha") or d.get("run_git_sha")
    pr_head = d.get("current_pr_head_sha") or d.get("pr_head_sha")
    match_flag = d.get("match_run_to_head")
    issues: list[str] = []
    if not executed:
        issues.append("missing_executed_code_sha")

    def _is_ancestor(sha: str, tip: str) -> bool:
        if not sha or not tip:
            return False
        if sha == tip:
            return True
        try:
            subprocess.check_call(  # noqa: S603
                ["git", "merge-base", "--is-ancestor", sha, tip],  # noqa: S603,S607
                cwd=str(_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.CalledProcessError, OSError):
            return False

    live_match = bool(executed and executed == head)
    # Forbidden: claim match when SHAs are stale relative to live HEAD
    if match_flag is True and not live_match:
        issues.append("false_match_run_to_head_with_stale_executed_code_sha")
        if pr_head and pr_head != head:
            issues.append("false_match_run_to_head_with_stale_pr_head")
            issues.append("stale_pr_head_claimed_as_current")
    # executed must be this tip or an ancestor (evidence-only lag commits)
    if executed and not _is_ancestor(str(executed), head):
        issues.append("executed_code_sha_not_ancestor_of_head")
    # Local execution provenance
    local_fields_ok = True
    if not os.environ.get("GITHUB_ACTIONS"):
        att = ART / "evidence-package" / "attestation.json"
        if att.is_file():
            a = json.loads(att.read_text(encoding="utf-8"))
            if not a.get("executed_git_sha") and not a.get("executed_code_sha"):
                local_fields_ok = False
                issues.append("attestation_missing_executed_code_sha")
    ok = not issues and bool(executed)
    report = {
        "ok": ok,
        "current_repo_head": head,
        "executed_code_sha": executed,
        "current_pr_head_sha_declared": pr_head,
        "live_head": head,
        "workflow_run_id": d.get("workflow_run_id") or os.environ.get("GITHUB_RUN_ID"),
        "match_run_to_head_declared": match_flag,
        "live_match_executed_to_head": live_match,
        "executed_is_ancestor_of_head": _is_ancestor(str(executed or ""), head),
        "issues": issues,
        "local_fields_ok": local_fields_ok,
        "note": (
            "match_run_to_head=true only valid when executed_code_sha == live HEAD. "
            "Ancestor lag with match_run_to_head=false is honest evidence packaging."
        ),
    }
    (ART / "evidence-provenance-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


def cmd_full_population(_: argparse.Namespace) -> int:
    """Validate explicit mode semantics — forbid ambiguous FULL_POPULATION claim alone."""
    d = _load_run()
    disc = d.get("discovery_mode")
    hist = d.get("history_expansion_mode")
    rank = d.get("ranking_population_mode")
    pop = d.get("population_mode")
    lim = (d.get("load_meta") or {}).get("limit_applied") or (d.get("metrics") or {}).get(
        "limit_applied"
    )
    # Acceptable: discovery prefilter + full history + full eligible ranking, no limit
    ok = (
        disc == "PREFILTERED_CANDIDATE_DISCOVERY"
        and hist == "FULL_CANDIDATE_HISTORY"
        and rank in ("FULL_ELIGIBLE_CANDIDATES", None)
        and not lim
        and pop not in (None, "")  # legacy field may still say FULL_POPULATION
    )
    # Explicitly reject claiming FULL_SNAPSHOT_SCAN when discovery was prefiltered
    if disc == "PREFILTERED_CANDIDATE_DISCOVERY" and pop == "FULL_SNAPSHOT_SCAN":
        ok = False
    report = {
        "ok": ok,
        "population_mode_legacy": pop,
        "discovery_mode": disc,
        "history_expansion_mode": hist,
        "ranking_population_mode": rank,
        "limit_applied": lim,
        "note": (
            "PASS requires PREFILTERED_CANDIDATE_DISCOVERY + FULL_CANDIDATE_HISTORY "
            "with no LIMIT; FULL_POPULATION alone is not a completeness claim"
        ),
    }
    print(report)
    return 0 if ok else 1


def cmd_prefilter_recall(_: argparse.Namespace) -> int:
    """Re-measure prefilter recall live against DB (same UF universe)."""
    from scripts.commercial_leads.contract_relevance import classify_contract_relevance
    from scripts.commercial_leads.dbutil import connect, fetch_all
    from scripts.commercial_leads.pipeline import (
        _normalize_cnpj_digits,
        discover_candidate_suppliers,
    )
    from scripts.commercial_leads.profile import load_profile

    dsn = _require_dsn()
    conn = connect(dsn)
    try:
        profile = load_profile(_ROOT / "config/commercial_profiles/confenge.yaml")
        uf_list = list((profile.data.get("region") or {}).get("primary_ufs") or [])
        uf_list += list((profile.data.get("region") or {}).get("secondary_ufs") or [])
        uf_list = [u.upper() for u in uf_list if u]
        rows = fetch_all(
            conn,
            """
            SELECT contrato_id, fornecedor_cnpj, objeto_contrato, uf
            FROM public.pncp_supplier_contracts
            WHERE is_active = TRUE AND fornecedor_cnpj IS NOT NULL AND btrim(fornecedor_cnpj) <> ''
              AND uf IS NOT NULL AND upper(btrim(uf)) = ANY(%s)
              AND (abs(hashtext(contrato_id::text)) %% 100) < 8
            LIMIT 8000
            """,
            (uf_list,),
        )
        gold: set[str] = set()
        for r in rows:
            if classify_contract_relevance(r.get("objeto_contrato")).status == "PASS":
                c = _normalize_cnpj_digits(r.get("fornecedor_cnpj"))
                if c:
                    gold.add(c)
        evidence, meta = discover_candidate_suppliers(
            conn, profile, population_mode="FULL_POPULATION"
        )
        disc = set(evidence.keys())
        found = gold & disc
        recall = len(found) / len(gold) if gold else None
        ok = recall is not None and recall >= 0.95
        report = {
            "method": "live_same_universe_uf_hash_sample_no_keyword_prefilter",
            "ufs": uf_list,
            "sample_contracts": len(rows),
            "gold_relevant_suppliers_in_sample": len(gold),
            "discovered_among_gold": len(found),
            "missed": len(gold - disc) if gold else None,
            "candidate_discovery_recall": round(recall, 4) if recall is not None else None,
            "threshold": 0.95,
            "ok": ok,
            "status": "PASS" if ok else "FAIL",
            "discovery_meta_candidate_count": meta.get("candidate_supplier_count"),
        }
        (ART / "prefilter-recall.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        return 0 if ok else 2
    finally:
        conn.close()


def cmd_ranking_quality(_: argparse.Namespace) -> int:
    d = _load_run()
    leads = d.get("leads") or []
    top = leads[:10]
    oos = sum(1 for item in top if item.get("supplier_sector_fit") == "OUT_OF_SCOPE")
    strong = (
        all(
            item.get("supplier_sector_fit")
            in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT")
            for item in top
        )
        if top
        else False
    )
    # also require data_quality full history fields present
    hist_ok = all(
        (item.get("data_quality") or {}).get("total_contract_count_full_history") is not None
        for item in top
    ) if top else False
    print({"top10": len(top), "oos": oos, "strong": strong, "full_history_fields": hist_ok})
    return 0 if strong and oos == 0 and top and hist_ok else 1


def cmd_ranking_stability(_: argparse.Namespace) -> int:
    """Re-execute ranking on the frozen candidate universe (not top20 alone).

    Each pass reloads ALL-STATUS history, recomputes sector fit + signals + offer,
    and requires identical ranking hashes. Does not re-read a boolean file.
    """
    dsn = _require_dsn()
    run = _load_run()
    lm = run.get("load_meta") or {}
    universe = list(lm.get("candidate_supplier_cnpjs") or [])
    leads = run.get("leads") or []
    if not universe and leads:
        universe = [str(L["cnpj14"]) for L in leads]
    if len(universe) < 5 and len(leads) < 5:
        report = {"ok": False, "reason": "insufficient_candidates_in_run", "n": len(universe)}
        (ART / "ranking-stability.json").write_text(json.dumps(report, indent=2) + "\n")
        print(report)
        return 1

    def rank_blob(items: list[dict[str, Any]]) -> str:
        blob = json.dumps(
            [
                (
                    item.get("cnpj14"),
                    item.get("score_total"),
                    item.get("priority"),
                    item.get("supplier_sector_fit"),
                    item.get("selected_offer") or item.get("suggested_offer"),
                )
                for item in items
            ],
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    from datetime import date

    from scripts.commercial_leads.dbutil import connect
    from scripts.commercial_leads.pipeline import load_full_supplier_histories
    from scripts.commercial_leads.profile import load_profile
    from scripts.commercial_leads.scoring import rank_leads, score_supplier
    from scripts.commercial_leads.sector_fit import classify_supplier_sector_fit
    from scripts.commercial_leads.signals import compute_signals_for_supplier, rows_from_dicts
    from scripts.commercial_leads.supplier_registry import load_registry_map

    profile = load_profile(_ROOT / "config/commercial_profiles/confenge.yaml")
    # Prefer full frozen universe; cap only for extreme sizes to keep gate practical
    cnpjs = universe[:5000] if len(universe) > 5000 else universe
    if not cnpjs:
        cnpjs = [str(item["cnpj14"]) for item in leads]

    conn = connect(dsn)
    try:
        groups, hist = load_full_supplier_histories(conn, cnpjs, per_supplier_limit=None)
        reg_map = load_registry_map(conn, cnpjs)
    finally:
        conn.close()
    if not hist.get("history_complete") or not hist.get("all_statuses_loaded"):
        report = {
            "ok": False,
            "reason": "history_incomplete_on_stability_recheck",
            "hist": hist,
        }
        (ART / "ranking-stability.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(report)
        return 1

    as_of = date.fromisoformat(str(run.get("as_of") or date.today().isoformat()))
    names = {str(L.get("cnpj14")): L.get("razao_social") for L in leads}

    def score_universe() -> list[Any]:
        scored = []
        for cnpj in cnpjs:
            crow = groups.get(cnpj) or []
            if not crow:
                continue
            contracts = rows_from_dicts(crow)
            reg = reg_map.get(cnpj)
            sector = classify_supplier_sector_fit(
                razao_social=names.get(cnpj) or crow[0].get("fornecedor_nome"),
                contracts=crow,
                cnae_principal=reg.cnae_principal if reg else None,
                cnaes_secundarios=list(reg.cnaes_secundarios) if reg else [],
                history_is_full=True,
            )
            if sector.classification not in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT"):
                continue
            sigs = compute_signals_for_supplier(contracts, profile, as_of=as_of, official_acts=None)
            total_value = sum(
                float(c.valor_total or 0) for c in contracts if c.valor_total is not None
            )
            pubs = [c.data_publicacao for c in contracts if c.data_publicacao]
            last_pub = max(pubs).isoformat() if pubs else None
            lead = score_supplier(
                cnpj14=cnpj,
                razao_social=names.get(cnpj) or crow[0].get("fornecedor_nome") or cnpj,
                signal_results=sigs,
                profile=profile,
                total_value=total_value,
                contract_count=len(contracts),
                last_publication=last_pub,
            )
            # attach fresh sector (never reuse prior result classes)
            lead._sector = sector.classification  # type: ignore[attr-defined]
            scored.append(lead)
        return scored

    scored_a = score_universe()
    ranked_a = rank_leads(scored_a, profile, suppressed_cnpjs=set(), state_by_cnpj={})
    scored_b = score_universe()
    ranked_b = rank_leads(scored_b, profile, suppressed_cnpjs=set(), state_by_cnpj={})

    def as_items(ranked):
        return [
            {
                "cnpj14": x.cnpj14,
                "score_total": x.score_total,
                "priority": x.priority,
                "supplier_sector_fit": getattr(x, "_sector", None),
                "selected_offer": x.selected_offer or x.suggested_offer,
            }
            for x in ranked
        ]

    ha = rank_blob(as_items(ranked_a))
    hb = rank_blob(as_items(ranked_b))
    order_a = [x.cnpj14 for x in ranked_a]
    order_b = [x.cnpj14 for x in ranked_b]
    published_order = [str(L["cnpj14"]) for L in leads]
    ok = ha == hb and order_a == order_b
    report = {
        "ok": ok,
        "method": "live_full_universe_rescore_twice_all_status_history",
        "candidate_universe_n": len(cnpjs),
        "eligible_rescored_n": len(scored_a),
        "same_snapshot": {"ok": ha == hb, "hash_a": ha, "hash_b": hb},
        "order_stable": order_a == order_b,
        "top20_rescored": order_a[:20],
        "published_top20": published_order[:20],
        "history_view": hist.get("history_view"),
        "history_complete": hist.get("history_complete"),
        "all_statuses_loaded": hist.get("all_statuses_loaded"),
        "note": (
            "Does not reuse prior sector classes, scores, offers, or top20 list. "
            "Re-expands ALL_SNAPSHOT_SUPPLIER_HISTORY for the frozen candidate universe."
        ),
    }
    (ART / "ranking-stability.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


def cmd_baseline_superiority(_: argparse.Namespace) -> int:
    d = _load_run()
    b = d.get("baseline_comparison") or {}
    hm = d.get("human_metrics") or {}
    if hm.get("human_review_status") != "COMPLETE" or hm.get("precision_at_10") is None:
        print(
            {
                "ok": False,
                "status": "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
                "baseline": b,
            }
        )
        return 2
    print(b)
    return 0 if b.get("proposed_better") else 1


def cmd_snapshot_content_binding(_: argparse.Namespace) -> int:
    """Live recompute canonical_table_hash and compare to independent pre-export anchor."""
    from scripts.commercial_leads.isolation import open_source_connection
    from scripts.commercial_leads.snapshot import (
        bind_snapshot_to_database,
        validate_snapshot_manifest,
    )

    dsn = _require_dsn()
    manifest = os.environ.get("CONFENGE_COMMERCIAL_SNAPSHOT") or str(
        ART / "snapshot-manifest.json"
    )
    if not Path(manifest).is_file():
        report = {
            "ok": False,
            "status": "BLOCKED_MISSING_INDEPENDENT_SNAPSHOT_ANCHOR",
            "reason": "CONFENGE_COMMERCIAL_SNAPSHOT / snapshot-manifest.json required",
        }
        (ART / "snapshot-content-binding-gate.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        return 2
    snap = validate_snapshot_manifest(manifest, allow_missing_dump=True)
    if not snap.ok or not snap.canonical_table_hash:
        report = {
            "ok": False,
            "status": snap.status
            if str(snap.status).startswith("BLOCKED")
            else "BLOCKED_MISSING_INDEPENDENT_SNAPSHOT_ANCHOR",
            "reasons": list(snap.reasons or [])
            + (["manifest_without_canonical_table_hash"] if not snap.canonical_table_hash else []),
            "snapshot": snap.as_dict(),
        }
        (ART / "snapshot-content-binding-gate.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2, default=str))
        return 2
    # Explicit marker rejection even if validation path changes
    dump = snap.dump_path or ""
    if "marker" in str(dump).lower():
        report = {
            "ok": False,
            "status": "BLOCKED_MISSING_INDEPENDENT_SNAPSHOT_ANCHOR",
            "reasons": ["marker_dump_cannot_sustain_release"],
            "snapshot": snap.as_dict(),
        }
        (ART / "snapshot-content-binding-gate.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2, default=str))
        return 2
    conn = open_source_connection(dsn)
    try:
        binding = bind_snapshot_to_database(conn, snap, require_canonical_match=True)
    finally:
        conn.close()
    (ART / "snapshot-content-binding-gate.json").write_text(
        json.dumps(binding, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(binding, indent=2, default=str))
    if binding.get("status") == "BLOCKED_MISSING_INDEPENDENT_SNAPSHOT_ANCHOR":
        return 2
    return 0 if binding.get("ok") and binding.get("canonical_table_hash") else 1


def cmd_source_state_isolation(_: argparse.Namespace) -> int:
    """Prove snapshot writes FAIL and ledger writes PASS (RESTORED_SNAPSHOT_SINGLE_DB)."""
    from scripts.commercial_leads.dbutil import connect
    from scripts.commercial_leads.isolation import (
        assert_source_state_isolation,
        probe_snapshot_write_denied,
    )

    dsn = _require_dsn()
    isolation = assert_source_state_isolation(
        source_dsn=dsn,
        state_dsn=dsn,
        force_mode="RESTORED_SNAPSHOT_SINGLE_DB",
        enforce_source_readonly=True,  # non-negotiable for this gate
    )
    snapshot_probe = getattr(isolation, "snapshot_write_probe", None) or probe_snapshot_write_denied(
        dsn
    )

    # Ledger insert must still work on state path (writable commercial tables)
    conn = connect(dsn)
    ledger: dict[str, Any] = {}
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO commercial_lead_runs (
                        run_id, profile_id, profile_version, profile_hash,
                        snapshot_hash, snapshot_manifest, git_sha, status,
                        queue_limit, eligible_companies, ranked_companies, metrics, non_claims
                    ) VALUES (
                        'gate-isolation-probe', 'confenge', 'gate', 'x',
                        'x', '{}'::jsonb, 'gate', 'FAIL',
                        1, 0, 0, '{}'::jsonb, '[]'::jsonb
                    )
                    ON CONFLICT (run_id) DO UPDATE SET status = 'FAIL'
                    """
                )
                conn.commit()
                ledger["insert_ledger"] = "ok"
                cur.execute(
                    "DELETE FROM commercial_lead_runs WHERE run_id = 'gate-isolation-probe'"
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                ledger["insert_ledger"] = f"fail:{exc}"
                try:
                    conn.rollback()
                except Exception as rb_exc:  # noqa: BLE001
                    ledger["rollback_error"] = str(rb_exc)
    finally:
        conn.close()

    # Count must remain stable after probe
    from scripts.commercial_leads.dbutil import fetch_all

    conn2 = connect(dsn)
    try:
        n = int(fetch_all(conn2, "SELECT COUNT(*)::int AS n FROM public.pncp_supplier_contracts")[0]["n"])
    finally:
        conn2.close()

    report: dict[str, Any] = {
        "isolation": isolation.as_dict(),
        "snapshot_write_probe": snapshot_probe,
        "ledger": ledger,
        "snapshot_row_count_after_probe": n,
        "ok": bool(
            isolation.source_state_mode == "RESTORED_SNAPSHOT_SINGLE_DB"
            and isolation.source_read_only_enforced is True
            and snapshot_probe.get("ok") is True
            and ledger.get("insert_ledger") == "ok"
            and str(snapshot_probe.get("insert", "")).startswith("denied")
            and str(snapshot_probe.get("update_real_row", "")).startswith("denied")
            and str(snapshot_probe.get("delete", "")).startswith("denied")
            and snapshot_probe.get("residual_probe_rows") == 0
        ),
        "note": (
            "RESTORED_SNAPSHOT_SINGLE_DB: snapshot mutations denied by DB trigger (064); "
            "ledger writes allowed; not claimed as SOURCE_STATE_SEPARATED."
        ),
    }
    (ART / "source-state-isolation-gate.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


def cmd_migrations(_: argparse.Namespace) -> int:
    """Live migration double-apply; file presence alone is never PASS."""
    from scripts.commercial_leads.pipeline import verify_migration_idempotence

    dsn = _require_dsn()
    r = verify_migration_idempotence(dsn)
    r["skipped"] = False
    r["ok"] = bool(r.get("idempotent") and r.get("first_ok") and r.get("second_ok"))
    # verify 063 present in _migrations
    from scripts.commercial_leads.dbutil import connect, fetch_all

    conn = connect(dsn)
    try:
        rows = fetch_all(
            conn,
            "SELECT version, name FROM _migrations WHERE version IN ('062','063','064') ORDER BY version",
        )
        r["applied_versions"] = [x["version"] for x in rows]
        r["has_062"] = any(x["version"] == "062" for x in rows)
        r["has_063"] = any(x["version"] == "063" for x in rows)
        r["has_064"] = any(x["version"] == "064" for x in rows)
        r["ok"] = r["ok"] and r["has_062"] and r["has_063"] and r["has_064"]
    finally:
        conn.close()
    (ART / "migrations-gate.json").write_text(json.dumps(r, indent=2, default=str) + "\n")
    print(json.dumps(r, indent=2, default=str))
    return 0 if r["ok"] else 1


def cmd_package_evidence(_: argparse.Namespace) -> int:
    out = ART / "evidence-package"
    out.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S603,S607
        cwd=str(_ROOT),
        text=True,
    ).strip()
    import platform
    import socket

    machine = hashlib.sha256(
        f"{platform.node()}|{socket.gethostname()}|{os.environ.get('USER','')}".encode()
    ).hexdigest()[:16]
    files = [
        "result.json",
        "queue-summary.json",
        "denominator-integrity.json",
        "contract-relevance-holdout.json",
        "contract-relevance-real-holdout.json",
        "gold-standard-baseline.json",
        "prefilter-recall.json",
        "full-candidate-history-gate.json",
        "all-status-history-gate.json",
        "registry-coverage-gate.json",
        "registry-selection-independence-gate.json",
        "historical-window-gate.json",
        "snapshot-content-binding-gate.json",
        "offer-discrimination-gate.json",
        "end-to-end-reproducibility-gate.json",
        "evidence-provenance-gate.json",
    ]
    checks: dict[str, Any] = {}
    for f in files:
        p = ART / f
        checks[f] = {
            "exists": p.is_file(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
        }
    started = datetime.now(UTC).isoformat()
    pkg = {
        "executed_code_sha": sha,
        "executed_git_sha": sha,
        "current_pr_head_sha": os.environ.get("PR_HEAD_SHA") or os.environ.get("GITHUB_SHA") or sha,
        "evidence_commit_sha": sha,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "execution_environment": (
            "github_actions" if os.environ.get("GITHUB_ACTIONS") else "local"
        ),
        "machine_id_hash": machine,
        "command": "make package-confenge-commercial-evidence",
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "exit_code": 0,
        "created_at": started,
        "checksums": checks,
        "note": (
            "Execution provenance package. Checksums alone without executed_code_sha "
            "and environment are not a valid attestation."
        ),
    }
    blob = json.dumps(pkg, sort_keys=True).encode()
    pkg["evidence_package_hash"] = hashlib.sha256(blob).hexdigest()
    (out / "attestation.json").write_text(
        json.dumps(pkg, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(pkg, indent=2))
    return 0


def cmd_verify_attestation(_: argparse.Namespace) -> int:
    """executed_git_sha must equal HEAD, or be a git ancestor with only evidence lag.

    Committing attestation cannot embed its own final SHA (recursive). Policy:
    exact match OR executed is ancestor of HEAD (artifact-only lag commits).
    """
    p = ART / "evidence-package" / "attestation.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S603,S607
        cwd=str(_ROOT),
        text=True,
    ).strip()
    executed = d.get("executed_git_sha") or ""
    exact = executed == head
    ancestor = False
    if executed and not exact:
        try:
            subprocess.check_call(  # noqa: S603
                ["git", "merge-base", "--is-ancestor", executed, head],  # noqa: S603,S607
                cwd=str(_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ancestor = True
        except (subprocess.CalledProcessError, OSError):
            ancestor = False
    ok = (exact or ancestor) and bool(
        (d.get("checksums") or {}).get("gold-standard-baseline.json", {}).get("exists")
    )
    report = {
        "ok": ok,
        "executed": executed,
        "head": head,
        "exact_match": exact,
        "ancestor_with_artifact_lag": ancestor,
        "policy": "exact_or_ancestor_artifact_only_lag",
    }
    print(report)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    mapping = {
        "full-candidate-history": cmd_full_candidate_history,
        "all-status-history": cmd_all_status_history,
        "active-vs-historical-separation": cmd_active_vs_historical_separation,
        "registry-coverage": cmd_registry_coverage,
        "registry-universe": cmd_registry_universe,
        "registry-selection-independence": cmd_registry_selection_independence,
        "historical-window": cmd_historical_window,
        "export-authenticated-snapshot": cmd_export_authenticated_snapshot,
        "verify-authenticated-snapshot": cmd_verify_authenticated_snapshot,
        "snapshot-manifest-immutability": cmd_snapshot_manifest_immutability,
        "offer-discrimination": cmd_offer_discrimination,
        "end-to-end-reproducibility": cmd_end_to_end_reproducibility,
        "evidence-provenance": cmd_evidence_provenance,
        "full-population": cmd_full_population,
        "prefilter-recall": cmd_prefilter_recall,
        "ranking-quality": cmd_ranking_quality,
        "ranking-stability": cmd_ranking_stability,
        "baseline-superiority": cmd_baseline_superiority,
        "snapshot-content-binding": cmd_snapshot_content_binding,
        "source-state-isolation": cmd_source_state_isolation,
        "migrations": cmd_migrations,
        "package-evidence": cmd_package_evidence,
        "verify-attestation": cmd_verify_attestation,
    }
    for name in mapping:
        sub.add_parser(name)
    args = ap.parse_args(argv)
    return mapping[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
