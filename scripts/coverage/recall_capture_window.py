#!/usr/bin/env python3
"""Capture official publications into isolated opportunity_intel for recall replay.

Does NOT read operational production DSN. Fetches public APIs and upserts by
official id. Used after gold sample freeze to measure true capture/match.

Usage:
  RECALL_ISOLATED_DSN=postgresql://test:test@127.0.0.1:5437/extra_recall_rc \\
  python -m scripts.coverage.recall_capture_window --window-start 2026-07-01 --window-end 2026-07-22
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.coverage.independent_inventory import (  # noqa: E402
    collect_ciga,
    collect_pncp,
    collect_sc_compras,
)

USER_AGENT = "ExtraConsultoria-RecallCampaign/1.0"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def upsert_rows(dsn: str, rows: list[dict[str, Any]], run_token: str) -> dict[str, int]:
    import psycopg2

    inserted = 0
    updated = 0
    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            for r in rows:
                source = r["source"]
                source_id = str(r["source_id"])
                cur.execute(
                    """
                    SELECT id FROM opportunity_intel
                    WHERE source = %s AND source_id = %s
                    LIMIT 1
                    """,
                    (source, source_id),
                )
                existing = cur.fetchone()
                payload = (
                    source,
                    source_id,
                    r.get("source_url"),
                    r.get("content_hash"),
                    r.get("numero_controle_pncp"),
                    r.get("orgao_cnpj"),
                    r.get("orgao_nome"),
                    r.get("uf") or "SC",
                    r.get("municipio"),
                    r.get("objeto"),
                    r.get("data_publicacao"),
                    r.get("status_canonico") or "open",
                    r.get("status_fonte"),
                    r.get("link_edital"),
                    True,
                    json.dumps(r.get("proveniencia") or {"run": run_token}),
                    run_token,
                )
                if existing:
                    cur.execute(
                        """
                        UPDATE opportunity_intel SET
                          source_url = COALESCE(%s, source_url),
                          content_hash = COALESCE(%s, content_hash),
                          numero_controle_pncp = COALESCE(%s, numero_controle_pncp),
                          orgao_cnpj = COALESCE(%s, orgao_cnpj),
                          orgao_nome = COALESCE(%s, orgao_nome),
                          uf = COALESCE(%s, uf),
                          municipio = COALESCE(%s, municipio),
                          objeto = COALESCE(%s, objeto),
                          data_publicacao = COALESCE(%s::timestamptz, data_publicacao),
                          status_canonico = COALESCE(%s, status_canonico),
                          status_fonte = COALESCE(%s, status_fonte),
                          link_edital = COALESCE(%s, link_edital),
                          is_active = %s,
                          source_active = TRUE,
                          proveniencia = COALESCE(proveniencia, '{}'::jsonb) || %s::jsonb,
                          updated_at = NOW(),
                          last_seen_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            payload[2],
                            payload[3],
                            payload[4],
                            payload[5],
                            payload[6],
                            payload[7],
                            payload[8],
                            payload[9],
                            payload[10],
                            payload[11],
                            payload[12],
                            payload[13],
                            payload[14],
                            payload[15],
                            existing[0],
                        ),
                    )
                    updated += 1
                else:
                    cur.execute(
                        """
                        INSERT INTO opportunity_intel (
                          source, source_id, source_url, content_hash, numero_controle_pncp,
                          orgao_cnpj, orgao_nome, uf, municipio, objeto,
                          data_publicacao, status_canonico, status_fonte, link_edital,
                          is_active, source_active, proveniencia, crawl_batch_id,
                          first_seen_at, last_seen_at, ingested_at, updated_at
                        ) VALUES (
                          %s,%s,%s,%s,%s,
                          %s,%s,%s,%s,%s,
                          %s::timestamptz,%s,%s,%s,
                          %s,TRUE,%s::jsonb,%s,
                          NOW(),NOW(),NOW(),NOW()
                        )
                        """,
                        (
                            payload[0],
                            payload[1],
                            payload[2],
                            payload[3],
                            payload[4],
                            payload[5],
                            payload[6],
                            payload[7],
                            payload[8],
                            payload[9],
                            payload[10],
                            payload[11],
                            payload[12],
                            payload[13],
                            payload[14],
                            payload[15],
                            payload[16],
                        ),
                    )
                    inserted += 1
        conn.commit()
    finally:
        conn.close()
    return {"inserted": inserted, "updated": updated, "total": len(rows)}


