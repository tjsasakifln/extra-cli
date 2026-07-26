#!/usr/bin/env python3
"""Campaign / RC / DOD gates for CONFENGE-COMMERCIAL-READY-01 (fail-closed)."""

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

CAMPAIGN = "CONFENGE-COMMERCIAL-READY-01"
_ROOT = Path(__file__).resolve().parents[2]
_ART = _ROOT / "artifacts/campaigns" / CAMPAIGN


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_sha() -> str:
    try:
        return subprocess.check_output(  # noqa: S603,S607
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _run(cmd: list[str], *, timeout: int = 600) -> dict[str, Any]:
    p = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return {
        "cmd": cmd,
        "exit_code": p.returncode,
        "stdout_tail": (p.stdout or "")[-4000:],
        "stderr_tail": (p.stderr or "")[-4000:],
        "ok": p.returncode == 0,
    }


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    else:
        path.write_text(str(data), encoding="utf-8")


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_campaign_gate(_: argparse.Namespace) -> int:
    results: dict[str, Any] = {"campaign_id": CAMPAIGN, "git_sha": git_sha(), "steps": {}}
    fails: list[str] = []

    # structure
    required = [
        "db/migrations/062_commercial_leads_ledger.sql",
        "config/commercial_profiles/confenge.yaml",
        "config/commercial_profiles/signal_catalog.yaml",
        "scripts/ops/confenge_commercial_cycle.py",
        "scripts/ops/verify_soak_non_interference.py",
        "specs/006-confenge-commercial-ready/spec.md",
        "specs/006-confenge-commercial-ready/plan.md",
        "specs/006-confenge-commercial-ready/tasks.md",
    ]
    for rel in required:
        ok = (_ROOT / rel).is_file()
        results["steps"][f"file:{rel}"] = ok
        if not ok:
            fails.append(f"missing:{rel}")

    from scripts.commercial_leads.profile import load_profile

    prof = load_profile(_ROOT / "config/commercial_profiles/confenge.yaml")
    results["steps"]["profile_signals_ge_12"] = len(prof.signal_ids) >= 12
    if len(prof.signal_ids) < 12:
        fails.append("catalog_lt_12")

    # unit tests → junit
    junit = _ART / "junit-commercial-leads.xml"
    t = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/commercial_leads/",
            "-q",
            "--tb=short",
            "-o",
            "addopts=",
            f"--junitxml={junit}",
        ]
    )
    results["steps"]["pytest"] = t
    if not t["ok"]:
        fails.append("pytest")

    # Gold-standard denominator integrity (synthetic adversarial always)
    den = _run(
        [
            sys.executable,
            "-m",
            "scripts.ops.verify_confenge_denominator_integrity",
            "--out",
            str(_ART / "denominator-integrity.json"),
        ]
    )
    results["steps"]["denominator_integrity"] = den
    if not den["ok"]:
        fails.append("denominator_integrity")

    hold = _run(
        [
            sys.executable,
            "-m",
            "scripts.ops.eval_contract_relevance_holdout",
            "--out",
            str(_ART / "contract-relevance-holdout.json"),
        ]
    )
    results["steps"]["contract_relevance_holdout"] = hold
    if not hold["ok"]:
        fails.append("contract_relevance_holdout")

    # ruff
    r = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "scripts/commercial_leads",
            "scripts/ops/confenge_commercial_cycle.py",
            "scripts/ops/verify_soak_non_interference.py",
            "scripts/ops/confenge_commercial_gates.py",
        ]
    )
    results["steps"]["ruff"] = r
    if not r["ok"]:
        fails.append("ruff")

    # mypy (best effort on commercial path)
    m = _run(
        [
            sys.executable,
            "-m",
            "mypy",
            "scripts/commercial_leads",
            "scripts/ops/confenge_commercial_cycle.py",
            "scripts/ops/verify_soak_non_interference.py",
            "--ignore-missing-imports",
            "--no-error-summary",
        ]
    )
    results["steps"]["mypy"] = {"ok": m["ok"], "exit_code": m["exit_code"], "stderr_tail": m["stderr_tail"]}
    if not m["ok"]:
        fails.append("mypy")

    # bandit
    b = _run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-q",
            "-r",
            "scripts/commercial_leads",
            "scripts/ops/confenge_commercial_cycle.py",
            "scripts/ops/verify_soak_non_interference.py",
            "-ll",
        ]
    )
    results["steps"]["bandit"] = b
    if not b["ok"]:
        fails.append("bandit")

    # pip-audit: CRITICAL/HIGH → FAIL; MEDIUM requires versioned waiver
    pa = _run([sys.executable, "-m", "pip_audit", "-r", "requirements.txt", "-f", "json"], timeout=300)
    results["steps"]["pip_audit"] = {
        "ok": pa["ok"],
        "exit_code": pa["exit_code"],
        "stdout_tail": pa["stdout_tail"][-1500:],
    }
    if "No module named" in (pa["stderr_tail"] + pa["stdout_tail"]):
        results["steps"]["pip_audit"]["module_missing"] = True
        fails.append("pip_audit_module_missing")
    elif pa["exit_code"] not in (0, 1):
        fails.append("pip_audit_error")
    elif pa["exit_code"] == 1:
        # Parse severities when possible
        high = False
        try:
            vulns = json.loads(pa["stdout_tail"] or "[]")
            if isinstance(vulns, list):
                for item in vulns:
                    for v in item.get("vulns") or item.get("vulnerabilities") or []:
                        sev = str(v.get("severity") or v.get("fix") or "").upper()
                        if sev in ("CRITICAL", "HIGH", "H", "C"):
                            high = True
        except json.JSONDecodeError:
            # fail closed if vulns reported but unparsed
            high = True
        results["steps"]["pip_audit"]["known_vulns"] = True
        results["steps"]["pip_audit"]["high_or_critical"] = high
        waiver_path = _ROOT / "artifacts/campaigns" / CAMPAIGN / "security-waivers.json"
        if high:
            fails.append("pip_audit_high_or_critical")
        elif waiver_path.is_file():
            results["steps"]["pip_audit"]["waivers"] = json.loads(
                waiver_path.read_text(encoding="utf-8")
            )
        else:
            # MEDIUM without waiver → FAIL
            fails.append("pip_audit_medium_without_waiver")

    # migrations double-apply when DSN present
    dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN")
    mig_report: dict[str, Any] = {"dsn_present": bool(dsn)}
    if dsn:
        m1 = _run([sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", dsn], timeout=300)
        m2 = _run([sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", dsn], timeout=300)
        mig_report["first"] = m1
        mig_report["second"] = m2
        mig_report["idempotent"] = m1["ok"] and m2["ok"]
        if not mig_report["idempotent"]:
            fails.append("migrations_not_idempotent")
    else:
        mig_report["skipped"] = "CONFENGE_COMMERCIAL_STATE_DSN not set"
    results["steps"]["migrations"] = mig_report
    _write(_ART / "migration-tests.json", mig_report)

    # security aggregate
    _write(
        _ART / "security.json",
        {
            "bandit_ok": b["ok"],
            "pip_audit": results["steps"]["pip_audit"],
            "git_sha": git_sha(),
            "at": utc_now(),
        },
    )

    results["ok"] = len(fails) == 0
    results["fails"] = fails
    results["status"] = "PASS" if results["ok"] else "FAIL"
    results["at"] = utc_now()
    _write(_ART / "campaign-gate.json", results)
    print(json.dumps({"status": results["status"], "fails": fails, "git_sha": results["git_sha"]}, indent=2))
    return 0 if results["ok"] else 1


def cmd_release_candidate(args: argparse.Namespace) -> int:
    sha = git_sha()
    run_path = Path(args.run_result or (_ART / "run" / "run-result.json"))
    if not run_path.is_file():
        print("FAIL: missing run-result.json — run verify-confenge-commercial-ready-real first", file=sys.stderr)
        return 1
    run = json.loads(run_path.read_text(encoding="utf-8"))
    gate_path = _ART / "gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.is_file() else {}

    # freeze hashes
    package_files = list((_ART / "run").glob("commercial-*")) + [
        run_path.resolve() if Path(run_path).exists() else _ART / "run" / "run-result.json",
        _ART / "gate.json",
        _ART / "soak-non-interference.json",
        _ART / "recurrence.json",
    ]
    checksums: dict[str, str] = {}
    for p in package_files:
        pp = Path(p).resolve()
        if pp.is_file():
            try:
                rel = str(pp.relative_to(_ROOT.resolve()))
            except ValueError:
                rel = str(pp)
            checksums[rel] = _sha_file(pp)

    # package reconciliation
    leads = run.get("leads") or []
    recon = {
        "ok": True,
        "issues": [],
        "lead_count_run": len(leads),
        "export_reconciliation": run.get("export_reconciliation"),
    }
    csv_path = _ART / "run" / "commercial-leads.csv"
    if csv_path.is_file():
        n = sum(1 for _ in csv_path.open(encoding="utf-8")) - 1
        recon["lead_count_csv"] = n
        if n != len(leads):
            recon["ok"] = False
            recon["issues"].append("csv_count_mismatch")
    else:
        recon["ok"] = False
        recon["issues"].append("missing_commercial_leads_csv")
    _write(_ART / "package-reconciliation.json", recon)

    # ranking stability from reproduce if present
    repro_path = _ART / "reproduce" / "reproduce.json"
    stability = {"ok": False, "reason": "missing_reproduce"}
    if repro_path.is_file():
        repro = json.loads(repro_path.read_text(encoding="utf-8"))
        stability = {
            "ok": bool(repro.get("ok")),
            "ranking_hash_run1": repro.get("ranking_hash_run1"),
            "ranking_hash_run2": repro.get("ranking_hash_run2"),
            "identical": repro.get("ranking_hash_run1") == repro.get("ranking_hash_run2"),
        }
    _write(_ART / "ranking-stability.json", stability)

    # performance from run metrics
    metrics = run.get("metrics") or {}
    _write(
        _ART / "performance.json",
        {
            "elapsed_seconds": metrics.get("elapsed_seconds"),
            "raw_contracts_loaded": metrics.get("raw_contracts_loaded"),
            "eligible_companies": metrics.get("eligible_companies"),
            "ranked_leads": metrics.get("ranked_leads"),
            "llm_cost": 0,
            "mode": "deterministic",
            "git_sha": run.get("git_sha"),
        },
    )

    # state-events from ledger
    events_path = _ART / "state-events.jsonl"
    with events_path.open("w", encoding="utf-8") as f:
        for row in run.get("ledger") or []:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    # requirement traceability
    trace = {
        "FR-01": {"code": "config/commercial_profiles/confenge.yaml", "test": "test_signals", "status": "ok"},
        "FR-02": {"code": "config/commercial_profiles/signal_catalog.yaml", "test": "test_catalog_has_at_least_12_signals", "status": "ok"},
        "FR-03": {"code": "scripts/commercial_leads/identity.py", "test": "test_identity", "status": "ok"},
        "FR-04": {"code": "scripts/commercial_leads/signals.py", "test": "test_not_computable_never_zero_contribution", "status": "ok"},
        "FR-05": {"code": "scripts/commercial_leads/scoring.py", "test": "test_score_decomposable_and_rank", "status": "ok"},
        "FR-06": {"code": "scripts/commercial_leads/review.py", "test": "test_review_states + test_dnc", "status": "ok"},
        "FR-07": {"code": "scripts/commercial_leads/baseline.py", "artifact": "baseline-comparison.json", "status": "ok"},
        "FR-08": {"code": "scripts/commercial_leads/exports.py", "test": "test_exports_reconcile", "status": "ok"},
        "FR-09": {"code": "scripts/commercial_leads/isolation.py", "artifact": "soak-non-interference.json", "status": "ok"},
        "FR-10": {"artifact": "run/run-result.json", "status": "ok" if run.get("status") == "PASS" else "pending"},
        "FR-11": {"code": "scripts/workspace/cli.py", "status": "ok"},
        "FR-12": {"artifact": "recurrence.json / ranking-stability.json", "status": "ok" if stability.get("ok") else "pending"},
        "FR-13": {"artifact": "user-acceptance.json", "status": "PENDING_HUMAN"},
    }
    _write(_ART / "requirement-traceability.json", trace)

    ua = {
        "status": "PENDING_HUMAN",
        "campaign_id": CAMPAIGN,
        "author_required": "Tiago Sasaki",
        "run_id": run.get("run_id"),
        "git_sha": sha,
        "profile_hash": run.get("profile_hash"),
        "catalog_hash": run.get("catalog_hash"),
        "dataset_hash": run.get("snapshot_hash"),
        "package_checksums": checksums,
        "note": "Agent must not set ACCEPTED. Tiago reviews and binds acceptance to hashes.",
        "created_at": utc_now(),
    }
    _write(_ART / "user-acceptance.json", ua)

    # Commercial validity requirements (no RC_TECHNICAL_PASS ever)
    top10 = leads[:10]
    sector_ok = all(
        str(L.get("supplier_sector_fit") or "") in {
            "CONFIRMED_ENGINEERING",
            "STRONG_ENGINEERING_FIT",
        }
        for L in top10
    ) if top10 else False
    oos_top10 = sum(1 for L in top10 if str(L.get("supplier_sector_fit") or "") == "OUT_OF_SCOPE")
    pop_full = run.get("population_mode") == "FULL_POPULATION"
    binding_ok = bool((run.get("snapshot_binding") or {}).get("ok"))
    ranking_ok = bool(stability.get("ok"))
    mig = run.get("migrations") or {}
    mig_ok = (
        mig.get("skipped") is False
        and bool(mig.get("idempotent") or (mig.get("first_ok") and mig.get("second_ok")))
    )
    sha_fields_ok = all(
        (run.get(k) or run.get("git_sha")) == sha
        for k in ("git_sha", "run_git_sha", "artifact_git_sha")
        if run.get(k) is not None
    ) and bool(run.get("git_sha")) and run.get("git_sha") != "unknown"

    commercial_reasons: list[str] = []
    if not top10:
        commercial_reasons.append("empty_top10")
    if not sector_ok:
        commercial_reasons.append("top10_sector_not_strong")
    if oos_top10:
        commercial_reasons.append("out_of_scope_in_top10")
    if not pop_full:
        commercial_reasons.append("BLOCKED_FULL_POPULATION_NOT_AVAILABLE")
    if not binding_ok:
        commercial_reasons.append("snapshot_binding_failed")
    if not ranking_ok:
        commercial_reasons.append("ranking_stability_missing_or_false")
    if not mig_ok:
        commercial_reasons.append("migrations_not_ok")
    if not sha_fields_ok or run.get("git_sha") != sha:
        commercial_reasons.append("RUN_SHA_MISMATCH")
    if any(str(L.get("commercial_state") or "").upper() == "DO_NOT_CONTACT" for L in leads):
        commercial_reasons.append("dnc_in_queue")
    if (run.get("baseline_comparison") or {}).get("ranking_quality_status") == (
        "FAIL_RANKING_NOT_BETTER_THAN_SIMPLE_BASELINE"
    ):
        commercial_reasons.append("FAIL_RANKING_NOT_BETTER_THAN_SIMPLE_BASELINE")

    # Terminal: PASS only if all technical commercial gates + human would still be needed
    # Without human labels / acceptance, max is BLOCKED
    technical_commercial_ok = (
        run.get("status") == "PASS"
        and gate.get("ok") is True
        and recon.get("ok") is True
        and sector_ok
        and oos_top10 == 0
        and pop_full
        and binding_ok
        and ranking_ok
        and mig_ok
        and sha_fields_ok
        and not commercial_reasons
    )

    if commercial_reasons and run.get("status") == "FAIL":
        terminal = "FAIL"
        terminal_reason = commercial_reasons[0]
    elif not technical_commercial_ok:
        terminal = "BLOCKED"
        if not sector_ok or oos_top10:
            terminal_reason = "BLOCKED_COMMERCIAL_RELEVANCE_NOT_PROVEN"
        elif not pop_full:
            terminal_reason = "BLOCKED_FULL_POPULATION_NOT_AVAILABLE"
        elif "BLOCKED_INSUFFICIENT_HUMAN_LABELS" in str(
            (run.get("baseline_comparison") or {}).get("ranking_quality_status")
        ):
            terminal_reason = "BLOCKED_INSUFFICIENT_HUMAN_LABELS"
        else:
            terminal_reason = "BLOCKED_COMMERCIAL_RELEVANCE_NOT_PROVEN"
    else:
        terminal = "BLOCKED"
        terminal_reason = "BLOCKED_PENDING_HUMAN_ACCEPTANCE"

    rc = {
        "campaign_id": CAMPAIGN,
        "status": terminal,  # PASS | BLOCKED | FAIL only — never RC_TECHNICAL_PASS
        "technical_status": terminal,
        "campaign_terminal": terminal,
        "campaign_terminal_reason": terminal_reason,
        "git_sha": sha,
        "artifact_git_sha": sha,
        "gate_git_sha": sha,
        "review_git_sha": sha,
        "run_id": run.get("run_id"),
        "run_git_sha": run.get("run_git_sha") or run.get("git_sha"),
        "sha_match_run": (run.get("run_git_sha") or run.get("git_sha")) == sha,
        "profile_hash": run.get("profile_hash"),
        "catalog_hash": run.get("catalog_hash"),
        "snapshot_hash": run.get("snapshot_hash"),
        "population_mode": run.get("population_mode"),
        "source_state_mode": run.get("source_state_mode"),
        "sector_fit_distribution": run.get("sector_fit_distribution"),
        "top10_validation": run.get("top10_validation"),
        "commercial_reasons": commercial_reasons,
        "package_checksums": checksums,
        "gate": gate,
        "package_reconciliation": recon,
        "ranking_stability": stability,
        "user_acceptance": "NOT_REQUESTED" if terminal_reason != "BLOCKED_PENDING_HUMAN_ACCEPTANCE" else "PENDING_HUMAN",
        "migrations_in_run": run.get("migrations"),
        "rc_technical_pass_revoked": True,
        "created_at": utc_now(),
    }

    # Campaign result.json — bound to HEAD
    result_body = {
        "status": terminal,
        "reason": terminal_reason,
        "technical_status": terminal,
        "campaign_id": CAMPAIGN,
        "run_id": run.get("run_id"),
        "git_sha": sha,
        "run_git_sha": run.get("run_git_sha") or run.get("git_sha"),
        "artifact_git_sha": sha,
        "gate_git_sha": sha,
        "review_git_sha": sha,
        "sha_match": (run.get("run_git_sha") or run.get("git_sha")) == sha,
        "population_mode": run.get("population_mode"),
        "source_state_mode": run.get("source_state_mode"),
        "leads": len(leads),
        "top5": [
            {
                "cnpj14": L.get("cnpj14"),
                "score": L.get("score_total"),
                "state": L.get("commercial_state"),
                "razao": L.get("razao_social"),
                "supplier_sector_fit": L.get("supplier_sector_fit"),
            }
            for L in leads[:5]
        ],
        "sector_fit_distribution": run.get("sector_fit_distribution"),
        "blockers": commercial_reasons or [terminal_reason],
        "rc_technical_pass_revoked": True,
        "user_acceptance": rc["user_acceptance"],
        "branch": "campaign/confenge-commercial-ready-01",
        "updated_at": utc_now(),
    }
    _write(_ART / "result.json", result_body)
    _write(_ART / "release-candidate.json", rc)
    print(json.dumps({"status": rc["status"], "terminal": rc["campaign_terminal"], "git_sha": sha, "reason": terminal_reason}, indent=2))
    if terminal == "FAIL":
        return 1
    if terminal == "BLOCKED":
        return 2
    return 0


def cmd_dod_audit(_: argparse.Namespace) -> int:
    from scripts.commercial_leads.profile import load_profile

    issues: list[str] = []
    prof = load_profile(_ROOT / "config/commercial_profiles/confenge.yaml")
    if prof.profile_id != "confenge":
        issues.append("profile_id")
    if len(prof.signal_ids) < 12:
        issues.append("signals_lt_12")
    for rel in [
        "specs/006-confenge-commercial-ready/spec.md",
        "specs/006-confenge-commercial-ready/tasks.md",
        "db/migrations/062_commercial_leads_ledger.sql",
        "scripts/commercial_leads/pipeline.py",
        "docs/canonical-entry-points.yaml",
    ]:
        if not (_ROOT / rel).is_file():
            issues.append(f"missing:{rel}")
    # DOD must not claim CONFENGE_COMMERCIAL_READY
    dod = (_ROOT / "DOD.md").read_text(encoding="utf-8")
    # ensure gate checkbox still open for commercial ready
    if "- [x] O gate imediato `CONFENGE_COMMERCIAL_READY`" in dod:
        issues.append("dod_premature_commercial_ready_checked")
    # tasks convergence
    tasks = (_ROOT / "specs/006-confenge-commercial-ready/tasks.md").read_text(encoding="utf-8")
    if "pending" in tasks.lower() and "T10" in tasks and "| pending |" in tasks:
        # allow only FR-13 human pending reflected honestly
        pass
    t = _run([sys.executable, "-m", "pytest", "tests/commercial_leads/", "-q", "-o", "addopts="])
    if not t["ok"]:
        issues.append("tests")
    report = {
        "ok": len(issues) == 0,
        "issues": issues,
        "signal_count": len(prof.signal_ids),
        "git_sha": git_sha(),
        "at": utc_now(),
    }
    _write(_ART / "dod-audit.json", report)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("campaign-gate")
    g.set_defaults(func=cmd_campaign_gate)
    r = sub.add_parser("release-candidate")
    r.add_argument("--run-result", default=None)
    r.set_defaults(func=cmd_release_candidate)
    d = sub.add_parser("dod-audit")
    d.set_defaults(func=cmd_dod_audit)
    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
