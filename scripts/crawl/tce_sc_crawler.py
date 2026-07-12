"""TCE-SC Crawler — SCMWeb JSON API adapter.

Extrai dados de licitacoes e contratos do SCMWeb (Sistema de Compras e
Contratos da Administracao Publica de SC) via JSON API.

Fonte: https://www.scmweb.com.br/processos/index.php (SCMWeb Transparency)
Cobre: TCE-SC como orgao publicante primario

Adaptado para a interface sync esperada pelo monitor.py:
    crawl(mode) -> list[dict]       # busca dados brutos da API
    transform(records) -> list[dict] # normaliza para schema pncp_raw_bids

Nota tecnica:
    O parametro ``p285`` no URL identifica o TCE-SC como orgao. O SCMWeb
    suporta filtro por ``unidade_gestora`` para expandir cobertura a outros
    entes municipais de SC (ver Fase 2 do plano de expansao).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.security import USER_AGENT, sanitize_url_param

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.scmweb.com.br/processos/index.php"

# Parametro fixo que identifica o TCE-SC como orgao no SCMWeb
ORGAO_PARAM = "p285"

# Timeout per API call (seconds)
HTTP_TIMEOUT = 30

# Delay between requests (rate limiting)
DEFAULT_DELAY_SECONDS = float(os.getenv("TCE_SC_REQUEST_DELAY", "2.0"))

# Max retries per failed request
MAX_RETRIES = int(os.getenv("TCE_SC_MAX_RETRIES", "3"))

# Full crawl window (days)
TCE_SC_FULL_DAYS = int(os.getenv("TCE_SC_FULL_DAYS", "365"))

# Incremental crawl window (days)
TCE_SC_INCREMENTAL_DAYS = int(os.getenv("TCE_SC_INCREMENTAL_DAYS", "7"))

# Feature flag
TCE_SC_ENABLED = os.getenv("TCE_SC_ENABLED", "true").lower() in ("true", "1")

# Modalidades de contratacao (mapeamento SCMWeb -> padrao)
_MODALIDADE_MAP: dict[str, int] = {
    "pregao": 5,
    "pregao eletronico": 5,
    "pregao presencial": 6,
    "concorrencia": 4,
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

# Status mapping (SCMWeb -> normalizado)
_SITUACAO_MAP: dict[str, str] = {
    "finalizada": "finalizada",
    "homologada": "homologada",
    "em andamento": "em_andamento",
    "aberta": "aberta",
    "revogada": "revogada",
    "anulada": "anulada",
    "suspensa": "suspensa",
    "vigente": "vigente",
    "encerrada": "encerrada",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _digits_only(s: str | None) -> str:
    """Strip non-digit characters from a string."""
    if not s:
        return ""
    return re.sub(r"\D", "", s)


def _parse_date(value: Any) -> str | None:
    """Parse a date from various formats to YYYY-MM-DD string.

    Handles:
        - ISO 8601 (2026-07-09)
        - Brazilian format (09/07/2026)
        - Datetime strings like '2026-07-09T00:00:00'
    """
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if len(s) >= 10 and s[4] == "-":
            return s[:10]
        if len(s) >= 10 and s[2] == "/":
            try:
                return datetime.strptime(s[:10], "%d/%m/%Y").date().isoformat()
            except ValueError:
                pass
        # Try partial ISO (YYYY-MM-DD anywhere)
        for i in range(len(s) - 9):
            if s[i + 4] == "-" and s[i + 7] == "-":
                return s[i : i + 10]
    return None


def _safe_float(value: Any) -> float | None:
    """Safely parse a numeric value to float."""
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


def _normalize_modalidade(raw: str) -> str:
    """Strip accents, lowercase, remove numbering prefixes."""
    import unicodedata

    s = raw.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"^\d+[\.\)]\s*", "", s)
    s = re.sub(r"[\(\)]", "", s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    return s


def _map_modalidade(raw: str) -> tuple[int, str]:
    """Map SCMWeb modalidade string to (modalidade_id, modalidade_nome).

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
    _logger.debug("[TCE-SC] Unknown modalidade: '%s' (normalized: '%s')", raw, normalized)
    return 0, raw.strip()


def _normalize_situacao(raw: str) -> str:
    """Normalize situacao string."""
    if not raw:
        return ""
    s = raw.strip().lower()
    s = re.sub(r"\s*/\s*", "/", s)
    # Extract primary status from compound values like "FINALIZADA / HOMOLOGADA"
    primary = s.split("/")[0].strip()
    for key, mapped in _SITUACAO_MAP.items():
        if key in primary or primary in key:
            return mapped
    return primary


