#!/usr/bin/env python3
"""Campaign entry: hybrid sector recall + selective classification + LLM deferral.

Offline by default (fake LLM). Never mutates frozen RC v2. Never merges #131.

Usage:
  python -m scripts.ops.campaign_hybrid_sector_recall --fixtures
  python -m scripts.ops.campaign_hybrid_sector_recall \\
    --corpus tests/fixtures/hybrid_sector/real_operational_corpus.json \\
    --split locked --out /tmp/hybrid-sector-locked
  python -m scripts.ops.campaign_hybrid_sector_recall --require-ready ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.ops.hybrid_sector import REQUIRED_HONEST_BLOCKERS
from scripts.ops.hybrid_sector.evaluation.annotation import write_annotation_artifacts
from scripts.ops.hybrid_sector.evaluation.gold_corpus import (
    corpus_manifest,
    load_gold_corpus,
    locked_test_adequacy,
    split_stats,
)
from scripts.ops.hybrid_sector.evaluation.real_corpus import (
    ensure_real_corpus_file,
)
from scripts.ops.hybrid_sector.pipeline import (
    load_config,
    run_from_gold_corpus,
    run_pipeline,
    write_campaign_artifacts,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    PROJECT_ROOT / "artifacts/campaigns/HYBRID-SECTOR-RECALL-LLM-ARBITER-01"
)
# Level B synthetic — never default for operational claims
DEFAULT_SYNTHETIC = (
    PROJECT_ROOT / "tests/fixtures/hybrid_sector/synthetic_adversarial_corpus.json"
)
DEFAULT_REAL = (
    PROJECT_ROOT / "tests/fixtures/hybrid_sector/real_operational_corpus.json"
)
READY = "READY_FOR_RECALL_ASSURANCE_REVIEW"


def _minimal_fixtures() -> list[dict]:
    """Small Level A smoke universe when full corpus missing."""
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
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="Run minimal Level A fixtures only (not locked evaluation)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run Level B synthetic adversarial corpus (not operational gold)",
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--allow-paid-llm",
        action="store_true",
        help="OPERATIONAL ONLY: use openai_compatible provider (not default CI)",
    )
    parser.add_argument(
        "--include-distractors",
        action="store_true",
        help="Include dev/calibration with labels (alternative to locked-only)",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help=(
            "Exit non-zero unless terminal is exactly READY_FOR_RECALL_ASSURANCE_REVIEW"
        ),
    )
    parser.add_argument(
        "--full-suite-passed",
        action="store_true",
        help="Mark full suite as passed (only when actually green)",
    )
    parser.add_argument(
        "--rc-v2-intact",
        action="store_true",
        help="Mark RC v2 freeze intact (only after real diff -- check)",
    )
    parser.add_argument(
        "--embedding-benchmark",
        action="store_true",
        help="Run embedding channel benchmark on the corpus",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    force_fake = not args.allow_paid_llm

    full_suite = {
        "passed": bool(args.full_suite_passed),
        "status": (
            "FULL_SUITE_GREEN"
            if args.full_suite_passed
            else "BLOCKED_FULL_SUITE_VALIDATION"
        ),
    }
    rc_v2 = True if args.rc_v2_intact else None

    corpus_manifest_data: dict = {}
    if args.fixtures:
        result = run_pipeline(
            _minimal_fixtures(),
            config=cfg,
            force_fake_llm=force_fake,
            evaluation_level="A",
            full_suite=full_suite,
            rc_v2_intact=rc_v2,
        )
        corpus_manifest_data = {
            "mode": "minimal_fixtures",
            "evaluation_level": "A",
            "corpus_kind": "UNIT_FIXTURE",
            "n": 5,
            "operational_gold": False,
        }
    else:
        # Prefer explicit corpus; for locked ops default to real scaffold
        if args.corpus is not None:
            corpus_path = args.corpus
        elif args.synthetic:
            corpus_path = DEFAULT_SYNTHETIC
        elif DEFAULT_REAL.is_file() or True:
            # Ensure real scaffold exists; may be empty → BLOCKED_INSUFFICIENT
            ensure_real_corpus_file(DEFAULT_REAL)
            # If user asked locked path without --synthetic and real is empty,
            # still run real path for honest blockers. Use synthetic only with --synthetic.
            real_data = load_gold_corpus(DEFAULT_REAL) if DEFAULT_REAL.is_file() else None
            if real_data and (real_data.get("records") or args.corpus):
                corpus_path = DEFAULT_REAL
            elif DEFAULT_SYNTHETIC.is_file() and args.synthetic:
                corpus_path = DEFAULT_SYNTHETIC
            elif DEFAULT_REAL.is_file():
                corpus_path = DEFAULT_REAL
            else:
                corpus_path = DEFAULT_SYNTHETIC

        # When --corpus not set and not --synthetic, prefer real for locked honesty
        if args.corpus is None and not args.synthetic:
            ensure_real_corpus_file(DEFAULT_REAL)
            corpus_path = DEFAULT_REAL

        if not corpus_path.is_file():
            print(f"corpus missing: {corpus_path}", file=sys.stderr)
            return 2

        corpus = load_gold_corpus(corpus_path)
        adequacy = locked_test_adequacy(corpus, cfg=cfg.get("evaluation"))
        corpus_manifest_data = corpus_manifest(corpus_path, corpus)
        corpus_manifest_data["locked_adequacy"] = adequacy
        corpus_manifest_data["split_stats"] = split_stats(corpus)

        # Annotation artifacts (provenance / agreement / adjudications)
        write_annotation_artifacts(
            list(corpus.get("records") or []),
            args.out,
        )

        result = run_from_gold_corpus(
            corpus_path,
            split=args.split,
            config=cfg,
            force_fake_llm=force_fake,
            include_distractors=args.include_distractors,
            full_suite=full_suite,
            rc_v2_intact=rc_v2,
            run_embedding_benchmark=args.embedding_benchmark,
        )

    paths = write_campaign_artifacts(
        result,
        args.out,
        corpus_manifest=corpus_manifest_data,
    )

    # Integration gate artifacts
    integ = PROJECT_ROOT / "artifacts/integration"
    integ.mkdir(parents=True, exist_ok=True)
    gate = {
        "gate_id": "SECTOR-CLASSIFIER-RECALL-GATE",
        "terminal_status": result.terminal_status,
        "active_blockers": result.active_blockers,
        "required_honest_blockers": sorted(REQUIRED_HONEST_BLOCKERS),
        "campaign": "HYBRID-SECTOR-RECALL-LLM-ARBITER-01",
        "offline_default": True,
        "paid_llm_default": False,
        "pr_131": "CHANGES_REQUESTED_RECALL_ASSURANCE",
        "evaluation_level": result.evaluation.get("evaluation_level"),
        "corpus_kind": result.evaluation.get("corpus_kind"),
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
    print(f"active_blockers={result.active_blockers}", file=sys.stderr)
    print(f"artifacts={args.out}", file=sys.stderr)
    print(f"files={len(paths)}", file=sys.stderr)

    if args.require_ready:
        if result.terminal_status != READY:
            print(
                f"--require-ready: terminal {result.terminal_status!r} != {READY!r}",
                file=sys.stderr,
            )
            return 1
    return 0


def _integration_md(result) -> str:
    blockers = ", ".join(result.active_blockers) or "none"
    return f"""# Sector Classifier — Hybrid Recall + LLM Arbiter

