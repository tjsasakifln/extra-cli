#!/usr/bin/env python3
"""Fail closed if campaign docs stamps drift from dual truth on main.

Design notes
------------
A pure docs merge advances ``origin/main`` without changing dual metrics.
Requiring stamp docs to always equal HEAD would force an infinite restamp
loop. Therefore this gate checks:

1. Honest dual metrics in ``evidence/dual-reproof-summary.json``
   (measurement_success=false, mapping_status=identity_unresolved, …)
   until identity is fixed (``--allow-measurement-true``).
2. Evidence ``git_sha`` is an **ancestor of or equal to** ``origin/main``
   (i.e. the snapshot was taken on a commit that is still on main history).
3. Stamp docs mention that evidence SHA (full or 12-char prefix).
4. Stamp docs do not claim measurement_success=true / mapping ok while the
   locked honest state still applies.

Usage:
  python3 docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/scripts/check_campaign_stamp_consistency.py
  python3 .../check_campaign_stamp_consistency.py --repo-root /path
  python3 .../check_campaign_stamp_consistency.py --allow-measurement-true
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

EXPECTED_MEASUREMENT_SUCCESS = False
EXPECTED_MAPPING_STATUS = "identity_unresolved"
EXPECTED_IDENTITY_UNRESOLVED_COUNT = 4
EXPECTED_DUAL_GATE = "NOT_READY"


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def _is_ancestor(repo: Path, maybe_ancestor: str, descendant: str) -> bool:
    """True if maybe_ancestor is ancestor of or equal to descendant."""
    try:
        subprocess.check_call(
            [
                "git",
                "-C",
                str(repo),
                "merge-base",
                "--is-ancestor",
                maybe_ancestor,
                descendant,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument(
        "--allow-measurement-true",
        action="store_true",
        help="Relax honest-state lock after identity_unresolved is fixed",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    if args.repo_root is not None:
        repo = args.repo_root.resolve()
    else:
        candidates = [script_path.parents[5], Path.cwd()]
        repo = next(
            (c for c in candidates if (c / ".git").exists() or (c / "docs").exists()),
            Path.cwd(),
        ).resolve()

    errors: list[str] = []
    notes: list[str] = []
    notes.append(f"repo_root={repo}")

    try:
        origin_main = _run_git(repo, "rev-parse", "origin/main").lower()
    except subprocess.CalledProcessError:
        origin_main = _run_git(repo, "rev-parse", "HEAD").lower()
    notes.append(f"origin/main={origin_main}")

    # --- evidence JSON ---
    evidence_sha = ""
    ev_path = repo / EVIDENCE_JSON
    if not ev_path.is_file():
        errors.append(f"missing_evidence_json:{EVIDENCE_JSON}")
        data = None
    else:
        try:
            data = json.loads(ev_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"evidence_json_invalid:{exc}")
            data = None

    if data is not None:
        u = data.get("universe") or {}
        evidence_sha = str(u.get("git_sha") or data.get("git_sha") or "").lower()
        if not evidence_sha:
            errors.append("evidence_missing_git_sha")
        else:
            notes.append(f"evidence.git_sha={evidence_sha}")
            if not _is_ancestor(repo, evidence_sha, origin_main):
                errors.append(
                    f"evidence_git_sha_not_on_main:evidence={evidence_sha}:main={origin_main}"
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
            if ms is True and map_status == "identity_unresolved":
                errors.append(
                    "evidence_incoherent:measurement_true_with_identity_unresolved"
                )

        for cap_name, cap in (data.get("capabilities") or {}).items():
            if ms is False and cap.get("measurement_success") is True:
                errors.append(f"cap_measurement_incoherent:{cap_name}:cap_true_report_false")

    # --- stamp docs must mention evidence SHA (not necessarily HEAD) ---
    sha_to_find = evidence_sha or origin_main
    short = sha_to_find[:12] if sha_to_find else ""
    for rel in STAMP_DOCS + OPTIONAL_DOCS:
        path = repo / rel
        if not path.is_file():
            if rel in OPTIONAL_DOCS:
                notes.append(f"optional_missing={rel}")
                continue
            errors.append(f"missing_stamp_doc:{rel}")
            continue
        text = _read(path)
        if short and short not in text and sha_to_find not in text:
            errors.append(f"evidence_sha_missing_in_doc:{rel}:expected_prefix={short}")
        if rel.name in {"NEXT-DOD-PATH.md", "STATUS.md", "README-REPROOF.md"}:
            if re.search(
                r"measurement_success\s*\|\s*\*?\*?true\*?\*?",
                text,
                flags=re.IGNORECASE,
            ):
                if not args.allow_measurement_true:
                    errors.append(f"stale_measurement_true_claim:{rel}")
            if re.search(
                r"mapping_status\s*\|\s*\*?\*?ok\*?\*?",
                text,
                flags=re.IGNORECASE,
            ):
                if not args.allow_measurement_true:
                    errors.append(f"stale_mapping_ok_claim:{rel}")

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
