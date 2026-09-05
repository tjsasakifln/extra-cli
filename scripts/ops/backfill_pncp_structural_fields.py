#!/usr/bin/env python3
"""Resumable backfill of official PNCP structural fields (#546).

Prefers archived payloads (JSONL or raw_http_fetches + CAS). Does not scrape
PNCP unless ``--from-pncp`` is explicitly passed.

Usage::

    python3 -m scripts.ops.backfill_pncp_structural_fields --from-jsonl payloads.jsonl --limit 500
    python3 -m scripts.ops.backfill_pncp_structural_fields --from-archive --limit 500 --after ID
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.crawl.pncp_structural_fields import (  # noqa: E402
    RULE_VERSION,
    plan_structural_backfill,
)


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if isinstance(payload, dict):
                yield payload


def _load_archive_payloads(conn: Any, *, limit: int | None) -> list[dict[str, Any]]:
    """Load archived PNCP contract JSON from CAS-backed raw_http_fetches.

    Metadata lives in PostgreSQL; bodies are off-database. Missing CAS is
    skipped, never invented.
    """
    cur = conn.cursor()
    sql = """
        SELECT body_uri, body_sha256, sanitized_url
        FROM public.raw_http_fetches
        WHERE source ILIKE '%pncp%'
          AND (
              request_scope ILIKE '%contrato%'
              OR sanitized_url ILIKE '%/contratos%'
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
        if not body_uri:
            continue
        try:
            raw = cas_get(str(body_uri))
        except Exception as exc:
            print(f"skip cas body {body_uri}: {exc}", file=sys.stderr)
            continue
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
        items: Iterable[Any]
        if isinstance(decoded, dict) and isinstance(decoded.get("data"), list):
            items = decoded["data"]
        elif isinstance(decoded, list):
            items = decoded
        elif isinstance(decoded, dict):
            items = [decoded]
        else:
            continue
        for item in items:
            if isinstance(item, dict):
                payloads.append(item)
        if limit is not None and len(payloads) >= int(limit):
            break
    return payloads


def apply_batch(conn: Any, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    cur = conn.cursor()
    cur.execute(
        "SELECT contrato_id FROM apply_pncp_structural_fields(%s::jsonb)",
        (json.dumps(rows, default=str),),
    )
    updated = cur.fetchall() or []
    return len(updated)


def record_state(
    conn: Any,
    *,
    run_id: str,
    cursor: str | None,
    processed: int,
    updated: int,
    skipped: int,
) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO public.pncp_structural_fields_backfill_state (
            run_id, cursor_contrato_id, processed, updated, skipped, last_run_at, notes
        ) VALUES (%s, %s, %s, %s, %s, NOW(), %s)
        ON CONFLICT (run_id) DO UPDATE SET
            cursor_contrato_id = EXCLUDED.cursor_contrato_id,
            processed = public.pncp_structural_fields_backfill_state.processed + EXCLUDED.processed,
            updated = public.pncp_structural_fields_backfill_state.updated + EXCLUDED.updated,
            skipped = public.pncp_structural_fields_backfill_state.skipped + EXCLUDED.skipped,
            last_run_at = NOW(),
            notes = EXCLUDED.notes
        """,
        (run_id, cursor, processed, updated, skipped, RULE_VERSION),
    )


def run_backfill(
    conn: Any,
    payloads: list[Mapping[str, Any]],
    *,
    after: str | None,
    limit: int | None,
    run_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    planned = plan_structural_backfill(payloads, after_contrato_id=after, limit=limit)
    skipped = max(0, len(payloads) - len(planned))
    updated = 0 if dry_run else apply_batch(conn, planned)
    cursor = planned[-1]["contrato_id"] if planned else after
    if not dry_run:
        record_state(
            conn,
            run_id=run_id,
            cursor=cursor,
            processed=len(planned),
            updated=updated,
            skipped=skipped,
        )
        conn.commit()
    return {
        "rule_version": RULE_VERSION,
        "planned": len(planned),
        "updated": updated,
        "skipped": skipped,
        "cursor": cursor,
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-jsonl", type=Path, default=None)
    parser.add_argument("--from-archive", action="store_true")
    parser.add_argument("--from-pncp", action="store_true", help="Forbidden default; explicit opt-in only.")
    parser.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL"))
    parser.add_argument("--after", default=None, help="Resume after this contrato_id (exclusive).")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-id", default="structural-fields-default")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.from_pncp:
        raise SystemExit("refusing --from-pncp: backfill must use archived payloads first (#546)")
    if not args.from_jsonl and not args.from_archive:
        raise SystemExit("provide --from-jsonl PATH or --from-archive")
    if not args.dsn:
        raise SystemExit("LOCAL_DATALAKE_DSN or --dsn is required")

    import psycopg2

    conn = psycopg2.connect(args.dsn)
    try:
        payloads: list[dict[str, Any]] = []
        if args.from_jsonl:
            payloads.extend(_iter_jsonl(args.from_jsonl))
        if args.from_archive:
            payloads.extend(_load_archive_payloads(conn, limit=args.limit))
        result = run_backfill(
            conn,
            payloads,
            after=args.after,
            limit=args.limit,
            run_id=args.run_id,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
