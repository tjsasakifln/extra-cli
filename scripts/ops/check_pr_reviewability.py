"""Fail-closed PR reviewability gate.

Blocks ready-for-review PRs that are too large, multi-capability mega-mixes,
contain product binaries/generated bulk, or declare CI SHA/PASS inconsistently.

Usage:
  python -m scripts.ops.check_pr_reviewability --base origin/main
  python -m scripts.ops.check_pr_reviewability --base origin/main --draft
  python -m scripts.ops.check_pr_reviewability --paths a.py b.py --stats

Exit 0 = pass, 1 = violations, 2 = usage/error.

Classification:
  - migration/sql, tests, docs, and pure config do not alone trigger multi-cap.
  - Multi-capability fires when migrations AND CI AND runtime AND commercial
    deliverable paths appear together without an explicit exception file.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

MAX_FILES_READY = 60
MAX_TEXTUAL_LINES_ADDED = 10_000
EXCEPTION_PATH = "docs/pr-reviewability-exceptions.json"

BINARY_SUFFIXES = (
    ".pdf",
    ".xlsx",
    ".xls",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".zip",
    ".dump",
)

# Path buckets for multi-capability detection
MIGRATION_RE = re.compile(r"^db/migrations/|^scripts/ops/apply_migrations")
CI_RE = re.compile(r"^\.github/workflows/|^Makefile$")
RUNTIME_RE = re.compile(r"^scripts/(?!ops/check_)")
COMMERCIAL_RE = re.compile(
    r"artifacts/campaigns/.*/(pack|deliverable|client-ready|executive)|"
    r"scripts/ops/(live_consulting_pack|client_ready|publish_commercial|"
    r"commercial_executive|deliverable_)"
)

TEXTUAL_SUFFIXES = {
    ".py",
    ".sql",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".txt",
    ".sh",
    ".csv",
    ".feature",
    ".ini",
    ".cfg",
    ".html",
    ".xml",
}


def _git_bin() -> str:
    return shutil.which("git") or "git"


def _run_git(args: list[str]) -> str:
    cmd = [_git_bin(), *args]
    return subprocess.check_output(  # noqa: S603
        cmd,
        cwd=REPO_ROOT,
        text=True,
        stderr=subprocess.PIPE,
    )


def _diff_name_status(base: str) -> list[tuple[str, str]]:
    try:
        out = _run_git(["diff", "--name-status", "--diff-filter=ACMR", f"{base}...HEAD"])
    except subprocess.CalledProcessError:
        out = _run_git(["diff", "--name-status", "--diff-filter=ACMR", base])
    rows: list[tuple[str, str]] = []
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0].strip(), parts[-1].strip()))
    return rows


def _numstat(base: str) -> list[tuple[int, int, str]]:
    try:
        out = _run_git(["diff", "--numstat", f"{base}...HEAD"])
    except subprocess.CalledProcessError:
        out = _run_git(["diff", "--numstat", base])
    rows: list[tuple[int, int, str]] = []
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        if a == "-" or d == "-":
            # binary
            rows.append((-1, -1, path))
        else:
            rows.append((int(a), int(d), path))
    return rows


def _load_exception() -> dict[str, object] | None:
    fp = REPO_ROOT / EXCEPTION_PATH
    if not fp.is_file():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    # Active exception requires human fields
    active = data.get("active")
    if not active:
        return None
    required = ("reason", "owner", "deadline", "approved_by")
    if any(not active.get(k) for k in required):
        return None
    return active


def classify_path(path: str) -> set[str]:
    tags: set[str] = set()
    posix = path.replace("\\", "/")
    if MIGRATION_RE.search(posix) or posix.endswith(".sql") and "migration" in posix:
        tags.add("migration")
    if CI_RE.search(posix):
        tags.add("ci")
    if RUNTIME_RE.search(posix):
        tags.add("runtime")
    if COMMERCIAL_RE.search(posix):
        tags.add("commercial")
    if posix.startswith("tests/"):
        tags.add("tests")
    if posix.startswith("docs/") or posix.startswith("specs/"):
        tags.add("docs")
    return tags


def is_textual(path: str) -> bool:
    return Path(path).suffix.lower() in TEXTUAL_SUFFIXES


# Required canonical CI job names (must match .github/workflows/ci.yml `name:`)
REQUIRED_CANONICAL_CHECKS = (
    "Lint (ruff)",
    "Type Check (mypy)",
    "Test (critical readiness)",
    "Test operational expanded (PR)",
    "Test All (full suite)",
    "Resilience Gate (pre-VPS)",
    "Security (bandit)",
    "Dependency Audit (pip-audit)",
    "Generated Artifacts Policy",
    "PR Reviewability Policy",
    "Pytest Skip Policy",
)

# Match HEAD/CI SHA declarations including Markdown bold/backticks:
#   **HEAD SHA:** `abc123...`
#   HEAD SHA: abc123
#   CI SHA: `abc`
_CLAIMED_SHA_RES = (
    re.compile(
        r"(?is)(?:\*{0,2}|_{0,2})?(?:ci\s+|head\s+)?(?:sha|commit|head)"
        r"(?:\s+sha)?(?:\*{0,2}|_{0,2})?\s*[:=]\s*"
        r"(?:\*{0,2}|_{0,2})?\s*`?([0-9a-f]{7,40})`?",
    ),
    re.compile(
        r"(?is)\*{0,2}head\s+sha\*{0,2}\s*[:=]\s*\*{0,2}\s*`?([0-9a-f]{7,40})`?",
    ),
)


def extract_claimed_head_shas(body: str) -> list[str]:
    """Return claimed HEAD/CI SHAs from PR body (Markdown-aware)."""
    if not body:
        return []
    # Strip common Markdown emphasis so bold labels still match.
    stripped = re.sub(r"[*_]{1,3}", "", body)
    found: list[str] = []
    for src in (body, stripped):
        for cre in _CLAIMED_SHA_RES:
            for m in cre.finditer(src):
                sha = m.group(1).lower()
                if sha not in found:
                    found.append(sha)
    return found


def sha_matches_head(claimed: str, head_sha: str) -> bool:
    head_l = head_sha.lower()
    c = claimed.lower()
    return head_l.startswith(c) or c.startswith(head_l[:7])



def evaluate(
    *,
    base: str,
    draft: bool,
    paths: list[str] | None = None,
    body: str | None = None,
    head_sha: str | None = None,
    required_checks_present: bool | None = None,
    required_check_names: list[str] | None = None,
) -> list[dict[str, object]]:
    """Return list of violations. Draft PRs skip size/multi-cap hard fails."""
    violations: list[dict[str, object]] = []
    exception = _load_exception()

    if paths is not None:
        files = paths
        textual_added = 0
        binary_in_diff: list[str] = []
        for p in files:
            if Path(p).suffix.lower() in BINARY_SUFFIXES:
                binary_in_diff.append(p)
        # line count unknown without git — leave 0 unless numstat used
        added_lines = 0
    else:
        name_status = _diff_name_status(base)
        files = [p for _, p in name_status]
        stats = _numstat(base)
        added_lines = 0
        binary_in_diff = []
        for a, _d, path in stats:
            if a < 0:
                binary_in_diff.append(path)
            elif is_textual(path):
                added_lines += a
        textual_added = added_lines

    n_files = len(files)
    buckets: dict[str, list[str]] = defaultdict(list)
    for p in files:
        for tag in classify_path(p):
            buckets[tag].append(p)

    multi_cap = (
        bool(buckets.get("migration"))
        and bool(buckets.get("ci"))
        and bool(buckets.get("runtime"))
        and bool(buckets.get("commercial"))
    )

    def maybe(reason: str, detail: dict[str, object]) -> None:
        if exception and reason in (exception.get("waives") or []):
            return
        if draft and reason in {
            "too_many_files",
            "too_many_textual_lines",
            "multi_capability_mix",
            "body_ci_sha_mismatch",  # draft tip may move before body refresh
        }:
            # Draft may exceed size while being rebuilt; still flag binaries.
            return
        violations.append({"reason": reason, **detail})

    if n_files > MAX_FILES_READY:
        maybe(
            "too_many_files",
            {
                "files": n_files,
                "limit": MAX_FILES_READY,
                "hint": (
                    "Split the PR or mark as draft while reconstructing. "
                    "Legitimate large migration+test suites can request a "
                    f"human exception in {EXCEPTION_PATH}."
                ),
            },
        )

    if textual_added > MAX_TEXTUAL_LINES_ADDED:
        maybe(
            "too_many_textual_lines",
            {
                "textual_lines_added": textual_added,
                "limit": MAX_TEXTUAL_LINES_ADDED,
                "hint": "Remove generated dumps; keep product/tests only.",
            },
        )

    if binary_in_diff:
        # product binaries always fail unless exception waives binary_product
        product_bins = [
            p
            for p in binary_in_diff
            if not p.startswith("tests/")
            and Path(p).suffix.lower() in BINARY_SUFFIXES
        ]
        if product_bins:
            maybe(
                "binary_or_generated_in_diff",
                {
                    "paths": product_bins[:20],
                    "count": len(product_bins),
                    "hint": "Use fixture builders or GH Actions artifacts.",
                },
            )

    if multi_cap:
        maybe(
            "multi_capability_mix",
            {
                "buckets": {k: len(v) for k, v in buckets.items()},
                "hint": (
                    "Do not mix migrations + CI + runtime + commercial deliverable "
                    "in one ready PR. Decompose into foundation / linkage / pack."
                ),
            },
        )

    # Body consistency checks (when provided by CI)
    if body:
        if head_sha:
            for claimed in extract_claimed_head_shas(body):
                if not sha_matches_head(claimed, head_sha):
                    maybe(
                        "body_ci_sha_mismatch",
                        {
                            "claimed": claimed,
                            "head": head_sha,
                            "hint": (
                                "Update PR body so **HEAD SHA:** matches the exact "
                                "tip under test (Markdown bold/backticks supported)."
                            ),
                        },
                    )
        # Only treat status-like declarations as PASS claims — not prose that
        # merely mentions the word "PASS" (e.g. "when body declares PASS").
        declares_pass = bool(
            re.search(
                r"(?is)(?:status|verdict|result|ci(?:\s+status)?)\s*[:=]\s*"
                r"`?(?:PASS|CI_GREEN|READY_TO_MERGE)`?\b"
                r"|\bCI_GREEN\b|\bREADY_TO_MERGE\b"
                r"|(?:^|\n)\s*PASS\s*(?:\n|$)",
                body,
            )
        )
        if declares_pass:
            # Fail-closed: PASS claims require explicit confirmation that
            # required gates ran (not unknown / not false).
            if required_checks_present is not True:
                maybe(
                    "declared_pass_without_gates",
                    {
                        "required_checks_present": required_checks_present,
                        "hint": (
                            "Do not declare PASS/CI_GREEN while required gates are "
                            "missing or unverified (pass --required-checks-present true "
                            "only when all REQUIRED_CANONICAL_CHECKS completed)."
                        ),
                    },
                )
            if required_check_names is not None:
                present = set(required_check_names)
                missing = [c for c in REQUIRED_CANONICAL_CHECKS if c not in present]
                if missing:
                    maybe(
                        "missing_required_checks",
                        {
                            "missing": missing,
                            "hint": "All REQUIRED_CANONICAL_CHECKS must be present.",
                        },
                    )


    if exception is None and (REPO_ROOT / EXCEPTION_PATH).is_file():
        # Only fail when active is present but incomplete (missing required fields).
        # null/empty active is fine; a complete active with exception=None is treated
        # as intentional override (tests mock _load_exception) and is not a violation.
        try:
            raw = json.loads((REPO_ROOT / EXCEPTION_PATH).read_text(encoding="utf-8"))
            active = raw.get("active")
            if isinstance(active, dict) and active:
                required = ("reason", "owner", "deadline", "approved_by")
                if any(not active.get(k) for k in required):
                    violations.append(
                        {
                            "reason": "invalid_reviewability_exception",
                            "hint": (
                                "active exception needs reason, owner, deadline, "
                                "approved_by"
                            ),
                        }
                    )
        except json.JSONDecodeError:
            violations.append(
                {
                    "reason": "invalid_reviewability_exception",
                    "hint": "JSON parse failed",
                }
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--draft", action="store_true", help="draft PR (lenient size)")
    parser.add_argument("--body-file", help="PR body for SHA/PASS consistency checks")
    parser.add_argument("--head-sha", help="exact HEAD SHA of the PR tip")
    parser.add_argument(
        "--required-checks-present",
        choices=("true", "false", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--required-check-names-file",
        help="file with one completed check name per line (optional)",
    )
    parser.add_argument("--paths", nargs="*", help="explicit paths (tests)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    body = None
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")

    rcp: bool | None
    if args.required_checks_present == "true":
        rcp = True
    elif args.required_checks_present == "false":
        rcp = False
    else:
        rcp = None

    check_names: list[str] | None = None
    if args.required_check_names_file:
        check_names = [
            ln.strip()
            for ln in Path(args.required_check_names_file).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]

    try:
        violations = evaluate(
            base=args.base,
            draft=args.draft,
            paths=list(args.paths) if args.paths else None,
            body=body,
            head_sha=args.head_sha,
            required_checks_present=rcp,
            required_check_names=check_names,
        )
    except subprocess.CalledProcessError as exc:
        print(f"error: git failed: {exc}", file=sys.stderr)
        return 2

    report = {
        "ok": not violations,
        "draft": args.draft,
        "violation_count": len(violations),
        "violations": violations,
        "limits": {
            "max_files_ready": MAX_FILES_READY,
            "max_textual_lines_added": MAX_TEXTUAL_LINES_ADDED,
        },
        "policy": "docs/pr-reviewability-policy.md",
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"pr-reviewability: draft={args.draft} "
            f"violations={len(violations)}"
        )
        for v in violations:
            print(f"  FAIL {v['reason']}: {json.dumps({k: v[k] for k in v if k != 'reason'})}")
        if not violations:
            print("  PASS")
        else:
            print(
                "\nActionable: reduce scope, remove binaries/generated packs, "
                "or add a human-approved exception in "
                f"{EXCEPTION_PATH} with reason/owner/deadline/approved_by/waives."
            )
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
