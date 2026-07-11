"""PNCP Crawler adapter — Extra Consultoria.

Wraps the existing bids_crawler.py and pncp_client.py into the simple
interface expected by monitor.py: crawl(mode) → list[dict], transform(records) → list[dict].

This adapter bridges the gap between the original async/ARQ-based crawler
and the new synchronous single-user monitor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
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
PNCP_PAGE_SIZE = int(os.getenv("PNCP_PAGE_SIZE", "50"))   # PNCP API max 50 (reduced Feb 2026)
PNCP_MAX_PAGES = int(os.getenv("PNCP_MAX_PAGES", "50"))
PNCP_READ_TIMEOUT = int(os.getenv("PNCP_READ_TIMEOUT", "30"))
PNCP_MAX_RETRIES = int(os.getenv("PNCP_MAX_RETRIES", "2"))
PNCP_REQUEST_DELAY = float(os.getenv("PNCP_REQUEST_DELAY", "0.5"))  # 500ms between requests (avoid 429)

INGESTION_UFS = [u.strip().upper() for u in os.getenv("INGESTION_UFS", "SC").split(",") if u.strip()]

# Engineering keywords from sectors_config.yaml — filter irrelevant procurement
_ENGINEERING_KEYWORDS = [
    kw.strip().lower()
    for kw in os.getenv(
        "INGESTION_KEYWORDS",
        "construç,construc,edifici,obra,engenharia,paviment,infraestrutura,urbaniz,"
        "reforma,edificação,edificacao,rodovia,ponte,viaduto,saneamento,drenagem,"
        "fundação,fundacao,estrutura,terraplenagem,asfalto",
    ).split(",")
    if kw.strip()
]
INGESTION_MODALIDADES = [
    int(m) for m in os.getenv("INGESTION_MODALIDADES", "2,3,4,7").split(",")
]
# Modalidades de engenharia (default):
#   2 = Tomada de Preços (obras médio porte)
#   3 = Convite (obras pequeno porte)
#   4 = Concorrência (obras grande porte) — PRINCIPAL
#   7 = Dispensa (obras pequeno valor)
#   6 = Concurso (projetos arquitetônicos) — opcional
# NÃO engenharia: 5=Pregão Eletrônico (bens comuns), 1=Pregão Presencial
INGESTION_DATE_RANGE_DAYS = int(os.getenv("INGESTION_DATE_RANGE_DAYS", "3"))
INGESTION_INCREMENTAL_DAYS = int(os.getenv("INGESTION_INCREMENTAL_DAYS", "3"))

# ---------------------------------------------------------------------------
# PNCP API Client (simplified sync version)
# ---------------------------------------------------------------------------

def _fetch_page(uf: str, modalidade: int, pagina: int,
                data_inicial: date, data_final: date) -> tuple[list[dict], bool]:
    """Fetch one page of PNCP results synchronously.

    Returns (records, has_next_page).
    Uses correct PNCP API parameters (camelCase, YYYYMMDD dates).
    """
    import urllib.request
    import urllib.error

    # PNCP API: dates in YYYYMMDD format, codigoModalidadeContratacao NOT modalidade
    params = {
        "dataInicial": data_inicial.strftime("%Y%m%d"),
        "dataFinal": data_final.strftime("%Y%m%d"),
        "codigoModalidadeContratacao": str(modalidade),
        "pagina": str(pagina),
        "tamanhoPagina": str(PNCP_PAGE_SIZE),
    }
    if uf:
        params["uf"] = uf

    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{PNCP_BASE}/contratacoes/publicacao?{query}"

    for attempt in range(PNCP_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Extra-Consultoria/1.0 (consultoria-licitacoes)")
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=PNCP_READ_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                # HTTP 204 No Content — no data for this day
                if not body or not body.strip():
                    return [], False
                data = json.loads(body)

            # PNCP API response: {"data": [...], "temProximaPagina": bool, "totalRegistros": int, ...}
            if isinstance(data, dict):
                records = data.get("data", [])
                has_next = data.get("temProximaPagina", False)
                if isinstance(records, list):
                    return records, has_next
                return [], False

            if isinstance(data, list):
                return data, False

            return [], False

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:200]
            except Exception:
                pass
            # 429 Too Many Requests — backoff longer
            if e.code == 429:
                wait = 5 * (attempt + 1)
                _logger.debug(f"PNCP 429, waiting {wait}s before retry")
                time.sleep(wait)
                continue
            if e.code == 404 or e.code == 400:
                _logger.debug(f"PNCP HTTP {e.code} for {url}: {body}")
                return [], False
            if attempt < PNCP_MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            _logger.warning(f"PNCP HTTP {e.code} after {PNCP_MAX_RETRIES} retries: {url}")
            return [], False
        except Exception as e:
            if attempt < PNCP_MAX_RETRIES:
                time.sleep(1 + attempt)
                continue
            _logger.warning(f"PNCP fetch error: {e}")
            return [], False

    return [], False


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

    Uses day-by-day chunking to avoid backend timeouts on multi-day queries.
    Each (UF, modalidade, day) is a separate API call (~0.2s each).

    Args:
        mode: 'full' or 'incremental'

    Returns:
        List of raw PNCP API records (not yet transformed)
    """
    days = INGESTION_DATE_RANGE_DAYS if mode == "full" else INGESTION_INCREMENTAL_DAYS
    data_final = date.today()

    all_records: list[dict] = []
    total_calls = 0
    total_success = 0

    for uf in INGESTION_UFS:
        for mod in INGESTION_MODALIDADES:
            uf_mod_records = 0
            # Day-by-day chunking: PNCP backend times out on multi-day queries
            for day_offset in range(days):
                dia = data_final - timedelta(days=day_offset)
                pagina = 1
                while pagina <= PNCP_MAX_PAGES:
                    total_calls += 1
                    records, has_next = _fetch_page(uf, mod, pagina, dia, dia)
                    if records:
                        total_success += 1
                        all_records.extend(records)
                        uf_mod_records += len(records)
                    if not records and pagina == 1:
                        break  # No results for this day
                    if not has_next:
                        break
                    pagina += 1
                    time.sleep(PNCP_REQUEST_DELAY)
                # Delay between days to avoid 429 rate limiting
                if day_offset < days - 1:
                    time.sleep(PNCP_REQUEST_DELAY)
            if uf_mod_records > 0:
                _logger.info(
                    "  %s/mod%d: %d records across %d days",
                    uf, mod, uf_mod_records, days,
                )

    _logger.info(
        "PNCP crawl done: %d records, %d/%d API calls returned data",
        len(all_records), total_success, total_calls,
    )
    return all_records


def transform(raw_records: list[dict]) -> list[dict]:
    """Transform raw PNCP records to unified pncp_raw_bids schema.

    Filters by engineering keywords (INGESTION_KEYWORDS env var).
    Only records matching at least one keyword pass through.
    """
    transformed = []
    skipped = 0
    for rec in raw_records:
        t = _transform_record(rec)
        if not t or not t.get("orgao_cnpj"):
            continue
        # Engineering keyword filter
        objeto = (t.get("objeto_compra", "") or "").lower()
        modalidade = (t.get("modalidade_nome", "") or "").lower()
        text = f"{objeto} {modalidade}"
        if not any(kw in text for kw in _ENGINEERING_KEYWORDS):
            skipped += 1
            continue
        transformed.append(t)
    if skipped:
        _logger.debug("Keyword filter: %d non-engineering records skipped", skipped)
    return transformed
