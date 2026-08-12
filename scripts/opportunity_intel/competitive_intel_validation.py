"""Schema validation for competitive intelligence queries.

Validates that the PostgreSQL schema supports the three main competitive
intelligence queries: market share, HHI concentration, and supplier ranking.
All queries are READ-ONLY — no data or schema is modified by this module.

Usage:
    export DATABASE_URL="postgresql://user:pass@host:port/db"
    python scripts/opportunity_intel/competitive_intel_validation.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import psycopg2

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result of a single schema validation check.

    Attributes:
        status: ``"pass"`` if the query executed successfully,
            ``"fail"`` otherwise.
        error_message: Empty string on success.  On failure, contains the
            database error text (including the missing column name when
            the error is an ``UndefinedColumn``).
    """

    status: str = "pass"
    error_message: str = ""


@dataclass
class SchemaValidation:
    """Aggregated results of all competitive intelligence schema validations.

    Each field corresponds to one analytical query and its ``CheckResult``.

    Attributes:
        market_share:     Check for the top-20 suppliers by contract value.
        hhi:              Check for the Herfindahl-Hirschman Index query.
        supplier_ranking: Check for the per-entity supplier ranking query.
    """

    market_share: CheckResult
    hhi: CheckResult
    supplier_ranking: CheckResult


# ---------------------------------------------------------------------------
# SQL Queries — v_contracts_canonical_v2 (migration 077)
# ---------------------------------------------------------------------------
# Buyer and supplier roles are intentionally separate.

_MARKET_SHARE_QUERY = """
    SELECT
        supplier_cnpj,
        SUM(valor) AS total,
        COUNT(*) AS contratos
    FROM v_contracts_canonical_v2
    WHERE valor IS NOT NULL
      AND valor > 0
      AND supplier_id_type = 'CNPJ'
      AND supplier_cnpj IS NOT NULL
      AND is_active IS TRUE
    GROUP BY supplier_cnpj
    ORDER BY total DESC
    LIMIT 20
"""

_HHI_QUERY = """
    WITH supplier_totals AS (
        SELECT
            supplier_cnpj,
            SUM(valor) AS total
        FROM v_contracts_canonical_v2
        WHERE valor IS NOT NULL
          AND valor > 0
          AND supplier_id_type = 'CNPJ'
          AND supplier_cnpj IS NOT NULL
          AND is_active IS TRUE
        GROUP BY supplier_cnpj
    ),
    grand_total AS (
        SELECT SUM(total) AS gt
        FROM supplier_totals
    )
    SELECT
        COALESCE(
            SUM(
                POWER(
                    total * 100.0 / NULLIF((SELECT gt FROM grand_total), 0),
                    2
                )
            ),
            0
        ) AS hhi
    FROM supplier_totals
"""

_SUPPLIER_RANKING_QUERY = """
    SELECT
        buyer_entity_id,
        buyer_entity_nome,
        supplier_cnpj,
        supplier_nome,
        SUM(valor) AS total,
        COUNT(*) AS contratos,
        ROW_NUMBER() OVER (
            PARTITION BY buyer_entity_id
            ORDER BY SUM(valor) DESC
        ) AS ranking
    FROM v_contracts_canonical_v2
    WHERE valor IS NOT NULL
      AND valor > 0
      AND buyer_entity_id IS NOT NULL
      AND supplier_id_type = 'CNPJ'
      AND supplier_cnpj IS NOT NULL
      AND is_active IS TRUE
    GROUP BY buyer_entity_id, buyer_entity_nome, supplier_cnpj, supplier_nome
    ORDER BY buyer_entity_id, ranking
"""

# ---------------------------------------------------------------------------
# SQL Queries — pncp_supplier_contracts (fallback when view missing)
# ---------------------------------------------------------------------------
# Fallback preserves the same roles directly from the fact table.

_MARKET_SHARE_FALLBACK = """
    SELECT
        fornecedor_cnpj AS supplier_cnpj,
        SUM(valor_total) AS total,
        COUNT(*) AS contratos
    FROM pncp_supplier_contracts
    WHERE valor_total IS NOT NULL
      AND valor_total > 0
      AND supplier_id_type = 'CNPJ'
      AND fornecedor_cnpj IS NOT NULL
      AND is_active IS TRUE
      AND (data_inicio IS NOT NULL OR data_publicacao IS NOT NULL)
    GROUP BY fornecedor_cnpj
    ORDER BY total DESC
    LIMIT 20
"""

