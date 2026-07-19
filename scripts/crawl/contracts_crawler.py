"""PNCP Contracts Crawler — Extra Consultoria.

Adapted from the original async/BaseCrawler-based contracts_crawler.py
to the simple sync interface expected by monitor.py:
    crawl(mode) -> list[dict]
    transform(records) -> list[dict]

Crawls PNCP /contratos endpoint in date windows and normalizes
to the pncp_supplier_contracts schema (contrato_id, fornecedor_cnpj,
objeto_contrato, valor_total, etc.).

Modes:
  - full:           Last CONTRACTS_FULL_DAYS days (default 90)
  - incremental:    Last CONTRACTS_INCREMENTAL_DAYS days (default 3)
  - backfill_3y:    3-year backfill in windows with checkpoint support

Design constraints (per goal criteria):
  - Typed FetchResult distinguishes zero-real from connection/HTTP/parse/
    transform/persist failure. Exception → empty list is PROHIBITED.
  - UF is NEVER presumed "SC" when absent from API response.
  - Checkpoint files enable reentrant backfill across restarts.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.crawl.common import (
    digits_only as _digits_only,
)
from scripts.crawl.common import (
    generate_content_hash as _common_content_hash,
)
from scripts.crawl.common import (
    safe_date as _safe_date,
)
from scripts.crawl.common import (
    trunc as trunc,
)
from scripts.crawl.security import USER_AGENT, sanitize_url_param, validate_url_scheme

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
CONTRACTS_REQUEST_DELAY = float(os.getenv("CONTRACTS_REQUEST_DELAY", "1.0"))
CONTRACTS_WINDOW_DAYS = int(os.getenv("CONTRACTS_WINDOW_DAYS", "30"))
CONTRACTS_JANELA_DELAY = float(os.getenv("CONTRACTS_JANELA_DELAY", "5.0"))
CONTRACTS_FULL_DAYS = int(os.getenv("CONTRACTS_FULL_DAYS", "90"))
CONTRACTS_INCREMENTAL_DAYS = int(os.getenv("CONTRACTS_INCREMENTAL_DAYS", "3"))
CONTRACTS_BACKFILL_YEARS = int(os.getenv("CONTRACTS_BACKFILL_YEARS", "3"))
CONTRACTS_CHECKPOINT_DIR = os.getenv(
    "CONTRACTS_CHECKPOINT_DIR",
    str(_PROJECT_ROOT / "data" / "contracts_checkpoints"),
)

_ESFERA_MAP = {"F": 1, "E": 2, "M": 3, "D": 4}

# Contracts use a different schema (pncp_supplier_contracts) than bids.
# monitor.py reads this attribute to dispatch to the correct upsert RPC.
UPSERT_FUNCTION = "upsert_pncp_supplier_contracts"
SOURCE_PURPOSE = "contracts"

# Modes that persist reentrant window checkpoints (JSON under CONTRACTS_CHECKPOINT_DIR).
# full (90d pilot) and backfill_3y both need resume; incremental stays ephemeral.
_CHECKPOINT_MODES = frozenset({"full", "backfill_3y"})


# ---------------------------------------------------------------------------
# Typed fetch result — zero vs failure discrimination
# ---------------------------------------------------------------------------


class FetchStatus(Enum):
    """Machine-readable outcome of a fetch attempt.

    Every fetch returns exactly one status.  ``SUCCESS_ZERO`` means the API
    responded correctly but there were genuinely no records — this is NOT
    the same as a connection failure or HTTP error.
    """

    SUCCESS_DATA = "success_data"  # Data returned (page may be non-empty)
    SUCCESS_ZERO = "success_zero"  # API OK, zero records for this query
    CONNECTION_FAILED = "connection_failed"  # DNS/TCP/TLS/timeout
    HTTP_CLIENT_ERROR = "http_client_error"  # 4xx (not 429)
    HTTP_SERVER_ERROR = "http_server_error"  # 5xx
    HTTP_RATE_LIMIT = "http_rate_limit"  # 429
    PARSE_FAILED = "parse_failed"  # JSON parse error
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class FetchResult:
    """Result of a single page fetch with full error discrimination."""

    status: FetchStatus
    items: list[dict] = field(default_factory=list)
    total_records: int = 0
    total_pages: int = 0
    current_page: int = 0
    error_message: str | None = None
    error_code: int | None = None
    url: str = ""

    @property
    def is_success(self) -> bool:
        return self.status in (FetchStatus.SUCCESS_DATA, FetchStatus.SUCCESS_ZERO)

    @property
    def is_zero(self) -> bool:
        """True when the API returned a legitimate empty result set."""
        return self.status == FetchStatus.SUCCESS_ZERO

    @property
    def is_failure(self) -> bool:
        return not self.is_success

    @property
    def evidence_state(self) -> str:
        """Map FetchStatus to coverage_evidence state enum."""
        _map = {
            FetchStatus.SUCCESS_DATA: "success_with_data",
            FetchStatus.SUCCESS_ZERO: "success_zero",
            FetchStatus.CONNECTION_FAILED: "connection_failed",
            FetchStatus.HTTP_CLIENT_ERROR: "connection_failed",
            FetchStatus.HTTP_SERVER_ERROR: "connection_failed",
            FetchStatus.HTTP_RATE_LIMIT: "connection_failed",
            FetchStatus.PARSE_FAILED: "parse_failed",
            FetchStatus.UNKNOWN_ERROR: "connection_failed",
        }
        return _map.get(self.status, "connection_failed")


# ---------------------------------------------------------------------------
# Checkpoint (file-based, reentrant)
# ---------------------------------------------------------------------------


@dataclass
class CrawlCheckpoint:
    """Reentrant checkpoint for contract backfill."""

    source: str = "pncp_contracts"
    mode: str = "backfill_3y"
    completed_windows: list[str] = field(default_factory=list)
    current_window_start: str | None = None
    total_contracts_fetched: int = 0
    total_windows_completed: int = 0
    total_windows_failed: int = 0
    last_error: str | None = None
    updated_at: str | None = None
    # Provenance: run_id history (resume across runs is allowed by default)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "mode": self.mode,
            "completed_windows": self.completed_windows,
            "current_window_start": self.current_window_start,
            "total_contracts_fetched": self.total_contracts_fetched,
            "total_windows_completed": self.total_windows_completed,
            "total_windows_failed": self.total_windows_failed,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
            "meta": self.meta or {},
        }

    @classmethod
    def from_dict(cls, d: dict) -> CrawlCheckpoint:
        return cls(
            source=d.get("source", "pncp_contracts"),
            mode=d.get("mode", "backfill_3y"),
            completed_windows=d.get("completed_windows", []),
            current_window_start=d.get("current_window_start"),
            total_contracts_fetched=d.get("total_contracts_fetched", 0),
            total_windows_completed=d.get("total_windows_completed", 0),
            total_windows_failed=d.get("total_windows_failed", 0),
            last_error=d.get("last_error"),
            updated_at=d.get("updated_at"),
            meta=d.get("meta") or {},
        )


def _checkpoint_path(mode: str) -> str:
    """Filesystem path for the checkpoint file."""
    os.makedirs(CONTRACTS_CHECKPOINT_DIR, exist_ok=True)
    return os.path.join(CONTRACTS_CHECKPOINT_DIR, f"contracts_{mode}.json")


def load_checkpoint(mode: str) -> CrawlCheckpoint:
    """Load checkpoint from disk, or return a fresh one."""
    path = _checkpoint_path(mode)
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            return CrawlCheckpoint.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Corrupt checkpoint %s: %s — starting fresh", path, e)
    return CrawlCheckpoint(mode=mode)


def save_checkpoint(cp: CrawlCheckpoint) -> None:
    """Persist checkpoint to disk."""
    cp.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path = _checkpoint_path(cp.mode)
    with open(path, "w") as f:
        json.dump(cp.to_dict(), f, indent=2, default=str)


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


def uf_from_unidade(rec: dict) -> str | None:
    """Extract UF from a raw PNCP /contratos item via ``unidadeOrgao.ufSigla``.

    Never defaults to ``"SC"``. Returns ``None`` when absent/blank.

    Args:
        rec: Raw API item (or any dict with optional ``unidadeOrgao``).

    Returns:
        Two-letter UF or ``None``.
    """
    unidade = rec.get("unidadeOrgao") or {}
    if not isinstance(unidade, dict):
        return None
    uf = (unidade.get("ufSigla") or "").strip().upper()
    return uf[:2] if len(uf) >= 2 else (uf or None)


def _generate_content_hash(record: dict) -> str:
    """MD5 hash of key fields for dedup (pncp_supplier_contracts convention)."""
    return _common_content_hash(record, fields=["contrato_id", "orgao_cnpj", "objeto_contrato", "valor_total"])


def _fmt(d: date) -> str:
    return d.strftime("%Y%m%d")


def _persist_window_if_enabled(raw_items: list[dict]) -> int:
    """Optionally upsert a completed window immediately (default ON when DSN set).

    Avoids losing multi-window work on kill: monitor historically only upserted
    after crawl() returned the full list. Idempotent via SQL upsert function.
    Env:
      CONTRACTS_PERSIST_EACH_WINDOW=0 to disable
      LOCAL_DATALAKE_DSN / DATABASE_URL for connection
    """
    flag = os.getenv("CONTRACTS_PERSIST_EACH_WINDOW", "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return 0
    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not dsn or not raw_items:
        return 0
    try:
        import psycopg2
        from psycopg2.sql import SQL, Identifier

        transformed = transform(raw_items)
        if not transformed:
            return 0
        # monitor adds source=pncp_contracts; match that for consistency
        for row in transformed:
            row.setdefault("source", "pncp_contracts")
        conn = psycopg2.connect(dsn)
        try:
            cur = conn.cursor()
            cur.execute(
                SQL("SELECT * FROM {} (%s)").format(Identifier(UPSERT_FUNCTION)),
                (json.dumps(transformed, default=str),),
            )
            rows = cur.fetchall()
            conn.commit()
        finally:
            conn.close()
        if not rows:
            return 0
        first = rows[0]
        if len(rows) == 1 and len(first) >= 3 and all(isinstance(v, int) for v in first[:3]):
            return int(first[0]) + int(first[1])
        return len(rows)
    except Exception as exc:  # noqa: BLE001 — window crawl must continue
        logger.warning("Per-window persist failed (non-fatal): %s", exc)
        return 0


# ---------------------------------------------------------------------------
# HTTP fetch (sync, stdlib only) — typed result
# ---------------------------------------------------------------------------


def _fetch_page(data_ini: str, data_fim: str, page: int) -> FetchResult:
    """Fetch one page of contracts synchronously via urllib.

    Returns ``FetchResult`` with explicit status discrimination.
    NEVER returns ``SUCCESS_ZERO`` for a failure — callers can distinguish
    "API said zero" from "we couldn't reach the API".
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
            validate_url_scheme(url)
            req = urllib.request.Request(url)  # noqa: S310 — validated above
            req.add_header("User-Agent", USER_AGENT)
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=CONTRACTS_READ_TIMEOUT) as resp:  # noqa: S310 — validated above
                body = resp.read().decode("utf-8")
                try:
                    data = json.loads(body)
                except json.JSONDecodeError as e:
                    return FetchResult(
                        status=FetchStatus.PARSE_FAILED,
                        error_message=f"JSON parse error: {e}",
                        url=url,
                        current_page=page,
                    )

            if isinstance(data, dict):
                items = data.get("data", [])
                total_records = int(data.get("totalRegistros", 0))
                total_pages = int(data.get("totalPaginas", 1))

                if not isinstance(items, list):
                    items = []

                status = FetchStatus.SUCCESS_ZERO if len(items) == 0 else FetchStatus.SUCCESS_DATA
                return FetchResult(
                    status=status,
                    items=items,
                    total_records=total_records,
                    total_pages=total_pages,
                    current_page=page,
                    url=url,
                )

            if isinstance(data, list):
                status = FetchStatus.SUCCESS_ZERO if len(data) == 0 else FetchStatus.SUCCESS_DATA
                return FetchResult(
                    status=status,
                    items=data,
                    total_records=len(data),
                    total_pages=1,
                    current_page=page,
                    url=url,
                )

            # Unexpected response format
            return FetchResult(
                status=FetchStatus.PARSE_FAILED,
                error_message="Unexpected response format (not dict or list)",
                url=url,
                current_page=page,
            )

        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8")[:200]
            except Exception:
                logger.debug("[CONTRACTS] Could not read error body from HTTP response")

            if e.code == 429:
                if attempt < CONTRACTS_MAX_RETRIES:
                    wait = 10 * (attempt + 1)
                    logger.debug("PNCP 429, waiting %ds before retry %d/%d", wait, attempt + 1, CONTRACTS_MAX_RETRIES)
                    time.sleep(wait)
                    continue
                return FetchResult(
                    status=FetchStatus.HTTP_RATE_LIMIT,
                    error_message=f"429 Rate limit exceeded after {CONTRACTS_MAX_RETRIES} retries",
                    error_code=429,
                    url=url,
                    current_page=page,
                )

            if e.code in (404, 400, 422):
                return FetchResult(
                    status=FetchStatus.HTTP_CLIENT_ERROR,
                    error_message=f"HTTP {e.code}: {body_text}",
                    error_code=e.code,
                    url=url,
                    current_page=page,
                )

            if e.code >= 500:
                if attempt < CONTRACTS_MAX_RETRIES:
                    time.sleep(2**attempt)
                    continue
                return FetchResult(
                    status=FetchStatus.HTTP_SERVER_ERROR,
                    error_message=f"HTTP {e.code}: {body_text}",
                    error_code=e.code,
                    url=url,
                    current_page=page,
                )

            # Other 4xx (not 429, 404, 400, 422)
            return FetchResult(
                status=FetchStatus.HTTP_CLIENT_ERROR,
                error_message=f"HTTP {e.code}: {body_text}",
                error_code=e.code,
                url=url,
                current_page=page,
            )

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < CONTRACTS_MAX_RETRIES:
                time.sleep(1 + attempt)
                continue
            return FetchResult(
                status=FetchStatus.CONNECTION_FAILED,
                error_message=f"Network error after {CONTRACTS_MAX_RETRIES} retries: {e}",
                url=url,
                current_page=page,
            )

        except Exception as e:
            if attempt < CONTRACTS_MAX_RETRIES:
                time.sleep(1 + attempt)
                continue
            return FetchResult(
                status=FetchStatus.UNKNOWN_ERROR,
                error_message=f"Unexpected error: {type(e).__name__}: {e}",
                url=url,
                current_page=page,
            )

    # Should not reach here, but just in case
    return FetchResult(
        status=FetchStatus.UNKNOWN_ERROR,
        error_message="Exhausted all retries",
        url=url,
        current_page=page,
    )


