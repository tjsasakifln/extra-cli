"""Deterministic observation identity, hashes and CNPJ handling."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from scripts.official_contract_semantics.constants import (
    EXTRACTOR_VERSION,
    IDENTITY_FIELDS,
    MAX_EVIDENCE_EXCERPT,
    SCHEMA_VERSION,
    SEMANTIC_FIELDS,
)
from scripts.official_contract_semantics.serialize import content_hash, sha256_text

_CNPJ_DIGITS = re.compile(r"\D+")
_SECRET_MARKERS = (
    "-----begin",
    "api_key",
    "apikey",
    "secret_key",
    "aws_secret",
    "private_key",
    "password=",
    "token=",
)


def parse_optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "" or value == "unknown":
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("R$", "").replace(" ", "")
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def clip_excerpt(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return None
    if len(cleaned) <= MAX_EVIDENCE_EXCERPT:
        return cleaned
    return cleaned[: MAX_EVIDENCE_EXCERPT - 1] + "…"


def digits_only(value: str | None) -> str | None:
    if value is None:
        return None
    digits = _CNPJ_DIGITS.sub("", str(value))
    return digits or None


def normalize_cnpj(value: str | None) -> str | None:
    """Keep a complete official digit string. Masked or incomplete IDs stay unknown."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if any(marker in raw for marker in ("*", "#", "X", "x")):
        return None
    digits = digits_only(raw)
    if digits is None:
        return None
    if len(digits) not in {8, 11, 14}:
        return None
    return digits


def refuse_root_establishment_merge(left: str | None, right: str | None) -> bool:
    a = digits_only(left)
    b = digits_only(right)
    if not a or not b or a == b:
        return False
    if len(a) == 8 and len(b) == 14 and b.startswith(a):
        return True
    if len(b) == 8 and len(a) == 14 and a.startswith(b):
        return True
    return False


def detect_secret(text: str | None) -> bool:
    if not text:
        return False
    folded = text.casefold()
    return any(marker in folded for marker in _SECRET_MARKERS)


def raw_record_hash_for(payload: Any) -> str:
    if isinstance(payload, (bytes, bytearray)):
        from scripts.official_contract_semantics.serialize import sha256_bytes

        return sha256_bytes(bytes(payload))
    if isinstance(payload, str):
        return sha256_text(payload)
    return content_hash(payload)


def observation_id_for(payload: dict[str, Any]) -> str:
    material = {key: payload.get(key) for key in (*IDENTITY_FIELDS, *SEMANTIC_FIELDS)}
    material["schema_version"] = payload.get("schema_version") or SCHEMA_VERSION
    material["extractor_version"] = payload.get("extractor_version") or EXTRACTOR_VERSION
    material["supersedes_document_id"] = payload.get("supersedes_document_id")
    return content_hash(material)


def official_identity_present(payload: dict[str, Any]) -> bool:
    url = payload.get("official_url")
    document_id = payload.get("source_document_id")
    document_sha = payload.get("source_document_sha256")
    contract_id = payload.get("contract_identifier")
    raw_hash = payload.get("raw_record_hash")
    source_system = payload.get("source_system")
    if url:
        return True
    if document_id and document_sha:
        return True
    if source_system and contract_id and raw_hash:
        return True
    return False