_HHI_FALLBACK = """
    WITH supplier_totals AS (
        SELECT
            fornecedor_cnpj,
            SUM(valor_total) AS total
        FROM pncp_supplier_contracts
        WHERE valor_total IS NOT NULL
          AND valor_total > 0
          AND supplier_id_type = 'CNPJ'
          AND fornecedor_cnpj IS NOT NULL
          AND is_active IS TRUE
          AND (data_inicio IS NOT NULL OR data_publicacao IS NOT NULL)
        GROUP BY fornecedor_cnpj
    ),
    grand_total AS (
        SELECT SUM(total) AS gt
        FROM supplier_totals
    )
    SELECT
        COALESCE(
            SUM(
                POWER(
                    total * 100.0 / NULLIF((SELECT gt FROM grand_total), 0),
                    2
                )
            ),
            0
        ) AS hhi
    FROM supplier_totals
"""

_SUPPLIER_RANKING_FALLBACK = """
    SELECT
        e.id AS buyer_entity_id,
        e.razao_social AS buyer_entity_nome,
        c.fornecedor_cnpj AS supplier_cnpj,
        c.fornecedor_nome AS supplier_nome,
        SUM(c.valor_total) AS total,
        COUNT(*) AS contratos,
        ROW_NUMBER() OVER (
            PARTITION BY e.id
            ORDER BY SUM(c.valor_total) DESC
        ) AS ranking
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON e.cnpj_8 = left(regexp_replace(COALESCE(c.orgao_cnpj, ''), '\\D', '', 'g'), 8)
    WHERE c.valor_total IS NOT NULL
      AND c.valor_total > 0
      AND c.supplier_id_type = 'CNPJ'
      AND c.fornecedor_cnpj IS NOT NULL
      AND c.is_active IS TRUE
      AND (c.data_inicio IS NOT NULL OR c.data_publicacao IS NOT NULL)
      AND e.id IS NOT NULL
    GROUP BY e.id, e.razao_social, c.fornecedor_cnpj, c.fornecedor_nome
    ORDER BY e.id, ranking
"""


# ---------------------------------------------------------------------------
# Individual check execution
# ---------------------------------------------------------------------------


def _run_check(
    conn: psycopg2.extensions.connection,
    primary_query: str,
    fallback_query: str,
    description: str,
    *,
    use_fetchone: bool = False,
) -> CheckResult:
    """Execute a single SQL query and return a ``CheckResult``.

    Tries ``primary_query`` first.  If the table/view does not exist
    (``UndefinedTable``), falls back to ``fallback_query`` against the
    base table ``pncp_supplier_contracts``.

    Args:
        conn:           psycopg2 connection.
        primary_query:  SQL targeting ``v_contracts_canonical_v2``.
        fallback_query: SQL targeting ``pncp_supplier_contracts``.
        description:    Human-readable label for logging.
        use_fetchone:   If True, calls ``fetchone()`` (for scalar results).
                        Otherwise calls ``fetchall()``.

    Returns:
        ``CheckResult(status="pass")`` on success, or
        ``CheckResult(status="fail", error_message=...)`` on error.
    """
    use_savepoint = getattr(conn, "autocommit", True) is False
    savepoint_active = False
    try:
        with conn.cursor() as cursor:
            if use_savepoint:
                cursor.execute("SAVEPOINT competitive_intel_primary")
                savepoint_active = True
            cursor.execute(primary_query)
            if use_fetchone:
                cursor.fetchone()
            else:
                cursor.fetchall()
            if savepoint_active:
                cursor.execute("RELEASE SAVEPOINT competitive_intel_primary")
                savepoint_active = False
        return CheckResult(status="pass", error_message="")
    except psycopg2.errors.UndefinedColumn as exc:
        _restore_after_failed_primary(conn, savepoint_active)
        # Column-level error — report immediately with column name in message
        msg = str(exc)
        logger.warning("Column error in %s: %s", description, msg)
        return CheckResult(status="fail", error_message=msg)
    except psycopg2.errors.UndefinedTable:
        _restore_after_failed_primary(conn, savepoint_active)
        # View does not exist — try the base table fallback
        logger.info(
            "View not found for %s — trying pncp_supplier_contracts fallback",
            description,
        )
        return _try_fallback(conn, fallback_query, description, use_fetchone=use_fetchone)
    except psycopg2.Error as exc:
        _restore_after_failed_primary(conn, savepoint_active)
        msg = str(exc)
        logger.warning("Database error in %s: %s", description, msg)
        return CheckResult(status="fail", error_message=msg)


