#!/usr/bin/env python3
"""Stratified opportunity recall benchmark.

Compares system capture against an independent sample of official portal items.
Database row counts are NEVER a valid proxy for recall.

Usage:
  python -m scripts.coverage.recall_benchmark scaffold
  python -m scripts.coverage.recall_benchmark run --sample output/coverage/recall_sample.json
  python -m scripts.coverage.recall_benchmark evaluate
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE = PROJECT_ROOT / "output" / "coverage" / "recall_sample.json"
DEFAULT_RESULT = PROJECT_ROOT / "output" / "coverage" / "recall_benchmark.json"

# Stratified strata required by mandate
REQUIRED_STRATA = [
    "municipio_grande",
    "municipio_medio",
    "municipio_pequeno",
    "admin_direta",
    "admin_indireta",
    "autarquia",
    "fundacao",
    "camara",
    "consorcio",
    "source_api",
    "source_html",
    "source_pdf",
    "source_js",
    "platform_pncp",
    "platform_sc_compras",
    "platform_ciga",
]


def scaffold_sample(path: Path) -> dict[str, Any]:
    """Create empty stratified sample template for manual/portal verification."""
    sample = {
        "schema_version": 1,
        "purpose": "Independent stratified recall sample — fill portal_items then run evaluate",
        "window": {
            "start": "2026-07-01",
            "end": "2026-07-17",
            "notes": "Fill with items observed on official portals during window",
        },
        "methodology": {
            "rule": "For each portal_item, check if system captured it (by official id/url/hash)",
            "forbidden": "Do not use COUNT(*) from database as recall proxy",
            "required_strata": REQUIRED_STRATA,
        },
        "portal_items": [
            {
                "sample_id": "EXAMPLE-001",
                "strata": ["municipio_medio", "admin_direta", "source_api", "platform_pncp"],
                "orgao_nome": "MUNICIPIO EXEMPLO",
                "cnpj": None,
                "objeto": "Reforma de prédio público — PREENCHER",
                "portal_url": "https://example.invalid/edital/1",
                "published_at": "2026-07-10",
                "source_platform": "pncp",
                "external_id": None,
                "captured_by_system": None,  # true|false after evaluation
                "capture_evidence": None,
                "notes": "Replace with real portal observation",
            }
        ],
        "status": "SCAFFOLD",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sample


def evaluate_sample(sample: dict[str, Any]) -> dict[str, Any]:
    items = sample.get("portal_items") or []
    real = [i for i in items if not str(i.get("sample_id", "")).startswith("EXAMPLE")]
    if not real:
        return {
            "status": "NOT_READY",
            "captured": None,
            "published_in_sample": None,
            "pct": None,
            "as_of": date.today().isoformat(),
            "formula": "captured / published_in_sample",
            "notes": (
                "Sample still scaffold-only (EXAMPLE items). "
                "Populate portal_items from independent portal observation, "
                "set captured_by_system true/false with evidence, re-run evaluate."
            ),
            "strata_coverage": {},
            "forbidden_proxy_used": False,
        }

    labeled = [i for i in real if i.get("captured_by_system") is not None]
    unlabeled = len(real) - len(labeled)
    invalid_captured = [
        i for i in labeled if i.get("captured_by_system") is True and not i.get("capture_evidence")
    ]
    invalid_misses = [
        i
        for i in labeled
        if i.get("captured_by_system") is False
        and i.get("miss_reason") not in {"source_gap", "match_gap", "window_gap", "other"}
    ]
    notes = "All real items labeled" if not unlabeled else f"{unlabeled} items missing captured_by_system label"

    published = len(real)
    captured = sum(1 for i in labeled if i.get("captured_by_system") is True)
    strata_cov: dict[str, dict[str, int]] = {}
    for i in labeled:
        for s in i.get("strata") or []:
            strata_cov.setdefault(s, {"published": 0, "captured": 0})
            strata_cov[s]["published"] += 1
            if i.get("captured_by_system") is True:
                strata_cov[s]["captured"] += 1

    missing_strata = [s for s in REQUIRED_STRATA if s not in strata_cov]
    status = (
        "READY"
        if published > 0 and not missing_strata and not unlabeled and not invalid_captured and not invalid_misses
        else "PARTIAL"
    )
    if published == 0:
        status = "NOT_READY"

    pct = (captured / published * 100.0) if published and not unlabeled else None
    return {
        "status": status,
        "captured": captured if published else None,
        "published_in_sample": published if published else None,
        "pct": pct,
        "as_of": date.today().isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "formula": "captured / published_in_sample (independent stratified portal sample)",
        "notes": notes
        + (f"; missing_strata={missing_strata}" if missing_strata else "")
        + (f"; captured_without_evidence={len(invalid_captured)}" if invalid_captured else "")
        + (f"; misses_without_reason={len(invalid_misses)}" if invalid_misses else "")
        + "; target recall 95% on validated sample",
        "strata_coverage": strata_cov,
        "forbidden_proxy_used": False,
        "target_pct": 95.0,
    }


def try_match_against_system(sample: dict[str, Any], dsn: str | None = None) -> dict[str, Any]:
    """Best-effort auto-label from opportunity_intel / official_acts by URL or external id."""
    import os

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return sample

    dsn = dsn or os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/pncp_datalake")
    try:
        conn = psycopg2.connect(dsn)
    except Exception:
        return sample

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for item in sample.get("portal_items") or []:
                if str(item.get("sample_id", "")).startswith("EXAMPLE"):
                    continue
                if item.get("captured_by_system") is not None:
                    continue
                ext = item.get("external_id")
                url = item.get("portal_url")
                found = False
                evidence = None
                if ext:
                    cur.execute(
                        """
                        SELECT id, source, source_url FROM opportunity_intel
                        WHERE numero_controle_pncp = %s OR source_id = %s
                        LIMIT 1
                        """,
                        (ext, ext),
                    )
                    row = cur.fetchone()
                    if row:
                        found = True
                        evidence = f"opportunity_intel.id={row['id']}"
                if not found and url and "example.invalid" not in str(url):
                    cur.execute(
                        """
                        SELECT id, source FROM opportunity_intel
                        WHERE source_url = %s OR link_edital = %s
                        LIMIT 1
                        """,
                        (url, url),
                    )
                    row = cur.fetchone()
                    if row:
                        found = True
                        evidence = f"opportunity_intel.id={row['id']} url match"
                item["captured_by_system"] = found
                item["capture_evidence"] = evidence
                if not found:
                    item["capture_evidence"] = "not_found_in_opportunity_intel"
    finally:
        conn.close()
    return sample


def cmd_scaffold(args: argparse.Namespace) -> int:
    path = Path(args.output or DEFAULT_SAMPLE)
    scaffold_sample(path)
    print(f"Scaffold written: {path}")
    print("Next: replace EXAMPLE items with real portal observations, then run evaluate.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    sample_path = Path(args.sample or DEFAULT_SAMPLE)
    if not sample_path.exists():
        scaffold_sample(sample_path)
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    if args.auto_match:
        sample = try_match_against_system(sample, dsn=args.dsn)
        sample_path.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = evaluate_sample(sample)
    out = Path(args.output or DEFAULT_RESULT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Wrote {out}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    args.sample = args.sample if hasattr(args, "sample") else DEFAULT_SAMPLE
    return cmd_run(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stratified opportunity recall benchmark")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scaffold", help="Create empty stratified sample template")
    s.add_argument("--output", "-o", default=str(DEFAULT_SAMPLE))
    s.set_defaults(func=cmd_scaffold)

    r = sub.add_parser("run", help="Evaluate sample and write recall_benchmark.json")
    r.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    r.add_argument("--output", "-o", default=str(DEFAULT_RESULT))
    r.add_argument("--auto-match", action="store_true", help="Try match portal items against DB")
    r.add_argument("--dsn", default=None)
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("evaluate", help="Alias for run")
    e.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    e.add_argument("--output", "-o", default=str(DEFAULT_RESULT))
    e.add_argument("--auto-match", action="store_true")
    e.add_argument("--dsn", default=None)
    e.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
