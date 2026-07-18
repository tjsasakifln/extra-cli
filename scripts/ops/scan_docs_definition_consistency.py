#!/usr/bin/env python3
"""Scan canonical docs for scope promises, shared definitions, conflicting numbers.

Supports DoD §25 residual language items:
- no out-of-scope capacity promises
- README/PRD/DOD/manifests share definitions
- conflicting headline numbers must be historical or resolved
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

CANONICAL_DOCS: tuple[str, ...] = (
    "README.md",
    "DOD.md",
    "docs/prd/PRD-consultoria-extra.md",
    "docs/architecture/coverage-contract.md",
)

# Affirmative out-of-scope promises (not mere exclusion language).
OUT_OF_SCOPE_PROMISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmulti[- ]tenant\b.*\b(suport|oferec|pronto|dispon[ií]vel)", re.I),
    re.compile(r"\bSaaS\b.*\b(pronto|dispon[ií]vel|lan[cç]ado)", re.I),
    re.compile(r"\bAPI\s+p[uú]blica\b.*\b(pronto|dispon[ií]vel)", re.I),
    re.compile(r"\bdashboard\s+web\b.*\b(pronto|dispon[ií]vel|entregue)", re.I),
    re.compile(
        r"\b(oferecemos|disponibilizamos|entregamos)\b.*\bacompanhamento\s+f[ií]sico\b",
        re.I,
    ),
)

# Shared definition anchors that must not contradict each other.
SHARED_DEFS: dict[str, re.Pattern[str]] = {
    "universe_1093": re.compile(r"\b1[.\s]?093\b|\b1093\b"),
    "commercial_not_coverage": re.compile(
        r"commercial[_\s-]?signal|sinal\s+comercial|n[aã]o\s+(?:[eé]\s+)?cobertura",
        re.I,
    ),
    "coverage_95_target": re.compile(r"95\s*%|≥\s*95|>=\s*95"),
}

# Headline percentage claims that need historical context if stale.
HEADLINE_PCT = re.compile(
    r"(?:cobertura|coverage)[^\n]{0,40}?(\d{1,3}(?:[.,]\d+)?\s*%)",
    re.I,
)
HISTORICAL_CTX = re.compile(
    r"(hist[oó]ric|stale|baseline|antes|before|sess[aã]o|2026-07-1[67]|n[aã]o\s+confiar)",
    re.I,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def scan_out_of_scope_promises(repo: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rel in CANONICAL_DOCS:
        path = repo / rel
        text = _read(path)
        if not text:
            findings.append({"path": rel, "issue": "missing_doc", "severity": "medium"})
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"fora\s+de\s+escopo|n[aã]o\s+(?:inclui|oferece|possui)", line, re.I):
                continue
            for pat in OUT_OF_SCOPE_PROMISE_PATTERNS:
                if pat.search(line):
                    findings.append(
                        {
                            "path": rel,
                            "line": i,
                            "issue": "out_of_scope_promise",
                            "text": line.strip()[:160],
                            "severity": "high",
                        }
                    )
    return findings


def scan_shared_definitions(repo: Path) -> dict[str, Any]:
    present: dict[str, list[str]] = {k: [] for k in SHARED_DEFS}
    missing_files: list[str] = []
    for rel in CANONICAL_DOCS:
        path = repo / rel
        text = _read(path)
        if not text:
            missing_files.append(rel)
            continue
        for key, pat in SHARED_DEFS.items():
            if pat.search(text):
                present[key].append(rel)
    # Universe + commercial/coverage separation should appear in DOD and coverage docs
    required_pairs = {
        "universe_1093": {"DOD.md"},
        "commercial_not_coverage": {"DOD.md"},
    }
    gaps = []
    for key, required in required_pairs.items():
        have = set(present[key])
        for r in required:
            if r not in have:
                gaps.append({"definition": key, "missing_in": r})
    return {
        "present": present,
        "missing_files": missing_files,
        "gaps": gaps,
        "ok": len(gaps) == 0,
    }


def scan_conflicting_numbers(repo: Path) -> dict[str, Any]:
    """Collect coverage % mentions; flag uncontextualized conflicts with current ~0% operational."""
    mentions: list[dict[str, Any]] = []
    for rel in CANONICAL_DOCS:
        text = _read(repo / rel)
        for i, line in enumerate(text.splitlines(), 1):
            for m in HEADLINE_PCT.finditer(line):
                pct_raw = m.group(1).replace(",", ".").replace("%", "").strip()
                try:
                    pct = float(pct_raw)
                except ValueError:
                    continue
                window_start = max(0, i - 3)
                window = "\n".join(text.splitlines()[window_start : i + 2])
                historical = bool(HISTORICAL_CTX.search(window) or HISTORICAL_CTX.search(line))
                mentions.append(
                    {
                        "path": rel,
                        "line": i,
                        "pct": pct,
                        "historical_context": historical,
                        "text": line.strip()[:160],
                    }
                )
    # Conflict: language that asserts *current achieved* high operational coverage
    # without historical marker. Targets, open checkboxes, and negations are OK.
    _benign = re.compile(
        r"(meta|target|m[ií]nim|objetivo|gate|n[aã]o\s+declara|n[aã]o\s+afirma|"
        r"nem\s+cobertura|sem\s+evid[eê]ncia|not\s+claim|unchecked|\-\s*\[\s\]|"
        r"deve\s+(?:ser|atingir)|requer|required|threshold|trajet[oó]ria|"
        r"pr[oó]ximo|investimento|nunca\s+atinge|checklist|gate\s)",
        re.I,
    )
    _achieved = re.compile(
        r"(atingiu|alcan[cç]ou|comprovad[ao]|atual(?:mente)?\s+(?:em\s+)?\d|"
        r"cobertura\s+operacional\s+(?:[eé]\s+|=)\s*\d|"
        r"operational[_\s-]?coverage\s*=\s*\d)",
        re.I,
    )
    conflicts = []
    for m in mentions:
        if m["pct"] < 90 or m["historical_context"]:
            continue
        text = m["text"]
        if _benign.search(text):
            continue
        if _achieved.search(text):
            conflicts.append(m)
    return {"mentions": mentions, "conflicts": conflicts, "ok": len(conflicts) == 0}


def scan_repo(repo: Path | None = None) -> dict[str, Any]:
    root = repo or REPO
    scope = scan_out_of_scope_promises(root)
    defs = scan_shared_definitions(root)
    nums = scan_conflicting_numbers(root)
    return {
        "ok": len(scope) == 0 and defs["ok"] and nums["ok"],
        "out_of_scope_promises": scope,
        "shared_definitions": defs,
        "conflicting_numbers": nums,
        "canonical_docs": list(CANONICAL_DOCS),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    report = scan_repo(args.repo)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(
            f"docs_definition_consistency: ok={report['ok']} "
            f"scope_hits={len(report['out_of_scope_promises'])} "
            f"def_gaps={len(report['shared_definitions']['gaps'])} "
            f"num_conflicts={len(report['conflicting_numbers']['conflicts'])}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
