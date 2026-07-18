"""DoD «Convenção de evidência» — formal catalog of accepted evidence kinds.

An item may be marked complete only when at least one evidence kind exists.
This module catalogs the kinds, classifies free-text evidence lines, and audits
DOD.md for checked items lacking any recognized evidence class.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOD = PROJECT_ROOT / "DOD.md"

# Canonical kinds from DOD.md § Convenção de evidência (order preserved).
EVIDENCE_KINDS: tuple[dict[str, Any], ...] = (
    {
        "id": "automated_test",
        "label": "teste automatizado reproduzível",
        "patterns": (
            r"\bpytest\b",
            r"\bunittest\b",
            r"\btests?/",
            r"\b\d+\s+passed\b",
            r"test_.*\.py",
            r"scripts/ops/",
            r"\bqa\s+pass\b",
        ),
    },
    {
        "id": "documented_command_exit_0",
        "label": "comando documentado com exit code 0",
        "patterns": (
            r"exit\s*code\s*`?0`?",
            r"exit\s*=\s*0",
            r"\bexit\s+0\b",
            r"`[^`]+`\s+.*exit",
        ),
    },
    {
        "id": "system_report",
        "label": "relatório JSON/CSV/Excel/PDF/Markdown gerado pelo sistema",
        "patterns": (
            r"\bjson\b",
            r"\bcsv\b",
            r"\bexcel\b",
            r"\b\.xlsx\b",
            r"\bpdf\b",
            r"\bmarkdown\b",
            r"\b\.md\b",
            r"output/",
            r"docs/ops/session-",
        ),
    },
    {
        "id": "sql_query",
        "label": "consulta SQL com resultado esperado",
        "patterns": (
            r"\bsql\b",
            r"\bselect\b",
            r"\bpsql\b",
            r"\bpostgresql\b",
            r"\bquery\b.*\bresult",
        ),
    },
    {
        "id": "run_ledger",
        "label": "execução registrada em ledger/manifest/runs",
        "patterns": (
            r"\bledger\b",
            r"\bmanifest\b",
            r"\brun_id\b",
            r"\bruns?\b",
            r"execution.?record",
            r"data/requirement_states",
        ),
    },
    {
        "id": "dated_log",
        "label": "log datado e correlacionável",
        "patterns": (
            r"\blog\b",
            r"journalctl",
            r"\bcorrelation\b",
            r"20\d{2}-\d{2}-\d{2}",
        ),
    },
    {
        "id": "manual_validation_tiago",
        "label": "validação manual registrada por Tiago",
        "patterns": (
            r"valida[cç][aã]o\s+manual",
            r"\btiago\b.*valid",
            r"manual\s+accept",
            r"aceite\s+manual",
        ),
    },
    {
        "id": "commit_or_pr",
        "label": "commit ou pull request identificável",
        "patterns": (
            r"\bcommit\b",
            r"\bsha\b",
            r"\bpr\s*#?\d+",
            r"pull\s+request",
            r"\b[0-9a-f]{7,40}\b",
            r"github\.com/.*/pull/",
        ),
    },
    {
        "id": "restore_or_recovery_executed",
        "label": "teste de restauração ou recuperação efetivamente executado",
        "patterns": (
            r"\bpg_restore\b",
            r"\brestore\b",
            r"\brecovery\b",
            r"local_backup_restore",
            r"backup.?proof",
        ),
    },
    {
        "id": "official_source_comparison",
        "label": "comparação com fonte oficial na mesma data/período",
        "patterns": (
            r"fonte\s+oficial",
            r"official\s+source",
            r"compar(a|ison).*fonte",
            r"same\s+(date|period|day)",
            r"mesma\s+data",
            r"mesmo\s+per[ií]odo",
        ),
    },
)

KIND_IDS = tuple(k["id"] for k in EVIDENCE_KINDS)


@dataclass
class Classification:
    text: str
    kinds: list[str]
    accepted: bool


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def classify_evidence(text: str) -> Classification:
    """Return which evidence kinds match free-text evidence."""
    lower = text.lower()
    kinds: list[str] = []
    for kind in EVIDENCE_KINDS:
        for pat in kind["patterns"]:
            if re.search(pat, lower, re.I):
                kinds.append(kind["id"])
                break
    return Classification(text=text[:300], kinds=kinds, accepted=bool(kinds))


def item_may_be_marked_complete(evidence_texts: list[str]) -> dict[str, Any]:
    """Policy: at least one recognized evidence kind required."""
    matched: set[str] = set()
    for t in evidence_texts:
        matched.update(classify_evidence(t).kinds)
    return {
        "allowed": bool(matched),
        "kinds": sorted(matched),
        "rule": "at_least_one_evidence_kind_required",
    }


def parse_checked_items(dod_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for i, line in enumerate(dod_text.splitlines(), 1):
        m = re.match(r"^\s*-\s*\[[xX]\]\s*(.*)$", line)
        if not m:
            continue
        body = m.group(1).strip()
        clf = classify_evidence(body)
        items.append(
            {
                "line": i,
                "text": body[:240],
                "kinds": clf.kinds,
                "has_evidence_kind": clf.accepted,
            }
        )
    return items


def audit_evidence_convention(path: str | Path = DEFAULT_DOD) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    checked = parse_checked_items(text)
    weak = [c for c in checked if not c["has_evidence_kind"]]
    return {
        "ok": True,  # advisory; campaign uses QA for flips
        "generated_at": utc_now(),
        "dod_path": str(path),
        "kinds_catalog": [{"id": k["id"], "label": k["label"]} for k in EVIDENCE_KINDS],
        "checked_total": len(checked),
        "checked_with_kind": len(checked) - len(weak),
        "checked_without_kind": len(weak),
        "sample_without_kind": weak[:25],
        "policy": {
            "complete_requires_at_least_one_kind": True,
            "kinds_count": len(EVIDENCE_KINDS),
            "kinds": list(KIND_IDS),
        },
    }


def catalog() -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "section": "Convenção de evidência",
        "kinds": [{"id": k["id"], "label": k["label"]} for k in EVIDENCE_KINDS],
        "rule": "Um item pode ser marcado como concluído apenas quando pelo menos uma das evidências existir",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD evidence convention")
    p.add_argument("command", choices=["catalog", "audit", "classify"])
    p.add_argument("--dod", type=Path, default=DEFAULT_DOD)
    p.add_argument("--text", default="")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.command == "catalog":
        report: dict[str, Any] = catalog()
    elif args.command == "classify":
        report = asdict(classify_evidence(args.text))
    else:
        report = audit_evidence_convention(args.dod)

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
