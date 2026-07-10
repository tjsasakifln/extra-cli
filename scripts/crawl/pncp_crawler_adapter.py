"""PNCP Crawler adapter — Extra Consultoria.

Wraps the existing bids_crawler.py and pncp_client.py into the simple
interface expected by monitor.py: crawl(mode) → list[dict], transform(records) → list[dict].

This adapter bridges the gap between the original async/ARQ-based crawler
and the new synchronous single-user monitor.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (mirrors ingestion/config.py but with env overrides)
# ---------------------------------------------------------------------------

PNCP_BASE = os.getenv("PNCP_BASE", "https://pncp.gov.br/api/consulta/v1")
PNCP_PAGE_SIZE = int(os.getenv("PNCP_PAGE_SIZE", "100"))
PNCP_MAX_PAGES = int(os.getenv("PNCP_MAX_PAGES", "50"))
PNCP_READ_TIMEOUT = int(os.getenv("PNCP_READ_TIMEOUT", "15"))
PNCP_MAX_RETRIES = int(os.getenv("PNCP_MAX_RETRIES", "1"))

INGESTION_UFS = os.getenv("INGESTION_UFS", "SC").split(",")
INGESTION_MODALIDADES = [
    int(m) for m in os.getenv("INGESTION_MODALIDADES", "4,5,6,7").split(",")
]
INGESTION_DATE_RANGE_DAYS = int(os.getenv("INGESTION_DATE_RANGE_DAYS", "3"))
INGESTION_INCREMENTAL_DAYS = int(os.getenv("INGESTION_INCREMENTAL_DAYS", "3"))

# ---------------------------------------------------------------------------
# PNCP API Client (simplified sync version)
# ---------------------------------------------------------------------------

def _fetch_page(uf: str, modalidade: int, pagina: int,
                data_inicial: date, data_final: date) -> list[dict]:
    """Fetch one page of PNCP results synchronously."""
    import urllib.request
    import urllib.error

    params = {
        "uf": uf,
        "modalidade": str(modalidade),
        "pagina": str(pagina),
        "tamanhoPagina": str(PNCP_PAGE_SIZE),
        "dataPublicacaoInicial": data_inicial.isoformat(),
        "dataPublicacaoFinal": data_final.isoformat(),
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{PNCP_BASE}/contratacoes/publicacao?{query}"

    for attempt in range(PNCP_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Extra-Consultoria/1.0 (consultoria-licitacoes)")
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=PNCP_READ_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # PNCP wraps results differently depending on endpoint version
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Check common PNCP response shapes
                for key in ("data", "resultados", "content", "items", "registros"):
                    if key in data:
                        items = data[key]
                        if isinstance(items, list):
                            return items
                        if isinstance(items, dict) and "content" in items:
                            return items["content"]
                # Some endpoints return flat records
                return [data]
            return []

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if attempt < PNCP_MAX_RETRIES:
                import time
                time.sleep(2 ** attempt)
                continue
            _logger.warning(f"PNCP HTTP {e.code} for {url}")
            return []
        except Exception as e:
            if attempt < PNCP_MAX_RETRIES:
                import time
                time.sleep(2 ** attempt)
                continue
            _logger.warning(f"PNCP fetch error: {e}")
            return []

    return []


def _generate_content_hash(record: dict) -> str:
    """Deterministic hash for dedup — matches original transformer logic."""
    key_fields = [
        record.get("orgao_cnpj", ""),
        record.get("objeto_compra", ""),
        record.get("data_publicacao", ""),
        str(record.get("valor_total_estimado", "")),
    ]
    key_str = "|".join(key_fields)
    return hashlib.md5(key_str.encode("utf-8")).hexdigest()


def _transform_record(rec: dict) -> dict | None:
    """Transform a raw PNCP API record into the pncp_raw_bids schema."""
    try:
        orgao = rec.get("orgao", rec.get("unidade", rec.get("orgaoEntidade", {})))
        if isinstance(orgao, dict):
            orgao_cnpj = orgao.get("cnpj", "")
            orgao_nome = orgao.get("razaoSocial", orgao.get("nome", ""))
        else:
            orgao_cnpj = rec.get("orgao_cnpj", rec.get("cnpjOrgao", ""))
            orgao_nome = rec.get("orgao_razao_social", rec.get("nomeOrgao", ""))

        # Safe numeric parse
        def _safe_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _safe_date(v):
            if not v:
                return None
            if isinstance(v, (date, datetime)):
                return v.isoformat()[:10] if hasattr(v, 'isoformat') else str(v)[:10]
            s = str(v)[:10]
            return s if s and s != "None" else None

        obj = rec.get("objeto", rec.get("objetoCompra", rec.get("objeto_compra", "")))
        pncp_id = rec.get("id", rec.get("pncpId", rec.get("pncp_id", "")))
        if not pncp_id:
            # Generate synthetic ID
            pncp_id = hashlib.md5(
                f"{orgao_cnpj}|{obj}|{_safe_date(rec.get('dataPublicacao', ''))}".encode()
            ).hexdigest()

        content_hash = _generate_content_hash(rec)

        return {
            "pncp_id": str(pncp_id),
            "objeto_compra": obj,
            "valor_total_estimado": _safe_float(
                rec.get("valorTotalEstimado", rec.get("valor_total_estimado", 0))
            ),
            "modalidade_id": int(rec.get("modalidadeId", rec.get("modalidade_id", 0))),
            "modalidade_nome": rec.get("modalidadeNome", rec.get("modalidade_nome", "")),
            "esfera_id": int(rec.get("esferaId", rec.get("esfera_id", 0))),
            "uf": rec.get("uf", rec.get("ufOrgao", "SC")),
            "municipio": rec.get("municipio", rec.get("nomeMunicipio", "")),
            "codigo_municipio_ibge": rec.get("codigoIbge", rec.get("codigoMunicipioIbge", "")),
            "orgao_razao_social": orgao_nome,
            "orgao_cnpj": orgao_cnpj,
            "data_publicacao": _safe_date(rec.get("dataPublicacao", rec.get("data_publicacao"))),
            "data_abertura": _safe_date(rec.get("dataAbertura", rec.get("data_abertura"))),
            "data_encerramento": _safe_date(rec.get("dataEncerramento", rec.get("data_encerramento"))),
            "link_pncp": rec.get("link", rec.get("link_pncp", rec.get("url", ""))),
            "content_hash": content_hash,
            "source_id": str(pncp_id),
        }
    except Exception as e:
        _logger.warning(f"Transform error: {e}")
        return None


# ---------------------------------------------------------------------------
# Crawler interface (called by monitor.py)
# ---------------------------------------------------------------------------

def crawl(mode: str = "full") -> list[dict]:
    """Crawl PNCP for configured UFs and modalidades.

    Args:
        mode: 'full' or 'incremental'

    Returns:
        List of raw PNCP API records (not yet transformed)
    """
    days = INGESTION_DATE_RANGE_DAYS if mode == "full" else INGESTION_INCREMENTAL_DAYS
    data_final = date.today()
    data_inicial = data_final - timedelta(days=days)

    all_records = []

    for uf in INGESTION_UFS:
        uf = uf.strip().upper()
        for mod in INGESTION_MODALIDADES:
            for pagina in range(1, PNCP_MAX_PAGES + 1):
                records = _fetch_page(uf, mod, pagina, data_inicial, data_final)
                if not records:
                    break  # No more pages for this (UF, modalidade)
                all_records.extend(records)
                if len(records) < PNCP_PAGE_SIZE:
                    break  # Last page

    return all_records


def transform(raw_records: list[dict]) -> list[dict]:
    """Transform raw PNCP records to unified pncp_raw_bids schema."""
    transformed = []
    for rec in raw_records:
        t = _transform_record(rec)
        if t and t.get("orgao_cnpj"):  # Require at least CNPJ
            transformed.append(t)
    return transformed