# ---------------------------------------------------------------------------
# HTTP Client (sync, stdlib only)
# ---------------------------------------------------------------------------


def _api_request(params: dict[str, Any], timeout: int = HTTP_TIMEOUT) -> dict | list | None:
    """Make a sync HTTP GET request to the SCMWeb JSON API.

    Args:
        params: Query parameters for the request.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON (dict or list), or None on failure.
    """
    import urllib.error
    import urllib.request

    # Build query string
    param_parts = []
    for k, v in params.items():
        if v is not None:
            param_parts.append(f"{k}={sanitize_url_param(v)}")
    query = "&".join(param_parts)

    # Ensure base params for SCMWeb transparency
    base = {
        "pg": "transparencia",
        ORGAO_PARAM: "",
    }
    base.update(params)
    base.pop(ORGAO_PARAM, None)
    # Rebuild with orgao_param as flag (no value)
    param_parts = []
    param_parts.append("pg=transparencia")
    param_parts.append(ORGAO_PARAM)
    for k, v in params.items():
        if k != "pg" and v is not None:
            param_parts.append(f"{k}={sanitize_url_param(v)}")
    query = "&".join(param_parts)
    full_url = f"{BASE_URL}?{query}"

    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(full_url)
            req.add_header("User-Agent", USER_AGENT)
            req.add_header("Accept", "application/json")
            req.add_header("Accept-Language", "pt-BR,pt;q=0.9")

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")

            # Handle empty response (204 No Content)
            if not body or not body.strip():
                return None

            data = json.loads(body)
            return data

        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = 5 * (attempt + 1)
                _logger.warning("[TCE-SC] Rate limited (429), waiting %ds before retry", wait)
                time.sleep(wait)
                continue
            if exc.code in (404, 400):
                _logger.debug("[TCE-SC] HTTP %d for %s", exc.code, full_url)
                return None
            if attempt < MAX_RETRIES:
                delay = 2**attempt
                _logger.debug("[TCE-SC] HTTP %d, retrying in %ds", exc.code, delay)
                time.sleep(delay)
                continue
            _logger.error(
                "[TCE-SC] HTTP %d after %d retries: %s",
                exc.code,
                MAX_RETRIES,
                full_url,
            )
            return None

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < MAX_RETRIES:
                delay = 1 + attempt
                _logger.debug("[TCE-SC] Connection error, retrying in %ds: %s", delay, exc)
                time.sleep(delay)
                continue
            _logger.error(
                "[TCE-SC] Request failed after %d retries: %s: %s",
                MAX_RETRIES,
                type(exc).__name__,
                exc,
            )
            return None

        except json.JSONDecodeError as exc:
            _logger.error("[TCE-SC] Invalid JSON response: %s", exc)
            return None

    return None


# ---------------------------------------------------------------------------
# API data fetching
# ---------------------------------------------------------------------------


def _fetch_licitacoes(
    data_inicial: date | None = None,
    data_final: date | None = None,
    ano: int | None = None,
    unidade_gestora: str | None = None,
) -> list[dict]:
    """Fetch licitacoes from SCMWeb JSON API.

    Args:
        data_inicial: Start date filter.
        data_final: End date filter.
        ano: Year filter (e.g., 2026).
        unidade_gestora: Optional filter by managing unit code.

    Returns:
        List of raw licitacao dicts from the API.
    """
    params: dict[str, Any] = {
        "page": "licitacoes",
        "export": "json",
        "type": "licitacoes",
    }

    if ano:
        params["ano"] = str(ano)
    if data_inicial:
        params["data_inicio"] = data_inicial.strftime("%d/%m/%Y")
    if data_final:
        params["data_fim"] = data_final.strftime("%d/%m/%Y")
    if unidade_gestora:
        params["unidade_gestora"] = unidade_gestora

    records: list[dict] = []
    page = 1

    while True:
        params["pn"] = str(page)
        _logger.debug("[TCE-SC] Fetching page %d of licitacoes", page)

        data = _api_request(params)
        if data is None:
            _logger.warning("[TCE-SC] Failed to fetch page %d", page)
            break

        # API pode retornar dict com "data" ou lista direta
        if isinstance(data, dict):
            items = data.get("data", data.get("rows", data.get("results", [])))
            if not isinstance(items, list):
                items = [data]
        elif isinstance(data, list):
            items = data
        else:
            break

        if not items:
            break

        records.extend(items)
        _logger.debug("[TCE-SC] Page %d: %d items (total: %d)", page, len(items), len(records))

        # Heuristica de paginacao: se retornou menos que o tamanho da pagina, parar
        if len(items) < 20:
            break

        page += 1
        time.sleep(DEFAULT_DELAY_SECONDS)

    _logger.info("[TCE-SC] Fetched %d licitacoes total", len(records))
    return records


