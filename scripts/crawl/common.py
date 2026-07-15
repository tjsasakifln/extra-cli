"""Shared helpers for crawler modules — Extra Consultoria.

Centralized versions of utility functions that were historically
duplicated across multiple crawlers (``_digits_only``, ``_parse_date``,
``_safe_float``, ``_extract_cnpj``, etc.).

Usage::

    from scripts.crawl.common import digits_only, safe_float, parse_date

All crawlers SHOULD use these functions instead of defining their own
private copies. Crawler-specific adaptations (e.g. logging for zero
values) SHOULD be thin wrappers that call these and add behavior.

Consolidated per TD-3.2 (Eliminar Codigo Duplicado).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from typing import Any

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------


def digits_only(s: str | None) -> str:
    """Strip all non-digit characters from a string.

    Args:
        s: Input string (e.g. ``"12.345.678/0001-99"``).

    Returns:
        Digits-only string (e.g. ``"12345678000199"``), or ``""`` for
        ``None`` / empty input.
    """
    if not s:
        return ""
    return re.sub(r"\D", "", s)


def extract_cnpj(text: str | None) -> str:
    """Extract CNPJ (``XX.XXX.XXX/XXXX-XX`` or 14 consecutive digits) from text.

    Tries formatted pattern first (``XX.XXX.XXX/XXXX-XX``), then
    bare 14-digit sequence. Returns only the digits.

    Args:
        text: Arbitrary text that may contain a CNPJ.

    Returns:
        CNPJ digits only (14 characters), or ``""`` if none found.
    """
    if not text:
        return ""
    # Standard CNPJ pattern: XX.XXX.XXX/XXXX-XX
    m = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", text)
    if m:
        return digits_only(m.group(0))
    # 14 consecutive digits
    m = re.search(r"\d{14}", text)
    if m:
        return m.group(0)
    return ""


def trunc(s: str | None, max_len: int) -> str | None:
    """Truncate a string to ``max_len`` with ellipsis if longer.

    Args:
        s: Input string.
        max_len: Maximum length before truncation with ``"..."``.

    Returns:
        Truncated string (minimum 4 chars to accommodate ellipsis), or
        ``None`` for ``None`` / empty / whitespace-only input.
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    if len(s) > max_len:
        return s[: max(4, max_len) - 3] + "..."
    return s


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def safe_float(value: Any) -> float | None:
    """Safely parse a numeric value to ``float``.

    Handles Brazilian format (``"150.000,00"``), regular format (``150000.00``),
    and ``int`` / ``float`` directly.

    Args:
        value: Value to convert (str, int, float, or None).

    Returns:
        ``float`` rounded to 2 decimal places, or ``None`` if unparseable.
    """
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return round(float(value), 2)
        val_str = str(value).strip()
        if not val_str:
            return None
        # Brazilian format: "150.000,00" or "150000.00"
        if "," in val_str and "." in val_str:
            val_str = val_str.replace(".", "").replace(",", ".")
        elif "," in val_str:
            val_str = val_str.replace(",", ".")
        return round(float(val_str), 2)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def parse_date(value: Any) -> str | None:
    """Parse a date from various formats to ``YYYY-MM-DD`` string.

    Handles:
    - ``datetime`` / ``date`` objects
    - ISO 8601 strings (``2026-07-09``, ``2026-07-09T00:00:00``)
    - Brazilian format (``09/07/2026``)
    - Partial ISO substrings

    Args:
        value: Date value in any supported format.

    Returns:
        ISO date string (``YYYY-MM-DD``) or ``None`` if unparseable.
    """
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        s = value.strip()
        if len(s) >= 10 and s[4] == "-":
            return s[:10]
        if len(s) >= 10 and s[2] == "/":
            try:
                return datetime.strptime(s[:10], "%d/%m/%Y").date().isoformat()
            except ValueError:
                pass
        # Partial ISO anywhere
        for i in range(len(s) - 9):
            if s[i + 4] == "-" and s[i + 7] == "-":
                return s[i : i + 10]
    return None


def safe_date(v: Any) -> str | None:
    """Extract an ISO date string from various value types.

    Simpler than ``parse_date`` -- handles ``date`` / ``datetime`` objects
    and string extraction of the first 10 ISO characters.

    Args:
        v: Value to extract date from.

    Returns:
        ``YYYY-MM-DD`` string, or ``None`` for ``None`` / blank / ``"None"``.
    """
    if not v:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10] if hasattr(v, "isoformat") else str(v)[:10]
    s = str(v)[:10]
    return s if s and s != "None" else None


# ---------------------------------------------------------------------------
# Content hash (MD5 dedup)
# ---------------------------------------------------------------------------


def generate_content_hash(record: dict, fields: list[str] | None = None) -> str:
    """Deterministic MD5 hash for dedup across a subset of record fields.

    Args:
        record: Data dict (typically a normalized or raw record).
        fields: Key field names to hash over. Defaults to
            ``["orgao_cnpj", "objeto_compra", "data_publicacao"]``.

    Returns:
        32-character MD5 hex digest.
    """
    if fields is None:
        fields = ["orgao_cnpj", "objeto_compra", "data_publicacao"]
    key_fields = [str(record.get(f, "")) for f in fields]
    key_str = "|".join(key_fields)
    return hashlib.md5(key_str.encode("utf-8"), usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# Cross-source canonical hash (CM-13)
# ---------------------------------------------------------------------------


def _normalize_objeto(objeto: str | None) -> str:
    """Normaliza objeto de licitação para hash determinístico.

    Remove: acentos, pontuação dupla, espaços extras, case folding.
    """
    if not objeto:
        return ""
    import unicodedata

    s = objeto.strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    # Remove pontuação dupla e espaços múltiplos
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_modalidade(modalidade: str | None) -> str:
    """Normaliza nome de modalidade para hash cross-source."""
    if not modalidade:
        return ""
    return modalidade.strip().lower()


def generate_cross_source_hash(
    modalidade: str | None = None,
    objeto: str | None = None,
    orgao_cnpj_raiz: str | None = None,
    data_publicacao: str | None = None,
    valor_total: float | None = None,
    use_md5: bool = False,
) -> str:
    """Hash canônico cross-source para dedup multi-fonte.

    Story: CM-13 — Deduplicação Multicanal e Aliases de Compradores.

    Combinação normalizada de:
      modalidade + objeto_normalizado + orgao_raiz + data + valor

    Usa SHA-256 por padrão (colisão extremamente improvável).
    ``use_md5=True`` produz MD5 para compatibilidade retroativa.

    Args:
        modalidade: Nome da modalidade (ex: "Pregão Eletrônico").
        objeto: Texto do objeto da licitação.
        orgao_cnpj_raiz: CNPJ raiz (8 dígitos) do órgão publicante.
        data_publicacao: Data de publicação (YYYY-MM-DD).
        valor_total: Valor total estimado (float).
        use_md5: Se True, usa MD5 em vez de SHA-256.

    Returns:
        Hash hex digest (64 chars SHA-256, 32 chars MD5).
    """
    parts = [
        _normalize_modalidade(modalidade),
        _normalize_objeto(objeto),
        orgao_cnpj_raiz or "",
        data_publicacao or "",
        f"{valor_total:.2f}" if valor_total is not None else "",
    ]
    key = "|".join(parts)
    if use_md5:
        return hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
