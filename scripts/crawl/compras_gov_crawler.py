"""ComprasGov v3 crawler adapter — Extra Consultoria.

Sync adapter for the ComprasGov v3 open data API (dadosabertos.compras.gov.br).

Interface esperada pelo monitor.py:
    crawl(mode) -> list[dict]       # raw records da API
    transform(records) -> list[dict]  # normalizados para pncp_raw_bids schema

Estrategia de dois endpoints:
  - Legado (/modulo-legado/1_consultarLicitacao): pre-2024, filtra UF server-side
  - Lei 14.133 (/modulo-contratacoes/1_consultarContratacoes_PNCP_14133): pos-2024,
    UF filtering client-side (API nao suporta filtro)

Sem async, sem httpx, sem clients.base. Apenas urllib da stdlib.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.common import (
    generate_content_hash as _common_content_hash,
)
from scripts.crawl.security import USER_AGENT, sanitize_url_param

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env overridable)
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("COMPRASGOV_BASE", "https://dadosabertos.compras.gov.br")
PAGE_SIZE = int(os.getenv("COMPRASGOV_PAGE_SIZE", "500"))
MAX_PAGES = int(os.getenv("COMPRASGOV_MAX_PAGES", "50"))
READ_TIMEOUT = int(os.getenv("COMPRASGOV_READ_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("COMPRASGOV_MAX_RETRIES", "2"))
REQUEST_DELAY = float(os.getenv("COMPRASGOV_REQUEST_DELAY", "0.2"))  # 200ms = 5 req/s

INGESTION_UFS = [u.strip().upper() for u in os.getenv("INGESTION_UFS", "SC").split(",") if u.strip()]
INGESTION_DATE_RANGE_DAYS = int(os.getenv("INGESTION_DATE_RANGE_DAYS", "3"))
INGESTION_INCREMENTAL_DAYS = int(os.getenv("INGESTION_INCREMENTAL_DAYS", "1"))

# API endpoints
LEGACY_ENDPOINT = "/modulo-legado/1_consultarLicitacao"
LEI_14133_ENDPOINT = "/modulo-contratacoes/1_consultarContratacoes_PNCP_14133"

# Modalidade name -> ID mapping (baseado na nomenclatura PNCP/ComprasGov)
_MODALIDADE_ID_MAP: dict[str, int] = {
    "Pregão": 1,
    "Pregao": 1,
    "Concorrência": 3,
    "Concorrencia": 3,
    "Concurso": 4,
    "Leilão": 5,
    "Leilao": 5,
    "Tomada de Preços": 6,
    "Tomada de Precos": 6,
    "Diálogo Competitivo": 7,
    "Dialogo Competitivo": 7,
    "Credenciamento": 8,
    "Pré-qualificação": 9,
    "Pre-qualificacao": 9,
    "Dispensa de Licitação": 10,
    "Dispensa de Licitacao": 10,
    "Inexigibilidade": 11,
    "Inexigibilidade de Licitação": 11,
    "Inexigibilidade de Licitacao": 11,
    "Convite": 12,
}

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _make_request(url: str) -> dict | None:
    """Sync HTTP GET via urllib com retry logic.

    Args:
        url: URL completa para request

    Returns:
        Dict parsed do JSON, ou None em erro nao-recuperavel
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")[:200]
            except Exception:
                pass

            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 60))
                _logger.warning(f"[COMPRAS_GOV] Rate limited. Waiting {retry_after}s")
                time.sleep(retry_after)
                continue

            if e.code in (404, 400):
                _logger.debug(f"[COMPRAS_GOV] HTTP {e.code} for {url}: {err_body}")
                return None

            if e.code >= 500 and attempt < MAX_RETRIES:
                delay = 2.0 * (2**attempt)
                _logger.warning(f"[COMPRAS_GOV] Server error {e.code}. Retrying in {delay:.1f}s")
                time.sleep(delay)
                continue

            _logger.warning(f"[COMPRAS_GOV] HTTP {e.code} after {MAX_RETRIES} retries: {url}")
            return None

        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                delay = 1.0 + attempt * 2.0
                _logger.warning(f"[COMPRAS_GOV] Connection error: {e}. Retrying in {delay:.1f}s")
                time.sleep(delay)
                continue
            _logger.warning(f"[COMPRAS_GOV] Connection failed after {MAX_RETRIES} retries: {e}")
            return None

        except Exception as e:
            if attempt < MAX_RETRIES:
                _logger.debug(f"[COMPRAS_GOV] Request error (attempt {attempt + 1}): {e}")
                time.sleep(1.0 + attempt)
                continue
            _logger.warning(f"[COMPRAS_GOV] Request failed after {MAX_RETRIES} retries: {e}")
            return None

    return None


