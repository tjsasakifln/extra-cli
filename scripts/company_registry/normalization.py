"""CNPJ and cadastral field normalization (pure functions)."""

from __future__ import annotations

import re
from typing import Any

from scripts.linkage.keys import digits_only, is_valid_cnpj14

__all__ = [
    "digits_only",
    "is_valid_cnpj14",
    "normalize_cnpj14",
    "normalize_cnpj_root",
    "compose_cnpj14",
    "normalize_situacao",
    "normalize_cnae",
    "parse_money_br",
]


def normalize_cnpj14(raw: Any) -> str | None:
    """Return 14-digit CNPJ string or None if structural length wrong.

    Does not validate check digits — use is_valid_cnpj14 for that.
    Preserves leading zeros when input has them as digits.
    """
    d = digits_only(raw)
    if len(d) == 14:
        return d
    if len(d) < 14 and len(d) > 0:
        # pad left only when clearly truncated numeric form
        return d.zfill(14) if len(d) <= 14 else None
    if len(d) > 14:
        return d[-14:]
    return None


def normalize_cnpj_root(raw: Any) -> str | None:
    d = digits_only(raw)
    if len(d) >= 8:
        return d[:8]
    if len(d) > 0:
        return d.zfill(8)
    return None


def compose_cnpj14(basico: Any, ordem: Any, dv: Any) -> str | None:
    b = digits_only(basico).zfill(8)[-8:]
    o = digits_only(ordem).zfill(4)[-4:]
    v = digits_only(dv).zfill(2)[-2:]
    if len(b) != 8 or len(o) != 4 or len(v) != 2:
        return None
    return b + o + v


def normalize_situacao(code_or_label: Any) -> str | None:
    if code_or_label is None:
        return None
    s = str(code_or_label).strip().upper()
    if not s:
        return None
    mapping = {
        "1": "NULA",
        "01": "NULA",
        "2": "ATIVA",
        "02": "ATIVA",
        "3": "SUSPENSA",
        "03": "SUSPENSA",
        "4": "INAPTA",
        "04": "INAPTA",
        "8": "BAIXADA",
        "08": "BAIXADA",
        "ATIVA": "ATIVA",
        "SUSPENSA": "SUSPENSA",
        "INAPTA": "INAPTA",
        "BAIXADA": "BAIXADA",
        "NULA": "NULA",
        "INATIVA": "INATIVA",
    }
    return mapping.get(s, s)


def normalize_cnae(raw: Any) -> str | None:
    if raw is None:
        return None
    d = re.sub(r"\D", "", str(raw))
    if not d:
        return None
    # RFB publishes 7-digit CNAE
    return d.zfill(7) if len(d) <= 7 else d[:7]


def parse_money_br(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    s = str(raw).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        try:
            return float(str(raw).strip())
        except ValueError:
            return None
