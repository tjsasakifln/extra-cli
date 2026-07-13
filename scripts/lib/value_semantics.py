"""Value Semantics — typed distinction between value types across B2G sources.

PNCP, ComprasGov and TCE/SC each expose values at different stages of the
procurement lifecycle. Using ``valor_global`` as "preco praticado" is incorrect
because PNCP's global contract value is NOT the price actually paid — it is
the maximum contractual ceiling.

Lifecycle stages
----------------
    ESTIMADO    → Edital / bid — what the government expects to pay
    HOMOLOGADO  → Award result — what was actually awarded to winner
    CONTRATADO  → Contract signature — what was signed (may include options)
    PAGO        → Payment/empenho — what was actually disbursed
    GLOBAL      → PNCP umbrella — undifferentiated total

Usage
-----
    >>> from scripts.lib.value_semantics import SOURCE_VALUE_TYPES, ValorSemantica
    >>> SOURCE_VALUE_TYPES["pncp"]["contracts"]
    <ValorSemantica.CONTRATADO: 'valor_contratado'>

    >>> calculate_desagio(1_000_000, 850_000)
    {'valor_estimado': 1000000.0, 'valor_homologado': 850000.0,
     'desconto_absoluto': 150000.0, 'desagio_percentual': 15.0,
     'semantica': 'estimado→contratado'}
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ValorSemantica(Enum):
    """Typed semantics for each value stage in the B2G lifecycle."""

    ESTIMADO = "valor_estimado"
    """From edital — what the government expects to pay (PNCP bids)."""

    HOMOLOGADO = "valor_homologado"
    """From award result — what was actually awarded (ComprasGov)."""

    CONTRATADO = "valor_contratado"
    """From contract — what was signed (PNCP contracts, signed value)."""

    PAGO = "valor_pago"
    """From payment records — what was actually disbursed (TCE/SC empenhos)."""

    GLOBAL = "valor_global"
    """Undifferentiated total — PNCP default; NOT "preco praticado"."""


# ── Source-to-semantic mapping ──────────────────────────────────────────────
# Each (source, entity_type) pair documents what value type it exposes and
# the actual database column name.

SOURCE_VALUE_TYPES: dict[str, dict[str, ValorSemantica]] = {
    "pncp": {
        "bids": ValorSemantica.ESTIMADO,
        # pncp_raw_bids.valor_total_estimado
        "contracts": ValorSemantica.CONTRATADO,
        # pncp_supplier_contracts.valor_global — this IS the signed contract
        # value, which is semantically "contratado" even though PNCP labels
        # it "global". It is NOT "preco praticado" because it does not
        # reflect actual disbursements, renegotiations, or partial terminations.
    },
    "compras_gov": {
        "bids": ValorSemantica.HOMOLOGADO,
        # ComprasGov provides pregos com valores homologados por item/lote.
        # Not yet ingested in this data lake. Documented for future use.
    },
    "tce_sc": {
        "contracts": ValorSemantica.PAGO,
        # TCE/SC fornece empenhos (pagamentos efetivos). Not yet ingested.
        # Documented for future ingestion contracts.
    },
}

# Human-readable descriptions for each semantic (for CLI output and reports)
VALOR_SEMANTICA_LABELS: dict[ValorSemantica, str] = {
    ValorSemantica.ESTIMADO: "Valor estimado (edital)",
    ValorSemantica.HOMOLOGADO: "Valor homologado (resultado da licitacao)",
    ValorSemantica.CONTRATADO: "Valor contratado (contrato assinado)",
    ValorSemantica.PAGO: "Valor pago (empenhos efetivos)",
    ValorSemantica.GLOBAL: "Valor global PNCP (nao diferenciado)",
}


# ── Desagio calculation ─────────────────────────────────────────────────────


def calculate_desagio(
    valor_estimado: float,
    valor_homologado: float,
    semantica: str = "estimado→contratado",
) -> dict[str, Any] | None:
    """Calculate desagio (discount) from estimated to homologated/contracted value.

    Parameters
    ----------
    valor_estimado:
        The estimated value from the edital/bid.
    valor_homologado:
        The actual awarded/contracted value.
    semantica:
        Semantic label describing the value transition, e.g.
        "estimado→homologado", "estimado→contratado".

    Returns
    -------
    dict or None:
        Desagio breakdown, or **None** if inputs are invalid.

    Examples
    --------
    >>> d = calculate_desagio(1_000_000.0, 850_000.0)
    >>> d["desagio_percentual"]
    15.0
    """
    if valor_estimado is None or valor_homologado is None:
        return None
    if valor_estimado <= 0 or valor_homologado <= 0:
        return None

    desconto = valor_estimado - valor_homologado
    percentual = (desconto / valor_estimado) * 100.0

    return {
        "valor_estimado": round(valor_estimado, 2),
        "valor_homologado": round(valor_homologado, 2),
        "desconto_absoluto": round(desconto, 2),
        "desagio_percentual": round(percentual, 2),
        "semantica": semantica,
    }


def compute_bid_contract_desagio(
    valor_estimado: float,
    valor_global_contrato: float,
) -> dict[str, Any] | None:
    """Calculate desagio from a bid's estimated value to its eventual contract value.

    This is the most common pattern in PNCP-only data: compare
    ``valor_total_estimado`` from ``pncp_raw_bids`` with ``valor_global``
    from the resulting ``pncp_supplier_contract``.

    Parameters
    ----------
    valor_estimado:
        ``valor_total_estimado`` from PNCP bid.
    valor_global_contrato:
        ``valor_global`` from PNCP contract.

    Returns
    -------
    dict or None:
        Same structure as :func:`calculate_desagio` with fixed semantics.
    """
    return calculate_desagio(
        valor_estimado=valor_estimado,
        valor_homologado=valor_global_contrato,
        semantica="estimado→contratado",
    )


# ── Aggregation helpers ─────────────────────────────────────────────────────


def aggregate_contract_values(
    contracts: list[dict[str, Any]],
    value_field: str = "valor_global",
) -> dict[str, Any]:
    """Compute aggregate statistics over contract values.

    Parameters
    ----------
    contracts:
        List of contract dicts, each containing *value_field*.
    value_field:
        Column name for the value (default ``valor_global``).

    Returns
    -------
    dict with keys: ``total``, ``avg``, ``median``, ``min``, ``max``, ``count``.
    """
    values = [float(c[value_field]) for c in contracts if c.get(value_field) is not None and float(c[value_field]) > 0]

    if not values:
        return {
            "total": 0.0,
            "avg": 0.0,
            "median": 0.0,
            "min": 0.0,
            "max": 0.0,
            "count": 0,
            "semantica": "N/A",
        }

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    return {
        "total": round(sum(sorted_vals), 2),
        "avg": round(sum(sorted_vals) / n, 2),
        "median": round(sorted_vals[n // 2], 2)
        if n % 2 == 1
        else round((sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2, 2),
        "min": round(sorted_vals[0], 2),
        "max": round(sorted_vals[-1], 2),
        "count": n,
        "semantica": "valor_contratado (valor_global PNCP)",
    }


# ── Semantic label helpers ──────────────────────────────────────────────────


def coluna_para_semantica(column_name: str) -> ValorSemantica | None:
    """Map a database column name to its semantic value type.

    Parameters
    ----------
    column_name:
        Actual column name in the DB (e.g. ``valor_total_estimado``).

    Returns
    -------
    ValorSemantica or None if unknown.
    """
    mapping = {
        "valor_total_estimado": ValorSemantica.ESTIMADO,
        "valor_estimado": ValorSemantica.ESTIMADO,
        "valor_homologado": ValorSemantica.HOMOLOGADO,
        "valor_global": ValorSemantica.CONTRATADO,
        "valor_pago": ValorSemantica.PAGO,
    }
    return mapping.get(column_name)


def rotulo_valor(column_name: str) -> str:
    """Human-readable label for a value column.

    Examples
    --------
    >>> rotulo_valor("valor_total_estimado")
    'Valor estimado (edital)'
    >>> rotulo_valor("valor_global")
    'Valor contratado (contrato assinado) — coluna valor_global PNCP'
    """
    sem = coluna_para_semantica(column_name)
    if sem:
        base = VALOR_SEMANTICA_LABELS.get(sem, column_name)
        if sem == ValorSemantica.CONTRATADO:
            return f"{base} — coluna {column_name} PNCP"
        return base
    return f"Valor ({column_name}) — semantica nao classificada"
