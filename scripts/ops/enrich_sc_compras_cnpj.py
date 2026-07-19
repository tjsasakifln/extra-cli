#!/usr/bin/env python3
"""Enrich sc_compras rows missing orgao_cnpj via deterministic name match.

Maps orgao_razao_social → sc_public_entities.cnpj_8 (and explicit aliases).
Stores placeholder full CNPJ as cnpj8 + '000000' so generated orgao_cnpj_8 works.
Does NOT invent identity beyond deterministic dictionary match.

Usage:
  python3 -m scripts.ops.enrich_sc_compras_cnpj --dsn "$LOCAL_DATALAKE_DSN"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg2

# Explicit portal name → cnpj8 (must exist in universe when claimed covered)
EXPLICIT_ALIASES: dict[str, str] = {
    "FUNDACAO UNIVERSIDADE DO ESTADO DE SANTA CATARINA UDESC": "83891283",
    "SECRETARIA DE ESTADO DA INFRAESTRUTURA E MOBILIDADE SIE": "82951344",
    "POLICIA CIVIL PC": "15211786",
    "DEFENSORIA PUBLICA DO ESTADO DE SANTA CATARINA DPE": "16867676",
    "INSTITUTO DE METROLOGIA DE SANTA CATARINA IMETRO SC": "07410720",
    "POLICIA MILITAR DO ESTADO DE SANTA CATARINA PM SC": "83931550",
    "POLICIA CIENTIFICA DE SANTA CATARINA": "36127642",
    "PROCURADORIA GERAL DO ESTADO DE SANTA CATARINA PGE": "76276823",
    "CORPO DE BOMBEIROS MILITAR CBM SC FUNDO DE MELHORIA": "14186135",
}


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9 ]+", " ", s.upper())
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+-\s+[A-Z0-9]{2,10}$", "", s)
    return s


def build_name_index(cur: Any) -> dict[str, str]:
    cur.execute("SELECT cnpj_8, razao_social FROM sc_public_entities WHERE is_active")
    by_name: dict[str, str] = {}
    for c8, nome in cur.fetchall():
        k = norm(nome)
        if k and k not in by_name:
            by_name[k] = c8
    for k, c8 in list(by_name.items()):
        for prefix in (
            "MUNICIPIO DE ",
            "PREFEITURA MUNICIPAL DE ",
            "PREFEITURA DE ",
            "SECRETARIA DE ESTADO DA ",
            "SECRETARIA DE ESTADO DE ",
        ):
            if k.startswith(prefix):
                by_name.setdefault(k[len(prefix) :], c8)
    by_name.update(EXPLICIT_ALIASES)
    return by_name


def resolve_cnpj8(nome: str | None, by_name: dict[str, str]) -> str | None:
    k = norm(nome)
    if c8 := by_name.get(k):
        return c8
    k2 = re.sub(r"\s+[A-Z]{2,6}$", "", k).strip()
    if c8 := by_name.get(k2):
        return c8
    for ak, av in EXPLICIT_ALIASES.items():
        if ak in k or k in ak:
            return av
    return None


def enrich(dsn: str) -> dict[str, Any]:
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    by_name = build_name_index(cur)
    cur.execute(
        """
        SELECT pncp_id, orgao_razao_social FROM pncp_raw_bids
        WHERE source='sc_compras' AND (orgao_cnpj IS NULL OR orgao_cnpj='')
        """
    )
    rows = cur.fetchall()
    matched = 0
    unmatched: Counter[str] = Counter()
    for pid, nome in rows:
        c8 = resolve_cnpj8(nome, by_name)
        if c8:
            cur.execute(
                "UPDATE pncp_raw_bids SET orgao_cnpj=%s, updated_at=NOW() WHERE pncp_id=%s",
                (c8 + "000000", pid),
            )
            matched += 1
        else:
            unmatched[nome or ""] += 1
    conn.commit()

    cur.execute(
        """
        WITH den AS (SELECT cnpj_8 FROM sc_public_entities WHERE is_active AND raio_200km),
        hit AS (
          SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'),8) c8
          FROM pncp_raw_bids
          WHERE LENGTH(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'))>=8
        )
        SELECT COUNT(*) FROM den d JOIN hit h ON d.cnpj_8=h.c8
        """
    )
    pe = int(cur.fetchone()[0])
    conn.close()
    return {
        "measured_at": datetime.now(UTC).isoformat(),
        "rows_seen": len(rows),
        "matched_updates": matched,
        "unmatched_names": len(unmatched),
        "top_unmatched": unmatched.most_common(15),
        "presence_editais_200km": pe,
        "presence_editais_pct": round(100 * pe / 1093, 4),
        "method": "deterministic name match; placeholder full CNPJ = cnpj8||'000000'",
        "claims_forbidden": [
            "full CNPJ verified for enriched rows",
            "seven-stage operational coverage",
            "95% coverage",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=None)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    import os

    dsn = args.dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        print("DSN required", file=sys.stderr)
        return 2
    result = enrich(dsn)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
