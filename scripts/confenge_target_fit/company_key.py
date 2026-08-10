"""Canonical commercial unit: CNPJ root / company group."""

from __future__ import annotations

import re
from typing import Any


def digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def cnpj_raiz_from_cnpj14(cnpj: str | None) -> str | None:
    d = digits_only(cnpj)
    if len(d) >= 8:
        return d[:8]
    return None


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
    if contract.get("is_consortium") or contract.get("consorcio") or contract.get(
        "consortium"
    ):
        return True
    obj = str(
        contract.get("objeto_contrato")
        or contract.get("objeto")
        or contract.get("object")
        or ""
    ).lower()
    nome = str(
        contract.get("fornecedor_nome") or contract.get("nome_fornecedor") or ""
    ).lower()
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
