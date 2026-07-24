#!/usr/bin/env python3
"""Seed sc_public_entities from canonical universe into an isolated DSN.

Used by EXTRA-LIVE-CONSULTING-PACK-01 so workspace views (expiring/winners)
work without touching VPS. Never points at production.
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("CAMPAIGN_TEST_DSN") or os.getenv("LOCAL_DATALAKE_DSN"))
    p.add_argument("--seed", default="fixtures/canonical_universe_r0.xlsx")
    args = p.parse_args(argv)
    if not args.dsn:
        print("DSN required", file=sys.stderr)
        return 2
    low = args.dsn.lower()
    if any(x in low for x in ("ec-prod", "extra_prod", "/opt/extra")):
        print("ISOLATION_FAIL: refusing prod DSN", file=sys.stderr)
        return 2
    import psycopg2

    from scripts.lib.universe import load_canonical_universe
    u = load_canonical_universe(seed_path=args.seed)
    conn = psycopg2.connect(args.dsn)
    conn.autocommit = True
    n = 0
    with conn.cursor() as cur:
        for e in u.included:
            cur.execute(
                """
                INSERT INTO sc_public_entities (
                    razao_social, cnpj_8, municipio, codigo_ibge, natureza_juridica,
                    latitude, longitude, distancia_fk, raio_200km, is_active
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                ON CONFLICT (cnpj_8) DO UPDATE SET
                    razao_social = EXCLUDED.razao_social,
                    municipio = EXCLUDED.municipio,
                    raio_200km = EXCLUDED.raio_200km,
                    is_active = TRUE
                """,
                (
                    e.razao_social or e.entity_id,
                    e.cnpj8,
                    e.municipio,
                    e.codigo_ibge,
                    e.natureza_juridica,
                    e.latitude,
                    e.longitude,
                    e.distancia_km,
                    bool(e.within_radius),
                ),
            )
            n += 1
    conn.close()
    import json

    print(json.dumps({"seeded": n, "seed": args.seed}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