def _fetch_contratos(
    data_inicial: date | None = None,
    data_final: date | None = None,
    ano: int | None = None,
    unidade_gestora: str | None = None,
) -> list[dict]:
    """Fetch contratos from SCMWeb JSON API.

    Args:
        data_inicial: Start date filter.
        data_final: End date filter.
        ano: Year filter.
        unidade_gestora: Optional filter by managing unit code.

    Returns:
        List of raw contrato dicts from the API.
    """
    params: dict[str, Any] = {
        "page": "contratos",
        "export": "json",
        "type": "contratos",
    }

    if ano:
        params["ano"] = str(ano)
    if data_inicial:
        params["data_inicio"] = data_inicial.strftime("%d/%m/%Y")
    if data_final:
        params["data_fim"] = data_final.strftime("%d/%m/%Y")
    if unidade_gestora:
        params["unidade_gestora"] = unidade_gestora

    records: list[dict] = []
    page = 1

    while True:
        params["pn"] = str(page)
        _logger.debug("[TCE-SC] Fetching page %d of contratos", page)

        data = _api_request(params)
        if data is None:
            _logger.warning("[TCE-SC] Failed to fetch contratos page %d", page)
            break

        if isinstance(data, dict):
            items = data.get("data", data.get("rows", data.get("results", [])))
            if not isinstance(items, list):
                items = [data]
        elif isinstance(data, list):
            items = data
        else:
            break

        if not items:
            break

        records.extend(items)
        _logger.debug("[TCE-SC] Contratos page %d: %d items (total: %d)", page, len(items), len(records))

        if len(items) < 20:
            break

        page += 1
        time.sleep(DEFAULT_DELAY_SECONDS)

    _logger.info("[TCE-SC] Fetched %d contratos total", len(records))
    return records


