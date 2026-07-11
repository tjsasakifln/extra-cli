"""PNCP Contracts Crawler — Extra Consultoria.

Adapted from the original async/BaseCrawler-based contracts_crawler.py
to the simple sync interface expected by monitor.py:
    crawl(mode) -> list[dict]
    transform(records) -> list[dict]

Crawls PNCP /contratos endpoint in date windows and normalizes
to the pncp_supplier_contracts schema (contrato_id, fornecedor_cnpj,
objeto_contrato, valor_total, etc.).

Modes:
  - full:        Last CONTRACTS_FULL_DAYS days (default 90)
  - incremental: Last CONTRACTS_INCREMENTAL_DAYS days (default 3)
"""

from __future__ import annotations

import json
import logging
import os
import sys

from scripts.crawl.common import (
    digits_only as _digits_only,
    generate_content_hash as _common_content_hash,
    safe_date as _safe_date,
    trunc as trunc,
)
from scripts.crawl.security import USER_AGENT, sanitize_url_param
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root for standalone imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env vars with CONTRACTS_ prefix)
# ---------------------------------------------------------------------------

CONTRACTS_BASE = os.getenv("CONTRACTS_BASE", "https://pncp.gov.br/api/consulta/v1")
CONTRACTS_PAGE_SIZE = int(os.getenv("CONTRACTS_PAGE_SIZE", "500"))
CONTRACTS_MAX_PAGES = int(os.getenv("CONTRACTS_MAX_PAGES", "10000"))
CONTRACTS_READ_TIMEOUT = int(os.getenv("CONTRACTS_READ_TIMEOUT", "30"))
CONTRACTS_MAX_RETRIES = int(os.getenv("CONTRACTS_MAX_RETRIES", "3"))
CONTRACTS_REQUEST_DELAY = float(os.getenv("CONTRACTS_REQUEST_DELAY", "0.5"))
CONTRACTS_WINDOW_DAYS = int(os.getenv("CONTRACTS_WINDOW_DAYS", "90"))
CONTRACTS_FULL_DAYS = int(os.getenv("CONTRACTS_FULL_DAYS", "90"))
CONTRACTS_INCREMENTAL_DAYS = int(os.getenv("CONTRACTS_INCREMENTAL_DAYS", "3"))

_ESFERA_MAP = {"F": 1, "E": 2, "M": 3, "D": 4}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    """Safely parse a numeric value to float, with negative value warning.

    Handles Brazilian format (``"150.000,00"``) and regular format.
    Warns and returns ``None`` for negative values (contracts-specific rule).
    """
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            result = round(float(value), 2)
            if result < 0:
                logger.warning("Negative value for contract: %s", value)
                return None
            return result
        val_str = str(value).strip()
        if not val_str:
            return None
        # Brazilian format: "150.000,00" or "150000.00"
        if "," in val_str and "." in val_str:
            val_str = val_str.replace(".", "").replace(",", ".")
        elif "," in val_str:
            val_str = val_str.replace(",", ".")
        result = round(float(val_str), 2)
        if result < 0:
            logger.warning("Negative value for contract: %s", value)
            return None
        return result
    except (ValueError, TypeError):
        return None


_CNPJ_ROOT_UF: dict[str, str] = {
    "000000": "DF",
    "003944": "DF",
    "005654": "DF",
    "005665": "DF",
    "008898": "DF",
    "008929": "DF",
    "008944": "DF",
    "009532": "DF",
    "009610": "DF",
    "010001": "DF",
}


def _uf_from_cnpj(cnpj: str) -> str | None:
    """Infer UF from CNPJ root (first 6 digits).

    Args:
        cnpj: Full CNPJ (14+ digits) or any string.

    Returns:
        Two-letter UF (e.g. ``"DF"``) or ``None`` if unknown.
    """
    if not cnpj or len(cnpj) < 6:
        return None
    return _CNPJ_ROOT_UF.get(cnpj[:6])


def _generate_content_hash(record: dict) -> str:
    """MD5 hash of key fields for dedup (pncp_supplier_contracts convention)."""
    return _common_content_hash(record, fields=["contrato_id", "orgao_cnpj", "objeto_contrato", "valor_total"])


def _fmt(d: date) -> str:
    return d.strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# HTTP fetch (sync, stdlib only)
# ---------------------------------------------------------------------------


def _fetch_page(
    data_ini: str, data_fim: str, page: int
) -> tuple[list[dict], int, int]:
    """Fetch one page of contracts synchronously via urllib.

    Returns (items, total_records, total_pages).
    On failure returns ([], 0, 0) with a warning log.
    """
    import urllib.error
    import urllib.request

    params = {
        "dataInicial": data_ini,
        "dataFinal": data_fim,
        "pagina": str(page),
        "tamanhoPagina": str(CONTRACTS_PAGE_SIZE),
    }
    query = "&".join(f"{k}={sanitize_url_param(v)}" for k, v in params.items())
    url = f"{CONTRACTS_BASE}/contratos?{query}"

    for attempt in range(CONTRACTS_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=CONTRACTS_READ_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)

            if isinstance(data, dict):
                items = data.get("data", [])
                total_records = int(data.get("totalRegistros", 0))
                total_pages = int(data.get("totalPaginas", 1))
                return (items if isinstance(items, list) else []), total_records, total_pages

            if isinstance(data, list):
                return data, len(data), 1

            return [], 0, 0

        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8")[:200]
            except Exception:
                pass
            if e.code in (404, 400):
                logger.debug("PNCP HTTP %d for %s: %s", e.code, url, body_text)
                return [], 0, 0
            if attempt < CONTRACTS_MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            logger.warning(
                "PNCP HTTP %d after %d retries: %s — %s",
                e.code, CONTRACTS_MAX_RETRIES, url, body_text,
            )
            return [], 0, 0

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < CONTRACTS_MAX_RETRIES:
                time.sleep(1 + attempt)
                continue
            logger.warning(
                "PNCP network error page %d attempt %d/%d: %s — returning empty",
                page, attempt, CONTRACTS_MAX_RETRIES, e,
            )
            return [], 0, 0

    return [], 0, 0


