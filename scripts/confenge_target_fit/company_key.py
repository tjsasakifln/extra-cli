"""Canonical commercial unit: CNPJ root / company group."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

TARGET_MEMBERSHIP_SCHEMA_VERSION = "confenge.target_membership.v1"
TARGET_MEMBERSHIP_IDENTITY_KEY = "cnpj_root8"
TARGET_MEMBERSHIP_HASH_ALGORITHM = "sha256(sorted_unique_cnpj_root8_newline_utf8)"

# Curated corrections are applied at the commercial-feed boundary as identity
# aliases.  Keep the raw source evidence unchanged; every emitted decision uses
# the corrected canonical CNPJ.
_CNPJ14_CORRECTIONS = {
    "01489370000105": "14893700000105",  # PREVENCAO LABORATORIO
}


def digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def canonical_cnpj14(value: Any) -> str:
    digits = digits_only(value)
    if len(digits) != 14:
        return ""
    return _CNPJ14_CORRECTIONS.get(digits, digits)


def cnpj_raiz_from_cnpj14(cnpj: str | None) -> str | None:
    d = canonical_cnpj14(cnpj) or digits_only(cnpj)
    if len(d) >= 8:
        return d[:8]
    return None


def canonical_target_membership(cnpjs: list[Any]) -> dict[str, Any]:
    """Return the reproducible one-company-per-root TARGET membership contract.

    The digest intentionally matches the operational proof used in #468:
    canonical eight-digit roots, byte-sorted, one UTF-8 root per newline.  A
    repeated root is refused rather than silently publishing two Warmbly
    accounts for the same commercial company.
    """

    roots: list[str] = []
    invalid: list[str] = []
    for value in cnpjs:
        cnpj14 = canonical_cnpj14(value)
        if not cnpj14:
            invalid.append(str(value or ""))
            continue
        roots.append(cnpj14[:8])
    if invalid:
        raise ValueError(
            f"target membership contains non-canonical CNPJ14 values: count={len(invalid)} sample={invalid[:10]}"
        )

    ordered = sorted(roots)
    unique = sorted(set(ordered))
    duplicate_count = len(ordered) - len(unique)
    if duplicate_count:
        duplicate_roots = sorted(root for root, count in Counter(ordered).items() if count > 1)
        raise ValueError(
            "target membership contains duplicate CNPJ roots; reconcile before publication: "
            f"duplicate_rows={duplicate_count} sample={duplicate_roots[:10]}"
        )

    encoded = "".join(f"{root}\n" for root in unique).encode("utf-8")
    return {
        "schema_version": TARGET_MEMBERSHIP_SCHEMA_VERSION,
        "identity_key": TARGET_MEMBERSHIP_IDENTITY_KEY,
        "hash_algorithm": TARGET_MEMBERSHIP_HASH_ALGORITHM,
        "population_count": len(unique),
        "membership_hash": hashlib.sha256(encoded).hexdigest(),
        "duplicate_member_count": 0,
    }


def company_key_from_raiz(cnpj_raiz: str) -> str:
    """Stable company_key. Root is the commercial grouping unit."""
    r = digits_only(cnpj_raiz)[:8]
    if len(r) != 8:
        raise ValueError(f"invalid cnpj_raiz for company_key: {cnpj_raiz!r}")
    return f"cnpj_root:{r}"


def parse_company_key(company_key: str) -> str:
    """Return 8-digit raiz from company_key."""
    if company_key.startswith("cnpj_root:"):
        return digits_only(company_key.split(":", 1)[1])[:8]
    return digits_only(company_key)[:8]


def resolve_company_from_contract(contract: dict[str, Any]) -> tuple[str, str] | None:
    """Map contract → (company_key, cnpj_raiz). Never uses orgão CNPJ."""
    raw = (
        contract.get("fornecedor_cnpj")
        or contract.get("ni_fornecedor")
        or contract.get("cnpj")
        or contract.get("cnpj14")
    )
    raiz = cnpj_raiz_from_cnpj14(raw)
    if not raiz or len(raiz) != 8:
        return None
    # Reject obvious invalid roots
    if raiz == "00000000" or len(set(raiz)) == 1:
        return None
    return company_key_from_raiz(raiz), raiz


def is_consortium_contract(contract: dict[str, Any]) -> bool:
    if contract.get("is_consortium") or contract.get("consorcio") or contract.get("consortium"):
        return True
    obj = str(contract.get("objeto_contrato") or contract.get("objeto") or contract.get("object") or "").lower()
    nome = str(contract.get("fornecedor_nome") or contract.get("nome_fornecedor") or "").lower()
    markers = ("consórcio", "consorcio", " em consorcio", " em consórcio")
    return any(m in obj or m in nome for m in markers)


def canary_bucket(company_key: str) -> int:
    """Stable 0..99 bucket for canary rollout."""
    # FNV-1a 32-bit
    h = 2166136261
    for ch in company_key.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return h % 100
