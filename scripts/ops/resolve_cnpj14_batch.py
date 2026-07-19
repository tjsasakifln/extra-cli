#!/usr/bin/env python3
"""Batch-resolve CNPJ-14 for residual 200km entities via PNCP orgaos API.

Writes append-only cache at data/cnpj14_cache/pncp_orgaos_by_name.jsonl.
Respects rate limits with delay + 429 backoff.

Usage:
  python3 -m scripts.ops.resolve_cnpj14_batch --limit 150 --delay 0.8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg2

from scripts.entity_identity.pncp_orgao_resolve import pick_match, search_orgaos

REPO = Path(__file__).resolve().parents[2]
CACHE_DEFAULT = REPO / "data/cnpj14_cache/pncp_orgaos_by_name.jsonl"


def load_have(path: Path) -> set[str]:
    have: set[str] = set()
    if not path.exists():
        return have
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            have.add(json.loads(line)["cnpj8"])
    return have


def residual_rows(cur, have: set[str], limit: int) -> list[tuple]:
    cur.execute(
        """
        WITH den AS (
          SELECT cnpj_8, razao_social, municipio
          FROM sc_public_entities WHERE is_active AND raio_200km
        ),
        hit AS (
          SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'),8) c8
          FROM pncp_raw_bids
          WHERE LENGTH(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'))>=8
          UNION
          SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'),8) c8
          FROM pncp_supplier_contracts
          WHERE LENGTH(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'))>=8
        )
        SELECT d.cnpj_8, d.razao_social, d.municipio
        FROM den d
        LEFT JOIN hit h ON d.cnpj_8 = h.c8
        WHERE h.c8 IS NULL
        ORDER BY d.razao_social
        """
    )
    out = []
    for c8, razao, mun in cur.fetchall():
        if c8 in have:
            continue
        out.append((c8, razao, mun))
        if len(out) >= limit:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--delay", type=float, default=0.8)
    p.add_argument("--cache", type=Path, default=CACHE_DEFAULT)
    args = p.parse_args(argv)

    dsn = args.dsn or os.environ.get(
        "LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    cache = args.cache if args.cache.is_absolute() else REPO / args.cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    have = load_have(cache)

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    rows = residual_rows(cur, have, args.limit)
    conn.close()
    print(f"todo={len(rows)} already_cached={len(have)}", flush=True)

    resolved = 0
    errors = 0
    for i, (c8, razao, mun) in enumerate(rows, 1):
        try:
            hits = search_orgaos(razao)
            time.sleep(args.delay)
            m = pick_match(c8, razao, hits)
            if not m and mun:
                hits2 = search_orgaos(f"PREFEITURA {mun}")
                time.sleep(args.delay)
                m = pick_match(c8, razao, hits2)
            if m:
                c14, method, _h = m
                with cache.open("a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "cnpj8": c8,
                                "cnpj14": c14,
                                "method": method,
                                "razao": razao,
                                "resolved_at": datetime.now(UTC).isoformat(),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                resolved += 1
                have.add(c8)
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"err {c8} {e}", flush=True)
            if "429" in str(e):
                time.sleep(60)
        if i % 25 == 0 or i == len(rows):
            print(f"progress {i}/{len(rows)} resolved={resolved} errors={errors}", flush=True)

    print(f"done resolved={resolved} of={len(rows)} cache_total={len(have)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
