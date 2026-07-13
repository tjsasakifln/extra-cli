"""Central canonical universe definition for all modules.

TODOS os modulos devem importar daqui — nunca definir universo propriamente.

This module defines the single source of truth for:
    - ``CANONICAL_UNIVERSE``: The authoritative count of entities within
      200 km of Florianópolis (constant 1093, from the audited seed spreadsheet).
    - ``get_canonical_universe()``: Runtime DB query confirming the count.
    - ``normalize_cnpj8()``: Standard CNPJ‑root (8‑digit) normalization
      used in all entity‑to‑source joins.
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical universe constant
# ---------------------------------------------------------------------------
# Entities within 200 km of Florianópolis (SC).
# Source: seed spreadsheet column "Raio 200km?" = SIM + Haversine ≤ 200 km.
# Audited in docs/coverage-truth/fase0-audit-2026-07-12.md.
# This is the ONLY place this constant is defined.
CANONICAL_UNIVERSE = 1093


# ---------------------------------------------------------------------------
# Runtime DB query
# ---------------------------------------------------------------------------


def get_canonical_universe(conn: Any) -> int:
    """Query the database for the current canonical universe count.

    Executes::

        SELECT COUNT(*) FROM sc_public_entities WHERE raio_200km = TRUE

    Args:
        conn: An active database connection (psycopg2, psycopg, or any
              DB-API 2.0 connection with a ``cursor()`` method).

    Returns:
        The count of active entities flagged as within 200 km.

    Raises:
        Exception: If the query fails (caller is responsible for handling).
    """
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sc_public_entities WHERE raio_200km = TRUE")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        _logger.exception("Failed to query canonical universe count")
        raise


# ---------------------------------------------------------------------------
# CNPJ‑8 normalisation
# ---------------------------------------------------------------------------


def normalize_cnpj8(cnpj: str) -> str:
    """Normalise a CNPJ string to its 8‑digit root.

    Strips all non‑digit characters and truncates to the first 8 digits.

    Args:
        cnpj: Raw CNPJ string (e.g. ``"12.345.678/0001-90"``).

    Returns:
        The 8‑digit root (e.g. ``"12345678"``).

    Examples:
        >>> normalize_cnpj8("12.345.678/0001-90")
        '12345678'
        >>> normalize_cnpj8("12345678901234")
        '12345678'
        >>> normalize_cnpj8("abc")
        ''
        >>> normalize_cnpj8("")
        ''
    """
    return "".join(c for c in cnpj if c.isdigit())[:8]
