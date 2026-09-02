"""One public identity rule for PNCP contract projections."""

from __future__ import annotations

from typing import Any

OFFICIAL_CONTRACT_ID_FIELDS = ("contrato_id", "numero_controle_pncp", "contract_id")


def public_contract_id(
    record: dict[str, Any], *, allow_legacy_surrogate: bool = False
) -> str:
    """Return a non-empty official ID; legacy ``id`` needs explicit opt-in."""
    for field in OFFICIAL_CONTRACT_ID_FIELDS:
        value = str(record.get(field) or "").strip()
        if value:
            return value
    return str(record.get("id") or "").strip() if allow_legacy_surrogate else ""