# ---------------------------------------------------------------------------
# Transform a single record
# ---------------------------------------------------------------------------


def _transform_record(rec: dict) -> dict | None:
    """Normalize a single PNCP /contratos item to pncp_supplier_contracts schema.

    Returns ``None`` if the record lacks a valid ``numeroControlePNCP``.

    UF determination (GOAL CRITERION 2):
      - Primary: ``unidadeOrgao.ufSigla`` from API response.
      - Secondary: CNPJ-root lookup via ``_uf_from_cnpj()``.
      - NEVER defaults to "SC".  If UF cannot be determined, it stays ``None``.
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
        orgao_nome = (unidade.get("nomeUnidade") or orgao.get("razaoSocial") or "")[:300] or None

        # Dates — keep fields semantically distinct (migration 051).
        # BUGFIX: do NOT map dataAssinatura → data_publicacao as publication.
        data_assinatura = _safe_date(rec.get("dataAssinatura"))
        data_publicacao_fonte = _safe_date(
            rec.get("dataPublicacaoPncp")
            or rec.get("dataPublicacao")
            or rec.get("dataPublicacaoContrato")
        )
        data_atualizacao_fonte = _safe_date(
            rec.get("dataAtualizacao") or rec.get("dataAtualizacaoGlobal")
        )
        # Best event date for the contract act
        source_event_date = data_assinatura or data_publicacao_fonte
        # LEGACY: keep data_publicacao for backward compat; prefer true pub then assinatura
        data_publicacao = data_publicacao_fonte or data_assinatura

        if data_publicacao_fonte and rec.get("dataPublicacaoPncp"):
            source_date_semantics = "dataPublicacaoPncp"
        elif data_publicacao_fonte:
            source_date_semantics = "dataPublicacao"
        elif data_assinatura:
            source_date_semantics = "dataAssinatura_as_event"
        else:
            source_date_semantics = "unknown"

        data_inicio = _safe_date(rec.get("dataVigenciaInicio"))
        data_fim = _safe_date(rec.get("dataVigenciaFim"))

        # Optional crawl window metadata (may be attached by callers)
        query_window_start = _safe_date(rec.get("query_window_start") or rec.get("_query_window_start"))
        query_window_end = _safe_date(rec.get("query_window_end") or rec.get("_query_window_end"))

        # UF — unidade first, CNPJ lookup second, NEVER default to "SC"
        uf = uf_from_unidade(rec)
        if not uf:
            uf = _uf_from_cnpj(orgao_cnpj)
        # GOAL CRITERION 2: No fallback to "SC".  If UF is genuinely
        # unavailable, it stays None so downstream consumers can flag it.

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
            "data_assinatura": data_assinatura,
            "data_publicacao_fonte": data_publicacao_fonte,
            "data_atualizacao_fonte": data_atualizacao_fonte,
            "source_event_date": source_event_date,
            "source_date_semantics": source_date_semantics,
            "query_window_start": query_window_start,
            "query_window_end": query_window_end,
            "uf": uf or None,
            "municipio": municipio,
            "source_id": contrato_id,
        }

        return record

    except Exception as e:
        logger.warning("Transform error for record %s: %s", rec.get("numeroControlePNCP", ""), e)
        return None


# ---------------------------------------------------------------------------
# CrawlResult — aggregate result with per-window evidence
# ---------------------------------------------------------------------------


@dataclass
class WindowResult:
    """Result for a single date window."""

    window_start: str
    window_end: str
    status: FetchStatus
    records_fetched: int = 0
    pages_fetched: int = 0
    error_message: str | None = None


@dataclass
class CrawlResult:
    """Aggregate result of a crawl operation with per-window evidence."""

    mode: str
    windows: list[WindowResult] = field(default_factory=list)
    total_records: int = 0
    total_windows_ok: int = 0
    total_windows_failed: int = 0
    checkpoint: CrawlCheckpoint | None = None

    @property
    def evidence_rows(self) -> list[dict]:
        """Generate evidence rows for each window."""
        rows = []
        for w in self.windows:
            rows.append(
                {
                    "source": "pncp_contracts",
                    "data_type": "contracts",
                    "queried_start": w.window_start,
                    "queried_end": w.window_end,
                    "count_obtained": w.records_fetched,
                    "state": w.status.evidence_state,
                    "error_message": w.error_message,
                }
            )
        return rows


# ---------------------------------------------------------------------------
# Public interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl PNCP /contratos endpoint for raw contract records.

    Args:
        mode: 'full' — last CONTRACTS_FULL_DAYS (default 90 days)
              'incremental' — last CONTRACTS_INCREMENTAL_DAYS (default 3 days)
              'backfill_3y' — 3-year backfill with checkpoint

    Returns:
        List of raw PNCP API records (not yet transformed).
        Empty list only when API returned zero records for ALL windows.
        On partial failure, returns whatever was fetched successfully.
    """
    days = CONTRACTS_FULL_DAYS if mode == "full" else CONTRACTS_INCREMENTAL_DAYS
    today = date.today()

    if mode == "backfill_3y":
        start = today - timedelta(days=CONTRACTS_BACKFILL_YEARS * 365)
    else:
        start = today - timedelta(days=days)

    return _crawl_date_range(start, today, mode)


