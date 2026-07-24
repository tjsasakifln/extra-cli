"""Pure key normalization and validation for entity linkage.

No database I/O. Inputs → digits, keys, validation flags.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


def digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_name(value: str | None) -> str:
    """ASCII-fold, uppercase, strip punctuation — pure function."""
    s = unicodedata.normalize("NFKD", value or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9 ]+", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def is_valid_cnpj14(cnpj: str | None) -> bool:
    d = digits_only(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False
    # Basic check-digit validation
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def _dv(nums: str, weights: list[int]) -> int:
        total = sum(int(n) * w for n, w in zip(nums, weights, strict=True))
        rem = total % 11
        return 0 if rem < 2 else 11 - rem

    return _dv(d[:12], weights1) == int(d[12]) and _dv(d[:13], weights2) == int(d[13])


def is_valid_cpf11(cpf: str | None) -> bool:
    d = digits_only(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False

    def _dv(nums: str, max_w: int) -> int:
        total = sum(int(n) * w for n, w in zip(nums, range(max_w, 1, -1), strict=False))
        rem = (total * 10) % 11
        return 0 if rem == 10 else rem

    return _dv(d[:9], 10) == int(d[9]) and _dv(d[:10], 11) == int(d[10])


def is_valid_ibge7(code: str | None) -> bool:
    d = digits_only(code)
    return len(d) == 7 and d[0] in "12345"


@dataclass(frozen=True)
class StrongKeys:
    """Official identifiers extracted from a raw record."""

    cnpj14: str | None = None
    cnpj8: str | None = None
    cpf11: str | None = None
    ibge7: str | None = None
    pncp_control: str | None = None
    raw_name: str = ""
    normalized_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "cnpj14": self.cnpj14,
            "cnpj8": self.cnpj8,
            "cpf11": self.cpf11,
            "ibge7": self.ibge7,
            "pncp_control": self.pncp_control,
            "raw_name": self.raw_name,
            "normalized_name": self.normalized_name,
        }


def extract_person_keys(
    tax_id: str | None,
    name: str | None = None,
) -> StrongKeys:
    """Extract supplier/person strong keys from tax id + name."""
    d = digits_only(tax_id)
    raw = (name or "").strip()
    norm = normalize_name(raw)
    if len(d) == 14 and is_valid_cnpj14(d):
        return StrongKeys(cnpj14=d, cnpj8=d[:8], raw_name=raw, normalized_name=norm)
    if len(d) == 14:
        # Present but invalid check digits — keep as weak cnpj8 only if root looks ok
        return StrongKeys(
            cnpj14=None,
            cnpj8=d[:8] if len(d) >= 8 else None,
            raw_name=raw,
            normalized_name=norm,
        )
    if len(d) == 11 and is_valid_cpf11(d):
        return StrongKeys(cpf11=d, raw_name=raw, normalized_name=norm)
    if len(d) >= 8:
        return StrongKeys(cnpj8=d[:8], raw_name=raw, normalized_name=norm)
    return StrongKeys(raw_name=raw, normalized_name=norm)


def extract_organ_keys(
    cnpj: str | None,
    name: str | None = None,
    ibge: str | None = None,
    pncp_control: str | None = None,
) -> StrongKeys:
    d = digits_only(cnpj)
    raw = (name or "").strip()
    norm = normalize_name(raw)
    ibge7 = digits_only(ibge) if is_valid_ibge7(ibge) else None
    cnpj14 = d if len(d) == 14 and is_valid_cnpj14(d) else (d if len(d) == 14 else None)
    # Keep invalid-checkdigit 14 as cnpj8 root for soft join
    cnpj8 = d[:8] if len(d) >= 8 else None
    if cnpj14 and not is_valid_cnpj14(cnpj14):
        cnpj14 = None
    return StrongKeys(
        cnpj14=cnpj14,
        cnpj8=cnpj8,
        ibge7=ibge7,
        pncp_control=(pncp_control or "").strip() or None,
        raw_name=raw,
        normalized_name=norm,
    )


def organ_canonical_key(keys: StrongKeys) -> str | None:
    """Stable organ key. Prefer CNPJ14; else CNPJ8+norm name; never name-only merge."""
    if keys.cnpj14:
        return f"org:cnpj14:{keys.cnpj14}"
    if keys.cnpj8 and keys.normalized_name:
        return f"org:cnpj8:{keys.cnpj8}:{keys.normalized_name[:80]}"
    if keys.cnpj8:
        return f"org:cnpj8:{keys.cnpj8}"
    return None


def supplier_canonical_key(keys: StrongKeys) -> str | None:
    """Stable supplier key. Prefer CNPJ14; CPF; never name-only for distinct tax ids."""
    if keys.cnpj14:
        return f"sup:cnpj14:{keys.cnpj14}"
    if keys.cpf11:
        return f"sup:cpf11:{keys.cpf11}"
    # Weak: cnpj8 alone is insufficient for golden merge across names
    if keys.cnpj8 and keys.normalized_name:
        return f"sup:cnpj8:{keys.cnpj8}:{keys.normalized_name[:80]}"
    return None


def conflicting_strong_ids(a: StrongKeys, b: StrongKeys) -> list[str]:
    """Return reason codes if two key sets must NOT be merged."""
    codes: list[str] = []
    if a.cnpj14 and b.cnpj14 and a.cnpj14 != b.cnpj14:
        codes.append("conflict_cnpj14")
    if a.cpf11 and b.cpf11 and a.cpf11 != b.cpf11:
        codes.append("conflict_cpf11")
    if a.cnpj8 and b.cnpj8 and a.cnpj8 != b.cnpj8:
        # Different roots never merge
        codes.append("conflict_cnpj8")
    if a.ibge7 and b.ibge7 and a.ibge7 != b.ibge7 and a.cnpj14 and b.cnpj14 and a.cnpj14 == b.cnpj14:
        # Same CNPJ different IBGE is anomaly but not a merge of two organs
        codes.append("anomaly_ibge_mismatch_same_cnpj")
    return codes
