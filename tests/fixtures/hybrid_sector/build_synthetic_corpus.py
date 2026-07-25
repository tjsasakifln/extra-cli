"""Deterministic builder for a small synthetic adversarial gold corpus.

Replaces multi-megabyte committed JSON dumps. Generates enough labeled
records for unit/adversarial structure tests without claiming operational gold.

Usage:
  python -m tests.fixtures.hybrid_sector.build_synthetic_corpus
  python -m tests.fixtures.hybrid_sector.build_synthetic_corpus --out path.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "synthetic_adversarial_corpus.json"

# Compact templates — intentional Level B fixtures only (example.local URLs).
_POSITIVE = (
    "Pavimentação asfáltica de vias urbanas — fixture P{n}",
    "Drenagem pluvial em logradouro — fixture P{n}",
    "Construção de edifício escolar — fixture P{n}",
    "Recuperação estrutural de ponte — fixture P{n}",
    "Melhorias viárias com contenção de encosta — fixture P{n}",
)
_NEGATIVE = (
    "Aquisição de medicamentos e fármacos — fixture N{n}",
    "Manutenção de software e licenças — fixture N{n}",
    "Curso de capacitação para servidores — fixture N{n}",
    "Aquisição de combustíveis — fixture N{n}",
    "Credenciamento de instituições financeiras — fixture N{n}",
)
_AMBIGUOUS = (
    "Melhorias diversas no prédio municipal — fixture A{n}",
    "Serviços de adequação sem memorial — fixture A{n}",
    "Reforma de espaços com fornecimento misto — fixture A{n}",
)

_SOURCES = ("portal_sc", "compras_gov", "pncp")
_SPLITS = ("dev", "calibration", "locked")


def build_records(*, per_class: int = 5) -> list[dict[str, Any]]:
    """Build a small, deterministic adversarial record set."""
    records: list[dict[str, Any]] = []
    n = 0
    for label, templates, segment in (
        ("POSITIVE", _POSITIVE, "paraphrase"),
        ("NEGATIVE", _NEGATIVE, "hard_negative"),
        ("AMBIGUOUS", _AMBIGUOUS, "ambiguous"),
    ):
        for i in range(per_class):
            n += 1
            tmpl = templates[i % len(templates)]
            objeto = tmpl.format(n=n)
            split = _SPLITS[i % len(_SPLITS)]
            source = _SOURCES[i % len(_SOURCES)]
            oid = f"l{n:05d}"
            records.append(
                {
                    "canonical_id": f"{source}::{oid}",
                    "source": source,
                    "official_id": oid,
                    "objeto": objeto,
                    "titulo": "",
                    "items": ["item de fixture sintética de engenharia/adversarial"],
                    "categories": ["fixture"],
                    "orgao": "Secretaria Municipal de Obras",
                    "municipio": "Florianópolis",
                    "uf": "SC",
                    "modalidade": "Pregão Eletrônico",
                    "valor_estimado": 100_000.0 + n * 1000,
                    "data_encerramento": "2026-12-31",
                    "urls": [f"https://example.local/edital/{oid}"],
                    "has_edital": True,
                    "has_tr": label != "NEGATIVE",
                    "has_etp": False,
                    "has_anexos": False,
                    "label": label,
                    "segment": segment,
                    "criticality": "medium",
                    "justificativa": f"rótulo sintético independente {label}",
                    "evidence_span": objeto[:80],
                    "has_keyword": label == "POSITIVE" and i % 2 == 0,
                    "object_clarity": "partial" if label == "AMBIGUOUS" else "clear",
                    "split": split,
                    "second_review": True,
                    "label_origin": "human_authored_fixture_independent",
                    "date": "2025-06-01",
                    "value_band": "mid",
                    "source_coverage_status": "fixture",
                    "source_freshness_status": "fixture",
                }
            )
    return records


def build_corpus(*, per_class: int = 5) -> dict[str, Any]:
    records = build_records(per_class=per_class)
    return {
        "corpus_id": "hybrid-sector-synthetic-adversarial-v2-small",
        "version": "2.0.0",
        "label_policy": (
            "SYNTHETIC_ADVERSARIAL_FIXTURE — built by "
            "tests.fixtures.hybrid_sector.build_synthetic_corpus. "
            "NOT operational gold. Do not use for commercial recall/precision claims."
        ),
        "dual_review_policy": (
            "synthetic dual_review boolean only — NOT human dual labeling proof."
        ),
        "splits": list(_SPLITS),
        "records": records,
        "corpus_kind": "SYNTHETIC_ADVERSARIAL_FIXTURE",
        "evaluation_level": "B",
        "operational_gold": False,
        "not_for": ["commercial_ready", "operational_recall_claim"],
        "builder": "tests.fixtures.hybrid_sector.build_synthetic_corpus",
    }


def write_corpus(path: Path | None = None, *, per_class: int = 5) -> Path:
    out = path or DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build_corpus(per_class=per_class)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--per-class", type=int, default=8)
    args = parser.parse_args(argv)
    path = write_corpus(args.out, per_class=args.per_class)
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"wrote {path} records={len(data['records'])} bytes={path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
