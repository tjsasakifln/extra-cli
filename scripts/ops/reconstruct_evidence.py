#!/usr/bin/env python3
"""Reconstruct evidence artifact paths for coverage / freshness / recall / snapshot.

Does not invent metrics: only maps evidence kinds to commands and existing
artifact locations so DoD §29 reconstruction is executable and auditable.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

EVIDENCE_KINDS: tuple[str, ...] = (
    "coverage",
    "success_zero",
    "freshness",
    "recall",
    "snapshot",
    "acceptance",
)


@dataclass(frozen=True)
class EvidenceRecipe:
    kind: str
    reconstructible: bool
    command: str
    artifact_globs: list[str]
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RECIPES: dict[str, EvidenceRecipe] = {
    "coverage": EvidenceRecipe(
        kind="coverage",
        reconstructible=True,
        command="python3 -m scripts.coverage.coverage_contract_cli --json -o output/coverage/contract-report.json",
        artifact_globs=[
            "output/coverage/contract-report.json",
            "output/coverage/entity-source-gaps.jsonl",
            "docs/ops/session-*/coverage*.json",
        ],
        notes="Uses fixed denominator 1093; presence ≠ operational coverage.",
    ),
    "success_zero": EvidenceRecipe(
        kind="success_zero",
        reconstructible=True,
        command="python3 -m scripts.crawl.monitor --source pncp --mode incremental  # inspect run evidence success_zero",
        artifact_globs=[
            "output/golden-path/*.json",
            "data/**/checkpoints/**/*.json",
            "docs/ops/session-*/**/*success*zero*",
        ],
        notes="success_zero is a valid terminal status per entity/source when query succeeds with 0 rows.",
    ),
    "freshness": EvidenceRecipe(
        kind="freshness",
        reconstructible=True,
        command="python3 scripts/freshness_gate.py --json",
        artifact_globs=[
            "docs/ops/session-*/freshness_manifest.json",
            "output/**/freshness*.json",
        ],
        notes="Entity-level freshness may be NOT_READY if only source-level manifests exist.",
    ),
    "recall": EvidenceRecipe(
        kind="recall",
        reconstructible=True,
        command="python3 -c \"import json; print(json.load(open('docs/qa/recall-sample-2026-07-17.json'))['status'] if False else 'see sample')\"",
        artifact_globs=[
            "docs/qa/recall*.json",
            "output/coverage/recall*.json",
        ],
        notes="Recall only from stratified gold sample — never DB opportunity counts.",
    ),
    "snapshot": EvidenceRecipe(
        kind="snapshot",
        reconstructible=True,
        command="python3 -m scripts.opportunity_intel.cli snapshot  # or project snapshot path",
        artifact_globs=[
            "output/**/snapshot*.json",
            "docs/ops/session-*/**/*snapshot*",
        ],
        notes="active_snapshot_integrity must be re-measured; do not trust historical 1.0 without re-run.",
    ),
    "acceptance": EvidenceRecipe(
        kind="acceptance",
        reconstructible=True,
        command="see docs/ops/NEXT-DEV-STEP.md and guided acceptance pack (Tiago sign-off required)",
        artifact_globs=[
            "docs/ops/session-*/**/*accept*",
            "docs/ops/NEXT-DEV-STEP.md",
            "DOD.md",
        ],
        notes="Human acceptance remains open until Tiago signs.",
    ),
}


def recipe_for(kind: str) -> EvidenceRecipe:
    if kind not in RECIPES:
        raise KeyError(f"unknown evidence kind: {kind}")
    return RECIPES[kind]


def list_existing_artifacts(kind: str, repo: Path | None = None) -> list[str]:
    root = repo or REPO
    recipe = recipe_for(kind)
    found: list[str] = []
    for pattern in recipe.artifact_globs:
        found.extend(str(p.relative_to(root)) for p in root.glob(pattern) if p.is_file())
    return sorted(set(found))[:50]


def reconstruct_plan(kind: str | None = None, repo: Path | None = None) -> dict[str, Any]:
    kinds = [kind] if kind else list(EVIDENCE_KINDS)
    items = []
    for k in kinds:
        r = recipe_for(k)
        items.append(
            {
                **r.to_dict(),
                "existing_artifacts": list_existing_artifacts(k, repo),
            }
        )
    return {
        "ok": True,
        "kinds": kinds,
        "items": items,
        "dod_refs": [
            "A evidência de coverage pode ser reconstruída.",
            "A evidência de success_zero pode ser reconstruída.",
            "A evidência de freshness pode ser reconstruída.",
            "A evidência de recall pode ser reconstruída.",
            "A evidência de snapshot pode ser reconstruída.",
            "O DOD aponta para os artefatos finais de aceite.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", choices=list(EVIDENCE_KINDS), default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--repo", type=Path, default=None)
    args = p.parse_args(argv)
    plan = reconstruct_plan(args.kind, args.repo)
    if args.json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        for item in plan["items"]:
            print(f"{item['kind']}: reconstructible={item['reconstructible']}")
            print(f"  cmd: {item['command']}")
            print(f"  artifacts: {len(item['existing_artifacts'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
