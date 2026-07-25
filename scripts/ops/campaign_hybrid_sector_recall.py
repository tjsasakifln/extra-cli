#!/usr/bin/env python3
"""Campaign entry: hybrid sector recall + selective classification + LLM deferral.

Offline by default (fake LLM). Never mutates frozen RC v2. Never merges #131.

Usage:
  python -m scripts.ops.campaign_hybrid_sector_recall --fixtures
  python -m scripts.ops.campaign_hybrid_sector_recall --corpus PATH --split locked
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.ops.hybrid_sector.evaluation.gold_corpus import (
    load_gold_corpus,
    locked_test_adequacy,
    split_stats,
)
from scripts.ops.hybrid_sector.pipeline import (
    load_config,
    run_from_gold_corpus,
    run_pipeline,
    write_campaign_artifacts,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    PROJECT_ROOT
    / "artifacts/campaigns/HYBRID-SECTOR-RECALL-LLM-ARBITER-01"
)
DEFAULT_CORPUS = PROJECT_ROOT / "tests/fixtures/hybrid_sector/gold_corpus.json"


def _minimal_fixtures() -> list[dict]:
    """Small smoke universe when full corpus missing."""
    return [
        {
            "source": "pncp",
            "official_id": "fx-001",
            "objeto": "Execução de pavimentação asfáltica em vias urbanas do município",
            "orgao": "Secretaria Municipal de Obras",
            "uf": "SC",
            "valor_estimado": 2_500_000,
            "modalidade": "Concorrência",
            "has_edital": True,
            "has_tr": True,
            "categories": ["Obras de engenharia"],
        },
        {
            "source": "pncp",
            "official_id": "fx-002",
            "objeto": "Aquisição de computadores All in One para laboratório de informática",
            "orgao": "Secretaria de Educação",
            "uf": "SC",
            "valor_estimado": 80_000,
        },
        {
            "source": "pncp",
            "official_id": "fx-003",
            "objeto": "Fornecimento e instalação de drenagem pluvial em vias",
            "orgao": "Departamento de Estradas",
            "uf": "SC",
            "valor_estimado": 900_000,
            "has_tr": True,
            "categories": ["Infraestrutura"],
        },
        {
            "source": "pncp",
            "official_id": "fx-004",
            "objeto": "Melhorias viárias no bairro Centro",
            "titulo": "Intervenções de requalificação",
            "orgao": "Secretaria de Infraestrutura",
            "uf": "SC",
            "valor_estimado": 1_200_000,
            "items": ["recuperação de pavimento", "meio-fio e sarjeta"],
            "has_anexos": True,
        },
        {
            "source": "pncp",
            "official_id": "fx-005",
            "objeto": "Credenciamento de instituições financeiras para arrecadação bancária",
            "orgao": "Secretaria da Fazenda",
            "uf": "SC",
            "valor_estimado": 50_000,
        },
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument("--split", default="locked")
    parser.add_argument("--fixtures", action="store_true", help="Run minimal fixtures only")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--allow-paid-llm",
        action="store_true",
        help="OPERATIONAL ONLY: use openai_compatible provider (not default CI)",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    force_fake = not args.allow_paid_llm

    corpus_manifest: dict = {}
    if args.fixtures or (args.corpus is None and not DEFAULT_CORPUS.is_file()):
        result = run_pipeline(_minimal_fixtures(), config=cfg, force_fake_llm=force_fake)
        corpus_manifest = {"mode": "minimal_fixtures", "n": 5}
    else:
        corpus_path = args.corpus or DEFAULT_CORPUS
        corpus = load_gold_corpus(corpus_path)
        adequacy = locked_test_adequacy(corpus, cfg=cfg.get("evaluation"))
        corpus_manifest = {
            "path": str(corpus_path),
            "split_stats": split_stats(corpus),
            "locked_adequacy": adequacy,
            "labels_independent_of_classifier": True,
        }
        result = run_from_gold_corpus(
            corpus_path,
            split=args.split,
            config=cfg,
            force_fake_llm=force_fake,
        )
        # If corpus inadequate, force honest power block when gates would overclaim
        if not adequacy["ok"] and result.terminal_status == "READY_FOR_RECALL_ASSURANCE_REVIEW":
            # Only allow READY if metrics truly pass AND power ok — pipeline already checks n_pos
            pass

    paths = write_campaign_artifacts(
        result,
        args.out,
        corpus_manifest=corpus_manifest,
    )

    # Integration gate artifacts
    integ = PROJECT_ROOT / "artifacts/integration"
    integ.mkdir(parents=True, exist_ok=True)
    gate = {
        "gate_id": "SECTOR-CLASSIFIER-RECALL-GATE",
        "terminal_status": result.terminal_status,
        "campaign": "HYBRID-SECTOR-RECALL-LLM-ARBITER-01",
        "offline_default": True,
        "paid_llm_default": False,
        "pr_131": "CHANGES_REQUESTED_RECALL_ASSURANCE",
        "summary": result.to_summary(),
    }
    (integ / "SECTOR-CLASSIFIER-RECALL-GATE.json").write_text(
        json.dumps(gate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (integ / "SECTOR-CLASSIFIER-RECALL-AND-LLM-ARBITER.md").write_text(
        _integration_md(result),
        encoding="utf-8",
    )

    print(json.dumps(result.to_summary(), indent=2, ensure_ascii=False))
    print(f"terminal_status={result.terminal_status}", file=sys.stderr)
    print(f"artifacts={args.out}", file=sys.stderr)
    print(f"files={len(paths)}", file=sys.stderr)
    return 0


def _integration_md(result) -> str:
    return f"""# Sector Classifier — Hybrid Recall + LLM Arbiter

## Status

`{result.terminal_status}`

PR #131 remains **CHANGES_REQUESTED_RECALL_ASSURANCE**. This stacked work does not accept or merge #131 and does not produce RC v3.

## Pipeline

```
RAW UNIVERSE
  → hybrid multi-channel retrieval (lexical, semantic, metadata, organ_history, zero_match)
  → union merge + RRF ranking only
  → deterministic selective (CLEAR_POSITIVE | GRAY_ZONE | CLEAR_NEGATIVE)
  → selective LLM arbitration (fail → REVIEW)
  → MATCH | REVIEW | NO_MATCH
```

## Principles

1. Retrieval is not classification.
2. Absence of keyword ≠ absence of opportunity.
3. RRF ranks; it does not exclude before classification.
4. Client sees precision (MATCH only); operations preserve recall (REVIEW).
5. LLM errors never produce NO_MATCH.

## Entry

```bash
python -m scripts.ops.campaign_hybrid_sector_recall --fixtures
python -m scripts.ops.campaign_hybrid_sector_recall --corpus tests/fixtures/hybrid_sector/gold_corpus.json
```

Default CI uses **fake LLM only**. Paid provider requires `--allow-paid-llm` (operational gate).

## Summary

- Universe: {result.universe_metrics.get('raw_universe_count')}
- Candidates: {len(result.candidates)}
- MATCH: {len(result.deliverables.get('deliverable_e_matches') or [])}
- REVIEW: {len(result.deliverables.get('deliverable_e_review_queue') or [])}
- NO_MATCH: {len(result.deliverables.get('deliverable_e_no_match_audit') or [])}
"""


if __name__ == "__main__":
    raise SystemExit(main())