# ---------------------------------------------------------------------------
# Public interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl TCE-SC SCMWeb API.

    Coleta licitacoes e contratos do SCMWeb. No modo 'full', busca o periodo
    completo configurado (TCE_SC_FULL_DAYS). No modo 'incremental', busca
    apenas o periodo recente (TCE_SC_INCREMENTAL_DAYS).

    Args:
        mode: 'full' (periodo completo) ou 'incremental' (ultimos dias).

    Returns:
        Lista de registros brutos (dicts) mesclando licitacoes e contratos,
        cada um com um campo ``_tipo`` indicando 'licitacao' ou 'contrato'.
    """
    if not TCE_SC_ENABLED:
        _logger.info("[TCE-SC] Disabled (TCE_SC_ENABLED=false)")
        return []

    days = TCE_SC_FULL_DAYS if mode == "full" else TCE_SC_INCREMENTAL_DAYS
    data_final = date.today()
    data_inicial = data_final - timedelta(days=days)

    _logger.info(
        "[TCE-SC] Crawling %s mode: %s to %s (%d days)",
        mode,
        data_inicial,
        data_final,
        days,
    )

    all_records: list[dict] = []

    # Fase 1: Licitacoes
    try:
        licitacoes = _fetch_licitacoes(data_inicial=data_inicial, data_final=data_final)
        for rec in licitacoes:
            rec["_tipo"] = "licitacao"
        all_records.extend(licitacoes)
        _logger.info("[TCE-SC] Licitações: %d records", len(licitacoes))
    except Exception as exc:
        _logger.error("[TCE-SC] Failed to fetch licitações: %s", exc)

    # Rate limit entre chamadas
    if all_records:
        time.sleep(DEFAULT_DELAY_SECONDS)

    # Fase 2: Contratos
    try:
        contratos = _fetch_contratos(data_inicial=data_inicial, data_final=data_final)
        for rec in contratos:
            rec["_tipo"] = "contrato"
        all_records.extend(contratos)
        _logger.info("[TCE-SC] Contratos: %d records", len(contratos))
    except Exception as exc:
        _logger.error("[TCE-SC] Failed to fetch contratos: %s", exc)

    _logger.info("[TCE-SC] Crawl complete: %d total records", len(all_records))
    return all_records


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------


def _generate_content_hash(record: dict) -> str:
    """Deterministic MD5 hash for dedup.

    Uses key fields: orgao_cnpj, numero, data_publicacao.
    """
    key_fields = [
        str(record.get("orgao_cnpj", "")),
        str(record.get("pncp_id", "")),
        str(record.get("objeto_compra", "")),
        str(record.get("data_publicacao", "")),
        str(record.get("valor_total_estimado", "")),
    ]
    key_str = "|".join(key_fields)
    return hashlib.md5(key_str.encode("utf-8"), usedforsecurity=False).hexdigest()


def _transform_licitacao(raw: dict) -> dict | None:
    """Transform a single SCMWeb licitacao record into pncp_raw_bids schema."""
    try:
        numero = str(raw.get("Numero") or "").strip()
        if not numero:
            return None

        modalidade_raw = str(raw.get("Modalidade") or "").strip()
        modalidade_id, modalidade_nome = _map_modalidade(modalidade_raw)
        objeto = str(raw.get("Objeto") or "").strip()
        data_abertura = _parse_date(raw.get("Data_Abertura"))
        valor = _safe_float(raw.get("Valor_Estimado"))
        situacao = _normalize_situacao(str(raw.get("Status") or ""))

        ano = raw.get("Ano", "")
        pncp_id = f"tce_sc_lic_{numero}_{ano}"

        data_publicacao = data_abertura  # Data_Abertura serves as publicacao

        orgao_nome = str(raw.get("Orgao", raw.get("orgao", ""))).strip()
        orgao_cnpj = _digits_only(str(raw.get("CNPJ_Orgao", raw.get("cnpj_orgao", ""))))

        # Extract municipio from API response when available; fall back to
        # Florianopolis (TCE-SC headquarters) only when the field is absent.
        raw_municipio = str(raw.get("Municipio", raw.get("municipio", ""))).strip()
        raw_ibge = str(raw.get("Codigo_IBGE", raw.get("codigo_ibge", ""))).strip()
        municipio = raw_municipio if raw_municipio else "Florianopolis"
        codigo_municipio_ibge = raw_ibge if raw_ibge else "4205407"

        record = {
            "pncp_id": pncp_id,
            "objeto_compra": objeto,
            "valor_total_estimado": valor,
            "modalidade_id": modalidade_id,
            "modalidade_nome": modalidade_nome,
            "situacao_compra": situacao,
            "esfera_id": 2,  # Estadual (TCE-SC)
            "uf": "SC",
            "municipio": municipio,
            "codigo_municipio_ibge": codigo_municipio_ibge,
            "orgao_razao_social": orgao_nome or "TCE-SC",
            "orgao_cnpj": orgao_cnpj or "",
            "data_publicacao": data_publicacao or "",
            "data_abertura": data_abertura or "",
            "data_encerramento": None,
            "link_sistema_origem": (
                "https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285&page=licitacoes"
            ),
            "link_pncp": "",
            "content_hash": "",
            "source_id": pncp_id,
        }
        record["content_hash"] = _generate_content_hash(record)
        return record

    except Exception as exc:
        _logger.warning("[TCE-SC] Transform licitacao error: %s: %s", type(exc).__name__, exc)
        return None


def _transform_contrato(raw: dict) -> dict | None:
    """Transform a single SCMWeb contrato record into pncp_raw_bids schema."""
    try:
        numero = str(raw.get("Numero") or "").strip()
        if not numero:
            return None

        contratado = str(raw.get("Contratado") or "").strip()
        cnpj = _digits_only(str(raw.get("CNPJ") or ""))
        objeto = str(raw.get("Objeto") or "").strip()
        valor = _safe_float(raw.get("Valor"))
        situacao = _normalize_situacao(str(raw.get("Status") or ""))

        # Contratos nao tem data de abertura explicita no schema do SCMWeb
        # Usar data de publicacao se disponivel
        data_pub = _parse_date(raw.get("Data_Publicacao", raw.get("data_publicacao")))
        pncp_id = f"tce_sc_ctr_{numero}"

        orgao_nome = str(raw.get("Orgao", raw.get("orgao", ""))).strip()

        # Extract municipio from API response when available
        raw_municipio = str(raw.get("Municipio", raw.get("municipio", ""))).strip()
        raw_ibge = str(raw.get("Codigo_IBGE", raw.get("codigo_ibge", ""))).strip()
        municipio = raw_municipio if raw_municipio else "Florianopolis"
        codigo_municipio_ibge = raw_ibge if raw_ibge else "4205407"

        record = {
            "pncp_id": pncp_id,
            "objeto_compra": objeto or f"Contrato - {contratado}" if contratado else "Contrato",
            "valor_total_estimado": valor,
            "modalidade_id": 0,
            "modalidade_nome": "Contrato",
            "situacao_compra": situacao,
            "esfera_id": 2,  # Estadual
            "uf": "SC",
            "municipio": municipio,
            "codigo_municipio_ibge": codigo_municipio_ibge,
            "orgao_razao_social": orgao_nome or "TCE-SC",
            "orgao_cnpj": cnpj or "",
            "data_publicacao": data_pub or "",
            "data_abertura": None,
            "data_encerramento": None,
            "link_sistema_origem": (
                "https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285&page=contratos"
            ),
            "link_pncp": "",
            "content_hash": "",
            "source_id": pncp_id,
        }
        record["content_hash"] = _generate_content_hash(record)
        return record

    except Exception as exc:
        _logger.warning("[TCE-SC] Transform contrato error: %s: %s", type(exc).__name__, exc)
        return None


def transform(records: list[dict]) -> list[dict]:
    """Transform raw SCMWeb records to unified pncp_raw_bids schema.

    O campo ``_tipo`` (adicionado pelo crawl) determina se o registro
    e uma licitacao ou contrato, aplicando o transformer adequado.

    Args:
        records: Lista de registros brutos de crawl().

    Returns:
        Lista de dicts normalizados para o schema pncp_raw_bids.
    """
    transformed: list[dict] = []
    skipped = 0

    for rec in records:
        tipo = rec.pop("_tipo", "licitacao")

        if tipo == "contrato":
            t = _transform_contrato(rec)
        else:
            t = _transform_licitacao(rec)

        if t and t.get("pncp_id"):
            transformed.append(t)
        else:
            skipped += 1

    if skipped:
        _logger.info("[TCE-SC] Transform complete: %d records, %d skipped", len(transformed), skipped)
    else:
        _logger.info("[TCE-SC] Transform complete: %d records", len(transformed))

    return transformed


# ---------------------------------------------------------------------------
# Filtro por municipio / unidade gestora
# ---------------------------------------------------------------------------


def crawl_by_municipio(
    codigo_ibge: str,
    data_inicial: date | None = None,
    data_final: date | None = None,
) -> list[dict]:
    """Crawl SCMWeb filtrando por municipio (codigo IBGE).

    Nota: Esta funcao requer que o SCMWeb aceite ``cod_ibge`` ou
    ``unidade_gestora`` como parametro de filtro. O comportamento
    exato depende da implementacao do SCMWeb.

    Args:
        codigo_ibge: Codigo IBGE de 7 digitos do municipio (ex: 4205407).
        data_inicial: Data inicial do filtro.
        data_final: Data final do filtro.

    Returns:
        Lista de registros brutos filtrados por municipio.
    """
    _logger.info("[TCE-SC] Crawling by municipio: IBGE=%s", codigo_ibge)

    # Tentar primeiro com unidade_gestora (se aceito pela API)
    records: list[dict] = []

    try:
        licitacoes = _fetch_licitacoes(
            data_inicial=data_inicial,
            data_final=data_final,
            unidade_gestora=codigo_ibge,
        )
        for rec in licitacoes:
            rec["_tipo"] = "licitacao"
        records.extend(licitacoes)
    except Exception as exc:
        _logger.warning("[TCE-SC] Municipio filter failed for licitacoes: %s", exc)

    time.sleep(DEFAULT_DELAY_SECONDS)

    try:
        contratos = _fetch_contratos(
            data_inicial=data_inicial,
            data_final=data_final,
            unidade_gestora=codigo_ibge,
        )
        for rec in contratos:
            rec["_tipo"] = "contrato"
        records.extend(contratos)
    except Exception as exc:
        _logger.warning("[TCE-SC] Municipio filter failed for contratos: %s", exc)

    return records


def crawl_by_year(ano: int) -> list[dict]:
    """Crawl SCMWeb filtrando por ano.

    Args:
        ano: Ano para filtro (ex: 2026).

    Returns:
        Lista de registros brutos filtrados por ano.
    """
    _logger.info("[TCE-SC] Crawling by year: %d", ano)

    records: list[dict] = []

    try:
        licitacoes = _fetch_licitacoes(ano=ano)
        for rec in licitacoes:
            rec["_tipo"] = "licitacao"
        records.extend(licitacoes)
    except Exception as exc:
        _logger.warning("[TCE-SC] Year filter failed for licitacoes: %s", exc)

    time.sleep(DEFAULT_DELAY_SECONDS)

    try:
        contratos = _fetch_contratos(ano=ano)
        for rec in contratos:
            rec["_tipo"] = "contrato"
        records.extend(contratos)
    except Exception as exc:
        _logger.warning("[TCE-SC] Year filter failed for contratos: %s", exc)

    return records
