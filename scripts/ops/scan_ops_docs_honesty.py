#!/usr/bin/env python3
"""Verify operational documentation honesty (DoD §31 slice)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

REQUIRED_PATHS: dict[str, str] = {
    "readme": "README.md",
    "prd": "docs/prd/PRD-consultoria-extra.md",
    "dod": "DOD.md",
    "glossary": "docs/GLOSSARY.md",
    "adr_index": "docs/architecture/adr/INDEX.md",
    "runbook": "docs/ops/runbook.md",
}

README_HONESTY_MARKERS = (
    re.compile(r"alvo|futur|n[aã]o\s+baseline|NOT_READY|datalake local", re.I),
    re.compile(r"VPS|PRE_VPS|n[aã]o\s+est[aá]\s+definido", re.I),
)

RUNBOOK_SECTIONS = (
    re.compile(r"runbook de rollback", re.I),
    re.compile(r"schema drift", re.I),
    re.compile(r"cobertura abaixo de 95|cobertura.*95", re.I),
)


def scan(repo: Path | None = None) -> dict:
    root = repo or REPO
    missing = []
    present = {}
    for key, rel in REQUIRED_PATHS.items():
        path = root / rel
        if path.is_file():
            present[key] = rel
        else:
            missing.append(rel)

    readme = (root / "README.md").read_text(encoding="utf-8", errors="replace") if (root / "README.md").is_file() else ""
    readme_ok = all(p.search(readme) for p in README_HONESTY_MARKERS)

    runbook = (root / "docs/ops/runbook.md").read_text(encoding="utf-8", errors="replace") if (root / "docs/ops/runbook.md").is_file() else ""
    runbook_sections_ok = all(p.search(runbook) for p in RUNBOOK_SECTIONS)

    adr_index = (root / "docs/architecture/adr/INDEX.md").read_text(encoding="utf-8", errors="replace") if (root / "docs/architecture/adr/INDEX.md").is_file() else ""
    adr_active = "Vigente" in adr_index
    adr_revoked_section = re.search(r"revogad", adr_index, re.I) is not None

    glossary = (root / "docs/GLOSSARY.md").read_text(encoding="utf-8", errors="replace") if (root / "docs/GLOSSARY.md").is_file() else ""
    glossary_has_1093 = "1093" in glossary or "1.093" in glossary

    prd = (root / "docs/prd/PRD-consultoria-extra.md").read_text(encoding="utf-8", errors="replace") if (root / "docs/prd/PRD-consultoria-extra.md").is_file() else ""
    prd_mentions_dod = bool(re.search(r"\bDOD\b|Definition of Done|cobertura", prd, re.I))

    ok = (
        not missing
        and readme_ok
        and runbook_sections_ok
        and adr_active
        and adr_revoked_section
        and glossary_has_1093
        and prd_mentions_dod
    )
    return {
        "ok": ok,
        "missing": missing,
        "present": present,
        "checks": {
            "readme_honesty_markers": readme_ok,
            "runbook_rollback_drift_coverage": runbook_sections_ok,
            "adr_index_active": adr_active,
            "adr_index_revoked_section": adr_revoked_section,
            "glossary_universe_1093": glossary_has_1093,
            "prd_aligned_language": prd_mentions_dod,
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    report = scan(args.repo)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"ops_docs_honesty: ok={report['ok']} missing={report['missing']}")
        for k, v in report["checks"].items():
            print(f"  {k}={v}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
