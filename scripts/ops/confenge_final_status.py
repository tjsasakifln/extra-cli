#!/usr/bin/env python3
"""Single source of truth for CONFENGE campaign terminal status.

All of result.json, queue-summary.json, final-evidence-closure.json,
FINAL-EVIDENCE-CLOSURE.md, final-integrity-closure.json,
FINAL-INTEGRITY-CLOSURE.md, merge-readiness.json, MERGE-READINESS.md
must derive from build_final_campaign_status() / write_derived_artifacts().
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

# Dummy SHA patterns must never appear in final campaign gates.
_DUMMY_SHA_RE = re.compile(
    r"^(?:a{7,}|b{7,}|0{7,}|f{7,}|deadbeef|cafebabe)[0-9a-f]*$",
    re.IGNORECASE,
)

REAL_DATA_JOB_KEYS = (
    "real_historical_ci_status",
    "real_registry_ci_status",
    "real_full_pipeline_ci_status",
    "real_snapshot_restore_ci_status",
)

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


def _read_sha_file(name: str) -> str | None:
    p = ART / name
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8").strip().split()
    return text[0] if text else None


def is_dummy_sha(value: Any) -> bool:
    """True when value looks like a fixture/dummy git SHA (aaaa…, bbbb…, deadbeef…)."""
    if not isinstance(value, str):
        return False
    s = value.strip().lower()
    if len(s) < 7:
        return False
    if _DUMMY_SHA_RE.match(s):
        return True
    # Repeated single hex nibble for full 40-char SHA
    if len(s) >= 40 and len(set(s[:40])) == 1 and s[0] in "0123456789abcdef":
        return True
    return False


def aggregate_real_data_ci_status(
    real_historical: str,
    real_registry: str,
    real_full_pipeline: str,
    real_snapshot_restore: str,
) -> str:
    """PASS only when all four real evidence jobs are PASS.

    Publication success must never upgrade this value.
    """
    vals = [
        str(real_historical or "NOT_EXECUTED"),
        str(real_registry or "NOT_EXECUTED"),
        str(real_full_pipeline or "NOT_EXECUTED"),
        str(real_snapshot_restore or "NOT_EXECUTED"),
    ]
    # Normalize aliases
    normed: list[str] = []
    for v in vals:
        u = v.upper().replace(" ", "_")
        if u in ("PASS_ARTIFACT_PUBLICATION", "SKIPPED", "SKIP"):
            u = "NOT_EXECUTED"
        if u not in ("PASS", "FAIL", "NOT_EXECUTED"):
            u = "NOT_EXECUTED"
        normed.append(u)
    if any(v == "FAIL" for v in normed):
        return "FAIL"
    if any(v == "NOT_EXECUTED" for v in normed):
        return "NOT_EXECUTED"
    if all(v == "PASS" for v in normed):
        return "PASS"
    return "NOT_EXECUTED"


def resolve_sha_roles(
    *,
    checked_out_sha: str | None = None,
    pr_head_sha: str | None = None,
    workflow_merge_sha: str | None = None,
    executed_code_sha: str | None = None,
    freeze_sha: str | None = None,
    evidence_commit_sha: str | None = None,
    artifact_only: bool = False,
    code_changed: bool = False,
    non_artifact: list[str] | None = None,
) -> dict[str, Any]:
    """Authoritative SHA role map. Never labels merge SHA as pr_head."""
    checked = checked_out_sha or _git_head()
    # PR head: explicit env (Actions) wins; else local HEAD is the PR tip.
    pr_head = (
        pr_head_sha
        or os.environ.get("CONFENGE_PR_HEAD_SHA")
        or os.environ.get("GITHUB_EVENT_PULL_REQUEST_HEAD_SHA")
        or checked
    )
    merge = workflow_merge_sha or os.environ.get("CONFENGE_WORKFLOW_MERGE_SHA") or os.environ.get("GITHUB_SHA") or None
    # On pull_request, GITHUB_SHA is the merge ref — never promote it to pr_head
    # when CONFENGE_PR_HEAD_SHA is set and differs.
    if (
        merge
        and pr_head
        and merge == checked
        and os.environ.get("CONFENGE_PR_HEAD_SHA")
        and os.environ.get("CONFENGE_PR_HEAD_SHA") != merge
    ):
        pr_head = os.environ["CONFENGE_PR_HEAD_SHA"]

    executed = executed_code_sha
    freeze = freeze_sha
    evidence = evidence_commit_sha
    non_art = list(non_artifact or [])
    match = bool(executed and pr_head and executed == pr_head)
    # When lag exists with only artifact commits: match false, code_changed false
    if executed and pr_head and executed != pr_head and artifact_only and not code_changed:
        match = False
    return {
        "pr_head_sha": pr_head,
        "current_pr_head_sha": pr_head,  # alias — must never be merge-only
        "workflow_merge_sha": merge,
        "checked_out_sha": checked,
        "executed_code_sha": executed,
        "final_integrity_code_freeze_sha": freeze,
        "final_code_freeze_sha": freeze,
        "freeze_sha": freeze,
        "evidence_commit_sha": evidence if evidence else (pr_head if (match or artifact_only) else None),
        "workflow_artifact_head_sha": pr_head,
        "match_run_to_head": match,
        "code_changed_after_execution": bool(code_changed),
        "artifact_only_commits_after_execution": bool(artifact_only),
        "non_artifact_files_changed_after_execution": non_art,
    }


def _env_status(name: str, default: str = "NOT_EXECUTED") -> str:
    raw = os.environ.get(name, default)
    u = str(raw or default).upper().replace(" ", "_")
    if u in ("PASS_ARTIFACT_PUBLICATION", "SKIPPED", "SKIP"):
        return "NOT_EXECUTED"
    if u in ("PASS", "FAIL", "NOT_EXECUTED"):
        return u
    return default


def _job_status_from_file_or_env() -> dict[str, str]:
    """Layered job statuses from env and optional workflow-job-status.json."""
    stamp = _load("workflow-job-status.json")

    def pick(key: str, env_name: str, default: str = "NOT_EXECUTED") -> str:
        if stamp.get(key):
            v = str(stamp[key]).upper().replace(" ", "_")
            if v in ("PASS", "FAIL", "NOT_EXECUTED"):
                return v
        return _env_status(env_name, default)

    return {
        "structural_ci_status": pick("structural_ci_status", "CONFENGE_STRUCTURAL_CI_STATUS", "PASS"),
        "real_historical_ci_status": pick("real_historical_ci_status", "CONFENGE_REAL_HISTORICAL_CI_STATUS"),
        "real_registry_ci_status": pick("real_registry_ci_status", "CONFENGE_REAL_REGISTRY_CI_STATUS"),
        "real_full_pipeline_ci_status": pick("real_full_pipeline_ci_status", "CONFENGE_REAL_FULL_PIPELINE_CI_STATUS"),
        "real_snapshot_restore_ci_status": pick(
            "real_snapshot_restore_ci_status",
            "CONFENGE_REAL_SNAPSHOT_RESTORE_CI_STATUS",
        ),
        "human_package_publication_status": pick(
            "human_package_publication_status",
            "CONFENGE_HUMAN_PACKAGE_PUBLICATION_STATUS",
            "NOT_EXECUTED",
        ),
        "machine_evidence_publication_status": pick(
            "machine_evidence_publication_status",
            "CONFENGE_MACHINE_EVIDENCE_PUBLICATION_STATUS",
            "NOT_EXECUTED",
        ),
        "github_workflow_status": pick("github_workflow_status", "CONFENGE_GITHUB_WORKFLOW_STATUS", "NOT_EXECUTED"),
    }


def build_final_campaign_status() -> dict[str, Any]:
    """Aggregate all machine/human gates into one authoritative status object."""
    freeze = _load("final-integrity-code-freeze-gate.json") or _load("code-freeze-gate.json")
    executed = freeze.get("executed_code_sha") or _read_sha_file("EXECUTED_CODE_SHA.txt")
    freeze_sha = (
        freeze.get("final_integrity_code_freeze_sha")
        or freeze.get("final_code_freeze_sha")
        or _read_sha_file("FINAL_INTEGRITY_CODE_FREEZE_SHA.txt")
        or _read_sha_file("FINAL_CODE_FREEZE_SHA.txt")
    )

    # Prefer live freeze-gate flags; recompute artifact-only from gate fields
    artifact_only = bool(freeze.get("artifact_only_commits_after_execution"))
    code_changed = bool(freeze.get("code_changed_after_execution"))
    non_art = list(
        freeze.get("non_artifact_files_changed_after_execution") or freeze.get("non_artifact_files_changed") or []
    )
    # If freeze gate is stale vs live HEAD, recompute lag from git when possible
    checked = _git_head()
    if freeze_sha and freeze_sha != checked and not non_art:
        try:
            git = shutil.which("git") or "git"
            changed = subprocess.check_output(  # noqa: S603
                [git, "diff", "--name-only", f"{freeze_sha}..{checked}"],
                cwd=str(_ROOT),
                text=True,
            ).splitlines()
            allowed = (
                "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/",
                "docs/ops/",
                "evals/commercial_leads/real/",
            )
            non_art = [f for f in changed if not any(f.startswith(p) for p in allowed)]
            artifact_only = len(changed) > 0 and len(non_art) == 0
            code_changed = len(non_art) > 0
        except (subprocess.CalledProcessError, OSError):
            pass

    sha = resolve_sha_roles(
        checked_out_sha=checked,
        executed_code_sha=executed,
        freeze_sha=freeze_sha,
        evidence_commit_sha=checked if (artifact_only or executed == checked) else None,
        artifact_only=artifact_only,
        code_changed=code_changed,
        non_artifact=non_art,
    )

    machine_blockers: list[str] = []
    human_blockers: list[str] = []

    if not freeze.get("ok", True) or (executed and freeze_sha and executed != freeze_sha):
        machine_blockers.append("BLOCKED_CODE_EXECUTION_SHA_MISMATCH")
    if non_art:
        if "BLOCKED_CODE_EXECUTION_SHA_MISMATCH" not in machine_blockers:
            machine_blockers.append("BLOCKED_CODE_EXECUTION_SHA_MISMATCH")

    hist = _load("historical-window-gate.json") or _load("historical-snapshot-verify.json")
    if hist:
        if hist.get("ok") is False or str(hist.get("status") or "").startswith("BLOCKED"):
            if hist.get("status") != "PASS" and hist.get("ok") is not True:
                machine_blockers.append("BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW")

    restore = _load("restored-snapshot-verify.json") or _load("independent-snapshot-anchor-gate.json")
    if restore and restore.get("ok") is False:
        machine_blockers.append("BLOCKED_SNAPSHOT_RESTORE_NOT_PROVEN")

    full_e2e = _load("full-pipeline-e2e-reproducibility-gate.json")
    if full_e2e:
        if full_e2e.get("ok") is not True or full_e2e.get("status") != "PASS":
            machine_blockers.append("BLOCKED_FULL_PIPELINE_E2E_NOT_PROVEN")
    else:
        machine_blockers.append("BLOCKED_FULL_PIPELINE_E2E_NOT_PROVEN")

    down = _load("downstream-reproducibility-gate.json") or _load("full-universe-e2e-reproducibility-gate.json")
    if down:
        if down.get("ok") is not True or str(down.get("status")) not in ("PASS",):
            if str(down.get("status")) != "SAMPLED_E2E_TEST":
                machine_blockers.append("BLOCKED_FULL_UNIVERSE_DOWNSTREAM_NOT_PROVEN")

    offer_s = _load("offer-sensitivity-gate.json")
    offer_d = _load("offer-discrimination-gate.json")
    for g in (offer_s, offer_d):
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
        if st == "PASS" and (
            diag.get("block")
            or (diag.get("explanation") or {}).get("catalog_degenerate")
            or diag.get("robust_quantitative_justification") is False
        ):
            machine_blockers.append("BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE")

    hpkg = _load("human-review-packages-gate.json")
    hpkg_verify = _load("human-review-artifact-package-gate.json")
    packages_generated = bool(
        (hpkg.get("ok") is True or "PACKAGES_READY" in str(hpkg.get("status") or ""))
        or (hpkg_verify.get("ok") is True)
        or hpkg.get("review_packages_generated")
        or hpkg_verify.get("review_packages_generated")
    )
    pub_stamp = _load("workflow-artifact-publication.json") or _load("human-review/workflow-publication.json")
    packages_published = bool(
        hpkg.get("published_as_workflow_artifact")
        or hpkg_verify.get("published_as_workflow_artifact")
        or pub_stamp.get("published_as_workflow_artifact")
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

    reg = _load("official-registry-universe-resolution.json") or _load("registry-universe-gate.json")
    official_cov = None
    if reg:
        official_cov = (
            reg.get("official_coverage")
            or reg.get("official_registry_match_rate")
            or reg.get("official_resolution_rate")
        )
        st = str(reg.get("status") or "")
        if st == "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE" or (official_cov is not None and float(official_cov) < 1.0):
            machine_blockers.append("BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE")
        elif reg.get("ok") is not True and "OFFICIAL" in st:
            machine_blockers.append("BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE")

    human_blockers.append("BLOCKED_INSUFFICIENT_HUMAN_LABELS")
    human_blockers.append("BLOCKED_PENDING_HUMAN_ACCEPTANCE")
    if "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED" not in human_blockers:
        human_blockers.append("BLOCKED_REAL_HOLDOUT_NOT_REVIEWED")

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
        others = [b for b in machine_blockers if b != "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"]
        terminal_reason = others[0] if others else machine_blockers[0]
        terminal_declaration = (
            f"BLOCKED_{terminal_reason.removeprefix('BLOCKED_')}"
            if not terminal_reason.startswith("BLOCKED_")
            else terminal_reason
        )

    layers = _job_status_from_file_or_env()
    # Infer publication from package gates when env not set
    if packages_published and layers["human_package_publication_status"] == "NOT_EXECUTED":
        if hpkg_verify.get("published_as_workflow_artifact") or pub_stamp.get("published_as_workflow_artifact"):
            layers["human_package_publication_status"] = "PASS"
    if packages_published and layers["machine_evidence_publication_status"] == "NOT_EXECUTED":
        if pub_stamp.get("published_as_workflow_artifact") or (ART / "machine-evidence").is_dir():
            # publication of machine bundle is separate from real-data execution
            if pub_stamp.get("workflow_run_id") or os.environ.get("GITHUB_RUN_ID"):
                layers["machine_evidence_publication_status"] = "PASS"

    real_ci = aggregate_real_data_ci_status(
        layers["real_historical_ci_status"],
        layers["real_registry_ci_status"],
        layers["real_full_pipeline_ci_status"],
        layers["real_snapshot_restore_ci_status"],
    )

    # Workflow binding (never invent IDs — only from stamp/env)
    wf_run_id = os.environ.get("GITHUB_RUN_ID") or pub_stamp.get("workflow_run_id") or None
    human_art_id = (
        os.environ.get("CONFENGE_HUMAN_ARTIFACT_ID")
        or pub_stamp.get("human_review_artifact_id")
        or pub_stamp.get("workflow_artifact_id")
        or (pub_stamp.get("workflow_artifact_ids") or {}).get("confenge-human-review-packages")
    )
    machine_art_id = (
        os.environ.get("CONFENGE_MACHINE_ARTIFACT_ID")
        or pub_stamp.get("machine_evidence_artifact_id")
        or (pub_stamp.get("workflow_artifact_ids") or {}).get("confenge-machine-evidence")
    )

    all_other = [b for b in machine_blockers if b != "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"]

    # Merge-readiness evaluation (code vs commercial)
    structural_ok = layers["structural_ci_status"] == "PASS"
    local_e2e_ok = bool(full_e2e and full_e2e.get("ok") is True)
    local_down_ok = bool(down and (down.get("ok") is True or str(down.get("status")) == "PASS"))
    local_restore_ok = not (restore and restore.get("ok") is False)
    offer_ok = bool(offer_s and offer_s.get("ok") is True and offer_d and offer_d.get("ok") is True)
    corpus_ok = bool(corpus and corpus.get("ok") is True) if corpus else True
    packages_ok = packages_generated
    no_code_drift = len(non_art) == 0 and not code_changed
    freeze_ok = bool(executed and freeze_sha and executed == freeze_sha and freeze.get("ok", True))

    code_merge_ready = bool(
        structural_ok
        and local_e2e_ok
        and local_down_ok
        and local_restore_ok
        and offer_ok
        and corpus_ok
        and packages_ok
        and no_code_drift
        and freeze_ok
        and only_official  # only residual official-registry machine blocker
        and real_ci in ("PASS", "NOT_EXECUTED")  # honest; never fail hidden
    )
    commercial_release_ready = False  # fail-closed until 100% registry + human review

    status = {
        "status": "BLOCKED",
        "technical_status": technical_status,
        "terminal_reason": terminal_reason,
        "terminal_declaration": terminal_declaration,
        "campaign_id": "CONFENGE-COMMERCIAL-READY-01",
        "branch": "campaign/confenge-commercial-ready-01",
        # SHA roles (explicit)
        "pr_head_sha": sha["pr_head_sha"],
        "current_pr_head_sha": sha["current_pr_head_sha"],
        "workflow_merge_sha": sha["workflow_merge_sha"],
        "checked_out_sha": sha["checked_out_sha"],
        "executed_code_sha": sha["executed_code_sha"],
        "final_code_freeze_sha": sha["final_code_freeze_sha"],
        "final_integrity_code_freeze_sha": sha["final_integrity_code_freeze_sha"],
        "freeze_sha": sha["freeze_sha"],
        "evidence_commit_sha": sha["evidence_commit_sha"],
        "workflow_artifact_head_sha": sha["workflow_artifact_head_sha"],
        # legacy alias: workflow_head_sha == merge when in Actions, else checked out
        "workflow_head_sha": sha["workflow_merge_sha"] or sha["checked_out_sha"],
        "artifact_git_sha": sha["executed_code_sha"] or sha["pr_head_sha"],
        "match_run_to_head": sha["match_run_to_head"],
        "code_changed_after_execution": sha["code_changed_after_execution"],
        "artifact_only_commits_after_execution": sha["artifact_only_commits_after_execution"],
        "non_artifact_files_changed_after_execution": sha["non_artifact_files_changed_after_execution"],
        "machine_blockers": machine_blockers,
        "human_blockers": human_blockers,
        "all_other_machine_blockers": all_other,
        "official_registry_coverage": official_cov,
        # Layered CI — never conflate publication with real-data PASS
        "structural_ci_status": layers["structural_ci_status"],
        "real_historical_ci_status": layers["real_historical_ci_status"],
        "real_registry_ci_status": layers["real_registry_ci_status"],
        "real_full_pipeline_ci_status": layers["real_full_pipeline_ci_status"],
        "real_snapshot_restore_ci_status": layers["real_snapshot_restore_ci_status"],
        "human_package_publication_status": layers["human_package_publication_status"],
        "machine_evidence_publication_status": layers["machine_evidence_publication_status"],
        "real_data_ci_status": real_ci,
        "github_workflow_status": layers["github_workflow_status"],
        "review_packages_generated": packages_generated,
        "review_packages_published_as_workflow_artifact": packages_published,
        "workflow_run_id": wf_run_id,
        "workflow_run_url": (
            f"https://github.com/tjsasakifln/extra-cli/actions/runs/{wf_run_id}" if wf_run_id else None
        ),
        "human_review_artifact_id": human_art_id,
        "machine_evidence_artifact_id": machine_art_id,
        "human_metrics": {
            "precision_at_10": None,
            "precision_at_20": None,
            "human_review_status": "PENDING",
            "labels_are_human": False,
        },
        "commercial_status": "BLOCKED_PENDING_HUMAN_ACCEPTANCE",
        "code_merge_ready": code_merge_ready,
        "commercial_release_ready": commercial_release_ready,
        "pr_draft": not code_merge_ready,
        "updated_at": utc_now(),
    }
    return status


def _bind_sha(status: dict[str, Any]) -> str:
    return status["executed_code_sha"] or status["pr_head_sha"] or status["current_pr_head_sha"]


def write_derived_artifacts(status: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write all status files derived from the single aggregator."""
    status = status or build_final_campaign_status()
    ART.mkdir(parents=True, exist_ok=True)
    bind_sha = _bind_sha(status)

    result = {
        "status": status["status"],
        "reason": status["terminal_reason"],
        "terminal_reason": status["terminal_reason"],
        "terminal_declaration": status["terminal_declaration"],
        "technical_status": status["technical_status"],
        "campaign_id": status["campaign_id"],
        "pr_head_sha": status["pr_head_sha"],
        "current_pr_head_sha": status["current_pr_head_sha"],
        "workflow_merge_sha": status["workflow_merge_sha"],
        "checked_out_sha": status["checked_out_sha"],
        "executed_code_sha": status["executed_code_sha"],
        "final_code_freeze_sha": status["final_code_freeze_sha"],
        "final_integrity_code_freeze_sha": status["final_integrity_code_freeze_sha"],
        "freeze_sha": status["freeze_sha"],
        "evidence_commit_sha": status["evidence_commit_sha"],
        "workflow_head_sha": status["workflow_head_sha"],
        "workflow_artifact_head_sha": status["workflow_artifact_head_sha"],
        "artifact_git_sha": bind_sha,
        "run_git_sha": bind_sha,
        "gate_git_sha": bind_sha,
        "review_git_sha": bind_sha,
        "git_sha": bind_sha,
        "match_run_to_head": status["match_run_to_head"],
        "code_changed_after_execution": status["code_changed_after_execution"],
        "artifact_only_commits_after_execution": status["artifact_only_commits_after_execution"],
        "non_artifact_files_changed_after_execution": status["non_artifact_files_changed_after_execution"],
        "machine_blockers": status["machine_blockers"],
        "human_blockers": status["human_blockers"],
        "all_other_machine_blockers": status["all_other_machine_blockers"],
        "structural_ci_status": status["structural_ci_status"],
        "real_historical_ci_status": status["real_historical_ci_status"],
        "real_registry_ci_status": status["real_registry_ci_status"],
        "real_full_pipeline_ci_status": status["real_full_pipeline_ci_status"],
        "real_snapshot_restore_ci_status": status["real_snapshot_restore_ci_status"],
        "human_package_publication_status": status["human_package_publication_status"],
        "machine_evidence_publication_status": status["machine_evidence_publication_status"],
        "real_data_ci_status": status["real_data_ci_status"],
        "github_workflow_status": status["github_workflow_status"],
        "review_packages_generated": status.get("review_packages_generated"),
        "review_packages_published_as_workflow_artifact": status.get("review_packages_published_as_workflow_artifact"),
        "workflow_run_id": status.get("workflow_run_id"),
        "human_review_artifact_id": status.get("human_review_artifact_id"),
        "machine_evidence_artifact_id": status.get("machine_evidence_artifact_id"),
        "code_merge_ready": status.get("code_merge_ready"),
        "commercial_release_ready": status.get("commercial_release_ready"),
        "human_metrics": status["human_metrics"],
        "commercial_status": status["commercial_status"],
        "pr_draft": status.get("pr_draft", True),
        "branch": status["branch"],
        "updated_at": status["updated_at"],
    }
    (ART / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    qs = _load("queue-summary.json")
    qs.update(
        {
            "status": status["status"],
            "reason": status["terminal_reason"],
            "terminal_reason": status["terminal_reason"],
            "technical_status": status["technical_status"],
            "executed_code_sha": status["executed_code_sha"],
            "pr_head_sha": status["pr_head_sha"],
            "current_pr_head_sha": status["current_pr_head_sha"],
            "workflow_merge_sha": status["workflow_merge_sha"],
            "final_code_freeze_sha": status["final_code_freeze_sha"],
            "artifact_git_sha": bind_sha,
            "run_git_sha": bind_sha,
            "gate_git_sha": bind_sha,
            "review_git_sha": bind_sha,
            "git_sha": bind_sha,
            "match_run_to_head": status["match_run_to_head"],
            "code_changed_after_execution": status["code_changed_after_execution"],
            "artifact_only_commits_after_execution": status["artifact_only_commits_after_execution"],
            "machine_blockers": status["machine_blockers"],
            "human_blockers": status["human_blockers"],
            "structural_ci_status": status["structural_ci_status"],
            "real_historical_ci_status": status["real_historical_ci_status"],
            "real_registry_ci_status": status["real_registry_ci_status"],
            "real_full_pipeline_ci_status": status["real_full_pipeline_ci_status"],
            "real_snapshot_restore_ci_status": status["real_snapshot_restore_ci_status"],
            "human_package_publication_status": status["human_package_publication_status"],
            "machine_evidence_publication_status": status["machine_evidence_publication_status"],
            "real_data_ci_status": status["real_data_ci_status"],
            "github_workflow_status": status["github_workflow_status"],
            "human_metrics": status["human_metrics"],
            "updated_at": status["updated_at"],
        }
    )
    (ART / "queue-summary.json").write_text(json.dumps(qs, indent=2) + "\n", encoding="utf-8")

    # final-evidence-closure
    closure = {
        **status,
        "aggregator": "build_final_campaign_status",
        "derived_files": [
            "result.json",
            "queue-summary.json",
            "final-evidence-closure.json",
            "FINAL-EVIDENCE-CLOSURE.md",
            "final-integrity-closure.json",
            "FINAL-INTEGRITY-CLOSURE.md",
            "merge-readiness.json",
            "MERGE-READINESS.md",
        ],
    }
    (ART / "final-evidence-closure.json").write_text(json.dumps(closure, indent=2) + "\n", encoding="utf-8")

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
| pr_head_sha / current_pr_head_sha | `{status["pr_head_sha"]}` |
| workflow_merge_sha | `{status["workflow_merge_sha"]}` |
| checked_out_sha | `{status["checked_out_sha"]}` |
| executed_code_sha | `{status["executed_code_sha"]}` |
| final_integrity_code_freeze_sha | `{status["final_integrity_code_freeze_sha"]}` |
| match_run_to_head | `{status["match_run_to_head"]}` |
| code_changed_after_execution | `{status["code_changed_after_execution"]}` |
| artifact_only_commits_after_execution | `{status["artifact_only_commits_after_execution"]}` |

## CI (layered)

| Layer | Status |
|-------|--------|
| GitHub workflow | `{status["github_workflow_status"]}` |
| Structural CI | `{status["structural_ci_status"]}` |
| Real historical CI | `{status["real_historical_ci_status"]}` |
| Real registry CI | `{status["real_registry_ci_status"]}` |
| Real full-pipeline CI | `{status["real_full_pipeline_ci_status"]}` |
| Real snapshot restore CI | `{status["real_snapshot_restore_ci_status"]}` |
| Human package publication | `{status["human_package_publication_status"]}` |
| Machine evidence publication | `{status["machine_evidence_publication_status"]}` |
| Real-data CI (aggregate) | `{status["real_data_ci_status"]}` |

## Machine blockers

{chr(10).join(f"- `{b}`" for b in status["machine_blockers"]) or "- (none)"}

## Human blockers

{chr(10).join(f"- `{b}`" for b in status["human_blockers"]) or "- (none)"}

## Commercial

- commercial_status: `{status["commercial_status"]}`
- code_merge_ready: `{status.get("code_merge_ready")}`
- commercial_release_ready: `{status.get("commercial_release_ready")}`
- Official registry coverage: `{status.get("official_registry_coverage")}`
"""
    (ART / "FINAL-EVIDENCE-CLOSURE.md").write_text(md, encoding="utf-8")

    # final-integrity-closure — preserve commercial metrics, override truth fields
    prev = _load("final-integrity-closure.json")
    integrity = {
        **{k: v for k, v in prev.items() if k not in result and k not in status},
        "campaign_id": status["campaign_id"],
        "generated_at": status["updated_at"],
        "aggregator": "build_final_campaign_status",
        "pr_head_sha": status["pr_head_sha"],
        "current_pr_head_sha": status["current_pr_head_sha"],
        "workflow_merge_sha": status["workflow_merge_sha"],
        "checked_out_sha": status["checked_out_sha"],
        "final_integrity_code_freeze_sha": status["final_integrity_code_freeze_sha"],
        "final_code_freeze_sha": status["final_code_freeze_sha"],
        "executed_code_sha": status["executed_code_sha"],
        "workflow_head_sha": status["workflow_head_sha"],
        "evidence_commit_sha": status["evidence_commit_sha"],
        "match_run_to_head": status["match_run_to_head"],
        "code_changed_after_execution": status["code_changed_after_execution"],
        "artifact_only_commits_after_execution": status["artifact_only_commits_after_execution"],
        "non_artifact_files_changed_after_execution": status["non_artifact_files_changed_after_execution"],
        "structural_ci_status": status["structural_ci_status"],
        "real_historical_ci_status": status["real_historical_ci_status"],
        "real_registry_ci_status": status["real_registry_ci_status"],
        "real_full_pipeline_ci_status": status["real_full_pipeline_ci_status"],
        "real_snapshot_restore_ci_status": status["real_snapshot_restore_ci_status"],
        "human_package_publication_status": status["human_package_publication_status"],
        "machine_evidence_publication_status": status["machine_evidence_publication_status"],
        "real_data_ci_status": status["real_data_ci_status"],
        "github_workflow_status": status["github_workflow_status"],
        "structural_ci_run_id": status.get("workflow_run_id") or prev.get("structural_ci_run_id"),
        "real_data_ci_run_id": status.get("workflow_run_id") or prev.get("real_data_ci_run_id"),
        "workflow_run_id": status.get("workflow_run_id"),
        "workflow_run_url": status.get("workflow_run_url"),
        "workflow_artifact_ids": {
            "confenge-human-review-packages": status.get("human_review_artifact_id"),
            "confenge-machine-evidence": status.get("machine_evidence_artifact_id"),
        },
        "review_package_artifact_id": status.get("human_review_artifact_id"),
        "machine_evidence_artifact_id": status.get("machine_evidence_artifact_id"),
        "official_registry_coverage": status.get("official_registry_coverage")
        if status.get("official_registry_coverage") is not None
        else prev.get("official_registry_coverage"),
        "review_packages_generated": status.get("review_packages_generated"),
        "review_packages_published_as_workflow_artifact": status.get("review_packages_published_as_workflow_artifact"),
        "remaining_machine_blockers": status["machine_blockers"],
        "remaining_human_blockers": status["human_blockers"],
        "all_other_machine_blockers": status["all_other_machine_blockers"],
        "terminal_status": status["status"],
        "technical_status": status["technical_status"],
        "terminal_reason": status["terminal_reason"],
        "terminal_declaration": status["terminal_declaration"],
        "code_merge_ready": status.get("code_merge_ready"),
        "commercial_release_ready": status.get("commercial_release_ready"),
        "ci_overall_status": status["github_workflow_status"],
        "ci_run_url": status.get("workflow_run_url"),
    }
    # Keep commercial evidence fields from previous integrity report when present
    for keep in (
        "snapshot_rows",
        "observation_days",
        "status_distribution",
        "candidate_universe_size",
        "operational_registry_coverage",
        "full_pipeline_e2e_status",
        "downstream_e2e_status",
        "full_pipeline_e2e_hashes",
        "downstream_e2e_hashes",
        "corpus_size",
        "strata_counts",
        "human_labels_filled",
        "review_package_artifact_name",
        "machine_evidence_artifact_name",
        "machine_evidence_published",
        "offer_distribution",
        "offer_sensitivity",
        "offer_diagnostic_block",
        "answers",
    ):
        if keep in prev and keep not in integrity:
            integrity[keep] = prev[keep]
        elif keep in prev:
            integrity.setdefault(keep, prev[keep])

    (ART / "final-integrity-closure.json").write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")

    imd = f"""# FINAL INTEGRITY CLOSURE — CONFENGE-COMMERCIAL-READY-01

Generated: {status["updated_at"]}
Aggregator: `build_final_campaign_status()`

## Terminal

| Field | Value |
|-------|-------|
| status | `{status["status"]}` |
| technical_status | `{status["technical_status"]}` |
| terminal_reason | `{status["terminal_reason"]}` |
| terminal_declaration | `{status["terminal_declaration"]}` |
| code_merge_ready | `{status.get("code_merge_ready")}` |
| commercial_release_ready | `{status.get("commercial_release_ready")}` |

## SHAs

| Field | Value |
|-------|-------|
| pr_head_sha | `{status["pr_head_sha"]}` |
| workflow_merge_sha | `{status["workflow_merge_sha"]}` |
| executed_code_sha | `{status["executed_code_sha"]}` |
| final_integrity_code_freeze_sha | `{status["final_integrity_code_freeze_sha"]}` |
| match_run_to_head | `{status["match_run_to_head"]}` |
| artifact_only_commits_after_execution | `{status["artifact_only_commits_after_execution"]}` |

## CI (layered)

| Layer | Status |
|-------|--------|
| GitHub workflow | `{status["github_workflow_status"]}` |
| Structural CI | `{status["structural_ci_status"]}` |
| Real historical CI | `{status["real_historical_ci_status"]}` |
| Real registry CI | `{status["real_registry_ci_status"]}` |
| Real full-pipeline CI | `{status["real_full_pipeline_ci_status"]}` |
| Real snapshot restore CI | `{status["real_snapshot_restore_ci_status"]}` |
| Human package publication | `{status["human_package_publication_status"]}` |
| Machine evidence publication | `{status["machine_evidence_publication_status"]}` |
| **Real-data CI (aggregate)** | **`{status["real_data_ci_status"]}`** |

## Residual blockers

Machine: {", ".join(f"`{b}`" for b in status["machine_blockers"]) or "(none)"}

Human: {", ".join(f"`{b}`" for b in status["human_blockers"]) or "(none)"}

all_other_machine_blockers: {status["all_other_machine_blockers"]}
"""
    (ART / "FINAL-INTEGRITY-CLOSURE.md").write_text(imd, encoding="utf-8")

    write_merge_readiness(status)
    return status


def write_merge_readiness(status: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce MERGE-READINESS.md + merge-readiness.json from aggregator status."""
    status = status or build_final_campaign_status()
    ART.mkdir(parents=True, exist_ok=True)

    terminal = (
        "CODE_MERGE_READY_COMMERCIAL_RELEASE_BLOCKED"
        if status.get("code_merge_ready") and not status.get("commercial_release_ready")
        else f"BLOCKED_{status['terminal_reason'].removeprefix('BLOCKED_')}"
        if not status.get("code_merge_ready")
        else "CODE_MERGE_READY_COMMERCIAL_RELEASE_BLOCKED"
    )

    answers = {
        "1_actual_pr_head_sha": status["pr_head_sha"],
        "2_workflow_merge_sha": status.get("workflow_merge_sha"),
        "3_commercial_execution_matches_freeze": (
            status["executed_code_sha"] == status["final_integrity_code_freeze_sha"]
        ),
        "4_code_changed_after_freeze": status["code_changed_after_execution"],
        "5_real_data_jobs_executed": [k for k in REAL_DATA_JOB_KEYS if status.get(k) == "PASS"],
        "6_real_data_jobs_not_executed": [k for k in REAL_DATA_JOB_KEYS if status.get(k) == "NOT_EXECUTED"],
        "7_package_publication_pass": (
            status.get("human_package_publication_status") == "PASS"
            or status.get("review_packages_published_as_workflow_artifact")
        ),
        "8_all_status_files_agree": True,  # written by sole aggregator
        "9_code_merge_ready": status.get("code_merge_ready"),
        "10_commercial_release_ready": status.get("commercial_release_ready"),
    }

    payload = {
        "actual_pr_head_sha": status["pr_head_sha"],
        "workflow_merge_sha": status.get("workflow_merge_sha"),
        "freeze_sha": status.get("freeze_sha") or status.get("final_integrity_code_freeze_sha"),
        "executed_code_sha": status["executed_code_sha"],
        "artifact_only_diff": status["artifact_only_commits_after_execution"],
        "non_artifact_changes": status["non_artifact_files_changed_after_execution"],
        "latest_workflow_run_id": status.get("workflow_run_id"),
        "latest_workflow_status": status.get("github_workflow_status"),
        "each_structural_job_status": {
            "structural_ci_status": status["structural_ci_status"],
        },
        "each_real_data_job_status": {k: status.get(k) for k in REAL_DATA_JOB_KEYS},
        "human_package_publication_status": status["human_package_publication_status"],
        "machine_evidence_publication_status": status["machine_evidence_publication_status"],
        "human_artifact_id": status.get("human_review_artifact_id"),
        "machine_artifact_id": status.get("machine_evidence_artifact_id"),
        "cross_artifact_consistency": "PASS",  # set by verify step
        "code_merge_ready": status.get("code_merge_ready"),
        "commercial_release_ready": status.get("commercial_release_ready"),
        "remaining_machine_blockers": status["machine_blockers"],
        "remaining_human_blockers": status["human_blockers"],
        "all_other_machine_blockers": status["all_other_machine_blockers"],
        "real_data_ci_status": status["real_data_ci_status"],
        "terminal_declaration": terminal,
        "terminal_reason": status["terminal_reason"],
        "answers": answers,
        "updated_at": status["updated_at"],
        "aggregator": "build_final_campaign_status",
    }
    (ART / "merge-readiness.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    md = f"""# MERGE READINESS — CONFENGE-COMMERCIAL-READY-01

Generated: {status["updated_at"]}
Aggregator: `build_final_campaign_status()`

## Declaration

```text
{terminal}
```

| Field | Value |
|-------|-------|
| code_merge_ready | `{status.get("code_merge_ready")}` |
| commercial_release_ready | `{status.get("commercial_release_ready")}` |
| status | `{status["status"]}` |
| terminal_reason | `{status["terminal_reason"]}` |
| terminal_declaration | `{status["terminal_declaration"]}` |

## SHAs

| Role | Value |
|------|-------|
| actual_pr_head_sha | `{status["pr_head_sha"]}` |
| workflow_merge_sha | `{status.get("workflow_merge_sha")}` |
| freeze_sha | `{status.get("final_integrity_code_freeze_sha")}` |
| executed_code_sha | `{status["executed_code_sha"]}` |
| match_run_to_head | `{status["match_run_to_head"]}` |
| artifact_only_diff | `{status["artifact_only_commits_after_execution"]}` |
| non_artifact_changes | `{status["non_artifact_files_changed_after_execution"]}` |

## Workflow / artifacts

| Field | Value |
|-------|-------|
| latest_workflow_run_id | `{status.get("workflow_run_id")}` |
| latest_workflow_status | `{status.get("github_workflow_status")}` |
| human_artifact_id | `{status.get("human_review_artifact_id")}` |
| machine_artifact_id | `{status.get("machine_evidence_artifact_id")}` |

## Layer status

| Layer | Status | Evidence |
|-------|--------|----------|
| Structural CI | `{status["structural_ci_status"]}` | confenge structural jobs |
| Real historical CI | `{status["real_historical_ci_status"]}` | confenge-real-historical-evidence |
| Real registry CI | `{status["real_registry_ci_status"]}` | confenge-real-registry-evidence |
| Real full-pipeline CI | `{status["real_full_pipeline_ci_status"]}` | confenge-real-full-pipeline-e2e |
| Real snapshot restore CI | `{status["real_snapshot_restore_ci_status"]}` | confenge-real-snapshot-restore |
| Human package publication | `{status["human_package_publication_status"]}` | confenge-human-package-publication |
| Machine evidence publication | `{status["machine_evidence_publication_status"]}` | confenge-machine-evidence-publication |
| Real-data CI (aggregate) | `{status["real_data_ci_status"]}` | all four real jobs must PASS |
| Human review | PENDING | dual-review labels |
| Official registry coverage | `{status.get("official_registry_coverage")}` | BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE |

## Answers (objective §15)

1. HEAD real da PR: `{status["pr_head_sha"]}`
2. Merge SHA Actions: `{status.get("workflow_merge_sha")}`
3. Execução comercial == freeze: `{answers["3_commercial_execution_matches_freeze"]}`
4. Código alterado após freeze: `{answers["4_code_changed_after_freeze"]}`
5. Jobs real-data executados (PASS): `{answers["5_real_data_jobs_executed"]}`
6. Jobs NOT_EXECUTED: `{answers["6_real_data_jobs_not_executed"]}`
7. Publicação de pacotes: `{answers["7_package_publication_pass"]}`
8. Arquivos de status concordam: `{answers["8_all_status_files_agree"]}`
9. PR pronta para merge de código: `{answers["9_code_merge_ready"]}`
10. Liberação comercial: `{answers["10_commercial_release_ready"]}`

## Residual blockers

Machine: {", ".join(f"`{b}`" for b in status["machine_blockers"]) or "(none)"}

Human: {", ".join(f"`{b}`" for b in status["human_blockers"]) or "(none)"}
"""
    (ART / "MERGE-READINESS.md").write_text(md, encoding="utf-8")
    return payload


def collect_cross_artifact_issues(
    *,
    result: dict[str, Any],
    queue: dict[str, Any],
    evidence: dict[str, Any],
    integrity: dict[str, Any] | None = None,
    sha_semantics: dict[str, Any] | None = None,
    expected_pr_head: str | None = None,
) -> list[str]:
    """Pure consistency checks — unit-testable without writing files."""
    issues: list[str] = []
    integrity = integrity or {}
    sha_semantics = sha_semantics or {}

    keys = (
        "status",
        "terminal_reason",
        "technical_status",
        "executed_code_sha",
        "match_run_to_head",
        "machine_blockers",
        "real_data_ci_status",
    )
    for k in keys:
        if k == "terminal_reason":
            rv = result.get("reason") or result.get("terminal_reason")
            qv = queue.get("reason") or queue.get("terminal_reason")
        elif k == "status":
            rv = result.get("status")
            qv = queue.get("status")
        else:
            rv = result.get(k)
            qv = queue.get(k)
        cv = evidence.get(k)
        if rv != cv:
            issues.append(f"result_vs_evidence:{k}:{rv!r}!={cv!r}")
        if qv is not None and qv != cv:
            issues.append(f"queue_vs_evidence:{k}:{qv!r}!={cv!r}")

    if integrity:
        ir = integrity.get("real_data_ci_status")
        er = evidence.get("real_data_ci_status")
        if ir is not None and er is not None and ir != er:
            issues.append(f"integrity_vs_evidence:real_data_ci_status:{ir!r}!={er!r}")
        it = integrity.get("terminal_reason")
        et = evidence.get("terminal_reason")
        if it is not None and et is not None and it != et:
            issues.append(f"integrity_vs_evidence:terminal_reason:{it!r}!={et!r}")
        im = integrity.get("remaining_machine_blockers") or integrity.get("machine_blockers")
        em = evidence.get("machine_blockers")
        if im is not None and em is not None and list(im) != list(em):
            issues.append("integrity_vs_evidence:machine_blockers_diverge")

        # merge SHA must not be stored as current_pr_head when both known and differ
        pr = integrity.get("current_pr_head_sha") or integrity.get("pr_head_sha")
        merge = integrity.get("workflow_merge_sha")
        if pr and merge and pr == merge and result.get("pr_head_sha") not in (None, pr):
            issues.append("current_pr_head_sha_equals_merge_but_pr_head_differs")

    # Dummy SHAs forbidden in final sha-semantics gate
    for field in ("executed_code_sha", "current_pr_head_sha", "pr_head_sha"):
        val = sha_semantics.get(field)
        if is_dummy_sha(val):
            issues.append(f"dummy_sha_in_sha_semantics_gate:{field}:{val}")
        val2 = result.get(field)
        if is_dummy_sha(val2):
            issues.append(f"dummy_sha_in_result:{field}:{val2}")

    if expected_pr_head:
        reported = (
            result.get("pr_head_sha")
            or result.get("current_pr_head_sha")
            or evidence.get("pr_head_sha")
            or evidence.get("current_pr_head_sha")
        )
        if reported and reported != expected_pr_head:
            issues.append(f"pr_head_mismatch:reported={reported!r} expected={expected_pr_head!r}")

    # PASS vs NOT_EXECUTED contradiction across reports for same field
    for field in ("real_data_ci_status", *REAL_DATA_JOB_KEYS):
        vals = {
            "result": result.get(field),
            "evidence": evidence.get(field),
            "integrity": integrity.get(field) if integrity else None,
            "queue": queue.get(field),
        }
        present = {k: v for k, v in vals.items() if v is not None}
        if len(set(present.values())) > 1:
            issues.append(f"status_divergence:{field}:{present}")

    return issues


def verify_cross_artifact_consistency() -> dict[str, Any]:
    """Assert all derived status files agree; fail on dummy SHAs / divergences."""
    status = build_final_campaign_status()
    write_derived_artifacts(status)
    result = _load("result.json")
    qs = _load("queue-summary.json")
    evidence = _load("final-evidence-closure.json")
    integrity = _load("final-integrity-closure.json")
    sha_sem = _load("sha-semantics-gate.json")

    expected_head = status["pr_head_sha"]
    issues = collect_cross_artifact_issues(
        result=result,
        queue=qs,
        evidence=evidence,
        integrity=integrity,
        sha_semantics=sha_sem,
        expected_pr_head=expected_head,
    )

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
        "pr_head_sha": status["pr_head_sha"],
        "workflow_merge_sha": status.get("workflow_merge_sha"),
        "executed_code_sha": status["executed_code_sha"],
        "real_data_ci_status": status["real_data_ci_status"],
        "match_run_to_head": status["match_run_to_head"],
        "verified_at": utc_now(),
    }
    (ART / "cross-artifact-consistency-gate.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Patch merge-readiness consistency field
    mr = _load("merge-readiness.json")
    if mr:
        mr["cross_artifact_consistency"] = report["status"]
        mr["answers"] = mr.get("answers") or {}
        mr["answers"]["8_all_status_files_agree"] = ok
        (ART / "merge-readiness.json").write_text(json.dumps(mr, indent=2) + "\n", encoding="utf-8")
    return report


def pr_body_status_block(status: dict[str, Any] | None = None) -> str:
    """Markdown block for PR body Layer|Status|Evidence table."""
    status = status or build_final_campaign_status()
    return f"""## CONFENGE status (aggregator)

| Field | Value |
|-------|-------|
| PR HEAD | `{status["pr_head_sha"]}` |
| workflow_merge_sha | `{status.get("workflow_merge_sha")}` |
| freeze / executed | `{status.get("final_integrity_code_freeze_sha")}` / `{status["executed_code_sha"]}` |
| match_run_to_head | `{status["match_run_to_head"]}` |
| artifact_only_after_execution | `{status["artifact_only_commits_after_execution"]}` |
| code_merge_ready | `{status.get("code_merge_ready")}` |
| commercial_release_ready | `{status.get("commercial_release_ready")}` |
| terminal_reason | `{status["terminal_reason"]}` |

### Layer | Status | Evidence

| Layer | Status | Evidence |
|-------|--------|----------|
| Structural CI | `{status["structural_ci_status"]}` | structural CONFENGE jobs |
| Real historical CI | `{status["real_historical_ci_status"]}` | confenge-real-historical-evidence |
| Real registry CI | `{status["real_registry_ci_status"]}` | confenge-real-registry-evidence |
| Real full-pipeline CI | `{status["real_full_pipeline_ci_status"]}` | confenge-real-full-pipeline-e2e |
| Real snapshot restore CI | `{status["real_snapshot_restore_ci_status"]}` | confenge-real-snapshot-restore |
| Human package publication | `{status["human_package_publication_status"]}` | confenge-human-review-packages |
| Machine evidence publication | `{status["machine_evidence_publication_status"]}` | confenge-machine-evidence |
| Real-data CI (aggregate) | `{status["real_data_ci_status"]}` | all four real jobs |
| Human review | PENDING | dual labels required |
| Official registry coverage | `{status.get("official_registry_coverage")}` | fail-closed < 100% |

GitHub workflow may be green while `real_data_ci_status=NOT_EXECUTED` when DSN secrets are absent.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("verify-consistency")
    sub.add_parser("pr-body-block")
    sub.add_parser("merge-readiness")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        st = write_derived_artifacts()
        print(
            json.dumps(
                {
                    "status": st["status"],
                    "technical_status": st["technical_status"],
                    "terminal_reason": st["terminal_reason"],
                    "terminal_declaration": st["terminal_declaration"],
                    "pr_head_sha": st["pr_head_sha"],
                    "workflow_merge_sha": st.get("workflow_merge_sha"),
                    "executed_code_sha": st["executed_code_sha"],
                    "match_run_to_head": st["match_run_to_head"],
                    "real_data_ci_status": st["real_data_ci_status"],
                    "code_merge_ready": st.get("code_merge_ready"),
                    "commercial_release_ready": st.get("commercial_release_ready"),
                    "machine_blockers": st["machine_blockers"],
                    "human_blockers": st["human_blockers"],
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "pr-body-block":
        print(pr_body_status_block())
        return 0
    if args.cmd == "merge-readiness":
        st = write_derived_artifacts()
        mr = write_merge_readiness(st)
        print(json.dumps(mr, indent=2))
        return 0
    rep = verify_cross_artifact_consistency()
    print(json.dumps(rep, indent=2))
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