def _fetch_page(endpoint: str, params: dict) -> tuple[list[dict], bool]:
    """Busca uma pagina de um endpoint ComprasGov.

    Args:
        endpoint: Caminho da API (ex: /modulo-legado/1_consultarLicitacao)
        params: Dicionario de parametros de query

    Returns:
        (records_list, has_more_pages)
    """
    query = "&".join(f"{k}={sanitize_url_param(v)}" for k, v in params.items())
    url = f"{BASE_URL}{endpoint}?{query}"

    data = _make_request(url)
    if data is None:
        return [], False

    records = data.get("data", [])
    if not isinstance(records, list):
        return [], False

    # Resposta inclui paginasRestantes para controle de paginacao
    paginas_restantes = data.get("paginasRestantes", 0)
    has_more = paginas_restantes > 0

    return records, has_more


def _fetch_from_endpoint(
    endpoint: str,
    data_inicial: str,
    data_final: str,
    uf: str | None = None,
    max_pages: int | None = None,
) -> list[dict]:
    """Fetch paginado de um endpoint.

    Args:
        endpoint: Caminho da API
        data_inicial: Data inicio YYYY-MM-DD
        data_final: Data fim YYYY-MM-DD
        uf: Codigo UF (opcional, server-side filter no legado)
        max_pages: Paginas maximas (default: MAX_PAGES global)

    Returns:
        Lista de registros brutos da API
    """
    if max_pages is None:
        max_pages = MAX_PAGES

    all_records: list[dict] = []
    pagina = 1

    while pagina <= max_pages:
        params: dict[str, Any] = {
            "data_publicacao_inicial": data_inicial,
            "data_publicacao_final": data_final,
            "pagina": pagina,
            "tamanhoPagina": PAGE_SIZE,
        }
        if uf:
            params["uf"] = uf

        records, has_more = _fetch_page(endpoint, params)

        if not records:
            if pagina == 1:
                _logger.debug(f"[COMPRAS_GOV] {endpoint}: sem resultados pagina 1")
            break

        all_records.extend(records)

        if not has_more:
            break

        if pagina >= max_pages:
            _logger.warning(f"[COMPRAS_GOV] {endpoint}: atingiu max_pages ({max_pages})")
            break

        pagina += 1
        time.sleep(REQUEST_DELAY)  # Rate limiting

    if all_records:
        _logger.info(
            f"[COMPRAS_GOV] {endpoint}{' (' + uf + ')' if uf else ''}: {len(all_records)} registros ({pagina} paginas)"
        )

    return all_records


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _extract_date(value: Any) -> str | None:
    """Converte valor de data da API para string YYYY-MM-DD.

    Lida com datetime objects, timestamps (ms) e strings em varios formatos.
    """
    if not value:
        return None

    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]

    if isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(value / 1000)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None

    if isinstance(value, str):
        # Normaliza timezone suffix para parsing
        cleaned = value.replace("+00:00", "Z").replace("+0000", "Z").rstrip("Z")

        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

    return None


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------


def _generate_content_hash(record: dict) -> str:
    """Hash MD5 deterministico para dedup (delegates to common)."""
    return _common_content_hash(
        record, fields=["orgao_cnpj", "objeto_compra", "data_publicacao", "valor_total_estimado"]
    )


# ---------------------------------------------------------------------------
# Modalidade mapping
# ---------------------------------------------------------------------------


def _modalidade_id(nome: str) -> int:
    """Mapeia nome da modalidade para ID numerico."""
    if not nome:
        return 0
    return _MODALIDADE_ID_MAP.get(nome.strip(), 0)


# ---------------------------------------------------------------------------
# Normalization: Legacy endpoint (pre-2024)
# ---------------------------------------------------------------------------


