#!/usr/bin/env python3
"""Entity-scoped PNCP success_zero probe + persist for contracts (and optional bids).

Proves empty scopes via HTTP 204 / empty page with completion_rule and writes
coverage_evidence rows that satisfy ck_ce_success_zero_scope.

Usage:
  python3 -m scripts.ops.probe_entity_success_zero --data-type contracts --limit 80
  python3 -m scripts.ops.probe_entity_success_zero --data-type contracts --limit 80 --write

Does NOT claim operational 7-stage coverage — only entity-scoped presence proof
or success_zero with provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json

UA = "ExtraConsultoria-OPS95/1.0"
CACHE_DEFAULT = Path("data/cnpj14_cache/pncp_orgaos_by_name.jsonl")
REPO = Path(__file__).resolve().parents[2]


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def load_cache(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        c8 = digits(o.get("cnpj8"))[:8]
        c14 = digits(o.get("cnpj14"))
        if len(c8) == 8 and len(c14) == 14:
            out[c8] = o
    return out


def build_url(data_type: str, cnpj14: str, start: date, end: date, page: int = 1) -> str:
    di, df = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    if data_type == "contracts":
        path = "contratos"
        params = {
            "dataInicial": di,
            "dataFinal": df,
            "pagina": str(page),
            "tamanhoPagina": "50",
            "cnpjOrgao": cnpj14,
        }
    elif data_type == "bids":
        path = "contratacoes/publicacao"
        params = {
            "dataInicial": di,
            "dataFinal": df,
            "pagina": str(page),
            "tamanhoPagina": "50",
            "cnpjOrgao": cnpj14,
        }
    else:
        raise ValueError(f"unsupported data_type={data_type}")
    return f"https://pncp.gov.br/api/consulta/v1/{path}?{urllib.parse.urlencode(params)}"


def http_get(
    url: str,
    timeout: int = 30,
    *,
    max_retries: int = 3,
    base_backoff: float = 8.0,
) -> tuple[int, bytes]:
    """GET with exponential backoff on HTTP 429 / transient 5xx.

    Caps total wait so a single entity cannot stall the batch for minutes.
    """
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS URL: {url[:32]!r}")
    last_status, last_body = 0, b""
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})  # noqa: S310 — HTTPS PNCP consulta API
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — HTTPS PNCP consulta API
                return int(resp.status), resp.read()
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b""
            last_status, last_body = int(e.code), body
            if e.code in (429, 502, 503, 504) and attempt < max_retries:
                # 8, 16, 32 — max ~56s per entity before recording BLOCKED_API
                sleep_s = min(base_backoff * (2**attempt), 40.0)
                time.sleep(sleep_s)
                continue
            return last_status, last_body
        except TimeoutError:
            if attempt < max_retries:
                time.sleep(min(base_backoff * (attempt + 1), 20.0))
                continue
            raise
    return last_status, last_body


def classify_response(status: int, body: bytes) -> dict[str, Any]:
    content_hash = hashlib.sha256(body).hexdigest()
    if status == 204:
        return {
            "verdict": "SUCCESS_ZERO",
            "http_status": 204,
            "total": 0,
            "n_items": 0,
            "content_hash": content_hash,
            "completion_rule": "http_204_complete",
        }
    if status != 200:
        return {
            "verdict": "BLOCKED_API",
            "http_status": status,
            "total": None,
            "n_items": 0,
            "content_hash": content_hash,
            "error": f"http_{status}",
        }
    if not body or body.strip() in (b"", b"[]", b"{}"):
        return {
            "verdict": "SUCCESS_ZERO",
            "http_status": status,
            "total": 0,
            "n_items": 0,
            "content_hash": content_hash,
            "completion_rule": "empty_page_after_valid_scope",
        }
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {
            "verdict": "BLOCKED_API",
            "http_status": status,
            "total": None,
            "n_items": 0,
            "content_hash": content_hash,
            "error": "json_decode",
        }
    items: list[Any]
    total = None
    if isinstance(data, list):
        items = data
        total = len(items)
    elif isinstance(data, dict):
        items = list(data.get("data") or data.get("items") or data.get("conteudo") or [])
        for k in ("totalRegistros", "total", "totalElements", "quantidadeTotal"):
            if data.get(k) is not None:
                try:
                    total = int(data[k])
                    break
                except (TypeError, ValueError):
                    pass
        if total is None:
            total = len(items)
    else:
        items = []
        total = 0
    if total == 0 and len(items) == 0:
        return {
            "verdict": "SUCCESS_ZERO",
            "http_status": status,
            "total": 0,
            "n_items": 0,
            "content_hash": content_hash,
            "completion_rule": "empty_page_after_valid_scope",
        }
    return {
        "verdict": "HAS_DATA",
        "http_status": status,
        "total": total,
        "n_items": len(items),
        "content_hash": content_hash,
        "completion_rule": None,
    }


def residual_entities(cur, cache: dict[str, dict[str, Any]], data_type: str, limit: int) -> list[tuple]:
    """Entities in 200km without lake presence and without existing success_zero for data_type."""
    if data_type == "contracts":
        lake_sql = """
          SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'),8) c8
          FROM pncp_supplier_contracts
          WHERE LENGTH(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'))>=8
        """
    else:
        lake_sql = """
          SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'),8) c8
          FROM pncp_raw_bids
          WHERE LENGTH(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'))>=8
        """
    # lake_sql is a fixed internal whitelist (contracts vs bids tables only), not user input.
    cur.execute(
        f"""
        WITH den AS (
          SELECT id, cnpj_8, razao_social FROM sc_public_entities
          WHERE is_active AND raio_200km
        ),
        lake AS ({lake_sql}),
        sz AS (
          SELECT DISTINCT entity_id FROM coverage_evidence
          WHERE state = 'success_zero' AND data_type = %s
        )
        SELECT d.id, d.cnpj_8, d.razao_social
        FROM den d
        LEFT JOIN lake l ON d.cnpj_8 = l.c8
        LEFT JOIN sz s ON s.entity_id = d.id
        WHERE l.c8 IS NULL AND s.entity_id IS NULL
        ORDER BY d.razao_social
        """,  # noqa: S608 — lake_sql is fixed internal table whitelist only
        (data_type,),
    )
    rows = []
    for eid, c8, razao in cur.fetchall():
        if c8 in cache:
            rows.append((eid, c8, razao, cache[c8]["cnpj14"]))
        if len(rows) >= limit:
            break
    return rows


def insert_success_zero(
    cur,
    *,
    entity_id: int,
    cnpj8: str,
    cnpj14: str,
    data_type: str,
    start: date,
    end: date,
    url: str,
    classified: dict[str, Any],
    run_id: str,
) -> None:
    capability = "historical_contracts" if data_type == "contracts" else "open_tenders"
    scope_key = f"pncp|{data_type}|cnpjOrgao={cnpj14}|{start.isoformat()}..{end.isoformat()}"
    completion_rule = classified["completion_rule"]
    content_hash = classified["content_hash"]
    http_status = classified["http_status"]
    evidence_metadata = {
        "url": url,
        "campaign": "EXTRA-OPS-95",
        "http_status": http_status,
        "content_hash": content_hash,
        "completion_rule": completion_rule,
        "total_registros": 0,
    }
    provenance = {
        "url": url,
        "param": "cnpjOrgao",
        "run_id": run_id,
        "window": {"from": start.isoformat(), "to": end.isoformat(), "days": (end - start).days},
        "http_status": http_status,
        "content_hash": content_hash,
        "pages_fetched": 1,
        "pages_expected": None,
        "completion_rule": completion_rule,
    }
    now = datetime.now(UTC)
    cur.execute(
        """
        INSERT INTO coverage_evidence (
          entity_id, source, data_type, queried_start, queried_end, run_id,
          started_at, completed_at, count_obtained, count_transformed, count_persisted,
          state, metadata, canonical_entity_key, applicability, scope_key,
          checked_at, pages_expected, pages_processed, records_fetched, open_records,
          freshness_status, evidence_metadata, capability, records_expected,
          request_scope, pages_fetched, provenance, satisfactory
        ) VALUES (
          %s, 'pncp', %s, %s, %s, %s,
          %s, %s, 0, 0, 0,
          'success_zero', %s, %s, 'applicable', %s,
          %s, NULL, 1, 0, 0,
          'fresh', %s, %s, 0,
          %s, 1, %s, true
        )
        ON CONFLICT DO NOTHING
        """,
        (
            entity_id,
            data_type,
            start,
            end,
            run_id,
            now,
            now,
            Json({"pilot": "entity_sz", "campaign": "EXTRA-OPS-95"}),
            cnpj8,
            scope_key,
            now,
            Json(evidence_metadata),
            capability,
            scope_key,
            Json(provenance),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=None)
    p.add_argument("--data-type", choices=["contracts", "bids"], default="contracts")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--delay", type=float, default=0.45)
    p.add_argument("--write", action="store_true", help="Persist success_zero rows")
    p.add_argument("--cache", type=Path, default=CACHE_DEFAULT)
    p.add_argument("--output-json", type=Path, default=None)
    args = p.parse_args(argv)

    dsn = args.dsn or __import__("os").environ.get(
        "LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    cache_path = args.cache if args.cache.is_absolute() else REPO / args.cache
    cache = load_cache(cache_path)
    end = date.today()
    start = end - timedelta(days=args.days)
    run_id = f"sz-{args.data_type}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    targets = residual_entities(cur, cache, args.data_type, args.limit)
    results: list[dict[str, Any]] = []
    verdicts: dict[str, int] = {}
    written = 0

    print(f"run_id={run_id} targets={len(targets)} cache={len(cache)} write={args.write}", flush=True)

    for i, (eid, c8, razao, c14) in enumerate(targets, 1):
        url = build_url(args.data_type, c14, start, end)
        try:
            status, body = http_get(url)
            classified = classify_response(status, body)
        except Exception as e:  # noqa: BLE001
            classified = {
                "verdict": "BLOCKED_API",
                "http_status": None,
                "total": None,
                "n_items": 0,
                "content_hash": None,
                "error": f"{type(e).__name__}: {e}",
            }
            status = None
            body = b""

        verdict = classified["verdict"]
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        row = {
            "entity_id": eid,
            "cnpj8": c8,
            "cnpj14": c14,
            "razao": razao,
            "url": url,
            **{k: v for k, v in classified.items() if k != "items"},
        }
        if verdict == "SUCCESS_ZERO" and args.write:
            try:
                insert_success_zero(
                    cur,
                    entity_id=eid,
                    cnpj8=c8,
                    cnpj14=c14,
                    data_type=args.data_type,
                    start=start,
                    end=end,
                    url=url,
                    classified=classified,
                    run_id=run_id,
                )
                conn.commit()
                written += 1
                row["persisted"] = True
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                row["persisted"] = False
                row["persist_error"] = f"{type(e).__name__}: {e}"
                verdicts["BLOCKED_WRITE"] = verdicts.get("BLOCKED_WRITE", 0) + 1
        results.append(row)
        if i % 10 == 0 or i == len(targets):
            print(
                f"progress {i}/{len(targets)} written={written} verdicts={verdicts}",
                flush=True,
            )
        time.sleep(args.delay)

    # Remeasure ops proxy
    cur.execute(
        """
        WITH den AS (SELECT cnpj_8, id FROM sc_public_entities WHERE is_active AND raio_200km),
        lake AS (
          SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'),8) c8
          FROM pncp_supplier_contracts
          WHERE LENGTH(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'))>=8
        ),
        sz AS (
          SELECT DISTINCT entity_id FROM coverage_evidence
          WHERE state='success_zero' AND data_type='contracts'
        )
        SELECT
          (SELECT count(*) FROM den) AS den,
          (SELECT count(*) FROM den d JOIN lake l ON d.cnpj_8=l.c8) AS presence,
          (SELECT count(*) FROM den d JOIN sz s ON d.id=s.entity_id) AS sz_ents,
          (SELECT count(*) FROM den d
            WHERE EXISTS (SELECT 1 FROM lake l WHERE l.c8=d.cnpj_8)
               OR EXISTS (SELECT 1 FROM sz s WHERE s.entity_id=d.id)) AS ops_proxy
        """
    )
    den, presence, sz_ents, ops_proxy = cur.fetchone()
    report = {
        "measured_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "data_type": args.data_type,
        "probed": len(results),
        "success_zero_written": written,
        "verdicts": verdicts,
        "metrics": {
            "denominator": den,
            "presence_contracts": presence,
            "success_zero_entities": sz_ents,
            "ops_proxy_presence_or_sz": ops_proxy,
            "ops_proxy_pct": round(100.0 * ops_proxy / den, 4) if den else 0.0,
        },
        "results": results,
        "claims_forbidden": [
            "operational 7-stage coverage",
            "95% coverage",
            "either union as operational",
        ],
    }
    out = args.output_json
    if out is None:
        out = (
            REPO
            / "docs/ops/campaigns/EXTRA-OPS-95/evidence/M2-success-zero"
            / f"{args.data_type}-sz-{run_id}.json"
        )
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "results"}, ensure_ascii=False, indent=2))
    print(f"wrote {out}", flush=True)
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
