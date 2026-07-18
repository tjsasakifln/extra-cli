"""Map DoD §2.1 objectives to CLI entry points and honest readiness status.

Does not claim operational coverage ≥95%. Status is based on code presence +
known evidence artifacts, not live PG unless available.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

# status: READY | PARTIAL | NOT_READY
OBJECTIVES: list[dict[str, Any]] = [
    {
        "id": "locate_relevant_tenders",
        "dod": "O sistema ajuda a localizar editais relevantes para a Extra Construtora.",
        "commands": [
            "python3 -m scripts.opportunity_intel.cli list --status open",
            "python3 -m scripts.workspace today",
        ],
        "modules": ["scripts/opportunity_intel/cli.py", "scripts/workspace/cli.py"],
        "status": "PARTIAL",
        "reason": "CLI exists; operational coverage of universe still ~0% live.",
    },
    {
        "id": "verify_historical_contracts",
        "dod": "O sistema ajuda a verificar contratos históricos dos entes monitorados.",
        "commands": [
            "python3 -m scripts.contract_intel.cli --help",
            "python3 scripts/local_datalake.py supplier --cnpj <CNPJ>",
        ],
        "modules": ["scripts/contract_intel/cli.py", "scripts/local_datalake.py"],
        "status": "PARTIAL",
        "reason": "Paths exist; 3y backfill not fully complete for all entities.",
    },
    {
        "id": "identify_winners_competitors",
        "dod": "O sistema ajuda a identificar vencedores e concorrentes observáveis.",
        "commands": [
            "python3 -m scripts.buyer_intel.cli --help",
            "python3 -m scripts.contract_intel.cli fornecedores",
        ],
        "modules": ["scripts/buyer_intel/cli.py", "scripts/contract_intel/cli.py"],
        "status": "PARTIAL",
        "reason": "Observáveis only; not complete competitor set (claim_language).",
    },
    {
        "id": "value_references",
        "dod": "O sistema ajuda a formar referências de valores com semântica explícita.",
        "commands": [
            "python3 -c \"from scripts.lib.value_semantics import ValorSemantica; print(list(ValorSemantica))\"",
        ],
        "modules": ["scripts/lib/value_semantics.py"],
        "status": "PARTIAL",
        "reason": "Semantics module ready; commercial price panel may be data-limited.",
    },
    {
        "id": "decision_support",
        "dod": "O sistema ajuda Tiago a decidir quais oportunidades merecem análise humana.",
        "commands": [
            "python3 -m scripts.workspace decide --help",
            "python3 -m scripts.opportunity_intel.cli explain 1",
        ],
        "modules": ["scripts/workspace/cli.py", "scripts/opportunity_intel/cli.py"],
        "status": "PARTIAL",
        "reason": "GO/REVIEW/NO_GO path exists; profile incompleteness rebaixado a REVIEW.",
    },
    {
        "id": "reduce_missed_opportunities",
        "dod": "O sistema reduz o risco de perda de oportunidades por monitoramento incompleto.",
        "commands": [
            "python3 -m scripts.coverage.coverage_contract_cli --json",
        ],
        "modules": ["scripts/coverage/coverage_contract.py", "scripts/crawl/monitor.py"],
        "status": "NOT_READY",
        "reason": "Operational coverage ~0% — monitoring incomplete by definition.",
    },
    {
        "id": "evidence_reports",
        "dod": "O sistema produz evidências e relatórios utilizáveis na consultoria.",
        "commands": [
            "python3 -m scripts.reports.executive_report --help",
            "python3 -m scripts.reports.run_metadata",
        ],
        "modules": ["scripts/reports/", "scripts/generate_consultoria_pdf.py"],
        "status": "PARTIAL",
        "reason": "Report generators exist; need same run_id PDF×Excel with live data.",
    },
]


def inventory(repo: Path | None = None) -> dict[str, Any]:
    root = repo or REPO
    rows = []
    for obj in OBJECTIVES:
        modules_present = []
        modules_missing = []
        for m in obj["modules"]:
            p = root / m
            if p.exists():
                modules_present.append(m)
            else:
                modules_missing.append(m)
        rows.append(
            {
                **obj,
                "modules_present": modules_present,
                "modules_missing": modules_missing,
                "code_present": len(modules_missing) == 0,
            }
        )
    return {
        "ok": True,
        "objectives": rows,
        "counts": {
            "total": len(rows),
            "partial": sum(1 for r in rows if r["status"] == "PARTIAL"),
            "not_ready": sum(1 for r in rows if r["status"] == "NOT_READY"),
            "ready": sum(1 for r in rows if r["status"] == "READY"),
        },
        "forbidden_claim": "Do not claim all objectives READY while operational coverage <95%.",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    data = inventory()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for o in data["objectives"]:
            print(f"{o['status']:10} {o['id']}")
        print(data["counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