def _normalize_legacy(raw: dict) -> dict | None:
    """Normaliza registro do endpoint legado para schema pncp_raw_bids.

    Legacy field mapping:
      - numero_aviso / identificador / id -> pncp_id (prefixo cg_leg_)
      - objeto / descricao -> objeto_compra
      - valor_estimado / valor -> valor_total_estimado
      - uasg.nome / orgao_nome -> orgao_razao_social
      - uasg.cnpj / cnpj -> orgao_cnpj
      - uf -> uf
      - municipio -> municipio
      - modalidade.descricao -> modalidade_nome
      - data_publicacao -> data_publicacao
      - data_entrega_proposta -> data_abertura
    """
    try:
        source_id = str(raw.get("numero_aviso") or raw.get("identificador") or raw.get("id") or "")
        if not source_id:
            return None

        pncp_id = f"cg_leg_{source_id}"

        # Objeto
        objeto_compra = raw.get("objeto") or raw.get("descricao") or ""

        # Valor
        valor = raw.get("valor_estimado") or raw.get("valor") or 0
        if isinstance(valor, str):
            try:
                valor = float(valor.replace(".", "").replace(",", "."))
            except ValueError:
                valor = 0.0
        valor_float = float(valor) if valor else None
        if valor_float == 0:
            valor_float = None

        # Orgao
        uasg = raw.get("uasg") or {}
        if isinstance(uasg, dict):
            orgao_razao_social = uasg.get("nome") or raw.get("orgao_nome") or ""
            orgao_cnpj = uasg.get("cnpj") or raw.get("cnpj") or ""
        else:
            orgao_razao_social = raw.get("orgao_nome") or ""
            orgao_cnpj = raw.get("cnpj") or ""

        # Localizacao
        uf = raw.get("uf") or "SC"
        municipio = raw.get("municipio") or ""

        # Modalidade
        modalidade_obj = raw.get("modalidade") or {}
        if isinstance(modalidade_obj, dict):
            modalidade_nome = modalidade_obj.get("descricao") or ""
        else:
            modalidade_nome = str(modalidade_obj) if modalidade_obj else ""

        # Datas
        data_publicacao = _extract_date(raw.get("data_publicacao"))
        data_abertura = _extract_date(raw.get("data_entrega_proposta"))

        # Link
        link_pncp = raw.get("link") or ""
        if not link_pncp and source_id:
            link_pncp = f"{BASE_URL}/modulo-legado/licitacao/{source_id}"

        result = {
            "pncp_id": pncp_id,
            "objeto_compra": objeto_compra,
            "valor_total_estimado": valor_float,
            "modalidade_id": _modalidade_id(modalidade_nome),
            "modalidade_nome": modalidade_nome,
            "esfera_id": 1,  # Federal
            "uf": uf,
            "municipio": municipio,
            "codigo_municipio_ibge": raw.get("codigo_municipio_ibge", ""),
            "orgao_razao_social": orgao_razao_social,
            "orgao_cnpj": orgao_cnpj,
            "data_publicacao": data_publicacao,
            "data_abertura": data_abertura,
            "data_encerramento": None,
            "link_pncp": link_pncp,
            "source_id": f"cg_leg_{source_id}",
        }

        result["content_hash"] = _generate_content_hash(result)
        return result

    except Exception as e:
        _logger.warning(f"[COMPRAS_GOV] Legacy normalization error: {e}")
        return None


# ---------------------------------------------------------------------------
# Normalization: Lei 14.133 endpoint (pos-2024)
# ---------------------------------------------------------------------------


def _normalize_lei_14133(raw: dict) -> dict | None:
    """Normaliza registro do endpoint Lei 14.133 para schema pncp_raw_bids.

    Lei 14.133 field mapping:
      - numeroControlePNCP / id -> pncp_id (prefixo cg_14133_)
      - objetoCompra -> objeto_compra
      - valorTotalEstimado / valorEstimado -> valor_total_estimado
      - orgaoEntidade.razaoSocial -> orgao_razao_social
      - orgaoEntidade.cnpj -> orgao_cnpj
      - orgaoEntidade.municipio -> municipio
      - uf -> uf
      - modalidadeNome -> modalidade_nome
      - dataPublicacaoPncp -> data_publicacao
      - dataAberturaProposta -> data_abertura
      - dataEncerramentoProposta -> data_encerramento
    """
    try:
        source_id = str(raw.get("numeroControlePNCP") or raw.get("id") or "")
        if not source_id:
            return None

        pncp_id = f"cg_14133_{source_id}"

        # Objeto
        objeto_compra = raw.get("objetoCompra") or ""

        # Valor
        valor = raw.get("valorTotalEstimado") or raw.get("valorEstimado") or 0
        if isinstance(valor, str):
            try:
                valor = float(valor)
            except ValueError:
                valor = 0.0
        valor_float = float(valor) if valor else None
        if valor_float == 0:
            valor_float = None

        # Orgao
        orgao_obj = raw.get("orgaoEntidade") or {}
        if isinstance(orgao_obj, dict):
            orgao_razao_social = orgao_obj.get("razaoSocial") or ""
            orgao_cnpj = orgao_obj.get("cnpj") or ""
            municipio = orgao_obj.get("municipio") or ""
            codigo_ibge = orgao_obj.get("codigoIbge") or ""
        else:
            orgao_razao_social = ""
            orgao_cnpj = ""
            municipio = ""
            codigo_ibge = ""

        # Localizacao
        uf = raw.get("uf") or "SC"

        # Modalidade
        modalidade_nome = raw.get("modalidadeNome") or ""

        # Datas
        data_publicacao = _extract_date(raw.get("dataPublicacaoPncp"))
        data_abertura = _extract_date(raw.get("dataAberturaProposta"))
        data_encerramento = _extract_date(raw.get("dataEncerramentoProposta"))

        # Link
        link_pncp = raw.get("url") or raw.get("link") or ""
        if not link_pncp and source_id:
            link_pncp = f"https://pncp.gov.br/app/editais/{source_id}"

        result = {
            "pncp_id": pncp_id,
            "objeto_compra": objeto_compra,
            "valor_total_estimado": valor_float,
            "modalidade_id": _modalidade_id(modalidade_nome),
            "modalidade_nome": modalidade_nome,
            "esfera_id": 1,  # Federal
            "uf": uf,
            "municipio": municipio,
            "codigo_municipio_ibge": str(codigo_ibge) if codigo_ibge else "",
            "orgao_razao_social": orgao_razao_social,
            "orgao_cnpj": orgao_cnpj,
            "data_publicacao": data_publicacao,
            "data_abertura": data_abertura,
            "data_encerramento": data_encerramento,
            "link_pncp": link_pncp,
            "source_id": f"cg_14133_{source_id}",
        }

        result["content_hash"] = _generate_content_hash(result)
        return result

    except Exception as e:
        _logger.warning(f"[COMPRAS_GOV] Lei 14.133 normalization error: {e}")
        return None


