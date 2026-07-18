#!/usr/bin/env python3
"""Scan mandatory quality gates for fail-open suppressors.

Detects non-comment occurrences of:
  - shell ``|| true`` (exit-code swallowing)
  - GitHub Actions ``continue-on-error: true``

Mandatory gate surface is explicit and small. Operational scripts outside this
set may still use ``|| true`` for best-effort notify/cleanup; those are out of
scope for DoD §13.4 "Nenhum gate obrigatório usa ``|| true``".

Exit codes:
  0 — clean
  1 — violations found
  2 — usage / path error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Paths relative to repo root — only obligatory fail-closed gates.
MANDATORY_GATE_PATHS: tuple[str, ...] = (
    ".github/workflows/ci.yml",
    "scripts/ci_gate.sh",
    "scripts/ci-check.sh",
    "scripts/coverage_gate.py",
    "scripts/freshness_gate.py",
    "scripts/golden_path.py",
    "squads/extra-dod-roi/scripts/enforce_aiox_path.py",
)

# Non-comment executable suppressors.
_OR_TRUE = re.compile(r"\|\|\s*true\b")
_CONTINUE_ON_ERROR_TRUE = re.compile(r"continue-on-error\s*:\s*true\b", re.I)

# Lines that only document the ban must not count as violations.
_DOC_BAN_MARKERS = (
    "nenhum job usa",
    "nenhum gate",
    "no continue-on-error",
    "sem continue-on-error",
    "fail-closed, no continue",
    "fail-closed, sem continue",
    "no `|| true`",
    "no || true",
    "uses `|| true`",  # negative claim prose
    "usa `|| true`",
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    text: str


def _strip_line_comment(line: str) -> str:
    """Remove shell/YAML-style trailing comments; keep full-line comments as empty."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return ""
    # Drop trailing `# ...` outside simple single quotes (good enough for gates).
    if "#" in line:
        in_single = False
        in_double = False
        for idx, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                return line[:idx].rstrip()
    return line.rstrip()


def _is_ban_doc_only(code: str) -> bool:
    """True only when the *code* portion is pure ban documentation (no executable suppressor)."""
    lower = code.lower().strip()
    if not lower:
        return True
    # Executable suppressors always count — ban markers never neutralize them.
    if _OR_TRUE.search(code) or _CONTINUE_ON_ERROR_TRUE.search(code):
        return False
    return any(m in lower for m in _DOC_BAN_MARKERS)


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        code = _strip_line_comment(line)
        if not code or _is_ban_doc_only(code):
            continue
        if _OR_TRUE.search(code):
            findings.append(
                Finding(path=path, line=i, kind="or_true", text=line.strip()[:200])
            )
        if _CONTINUE_ON_ERROR_TRUE.search(code):
            findings.append(
                Finding(
                    path=path,
                    line=i,
                    kind="continue_on_error_true",
                    text=line.strip()[:200],
                )
            )
    return findings


def scan_repo(repo: Path | None = None) -> dict:
    root = repo or REPO_ROOT
    all_findings: list[Finding] = []
    scanned: list[str] = []
    missing: list[str] = []

    for rel in MANDATORY_GATE_PATHS:
        path = root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        scanned.append(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        all_findings.extend(scan_text(rel, text))

    return {
        "ok": len(all_findings) == 0 and len(missing) == 0,
        "scanned": scanned,
        "missing": missing,
        "findings": [asdict(f) for f in all_findings],
        "counts": {
            "scanned": len(scanned),
            "missing": len(missing),
            "findings": len(all_findings),
            "or_true": sum(1 for f in all_findings if f.kind == "or_true"),
            "continue_on_error_true": sum(
                1 for f in all_findings if f.kind == "continue_on_error_true"
            ),
        },
        "mandatory_paths": list(MANDATORY_GATE_PATHS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository root (default: inferred from this file)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full JSON report to stdout",
    )
    args = parser.parse_args(argv)

    report = scan_repo(args.repo)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(
            f"mandatory_gates_failclosed: scanned={report['counts']['scanned']} "
            f"findings={report['counts']['findings']} missing={report['counts']['missing']}"
        )
        for f in report["findings"]:
            print(f"  VIOLATION {f['path']}:{f['line']} [{f['kind']}] {f['text']}")
        for m in report["missing"]:
            print(f"  MISSING {m}")

    if report["missing"]:
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
