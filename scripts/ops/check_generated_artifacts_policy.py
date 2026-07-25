"""Fail-closed gate: prohibit heavy/reproducible campaign outputs in Git.

Usage:
  python -m scripts.ops.check_generated_artifacts_policy
  python -m scripts.ops.check_generated_artifacts_policy --base origin/main
  python -m scripts.ops.check_generated_artifacts_policy --paths path1 path2

Exit 0 = pass, 1 = violations, 2 = usage/error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Per-file ceiling for artifacts/campaigns/**
DEFAULT_MAX_BYTES = 512 * 1024
# Tighter ceiling for binary-like extensions always banned under campaigns
BANNED_SUFFIXES = (".pdf", ".xlsx", ".xls", ".docx", ".dump")
BANNED_NAMES = {
    "pack-full.json",
    "monthly-monitor-live.json",
    "cycle-state.json",
    "tests.xml",
}
BANNED_PREFIX_MARKERS = (
    "/pack-rc/",
    "/pack-verify/",
)
BANNED_NAME_PREFIXES = ("deliverable_",)
ALWAYS_ALLOW_NAMES = {
    "user-acceptance.json",
    "claims.json",
    "non-claims.json",
    "checksums.json",
    "pack-manifest.json",
    "manifest.json",
    "migrations.json",
    "isolation.json",
    "schema.json",
    "baseline.json",
    "baseline.md",
    "coverage.json",
    "security.json",
    "result.json",
    "ambiguity.json",
    "failures.json",
    "performance.json",
    "regression.json",
    "recurrence.json",
    "data-quality.json",
    "source-health.json",
    "linkage-quality.json",
    "linkage-run.json",
    "package-reconciliation.json",
    "requirements-traceability.json",
    "dod-impact.json",
    "investigation.json",
    "key-profile.json",
    "labeled-sample.json",
    "verify-isolated.json",
    "operational-report.json",
    "ci-full-suite-status.json",
    "BLOCKED.md",
    "PASS.md",
    "REVIEW-FOR-TIAGO.md",
    "HUMAN-ACCEPTANCE-INSTRUCTIONS.md",
    "REPRODUCIBLE-OUTPUTS.md",
    "executive-summary.md",
    "executive_summary.md",
    "meeting-support.md",
}


def _load_exceptions() -> dict[str, int]:
    path = REPO_ROOT / "docs" / "generated-artifacts-exceptions.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for ex in data.get("exceptions") or []:
        p = str(ex.get("path") or "")
        mb = int(ex.get("max_bytes") or DEFAULT_MAX_BYTES)
        if p:
            out[p] = mb
    return out


def _git_diff_names(base: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=AM", base],
            cwd=REPO_ROOT,
            text=True,
        )
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _file_size(path: str) -> int | None:
    fp = REPO_ROOT / path
    if fp.is_file():
        return fp.stat().st_size
    # try blob from HEAD
    try:
        out = subprocess.check_output(
            ["git", "cat-file", "-s", f"HEAD:{path}"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return int(out.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def classify_violation(path: str, size: int | None, exceptions: dict[str, int]) -> str | None:
    """Return violation reason or None if allowed."""
    posix = path.replace("\\", "/")
    name = Path(posix).name

    # Only enforce campaign artifact trees + obvious binary deliverables in artifacts/
    under_campaign = posix.startswith("artifacts/campaigns/")
    under_artifacts = posix.startswith("artifacts/")

    if name in ALWAYS_ALLOW_NAMES and under_campaign:
        max_b = exceptions.get(posix, 256 * 1024)
        if size is not None and size > max_b:
            return f"allowed_name_but_too_large:{size}>{max_b}"
        return None

    if posix in exceptions:
        max_b = exceptions[posix]
        if size is not None and size > max_b:
            return f"exception_exceeded:{size}>{max_b}"
        return None

    # tests/fixtures small files always ok outside ban list
    if posix.startswith("tests/"):
        if size is not None and size > 100 * 1024 and name.endswith(BANNED_SUFFIXES):
            return f"test_fixture_binary_too_large:{size}"
        return None

    if not under_artifacts:
        return None

    if not under_campaign:
        # still ban huge binaries at artifacts root
        if name.endswith(BANNED_SUFFIXES) and size is not None and size > 100 * 1024:
            return f"artifacts_binary_banned:{name}"
        return None

    # --- under artifacts/campaigns/ ---
    if name.endswith(BANNED_SUFFIXES):
        return f"banned_suffix:{name}"
    if name in BANNED_NAMES:
        return f"banned_name:{name}"
    if any(m in f"/{posix}" for m in BANNED_PREFIX_MARKERS):
        return f"banned_tree:{posix}"
    if any(name.startswith(p) for p in BANNED_NAME_PREFIXES) and name.endswith(".json"):
        return f"banned_deliverable_dump:{name}"
    if "/dossiers/" in f"/{posix}/" or "/dossiers/" in posix:
        # allow only if tiny and not html
        if name.endswith(".html"):
            return f"banned_dossier_html:{name}"
        if size is not None and size > 32 * 1024:
            return f"dossier_too_large:{size}"
    if name.endswith(".html") and under_campaign:
        return f"banned_campaign_html:{name}"
    if name.endswith(".csv") and under_campaign:
        if size is not None and size > 64 * 1024:
            return f"campaign_csv_too_large:{size}"
    if size is not None and size > DEFAULT_MAX_BYTES:
        return f"campaign_file_too_large:{size}>{DEFAULT_MAX_BYTES}"
    return None


def evaluate(paths: list[str]) -> list[dict[str, object]]:
    exceptions = _load_exceptions()
    violations: list[dict[str, object]] = []
    for path in paths:
        size = _file_size(path)
        reason = classify_violation(path, size, exceptions)
        if reason:
            violations.append({"path": path, "size": size, "reason": reason})
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="git base ref for diff")
    parser.add_argument("--paths", nargs="*", help="explicit paths (skip git diff)")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)

    if args.paths:
        paths = list(args.paths)
    else:
        paths = _git_diff_names(args.base)

    violations = evaluate(paths)
    report = {
        "ok": not violations,
        "checked_paths": len(paths),
        "violation_count": len(violations),
        "violations": violations,
        "policy": "docs/generated-artifacts-policy.md",
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"generated-artifacts-policy: checked={len(paths)} violations={len(violations)}")
        for v in violations:
            print(f"  FAIL {v['path']} ({v['size']} bytes) — {v['reason']}")
        if not violations:
            print("  PASS")
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
