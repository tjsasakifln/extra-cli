"""Crawler sync adapter for Portal de Compras SC (compras.sc.gov.br).

Adapted from legacy async/httpx/class-based crawler to the simple sync interface
expected by monitor.py: crawl(mode) -> list[dict], transform(records) -> list[dict].

Uses the JSON API (SPA React backend) at /api/editais.

API behaviour (probed live 2026-07):
  - ``GET /api/editais?ano=YYYY`` returns the full year bulk in ``conteudo``
    (server-side page size / pagina params are ignored; metadata still reports
    totalElementos / totalPaginas / porPagina≈10).
  - Client-side virtual pages of size ``PAGE_SIZE`` (default 10) slice the bulk.
  - ``GET /api/editais/{id}`` returns detail (datas, modalidade, linkArquivosFTP…).
  - No valor estimado field is exposed by the public API.
  - Filters situacao/modalidade/date query params return HTTP 400 or are ignored.

Modes:
  - smoke: 1–2 virtual pages, list-only (or limited detail), terminal artifact
  - incremental: since checkpoint (last_max_id) or last N days; checkpoint+run_id
  - full: year bulk bounded by max pages of detail enrichment

Stdlib only for HTTP; uses scripts.crawl.run_evidence for run_id/evidence.
"""

from __future__ import annotations

import argparse
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
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path for standalone usage
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.run_evidence import (  # noqa: E402
    bind_checkpoint_run_id,
    build_run_evidence,
    new_run_id,
    sha256_file,
    sha256_json,
)
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
PAGE_SIZE = int(os.getenv("SC_COMPRAS_PAGE_SIZE", "10"))  # client-side virtual page

SC_COMPRAS_FULL_DAYS = int(os.getenv("SC_COMPRAS_FULL_DAYS", "30"))
SC_COMPRAS_INCREMENTAL_DAYS = int(os.getenv("SC_COMPRAS_INCREMENTAL_DAYS", "3"))
SC_COMPRAS_SMOKE_PAGES = int(os.getenv("SC_COMPRAS_SMOKE_PAGES", "2"))

CHECKPOINT_DIR = Path(
    os.getenv(
        "SC_COMPRAS_CHECKPOINT_DIR",
        str(_PROJECT_ROOT / "data" / "sc_compras_checkpoints"),
    )
)
RAW_DIR = Path(
    os.getenv(
        "SC_COMPRAS_RAW_DIR",
        str(_PROJECT_ROOT / "data" / "raw" / "sc_compras"),
    )
)
OUTPUT_DIR = Path(
    os.getenv(
        "SC_COMPRAS_OUTPUT_DIR",
        str(_PROJECT_ROOT / "output" / "sc_compras"),
    )
)

# Fields considered for incompleteness / empty metrics on normalized records
_REQUIRED_FIELDS = ("pncp_id", "objeto_compra", "orgao_razao_social", "data_publicacao")
_TRACKED_EMPTY_FIELDS = (
    "objeto_compra",
    "orgao_razao_social",
    "data_publicacao",
    "data_abertura",
    "data_encerramento",
    "valor_total_estimado",
    "modalidade_nome",
    "municipio",
    "orgao_cnpj",
    "link_pncp",
    "status",
    "documentos",
)

# ---------------------------------------------------------------------------
# Modalidade mapping
# ---------------------------------------------------------------------------

