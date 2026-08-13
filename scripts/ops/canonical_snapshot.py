#!/usr/bin/env python3
"""Operate the client-independent canonical snapshot barrier (#287)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _connect(dsn: str | None = None):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    resolved = dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not resolved:
        raise RuntimeError("LOCAL_DATALAKE_DSN or DATABASE_URL is required")
    return psycopg2.connect(resolved, cursor_factory=RealDictCursor, connect_timeout=10)


def _show(connection: Any, snapshot_id: str) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM canonical_public_snapshots WHERE snapshot_id = %s", (snapshot_id,))
        snapshot = cursor.fetchone()
        if not snapshot:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        cursor.execute(
            "SELECT * FROM canonical_snapshot_source_watermarks WHERE snapshot_id = %s ORDER BY source",
            (snapshot_id,),
        )
        watermarks = [dict(row) for row in cursor.fetchall() or []]
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM canonical_snapshot_event_revisions WHERE snapshot_id = %s) AS event_revisions,
                (SELECT count(*) FROM canonical_snapshot_documents WHERE snapshot_id = %s) AS documents,
                (SELECT count(*) FROM canonical_snapshot_dossiers WHERE snapshot_id = %s) AS dossiers
            """,
            (snapshot_id, snapshot_id, snapshot_id),
        )
        counts = dict(cursor.fetchone())
    return {
        "snapshot": dict(snapshot),
        "cutoff": snapshot["cutoff_at"],
        "cutoff_timezone": snapshot["cutoff_timezone"],
        "blockers": snapshot["blockers"],
        "watermarks": watermarks,
        "counts": counts,
        "generation_allowed": snapshot["state"] == "READY_CANONICAL",
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical public snapshot barrier")
    parser.add_argument("--dsn")
    sub = parser.add_subparsers(dest="command", required=True)

    begin = sub.add_parser("begin")
    begin.add_argument("--cutoff", required=True, help="ISO timestamp with offset; operational timezone is America/Sao_Paulo")
    for name in ("universe", "policy", "schema", "adapter", "data", "document", "dossier"):
        begin.add_argument(f"--{name}-hash", required=True)
    begin.add_argument("--required-pairs", type=int, required=True)
    begin.add_argument("--relevant-dossiers", type=int, required=True)
    begin.add_argument("--actor", required=True)

    watermark = sub.add_parser("watermark")
    watermark.add_argument("snapshot_id")
    watermark.add_argument("--source", required=True)
    watermark.add_argument("--run-id", required=True)
    watermark.add_argument("--at", required=True)
    watermark.add_argument("--freshness", choices=["FRESH", "STALE", "FAILED", "BLOCKED", "UNKNOWN"], required=True)
    watermark.add_argument("--completeness", choices=["COMPLETE", "INCOMPLETE", "UNKNOWN"], required=True)
    watermark.add_argument("--applicable-pairs", type=int, required=True)
    watermark.add_argument("--evaluated-pairs", type=int, required=True)
    watermark.add_argument("--evidence-hash", required=True)

    revision = sub.add_parser("add-revision")
    revision.add_argument("snapshot_id")
    revision.add_argument("event_id")
    revision.add_argument("revision_id")

    document = sub.add_parser("add-document")
    document.add_argument("snapshot_id")
    document.add_argument("observation_id")
    document.add_argument("--sha256", required=True)
    document.add_argument("--completeness", choices=["COMPLETE", "INCOMPLETE", "BLOCKED"], required=True)

    dossier = sub.add_parser("add-dossier")
    dossier.add_argument("snapshot_id")
    dossier.add_argument("dossier_id")
    dossier.add_argument("--revision-hash", required=True)
    dossier.add_argument("--completeness", choices=["COMPLETE", "INCOMPLETE", "BLOCKED"], required=True)
    dossier.add_argument("--reason-code", action="append", default=[])

    close = sub.add_parser("close")
    close.add_argument("snapshot_id")
    show = sub.add_parser("show")
    show.add_argument("snapshot_id")

    projection = sub.add_parser("create-projection")
    projection.add_argument("snapshot_id")
    projection.add_argument("--consumer", required=True)
    projection.add_argument("--template-hash", required=True)
    projection.add_argument("--private-profile-hash")

    private = sub.add_parser("invalidate-private")
    private.add_argument("projection_id")
    private.add_argument("--template-hash", required=True)
    private.add_argument("--private-profile-hash")

    file_hash = sub.add_parser("hash-file")
    file_hash.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    if args.command == "hash-file":
        print(json.dumps({"path": str(args.path), "sha256": _hash_file(args.path)}, indent=2))
        return 0

    connection = _connect(args.dsn)
    code = 0
    try:
        with connection.cursor() as cursor:
            if args.command == "begin":
                values = [
                    args.cutoff,
                    args.universe_hash,
                    args.policy_hash,
                    args.schema_hash,
                    args.adapter_hash,
                    args.data_hash,
                    args.document_hash,
                    args.dossier_hash,
                    args.required_pairs,
                    args.relevant_dossiers,
                    args.actor,
                ]
                if any("client" in str(value).lower() or "profile_hash" in str(value).lower() for value in values):
                    raise ValueError("client/profile state is forbidden in canonical snapshot input")
                cursor.execute(
                    "SELECT begin_canonical_public_snapshot_v1(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS id",
                    tuple(values),
                )
                snapshot_id = cursor.fetchone()["id"]
                output = _show(connection, snapshot_id)
            elif args.command == "watermark":
                cursor.execute(
                    "SELECT put_canonical_snapshot_watermark_v1(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        args.snapshot_id,
                        args.source,
                        args.run_id,
                        args.at,
                        args.freshness,
                        args.completeness,
                        args.applicable_pairs,
                        args.evaluated_pairs,
                        args.evidence_hash,
                    ),
                )
                output = _show(connection, args.snapshot_id)
            elif args.command == "add-revision":
                cursor.execute(
                    """
                    INSERT INTO canonical_snapshot_event_revisions (snapshot_id, event_id, revision_id, fact_hash)
                    SELECT %s, revision.event_id, revision.revision_id, revision.fact_hash
                    FROM canonical_event_revisions revision
                    WHERE revision.event_id = %s AND revision.revision_id = %s
                    RETURNING revision_id
                    """,
                    (args.snapshot_id, args.event_id, args.revision_id),
                )
                if not cursor.fetchone():
                    raise ValueError("event/revision pair not found")
                output = _show(connection, args.snapshot_id)
            elif args.command == "add-document":
                cursor.execute(
                    "INSERT INTO canonical_snapshot_documents VALUES (%s, %s, %s, %s) RETURNING observation_id",
                    (args.snapshot_id, args.observation_id, args.sha256, args.completeness),
                )
                output = _show(connection, args.snapshot_id)
            elif args.command == "add-dossier":
                cursor.execute(
                    "INSERT INTO canonical_snapshot_dossiers VALUES (%s, %s, %s, %s, %s) RETURNING dossier_id",
                    (args.snapshot_id, args.dossier_id, args.revision_hash, args.completeness, args.reason_code),
                )
                output = _show(connection, args.snapshot_id)
            elif args.command == "close":
                cursor.execute("SELECT close_canonical_public_snapshot_v1(%s) AS result", (args.snapshot_id,))
                output = {"transition": cursor.fetchone()["result"], "manifest": _show(connection, args.snapshot_id)}
                code = 0 if output["transition"]["state"] == "READY_CANONICAL" else 2
            elif args.command == "show":
                output = _show(connection, args.snapshot_id)
                code = 0 if output["generation_allowed"] else 2
            elif args.command == "create-projection":
                projection_id = hashlib.sha256(
                    f"{args.consumer}|{args.snapshot_id}|{args.template_hash}|{args.private_profile_hash or ''}".encode()
                ).hexdigest()[:32]
                cursor.execute(
                    """
                    INSERT INTO public_consumer_projections (
                        projection_id, consumer_id, snapshot_id, template_hash, private_profile_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (projection_id) DO NOTHING RETURNING projection_id
                    """,
                    (projection_id, args.consumer, args.snapshot_id, args.template_hash, args.private_profile_hash),
                )
                output = {"projection_id": projection_id, "snapshot_id": args.snapshot_id}
            else:
                cursor.execute(
                    "SELECT invalidate_consumer_projection_private_v1(%s, %s, %s)",
                    (args.projection_id, args.template_hash, args.private_profile_hash),
                )
                output = {"projection_id": args.projection_id, "state": "STALE_PRIVATE"}
        connection.commit()
    finally:
        connection.close()
    print(json.dumps(output, ensure_ascii=False, indent=2, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)))
    return code


if __name__ == "__main__":
    sys.exit(main())