def _restore_after_failed_primary(
    conn: psycopg2.extensions.connection, savepoint_active: bool
) -> None:
    """Restore a caller-owned transaction without committing or rolling it back."""
    if not savepoint_active:
        return
    with conn.cursor() as cursor:
        cursor.execute("ROLLBACK TO SAVEPOINT competitive_intel_primary")
        cursor.execute("RELEASE SAVEPOINT competitive_intel_primary")


def _try_fallback(
    conn: psycopg2.extensions.connection,
    query: str,
    description: str,
    *,
    use_fetchone: bool = False,
) -> CheckResult:
    """Execute the fallback query against the base table."""
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            if use_fetchone:
                cursor.fetchone()
            else:
                cursor.fetchall()
        return CheckResult(status="pass", error_message="")
    except psycopg2.Error as exc:
        msg = str(exc)
        logger.warning("Fallback query also failed for %s: %s", description, msg)
        return CheckResult(status="fail", error_message=msg)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_competitive_intel_schema(conn: psycopg2.extensions.connection) -> SchemaValidation:
    """Execute the three competitive-intel queries and validate schema support.

    The function is **READ-ONLY**: it never modifies schema or data.

    1.  Tries each query against ``v_contracts_canonical_v2`` (preferred).
    2.  If the view does not exist, falls back to ``pncp_supplier_contracts``
        with adapted column names.
    3.  Returns a ``SchemaValidation`` with per-query status.

    Each query executes independently — a failure in one does not
    short-circuit the others.

    Args:
        conn: An open ``psycopg2`` connection (autocommit recommended).

    Returns:
        A ``SchemaValidation`` dataclass with three ``CheckResult`` fields.

    Raises:
        psycopg2.OperationalError: If the connection is closed, refused, or
            the database is unreachable. Propagates from ``conn.cursor()``.

    Example:
        >>> from psycopg2 import connect
        >>> conn = connect("postgresql://user:pass@localhost:5432/db")
        >>> result = validate_competitive_intel_schema(conn)
        >>> result.market_share.status
        'pass'
        >>> result.hhi.status
        'pass'
        >>> result.supplier_ranking.status
        'pass'

    Edge cases:
        View missing: If ``v_contracts_canonical_v2`` does not exist, each query
            transparently falls back to ``pncp_supplier_contracts`` with
            adapted column aliases. The ``CheckResult`` still reports
            ``status="pass"`` as long as the fallback succeeds.
        Column renamed: If a column referenced in the primary query has been
            dropped or renamed, ``UndefinedColumn`` is caught and returned as
            ``CheckResult(status="fail")`` with the database error message.
        Both view and base table missing: If neither target exists, returns
            ``CheckResult(status="fail")`` with the base-table error message.
        Empty results: A query that succeeds but returns zero rows is not
            considered a failure — it simply returns an empty resultset, and
            the check is marked ``status="pass"``.
        Partial failure: A ``fail`` in one query (e.g., market_share) does
            **not** prevent the other two queries from executing. The caller
            receives a complete ``SchemaValidation`` with mixed statuses.
    """
    return SchemaValidation(
        market_share=_run_check(
            conn,
            _MARKET_SHARE_QUERY,
            _MARKET_SHARE_FALLBACK,
            "market_share",
            use_fetchone=False,
        ),
        hhi=_run_check(
            conn,
            _HHI_QUERY,
            _HHI_FALLBACK,
            "hhi",
            use_fetchone=True,
        ),
        supplier_ranking=_run_check(
            conn,
            _SUPPLIER_RANKING_QUERY,
            _SUPPLIER_RANKING_FALLBACK,
            "supplier_ranking",
            use_fetchone=False,
        ),
    )


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run competitive intel schema validation from ``DATABASE_URL``.

    Requires the ``DATABASE_URL`` environment variable set to a valid
    PostgreSQL DSN (e.g., ``postgresql://user:pass@localhost:5432/db``).

    Exits with code 0 if all checks pass, 1 if any check fails.
    """
    import os
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
    )

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        logger.error("DATABASE_URL environment variable is required")
        sys.exit(1)

    logger.info("Connecting to %s", dsn.partition("@")[2] if "@" in dsn else dsn)

    try:
        conn = psycopg2.connect(dsn)
    except psycopg2.Error as exc:
        logger.error("Failed to connect: %s", exc)
        sys.exit(1)

    try:
        result = validate_competitive_intel_schema(conn)
        checks = [
            ("market_share", result.market_share),
            ("hhi", result.hhi),
            ("supplier_ranking", result.supplier_ranking),
        ]
        all_pass = True
        for name, check in checks:
            if check.status == "pass":
                logger.info("%s: PASS", name)
            else:
                logger.error("%s: FAIL — %s", name, check.error_message)
                all_pass = False
        sys.exit(0 if all_pass else 1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