_MODALIDADE_MAP: dict[str, int] = {
    "pregao": 5,
    "pregao eletronico": 5,
    "pregao presencial": 6,
    "concorrencia": 4,
    "concorrencia eletronica": 4,
    "concorrencia presencial": 4,
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
    """Parse DD/MM/YYYY or ISO datetime to YYYY-MM-DD. Returns None if unparseable."""
    if not s or not str(s).strip():
        return None
    s = str(s).strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return None


def _parse_br_number(s: str | None) -> float | None:
    """Parse Brazilian-formatted number (e.g. '1.500,00' or '150000')."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    if not str(s).strip():
        return None
    text = str(s).strip().replace("R$", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        if text.rindex(",") > text.rindex("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _content_hash(*parts: str) -> str:
    """Deterministic MD5 hash of joined parts for dedup."""
    raw = "|".join(parts)
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    numero = merged.get("edital") or merged.get("processo") or ""
    url_detalhe = f"{BASE_URL}/editais/{merged.get('id', '')}" if merged.get("id") else None

    # Documentos: API exposes FTP link (if any), not a file list
    documentos: list[dict[str, Any]] = []
    ftp = merged.get("linkArquivosFTP")
    if ftp:
        documentos.append({"tipo": "ftp", "url": ftp})

    canonical = {
        "numero_processo": str(numero).strip(),
        "api_id": merged.get("id"),
        "modalidade": merged.get("modalidade") or merged.get("tipo") or "",
        "objeto": (merged.get("objeto") or "").strip()
        if isinstance(merged.get("objeto"), str)
        else (merged.get("objeto") or ""),
        "orgao": (merged.get("orgaoNome") or "").strip()
        if isinstance(merged.get("orgaoNome"), str)
        else (merged.get("orgaoNome") or ""),
        "orgao_sigla": (merged.get("orgaoSigla") or "").strip()
        if isinstance(merged.get("orgaoSigla"), str)
        else (merged.get("orgaoSigla") or ""),
        "data_publicacao": (merged.get("dataPublicacao") or "").strip()
        if isinstance(merged.get("dataPublicacao"), str)
        else (merged.get("dataPublicacao") or ""),
        "data_abertura": merged.get("dataAbertura") or merged.get("abertura") or merged.get("entregaProposta") or "",
        "data_encerramento": merged.get("dataEncerramento") or "",
        "situacao": (merged.get("situacao") or "").strip()
        if isinstance(merged.get("situacao"), str)
        else (merged.get("situacao") or ""),
        "tipo_situacao": merged.get("tipoSituacao") or "",
        "natureza": merged.get("natureza") or "",
        "url_detalhe": url_detalhe,
        "documentos": documentos,
        "origem": merged.get("origem") or "",
        # Not available from public API:
        "orgao_cnpj": "",
        "municipio": "",
        "uf": "SC",
        "valor": None,
    }

    return canonical


# ---------------------------------------------------------------------------
# API request helpers (JSON API, no HTML scraping)
# ---------------------------------------------------------------------------


def _api_request(url: str) -> dict | None:
    """Make a GET request to the SC Compras JSON API. Returns parsed dict or None.

    Retries on HTTP 429 / 5xx / network errors with exponential backoff.
    """
    last_error: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            validate_url_scheme(url)
            req = urllib.request.Request(url)  # noqa: S310 — validated above
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", USER_AGENT)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
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
            last_error = f"HTTP {e.code}"
            # Retryable: rate limit and server errors
            if e.code in (429, 500, 502, 503, 504):
                backoff = 2.0 * attempt
                if e.code == 429:
                    # Honour Retry-After when present
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    try:
                        backoff = max(backoff, float(retry_after)) if retry_after else backoff * 2
                    except (TypeError, ValueError):
                        backoff = backoff * 2
                _logger.warning(
                    "[ScCompras] HTTP %d for %s (attempt %d/%d) — retry in %.1fs",
                    e.code,
                    url,
                    attempt,
                    MAX_RETRIES,
                    backoff if attempt < MAX_RETRIES else 0,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(backoff)
                    continue
            else:
                _logger.warning(
                    "[ScCompras] HTTP %d for %s (attempt %d/%d): %s",
                    e.code,
                    url,
                    attempt,
                    MAX_RETRIES,
                    e,
                )
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


def _fetch_api_list_meta(ano: int) -> tuple[list[dict], dict[str, Any]]:
    """Fetch year bulk from /api/editais and return (items, meta).

    The backend currently ignores server-side pagination and returns the full
    year set. Meta still exposes totalElementos / totalPaginas when present.
    """
    params = {"ano": str(ano), "tamanhoPagina": str(max(PAGE_SIZE, 3000))}
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{BASE_URL}/api/editais?{query}"

    data = _api_request(full_url)
    if not data:
        return [], {
            "ano": ano,
            "url": full_url,
            "total_elementos": 0,
            "total_paginas": 0,
            "por_pagina": PAGE_SIZE,
            "pagina": 0,
            "ok": False,
        }

    items = data.get("conteudo") or []
    if not isinstance(items, list):
        items = []

    meta = {
        "ano": ano,
        "url": full_url,
        "total_elementos": data.get("totalElementos", len(items)),
        "total_paginas": data.get("totalPaginas"),
        "por_pagina": data.get("porPagina") or PAGE_SIZE,
        "pagina": data.get("pagina", 0),
        "ok": True,
        "items_returned": len(items),
    }
    _logger.debug(
        "[ScCompras] API list: ano=%d -> %d items (totalElementos=%s)",
        ano,
        len(items),
        meta["total_elementos"],
    )
    return items, meta


def _fetch_api_list(ano: int) -> list[dict]:
    """Fetch all items from /api/editais for a given year (list only)."""
    items, _meta = _fetch_api_list_meta(ano)
    return items


def _fetch_api_detail(item_id: int) -> dict | None:
    """Fetch /api/editais/{id} detail for a single edital."""
    return _api_request(f"{BASE_URL}/api/editais/{item_id}")


def _virtual_pages(items: list[dict], page_size: int | None = None) -> list[list[dict]]:
    """Slice a bulk list into client-side virtual pages."""
    size = page_size or PAGE_SIZE
    if size <= 0:
        size = 10
    if not items:
        return []
    return [items[i : i + size] for i in range(0, len(items), size)]


def _page_slice(items: list[dict], page: int, page_size: int | None = None) -> list[dict]:
    """Return 0-based virtual page from bulk list (empty if out of range)."""
    size = page_size or PAGE_SIZE
    if size <= 0:
        size = 10
    start = page * size
    if start < 0 or start >= len(items):
        return []
    return items[start : start + size]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize_item(raw: dict) -> dict | None:
    """Normalize a raw SC portal item to pncp_raw_bids-compatible schema.

    Does NOT include 'source' — monitor.py adds it.
    """
    numero = (raw.get("numero_processo") or "").strip()
    api_id = raw.get("api_id")
    if not numero and api_id is None:
        return None
    if not numero:
        numero = str(api_id)

    if api_id is not None:
        pncp_id = f"sc-{api_id}"
        source_id = pncp_id
    else:
        pncp_id = f"sc-{numero}"
        source_id = pncp_id

    objeto = (raw.get("objeto") or "").strip()
    if len(objeto) > 1000:
        objeto = objeto[:997] + "..."

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
    esfera = _ESFERA_LETTER_TO_ID.get(esfera_letter, "2")

    content_hash = _content_hash(pncp_id, data_publicacao, objeto)
    status = (raw.get("situacao") or "").strip() or None
    documentos = raw.get("documentos") if isinstance(raw.get("documentos"), list) else []

    uf = (raw.get("uf") or "SC").strip().upper() or "SC"

    return {
        "pncp_id": pncp_id,
        "objeto_compra": objeto or None,
        "valor_total_estimado": round(valor, 2) if valor is not None else None,
        "modalidade_id": modalidade_id,
        "modalidade_nome": modalidade_nome or None,
        "esfera_id": esfera,
        "uf": uf,
        "municipio": municipio or None,
        "codigo_municipio_ibge": None,
        "orgao_razao_social": orgao or None,
        "orgao_cnpj": orgao_cnpj or None,
        "data_publicacao": data_publicacao,
        "data_abertura": data_abertura or None,
        "data_encerramento": data_encerramento or None,
        "link_pncp": url_detalhe or None,
        "content_hash": content_hash,
        "source_id": source_id,
        "status": status,
        "documentos": documentos,
        "api_id": api_id,
    }


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


@dataclass
class ScComprasCheckpoint:
    """File-based checkpoint for incremental SC Compras crawls."""

    source: str = "sc_compras"
    mode: str = "incremental"
    last_max_id: int | None = None
    last_seen_ids: list[int] = field(default_factory=list)
    last_year: int | None = None
    pages_completed: int = 0
    total_fetched: int = 0
    last_error: str | None = None
    updated_at: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScComprasCheckpoint:
        return cls(
            source=d.get("source", "sc_compras"),
            mode=d.get("mode", "incremental"),
            last_max_id=d.get("last_max_id"),
            last_seen_ids=list(d.get("last_seen_ids") or []),
            last_year=d.get("last_year"),
            pages_completed=int(d.get("pages_completed") or 0),
            total_fetched=int(d.get("total_fetched") or 0),
            last_error=d.get("last_error"),
            updated_at=d.get("updated_at"),
            meta=dict(d.get("meta") or {}),
        )


def checkpoint_path(mode: str = "incremental") -> Path:
    """Path for the checkpoint JSON for a given mode."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR / f"sc_compras_{mode}.json"


def load_checkpoint(mode: str = "incremental") -> ScComprasCheckpoint:
    """Load checkpoint from disk or return a fresh one."""
    path = checkpoint_path(mode)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ScComprasCheckpoint.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
            _logger.warning("[ScCompras] Corrupt checkpoint %s: %s — starting fresh", path, e)
    return ScComprasCheckpoint(mode=mode)


def save_checkpoint(cp: ScComprasCheckpoint) -> Path:
    """Persist checkpoint to disk; return path."""
    cp.updated_at = _utc_now_iso()
    path = checkpoint_path(cp.mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cp.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, obj: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return path


def _persist_raw_page(run_id: str, page_idx: int, payload: dict[str, Any]) -> Path:
    return _write_json(RAW_DIR / run_id / f"page_{page_idx:04d}.json", payload)


def _persist_normalized(run_id: str, records: list[dict]) -> Path:
    return _write_jsonl(OUTPUT_DIR / run_id / "licitacoes.jsonl", records)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_metrics(
    normalized: list[dict],
    *,
    raw_count: int,
    api_total_elementos: int | None,
    duplicate_count: int,
    started_at: datetime,
    live_fetch: bool,
) -> dict[str, Any]:
    """Compute crawl quality metrics (does NOT claim full portal coverage)."""
    dates: list[str] = []
    empty_fields: dict[str, int] = {k: 0 for k in _TRACKED_EMPTY_FIELDS}
    incomplete = 0
    non_sc = 0

    for rec in normalized:
        for k in _TRACKED_EMPTY_FIELDS:
            val = rec.get(k)
            if val is None or val == "" or val == []:
                empty_fields[k] = empty_fields.get(k, 0) + 1
        if any(not rec.get(req) for req in _REQUIRED_FIELDS):
            incomplete += 1
        uf = (rec.get("uf") or "").upper()
        if uf and uf != "SC":
            non_sc += 1
        for dk in ("data_publicacao", "data_abertura", "data_encerramento"):
            d = rec.get(dk)
            if d:
                dates.append(str(d)[:10])

    temporal_min = min(dates) if dates else None
    temporal_max = max(dates) if dates else None
    elapsed_s = round((datetime.now(UTC) - started_at).total_seconds(), 3)
    freshness_hours: float | None = None
    if temporal_max:
        try:
            tmax = datetime.strptime(temporal_max, "%Y-%m-%d").replace(tzinfo=UTC)
            freshness_hours = round((datetime.now(UTC) - tmax).total_seconds() / 3600.0, 2)
        except ValueError:
            freshness_hours = None

    return {
        "live_fetch": live_fetch,
        "api_total_elementos_reported": api_total_elementos,
        "records_raw": raw_count,
        "records_normalized": len(normalized),
        "duplicates": duplicate_count,
        "incomplete_records": incomplete,
        "empty_fields": empty_fields,
        "non_sc_records": non_sc,
        "temporal_range": {"min": temporal_min, "max": temporal_max},
        "freshness_hours_from_max_date": freshness_hours,
        "elapsed_s": elapsed_s,
        # Explicit: totalElementos is API metadata, not proven full-history coverage
        "coverage_claim": (
            "api_total_elementos is live metadata for the requested year filter only; "
            "not claimed as full portal historical coverage"
        ),
    }


# ---------------------------------------------------------------------------
# Filtering / selection
# ---------------------------------------------------------------------------


def _item_id(item: dict) -> int | None:
    try:
        return int(item["id"]) if item.get("id") is not None else None
    except (TypeError, ValueError):
        return None


def select_items_for_mode(
    items: list[dict],
    mode: str,
    *,
    checkpoint: ScComprasCheckpoint | None = None,
    max_pages: int | None = None,
    page_size: int | None = None,
    date_from: date | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Select which bulk items to process for the mode (client-side).

    Returns (selected_items, selection_meta).
    """
    size = page_size or PAGE_SIZE
    pages_limit = max_pages if max_pages is not None else (SC_COMPRAS_SMOKE_PAGES if mode == "smoke" else MAX_PAGES)
    meta: dict[str, Any] = {
        "mode": mode,
        "page_size": size,
        "pages_limit": pages_limit,
        "input_count": len(items),
        "strategy": None,
    }

    if not items:
        meta["strategy"] = "empty"
        return [], meta

    # Sort by id ascending so checkpoint resume is stable
    sorted_items = sorted(
        items,
        key=lambda it: (_item_id(it) is None, _item_id(it) or 0),
    )

    if mode == "smoke":
        selected = sorted_items[: size * max(1, pages_limit)]
        meta["strategy"] = "first_n_pages"
        return selected, meta

    if mode == "incremental":
        last_max = checkpoint.last_max_id if checkpoint else None
        if last_max is not None:
            selected = [it for it in sorted_items if (_item_id(it) or -1) > last_max]
            meta["strategy"] = "since_last_max_id"
            meta["last_max_id"] = last_max
            # Bound by max_pages of virtual pages
            cap = size * max(1, pages_limit)
            if len(selected) > cap:
                selected = selected[:cap]
                meta["capped"] = True
            return selected, meta
        # No checkpoint: last N days cannot be applied without detail dates on list
        # Use newest pages by id (tail of sorted list)
        cap = size * max(1, pages_limit)
        selected = sorted_items[-cap:] if len(sorted_items) > cap else list(sorted_items)
        meta["strategy"] = "newest_pages_no_checkpoint"
        meta["date_from_hint"] = date_from.isoformat() if date_from else None
        return selected, meta

    # full — process from oldest, bounded by max pages
    cap = size * max(1, pages_limit)
    selected = sorted_items[:cap] if len(sorted_items) > cap else list(sorted_items)
    meta["strategy"] = "full_bounded_pages"
    if date_from is not None:
        meta["date_from_hint"] = date_from.isoformat()
    return selected, meta


def dedupe_by_api_id(items: list[dict]) -> tuple[list[dict], int]:
    """Drop duplicate api ids (keep first). Returns (unique, duplicate_count)."""
    seen: set[Any] = set()
    unique: list[dict] = []
    dups = 0
    for it in items:
        key = it.get("id", it.get("api_id"))
        if key is None:
            unique.append(it)
            continue
        if key in seen:
            dups += 1
            continue
        seen.add(key)
        unique.append(it)
    return unique, dups


# ---------------------------------------------------------------------------
# Public API (called by monitor.py)
# ---------------------------------------------------------------------------


def smoke(ano: int | None = None) -> dict:
    """Connectivity smoke against public JSON API (list only, no detail fan-out).

    Performs a single GET ``/api/editais?ano=YYYY`` and returns a diagnostics
    dict suitable for ops probes. Does not enrich details (avoids N+1).
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
    """Crawl SC Compras portal via JSON API (monitor.py interface).

    Args:
        mode: 'full', 'incremental', or 'smoke'.

    Returns:
        List of raw item dicts in canonical format. Empty list on failure.
    """
    if mode == "smoke":
        result = smoke()
        if not result.get("ok"):
            _logger.warning("[ScCompras] smoke failed: %s", result.get("error"))
            return []
        raw_items = _fetch_api_list(int(result["ano"]))
        sample = raw_items[:5]
        return [_api_item_to_canonical(it) for it in sample]

    days = SC_COMPRAS_FULL_DAYS if mode == "full" else SC_COMPRAS_INCREMENTAL_DAYS
    today_d = date.today()
    date_from_d = today_d - timedelta(days=days)

    fetch_detail_flag = not bool(int(os.getenv("SC_COMPRAS_LIST_ONLY", "0")))

    _logger.info(
        "[ScCompras] Crawling %s mode: %s -> %s (JSON API, detail=%s)",
        mode,
        date_from_d.isoformat(),
        today_d.isoformat(),
        fetch_detail_flag,
    )

    years_needed = {today_d.year}
    if date_from_d.year < today_d.year:
        years_needed.add(date_from_d.year)

    cp = load_checkpoint(mode) if mode == "incremental" else ScComprasCheckpoint(mode=mode)

    all_items: list[dict] = []
    items_count = 0

    for ano in sorted(years_needed, reverse=True):
        raw_items, _meta = _fetch_api_list_meta(ano)
        if not raw_items:
            _logger.warning(
                "[ScCompras] No data for year %d — API may be unavailable",
                ano,
            )
            continue

        selected, sel_meta = select_items_for_mode(
            raw_items,
            mode,
            checkpoint=cp if mode == "incremental" else None,
            max_pages=MAX_PAGES,
            date_from=date_from_d,
        )
        _logger.info(
            "[ScCompras] year=%d selected=%d/%d strategy=%s detail=%s",
            ano,
            len(selected),
            len(raw_items),
            sel_meta.get("strategy"),
            fetch_detail_flag,
        )

        for item in selected:
            try:
                if fetch_detail_flag and item.get("id") is not None:
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
    """Transform raw SC portal records to pncp_raw_bids-compatible schema.

    Pure normalization — does NOT fetch additional data.
    Does NOT include 'source' field (monitor.py adds it).
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


# ---------------------------------------------------------------------------
# Full pipeline with checkpoint + run evidence + artifact
# ---------------------------------------------------------------------------


def run(
    mode: str = "smoke",
    *,
    ano: int | None = None,
    max_pages: int | None = None,
    fetch_detail: bool | None = None,
    persist: bool = True,
    live_fetch: bool = True,
    run_id: str | None = None,
    preloaded_items: list[dict] | None = None,
    preloaded_meta: dict[str, Any] | None = None,
    detail_loader: Any | None = None,
) -> dict[str, Any]:
    """Execute a crawl pipeline with checkpoint, metrics and terminal artifact.

    Args:
        mode: smoke | incremental | full
        ano: year filter (default: current year)
        max_pages: virtual page cap
        fetch_detail: override detail enrichment (default: False for smoke, True else)
        persist: write raw/normalized/checkpoint/artifact to disk
        live_fetch: mark artifact as live (False when injected fixtures in tests)
        run_id: optional fixed run id
        preloaded_items / preloaded_meta: inject list response (tests / offline)
        detail_loader: optional callable(id) -> detail dict (tests)

    Returns:
        Terminal artifact dict including run_id, metrics, paths, live_fetch.
    """
    mode = (mode or "smoke").lower().strip()
    if mode not in {"smoke", "incremental", "full"}:
        raise ValueError(f"unsupported mode: {mode}")

    year = ano or date.today().year
    rid = run_id or new_run_id(prefix=f"sc_compras-{mode}")
    started = datetime.now(UTC)
    pages_limit = max_pages if max_pages is not None else (SC_COMPRAS_SMOKE_PAGES if mode == "smoke" else MAX_PAGES)
    if fetch_detail is None:
        fetch_detail = mode != "smoke" and not bool(int(os.getenv("SC_COMPRAS_LIST_ONLY", "0")))

    days = SC_COMPRAS_FULL_DAYS if mode == "full" else SC_COMPRAS_INCREMENTAL_DAYS
    date_from_d = date.today() - timedelta(days=days)

    cp = load_checkpoint(mode)
    cp_dict = bind_checkpoint_run_id(cp.to_dict(), rid)
    cp = ScComprasCheckpoint.from_dict(cp_dict)

    errors: list[str] = []
    raw_pages_written: list[str] = []
    api_total: int | None = None

    # --- list fetch ---
    if preloaded_items is not None:
        raw_items = list(preloaded_items)
        list_meta = dict(preloaded_meta or {})
        list_meta.setdefault("ano", year)
        list_meta.setdefault("total_elementos", len(raw_items))
        list_meta.setdefault("ok", True)
        live_flag = bool(live_fetch)
    else:
        raw_items, list_meta = _fetch_api_list_meta(year)
        live_flag = True

    api_total = list_meta.get("total_elementos")
    if not list_meta.get("ok", True) and not raw_items:
        errors.append("list_fetch_failed")

    raw_items, list_dups = dedupe_by_api_id(raw_items)

    selected, sel_meta = select_items_for_mode(
        raw_items,
        mode,
        checkpoint=cp,
        max_pages=pages_limit,
        date_from=date_from_d,
    )

    # Persist raw bulk meta + first virtual pages of *selected* set
    pages = _virtual_pages(selected, PAGE_SIZE)
    if not pages and selected:
        pages = [selected]
    if not pages:
        # Explicit empty-page evidence
        pages = [[]]

    canonicals: list[dict] = []
    detail_fn = detail_loader or _fetch_api_detail

    for page_idx, page_items in enumerate(pages):
        page_payload = {
            "run_id": rid,
            "mode": mode,
            "ano": year,
            "page": page_idx,
            "page_size": PAGE_SIZE,
            "count": len(page_items),
            "api_total_elementos": api_total,
            "items": page_items,
            "fetched_at": _utc_now_iso(),
            "live_fetch": live_flag,
        }
        if persist:
            p = _persist_raw_page(rid, page_idx, page_payload)
            raw_pages_written.append(str(p))

        if not page_items:
            _logger.info("[ScCompras] empty virtual page %d — stop", page_idx)
            break

        for item in page_items:
            detail = None
            if fetch_detail and item.get("id") is not None:
                try:
                    detail = detail_fn(int(item["id"]))
                except Exception as e:  # noqa: BLE001
                    errors.append(f"detail_error:{item.get('id')}:{e}")
                    detail = None
            try:
                canonicals.append(_api_item_to_canonical(item, detail))
            except Exception as e:  # noqa: BLE001
                errors.append(f"canonical_error:{item.get('id')}:{e}")

        cp.pages_completed = page_idx + 1
        if persist and mode in {"incremental", "full"}:
            save_checkpoint(cp)

        if mode == "smoke" and page_idx + 1 >= pages_limit:
            break
        if page_idx + 1 < len(pages):
            time.sleep(PAGE_DELAY_S if live_flag else 0)

    # Dedupe after canonicalization by api_id
    seen_ids: set[Any] = set()
    unique_canonicals: list[dict] = []
    canon_dups = 0
    for c in canonicals:
        key = c.get("api_id")
        if key is not None and key in seen_ids:
            canon_dups += 1
            continue
        if key is not None:
            seen_ids.add(key)
        unique_canonicals.append(c)

    total_dups = list_dups + canon_dups
    normalized = transform(unique_canonicals)

    # Update checkpoint
    ids_processed = [int(c["api_id"]) for c in unique_canonicals if c.get("api_id") is not None]
    if ids_processed:
        batch_max = max(ids_processed)
        if cp.last_max_id is None or batch_max > cp.last_max_id:
            cp.last_max_id = batch_max
        cp.last_seen_ids = ids_processed[-50:]
    cp.last_year = year
    cp.total_fetched = int(cp.total_fetched or 0) + len(unique_canonicals)
    cp.mode = mode
    cp.last_error = errors[-1] if errors else None
    cp = ScComprasCheckpoint.from_dict(bind_checkpoint_run_id(cp.to_dict(), rid))

    ckpt_path: Path | None = None
    out_path: Path | None = None
    artifact_path: Path | None = None

    if persist:
        ckpt_path = save_checkpoint(cp)
        out_path = _persist_normalized(rid, normalized)

    metrics = compute_metrics(
        normalized,
        raw_count=len(unique_canonicals),
        api_total_elementos=api_total if isinstance(api_total, int) else None,
        duplicate_count=total_dups,
        started_at=started,
        live_fetch=live_flag,
    )
    metrics["selection"] = sel_meta
    metrics["list_meta"] = {
        k: list_meta.get(k)
        for k in ("ano", "total_elementos", "total_paginas", "por_pagina", "items_returned", "ok", "url")
    }
    metrics["fetch_detail"] = fetch_detail
    metrics["pages_processed"] = cp.pages_completed

    completed_at = _utc_now_iso()
    evidence = build_run_evidence(
        run_id=rid,
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        completed_at=completed_at,
        command="scripts.crawl.sc_compras_crawler",
        args={
            "mode": mode,
            "ano": year,
            "max_pages": pages_limit,
            "fetch_detail": fetch_detail,
            "page_size": PAGE_SIZE,
        },
        env_non_secret={
            k: str(v)
            for k, v in os.environ.items()
            if k.startswith("SC_COMPRAS_") and not any(s in k.upper() for s in ("PASSWORD", "TOKEN", "SECRET", "DSN"))
        },
        checkpoint_path=str(ckpt_path) if ckpt_path else None,
        output_path=str(out_path) if out_path else None,
        status="ok" if not errors or normalized else ("partial" if normalized else "error"),
        errors=errors,
        counts_before={"checkpoint_total_fetched": cp.total_fetched - len(unique_canonicals)},
        counts_after={
            "records_normalized": len(normalized),
            "records_raw": len(unique_canonicals),
            "api_total_elementos_reported": api_total,
        },
        criteria={
            "modes": ["smoke", "incremental", "full"],
            "live_fetch_required_for_smoke_claim": True,
        },
        claims_allowed=[
            "year_filter_live_totalElementos_metadata",
            "records_fetched_this_run",
            "checkpoint_resume_by_last_max_id",
        ],
        claims_forbidden=[
            "full_portal_historical_coverage",
            "unverified_2602_as_complete_universe",
        ],
        source="sc_compras",
        live_fetch=live_flag,
    )

    artifact: dict[str, Any] = {
        "run_id": rid,
        "source": "sc_compras",
        "mode": mode,
        "ano": year,
        "status": evidence["status"],
        "live_fetch": live_flag,
        "started_at": evidence["started_at"],
        "completed_at": completed_at,
        "metrics": metrics,
        "checkpoint": cp.to_dict(),
        "checkpoint_path": str(ckpt_path) if ckpt_path else None,
        "raw_pages": raw_pages_written,
        "output_path": str(out_path) if out_path else None,
        "sample_ids": [c.get("api_id") for c in unique_canonicals[:5]],
        "records_normalized": len(normalized),
        "evidence": evidence,
        "errors": errors,
    }

    if persist:
        artifact_path = OUTPUT_DIR / rid / "artifact.json"
        # Pre-hash paths
        if ckpt_path:
            evidence["checkpoint_hash"] = sha256_file(ckpt_path)
            evidence["checkpoint_content_sha256"] = sha256_json(cp.to_dict())
        if out_path:
            evidence["output_hash"] = sha256_file(out_path)
        artifact["evidence"] = evidence
        _write_json(artifact_path, artifact)
        artifact["artifact_path"] = str(artifact_path)
        # Self hash
        artifact["artifact_sha256"] = sha256_file(artifact_path)
        _write_json(artifact_path, artifact)

    return artifact


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Examples::

        python -m scripts.crawl.sc_compras_crawler --mode smoke
        python -m scripts.crawl.sc_compras_crawler --mode incremental --max-pages 5
        python -m scripts.crawl.sc_compras_crawler smoke
    """
    argv = list(argv if argv is not None else sys.argv[1:])

    # Back-compat: bare "smoke" / "--smoke"
    if argv and argv[0].lower() in {"smoke", "--smoke"} and not any(a.startswith("--mode") for a in argv):
        # Allow: smoke [--ano 2026]
        parser = argparse.ArgumentParser(prog="sc_compras_crawler")
        parser.add_argument("cmd", nargs="?", default="smoke")
        parser.add_argument("--ano", type=int, default=None)
        parser.add_argument("--no-persist", action="store_true")
        parser.add_argument("--list-only", action="store_true")
        parser.add_argument("--max-pages", type=int, default=None)
        ns = parser.parse_args(argv)
        if ns.cmd.lower() in {"smoke", "--smoke"}:
            art = run(
                mode="smoke",
                ano=ns.ano,
                max_pages=ns.max_pages or SC_COMPRAS_SMOKE_PAGES,
                fetch_detail=False if ns.list_only else False,
                persist=not ns.no_persist,
                live_fetch=True,
            )
            print(json.dumps(art, ensure_ascii=False, indent=2, default=str))
            return 0 if art.get("status") in {"ok", "partial"} and art.get("live_fetch") else 1
        print("Usage: python -m scripts.crawl.sc_compras_crawler --mode smoke|incremental|full", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(
        description="Portal de Compras SC crawler (JSON API)",
    )
    parser.add_argument(
        "--mode",
        choices=["smoke", "incremental", "full"],
        default="smoke",
        help="Crawl mode (default: smoke)",
    )
    parser.add_argument("--ano", type=int, default=None, help="Year filter (default: current)")
    parser.add_argument("--max-pages", type=int, default=None, help="Virtual page cap")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Skip detail enrichment (faster)",
    )
    parser.add_argument(
        "--with-detail",
        action="store_true",
        help="Force detail enrichment even for smoke",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write checkpoint/raw/output artifacts",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional fixed run_id",
    )
    # Back-compat positional
    parser.add_argument("cmd", nargs="?", default=None, help=argparse.SUPPRESS)

    ns = parser.parse_args(argv)
    mode = ns.mode
    if ns.cmd and ns.cmd.lower() in {"smoke", "incremental", "full"}:
        mode = ns.cmd.lower()

    fetch_detail: bool | None
    if ns.with_detail:
        fetch_detail = True
    elif ns.list_only:
        fetch_detail = False
    else:
        fetch_detail = None

    art = run(
        mode=mode,
        ano=ns.ano,
        max_pages=ns.max_pages,
        fetch_detail=fetch_detail,
        persist=not ns.no_persist,
        live_fetch=True,
        run_id=ns.run_id,
    )
    print(json.dumps(art, ensure_ascii=False, indent=2, default=str))
    ok = art.get("status") in {"ok", "partial"} and (art.get("live_fetch") is True or mode != "smoke")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
