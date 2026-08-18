"""Epistemic taxonomy: official fact vs derived vs unknown vs N/A vs delimited absence."""

from __future__ import annotations

import re
from typing import Any

from scripts.official_contract_semantics.constants import (
    COVERAGE_FIELDS,
    EPISTEMIC_ABSENT,
    EPISTEMIC_FACT_OFFICIAL,
    EPISTEMIC_HOLD_FOR_DATA,
    EPISTEMIC_NOT_APPLICABLE,
    EPISTEMIC_NOT_FOUND,
    EPISTEMIC_OBSERVATION_DERIVED,
    EPISTEMIC_UNAVAILABLE,
    EPISTEMIC_UNKNOWN,
    NOT_APPLICABLE_TOKENS,
    SEMANTIC_FIELDS,
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_BR_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_MASK_CHARS = re.compile(r"[*#Xx]")


def is_not_applicable_token(value: Any) -> bool:
    if value is None:
        return False
    folded = str(value).strip().casefold().replace("-", "_")
    return folded in NOT_APPLICABLE_TOKENS


def explicit_not_applicable_fields(raw: dict[str, Any]) -> set[str]:
    marked: set[str] = set()
    declared = raw.get("not_applicable_fields") or raw.get("nao_se_aplica") or ()
    if isinstance(declared, str):
        declared = [declared]
    for name in declared:
        token = str(name).strip()
        if token:
            marked.add(token)
    for name in (*SEMANTIC_FIELDS, *COVERAGE_FIELDS):
        if name in raw and is_not_applicable_token(raw.get(name)):
            marked.add(name)
    return marked


def parse_official_date(value: Any) -> tuple[str | None, str | None]:
    """Return (normalized, reject_reason). Unrecognized formats stay unknown."""
    if value is None or value == "":
        return None, None
    text = str(value).strip()
    if not text:
        return None, None
    if is_not_applicable_token(text):
        return None, None
    if _ISO_DATE.fullmatch(text):
        return text, None
    if _ISO_DATETIME.fullmatch(text):
        return text, None
    br = _BR_DATE.fullmatch(text)
    if br:
        day, month, year = br.groups()
        return f"{year}-{month}-{day}", None
    return None, "ambiguous_or_unrecognized_date"


def identifier_is_masked(value: Any) -> bool:
    if value is None:
        return False
    return bool(_MASK_CHARS.search(str(value)))


def classify_search_outcome(error_kind: str, http_status: int | None) -> str:
    if error_kind == "http_status" and http_status is not None:
        if http_status == 404:
            return EPISTEMIC_NOT_FOUND
        if http_status == 410:
            return EPISTEMIC_ABSENT
        return EPISTEMIC_NOT_FOUND
    return EPISTEMIC_UNAVAILABLE


def field_epistemic_for(
    name: str,
    value: Any,
    *,
    not_applicable: set[str],
    derived: bool = False,
) -> str:
    if name in not_applicable or is_not_applicable_token(value):
        return EPISTEMIC_NOT_APPLICABLE
    if value in {None, "", "unknown"}:
        return EPISTEMIC_UNKNOWN
    if derived:
        return EPISTEMIC_OBSERVATION_DERIVED
    return EPISTEMIC_FACT_OFFICIAL


def classify_fields(
    payload: dict[str, Any],
    *,
    not_applicable: set[str] | None = None,
    derived_fields: set[str] | None = None,
) -> dict[str, str]:
    marked = set(not_applicable or ())
    derived = set(derived_fields or ())
    epistemics: dict[str, str] = {}
    for name in SEMANTIC_FIELDS:
        epistemics[name] = field_epistemic_for(
            name,
            payload.get(name),
            not_applicable=marked,
            derived=name in derived,
        )
    return epistemics


def observation_epistemic_class(field_epistemics: dict[str, str], *, status: str | None = None) -> str:
    values = set(field_epistemics.values())
    if EPISTEMIC_OBSERVATION_DERIVED in values and EPISTEMIC_FACT_OFFICIAL not in values:
        return EPISTEMIC_OBSERVATION_DERIVED
    if EPISTEMIC_FACT_OFFICIAL in values:
        return EPISTEMIC_FACT_OFFICIAL
    if values and values <= {EPISTEMIC_NOT_APPLICABLE, EPISTEMIC_UNKNOWN}:
        if EPISTEMIC_NOT_APPLICABLE in values and EPISTEMIC_UNKNOWN not in values:
            return EPISTEMIC_NOT_APPLICABLE
        return EPISTEMIC_UNKNOWN
    if status == "unknown":
        return EPISTEMIC_UNKNOWN
    return EPISTEMIC_UNKNOWN


def hold_is_required(field_epistemics: dict[str, str], required: tuple[str, ...]) -> bool:
    for name in required:
        state = field_epistemics.get(name, EPISTEMIC_UNKNOWN)
        if state in {EPISTEMIC_UNKNOWN, EPISTEMIC_HOLD_FOR_DATA}:
            return True
    return False
