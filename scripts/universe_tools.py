#!/usr/bin/env python3
"""Universe snapshot, divergence ledger, and seed-change blocking tools.

Usage::

    # Generate a new snapshot from the current seed
    python scripts/universe_tools.py snapshot generate

    # Show divergence between seed and sc_public_entities
    python scripts/universe_tools.py divergence

    # Check whether the current seed matches the latest snapshot
    python scripts/universe_tools.py check-seed

    # List existing snapshots
    python scripts/universe_tools.py snapshot list

Exit codes:
    0 — success
    42 — seed has changed with no matching snapshot (blocking)
    1 — unexpected error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED_PATH = PROJECT_ROOT / "fixtures" / "canonical_universe_r0.xlsx"

# ---------------------------------------------------------------------------
# DB helpers (lightweight — uses psycopg2 like the rest of the project)
# ---------------------------------------------------------------------------


def _get_dsn() -> str:
    return os.getenv(
        "LOCAL_DATALAKE_DSN",
        "postgresql://postgres@127.0.0.1:5433/pncp_datalake",
    )


def _get_conn():
    import psycopg2

    dsn = _get_dsn()
    try:
        return psycopg2.connect(dsn, connect_timeout=5)
    except psycopg2.Error as e:
        raise ConnectionError(f"Cannot connect to database: {e}") from e


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def sha256_file(path: str | Path) -> str:
    """SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_git_sha() -> str | None:
    """Return the current git commit SHA, or None if unavailable."""
    try:
        result = subprocess.run(  # noqa: S603 — shell=False default
            ["git", "rev-parse", "HEAD"],  # noqa: S607 — git resolved from PATH (dev/CI env)
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


# ---------------------------------------------------------------------------
# Snapshot operations
# ---------------------------------------------------------------------------


def load_canonical_universe_for_snapshot(seed_path: str | Path = DEFAULT_SEED_PATH) -> Any:
    """Load the canonical universe for snapshot creation (import late)."""
    from scripts.lib.universe import load_canonical_universe

    return load_canonical_universe(seed_path=seed_path)


def get_latest_snapshot(conn) -> dict[str, Any] | None:
    """Return the latest target_universe_runs row, or None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, seed_sha256, seed_filename, radius_km, "
            "total_rows, included_rows, excluded_rows, unresolved_rows, "
            "created_at, git_sha "
            "FROM target_universe_runs "
            "ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "seed_sha256": row[1],
            "seed_filename": row[2],
            "radius_km": float(row[3]),
            "total_rows": row[4],
            "included_rows": row[5],
            "excluded_rows": row[6],
            "unresolved_rows": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "git_sha": row[9],
        }


def generate_snapshot(
    seed_path: str | Path = DEFAULT_SEED_PATH,
    block_on_change: bool = False,
) -> dict[str, Any]:
    """Generate a snapshot from the current seed and store it in the DB.

    Returns the snapshot metadata dict including the new ``run_id``.
    """
    # Load universe
    universe = load_canonical_universe_for_snapshot(seed_path)
    current_sha = sha256_file(seed_path)

    conn = _get_conn()
    try:
        # Check if this exact seed already has a snapshot
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM target_universe_runs WHERE seed_sha256 = %s LIMIT 1",
                (current_sha,),
            )
            existing = cur.fetchone()
            if existing is not None:
                return {
                    "status": "skipped",
                    "reason": "Snapshot already exists for this seed hash",
                    "run_id": existing[0],
                    "seed_sha256": current_sha,
                    "total_rows": len(universe.entities),
                    "included_rows": len(universe.included),
                    "excluded_rows": len(universe.excluded),
                    "unresolved_rows": len(universe.unresolved),
                }

            # Block if enabled and seed changed
            if block_on_change:
                cur.execute("SELECT id, seed_sha256 FROM target_universe_runs ORDER BY id DESC LIMIT 1")
                latest = cur.fetchone()
                if latest is not None and latest[1] != current_sha:
                    msg = (
                        f"ERROR: Seed hash changed from {latest[1]} to {current_sha}. "
                        "Run 'python scripts/universe_tools.py snapshot generate' before proceeding."
                    )
                    print(msg, file=sys.stderr)
                    sys.exit(42)

            # Get git SHA
            git_sha = get_git_sha()

            # Insert run
            cur.execute(
                "INSERT INTO target_universe_runs "
                "(seed_sha256, seed_filename, radius_km, total_rows, "
                " included_rows, excluded_rows, unresolved_rows, git_sha) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (
                    current_sha,
                    str(Path(seed_path).name),
                    universe.radius_km,
                    len(universe.entities),
                    len(universe.included),
                    len(universe.excluded),
                    len(universe.unresolved),
                    git_sha,
                ),
            )
            run_id = cur.fetchone()[0]

            # Insert entities in batches
            batch_size = 500
            entities_batch: list[tuple] = []
            for entity in universe.entities:
                entities_batch.append(
                    (
                        run_id,
                        entity.entity_id,
                        entity.seed_row,
                        entity.cnpj8,
                        entity.razao_social,
                        entity.municipio,
                        entity.codigo_ibge,
                        entity.natureza_juridica,
                        entity.latitude,
                        entity.longitude,
                        entity.distancia_km,
                        entity.radius_decision,
                        entity.duplicate_root,
                        entity.db_entity_id,
                        entity.db_match_method,
                    )
                )
                if len(entities_batch) >= batch_size:
                    _insert_entity_batch(cur, entities_batch)
                    entities_batch = []

            if entities_batch:
                _insert_entity_batch(cur, entities_batch)

            conn.commit()

            return {
                "status": "created",
                "run_id": run_id,
                "seed_sha256": current_sha,
                "total_rows": len(universe.entities),
                "included_rows": len(universe.included),
                "excluded_rows": len(universe.excluded),
                "unresolved_rows": len(universe.unresolved),
                "git_sha": git_sha,
            }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _insert_entity_batch(cur, batch: list[tuple]) -> None:
    """Insert a batch of entity rows into target_universe_entities."""
    import psycopg2.extras

    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO target_universe_entities "
        "(universe_run_id, canonical_entity_key, seed_row, cnpj8, legal_name, "
        " municipality, ibge_code, legal_nature, latitude, longitude, "
        " distance_km, radius_decision, duplicate_root, "
        " db_entity_id, match_method) "
        "VALUES %s",
        batch,
        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    )


def list_snapshots(conn=None, limit: int = 10) -> list[dict[str, Any]]:
    """List recent snapshots."""
    close_conn = False
    if conn is None:
        conn = _get_conn()
        close_conn = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, seed_sha256, seed_filename, radius_km, "
                "total_rows, included_rows, excluded_rows, unresolved_rows, "
                "created_at, git_sha "
                "FROM target_universe_runs "
                "ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "seed_sha256": r[1][:16] + "...",
                    "seed_filename": r[2],
                    "radius_km": float(r[3]),
                    "total_rows": r[4],
                    "included_rows": r[5],
                    "excluded_rows": r[6],
                    "unresolved_rows": r[7],
                    "created_at": r[8].isoformat() if r[8] else None,
                    "git_sha": r[9][:8] if r[9] else None,
                }
                for r in rows
            ]
    finally:
        if close_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Divergence ledger
# ---------------------------------------------------------------------------


def compute_divergence(seed_path: str | Path = DEFAULT_SEED_PATH) -> dict[str, Any]:
    """Compare seed entities with sc_public_entities to find divergences.

    Returns a dict with:
    - matched: entities found in both seed and DB
    - in_seed_only: entities in seed but not in DB
    - in_db_only: entities active in DB but not in seed
    - warnings: data quality notes
    """
    universe = load_canonical_universe_for_snapshot(seed_path)
    conn = _get_conn()
    try:
        # Load all active DB entities
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, cnpj_8, razao_social, municipio, raio_200km FROM sc_public_entities WHERE is_active IS TRUE"
            )
            db_entities = {
                str(r[1]): {
                    "id": r[0],
                    "cnpj_8": r[1],
                    "razao_social": r[2],
                    "municipio": r[3],
                    "raio_200km": r[4],
                }
                for r in cur.fetchall()
                if r[1]
            }

        # Compare
        seed_by_cnpj8: dict[str, list] = {}
        for entity in universe.included:
            seed_by_cnpj8.setdefault(entity.cnpj8, []).append(entity)

        matched: list[dict] = []
        in_seed_only: list[dict] = []
        for cnpj8, entities in seed_by_cnpj8.items():
            if cnpj8 in db_entities:
                db = db_entities[cnpj8]
                for e in entities:
                    matched.append(
                        {
                            "cnpj8": cnpj8,
                            "seed_name": e.razao_social,
                            "db_name": db["razao_social"],
                            "seed_municipio": e.municipio,
                            "db_municipio": db["municipio"],
                            "db_id": db["id"],
                            "db_raio_200km": db["raio_200km"],
                        }
                    )
            else:
                for e in entities:
                    in_seed_only.append(
                        {
                            "cnpj8": cnpj8,
                            "name": e.razao_social,
                            "municipio": e.municipio,
                        }
                    )

        in_db_only = [
            {
                "cnpj8": cnpj8,
                "name": db["razao_social"],
                "municipio": db["municipio"],
                "db_id": db["id"],
                "db_raio_200km": db["raio_200km"],
            }
            for cnpj8, db in db_entities.items()
            if cnpj8 not in seed_by_cnpj8
        ]

        # Warnings
        warnings: list[str] = []
        for m in matched:
            if m["seed_name"].upper() != m["db_name"].upper():
                warnings.append(
                    f"Name mismatch for CNPJ-8 {m['cnpj8']}: seed='{m['seed_name']}' vs DB='{m['db_name']}'"
                )

        return {
            "seed_path": str(seed_path),
            "seed_sha256": sha256_file(seed_path),
            "matched_count": len(matched),
            "in_seed_only_count": len(in_seed_only),
            "in_db_only_count": len(in_db_only),
            "warnings_count": len(warnings),
            "warnings": warnings,
            "matched": matched,
            "in_seed_only": in_seed_only,
            "in_db_only": in_db_only,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Seed change check (Task 9 — blocking)
# ---------------------------------------------------------------------------


def check_seed(seed_path: str | Path = DEFAULT_SEED_PATH) -> None:
    """Check if current seed matches the latest snapshot. Exit 42 if changed."""
    current_sha = sha256_file(seed_path)

    conn = _get_conn()
    try:
        latest = get_latest_snapshot(conn)
    finally:
        conn.close()

    if latest is None:
        print("WARNING: No snapshots exist. Run 'python scripts/universe_tools.py snapshot generate' first.")
        return

    if latest["seed_sha256"] == current_sha:
        print(f"OK — Seed matches snapshot #{latest['id']} ({latest['seed_sha256'][:16]}...)")
    else:
        msg = (
            f"ERROR: Seed hash changed from {latest['seed_sha256']} to {current_sha}. "
            "Run 'python scripts/universe_tools.py snapshot generate' before proceeding."
        )
        print(msg, file=sys.stderr)
        sys.exit(42)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Universe snapshot and divergence tools")
    sub = parser.add_subparsers(dest="command", required=True)

    # snapshot
    snap = sub.add_parser("snapshot", help="Snapshot operations")
    snap_sub = snap.add_subparsers(dest="action", required=True)

    snap_generate = snap_sub.add_parser("generate", help="Generate a new snapshot")
    snap_generate.add_argument("--seed", type=str, default=str(DEFAULT_SEED_PATH))
    snap_generate.add_argument(
        "--block-on-change", action="store_true", help="Exit 42 if seed changed without snapshot"
    )

    snap_list = snap_sub.add_parser("list", help="List existing snapshots")
    snap_list.add_argument("--limit", type=int, default=10)

    # divergence
    div = sub.add_parser("divergence", help="Compute seed vs DB divergence")
    div.add_argument("--seed", type=str, default=str(DEFAULT_SEED_PATH))
    div.add_argument("--output", type=str, help="Output file (JSON)")

    # check-seed
    check = sub.add_parser("check-seed", help="Check seed hash vs latest snapshot")
    check.add_argument("--seed", type=str, default=str(DEFAULT_SEED_PATH))

    args = parser.parse_args()

    if args.command == "snapshot":
        if args.action == "generate":
            result = generate_snapshot(seed_path=args.seed, block_on_change=args.block_on_change)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 42 if result.get("status") == "blocked" else 0
        elif args.action == "list":
            snapshots = list_snapshots(limit=args.limit)
            if not snapshots:
                print("No snapshots found.")
                return 0
            print(
                f"{'ID':>4}  {'Seed SHA256':<20}  {'File':<40}  {'Total':>6}  {'Incl':>5}  {'Excl':>5}  {'Unres':>5}  {'Created':<30}  {'Git'}"
            )
            print("-" * 140)
            for s in snapshots:
                print(
                    f"{s['id']:>4}  {s['seed_sha256']:<20}  {s['seed_filename']:<40}  "
                    f"{s['total_rows']:>6}  {s['included_rows']:>5}  {s['excluded_rows']:>5}  "
                    f"{s['unresolved_rows']:>5}  {s['created_at']:<30}  {s['git_sha'] or '-'}"
                )
            return 0

    elif args.command == "divergence":
        result = compute_divergence(seed_path=args.seed)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Divergence ledger written to {args.output}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    elif args.command == "check-seed":
        check_seed(seed_path=args.seed)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