def _crawl_date_range(
    start: date,
    end: date,
    mode: str = "full",
) -> list[dict]:
    """Crawl contracts in a date range with windowing and checkpoint.

    Returns raw records.  Uses checkpoint for 'full' and 'backfill_3y' modes.
    """
    all_records: list[dict] = []
    checkpoint = load_checkpoint(mode) if mode in _CHECKPOINT_MODES else None

    cur = start
    while cur < end:
        window_end = min(cur + timedelta(days=CONTRACTS_WINDOW_DAYS - 1), end)
        window_key = f"{_fmt(cur)}_{_fmt(window_end)}"

        # Skip completed windows (reentrant)
        if checkpoint and window_key in checkpoint.completed_windows:
            logger.debug("Skipping completed window: %s", window_key)
            cur = window_end + timedelta(days=1)
            continue

        data_ini = _fmt(cur)
        data_fim = _fmt(window_end)

        if checkpoint:
            checkpoint.current_window_start = data_ini
            save_checkpoint(checkpoint)

        page = 1
        window_records = 0
        window_pages = 0
        window_errors: list[str] = []
        window_items: list[dict] = []

        while page <= CONTRACTS_MAX_PAGES:
            result = _fetch_page(data_ini, data_fim, page)

            if result.is_failure:
                window_errors.append(f"Page {page}: [{result.status.value}] {result.error_message}")
                logger.warning(
                    "Window %s page %d failed: %s — %s",
                    window_key,
                    page,
                    result.status.value,
                    result.error_message,
                )
                # On first page failure, abort the window
                if page == 1:
                    break
                # On subsequent page failure, stop pagination but keep what we have
                break

            if result.is_zero and page == 1:
                # Legitimate zero — no contracts in this window
                break

            if result.is_zero:
                # No more pages
                break

            # Success with data
            all_records.extend(result.items)
            window_items.extend(result.items)
            window_records += len(result.items)
            window_pages += 1

            if page >= result.total_pages:
                break

            page += 1
            time.sleep(CONTRACTS_REQUEST_DELAY)

        if window_records > 0:
            logger.info(
                "Window %s->%s: %d records (%d pages)",
                data_ini,
                data_fim,
                window_records,
                window_pages,
            )

        # Mark window as completed ONLY when fully successful.
        # Partial data after page errors must NOT be treated as complete —
        # otherwise resume skips the window and silently under-covers K3.2.
        if checkpoint:
            fully_ok = not window_errors
            if fully_ok:
                # Persist immediately so kill mid-run does not drop completed windows.
                persisted = _persist_window_if_enabled(window_items)
                if persisted:
                    logger.info(
                        "Window %s persisted %d rows to DB (per-window upsert)",
                        window_key,
                        persisted,
                    )
                checkpoint.completed_windows.append(window_key)
                checkpoint.total_windows_completed += 1
                checkpoint.total_contracts_fetched += window_records
            else:
                checkpoint.total_windows_failed += 1
                checkpoint.last_error = "; ".join(window_errors[:3])
                logger.warning(
                    "Window %s NOT marked complete (errors=%d, records=%d)",
                    window_key,
                    len(window_errors),
                    window_records,
                )
            save_checkpoint(checkpoint)

        cur = window_end + timedelta(days=1)

        # Delay between date windows to respect rate limits
        if cur < end:
            time.sleep(CONTRACTS_JANELA_DELAY)

    return all_records


