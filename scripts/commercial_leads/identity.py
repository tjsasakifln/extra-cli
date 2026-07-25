"""Supplier identity resolution and exclusion rules for commercial queue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.linkage.keys import (
    digits_only,
    extract_person_keys,
    is_valid_cnpj14,
    normalize_name,
)


@dataclass
class ResolvedSupplier:
    cnpj14: str | None
    cnpj8: str | None
    razao_social: str
    person_kind: str  # cnpj | cpf | unknown | organ
    eligible: bool
    exclusion_reason: str | None = None
    raw_tax_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "cnpj14": self.cnpj14,
            "cnpj8": self.cnpj8,
            "razao_social": self.razao_social,
            "person_kind": self.person_kind,
            "eligible": self.eligible,
            "exclusion_reason": self.exclusion_reason,
            "raw_tax_id": self.raw_tax_id,
        }


@dataclass
class ExclusionRecord:
    raw_tax_id: str | None
    raw_name: str | None
    reason_code: str
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_tax_id": self.raw_tax_id,
            "raw_name": self.raw_name,
            "reason_code": self.reason_code,
            "detail": self.detail,
        }


def _looks_like_public_organ(name: str, markers: list[str]) -> bool:
    n = normalize_name(name)
    for m in markers:
        if normalize_name(m) in n:
            return True
    return False


def resolve_supplier(
    tax_id: str | None,
    name: str | None,
    *,
    organ_markers: list[str] | None = None,
    drop_organs: bool = True,
    drop_persons: bool = True,
    drop_invalid: bool = True,
) -> ResolvedSupplier:
    raw_name = (name or "").strip() or "SEM NOME"
    keys = extract_person_keys(tax_id, name)
    markers = organ_markers or []

    if drop_organs and _looks_like_public_organ(raw_name, markers):
        return ResolvedSupplier(
            cnpj14=keys.cnpj14,
            cnpj8=keys.cnpj8,
            razao_social=raw_name,
            person_kind="organ",
            eligible=False,
            exclusion_reason="public_organ_name",
            raw_tax_id=digits_only(tax_id) or None,
        )

    d = digits_only(tax_id)
    if len(d) == 11 or keys.cpf11:
        if drop_persons:
            return ResolvedSupplier(
                cnpj14=None,
                cnpj8=None,
                razao_social=raw_name,
                person_kind="cpf",
                eligible=False,
                exclusion_reason="natural_person",
                raw_tax_id=d or None,
            )

    if keys.cnpj14 and is_valid_cnpj14(keys.cnpj14):
        return ResolvedSupplier(
            cnpj14=keys.cnpj14,
            cnpj8=keys.cnpj8,
            razao_social=raw_name,
            person_kind="cnpj",
            eligible=True,
            raw_tax_id=keys.cnpj14,
        )

    if drop_invalid:
        reason = "invalid_or_missing_cnpj"
        if len(d) == 14 and not is_valid_cnpj14(d):
            reason = "invalid_cnpj_check_digits"
        elif not d:
            reason = "missing_tax_id"
        return ResolvedSupplier(
            cnpj14=None,
            cnpj8=keys.cnpj8,
            razao_social=raw_name,
            person_kind="unknown",
            eligible=False,
            exclusion_reason=reason,
            raw_tax_id=d or None,
        )

    return ResolvedSupplier(
        cnpj14=None,
        cnpj8=keys.cnpj8,
        razao_social=raw_name,
        person_kind="unknown",
        eligible=True,
        raw_tax_id=d or None,
    )


def is_public_organ_cnpj_root(cnpj14: str | None) -> bool:
    """Heuristic: federal public admin roots are not used as hard filter alone."""
    if not cnpj14 or len(cnpj14) < 8:
        return False
    # Conservative: do not auto-flag; name markers handle organs.
    return False
