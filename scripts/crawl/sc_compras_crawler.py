"""Crawler sync adapter for Portal de Compras SC (compras.sc.gov.br).

Adapted from legacy async/httpx/class-based crawler to the simple sync interface
expected by monitor.py: crawl(mode) -> list[dict], transform(records) -> list[dict].

Rewritten to use the JSON API (SPA React backend) instead of HTML scraping.
The portal migrated to a React SPA with a JSON API at /api/editais.

Stdlib only: urllib, json, hashlib, logging, os, time, datetime.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# Add project root to path for standalone usage
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.security import USER_AGENT, validate_url_scheme  # noqa: E402

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env vars with SC_COMPRAS_ prefix)
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("SC_COMPRAS_BASE_URL", "https://compras.sc.gov.br")

HTTP_TIMEOUT = int(os.getenv("SC_COMPRAS_TIMEOUT", "45"))
MAX_RETRIES = int(os.getenv("SC_COMPRAS_MAX_RETRIES", "3"))
PAGE_DELAY_S = float(os.getenv("SC_COMPRAS_PAGE_DELAY_S", "1.0"))
MAX_PAGES = int(os.getenv("SC_COMPRAS_MAX_PAGES", "100"))

SC_COMPRAS_FULL_DAYS = int(os.getenv("SC_COMPRAS_FULL_DAYS", "30"))
SC_COMPRAS_INCREMENTAL_DAYS = int(os.getenv("SC_COMPRAS_INCREMENTAL_DAYS", "3"))

# ---------------------------------------------------------------------------
# Modalidade mapping
# ---------------------------------------------------------------------------

_MODALIDADE_MAP: dict[str, int] = {
    "pregao": 5,
    "pregao eletronico": 5,
    "pregao presencial": 6,
    "concorrencia": 4,
    "concorrencia eletronica": 4,
    "concorrencia antiga": 1,
    "tomada de precos": 2,
    "convite": 3,
    "concurso": 9,
    "leilao": 10,
    "dialogo competitivo": 13,
    "dispena de licitacao": 7,
    "dispensa de licitacao": 7,
    "dispensa com cotacao eletronica": 7,
    "contratacao direta": 7,
    "inexigibilidade": 8,
    "inexigencia de licitacao": 8,
    "procedimento de licitacao": 4,
    "selecao de consultor individual": 7,
    "selecao direta": 7,
    "selecao baseada na qualidade e custo": 7,
    "selecao baseada na qualificacao dos consultores": 7,
    "credenciamento": 12,
}


def _normalize_modalidade(raw: str) -> str:
    """Normalize modalidade string for lookup — strip accents, lowercase, clean."""
    s = raw.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^\d+[\.\)]\s*", "", s)
    s = re.sub(r"[\(\)]", "", s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    return s


def _map_modalidade(raw: str) -> tuple[int | None, str]:
    """Map SC portal modalidade string to (modalidade_id, modalidade_nome).

    Returns (None, raw) if not found.
    """
    normalized = _normalize_modalidade(raw)
    if not normalized:
        return None, raw.strip()
    mid = _MODALIDADE_MAP.get(normalized)
    if mid is not None:
        return mid, raw.strip()
    # Fuzzy fallback
    for key, mid in _MODALIDADE_MAP.items():
        if key in normalized or normalized in key:
            return mid, raw.strip()
    _logger.debug("[ScCompras] Unknown modalidade: '%s' (normalized: '%s')", raw, normalized)
    return None, raw.strip()


# ---------------------------------------------------------------------------
# Esfera inference
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


def _infer_esfera(orgao_nome: str) -> str:
    """Infer sphere letter from orgao name: 'E' (Estadual) or 'M' (Municipal).

    Letter codes are mapped to PNCP numeric esfera_id in _normalize_item
    (E→2, M→3) to satisfy chk_pncp_raw_bids_esfera_id ('1'|'2'|'3'|'4').
    """
    lower = orgao_nome.lower().strip()
    for kw in _ESFERA_ESTADUAL_KEYWORDS:
        if kw in lower:
            return "E"
    if lower.startswith("pm ") or lower.startswith("prefeitura"):
        return "M"
    return "E"


# PNCP esfera_id codes (TEXT): 1=Federal, 2=Estadual, 3=Municipal, 4=Distrital
_ESFERA_LETTER_TO_ID: dict[str, str] = {"F": "1", "E": "2", "M": "3"}


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _digits_only(s: str | None) -> str:
    """Strip non-digits from a string."""
    if not s:
        return ""
    return re.sub(r"\D", "", s)


def _parse_br_date(s: str | None) -> str | None:
    """Parse DD/MM/YYYY to YYYY-MM-DD. Returns None if unparseable."""
    if not s or not s.strip():
        return None
    s = s.strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return None


def _parse_br_number(s: str | None) -> float | None:
    """Parse Brazilian-formatted number (e.g. '1.500,00' or '150000')."""
    if not s or not s.strip():
        return None
    s = s.strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rindex(",") > s.rindex("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _content_hash(*parts: str) -> str:
    """Deterministic MD5 hash of joined parts for dedup."""
    raw = "|".join(parts)
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# API-to-canonical mapping
# ---------------------------------------------------------------------------


def _api_item_to_canonical(item: dict, detail: dict | None = None) -> dict:
    """Map API JSON items/detail to the canonical dict keys expected by _normalize_item.

    API list fields:
        id, processo, tipo, orgaoSigla, orgaoNome, objeto,
        entregaProposta, abertura, situacao

    API detail fields (from /api/editais/{id}):
        id, modalidade, edital, dataAtualizacao, objeto, natureza,
        dataPublicacao (YYYY-MM-DD), dataEntrega, dataAbertura,
        processoSgpe, situacao, tipoSituacao, observacao, temRetificacao,
        dataSituacao, dataArremate, dataEncerramento, origem, linkArquivosFTP

    Merges optional detail over list data before returning.
    """
    merged = dict(item)
    if detail:
        merged.update(detail)

    # Map API keys to canonical keys
    numero = merged.get("edital") or merged.get("processo") or ""
    url_detalhe = f"{BASE_URL}/editais/{merged.get('id', '')}" if merged.get("id") else None

    canonical = {
        "numero_processo": numero.strip(),
        "api_id": merged.get("id"),
        "modalidade": merged.get("modalidade") or merged.get("tipo") or "",
        "objeto": merged.get("objeto", "").strip(),
        "orgao": merged.get("orgaoNome", "").strip(),
        "orgao_sigla": merged.get("orgaoSigla", "").strip(),
        "data_publicacao": merged.get("dataPublicacao", "").strip(),
        "data_abertura": merged.get("dataAbertura") or merged.get("abertura") or "",
        "data_encerramento": merged.get("dataEncerramento") or "",
        "situacao": merged.get("situacao", "").strip(),
        "url_detalhe": url_detalhe,
        # Not available from API (were in old HTML):
        "orgao_cnpj": "",
        "municipio": "",
        "uf": "",
        "valor": None,
    }

    return canonical


# ---------------------------------------------------------------------------
# API request helpers (JSON API, no HTML scraping)
# ---------------------------------------------------------------------------


def _api_request(url: str) -> dict | None:
    """Make a GET request to the SC Compras JSON API. Returns parsed dict or None."""
    last_error: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            validate_url_scheme(url)
            req = urllib.request.Request(url)  # noqa: S310 — validated above
            req.add_header("Accept", "application/json")
            req.add_header(
                "User-Agent",
                USER_AGENT,
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 — validated above
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8", errors="replace"))
                _logger.warning(
                    "[ScCompras] HTTP %s for %s (attempt %d/%d)",
                    resp.status,
                    url,
                    attempt,
                    MAX_RETRIES,
                )
                last_error = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                _logger.debug("[ScCompras] %s returned %d — no data", url, e.code)
                return None
            _logger.warning(
                "[ScCompras] HTTP %d for %s (attempt %d/%d): %s",
                e.code,
                url,
                attempt,
                MAX_RETRIES,
                e,
            )
            last_error = f"HTTP {e.code}"
        except Exception as e:
            _logger.warning(
                "[ScCompras] Network error for %s (attempt %d/%d): %s",
                url,
                attempt,
                MAX_RETRIES,
                e,
            )
            last_error = str(e)

        if attempt < MAX_RETRIES:
            time.sleep(2.0 * attempt)

    _logger.error(
        "[ScCompras] Failed to fetch %s after %d attempts: %s",
        url,
        MAX_RETRIES,
        last_error,
    )
    return None


def _fetch_api_list(ano: int) -> list[dict]:
    """Fetch all items from /api/editais for a given year.

    Uses a large page size so the API returns all matching items in one
    response (the 'pagina' parameter is ignored by the backend for this
    endpoint, so pagination iteration is not possible server-side).

    Returns a list of raw API item dicts, or empty list on failure.
    """
    params = {"ano": str(ano), "tamanhoPagina": "3000"}
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{BASE_URL}/api/editais?{query}"

    data = _api_request(full_url)
    if not data:
        return []

    items = data.get("conteudo", [])
    total = data.get("totalElementos", 0)
    _logger.debug(
        "[ScCompras] API list: ano=%d -> %d items returned (total=%d)",
        ano,
        len(items),
        total,
    )
    return items


def _fetch_api_detail(item_id: int) -> dict | None:
    """Fetch /api/editais/{id} detail for a single edital.

    Returns the detail dict (includes dataPublicacao, modalidade, natureza,
    dataAbertura, dataEncerramento, etc.) or None on failure.
    """
    return _api_request(f"{BASE_URL}/api/editais/{item_id}")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize_item(raw: dict) -> dict | None:
    """Normalize a raw SC portal item to pncp_raw_bids schema.

    The raw dict should be the canonical dict produced by _api_item_to_canonical()
    (keys: numero_processo, modalidade, objeto, orgao, data_publicacao,
    situacao, valor, url_detalhe, orgau_cnpj, municipio, etc.).

    Does NOT include 'source' — monitor.py adds it.
    Content hash uses MD5.
    """
    numero = (raw.get("numero_processo") or "").strip()
    api_id = raw.get("api_id")
    if not numero:
        return None

    # Use API id for uniqueness (process numbers are shared across editais)
    if api_id is not None:
        pncp_id = f"sc-{api_id}"
        source_id = pncp_id
    else:
        pncp_id = f"sc-{numero}"
        source_id = pncp_id
    objeto = (raw.get("objeto") or "").strip()
    if len(objeto) > 1000:
        objeto = objeto[:997] + "..."

    # data_publicacao may come from the API detail (dataPublicacao, YYYY-MM-DD)
    # or fall back to today
    data_publicacao = _parse_br_date(raw.get("data_publicacao")) or datetime.now().date().isoformat()
    data_abertura = _parse_br_date(raw.get("data_abertura"))
    data_encerramento = _parse_br_date(raw.get("data_encerramento"))

    orgao = (raw.get("orgao") or "").strip()
    orgao_cnpj = _digits_only(raw.get("orgao_cnpj"))
    valor = _parse_br_number(raw.get("valor"))

    modalidade_raw = (raw.get("modalidade") or "").strip()
    modalidade_id, modalidade_nome = _map_modalidade(modalidade_raw)

    municipio = (raw.get("municipio") or "").strip()
    url_detalhe = (raw.get("url_detalhe") or "").strip()
    esfera_letter = _infer_esfera(orgao)
    # DB constraint chk_pncp_raw_bids_esfera_id allows only '1'|'2'|'3'|'4'
    esfera = _ESFERA_LETTER_TO_ID.get(esfera_letter, "2")

    content_hash = _content_hash(pncp_id, data_publicacao, objeto)

    return {
        "pncp_id": pncp_id,
        "objeto_compra": objeto or None,
        "valor_total_estimado": round(valor, 2) if valor is not None else None,
        "modalidade_id": modalidade_id,
        "modalidade_nome": modalidade_nome or None,
        "esfera_id": esfera,
        "uf": "SC",
        "municipio": municipio or None,
        "codigo_municipio_ibge": None,  # Not available from SC portal
        "orgao_razao_social": orgao or None,
        "orgao_cnpj": orgao_cnpj or None,
        "data_publicacao": data_publicacao,
        "data_abertura": data_abertura or None,
        "data_encerramento": data_encerramento or None,
        "link_pncp": url_detalhe or None,
        "content_hash": content_hash,
        "source_id": source_id,
    }


# ---------------------------------------------------------------------------
# Public API (called by monitor.py)
# ---------------------------------------------------------------------------


def smoke(ano: int | None = None) -> dict:
    """Connectivity smoke against public JSON API (list only, no detail fan-out).

    Performs a single GET ``/api/editais?ano=YYYY`` and returns a diagnostics
    dict suitable for ops probes. Does not enrich details (avoids N+1).

    Returns:
        dict with keys: ok, http-ish status via ok flag, ano, total_elementos,
        count, sample_ids, error, base_url.
    """
    year = ano or date.today().year
    params = {"ano": str(year), "tamanhoPagina": "5"}
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{BASE_URL}/api/editais?{query}"
    started = time.time()
    out: dict = {
        "ok": False,
        "ano": year,
        "url": full_url,
        "base_url": BASE_URL,
        "total_elementos": None,
        "count": 0,
        "sample_ids": [],
        "error": None,
        "elapsed_s": None,
        "public_json": True,
        "probed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    data = _api_request(full_url)
    out["elapsed_s"] = round(time.time() - started, 3)
    if not data:
        out["error"] = "empty_or_failed_response"
        return out
    items = data.get("conteudo") or []
    if not isinstance(items, list):
        out["error"] = "unexpected_conteudo_type"
        return out
    out["ok"] = True
    out["total_elementos"] = data.get("totalElementos")
    out["count"] = len(items)
    out["sample_ids"] = [it.get("id") for it in items[:3] if isinstance(it, dict)]
    out["sample_keys"] = list(items[0].keys()) if items and isinstance(items[0], dict) else []
    return out


def crawl(mode: str = "full") -> list[dict]:
    """Crawl SC Compras portal via JSON API.

    Fetches the edital list from /api/editais (all at once, since the API
    ignores pagination parameters), then optionally enriches each item with
    detail from /api/editais/{id} to obtain additional fields (data_publicacao,
    data_encerramento, clean modalidade, etc.).

    Detail enrichment is enabled by default (matching the pre-SPA behavior).
    Set SC_COMPRAS_LIST_ONLY=1 to fetch list data only (faster, but loses
    publication dates which fall back to the current date).

    Args:
        mode: 'full' (last 30 days), 'incremental' (last 3 days), or
            'smoke' (list-only connectivity probe — returns up to a few
            canonical items without detail enrichment).

    Returns:
        List of raw item dicts in canonical format (keys expected by
        _normalize_item / transform). Empty list on failure (graceful
        degradation). For mode='smoke', at most 5 list items (no detail).
    """
    if mode == "smoke":
        result = smoke()
        if not result.get("ok"):
            _logger.warning("[ScCompras] smoke failed: %s", result.get("error"))
            return []
        # Re-fetch list via helper and map first few items list-only
        raw_items = _fetch_api_list(int(result["ano"]))
        sample = raw_items[:5]
        return [_api_item_to_canonical(it) for it in sample]

    days = SC_COMPRAS_FULL_DAYS if mode == "full" else SC_COMPRAS_INCREMENTAL_DAYS
    today_d = date.today()
    date_from_d = today_d - timedelta(days=days)

    # smoke already handled; list-only env still applies to full/incremental
    fetch_detail_flag = not bool(int(os.getenv("SC_COMPRAS_LIST_ONLY", "0")))

    _logger.info(
        "[ScCompras] Crawling %s mode: %s -> %s (JSON API, detail=%s)",
        mode,
        date_from_d.isoformat(),
        today_d.isoformat(),
        fetch_detail_flag,
    )

    # Determine which years to fetch
    years_needed = {today_d.year}
    if date_from_d.year < today_d.year:
        years_needed.add(date_from_d.year)

    all_items: list[dict] = []
    items_count = 0

    for ano in sorted(years_needed, reverse=True):
        raw_items = _fetch_api_list(ano)
        if not raw_items:
            _logger.warning(
                "[ScCompras] No data for year %d — API may be unavailable",
                ano,
            )
            continue

        if fetch_detail_flag:
            _logger.info(
                "[ScCompras] Enriching %d items with details (year %d) ...",
                len(raw_items),
                ano,
            )
        else:
            _logger.info(
                "[ScCompras] Using list-only for %d items (year %d); publication dates will default to today",
                len(raw_items),
                ano,
            )

        for i, item in enumerate(raw_items):
            try:
                if fetch_detail_flag:
                    detail = _fetch_api_detail(item["id"])
                else:
                    detail = None

                canonical = _api_item_to_canonical(item, detail)
                all_items.append(canonical)
                items_count += 1
            except Exception as e:
                _logger.debug(
                    "[ScCompras] Error processing item %s: %s",
                    item.get("processo", item.get("id", "?")),
                    e,
                )
                # Fallback: use list-only data
                canonical = _api_item_to_canonical(item)
                all_items.append(canonical)
                items_count += 1

        time.sleep(PAGE_DELAY_S)

    _logger.info(
        "[ScCompras] Crawl complete: %d items from %d year(s)",
        items_count,
        len(years_needed),
    )
    return all_items


def transform(records: list[dict]) -> list[dict]:
    """Transform raw SC portal records to pncp_raw_bids schema.

    Pure normalization — does NOT fetch additional data.
    Does NOT include 'source' field (monitor.py adds it).

    Args:
        records: Raw records from crawl() (enriched with detail data)

    Returns:
        List of normalized dicts matching pncp_raw_bids schema.
    """
    normalized: list[dict] = []
    errors = 0

    for raw in records:
        try:
            rec = _normalize_item(raw)
            if rec:
                normalized.append(rec)
            else:
                errors += 1
        except Exception as e:
            _logger.warning("[ScCompras] Transform error: %s", e)
            errors += 1

    if errors:
        _logger.warning(
            "[ScCompras] Transform: %d/%d records skipped due to errors",
            errors,
            len(records),
        )

    _logger.info(
        "[ScCompras] Transform complete: %d -> %d normalized records",
        len(records),
        len(normalized),
    )
    return normalized


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m scripts.crawl.sc_compras_crawler smoke``."""
    args = list(argv if argv is not None else sys.argv[1:])
    cmd = (args[0] if args else "smoke").lower()
    if cmd in {"smoke", "--smoke"}:
        result = smoke()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    print("Usage: python -m scripts.crawl.sc_compras_crawler smoke", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
