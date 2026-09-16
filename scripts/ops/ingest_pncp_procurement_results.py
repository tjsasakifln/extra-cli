#!/usr/bin/env python3
"""Resumable ingest of official PNCP item resultados (#545).

Prefers JSONL or CAS-backed archives. Live PNCP is opt-in via ``--from-pncp``.

Usage::

    python3 -m scripts.ops.ingest_pncp_procurement_results --from-jsonl resultados.jsonl --limit 200
    python3 -m scripts.ops.ingest_pncp_procurement_results --from-archive --after PARENT --limit 50
    python3 -m scripts.ops.ingest_pncp_procurement_results --from-pncp --parent 12345678000199-1-000010/2026
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.crawl.ingestion._base.crawler import FetchResult  # noqa: E402
from scripts.crawl.pncp_procurement_results import (  # noqa: E402
    RULE_VERSION,
    expand_result_payloads,
    parse_pncp_controle_id,
    plan_result_ingest,
)

FetchItems = Callable[[str, int, int], FetchResult]
FetchResultados = Callable[[str, int, int, int], FetchResult]


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
              sanitized_url ILIKE '%/resultados%'
              OR request_scope ILIKE '%resultado%'
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
        envelope: dict[str, Any] = {"source_url": url}
        if isinstance(decoded, dict):
            envelope.update(decoded)
            payloads.append(envelope)
        elif isinstance(decoded, list):
            payloads.append({"resultados": decoded, "source_url": url})
        if limit is not None and len(payloads) >= int(limit):
            break
    return payloads


def load_parents_from_lake(conn: Any, *, after: str | None, limit: int | None) -> list[str]:
    cur = conn.cursor()
    sql = """
        SELECT DISTINCT parent_procurement_id
        FROM public.pncp_supplier_contracts
        WHERE parent_procurement_id IS NOT NULL
          AND btrim(parent_procurement_id) <> ''
          AND parent_procurement_id > %s
        ORDER BY parent_procurement_id
    """
    params: list[Any] = [after or ""]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    parents: list[str] = []
    for row in rows:
        value = row[0] if not isinstance(row, Mapping) else row.get("parent_procurement_id")
        if value:
            parents.append(str(value))
    return parents


def fetch_results_for_parent(
    parent_id: str,
    *,
    fetch_items: FetchItems,
    fetch_resultados: FetchResultados,
) -> list[dict[str, Any]]:
    parsed = parse_pncp_controle_id(parent_id)
    if parsed is None:
        print(f"skip unparseable parent_procurement_id {parent_id}", file=sys.stderr)
        return []
    cnpj, ano, sequencial = parsed
    items_result = fetch_items(cnpj, ano, sequencial)
    items = _as_item_list(items_result.records)
    payloads: list[dict[str, Any]] = []
    for item in items:
        numero = item.get("numeroItem") or item.get("item") or item.get("item_numero")
        if numero in (None, ""):
            continue
        try:
            item_numero = int(numero)
        except (TypeError, ValueError):
            continue
        fetched = fetch_resultados(cnpj, ano, sequencial, item_numero)
        for record in fetched.records or []:
            if not isinstance(record, dict):
                continue
            payload = dict(record)
            payload.setdefault("numeroControlePNCPCompra", parent_id)
            payload.setdefault("parent_procurement_id", parent_id)
            payload.setdefault("numeroItem", item_numero)
            payloads.append(payload)
    return payloads


def _as_item_list(records: Iterable[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for record in records or []:
        if isinstance(record, list):
            out.extend(_as_item_list(record))
        elif isinstance(record, dict):
            nested = record.get("data") or record.get("itens")
            if isinstance(nested, list) and "numeroItem" not in record:
                out.extend(_as_item_list(nested))
            else:
                out.append(record)
    return out


def apply_batch(conn: Any, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    cur = conn.cursor()
    cur.execute(
        "SELECT action FROM apply_pncp_procurement_results(%s::jsonb)",
        (json.dumps(rows, default=str),),
    )
    applied = len(cur.fetchall() or [])
    cur.execute("SELECT public.link_procurement_results_to_contracts()")
    return applied


def run_ingest(
    conn: Any,
    *,
    documents: list[Mapping[str, Any]],
    parents: list[str],
    after: str | None,
    limit: int | None,
    dry_run: bool,
    fetch_items: FetchItems | None = None,
    fetch_resultados: FetchResultados | None = None,
) -> dict[str, Any]:
    payloads: list[Mapping[str, Any]] = list(expand_result_payloads(documents))
    skipped_parents = 0
    fetched_parents: list[str] = []
    if parents:
        if fetch_items is None or fetch_resultados is None:
            from scripts.crawl.pncp_crawler_adapter import fetch_compra_items, fetch_item_resultados

            fetch_items = fetch_items or fetch_compra_items
            fetch_resultados = fetch_resultados or fetch_item_resultados
        for parent_id in parents:
            if after and not (parent_id > after):
                skipped_parents += 1
                continue
            fetched_parents.append(parent_id)
            payloads.extend(
                fetch_results_for_parent(
                    parent_id,
                    fetch_items=fetch_items,
                    fetch_resultados=fetch_resultados,
                )
            )
            if limit is not None and len(fetched_parents) >= int(limit):
                break
    planned = plan_result_ingest(list(payloads))
    if limit is not None and not parents:
        planned = planned[: int(limit)]
    updated = 0 if dry_run else apply_batch(conn, planned)
    if not dry_run:
        conn.commit()
    cursor = fetched_parents[-1] if fetched_parents else (planned[-1]["parent_procurement_id"] if planned else after)
    return {
        "rule_version": RULE_VERSION,
        "planned": len(planned),
        "updated": updated,
        "parents": len(fetched_parents),
        "skipped_parents": skipped_parents,
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
        help="Opt-in live GET /itens/{n}/resultados for lake parent_procurement_id rows.",
    )
    parser.add_argument("--parent", action="append", default=[], help="PNCP compra id to fetch (repeatable).")
    parser.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL"))
    parser.add_argument("--after", default=None, help="Resume after this parent_procurement_id (exclusive).")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.from_jsonl and not args.from_archive and not args.from_pncp and not args.parent:
        raise SystemExit("provide --from-jsonl PATH, --from-archive, --from-pncp, or --parent ID")
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
        parents: list[str] = list(args.parent)
        if args.from_pncp and not parents:
            parents = load_parents_from_lake(conn, after=args.after, limit=args.limit)
        result = run_ingest(
            conn,
            documents=documents,
            parents=parents,
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