def inventory_to_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for it in items:
        platform = it.get("source_platform") or "unknown"
        if platform == "pncp":
            source = "pncp"
        elif platform == "sc_compras":
            source = "sc_compras"
        elif platform in {"ciga_dom", "ciga", "ciga_ckan"}:
            source = "ciga_ckan"
        else:
            source = platform
        ext = str(it.get("external_id") or it.get("sample_id"))
        url = it.get("portal_url")
        rows.append(
            {
                "source": source,
                "source_id": ext,
                "source_url": url,
                "link_edital": url,
                "content_hash": it.get("content_hash") or _hash(ext, str(url or "")),
                "numero_controle_pncp": ext if source == "pncp" else None,
                "orgao_cnpj": it.get("cnpj"),
                "orgao_nome": it.get("orgao_nome"),
                "municipio": it.get("municipio"),
                "objeto": it.get("objeto"),
                "data_publicacao": it.get("published_at"),
                "status_canonico": "open",
                "status_fonte": it.get("situacao") or "publicado",
                "proveniencia": {
                    "inventory_source": it.get("inventory_source"),
                    "sample_id": it.get("sample_id"),
                    "capture_path": "recall_capture_window",
                },
            }
        )
    return rows


def capture_from_live_apis(window_start: str, window_end: str) -> list[dict[str, Any]]:
    """Re-fetch live APIs (not the gold file) for capture path independence."""
    items: list[dict[str, Any]] = []
    items.extend(collect_pncp(window_start, window_end, max_items=120))
    time.sleep(0.4)
    items.extend(collect_sc_compras(year=int(window_start[:4]), max_items=80))
    time.sleep(0.4)
    items.extend(collect_ciga(max_items=80))
    return items


def cmd_run(args: argparse.Namespace) -> int:
    dsn = args.dsn or os.getenv("RECALL_ISOLATED_DSN") or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        print(json.dumps({"error": "DSN required", "status": "NOT_READY"}))
        return 2
    if "ec-prod" in dsn or "/opt/extra" in dsn:
        print(json.dumps({"error": "production DSN refused", "status": "FAIL"}))
        return 3

    run_token = f"recall-capture-{_utc_now().replace(':', '')}"
    if args.from_gold:
        gold = json.loads(Path(args.from_gold).read_text(encoding="utf-8"))
        live_items = gold.get("portal_items") or []
        mode = "from_gold_identity_replay"
    else:
        live_items = capture_from_live_apis(args.window_start, args.window_end)
        mode = "live_api_recapture"

    rows = inventory_to_rows(live_items)
    stats = upsert_rows(dsn, rows, run_token)
    out = {
        "status": "OK",
        "mode": mode,
        "run_token": run_token,
        "window": {"start": args.window_start, "end": args.window_end},
        "fetched_items": len(live_items),
        "upsert": stats,
        "generated_at": _utc_now(),
        "production_touched": False,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Isolated recall window capture")
    p.add_argument("--window-start", default="2026-07-01")
    p.add_argument("--window-end", default="2026-07-22")
    p.add_argument("--dsn", default=None)
    p.add_argument(
        "--from-gold",
        default=None,
        help="Optional: upsert using gold sample identities (still not a denominator proxy)",
    )
    p.add_argument(
        "--out",
        default="artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/replay.json",
    )
    p.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
