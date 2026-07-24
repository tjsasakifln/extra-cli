"""Seed isolated linkage DB from authenticated local artifacts (not soak/VPS).

Sources:
  - consulting-package/contracts.csv (real contracts export)
  - optional full custom dump path
  - entity_source_registry.jsonl (1093 universe)
  - open opportunities derived only from real contract organs that still have
    matching rows in a provided opportunities JSONL/CSV, OR from a minimal
    set of real open-tender fields already present in evidence files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


def connect(dsn: str):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    return conn


def load_contracts_csv(conn, path: Path, *, limit: int | None = None) -> int:
    n = 0
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        with conn.cursor() as cur:
            for row in reader:
                cid = (row.get("contrato_id") or "").strip()
                if not cid:
                    continue
                cur.execute(
                    """
                    INSERT INTO pncp_supplier_contracts (
                        contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj,
                        fornecedor_nome, objeto_contrato, valor_total,
                        data_assinatura, data_publicacao, source, is_active
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,'pncp',TRUE
                    )
                    ON CONFLICT (contrato_id) DO UPDATE SET
                        orgao_cnpj = EXCLUDED.orgao_cnpj,
                        fornecedor_cnpj = EXCLUDED.fornecedor_cnpj,
                        objeto_contrato = EXCLUDED.objeto_contrato,
                        last_seen_at = now()
                    """,
                    (
                        cid,
                        row.get("orgao_cnpj") or None,
                        row.get("orgao_nome") or None,
                        row.get("fornecedor_cnpj") or None,
                        row.get("fornecedor_nome") or None,
                        row.get("objeto_contrato") or None,
                        row.get("valor_total") or None,
                        row.get("data_assinatura") or None,
                        row.get("data_publicacao") or None,
                    ),
                )
                n += 1
                if limit and n >= limit:
                    break
        conn.commit()
    return n


def load_entities_jsonl(conn, path: Path) -> int:
    n = 0
    with path.open(encoding="utf-8") as f, conn.cursor() as cur:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            cnpj = "".join(ch for ch in str(rec.get("cnpj") or "") if ch.isdigit())
            cnpj8 = cnpj[:8] if len(cnpj) >= 8 else cnpj
            if not cnpj8:
                continue
            cur.execute(
                """
                INSERT INTO sc_public_entities (
                    razao_social, cnpj_8, municipio, codigo_ibge,
                    natureza_juridica, raio_200km, is_active
                ) VALUES (%s,%s,%s,%s,%s,TRUE,TRUE)
                ON CONFLICT DO NOTHING
                """,
                (
                    rec.get("razao_social") or cnpj8,
                    cnpj8,
                    rec.get("municipio"),
                    rec.get("ibge_code"),
                    rec.get("natureza_juridica"),
                ),
            )
            # entity_source_registry if table exists
            cur.execute(
                """
                INSERT INTO entity_source_registry (
                    canonical_id, razao_social, cnpj, natureza_juridica,
                    municipio, uf, ibge_code, access_status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'mapped')
                ON CONFLICT (canonical_id) DO NOTHING
                """,
                (
                    rec.get("canonical_id") or f"{cnpj8}:seed",
                    rec.get("razao_social") or cnpj8,
                    cnpj if cnpj else cnpj8,
                    rec.get("natureza_juridica") or "unknown",
                    rec.get("municipio"),
                    rec.get("uf") or "SC",
                    rec.get("ibge_code"),
                ),
            )
            n += 1
        conn.commit()
    return n


def seed_opportunities_from_top_organs(conn, *, n_organs: int = 5, per_organ: int = 1) -> list[int]:
    """Create open opportunities for organs that have real historical contracts.

    The opportunity rows use real organ CNPJ/name/objeto patterns drawn from
    actual contracts in the isolated DB (not invented tax ids). They represent
    the investigation cut for linkage proof when live open-tender rows are
    unavailable offline. Claim language must treat them as snapshot-seeded
    open opportunities for linkage, not as proof of a live PNCP crawl in this run.
    """
    ids: list[int] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT orgao_cnpj, MAX(orgao_nome) AS orgao_nome,
                   MAX(objeto_contrato) AS objeto, MAX(uf) AS uf,
                   MAX(municipio) AS municipio, COUNT(*) AS n
            FROM pncp_supplier_contracts
            WHERE orgao_cnpj IS NOT NULL AND length(regexp_replace(orgao_cnpj,'\\D','','g')) >= 8
            GROUP BY orgao_cnpj
            ORDER BY COUNT(*) DESC
            LIMIT %s
            """,
            (n_organs,),
        )
        organs = list(cur.fetchall())
        for org in organs:
            for i in range(per_organ):
                cnpj = org["orgao_cnpj"]
                objeto = (org["objeto"] or "SERVICOS DIVERSOS")[:500]
                source_id = f"linkage-seed:{cnpj}:{i}"
                content = hashlib.sha256(f"{source_id}|{objeto}".encode()).hexdigest()
                cur.execute(
                    """
                    INSERT INTO opportunity_intel (
                        source, source_id, content_hash, numero_controle_pncp,
                        orgao_cnpj, orgao_nome, uf, municipio, objeto,
                        status_canonico, is_active, ranking
                    ) VALUES (
                        'pncp', %s, %s, %s,
                        %s, %s, COALESCE(%s,'SC'), %s, %s,
                        'open', TRUE, 'REVIEW'
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    (
                        source_id,
                        content,
                        f"SEED-PNCP-{cnpj}-{i}",
                        cnpj,
                        org["orgao_nome"],
                        org["uf"],
                        org["municipio"],
                        f"[SNAPSHOT-SEED open] {objeto}",
                    ),
                )
                row = cur.fetchone()
                if row:
                    ids.append(int(row["id"]))
                else:
                    cur.execute(
                        "SELECT id FROM opportunity_intel WHERE source=%s AND source_id=%s",
                        ("pncp", source_id),
                    )
                    row = cur.fetchone()
                    if row:
                        ids.append(int(row["id"]))
        conn.commit()
    return ids


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default=os.environ.get("LINKAGE_TEST_DSN"))
    p.add_argument("--contracts-csv", type=Path)
    p.add_argument("--entities-jsonl", type=Path)
    p.add_argument("--contract-limit", type=int, default=None)
    p.add_argument("--seed-opportunities", type=int, default=5)
    args = p.parse_args(argv)
    if not args.dsn:
        print("missing dsn", file=sys.stderr)
        return 2
    from scripts.linkage.isolation import assert_isolated

    assert_isolated(args.dsn)
    conn = connect(args.dsn)
    out: dict[str, Any] = {}
    try:
        if args.contracts_csv and args.contracts_csv.exists():
            out["contracts_loaded"] = load_contracts_csv(conn, args.contracts_csv, limit=args.contract_limit)
        if args.entities_jsonl and args.entities_jsonl.exists():
            out["entities_loaded"] = load_entities_jsonl(conn, args.entities_jsonl)
        if args.seed_opportunities:
            out["opportunity_ids"] = seed_opportunities_from_top_organs(conn, n_organs=args.seed_opportunities)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM pncp_supplier_contracts")
            out["contracts_total"] = int(cur.fetchone()["n"])
            cur.execute("SELECT count(*) AS n FROM opportunity_intel WHERE is_active")
            out["opportunities_total"] = int(cur.fetchone()["n"])
    finally:
        conn.close()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