# ---------------------------------------------------------------------------
# Transform a single record
# ---------------------------------------------------------------------------


def _transform_record(rec: dict) -> dict | None:
    """Normalize a single PNCP /contratos item to pncp_supplier_contracts schema.

    Returns ``None`` if the record lacks a valid ``numeroControlePNCP``.
    """
    try:
        contrato_id = (rec.get("numeroControlePNCP") or "").strip()
        if not contrato_id:
            return None

        orgao = rec.get("orgaoEntidade") or {}
        unidade = rec.get("unidadeOrgao") or {}

        orgao_cnpj = _digits_only(orgao.get("cnpj"))

        # Supplier data
        fornecedor_cnpj = _digits_only(rec.get("niFornecedor"))
        fornecedor_nome = (rec.get("nomeRazaoSocialFornecedor") or "").strip()

        # Object / description
        objeto = (rec.get("objetoContrato") or rec.get("informacaoComplementar") or "").strip()
        if len(objeto) > 500:
            objeto = objeto[:497] + "..."

        # Contract value — try multiple field names
        valor = None
        for field in ("valorGlobal", "valorInicial", "valorTotalEstimado"):
            raw = rec.get(field)
            v = _safe_float(raw)
            if v is not None:
                valor = v
                break

        # Orgao name — unidade first, then orgao
        orgao_nome = (
            unidade.get("nomeUnidade") or orgao.get("razaoSocial") or ""
        )[:300] or None

        # Dates
        data_publicacao = _safe_date(rec.get("dataAssinatura"))
        data_inicio = _safe_date(rec.get("dataVigenciaInicio"))
        data_fim = _safe_date(rec.get("dataVigenciaFim"))

        # UF — unidade first, CNPJ lookup second, SC fallback
        uf = (unidade.get("ufSigla") or "")[:2] or None
        if not uf:
            uf = _uf_from_cnpj(orgao_cnpj)
        if not uf:
            uf = "SC"

        municipio = (unidade.get("municipioNome") or "")[:100] or None

        record = {
            "contrato_id": contrato_id,
            "orgao_cnpj": orgao_cnpj or None,
            "orgao_nome": orgao_nome,
            "fornecedor_cnpj": fornecedor_cnpj or None,
            "fornecedor_nome": fornecedor_nome or None,
            "objeto_contrato": objeto or None,
            "valor_total": round(valor, 2) if valor is not None else None,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "data_publicacao": data_publicacao,
            "uf": uf or None,
            "municipio": municipio,
            "source_id": contrato_id,
        }

        return record

    except Exception as e:
        logger.warning("Transform error for record %s: %s", rec.get("numeroControlePNCP", ""), e)
        return None


# ---------------------------------------------------------------------------
# Public interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl PNCP /contratos endpoint for raw contract records.

    Args:
        mode: 'full' — last CONTRACTS_FULL_DAYS (default 90 days)
              'incremental' — last CONTRACTS_INCREMENTAL_DAYS (default 3 days)

    Returns:
        List of raw PNCP API records (not yet transformed).
        Empty list if API is unreachable or returns no data.
    """
    days = CONTRACTS_FULL_DAYS if mode == "full" else CONTRACTS_INCREMENTAL_DAYS
    today = date.today()
    start = today - timedelta(days=days)

    all_records: list[dict] = []

    # Split date range into windows (default 90 days each)
    cur = start
    while cur < today:
        window_end = min(cur + timedelta(days=CONTRACTS_WINDOW_DAYS - 1), today)
        data_ini = _fmt(cur)
        data_fim = _fmt(window_end)

        page = 1
        window_records = 0
        window_pages = 0

        while page <= CONTRACTS_MAX_PAGES:
            items, total_records, total_pages = _fetch_page(data_ini, data_fim, page)

            if not items and page == 1:
                # Window has no records at all
                break

            if not items:
                break

            all_records.extend(items)
            window_records += len(items)
            window_pages += 1

            if page >= total_pages:
                break

            page += 1
            time.sleep(CONTRACTS_REQUEST_DELAY)

        if window_records > 0:
            logger.info(
                "Window %s->%s: %d records (%d pages)",
                data_ini, data_fim, window_records, window_pages,
            )

        cur = window_end + timedelta(days=1)

    return all_records


def transform(records: list[dict]) -> list[dict]:
    """Transform raw PNCP contracts records to pncp_supplier_contracts schema.

    Args:
        records: Raw records from crawl().

    Returns:
        Normalized records ready for upsert.
        Does NOT include 'source' field — monitor.py adds it as 'pncp_contracts'.
    """
    transformed: list[dict] = []
    for rec in records:
        t = _transform_record(rec)
        if t and t.get("fornecedor_cnpj"):
            transformed.append(t)
    return transformed
