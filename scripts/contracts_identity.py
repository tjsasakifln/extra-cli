"""Typed supplier identity for PNCP contracts.

The legacy ``fornecedor_cnpj`` column remains a CNPJ-only compatibility key.
CPF and foreign identifiers are never written into it or normalized as CNPJ.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Literal

from scripts.linkage.keys import digits_only, is_valid_cnpj14, is_valid_cpf11

SupplierIdType = Literal["CNPJ", "CPF", "FOREIGN", "UNKNOWN"]

_CNPJ_TYPES = frozenset({"PJ", "PESSOA JURIDICA", "JURIDICA", "LEGAL ENTITY"})
_CPF_TYPES = frozenset({"PF", "PESSOA FISICA", "FISICA", "NATURAL PERSON"})
_FOREIGN_TYPES = frozenset(
    {"PE", "ESTRANGEIRO", "PESSOA ESTRANGEIRA", "FOREIGN", "FOREIGN PERSON"}
)
_BRAZIL_CODES = frozenset({"BR", "BRA", "BRASIL", "BRAZIL", "76", "076"})


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.upper()).strip()


def normalize_country(value: Any) -> str | None:
    """Normalize a PNCP country code without inventing Brazil when absent."""
    text = _fold(value)
    if not text:
        return None
    if text in _BRAZIL_CODES:
        return "BR"
    return text[:32]


def cpf_export_mask() -> str:
    """Approved public/export representation: no CPF digit is emitted."""
    return "CPF:***.***.***-**"


@dataclass(frozen=True)
class SupplierIdentity:
    supplier_id_type: SupplierIdType
    supplier_identifier: str | None
    supplier_country: str | None
    supplier_identifier_hash: str | None
    supplier_identifier_export: str | None
    supplier_identity_reason: str
    fornecedor_cnpj: str | None

    def to_record_fields(self) -> dict[str, Any]:
        return asdict(self)


def _identifier_hash(id_type: SupplierIdType, identifier: str | None) -> str | None:
    if not identifier:
        return None
    material = f"supplier-identity-v1:{id_type}:{identifier}".encode()
    return hashlib.sha256(material).hexdigest()


def normalize_supplier_identity(
    raw_identifier: Any,
    *,
    declared_type: Any = None,
    country: Any = None,
) -> SupplierIdentity:
    """Classify and validate a PNCP supplier identifier without type coercion."""
    raw = str(raw_identifier or "").strip()
    digits = digits_only(raw)
    type_token = _fold(declared_type)
    country_code = normalize_country(country)
    explicit_foreign = type_token in _FOREIGN_TYPES or (
        country_code is not None and country_code != "BR"
    )

    id_type: SupplierIdType
    identifier: str | None
    reason: str
    fornecedor_cnpj: str | None = None

    if explicit_foreign:
        id_type = "FOREIGN" if raw else "UNKNOWN"
        identifier = f"FOREIGN:{country_code or 'ZZ'}:{raw}" if raw else None
        reason = "declared_foreign" if raw else "foreign_identifier_missing"
    elif type_token in _CNPJ_TYPES:
        if is_valid_cnpj14(digits):
            id_type = "CNPJ"
            identifier = digits
            fornecedor_cnpj = digits
            reason = "declared_cnpj_valid"
        else:
            id_type = "UNKNOWN"
            identifier = f"UNKNOWN:BR:{digits or raw}" if (digits or raw) else None
            reason = "declared_cnpj_invalid"
    elif type_token in _CPF_TYPES:
        if is_valid_cpf11(digits):
            id_type = "CPF"
            identifier = digits
            reason = "declared_cpf_valid"
        else:
            id_type = "UNKNOWN"
            identifier = f"UNKNOWN:BR:{digits or raw}" if (digits or raw) else None
            reason = "declared_cpf_invalid"
    elif is_valid_cnpj14(digits):
        id_type = "CNPJ"
        identifier = digits
        fornecedor_cnpj = digits
        reason = "inferred_cnpj_valid"
    elif is_valid_cpf11(digits):
        id_type = "CPF"
        identifier = digits
        reason = "inferred_cpf_valid"
    else:
        id_type = "UNKNOWN"
        identifier = f"UNKNOWN:{country_code or 'ZZ'}:{digits or raw}" if (digits or raw) else None
        reason = "identifier_invalid" if identifier else "identifier_missing"

    if id_type in {"CNPJ", "CPF"} and country_code is None:
        country_code = "BR"
    export_identifier = identifier
    if id_type == "CPF":
        export_identifier = cpf_export_mask()
    elif id_type == "UNKNOWN" and len(digits) == 11:
        export_identifier = "UNKNOWN:MASKED"

    return SupplierIdentity(
        supplier_id_type=id_type,
        supplier_identifier=identifier,
        supplier_country=country_code,
        supplier_identifier_hash=_identifier_hash(id_type, identifier),
        supplier_identifier_export=export_identifier,
        supplier_identity_reason=reason,
        fornecedor_cnpj=fornecedor_cnpj,
    )


def normalize_cnpj_supplier(value: Any) -> str | None:
    """Return only a valid 14-digit CNPJ; never pad CPF/short identifiers."""
    digits = digits_only(str(value or ""))
    return digits if is_valid_cnpj14(digits) else None


__all__ = [
    "SupplierIdentity",
    "SupplierIdType",
    "cpf_export_mask",
    "normalize_cnpj_supplier",
    "normalize_country",
    "normalize_supplier_identity",
]