# ---------------------------------------------------------------------------
# Public interface (chamado pelo monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl ComprasGov v3 para as UFs configuradas.

    Consulta ambos os endpoints em sequencia:
      1. Legado: filtra UF server-side (1 request stream por UF)
      2. Lei 14.133: filtra UF client-side (fetch all, filtra pos)

    Os registros sao retornados crus (raw) como vieram da API.
    O transform() detecta automaticamente qual endpoint gerou cada um.

    Args:
        mode: 'full' (janela maior) ou 'incremental' (janela menor)

    Returns:
        Lista de registros brutos da API (ambos endpoints mergeados)
    """
    days = INGESTION_DATE_RANGE_DAYS if mode == "full" else INGESTION_INCREMENTAL_DAYS
    data_final = date.today()
    data_inicial = data_final - timedelta(days=days)
    data_inicial_str = data_inicial.isoformat()
    data_final_str = data_final.isoformat()

    _logger.info(f"[COMPRAS_GOV] Crawl {mode}: {data_inicial_str} a {data_final_str} UFs={INGESTION_UFS}")

    all_records: list[dict] = []

    # 1. Legacy endpoint (server-side UF filter)
    for uf in INGESTION_UFS:
        records = _fetch_from_endpoint(LEGACY_ENDPOINT, data_inicial_str, data_final_str, uf=uf)
        all_records.extend(records)

    # 2. Lei 14.133 endpoint (client-side UF filter)
    lei_records = _fetch_from_endpoint(LEI_14133_ENDPOINT, data_inicial_str, data_final_str, uf=None)
    for r in lei_records:
        raw_uf = (r.get("uf") or "").upper()
        if raw_uf in INGESTION_UFS:
            all_records.append(r)

    _logger.info(f"[COMPRAS_GOV] Crawl complete: {len(all_records)} registros totais")
    return all_records


def transform(raw_records: list[dict]) -> list[dict]:
    """Transforma registros brutos do ComprasGov para schema pncp_raw_bids.

    Auto-detecção de endpoint: se o registro tem campos camelCase
    (numeroControlePNCP, objetoCompra) e do Lei 14.133, caso contrario
    do legado.

    Dedup: registros com mesmo pncp_id sao deduplicados (mantem o primeiro).

    Args:
        raw_records: Registros crus retornados por crawl()

    Returns:
        Registros normalizados no schema pncp_raw_bids
    """
    normalized: list[dict] = []
    seen_ids: set[str] = set()

    for raw in raw_records:
        # Auto-detecção do tipo de endpoint
        if "numeroControlePNCP" in raw or "objetoCompra" in raw:
            result = _normalize_lei_14133(raw)
        else:
            result = _normalize_legacy(raw)

        if result is None:
            continue

        # Filtro: requer CNPJ do orgao minimamente
        if not result.get("orgao_cnpj"):
            continue

        # Dedup por pncp_id
        pid = result["pncp_id"]
        if pid in seen_ids:
            continue
        seen_ids.add(pid)

        normalized.append(result)

    return normalized
