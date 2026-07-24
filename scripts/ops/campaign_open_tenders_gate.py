#!/usr/bin/env python3
"""Structural + unit gate for OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01.

Does not claim VPS operational PASS. Proves repository convergence of the
canonical weekly path, SLA 24h, deliverable-E fail-closed empty, profile
PENDING degradation, snapshot integrity module, and systemd unit presence.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

CAMPAIGN = "OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _check(item_id: str, ok: bool, evidence: list[str], notes: str = "") -> dict[str, Any]:
    return {
        "item_id": item_id,
        "status": "PASS" if ok else "FAIL",
        "evidence": evidence,
        "notes": notes,
    }


def run_gate(root: Path | None = None) -> dict[str, Any]:
    root = root or _PROJECT_ROOT
    checks: list[dict[str, Any]] = []

    # G1: weekly entry exists
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    weekly_py = root / "scripts" / "ops" / "weekly_cycle.py"
    checks.append(
        _check(
            "G1_canonical_entry",
            "extra-weekly:" in makefile and weekly_py.is_file(),
            ["Makefile extra-weekly", str(weekly_py.relative_to(root))],
        )
    )

    # G2: weekly uses run_pncp_open_monitoring
    weekly_src = weekly_py.read_text(encoding="utf-8")
    uses_audit = "run_pncp_open_monitoring" in weekly_src
    no_orphan_loop = "for m in DEFAULT_MODALIDADES" not in weekly_src
    checks.append(
        _check(
            "G2_aggregated_collect",
            uses_audit and no_orphan_loop,
            [
                f"run_pncp_open_monitoring_present={uses_audit}",
                f"orphan_modalidade_loop_absent={no_orphan_loop}",
            ],
        )
    )

    # G3: reconciler only via complete path (pncp_audit still owns reconcile)
    recon_src = (root / "scripts" / "opportunity_intel" / "reconciliation.py").read_text(
        encoding="utf-8"
    )
    audit_src = (root / "scripts" / "opportunity_intel" / "pncp_audit.py").read_text(
        encoding="utf-8"
    )
    checks.append(
        _check(
            "G3_reconcile_complete_only",
            "SourceSnapshotReconciler" in recon_src
            and "scope_complete" in recon_src
            and "SourceSnapshotReconciler" in audit_src
            and "scope_complete and outcome.status" in audit_src,
            ["reconciliation.py gate", "pncp_audit reconcile on complete"],
        )
    )

    # G4: SLA 24h default
    mod = importlib.import_module("scripts.ops.weekly_cycle")
    sla = int(getattr(mod, "PNCP_OPP_SLA_HOURS", 0))
    # If env override is set for tests, still require source default 24
    default_24 = 'WEEKLY_PNCP_SLA_HOURS", "24"' in weekly_src or "WEEKLY_PNCP_SLA_HOURS', '24'" in weekly_src
    checks.append(
        _check(
            "G4_sla_24h",
            default_24 and (sla == 24 or os.getenv("WEEKLY_PNCP_SLA_HOURS") is not None),
            [f"PNCP_OPP_SLA_HOURS={sla}", f"source_default_24={default_24}"],
        )
    )

    # G5: ciga sla ≤ 24
    policy_path = root / "config" / "source_applicability.yaml"
    policy_text = policy_path.read_text(encoding="utf-8")
    # parse ciga_ckan sla_hours
    ciga_sla = None
    try:
        import yaml

        policy = yaml.safe_load(policy_text) or {}
        ciga_sla = ((policy.get("sources") or {}).get("ciga_ckan") or {}).get("sla_hours")
    except Exception as exc:  # noqa: BLE001
        ciga_sla = f"error:{exc}"
    checks.append(
        _check(
            "G5_ciga_sla_24",
            isinstance(ciga_sla, int) and ciga_sla <= 24,
            [f"ciga_ckan.sla_hours={ciga_sla}", "DOD editais freshness ≤24h prevails"],
        )
    )

    # G6: deliverable E live + empty operational fail
    de = importlib.import_module("scripts.ops.deliverable_e_editais")
    empty = de.build_report([])
    audit_empty_op = de.audit_report(empty, operational=True)
    has_from_db = hasattr(de, "build_report_from_db") and hasattr(de, "load_open_candidates_from_db")
    checks.append(
        _check(
            "G6_deliverable_e_fail_closed_empty",
            has_from_db and audit_empty_op.get("ok") is False,
            [
                f"from_db={has_from_db}",
                f"operational_empty_ok={audit_empty_op.get('ok')}",
            ],
        )
    )

    # G7: PENDING capacity blocks GO
    ranking, _fav, risk, _notes = de.score_against_profile(
        {
            "uf": "SC",
            "objeto": "reforma predial de edificacao publica",
            "official_url": "https://pncp.gov.br/x",
            "status": "ABERTA",
        },
        {
            "region": {"uf_primary": "SC"},
            "engineering_categories": ["reforma_predial"],
            "hard_blocks": {},
            "elicitation": {
                "capital_giro": {"status": "PENDING", "value": None},
                "capacidade_simultanea": {"status": "PENDING", "value": None},
                "capacidade_garantia": {"status": "PENDING", "value": None},
                "cats_atestados": {"status": "PENDING", "value": []},
                "certidoes": {"status": "PENDING", "value": None},
            },
        },
    )
    checks.append(
        _check(
            "G7_pending_capacity_no_go",
            ranking == "REVIEW" and any("PENDING" in r for r in risk),
            [f"ranking={ranking}", f"risk={risk[:2]}"],
        )
    )

    # G8: snapshot integrity module
    si_path = root / "scripts" / "ops" / "snapshot_integrity.py"
    checks.append(
        _check(
            "G8_snapshot_integrity_module",
            si_path.is_file() and "measure_snapshot_integrity" in si_path.read_text(encoding="utf-8"),
            [str(si_path.relative_to(root))],
        )
    )

    # G9: campaign makefile target present (or this script exists for gate)
    gate_self = (root / "scripts" / "ops" / "campaign_open_tenders_gate.py").is_file()
    checks.append(
        _check(
            "G9_campaign_gate_script",
            gate_self and "campaign-gate-open-tenders" in makefile
            or gate_self,  # script alone is enough before Makefile wired; recheck after
            [f"makefile_target={'campaign-gate-open-tenders' in makefile}", f"script={gate_self}"],
        )
    )
    # tighten G9 after Makefile land: require both
    checks[-1] = _check(
        "G9_campaign_gate_script",
        gate_self and "campaign-gate-open-tenders" in makefile,
        [f"makefile_target={'campaign-gate-open-tenders' in makefile}", f"script={gate_self}"],
    )

    # G10: systemd units
    svc = root / "deploy" / "systemd" / "extra-weekly.service"
    tmr = root / "deploy" / "systemd" / "extra-weekly.timer"
    checks.append(
        _check(
            "G10_systemd_weekly",
            svc.is_file() and tmr.is_file(),
            [str(svc.relative_to(root)) if svc.is_file() else "missing service",
             str(tmr.relative_to(root)) if tmr.is_file() else "missing timer"],
        )
    )

    # baseline artifact
    baseline = root / "artifacts" / "campaigns" / CAMPAIGN / "baseline.json"
    checks.append(
        _check(
            "G0_baseline",
            baseline.is_file(),
            [str(baseline.relative_to(root)) if baseline.is_file() else "missing"],
        )
    )

    # AST sanity: weekly_cycle parses
    try:
        ast.parse(weekly_src)
        ast_ok = True
    except SyntaxError:
        ast_ok = False
    checks.append(_check("G_ast_weekly", ast_ok, ["weekly_cycle.py parses"]))

    fails = [c for c in checks if c["status"] == "FAIL"]
    return {
        "campaign_id": CAMPAIGN,
        "generated_at": _utc_now(),
        "ok": len(fails) == 0,
        "summary": {"total": len(checks), "pass": len(checks) - len(fails), "fail": len(fails)},
        "checks": checks,
        "claims_forbidden": [
            "VPS_OPERATIONAL",
            "coverage open_tenders ≥95% without regenerated dual report",
            "LOCAL_READY",
            "PROJECT_DONE",
        ],
        "note": "Structural/unit gate only — not full campaign operational PASS",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--root", type=Path, default=None)
    args = p.parse_args(argv)
    report = run_gate(args.root)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    out = args.out or (
        _PROJECT_ROOT
        / "artifacts"
        / "campaigns"
        / CAMPAIGN
        / "campaign-gate.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
