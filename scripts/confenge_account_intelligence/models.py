"""Lightweight types and pure helpers for account-intelligence dossiers."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_ID = "confenge-account-intelligence-v1"
SCHEMA_VERSION = "1.0.0"

DOMINANT_STATES = frozenset(
    {
        "DO_NOT_CONTACT",
        "HUMAN_REJECTED",
        "HUMAN_PAUSED",
        "STOP",
        "OPTED_OUT",
    }
)

_CNPJ_DIGITS = re.compile(r"\D+")


def digits_only(value: Any) -> str:
    if value is None:
        return ""
    return _CNPJ_DIGITS.sub("", str(value))


def cnpj_root(cnpj: Any) -> str:
    """Return 8-digit CNPJ root (padded if needed, empty if unknown)."""
    d = digits_only(cnpj)
    if len(d) >= 8:
        return d[:8]
    if not d:
        return "00000000"
    return d.zfill(8)


def cnpj14(cnpj: Any) -> str | None:
    d = digits_only(cnpj)
    if len(d) == 14:
        return d
    if len(d) == 8:
        return d + "0001" + "00"  # incomplete — still useful for root matching
    if len(d) > 14:
        return d[:14]
    if len(d) >= 8:
        return d.zfill(14)
    return d or None


def stable_source_hash(payload: dict[str, Any]) -> str:
    """Hash of source facts used for cache key (order-stable JSON)."""
    # Exclude volatile runtime fields if present.
    material = {
        k: payload.get(k)
        for k in (
            "cnpj",
            "cnpj14",
            "razao_social",
            "nome_fantasia",
            "municipio",
            "uf",
            "cnae_principal",
            "activity_class",
            "commercial_state",
            "human_outcome",
            "contracts",
            "signals",
            "facts",
            "evidence",
            "as_of",
        )
        if k in payload
    }
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def cache_key(*, cnpj_root_value: str, source_hash: str, as_of: str) -> str:
    return f"{cnpj_root_value}:{source_hash}:{as_of}"


def epistemic_item(
    *,
    item_id: str,
    text: str,
    epistemic_class: str,
    confidence: float,
    evidence_ids: list[str] | None = None,
    provenance: str,
    as_of: str | None = None,
) -> dict[str, Any]:
    if epistemic_class not in {"confirmed", "strong_inference", "weak_inference"}:
        raise ValueError(f"invalid epistemic_class: {epistemic_class}")
    conf = max(0.0, min(1.0, float(confidence)))
    return {
        "id": item_id,
        "text": text,
        "epistemic_class": epistemic_class,
        "confidence": conf,
        "evidence_ids": list(evidence_ids or []),
        "provenance": provenance,
        "as_of": as_of,
    }
