"""Deterministic opportunity identity resolution (no fuzzy-only dedupe)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class IdentityConflict(Exception):  # noqa: N818 — domain name kept without Error suffix
    """Ambiguous multi-source identity — must block for human review."""

    def __init__(self, reason: str, candidates: list[str], identifiers: dict[str, str]):
        super().__init__(reason)
        self.reason = reason
        self.candidates = candidates
        self.identifiers = identifiers


_WS = re.compile(r"\s+")


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    s = _WS.sub(" ", str(value).strip())
    return s or None


def extract_source_identifiers(row: dict[str, Any]) -> dict[str, str]:
    """Pull known stable identifiers from shortlist / actionable / review rows."""
    keys = (
        "opportunity_id",
        "opportunity_key",
        "numero_controle",
        "numero_controle_pncp",
        "pncp_id",
        "id_pncp",
        "external_id",
        "source_id",
        "edital_id",
        "processo",
        "numero_processo",
    )
    out: dict[str, str] = {}
    for k in keys:
        v = row.get(k)
        if v is None and isinstance(row.get("evidence"), dict):
            v = row["evidence"].get(k)
        n = _norm(str(v) if v is not None else None)
        if n:
            out[k] = n
    source = _norm(str(row.get("source") or row.get("fonte") or "") or None)
    if source:
        out["source"] = source
    return out


def resolve_opportunity_key(
    *,
    client_id: str,
    identifiers: dict[str, str] | None = None,
    explicit_key: str | None = None,
    known_keys_for_identifiers: dict[str, set[str]] | None = None,
) -> str:
    """Resolve a stable opportunity_key.

    Priority:
    1. explicit_key if provided
    2. numero_controle_pncp / numero_controle / opportunity_id (first present, normalized)
    3. hash of sorted identifier pairs when only weak ids exist

    If known_keys_for_identifiers maps different ids to different keys → IdentityConflict.
    """
    if not client_id or not str(client_id).strip():
        raise ValueError("client_id is required for opportunity identity")
    ids = {k: v for k, v in (identifiers or {}).items() if v}
    if explicit_key and str(explicit_key).strip():
        key = str(explicit_key).strip()
        _check_conflicts(key, ids, known_keys_for_identifiers)
        return key

    for prefer in (
        "numero_controle_pncp",
        "numero_controle",
        "opportunity_id",
        "opportunity_key",
        "pncp_id",
        "id_pncp",
        "external_id",
    ):
        if prefer in ids:
            key = ids[prefer]
            _check_conflicts(key, ids, known_keys_for_identifiers)
            return key

    if not ids:
        raise ValueError("cannot resolve opportunity_key without identifiers")

    # Weak composite — deterministic hash, not fuzzy text
    blob = json.dumps(sorted(ids.items()), ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(f"{client_id}|{blob}".encode()).hexdigest()[:24]
    key = f"weak:{digest}"
    _check_conflicts(key, ids, known_keys_for_identifiers)
    return key


def _check_conflicts(
    key: str,
    ids: dict[str, str],
    known: dict[str, set[str]] | None,
) -> None:
    if not known:
        return
    mapped: set[str] = set()
    for _field, val in ids.items():
        if val in known:
            mapped |= known[val]
    mapped.discard(key)
    if mapped:
        raise IdentityConflict(
            "ambiguous opportunity identity across sources",
            candidates=sorted({key, *mapped}),
            identifiers=ids,
        )


def index_identifier_keys(
    rows: list[tuple[str, dict[str, str]]],
) -> dict[str, set[str]]:
    """Build value → keys index for conflict detection.

    rows: list of (opportunity_key, identifiers)
    """
    idx: dict[str, set[str]] = {}
    for key, ids in rows:
        for val in ids.values():
            idx.setdefault(val, set()).add(key)
    return idx