## Status

`{result.terminal_status}`

Active blockers: `{blockers}`

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

## Evaluation levels

- **A** unit fixtures
- **B** `SYNTHETIC_ADVERSARIAL_FIXTURE` (regression only)
- **C** real locked operational gold (only C sustains operational claims)

## Principles

1. Retrieval is not classification.
2. Absence of keyword ≠ absence of opportunity.
3. RRF ranks; it does not exclude before classification.
4. Client sees precision (MATCH only); operations preserve recall (REVIEW).
5. LLM errors never produce NO_MATCH.
6. Never blend synthetic and real rates into one headline.

## Entry

```bash
python -m scripts.ops.campaign_hybrid_sector_recall --fixtures
python -m scripts.ops.campaign_hybrid_sector_recall --synthetic \\
  --corpus tests/fixtures/hybrid_sector/synthetic_adversarial_corpus.json
python -m scripts.ops.campaign_hybrid_sector_recall \\
  --corpus tests/fixtures/hybrid_sector/real_operational_corpus.json \\
  --split locked --out /tmp/hybrid-sector-locked
```

Default CI uses **fake LLM only**. Paid provider requires `--allow-paid-llm` (operational gate).

## Summary

- Universe: {result.universe_metrics.get('raw_universe_count')}
- Candidates: {len(result.candidates)}
- MATCH: {len(result.deliverables.get('deliverable_e_matches') or [])}
- REVIEW: {len(result.deliverables.get('deliverable_e_review_queue') or [])}
- NO_MATCH: {len(result.deliverables.get('deliverable_e_no_match_audit') or [])}
- Level: {result.evaluation.get('evaluation_level')}
- Corpus kind: {result.evaluation.get('corpus_kind')}
"""


if __name__ == "__main__":
    raise SystemExit(main())