def crawl_with_evidence(mode: str = "backfill_3y") -> CrawlResult:
    """Crawl and return CrawlResult with per-window evidence.

    This is the preferred API for the evidence ledger.  Returns typed
    results that can be fed directly to the evidence pipeline.
    """
    days = CONTRACTS_FULL_DAYS if mode == "full" else CONTRACTS_INCREMENTAL_DAYS
    today = date.today()

    if mode == "backfill_3y":
        start = today - timedelta(days=CONTRACTS_BACKFILL_YEARS * 365)
    else:
        start = today - timedelta(days=days)

    result = CrawlResult(mode=mode)
    checkpoint = load_checkpoint(mode) if mode in _CHECKPOINT_MODES else None
    result.checkpoint = checkpoint

    cur = start
    while cur < today:
        window_end = min(cur + timedelta(days=CONTRACTS_WINDOW_DAYS - 1), today)
        window_key = f"{_fmt(cur)}_{_fmt(window_end)}"

        # Skip completed windows (reentrant)
        if checkpoint and window_key in checkpoint.completed_windows:
            logger.debug("Skipping completed window: %s", window_key)
            cur = window_end + timedelta(days=1)
            continue

        data_ini = _fmt(cur)
        data_fim = _fmt(window_end)

        if checkpoint:
            checkpoint.current_window_start = data_ini
            save_checkpoint(checkpoint)

        page = 1
        window_records = 0
        window_pages = 0
        window_status = FetchStatus.SUCCESS_ZERO
        window_error: str | None = None

        while page <= CONTRACTS_MAX_PAGES:
            fetch_result = _fetch_page(data_ini, data_fim, page)

            if fetch_result.is_failure:
                window_status = fetch_result.status
                window_error = fetch_result.error_message
                if page == 1:
                    break
                break  # Partial window — stop pagination

            if fetch_result.is_zero and page == 1:
                window_status = FetchStatus.SUCCESS_ZERO
                break

            if fetch_result.is_zero:
                break

            window_records += len(fetch_result.items)
            window_pages += 1

            if page >= fetch_result.total_pages:
                break

            page += 1
            time.sleep(CONTRACTS_REQUEST_DELAY)

        wr = WindowResult(
            window_start=data_ini,
            window_end=data_fim,
            status=window_status,
            records_fetched=window_records,
            pages_fetched=window_pages,
            error_message=window_error,
        )
        result.windows.append(wr)
        result.total_records += window_records

        if window_status.is_success:
            result.total_windows_ok += 1
        else:
            result.total_windows_failed += 1

        # Update checkpoint
        if checkpoint:
            if window_status.is_success:
                checkpoint.completed_windows.append(window_key)
                checkpoint.total_windows_completed += 1
                checkpoint.total_contracts_fetched += window_records
            else:
                checkpoint.total_windows_failed += 1
                checkpoint.last_error = window_error
            save_checkpoint(checkpoint)

        cur = window_end + timedelta(days=1)

        if cur < today:
            time.sleep(CONTRACTS_JANELA_DELAY)

    return result


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


def transform_with_uf_filter(records: list[dict], uf: str | None = None) -> list[dict]:
    """Transform + optional client-side UF post-filter.

    The PNCP contratos API UF filter is broken server-side (returns same
    totalRegistros for any UF).  Use this when target filtering is needed.

    Args:
        records: Raw records from crawl().
        uf: Two-letter UF to filter by (e.g. ``"SC"``).  ``None`` = no filter.

    Returns:
        Normalized records, optionally filtered to the given UF.
    """
    transformed = transform(records)
    if uf:
        uf_upper = uf.upper().strip()
        transformed = [r for r in transformed if (r.get("uf") or "").upper() == uf_upper]
    return transformed


def filter_raw_by_uf(records: list[dict], uf: str) -> list[dict]:
    """Filter raw /contratos items by ``unidadeOrgao.ufSigla`` (client-side).

    Prefer this before transform when only one UF is needed (e.g. SC).
    """
    uf_upper = uf.upper().strip()
    return [r for r in records if (uf_from_unidade(r) or "") == uf_upper]
