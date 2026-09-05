#!/usr/bin/env python3
"""Resumable ingest of official PNCP contract termos (#548).

Prefers JSONL or CAS-backed archives. Live PNCP is opt-in via ``--from-pncp``.

Usage::

    python3 -m scripts.ops.ingest_pncp_contract_terms --from-jsonl termos.jsonl --limit 200
    python3 -m scripts.ops.ingest_pncp_contract_terms --from-archive --after CONTRATO --limit 50
    python3 -m scripts.ops.ingest_pncp_contract_terms --from-pncp --contrato-id 12345678000199-2-000010/2026
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.crawl.ingestion._base.crawler import FetchResult  # noqa: E402
from scripts.crawl.pncp_contract_terms import (  # noqa: E402
    RULE_VERSION,
    expand_term_payloads,
    parse_pncp_controle_id,
    plan_term_ingest,
)

FetchTerms = Callable[[str, int, int], FetchResult]


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if isinstance(payload, dict):
                yield payload
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        yield item


def _load_archive_payloads(conn: Any, *, limit: int | None) -> list[dict[str, Any]]:
    cur = conn.cursor()
    sql = """
        SELECT body_uri, sanitized_url
        FROM public.raw_http_fetches
        WHERE source ILIKE '%pncp%'
          AND (
              sanitized_url ILIKE '%/termos%'
              OR request_scope ILIKE '%termo%'
          )
        ORDER BY observed_at DESC
    """
    if limit is not None:
        sql += " LIMIT %s"
        cur.execute(sql, (int(limit) * 4,))
    else:
        cur.execute(sql)
    rows = cur.fetchall() or []
    payloads: list[dict[str, Any]] = []
    try:
        from scripts.ops.blob_cas import get as cas_get
    except ImportError:
        return payloads
    for row in rows:
        body_uri = row[0] if not isinstance(row, Mapping) else row.get("body_uri")
        url = row[1] if not isinstance(row, Mapping) else row.get("sanitized_url")
        if not body_uri:
            continue
        try:
            raw = cas_get(str(body_uri))
        except Exception as exc:
            print(f"skip cas body {body_uri}: {exc}", file=sys.stderr)
            continue
        decoded: Any
        if isinstance(raw, (bytes, bytearray)):
            try:
                decoded = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        elif isinstance(raw, str):
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                continue
        else:
            decoded = raw
        if isinstance(decoded, dict):
            envelope = dict(decoded)
            envelope["source_url"] = url
            payloads.append(envelope)
        elif isinstance(decoded, list):
            payloads.append({"termos": decoded, "source_url": url})
        if limit is not None and len(payloads) >= int(limit):
            break
    return payloads


def load_contrato_ids_from_lake(conn: Any, *, after: str | None, limit: int | None) -> list[str]:
    cur = conn.cursor()
    sql = """
        SELECT contrato_id
        FROM public.pncp_supplier_contracts
        WHERE contrato_id IS NOT NULL
          AND contrato_id > %s
        ORDER BY contrato_id
    """
    params: list[Any] = [after or ""]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    ids: list[str] = []
    for row in rows:
        value = row[0] if not isinstance(row, Mapping) else row.get("contrato_id")
        if value:
            ids.append(str(value))
    return ids


def fetch_terms_for_contrato(contrato_id: str, *, fetch_terms: FetchTerms) -> list[dict[str, Any]]:
    parsed = parse_pncp_controle_id(contrato_id)
    if parsed is None:
        print(f"skip unparseable contrato_id {contrato_id}", file=sys.stderr)
        return []
    cnpj, ano, sequencial = parsed
    fetched = fetch_terms(cnpj, ano, sequencial)
    payloads: list[dict[str, Any]] = []
    for record in fetched.records or []:
        if not isinstance(record, dict):
            continue
        payload = dict(record)
        payload.setdefault("contrato_id", contrato_id)
        payload.setdefault("numeroControlePNCP", contrato_id)
        payloads.append(payload)
    return payloads


def apply_batch(conn: Any, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    cur = conn.cursor()
    cur.execute(
        "SELECT action FROM apply_contract_terms(%s::jsonb)",
        (json.dumps(rows, default=str),),
    )
    return len(cur.fetchall() or [])


def run_ingest(
    conn: Any,
    *,
    documents: list[Mapping[str, Any]],
    contrato_ids: list[str],
    after: str | None,
    limit: int | None,
    dry_run: bool,
    fetch_terms: FetchTerms | None = None,
) -> dict[str, Any]:
    payloads: list[Mapping[str, Any]] = list(expand_term_payloads(documents))
    skipped = 0
    fetched_ids: list[str] = []
    if contrato_ids:
        if fetch_terms is None:
            from scripts.crawl.pncp_crawler_adapter import fetch_contract_terms

            fetch_terms = fetch_contract_terms
        for contrato_id in contrato_ids:
            if after and not (contrato_id > after):
                skipped += 1
                continue
            fetched_ids.append(contrato_id)
            payloads.extend(fetch_terms_for_contrato(contrato_id, fetch_terms=fetch_terms))
            if limit is not None and len(fetched_ids) >= int(limit):
                break
    planned = plan_term_ingest(list(payloads))
    if limit is not None and not contrato_ids:
        planned = planned[: int(limit)]
    updated = 0 if dry_run else apply_batch(conn, planned)
    if not dry_run:
        conn.commit()
    cursor = fetched_ids[-1] if fetched_ids else (planned[-1]["contrato_id"] if planned else after)
    return {
        "rule_version": RULE_VERSION,
        "planned": len(planned),
        "updated": updated,
        "contratos": len(fetched_ids),
        "skipped": skipped,
        "cursor": cursor,
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-jsonl", type=Path, default=None)
    parser.add_argument("--from-archive", action="store_true")
    parser.add_argument(
        "--from-pncp",
        action="store_true",
        help="Opt-in live GET /contratos/{ano}/{seq}/termos for lake contrato_id rows.",
    )
    parser.add_argument("--contrato-id", action="append", default=[], help="PNCP contrato id to fetch (repeatable).")
    parser.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL"))
    parser.add_argument("--after", default=None, help="Resume after this contrato_id (exclusive).")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.from_jsonl and not args.from_archive and not args.from_pncp and not args.contrato_id:
        raise SystemExit("provide --from-jsonl PATH, --from-archive, --from-pncp, or --contrato-id ID")
    if not args.dsn:
        raise SystemExit("LOCAL_DATALAKE_DSN or --dsn is required")

    import psycopg2

    conn = psycopg2.connect(args.dsn)
    try:
        documents: list[Mapping[str, Any]] = []
        if args.from_jsonl:
            documents.extend(_iter_jsonl(args.from_jsonl))
        if args.from_archive:
            documents.extend(_load_archive_payloads(conn, limit=args.limit))
        contrato_ids: list[str] = list(args.contrato_id)
        if args.from_pncp and not contrato_ids:
            contrato_ids = load_contrato_ids_from_lake(conn, after=args.after, limit=args.limit)
        result = run_ingest(
            conn,
            documents=documents,
            contrato_ids=contrato_ids,
            after=args.after,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
