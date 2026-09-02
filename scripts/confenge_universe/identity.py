"""Supplier identity resolution for the construction universe."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from scripts.company_registry.normalization import normalize_cnpj14, normalize_cnpj_root
from scripts.confenge_universe import (
    INVALID_IDENTITY,
    NATURAL_PERSON,
    NOT_CONSTRUCTION,
    PUBLIC_ORGAN,
)
from scripts.confenge_universe.parafiscal import (
    PARAFISCAL_INSTITUTIONAL,
    PARAFISCAL_INSTITUTIONAL_MARKERS,
    match_parafiscal_institutional,
)
from scripts.linkage.keys import is_valid_cnpj14, normalize_name

# Backwards-compatible alias: the taxonomy now lives in `parafiscal.py` (single
# source of truth shared with `classify_target_fit` — AC 23a). Re-exported here
# so existing importers of this name keep working WITHOUT a duplicated list.
DEFAULT_PARAFISCAL_INSTITUTIONAL_MARKERS = PARAFISCAL_INSTITUTIONAL_MARKERS

DEFAULT_ORGAN_MARKERS = (
    "prefeitura",
    "municipio",
    "governo",
    "secretaria",
    "ministerio",
    "autarquia",
    "instituto federal",
    "universidade federal",
    "camara municipal",
    "tribunal",
    "estado de",
    "uniao",
    "consorcio publico",
    "consorcio intermunicipal",
)

# Private non-construction financial/public-service suppliers that appear as
# "fornecedor" in PNCP but must never enter the B2G construction outreach universe.
# Matched as whole-token markers on normalized name (not substring of "banconadas").
DEFAULT_NON_CONSTRUCTION_SUPPLIER_MARKERS = (
    "banco do brasil",
    "banco bradesco",
    "banco itau",
    "itau unibanco",
    "caixa economica",
    "caixa economica federal",
    "banco santander",
    "banco safra",
    "banco inter",
    "banco btg",
    "nubank",
    "banco do nordeste",
    "banco da amazonia",
    "banco de brasilia",
    "banrisul",
    "sicoob",
    "sicredi",
    "correios",
    "empresa brasileira de correios",
    "petrobras",
    "eletrobras",
    "furnas",
    "companhia energetica",
)

# Construction/engineering evidence in the legal name. Mirrors the guard already
# used by `_looks_like_non_construction_supplier` for the bare `\bbanco\b` rule.
# NOTE: `normalize_name` upper-cases, so these patterns are case-insensitive.
_CONSTRUCTION_NAME_RE = re.compile(
    r"\b(construt|construcao|construcoes|engenhari|paviment|obras|obra|edifica)\w*",
    re.IGNORECASE,
)

# Bare "FUNDACAO ..." legal person. Public foundations must still be excluded as
# PUBLIC_ORGAN, but private engineering companies whose name merely contains
# "FUNDACAO" (e.g. "FUNDACAO ENGENHARIA E CONSTRUCOES LTDA") must not be.
_FUNDACAO_NAME_RE = re.compile(r"\bfundac(?:ao|oes)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Identity:
    cnpj14: str | None
    cnpj_root: str | None
    razao_social: str
    person_kind: str  # cnpj | cpf | organ | unknown
    valid: bool
    exclusion_code: str | None = None
    exclusion_detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "cnpj14": self.cnpj14,
            "cnpj_root": self.cnpj_root,
            "razao_social": self.razao_social,
            "person_kind": self.person_kind,
            "valid": self.valid,
            "exclusion_code": self.exclusion_code,
            "exclusion_detail": self.exclusion_detail,
        }


def _looks_like_organ(name: str, markers: tuple[str, ...]) -> bool:
    n = normalize_name(name)
    for m in markers:
        if normalize_name(m) in n:
            return True
    return False


def _looks_like_parafiscal_institutional(
    name: str,
    markers: tuple[str, ...] = DEFAULT_PARAFISCAL_INSTITUTIONAL_MARKERS,
) -> str | None:
    """Thin wrapper over the shared taxonomy in `parafiscal.py` (AC 23a).

    Kept as a module-level name because it is the historical entry point of this
    module's defence-in-depth path (aggregate.py / universe builder).
    """
    return match_parafiscal_institutional(name, markers)


def _looks_like_public_foundation(name: str) -> bool:
    """True for "FUNDACAO ..." legal persons with no construction evidence in the name.

    Replaces the bare "fundacao" entry previously in DEFAULT_ORGAN_MARKERS, which
    produced a false negative for private engineering companies such as
    "FUNDACAO ENGENHARIA E CONSTRUCOES LTDA".
    """
    n = normalize_name(name)
    if not _FUNDACAO_NAME_RE.search(n):
        return False
    return not _CONSTRUCTION_NAME_RE.search(n)


def _looks_like_non_construction_supplier(
    name: str,
    markers: tuple[str, ...] = DEFAULT_NON_CONSTRUCTION_SUPPLIER_MARKERS,
) -> bool:
    """True for banks / utilities that are not construction outreach targets."""
    n = f" {normalize_name(name)} "
    for m in markers:
        token = f" {normalize_name(m)} "
        if token in n or n.strip() == normalize_name(m):
            return True
    # Bare "BANCO X" pattern (private bank as supplier), excluding names that
    # clearly describe construction (e.g. none expected with BANCO prefix).
    if re.search(r"\bbanco\b", n) and not re.search(
        r"\b(construt|engenhari|paviment|obras|edifica)\w*", n
    ):
        return True
    return False


def resolve_identity(
    tax_id: str | None,
    name: str | None,
    *,
    organ_markers: tuple[str, ...] | None = None,
) -> Identity:
    raw_name = (name or "").strip() or "SEM NOME"
    markers = organ_markers or DEFAULT_ORGAN_MARKERS

    parafiscal = _looks_like_parafiscal_institutional(raw_name)
    if parafiscal:
        c14 = normalize_cnpj14(tax_id)
        return Identity(
            cnpj14=c14 if c14 and is_valid_cnpj14(c14) else None,
            cnpj_root=normalize_cnpj_root(tax_id),
            razao_social=raw_name,
            person_kind="organ",
            valid=False,
            exclusion_code=PARAFISCAL_INSTITUTIONAL,
            exclusion_detail=f"parafiscal_institutional_name:{parafiscal}",
        )

    if _looks_like_organ(raw_name, markers) or _looks_like_public_foundation(raw_name):
        c14 = normalize_cnpj14(tax_id)
        return Identity(
            cnpj14=c14 if c14 and is_valid_cnpj14(c14) else None,
            cnpj_root=normalize_cnpj_root(tax_id),
            razao_social=raw_name,
            person_kind="organ",
            valid=False,
            exclusion_code=PUBLIC_ORGAN,
            exclusion_detail="public_organ_name",
        )

    if _looks_like_non_construction_supplier(raw_name):
        c14 = normalize_cnpj14(tax_id)
        return Identity(
            cnpj14=c14 if c14 and is_valid_cnpj14(c14) else None,
            cnpj_root=normalize_cnpj_root(tax_id),
            razao_social=raw_name,
            person_kind="cnpj",
            valid=False,
            exclusion_code=NOT_CONSTRUCTION,
            exclusion_detail="non_construction_supplier_name",
        )

    digits = re.sub(r"\D", "", str(tax_id or ""))
    if len(digits) == 11:
        return Identity(
            cnpj14=None,
            cnpj_root=None,
            razao_social=raw_name,
            person_kind="cpf",
            valid=False,
            exclusion_code=NATURAL_PERSON,
            exclusion_detail="natural_person_cpf",
        )

    c14 = normalize_cnpj14(tax_id)
    root = normalize_cnpj_root(tax_id)
    if c14 and is_valid_cnpj14(c14):
        return Identity(
            cnpj14=c14,
            cnpj_root=root or c14[:8],
            razao_social=raw_name,
            person_kind="cnpj",
            valid=True,
        )

    reason = INVALID_IDENTITY
    detail = "invalid_or_missing_cnpj"
    if len(digits) == 14 and not is_valid_cnpj14(digits):
        detail = "invalid_cnpj_check_digits"
    elif not digits:
        detail = "missing_tax_id"
    return Identity(
        cnpj14=c14 if c14 and len(c14) == 14 else None,
        cnpj_root=root,
        razao_social=raw_name,
        person_kind="unknown",
        valid=False,
        exclusion_code=reason,
        exclusion_detail=detail,
    )
