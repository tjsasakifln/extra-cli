"""Deterministic identifier normalization and join keys.

Priority of joins (never use loose similarity when deterministic IDs exist):
1. numeroControlePNCP
2. numeroControlePNCPCompra
3. órgão + ano + sequencial
4. número do processo
5. número do contrato + órgão
6. probabilistic fallback — only when explicitly marked
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


def digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_cnpj(value: str | None) -> str:
    d = digits_only(value)
    return d[:14] if len(d) >= 14 else d


def cnpj_root(value: str | None) -> str:
    d = normalize_cnpj(value)
    return d[:8] if len(d) >= 8 else d


def normalize_pncp_control(value: str | None) -> str | None:
    """Normalize PNCP control numbers (keep structure, collapse whitespace)."""
    if not value:
        return None
    s = re.sub(r"\s+", "", str(value).strip())
    return s or None


_PROCESS_SEP = re.compile(r"[\s./\\|_-]+")


def normalize_process_number(value: str | None) -> str | None:
    """Normalize administrative process numbers across common masks.

    Examples that should collapse when digits+year structure matches:
    - 00123/2024
    - 123/2024
    - 00123.2024
    - processo nº 00123/2024
    """
    if not value:
        return None
    raw = str(value).strip()
    # Strip common prefixes
    raw = re.sub(r"(?i)^(processo|proc\.?|n[uú]mero|n[º°.]?)\s*", "", raw).strip()
    raw = re.sub(r"(?i)^(do\s+processo|administrativo)\s*", "", raw).strip()
    if not raw:
        return None
    # Keep alnum and separators for display key; also build digit-year form
    compact = re.sub(r"\s+", "", raw)
    # Prefer digit sequences with year
    m = re.search(
        r"(\d{1,12})\s*[./\\|_-]?\s*(20\d{2}|\d{2})\b",
        compact,
    )
    if m:
        seq = m.group(1).lstrip("0") or "0"
        year = m.group(2)
        if len(year) == 2:
            year = "20" + year
        return f"{seq}/{year}"
    # SEI-like: 00000.000000/2024-00
    m2 = re.search(r"(\d{5}\.\d{6}/\d{4}-\d{2})", compact)
    if m2:
        return m2.group(1)
    # Fallback: collapse separators, keep alnum
    alnum = re.sub(r"[^A-Za-z0-9]", "", compact)
    return alnum.lower() if alnum else None


def process_number_variants(value: str | None) -> list[str]:
    """Generate search variants for a process number."""
    base = normalize_process_number(value)
    if not base:
        return []
    variants = {base, str(value or "").strip()}
    if "/" in base:
        seq, year = base.split("/", 1)
        variants.add(f"{seq}/{year}")
        variants.add(f"{seq.zfill(5)}/{year}")
        variants.add(f"{seq}.{year}")
        variants.add(f"{seq}-{year}")
        variants.add(f"{seq}{year}")
    return [v for v in variants if v]


def normalize_company_name(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"\b(LTDA|S\.?A\.?|EIRELI|ME|EPP|MEI)\b", " ", text)
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass(frozen=True)
class JoinKey:
    method: str
    key: str
    confidence: float
    probabilistic: bool = False


def join_keys_from_contract(row: dict[str, Any]) -> list[JoinKey]:
    """Emit ordered join keys for a contract/procurement row."""
    keys: list[JoinKey] = []
    for field, method, conf in (
        ("numeroControlePNCP", "numeroControlePNCP", 1.0),
        ("numero_controle_pncp", "numeroControlePNCP", 1.0),
        ("numeroControlePncpCompra", "numeroControlePNCPCompra", 0.98),
        ("numero_controle_pncp_compra", "numeroControlePNCPCompra", 0.98),
        ("pncp_control_number", "numeroControlePNCP", 0.95),
    ):
        val = normalize_pncp_control(row.get(field))
        if val:
            keys.append(JoinKey(method=method, key=val, confidence=conf))

    org = normalize_cnpj(
        row.get("orgao_cnpj")
        or row.get("contracting_authority_cnpj")
        or (row.get("orgaoEntidade") or {}).get("cnpj")
    )
    year = row.get("ano") or row.get("ano_contrato") or row.get("anoCompra") or row.get("year")
    seq = (
        row.get("sequencial")
        or row.get("sequencial_contrato")
        or row.get("sequencialCompra")
        or row.get("sequential")
    )
    if org and year is not None and seq is not None:
        keys.append(
            JoinKey(
                method="orgao_ano_sequencial",
                key=f"{org}|{int(year)}|{int(seq)}",
                confidence=0.95,
            )
        )

    proc = normalize_process_number(
        row.get("processo")
        or row.get("administrative_process_number")
        or row.get("numero_processo")
        or row.get("process_number")
    )
    if proc and org:
        keys.append(JoinKey(method="process_number_org", key=f"{org}|{proc}", confidence=0.85))
    elif proc:
        keys.append(JoinKey(method="process_number", key=proc, confidence=0.7))

    contract_no = row.get("numero_contrato_empenho") or row.get("contract_number") or row.get("numeroContratoEmpenho")
    if contract_no and org:
        keys.append(
            JoinKey(
                method="contract_number_org",
                key=f"{org}|{re.sub(r'\s+', '', str(contract_no))}",
                confidence=0.75,
            )
        )
    return keys


def best_join(left: dict[str, Any], right: dict[str, Any]) -> JoinKey | None:
    """Return the highest-confidence deterministic join between two records."""
    left_keys = {k.key: k for k in join_keys_from_contract(left) if not k.probabilistic}
    right_keys = {k.key: k for k in join_keys_from_contract(right) if not k.probabilistic}
    best: JoinKey | None = None
    for key, lk in left_keys.items():
        rk = right_keys.get(key)
        if not rk:
            continue
        conf = min(lk.confidence, rk.confidence)
        candidate = JoinKey(method=lk.method, key=key, confidence=conf)
        if best is None or candidate.confidence > best.confidence:
            best = candidate
    return best


def parse_pncp_control_parts(control: str | None) -> dict[str, Any] | None:
    """Parse common PNCP control forms into orgao/year/seq when possible.

    Examples:
    - 12345678000199-1-000123/2024
    """
    c = normalize_pncp_control(control)
    if not c:
        return None
    m = re.match(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$", c)
    if m:
        return {
            "orgao_cnpj": m.group(1),
            "modality_or_type": int(m.group(2)),
            "sequential": int(m.group(3)),
            "year": int(m.group(4)),
        }
    return None
