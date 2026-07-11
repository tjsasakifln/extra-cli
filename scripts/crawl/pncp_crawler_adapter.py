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
from datetime import date, timedelta
from pathlib import Path

from scripts.crawl.common import (
    generate_content_hash as _common_content_hash,
)
from scripts.crawl.common import (
    safe_date as _safe_date,
)
from scripts.crawl.common import (
    safe_float as _safe_float,
)
from scripts.crawl.security import USER_AGENT, sanitize_url_param

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (mirrors ingestion/config.py but with env overrides)
# ---------------------------------------------------------------------------

PNCP_BASE = os.getenv("PNCP_BASE", "https://pncp.gov.br/api/consulta/v1")
PNCP_PAGE_SIZE = int(os.getenv("PNCP_PAGE_SIZE", "50"))  # PNCP API v3: max 50, min 10
PNCP_MAX_PAGES = int(os.getenv("PNCP_MAX_PAGES", "200"))
PNCP_READ_TIMEOUT = int(os.getenv("PNCP_READ_TIMEOUT", "30"))
PNCP_MAX_RETRIES = int(os.getenv("PNCP_MAX_RETRIES", "2"))
PNCP_REQUEST_DELAY = float(os.getenv("PNCP_REQUEST_DELAY", "0.5"))  # 500ms between requests (avoid 429)

INGESTION_UFS = [u.strip().upper() for u in os.getenv("INGESTION_UFS", "SC").split(",") if u.strip()]

# PNCP API v3 esferaId mapping (letter → integer for DB schema)
_ESFERA_MAP = {"F": 1, "E": 2, "M": 3, "D": 4}

# Optional keyword filter — empty default means ALL records pass through
_ENGINEERING_KEYWORDS = [
    kw.strip().lower()
    for kw in os.getenv("INGESTION_KEYWORDS", "").split(",")
    if kw.strip()
]
INGESTION_MODALIDADES = [int(m) for m in os.getenv("INGESTION_MODALIDADES", "4,5,6,7,8,12").split(",")]
# Modalidades PNCP v3:
#   1 = Pregão Presencial, 2 = Tomada de Preços, 3 = Convite
#   4 = Concorrência, 5 = Pregão Eletrônico, 6 = Concurso
#   7 = Dispensa, 8 = Inexigibilidade, 9 = Leilão
#   12 = Diálogo Competitivo
# Default: 4,5,6,7,8,12 — covers all relevant competitive modalities
INGESTION_DATE_RANGE_DAYS = int(os.getenv("INGESTION_DATE_RANGE_DAYS", "30"))
INGESTION_INCREMENTAL_DAYS = int(os.getenv("INGESTION_INCREMENTAL_DAYS", "1"))

# ---------------------------------------------------------------------------
# PNCP API Client (simplified sync version)
# ---------------------------------------------------------------------------


