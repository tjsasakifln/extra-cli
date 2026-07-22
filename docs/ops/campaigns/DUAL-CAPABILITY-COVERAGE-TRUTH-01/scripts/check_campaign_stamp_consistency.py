#!/usr/bin/env python3
"""Fail closed if campaign docs stamps drift from origin/main + live dual evidence.

Canonical stamps checked in:
  - NEXT-DOD-PATH.md
  - STATUS.md
  - evidence/README-REPROOF.md
  - evidence/dual-reproof-summary.json
  - specs/001-dual-capability-coverage-truth/converge-report.md (if present)

Exit 0 only when all of the following hold:
  * expected main tip SHA appears in the stamp docs
  * dual-reproof-summary.json git_sha == expected tip
  * dual-reproof-summary measurement_success is false (current honest state)
  * mapping_status == identity_unresolved with identity_unresolved_count == 4
  * no stale "measurement_success=true" claim without identity resolution in stamp docs

Usage:
  python3 docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/scripts/check_campaign_stamp_consistency.py
  python3 .../check_campaign_stamp_consistency.py --expected-main-sha 3ab3a3a...
  python3 .../check_campaign_stamp_consistency.py --repo-root /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CAMPAIGN = Path("docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01")
STAMP_DOCS = [
    CAMPAIGN / "NEXT-DOD-PATH.md",
    CAMPAIGN / "STATUS.md",
    CAMPAIGN / "evidence" / "README-REPROOF.md",
]
OPTIONAL_DOCS = [
    Path("specs/001-dual-capability-coverage-truth/converge-report.md"),
]
EVIDENCE_JSON = CAMPAIGN / "evidence" / "dual-reproof-summary.json"

# Honest live state on main tip at campaign closure (identity not resolved yet).
EXPECTED_MEASUREMENT_SUCCESS = False
EXPECTED_MAPPING_STATUS = "identity_unresolved"
EXPECTED_IDENTITY_UNRESOLVED_COUNT = 4
EXPECTED_DUAL_GATE = "NOT_READY"


def _run_git(repo: Path, *args: str) -> str:
    out = subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
        stderr=subprocess.STDOUT,
    )
    return out.strip()


def _resolve_expected_sha(repo: Path, explicit: str | None) -> str:
    if explicit:
        return explicit.strip().lower()
    try:
        return _run_git(repo, "rev-parse", "origin/main").lower()
    except subprocess.CalledProcessError:
        return _run_git(repo, "rev-parse", "HEAD").lower()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: discover from script location or cwd)",
    )
    parser.add_argument(
        "--expected-main-sha",
        default=None,
        help="Full or prefix SHA expected in stamp docs (default: origin/main)",
    )
    parser.add_argument(
        "--allow-measurement-true",
        action="store_true",
        help="Relax gate if identity has been fixed and measurement_success is true",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo = args.repo_root
    if repo is None:
        # .../docs/ops/campaigns/DUAL-.../scripts/this.py → repo root is parents[5]
        candidates = [
            script_path.parents[5],
            Path.cwd(),
        ]
        repo = next((c for c in candidates if (c / ".git").exists() or (c / "docs").exists()), Path.cwd())
    repo = repo.resolve()

    errors: list[str] = []
    notes: list[str] = []

    expected = _resolve_expected_sha(repo, args.expected_main_sha)
    short = expected[:12]
    notes.append(f"expected_main_sha={expected}")
    notes.append(f"repo_root={repo}")

    # --- stamp docs must contain tip SHA ---
    for rel in STAMP_DOCS + OPTIONAL_DOCS:
        path = repo / rel
        if not path.is_file():
            if rel in OPTIONAL_DOCS:
                notes.append(f"optional_missing={rel}")
                continue
            errors.append(f"missing_stamp_doc:{rel}")
            continue
        text = _read(path)
        if short not in text and expected not in text:
            errors.append(f"sha_missing_in_doc:{rel}:expected_prefix={short}")
        # Forbid optimistic stale claims in active stamp docs
        if rel.name in {"NEXT-DOD-PATH.md", "STATUS.md", "README-REPROOF.md"}:
            # measurement_success | true (markdown table or prose) as current state
            if re.search(
                r"measurement_success\s*\|\s*\*?\*?true\*?\*?",
                text,
                flags=re.IGNORECASE,
            ):
                if not args.allow_measurement_true:
                    errors.append(f"stale_measurement_true_claim:{rel}")
            if re.search(r"mapping_status\s*\|\s*\*?\*?ok\*?\*?", text, flags=re.IGNORECASE):
                if not args.allow_measurement_true:
                    errors.append(f"stale_mapping_ok_claim:{rel}")

    # --- evidence JSON must match tip + honest identity state ---
    ev_path = repo / EVIDENCE_JSON
    if not ev_path.is_file():
        errors.append(f"missing_evidence_json:{EVIDENCE_JSON}")
    else:
        try:
            data = json.loads(ev_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"evidence_json_invalid:{exc}")
            data = None
        if data is not None:
            u = data.get("universe") or {}
            git_sha = str(u.get("git_sha") or data.get("git_sha") or "").lower()
            if not git_sha:
                errors.append("evidence_missing_git_sha")
            elif not (git_sha == expected or expected.startswith(git_sha) or git_sha.startswith(short)):
                errors.append(
                    f"evidence_git_sha_mismatch:actual={git_sha}:expected={expected}"
                )
            ms = data.get("measurement_success")
            mm = data.get("mapping_metrics") or {}
            map_status = mm.get("mapping_status")
            iuc = mm.get("identity_unresolved_count")
            dgs = data.get("dual_gate_status")

            notes.append(f"evidence.measurement_success={ms}")
            notes.append(f"evidence.mapping_status={map_status}")
            notes.append(f"evidence.identity_unresolved_count={iuc}")
            notes.append(f"evidence.dual_gate_status={dgs}")

            if not args.allow_measurement_true:
                if ms is not EXPECTED_MEASUREMENT_SUCCESS:
                    errors.append(
                        f"evidence_measurement_success:actual={ms}:expected={EXPECTED_MEASUREMENT_SUCCESS}"
                    )
                if map_status != EXPECTED_MAPPING_STATUS:
                    errors.append(
                        f"evidence_mapping_status:actual={map_status}:expected={EXPECTED_MAPPING_STATUS}"
                    )
                if iuc != EXPECTED_IDENTITY_UNRESOLVED_COUNT:
                    errors.append(
                        f"evidence_identity_unresolved_count:actual={iuc}:expected={EXPECTED_IDENTITY_UNRESOLVED_COUNT}"
                    )
                if dgs != EXPECTED_DUAL_GATE:
                    errors.append(
                        f"evidence_dual_gate_status:actual={dgs}:expected={EXPECTED_DUAL_GATE}"
                    )
            else:
                # When identity is fixed, require measurement honesty still be self-consistent
                if ms is True and map_status == "identity_unresolved":
                    errors.append("evidence_incoherent:measurement_true_with_identity_unresolved")

            # Caps must not claim measurement_success true while report is false
            for cap_name, cap in (data.get("capabilities") or {}).items():
                cap_ms = cap.get("measurement_success")
                if ms is False and cap_ms is True:
                    errors.append(f"cap_measurement_incoherent:{cap_name}:cap_true_report_false")

    # --- optional: origin/main equals expected ---
    try:
        tip = _run_git(repo, "rev-parse", "origin/main").lower()
        notes.append(f"origin/main={tip}")
        if tip != expected and not args.expected_main_sha:
            errors.append(f"origin_main_drift:origin={tip}:resolved={expected}")
    except subprocess.CalledProcessError as exc:
        notes.append(f"git_origin_main_unavailable:{exc}")

    print("=== campaign stamp consistency ===")
    for n in notes:
        print(f"NOTE  {n}")
    if errors:
        for e in errors:
            print(f"FAIL  {e}")
        print(f"RESULT FAIL count={len(errors)}")
        return 1
    print("RESULT PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
