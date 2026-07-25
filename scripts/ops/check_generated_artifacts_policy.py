"""Fail-closed gate: prohibit heavy/reproducible generated outputs in Git.

Usage:
  python -m scripts.ops.check_generated_artifacts_policy
  python -m scripts.ops.check_generated_artifacts_policy --base origin/main
  python -m scripts.ops.check_generated_artifacts_policy --paths path1 path2

Exit 0 = pass, 1 = violations, 2 = usage/error.

Compares the PR (or local) diff against the real base ref. Files already present
on the base are ignored; only added/modified paths in the diff are checked.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MAX_BYTES = 512 * 1024
SMALL_EVIDENCE_MAX = 256 * 1024
FIXTURE_MAX = 100 * 1024
CSV_MAX = 64 * 1024

BANNED_SUFFIXES = (
    ".pdf",
    ".xlsx",
    ".xls",
    ".docx",
    ".dump",
    ".log",
    ".sql.dump",
)
BANNED_NAMES = {
    "pack-full.json",
    "monthly-monitor-live.json",
    "cycle-state.json",
    "tests.xml",
    "junit.xml",
}
BANNED_PREFIX_MARKERS = (
    "/pack-rc/",
    "/pack-verify/",
    "/pack-full/",
)
BANNED_NAME_PREFIXES = ("deliverable_",)

# Small durable evidence allowed under artifacts/campaigns (size-capped).
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
    "ARTIFACT-IDENTITY.json",
}

EXCEPTION_REQUIRED_FIELDS = ("path", "reason", "owner", "deadline", "max_bytes")


def _git_bin() -> str:
    return shutil.which("git") or "git"


def _run_git(args: list[str]) -> str:
    cmd = [_git_bin(), *args]
    return subprocess.check_output(  # noqa: S603
        cmd,
        cwd=REPO_ROOT,
        text=True,
        stderr=subprocess.DEVNULL,
    )


def _load_exceptions() -> tuple[dict[str, int], list[str]]:
    """Return (path -> max_bytes, registry_errors). Fail closed on bad registry."""
    path = REPO_ROOT / "docs" / "generated-artifacts-exceptions.json"
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"exceptions_json_invalid:{exc}"]

    errors: list[str] = []
    out: dict[str, int] = {}
    for i, ex in enumerate(data.get("exceptions") or []):
        if not isinstance(ex, dict):
            errors.append(f"exception[{i}]:not_object")
            continue
        missing = [f for f in EXCEPTION_REQUIRED_FIELDS if not ex.get(f)]
        if missing:
            errors.append(
                f"exception[{i}]:missing_fields:{','.join(missing)} "
                f"(path={ex.get('path')!r})"
            )
            continue
        deadline = str(ex["deadline"])
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", deadline):
            errors.append(f"exception[{i}]:invalid_deadline:{deadline}")
            continue
        p = str(ex["path"])
        try:
            mb = int(ex["max_bytes"])
        except (TypeError, ValueError):
            errors.append(f"exception[{i}]:invalid_max_bytes")
            continue
        if mb <= 0:
            errors.append(f"exception[{i}]:max_bytes_must_be_positive")
            continue
        out[p] = mb
    return out, errors


def _git_diff_names(base: str) -> list[str]:
    """Added/modified paths in the merge-base...HEAD range (PR-introduced only)."""
    try:
        out = _run_git(["diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD"])
    except subprocess.CalledProcessError:
        out = _run_git(["diff", "--name-only", "--diff-filter=AM", base])
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _file_size(path: str) -> int | None:
    fp = REPO_ROOT / path
    if fp.is_file():
        return fp.stat().st_size
    try:
        out = _run_git(["cat-file", "-s", f"HEAD:{path}"])
        return int(out.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def classify_violation(
    path: str,
    size: int | None,
    exceptions: dict[str, int],
) -> str | None:
    """Return violation reason or None if allowed."""
    posix = path.replace("\\", "/")
    name = Path(posix).name

    under_campaign = posix.startswith("artifacts/campaigns/")
    under_artifacts = posix.startswith("artifacts/")
    under_output = posix.startswith("output/")

    if under_output:
        return f"output_dir_not_in_git:{posix}"

    if posix in exceptions:
        max_b = exceptions[posix]
        if size is not None and size > max_b:
            return f"exception_exceeded:{size}>{max_b}"
        return None

    # Product / test source: ban large binaries; prefer fixture builders.
    if posix.startswith("tests/"):
        if name.endswith(BANNED_SUFFIXES):
            if size is not None and size > FIXTURE_MAX:
                return f"test_fixture_binary_too_large:{size}>{FIXTURE_MAX}"
        if size is not None and size > DEFAULT_MAX_BYTES:
            return f"test_file_too_large:{size}>{DEFAULT_MAX_BYTES}"
        return None

    if not under_artifacts:
        # Ban product binaries and bulk dumps anywhere in the PR diff.
        if name.endswith(BANNED_SUFFIXES) and not posix.startswith("docs/"):
            return f"banned_suffix_outside_fixtures:{name}"
        if name in BANNED_NAMES:
            return f"banned_name:{name}"
        return None

    # --- under artifacts/ ---
    if name in ALWAYS_ALLOW_NAMES:
        max_b = exceptions.get(posix, SMALL_EVIDENCE_MAX)
        if size is not None and size > max_b:
            return f"allowed_name_but_too_large:{size}>{max_b}"
        return None

    if name.endswith(BANNED_SUFFIXES):
        return f"banned_suffix:{name}"
    if name in BANNED_NAMES:
        return f"banned_name:{name}"
    if any(m in f"/{posix}" for m in BANNED_PREFIX_MARKERS):
        return f"banned_tree:{posix}"
    if any(name.startswith(p) for p in BANNED_NAME_PREFIXES) and name.endswith(
        (".json", ".csv", ".md")
    ):
        return f"banned_deliverable_dump:{name}"
    if "/dossiers/" in posix:
        if name.endswith(".html"):
            return f"banned_dossier_html:{name}"
        if size is not None and size > 32 * 1024:
            return f"dossier_too_large:{size}"
    if name.endswith(".html") and under_campaign:
        return f"banned_campaign_html:{name}"
    if name.endswith(".csv") and under_campaign:
        if size is not None and size > CSV_MAX:
            return f"campaign_csv_too_large:{size}>{CSV_MAX}"
    if size is not None and size > DEFAULT_MAX_BYTES:
        return f"campaign_file_too_large:{size}>{DEFAULT_MAX_BYTES}"
    # Large JSON not in allowlist under campaigns
    if (
        under_campaign
        and name.endswith(".json")
        and size is not None
        and size > SMALL_EVIDENCE_MAX
    ):
        return f"campaign_json_too_large:{size}>{SMALL_EVIDENCE_MAX}"
    return None


def evaluate(paths: list[str]) -> list[dict[str, object]]:
    exceptions, reg_errors = _load_exceptions()
    violations: list[dict[str, object]] = [
        {"path": "docs/generated-artifacts-exceptions.json", "size": None, "reason": e}
        for e in reg_errors
    ]
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
        try:
            paths = _git_diff_names(args.base)
        except subprocess.CalledProcessError as exc:
            print(f"error: git diff failed: {exc}", file=sys.stderr)
            return 2

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
        print(
            f"generated-artifacts-policy: checked={len(paths)} "
            f"violations={len(violations)}"
        )
        for v in violations:
            print(f"  FAIL {v['path']} ({v['size']} bytes) — {v['reason']}")
        if not violations:
            print("  PASS")
        else:
            print(
                "\nActionable: remove generated outputs from the PR, or add an "
                "exception in docs/generated-artifacts-exceptions.json with "
                "path, reason, owner, deadline (YYYY-MM-DD), and max_bytes. "
                "Prefer fixture builders and GitHub Actions artifacts."
            )
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
