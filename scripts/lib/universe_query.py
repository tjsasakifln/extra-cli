"""Query helpers for the canonical target universe.

Provides utilities for analytic queries to JOIN with the active universe
snapshot instead of filtering by ``sc_public_entities.raio_200km``.

Usage::

    from scripts.lib.universe_query import active_universe_join, get_active_run_id

    # Get the current run_id
    run_id = get_active_run_id(conn)

    # Use the CTE fragment in a query
    query = f\"\"\"
        SELECT e.*, c.*
        FROM sc_public_entities e
        {active_universe_join('e')}
        JOIN pncp_supplier_contracts c ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
        WHERE tue.universe_run_id = %s
    \"\"\"
    cur.execute(query, (run_id,))
"""

from __future__ import annotations

from typing import Any


def get_active_run_id(conn) -> int | None:
    """Return the latest target_universe_runs.id, or None if no snapshot exists."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM target_universe_runs ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None


def get_active_run_info(conn) -> dict[str, Any] | None:
    """Return full metadata of the latest snapshot, or None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, seed_sha256, radius_km, total_rows, included_rows, "
            "excluded_rows, unresolved_rows, created_at "
            "FROM target_universe_runs ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "seed_sha256": row[1],
            "radius_km": float(row[2]),
            "total_rows": row[3],
            "included_rows": row[4],
            "excluded_rows": row[5],
            "unresolved_rows": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
        }


def active_universe_join(entity_alias: str = "e") -> str:
    """Return a SQL JOIN fragment linking to the active universe snapshot.

    The fragment assumes ``target_universe_entities`` is aliased as ``tue`` and
    that the caller provides a ``universe_run_id`` parameter.

    Example::

        JOIN target_universe_entities tue
          ON tue.cnpj8 = e.cnpj_8
         AND tue.radius_decision = 'included'
    """
    return (
        f"JOIN target_universe_entities tue ON tue.cnpj8 = {entity_alias}.cnpj_8 AND tue.radius_decision = 'included'"
    )


def active_universe_view_join(view_alias: str = "e") -> str:
    """Return a SQL JOIN fragment using the v_target_universe_active view.

    Simpler than the raw table join -- the view already filters for included
    entities from the latest snapshot.

    Example::

        JOIN v_target_universe_active tuv
          ON tuv.cnpj8 = e.cnpj_8
    """
    return f"JOIN v_target_universe_active tuv ON tuv.cnpj8 = {view_alias}.cnpj_8"
