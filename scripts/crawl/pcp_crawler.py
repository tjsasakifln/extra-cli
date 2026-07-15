"""PCP Crawler adapter — Extra Consultoria.

Adapted from legacy PortalComprasAdapter (async/httpx/clients.base) to the
simple sync interface expected by monitor.py: crawl(mode) -> list[dict],
transform(records) -> list[dict].

Uses stdlib urllib only — no external HTTP dependencies.

API: Portal de Compras Publicas v2 Public API
    Base URL: https://compras.api.portaldecompraspublicas.com.br/v2
    No authentication required.
    Pagination: fixed 10 per page via `pagina` param.
    UF filtering: client-side only (API returns all UFs).
    Date format: YYYY-MM-DD.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from scripts.crawl.common import (
    generate_content_hash as _common_content_hash,
)
from scripts.crawl.common import (
    parse_date as _parse_date,
)
from scripts.crawl.security import USER_AGENT, sanitize_url_param

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env overrides match legacy naming)
# ---------------------------------------------------------------------------

PCP_BASE = "https://compras.api.portaldecompraspublicas.com.br"
PCP_PAGE_SIZE = 10  # v2 API fixed at 10 per page
PCP_MAX_PAGES = int(os.getenv("PCP_MAX_PAGES_V2", "200"))
PCP_READ_TIMEOUT = int(os.getenv("PCP_READ_TIMEOUT", "30"))
PCP_MAX_RETRIES = int(os.getenv("PCP_MAX_RETRIES", "2"))
PCP_REQUEST_DELAY = float(os.getenv("PCP_REQUEST_DELAY", "0.2"))  # 200ms between pages

INGESTION_UFS = [u.strip().upper() for u in os.getenv("INGESTION_UFS", "SC").split(",") if u.strip()]

# PCP internal UF codes — format: '1001' + IBGE state code.
# Determined empirically from Parse.bot docs (RS=100143, SP=100135) + runtime validation.
# Source: Exa MCP research via Parse.bot marketplace (2026-07-15).
_PCP_UF_CODE: dict[str, str] = {
    "RO": "100111", "AC": "100112", "AM": "100113", "RR": "100114", "PA": "100115",
    "AP": "100116", "TO": "100117", "MA": "100121", "PI": "100122", "CE": "100123",
    "RN": "100124", "PB": "100125", "PE": "100126", "AL": "100127", "SE": "100128",
    "BA": "100129", "MG": "100131", "ES": "100132", "RJ": "100133", "SP": "100135",
    "PR": "100141", "SC": "100142", "RS": "100143", "MS": "100150", "MT": "100151",
    "GO": "100152", "DF": "100153",
}

# ---------------------------------------------------------------------------
# Modalidade mapping (string names -> numeric IDs)
# ---------------------------------------------------------------------------

_MODALIDADE_MAP: dict[str, int] = {
    "pregao": 5,
    "pregao eletronico": 5,
    "pregao presencial": 6,
    "concorrencia": 4,
    "concorrencia antiga": 1,
    "tomada de precos": 2,
    "convite": 3,
    "concurso": 9,
    "leilao": 10,
    "dialogo competitivo": 13,
    "dispensa de licitacao": 7,
    "dispensa": 7,
    "contratacao direta": 7,
    "inexigibilidade": 8,
    "credenciamento": 12,
}


def _normalize_modalidade(raw: str) -> str:
    """Strip accents, lowercase, remove numbering prefixes."""
    s = raw.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"^\d+[\.\)]\s*", "", s)
    s = re.sub(r"[\(\)]", "", s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    return s


def _map_modalidade(raw: str) -> tuple[int, str]:
    """Map PCP modalidade string to (modalidade_id, modalidade_nome).

    Returns (0, raw) if unknown.
    """
    if not raw:
        return 0, ""
    normalized = _normalize_modalidade(raw)
    mid = _MODALIDADE_MAP.get(normalized)
    if mid is not None:
        return mid, raw.strip()
    # Fuzzy partial match
    for key, mid in _MODALIDADE_MAP.items():
        if key in normalized or normalized in key:
            return mid, raw.strip()
    _logger.debug("[PCP] Unknown modalidade: '%s' (normalized: '%s')", raw, normalized)
    return 0, raw.strip()


# ---------------------------------------------------------------------------
# Esfera inference (from orgão name)
# ---------------------------------------------------------------------------

_ESFERA_ESTADUAL_KEYWORDS = [
    "secretaria de estado",
    "secretaria da",
    "governo do estado",
    "fundo estadual",
    "companhia",
    "santa catarina",
    "deinfra",
    "udesc",
    "jucesc",
    "detran",
    "ima",
    "imetro",
    "aresc",
    "iprev",
    "fapesc",
    "fcc",
    "fcee",
    "fesporte",
    "ciasc",
    "badesc",
    "scpar",
    "scgas",
    "ceasa",
    "cidasc",
    "santur",
    "sudes",
    "pcisc",
    "ena",
]

_ESFERA_MUNICIPAL_KEYWORDS = [
    "prefeitura",
    "municipio de",
    "camara municipal",
    "fundacao municipal",
    "secretaria municipal",
    "servico autonomo",
    "departamento municipal",
]


def _infer_esfera(orgao_nome: str) -> int:
    """Infer administrative sphere from orgao name.

    Returns:
        1 = Federal, 2 = Estadual, 3 = Municipal (default for PCP)
    """
    if not orgao_nome:
        return 3
    lower = orgao_nome.lower().strip()

    for kw in _ESFERA_ESTADUAL_KEYWORDS:
        if kw in lower:
            return 2

    for kw in _ESFERA_MUNICIPAL_KEYWORDS:
        if kw in lower:
            return 3

    # Federal keywords (less common for PCP but worth checking)
    federal_kws = [
        "ministerio",
        "departamento nacional",
        "universidade federal",
        "instituto federal",
        "fundacao universidade federal",
    ]
    for kw in federal_kws:
        if kw in lower:
            return 1

    return 3  # Default to municipal for PCP


# ---------------------------------------------------------------------------
# HTTP client (stdlib urllib, sync)
# ---------------------------------------------------------------------------


def _fetch_page(
    pagina: int,
    data_inicial: str,
    data_final: str,
    codigo_uf: str | None = None,
) -> tuple[list[dict], bool]:
    """Fetch one page of PCP v2 results synchronously.

    Args:
        pagina: Page number (1-indexed).
        data_inicial: Start date YYYY-MM-DD.
        data_final: End date YYYY-MM-DD.
        codigo_uf: Optional PCP internal UF code for server-side filtering.
                   When provided, the API returns only records for that state,
                   making client-side UF filtering unnecessary.

    Returns:
        (records, has_next_page)
    """
    params = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "tipoData": "1",
        "pagina": str(pagina),
    }
    if codigo_uf:
        params["codigoUf"] = codigo_uf
    query = "&".join(f"{k}={sanitize_url_param(v)}" for k, v in params.items())
    url = f"{PCP_BASE}/v2/licitacao/processos?{query}"

    for attempt in range(PCP_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url)  # noqa: S310 — hardcoded HTTPS PCP API endpoint (PCP_BASE = https://...)
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", USER_AGENT)

            with urllib.request.urlopen(req, timeout=PCP_READ_TIMEOUT) as resp:  # noqa: S310 — hardcoded HTTPS PCP API endpoint
                body = resp.read().decode("utf-8")
                data = json.loads(body)

            # v2 response: { "result": [...], "total": N, "pageCount": N, ... }
            if isinstance(data, dict):
                records = data.get("result", [])
                if isinstance(records, list):
                    page_count = data.get("pageCount", 0) or 1
                    has_next = pagina < page_count
                    return records, has_next
                return [], False

            if isinstance(data, list):
                return data, bool(data)

            return [], False

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:200]
            except Exception:
                _logger.debug("[PCP] Could not read error body from HTTP %d response", e.code)
            if e.code in (404, 400):
                _logger.debug("[PCP] HTTP %d: %s", e.code, body)
                return [], False
            if e.code == 429 and attempt < PCP_MAX_RETRIES:
                retry_after = int(e.headers.get("Retry-After", "60"))
                _logger.warning("[PCP] Rate limited. Waiting %ds", retry_after)
                time.sleep(retry_after)
                continue
            if attempt < PCP_MAX_RETRIES:
                delay = 2**attempt
                _logger.debug("[PCP] HTTP %d, retrying in %ds", e.code, delay)
                time.sleep(delay)
                continue
            _logger.warning("[PCP] HTTP %d after %d retries: %s", e.code, PCP_MAX_RETRIES, url)
            return [], False

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < PCP_MAX_RETRIES:
                delay = 1 + attempt
                _logger.debug("[PCP] Connection error, retrying in %ds: %s", delay, e)
                time.sleep(delay)
                continue
            _logger.warning("[PCP] Fetch error after %d retries: %s", PCP_MAX_RETRIES, e)
            return [], False

    return [], False


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def _generate_content_hash(record: dict) -> str:
    """Deterministic MD5 hash over key fields (delegates to common)."""
    return _common_content_hash(
        record, fields=["orgao_cnpj", "objeto_compra", "data_publicacao", "valor_total_estimado"]
    )


# ---------------------------------------------------------------------------
# Record transformation
# ---------------------------------------------------------------------------


def _transform_record(rec: dict) -> dict | None:
    """Transform a raw PCP v2 API record into pncp_raw_bids schema.

    Returns None if the record is missing required fields (codigoLicitacao).
    """
    try:
        codigo = rec.get("codigoLicitacao")
        if not codigo:
            return None
        pncp_id = f"pcp_{codigo}"

        # Object description
        objeto = (rec.get("resumo") or "").strip()

        # Buyer info from unidadeCompradora
        unidade = rec.get("unidadeCompradora") or {}
        if isinstance(unidade, dict):
            orgao = unidade.get("nomeUnidadeCompradora") or rec.get("razaoSocial") or rec.get("nomeUnidade") or ""
            cnpj = unidade.get("CNPJ") or unidade.get("cnpj") or None
            municipio_nome = unidade.get("cidade") or ""
            uf = unidade.get("uf") or ""
        else:
            orgao = rec.get("razaoSocial") or ""
            cnpj = None
            municipio_nome = ""
            uf = ""

        # Dates
        data_publicacao = _parse_date(rec.get("dataHoraPublicacao"))
        data_abertura = _parse_date(rec.get("dataHoraInicioPropostas"))
        data_encerramento = _parse_date(rec.get("dataHoraFinalPropostas"))

        # Modalidade
        tipo_lic = rec.get("tipoLicitacao") or {}
        if isinstance(tipo_lic, dict):
            modalidade_raw = tipo_lic.get("modalidadeLicitacao") or tipo_lic.get("tipoLicitacao") or ""
        else:
            modalidade_raw = str(tipo_lic) if tipo_lic else ""

        modalidade_id, modalidade_nome = _map_modalidade(modalidade_raw)

        # Esfera (inferred from orgao name)
        esfera_id = _infer_esfera(orgao)

        # Link
        portal_url = "https://www.portaldecompraspublicas.com.br"
        url_ref = rec.get("urlReferencia") or ""
        if url_ref:
            link_pncp = f"{portal_url}{url_ref}"
        else:
            link_pncp = f"{portal_url}/processos/{codigo}"

        record = {
            "pncp_id": pncp_id,
            "objeto_compra": objeto,
            "valor_total_estimado": None,  # v2 listing does not include value
            "modalidade_id": modalidade_id,
            "modalidade_nome": modalidade_nome,
            "esfera_id": esfera_id,
            "uf": uf,
            "municipio": municipio_nome,
            "codigo_municipio_ibge": "",  # PCP v2 does not provide IBGE code
            "orgao_razao_social": orgao,
            "orgao_cnpj": cnpj,
            "data_publicacao": data_publicacao,
            "data_abertura": data_abertura,
            "data_encerramento": data_encerramento,
            "link_pncp": link_pncp,
            "content_hash": "",
        }
        record["content_hash"] = _generate_content_hash(record)

        return record

    except Exception as e:
        _logger.warning("[PCP] Transform error: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl PCP v2 API for procurement processes.

    Args:
        mode: 'full' = 365 days, 'incremental' = 3 days.

    Returns:
        List of raw PCP API records (not yet transformed).
        Filtered by INGESTION_UFS (server-side when possible, client-side fallback).
    """
    # Backward-compat: accept only str mode. CrawlRequest objects fall through to
    # the TypeError handler in monitor.py, which calls crawl(mode_str).
    if not isinstance(mode, str):
        raise TypeError(f"pcp_crawler.crawl() expects str mode, got {type(mode).__name__}")

    days = 365 if mode == "full" else 3
    data_final = date.today()
    data_inicial = data_final - timedelta(days=days)

    data_inicial_str = data_inicial.strftime("%Y-%m-%d")
    data_final_str = data_final.strftime("%Y-%m-%d")

    # Server-side UF filtering: use when exactly one UF is configured and we know its PCP code.
    # This avoids fetching all 27 states and filtering ~10% client-side.
    # Format: '1001' + IBGE state code (empirically validated 2026-07-15 via Exa MCP).
    codigo_uf: str | None = None
    if len(INGESTION_UFS) == 1:
        codigo_uf = _PCP_UF_CODE.get(INGESTION_UFS[0])
    server_side_uf = codigo_uf is not None

    _logger.info(
        "[PCP] Crawl [%s]: %s to %s, UF=%s, server_side=%s, max_pages=%d",
        mode,
        data_inicial_str,
        data_final_str,
        INGESTION_UFS,
        server_side_uf,
        PCP_MAX_PAGES,
    )

    all_records: list[dict] = []
    pagina = 1

    while pagina <= PCP_MAX_PAGES:
        page_start = time.time()
        records, has_next = _fetch_page(pagina, data_inicial_str, data_final_str, codigo_uf)

        elapsed_ms = int((time.time() - page_start) * 1000)

        if not records and pagina == 1:
            _logger.info("[PCP] No results for date range")
            break
        if not records:
            break

        _logger.debug("[PCP] Page %d: %d records in %dms", pagina, len(records), elapsed_ms)

        if server_side_uf:
            # All records are already from the target UF — no client-side filtering needed.
            all_records.extend(records)
        elif INGESTION_UFS:
            # Client-side UF filtering fallback (API returns all UFs).
            filtered: list[dict] = []
            for rec in records:
                unidade = rec.get("unidadeCompradora") or {}
                uf = unidade.get("uf", "") if isinstance(unidade, dict) else ""
                if uf.upper() in INGESTION_UFS:
                    filtered.append(rec)
            all_records.extend(filtered)
            _logger.debug(
                "[PCP] Page %d: %d records after UF filter",
                pagina,
                len(filtered),
            )
        else:
            all_records.extend(records)

        if not has_next:
            break

        pagina += 1
        time.sleep(PCP_REQUEST_DELAY)  # Rate limiting

    _logger.info("[PCP] Crawl complete: %d records (%d pages)", len(all_records), pagina)
    return all_records


def transform(raw_records: list[dict]) -> list[dict]:
    """Transform raw PCP records to unified pncp_raw_bids schema.

    NOTE: monitor.py adds ``source='pcp'`` after transform — do NOT add it here.

    PCP v2 API does NOT return CNPJ in listing endpoint. Records are kept
    with empty orgao_cnpj and matched later by name (orgao_razao_social + municipio).
    """
    transformed: list[dict] = []
    for rec in raw_records:
        t = _transform_record(rec)
        if t and t.get("pncp_id"):  # Only require synthetic ID
            transformed.append(t)
    return transformed
