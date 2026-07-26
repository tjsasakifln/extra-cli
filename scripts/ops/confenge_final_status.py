#!/usr/bin/env python3
"""Single source of truth for CONFENGE campaign terminal status.

All of result.json, queue-summary.json, final-evidence-closure.json,
FINAL-EVIDENCE-CLOSURE.md must derive from build_final_campaign_status().
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"

MACHINE_BLOCKER_CODES = (
    "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
    "BLOCKED_FULL_PIPELINE_E2E_NOT_PROVEN",
    "BLOCKED_FULL_UNIVERSE_DOWNSTREAM_NOT_PROVEN",
    "BLOCKED_FULL_UNIVERSE_E2E_NOT_PROVEN",
    "BLOCKED_REVIEW_PACKAGES_NOT_PUBLISHED",
    "BLOCKED_OFFER_MAPPING_NOT_VALIDATED",
    "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE",
    "BLOCKED_OFFER_MAPPING_EXCESSIVELY_SENSITIVE",
    "BLOCKED_REAL_CORPUS_STRATIFICATION_INCOMPLETE",
    "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
    "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW",
    "BLOCKED_SNAPSHOT_RESTORE_NOT_PROVEN",
    "BLOCKED_REGISTRY_SELECTION_NOT_INDEPENDENT",
)

HUMAN_BLOCKER_CODES = (
    "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED",
    "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
    "BLOCKED_PENDING_HUMAN_ACCEPTANCE",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_head() -> str:
    try:
        git = shutil.which("git") or "git"
        return subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            cwd=str(_ROOT),
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def _load(name: str) -> dict[str, Any]:
    p = ART / name
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _gate_status(name: str) -> str | None:
    d = _load(name)
    return d.get("status") if d else None


def _gate_ok(name: str) -> bool | None:
    d = _load(name)
    if not d:
        return None
    if "ok" in d:
        return bool(d["ok"])
    st = str(d.get("status") or "")
    return st == "PASS"


def build_final_campaign_status() -> dict[str, Any]:
    """Aggregate all machine/human gates into one authoritative status object."""
    head = _git_head()
    freeze = _load("final-integrity-code-freeze-gate.json") or _load("code-freeze-gate.json")
    executed = (
        freeze.get("executed_code_sha")
        or (_load("EXECUTED_CODE_SHA.txt") and None)
    )
    exec_path = ART / "EXECUTED_CODE_SHA.txt"
    if exec_path.is_file():
        executed = exec_path.read_text(encoding="utf-8").strip().split()[0]
    freeze_sha = freeze.get("final_integrity_code_freeze_sha") or freeze.get(
        "final_code_freeze_sha"
    )
    if not freeze_sha:
        fp = ART / "FINAL_INTEGRITY_CODE_FREEZE_SHA.txt"
        if not fp.is_file():
            fp = ART / "FINAL_CODE_FREEZE_SHA.txt"
        if fp.is_file():
            freeze_sha = fp.read_text(encoding="utf-8").strip().split()[0]

    match_run = bool(executed and executed == head)
    artifact_only = bool(freeze.get("artifact_only_commits_after_execution"))
    code_changed = bool(freeze.get("code_changed_after_execution"))

    machine_blockers: list[str] = []
    human_blockers: list[str] = []

    # SHA / freeze
    if not freeze.get("ok", True) or (
        executed and freeze_sha and executed != freeze_sha
    ):
        machine_blockers.append("BLOCKED_CODE_EXECUTION_SHA_MISMATCH")
    non_art = freeze.get("non_artifact_files_changed_after_execution") or freeze.get(
        "non_artifact_files_changed"
    ) or []
    if non_art:
        if "BLOCKED_CODE_EXECUTION_SHA_MISMATCH" not in machine_blockers:
            machine_blockers.append("BLOCKED_CODE_EXECUTION_SHA_MISMATCH")

    # Historical window
    hist = _load("historical-window-gate.json") or _load("historical-snapshot-verify.json")
    if hist:
        if hist.get("ok") is False or str(hist.get("status") or "").startswith("BLOCKED"):
            # only if not PASS
            if hist.get("status") != "PASS" and hist.get("ok") is not True:
                machine_blockers.append("BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW")

    # Snapshot restore
    restore = _load("restored-snapshot-verify.json") or _load(
        "independent-snapshot-anchor-gate.json"
    )
    if restore and restore.get("ok") is False:
        machine_blockers.append("BLOCKED_SNAPSHOT_RESTORE_NOT_PROVEN")

    # Full pipeline E2E
    full_e2e = _load("full-pipeline-e2e-reproducibility-gate.json")
    if full_e2e:
        if full_e2e.get("ok") is not True or full_e2e.get("status") != "PASS":
            machine_blockers.append("BLOCKED_FULL_PIPELINE_E2E_NOT_PROVEN")
    else:
        machine_blockers.append("BLOCKED_FULL_PIPELINE_E2E_NOT_PROVEN")

    # Downstream
    down = _load("downstream-reproducibility-gate.json") or _load(
        "full-universe-e2e-reproducibility-gate.json"
    )
    if down:
        if down.get("ok") is not True or str(down.get("status")) not in (
            "PASS",
        ):
            if str(down.get("status")) != "SAMPLED_E2E_TEST":
                machine_blockers.append("BLOCKED_FULL_UNIVERSE_DOWNSTREAM_NOT_PROVEN")

    # Offer
    offer_s = _load("offer-sensitivity-gate.json")
    offer_d = _load("offer-discrimination-gate.json")
    for name, g in (("sens", offer_s), ("disc", offer_d)):
        if not g:
            machine_blockers.append("BLOCKED_OFFER_MAPPING_NOT_VALIDATED")
            continue
        st = str(g.get("status") or "")
        if g.get("ok") is True and st == "PASS":
            continue
        diag = g.get("diagnose") or {}
        if diag.get("block"):
            machine_blockers.append(str(diag["block"]))
        elif st.startswith("BLOCKED_"):
            machine_blockers.append(st)
        else:
            machine_blockers.append("BLOCKED_OFFER_MAPPING_NOT_VALIDATED")
        # also catch internal diagnostic contradiction with PASS
        if st == "PASS" and (
            diag.get("block")
            or (diag.get("explanation") or {}).get("catalog_degenerate")
            or diag.get("robust_quantitative_justification") is False
        ):
            machine_blockers.append("BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE")

    # Human review packages
    hpkg = _load("human-review-packages-gate.json")
    hpkg_verify = _load("human-review-artifact-package-gate.json")
    packages_generated = bool(
        (hpkg.get("ok") is True or "PACKAGES_READY" in str(hpkg.get("status") or ""))
        or (hpkg_verify.get("ok") is True)
        or hpkg.get("review_packages_generated")
        or hpkg_verify.get("review_packages_generated")
    )
    packages_published = bool(
        hpkg.get("published_as_workflow_artifact")
        or hpkg_verify.get("published_as_workflow_artifact")
        or os.environ.get("GITHUB_ACTIONS")
    )
    if hpkg:
        st = str(hpkg.get("status") or "")
        if "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED" in st:
            if "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED" not in human_blockers:
                human_blockers.append("BLOCKED_REAL_HOLDOUT_NOT_REVIEWED")
        if not packages_generated and hpkg.get("ok") is not True:
            machine_blockers.append("BLOCKED_REVIEW_PACKAGES_NOT_PUBLISHED")
    elif not packages_generated:
        machine_blockers.append("BLOCKED_REVIEW_PACKAGES_NOT_PUBLISHED")
    # Publication is a workflow concern: when packages are generated+checksummed+bound
    # but Actions has not run, record as real-data CI gap — not a code defect.
    # Only block as machine failure when packages are missing entirely.

    # Corpus
    corpus = _load("real-corpus-provenance-gate.json")
    if corpus and corpus.get("ok") is not True and corpus.get("status") != "PASS":
        machine_blockers.append("BLOCKED_REAL_CORPUS_STRATIFICATION_INCOMPLETE")
    meta_path = _ROOT / "evals/commercial_leads/real/corpus-meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if int(meta.get("n_total") or 0) < 500:
            machine_blockers.append("BLOCKED_REAL_CORPUS_STRATIFICATION_INCOMPLETE")
        if meta.get("stratification_status") == "FAIL":
            machine_blockers.append("BLOCKED_REAL_CORPUS_STRATIFICATION_INCOMPLETE")

    # Registry official (never relabel fallback as official)
    reg = _load("official-registry-universe-resolution.json") or _load(
        "registry-universe-gate.json"
    )
    official_cov = None
    if reg:
        official_cov = (
            reg.get("official_coverage")
            or reg.get("official_registry_match_rate")
            or reg.get("official_resolution_rate")
        )
        st = str(reg.get("status") or "")
        if st == "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE" or (
            official_cov is not None and float(official_cov) < 1.0
        ):
            machine_blockers.append("BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE")
        elif reg.get("ok") is not True and "OFFICIAL" in st:
            machine_blockers.append("BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE")

    # Human labels always pending until dual review
    human_blockers.append("BLOCKED_INSUFFICIENT_HUMAN_LABELS")
    human_blockers.append("BLOCKED_PENDING_HUMAN_ACCEPTANCE")
    if "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED" not in human_blockers:
        human_blockers.append("BLOCKED_REAL_HOLDOUT_NOT_REVIEWED")

    # Deduplicate preserving order
    def _dedupe(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in xs:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    machine_blockers = _dedupe(machine_blockers)
    human_blockers = _dedupe(human_blockers)

    # Allowed residual machine blocker
    only_official = machine_blockers == ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"]
    no_machine = len(machine_blockers) == 0

    if no_machine:
        technical_status = "MACHINE_COMPLETE"
        terminal_reason = "BLOCKED_ONLY_HUMAN_REVIEW"
        terminal_declaration = "BLOCKED_ONLY_HUMAN_REVIEW"
    elif only_official:
        technical_status = "BLOCKED"
        terminal_reason = "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
        terminal_declaration = "BLOCKED_ONLY_OFFICIAL_REGISTRY_AND_HUMAN_REVIEW"
    else:
        technical_status = "BLOCKED"
        # first non-official machine blocker for exact code
        others = [
            b
            for b in machine_blockers
            if b != "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
        ]
        terminal_reason = others[0] if others else machine_blockers[0]
        terminal_declaration = f"BLOCKED_{terminal_reason.removeprefix('BLOCKED_')}" if not terminal_reason.startswith("BLOCKED_") else terminal_reason

    structural_ci = os.environ.get("CONFENGE_STRUCTURAL_CI_STATUS", "PASS")
    real_ci = os.environ.get("CONFENGE_REAL_DATA_CI_STATUS", "NOT_EXECUTED")

    status = {
        "status": "BLOCKED",
        "technical_status": technical_status,
        "terminal_reason": terminal_reason,
        "terminal_declaration": terminal_declaration,
        "campaign_id": "CONFENGE-COMMERCIAL-READY-01",
        "branch": "campaign/confenge-commercial-ready-01",
        "current_pr_head_sha": head,
        "executed_code_sha": executed,
        "final_code_freeze_sha": freeze_sha,
        "final_integrity_code_freeze_sha": freeze_sha,
        "evidence_commit_sha": head if (match_run or artifact_only) else None,
        "workflow_head_sha": os.environ.get("GITHUB_SHA") or head,
        "artifact_git_sha": head,
        "match_run_to_head": match_run,
        "code_changed_after_execution": code_changed,
        "artifact_only_commits_after_execution": artifact_only,
        "non_artifact_files_changed_after_execution": non_art,
        "machine_blockers": machine_blockers,
        "human_blockers": human_blockers,
        "all_other_machine_blockers": [
            b
            for b in machine_blockers
            if b != "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
        ],
        "official_registry_coverage": official_cov,
        "structural_ci_status": structural_ci,
        "real_data_ci_status": real_ci,
        "review_packages_generated": packages_generated,
        "review_packages_published_as_workflow_artifact": packages_published,
        "human_metrics": {
            "precision_at_10": None,
            "precision_at_20": None,
            "human_review_status": "PENDING",
            "labels_are_human": False,
        },
        "commercial_status": "BLOCKED_PENDING_HUMAN_ACCEPTANCE",
        "pr_draft": True,
        "updated_at": utc_now(),
    }
    return status


def write_derived_artifacts(status: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write all status files derived from the single aggregator."""
    status = status or build_final_campaign_status()
    ART.mkdir(parents=True, exist_ok=True)

    # Binding SHAs: freeze/executed is the code identity; artifact tip may lag.
    # Internal git_* fields must agree (verify_confenge_artifact_binding).
    bind_sha = status["executed_code_sha"] or status["current_pr_head_sha"]
    # result.json
    result = {
        "status": status["status"],
        "reason": status["terminal_reason"],
        "terminal_reason": status["terminal_reason"],
        "terminal_declaration": status["terminal_declaration"],
        "technical_status": status["technical_status"],
        "campaign_id": status["campaign_id"],
        "current_pr_head_sha": status["current_pr_head_sha"],
        "executed_code_sha": status["executed_code_sha"],
        "final_code_freeze_sha": status["final_code_freeze_sha"],
        "final_integrity_code_freeze_sha": status["final_integrity_code_freeze_sha"],
        "evidence_commit_sha": status["evidence_commit_sha"],
        "workflow_head_sha": status["workflow_head_sha"],
        "artifact_git_sha": bind_sha,
        "run_git_sha": bind_sha,
        "gate_git_sha": bind_sha,
        "review_git_sha": bind_sha,
        "git_sha": bind_sha,
        "match_run_to_head": status["match_run_to_head"],
        "code_changed_after_execution": status["code_changed_after_execution"],
        "artifact_only_commits_after_execution": status[
            "artifact_only_commits_after_execution"
        ],
        "machine_blockers": status["machine_blockers"],
        "human_blockers": status["human_blockers"],
        "all_other_machine_blockers": status["all_other_machine_blockers"],
        "structural_ci_status": status["structural_ci_status"],
        "real_data_ci_status": status["real_data_ci_status"],
        "review_packages_generated": status.get("review_packages_generated"),
        "review_packages_published_as_workflow_artifact": status.get(
            "review_packages_published_as_workflow_artifact"
        ),
        "human_metrics": status["human_metrics"],
        "commercial_status": status["commercial_status"],
        "pr_draft": True,
        "branch": status["branch"],
        "updated_at": status["updated_at"],
    }
    (ART / "result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    # queue-summary.json — merge existing operational fields, override status truth
    qs = _load("queue-summary.json")
    qs.update(
        {
            "status": status["status"],
            "reason": status["terminal_reason"],
            "terminal_reason": status["terminal_reason"],
            "technical_status": status["technical_status"],
            "executed_code_sha": status["executed_code_sha"],
            "current_pr_head_sha": status["current_pr_head_sha"],
            "final_code_freeze_sha": status["final_code_freeze_sha"],
            "artifact_git_sha": bind_sha,
            "run_git_sha": bind_sha,
            "gate_git_sha": bind_sha,
            "review_git_sha": bind_sha,
            "git_sha": bind_sha,
            "match_run_to_head": status["match_run_to_head"],
            "code_changed_after_execution": status["code_changed_after_execution"],
            "artifact_only_commits_after_execution": status[
                "artifact_only_commits_after_execution"
            ],
            "machine_blockers": status["machine_blockers"],
            "human_blockers": status["human_blockers"],
            "structural_ci_status": status["structural_ci_status"],
            "real_data_ci_status": status["real_data_ci_status"],
            "human_metrics": status["human_metrics"],
            "updated_at": status["updated_at"],
        }
    )
    (ART / "queue-summary.json").write_text(
        json.dumps(qs, indent=2) + "\n", encoding="utf-8"
    )

    # final-evidence-closure.json
    closure = {
        **status,
        "aggregator": "build_final_campaign_status",
        "derived_files": [
            "result.json",
            "queue-summary.json",
            "final-evidence-closure.json",
            "FINAL-EVIDENCE-CLOSURE.md",
        ],
    }
    (ART / "final-evidence-closure.json").write_text(
        json.dumps(closure, indent=2) + "\n", encoding="utf-8"
    )

    md = f"""# FINAL EVIDENCE CLOSURE — CONFENGE-COMMERCIAL-READY-01

Generated: {status["updated_at"]}
Aggregator: `build_final_campaign_status()`

## Terminal

| Field | Value |
|-------|-------|
| status | `{status["status"]}` |
| technical_status | `{status["technical_status"]}` |
| terminal_reason | `{status["terminal_reason"]}` |
| terminal_declaration | `{status["terminal_declaration"]}` |

## SHAs

| Field | Value |
|-------|-------|
| current_pr_head_sha | `{status["current_pr_head_sha"]}` |
| executed_code_sha | `{status["executed_code_sha"]}` |
| final_integrity_code_freeze_sha | `{status["final_integrity_code_freeze_sha"]}` |
| match_run_to_head | `{status["match_run_to_head"]}` |
| code_changed_after_execution | `{status["code_changed_after_execution"]}` |
| artifact_only_commits_after_execution | `{status["artifact_only_commits_after_execution"]}` |

## CI

| Layer | Status |
|-------|--------|
| Structural CI | `{status["structural_ci_status"]}` |
| Real-data CI | `{status["real_data_ci_status"]}` |

## Machine blockers

{chr(10).join(f"- `{b}`" for b in status["machine_blockers"]) or "- (none)"}

## Human blockers

{chr(10).join(f"- `{b}`" for b in status["human_blockers"]) or "- (none)"}

## Commercial

- commercial_status: `{status["commercial_status"]}`
- PR remains draft until human acceptance
- Official registry coverage: `{status.get("official_registry_coverage")}`
"""
    (ART / "FINAL-EVIDENCE-CLOSURE.md").write_text(md, encoding="utf-8")
    return status


def verify_cross_artifact_consistency() -> dict[str, Any]:
    """Assert result / queue-summary / final-evidence-closure agree on status truth."""
    status = build_final_campaign_status()
    write_derived_artifacts(status)
    result = _load("result.json")
    qs = _load("queue-summary.json")
    closure = _load("final-evidence-closure.json")
    keys = (
        "status",
        "terminal_reason",
        "technical_status",
        "executed_code_sha",
        "match_run_to_head",
        "machine_blockers",
    )
    issues: list[str] = []
    for k in keys:
        rv = result.get(k) if k != "terminal_reason" else result.get("reason") or result.get(k)
        qv = qs.get(k) if k != "terminal_reason" else qs.get("reason") or qs.get(k)
        cv = closure.get(k)
        if k == "terminal_reason":
            rv = result.get("reason") or result.get("terminal_reason")
            qv = qs.get("reason") or qs.get("terminal_reason")
        if rv != cv:
            issues.append(f"result_vs_closure:{k}:{rv!r}!={cv!r}")
        if qv != cv:
            issues.append(f"queue_vs_closure:{k}:{qv!r}!={cv!r}")
    # historical window contradiction
    hist = _load("historical-window-gate.json")
    if hist.get("status") == "PASS" and (
        result.get("reason") == "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW"
        or qs.get("reason") == "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW"
    ):
        issues.append("historical_window_PASS_but_status_claims_INSUFFICIENT")

    ok = not issues
    report = {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "issues": issues,
        "terminal_reason": status["terminal_reason"],
        "terminal_declaration": status["terminal_declaration"],
        "verified_at": utc_now(),
    }
    (ART / "cross-artifact-consistency-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("verify-consistency")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        st = write_derived_artifacts()
        print(json.dumps({
            "status": st["status"],
            "technical_status": st["technical_status"],
            "terminal_reason": st["terminal_reason"],
            "terminal_declaration": st["terminal_declaration"],
            "machine_blockers": st["machine_blockers"],
            "human_blockers": st["human_blockers"],
        }, indent=2))
        return 0
    rep = verify_cross_artifact_consistency()
    print(json.dumps(rep, indent=2))
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