def _fetch_page(uf: str, modalidade: int, pagina: int, data_inicial: date, data_final: date) -> tuple[list[dict], bool]:
    """Fetch one page of PNCP results synchronously.

    Returns (records, has_next_page).
    Uses correct PNCP API parameters (camelCase, YYYYMMDD dates).
    """
    import urllib.error
    import urllib.request

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

    query = "&".join(f"{k}={sanitize_url_param(v)}" for k, v in params.items())
    url = f"{PNCP_BASE}/contratacoes/publicacao?{query}"

    for attempt in range(PNCP_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=PNCP_READ_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                # HTTP 204 No Content — no data for this day
                if not body or not body.strip():
                    return [], False
                data = json.loads(body)

            # PNCP API v3 response: {"data": [...], "paginasRestantes": int, "totalRegistros": int, ...}
            if isinstance(data, dict):
                records = data.get("data", [])
                paginas_restantes = data.get("paginasRestantes", 0)
                has_next = bool(paginas_restantes > 0)
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
                time.sleep(2**attempt)
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
    """Deterministic hash for dedup — delegates to common.

    Uses v3 API field names. Falls back to transformed field names
    for backward compatibility during testing.
    """
    return _common_content_hash(
        record,
        fields=["orgao_cnpj", "objeto_compra", "data_publicacao", "valor_total_estimado"],
    )


def _transform_record(rec: dict) -> dict | None:
    """Transform a raw PNCP API v3 record into the pncp_raw_bids schema.

    PNCP API v3 nests organization data inside ``orgaoEntidade`` and
    ``unidadeOrgao`` objects.  This function flattens those into the
    top-level column names expected by ``upsert_pncp_raw_bids``.
    """
    try:
        orgao: dict = rec.get("orgaoEntidade") or {}
        unidade: dict = rec.get("unidadeOrgao") or {}

        # Core identifiers
        pncp_id: str = str(rec.get("numeroControlePNCP", ""))
        if not pncp_id:
            # Generate synthetic ID as last resort
            pncp_id = hashlib.md5(
                f"{orgao.get('cnpj', '')}|{rec.get('objetoCompra', '')}|{rec.get('dataPublicacaoPncp', '')}".encode(),
                usedforsecurity=False,
            ).hexdigest()

        objeto_compra: str = rec.get("objetoCompra", "")

        valor_total_estimado = _safe_float(rec.get("valorTotalEstimado"))

        modalidade_id = rec.get("modalidadeId") or rec.get("codigoModalidadeContratacao", 0)
        modalidade_nome: str = rec.get("modalidadeNome", "")

        esfera_raw = orgao.get("esferaId") or rec.get("esferaId", "")
        esfera_id = _ESFERA_MAP.get(str(esfera_raw).strip().upper())
        # DB CHECK constraint: 1,2,3,4 or NULL. 0/NULL for unknown.

        # Geography from unidadeOrgao
        uf: str = unidade.get("ufSigla") or rec.get("uf", "SC")
        municipio: str = unidade.get("municipioNome") or rec.get("municipio", "")
        codigo_municipio_ibge: str = unidade.get("codigoIbge") or unidade.get("codigoMunicipioIbge", "")

        # Orgao info
        orgao_razao_social: str = orgao.get("razaoSocial") or unidade.get("nomeUnidade", "")
        orgao_cnpj: str = orgao.get("cnpj", "")

        # Dates — API returns ISO strings in dataPublicacaoPncp, dataAberturaProposta, etc.
        data_publicacao = _safe_date(rec.get("dataPublicacaoPncp"))
        data_abertura = _safe_date(rec.get("dataAberturaProposta")) or data_publicacao
        data_encerramento = _safe_date(rec.get("dataEncerramentoProposta"))

        # Links
        link_pncp: str = rec.get("linkSistemaOrigem", "")
        if not link_pncp and pncp_id and orgao_cnpj:
            # Build fallback PNCP link: https://pncp.gov.br/app/editais/{pncp_id}
            link_pncp = f"https://pncp.gov.br/app/editais/{pncp_id}"

        result = {
            "pncp_id": pncp_id,
            "objeto_compra": objeto_compra,
            "valor_total_estimado": valor_total_estimado,
            "modalidade_id": int(modalidade_id) if modalidade_id else 0,
            "modalidade_nome": modalidade_nome,
            "esfera_id": esfera_id,  # None → NULL (DB CHECK: 1,2,3,4 or NULL)
            "uf": uf,
            "municipio": municipio,
            "codigo_municipio_ibge": str(codigo_municipio_ibge) if codigo_municipio_ibge else "",
            "orgao_razao_social": orgao_razao_social,
            "orgao_cnpj": orgao_cnpj,
            "data_publicacao": data_publicacao,
            "data_abertura": data_abertura,
            "data_encerramento": data_encerramento,
            "link_pncp": link_pncp,
            "content_hash": "",  # computed below
            "source": "pncp",
            "source_id": pncp_id,
        }
        # Compute content hash from transformed fields — deterministic dedup
        result["content_hash"] = _generate_content_hash(result)
        return result
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
                    uf,
                    mod,
                    uf_mod_records,
                    days,
                )

    _logger.info(
        "PNCP crawl done: %d records, %d/%d API calls returned data",
        len(all_records),
        total_success,
        total_calls,
    )
    return all_records


def transform(raw_records: list[dict]) -> list[dict]:
    """Transform raw PNCP records to unified pncp_raw_bids schema.

    Optionally filters by engineering keywords (INGESTION_KEYWORDS env var).
    When INGESTION_KEYWORDS is empty (default), ALL records pass through.
    """
    transformed = []
    skipped = 0
    for rec in raw_records:
        t = _transform_record(rec)
        if not t or not t.get("orgao_cnpj"):
            continue
        # Optional keyword filter — skip when _ENGINEERING_KEYWORDS is empty
        if _ENGINEERING_KEYWORDS:
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
