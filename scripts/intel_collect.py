#!/usr/bin/env python3
"""
Coleta deterministica de dados para o comando /intel-busca.

Busca exaustiva no PNCP por editais abertos de licitacoes competitivas
para um dado CNPJ + UFs. Zero falsos negativos, zero falsos positivos.

Usage:
    python scripts/intel-collect.py --cnpj 12345678000190 --ufs SC,PR,RS
    python scripts/intel-collect.py --cnpj 12.345.678/0001-90 --ufs SC --dias 60
    python scripts/intel-collect.py --cnpj 12345678000190 --ufs SC,PR --output out.json

Requires:
    pip install httpx pyyaml
"""
from __future__ import annotations

import argparse
import concurrent.futures
import glob as glob_mod
import hashlib
import importlib.util
import io
import json
import os
import re
import statistics
import sys
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx as _httpx

# Load .env for local development (Railway/Docker set env vars natively)
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))
except ImportError:
    pass  # python-dotenv not installed — OK in production

# Fix Windows console encoding for Unicode output
# Guard: only wrap if not already wrapped (collect-report-data.py also wraps on import)
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "buffer") and not isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer") and not isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (ValueError, AttributeError):
        pass  # Already wrapped or buffer closed

# ============================================================
# IMPORT from collect-report-data.py (hyphenated filename)
# ============================================================

# Ensure scripts/ is on sys.path so collect-report-data.py can import its siblings (report_dedup)
_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_crd_path = str(Path(__file__).resolve().parent / "collect-report-data.py")
_spec = importlib.util.spec_from_file_location("collect_report_data", _crd_path)
if _spec is None or _spec.loader is None:
    print(f"ERROR: Cannot load {_crd_path}")
    sys.exit(1)
_crd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_crd)

# Pull out everything we need
ApiClient = _crd.ApiClient
_clean_cnpj = _crd._clean_cnpj
_format_cnpj = _crd._format_cnpj
_safe_float = _crd._safe_float
_parse_date_flexible = _crd._parse_date_flexible
_source_tag = _crd._source_tag
_fmt_brl = _crd._fmt_brl
_strip_accents = _crd._strip_accents
collect_opencnpj = _crd.collect_opencnpj
map_sector = _crd.map_sector
PNCP_BASE = _crd.PNCP_BASE
PNCP_FILES_BASE = _crd.PNCP_FILES_BASE
PNCP_MAX_PAGE_SIZE = _crd.PNCP_MAX_PAGE_SIZE
MODALIDADES = _crd.MODALIDADES
MODALIDADES_EXCLUIDAS = _crd.MODALIDADES_EXCLUIDAS
PNCP_MAX_PAGES_UF = 80  # Override: 80 pages × 50 = 4000 items per UF per modalidade
PNCP_MAX_PAGES = _crd.PNCP_MAX_PAGES

# ── v1.3 Performance constants ──
# Date chunking: split large date ranges into smaller windows to avoid pagination exhaustion
_DATE_CHUNK_DAYS = 14  # Each chunk covers 14 days (shorter = fewer pages per combo)
# Parallel workers for PNCP fetch (all modalidade×UF×chunk combos dispatched at once)
_PNCP_FETCH_WORKERS = 4  # Balanced: 3-5 avoids cascading timeouts on gov server
# Adaptive rate limiter
_RATE_LIMIT_BASE_S = 0.15   # Base interval between requests (150ms)
_RATE_LIMIT_MAX_S = 30.0    # Max interval on slowdowns (v1.5: was 2.0s — increased for 429 backoff)
_RATE_LIMIT_SLOW_THRESHOLD_S = 5.0  # Response > 5s = "slow"
_RATE_LIMIT_DECAY = 0.85    # Decay factor on fast responses
_RATE_LIMIT_GROWTH = 1.5    # Growth factor on slow responses
# Circuit breaker: pause after consecutive timeouts
_CIRCUIT_BREAKER_THRESHOLD = 3   # 3 consecutive failures = pause
_CIRCUIT_BREAKER_PAUSE_S = 15.0  # Pause duration (seconds)
# 429 rate-limit specific (v1.5)
_RATE_LIMIT_429_GROWTH = 2.0    # Doubling factor for 429 backoff (start 2s → 4s → 8s → ...)
_RATE_LIMIT_429_MAX_S = 30.0    # Max interval for 429 backoff
_RATE_LIMIT_429_INITIAL_S = 2.0 # Initial wait on first 429 (seconds)
_PNCP_429_MAX_PER_COMBO = 10    # Max 429s per combo before suspension
CNAE_KEYWORD_REFINEMENTS = _crd.CNAE_KEYWORD_REFINEMENTS
_compile_keyword_patterns = _crd._compile_keyword_patterns
_compute_keyword_density = _crd._compute_keyword_density
_check_hard_exclusions = _crd._check_hard_exclusions
_load_json_cache = _crd._load_json_cache
_save_json_cache = _crd._save_json_cache
DOCS_CACHE_FILE = _crd.DOCS_CACHE_FILE
CNAE_INCOMPATIBLE_OBJECTS = _crd.CNAE_INCOMPATIBLE_OBJECTS
collect_sicaf = _crd.collect_sicaf
collect_portal_transparencia = _crd.collect_portal_transparencia

# ============================================================
# CONSTANTS
# ============================================================

VERSION = "1.4.0"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Checkpoint file for resume/fault-tolerance
_CHECKPOINT_FILE = _PROJECT_ROOT / "data" / "intel_pncp_checkpoint.json"
_CHECKPOINT_TTL_HOURS = 2      # Re-use cached UF+mod result if < 2h old
_CHECKPOINT_CLEANUP_HOURS = 24  # Evict stale checkpoint entries older than 24h

# Competitive intelligence cache
_COMPETITIVE_CACHE_FILE = str(_PROJECT_ROOT / "data" / "competitive_cache.json")
_COMPETITIVE_CACHE_TTL_DAYS = 7  # Cache competitive intel per organ for 7 days
_COMPETITIVE_MAX_ORGANS = 15     # Max unique organs to query
_COMPETITIVE_WORKERS = 6         # Parallel workers for competitive intel (was 3)
_BENCHMARK_WORKERS = 6           # Parallel workers for price benchmark (was 1/sequential)

# Modalidades competitivas relevantes (Lei 14.133/2021, arts. 28-29)
#
# INCLUÍDAS:
#   4: Concorrência Eletrônica — principal para OBRAS (art. 28, §1º)
#   5: Concorrência Presencial — mesma regra, formato presencial
#   6: Pregão Eletrônico — serviços comuns de engenharia + materiais (art. 29)
#   7: Pregão Presencial — mesma regra, formato presencial
#
# EXCLUÍDAS (sem competição ou irrelevantes):
#   8: Dispensa — contratação direta, sem licitação
#   9: Inexigibilidade — fornecedor exclusivo, sem competição
#  14: Inaplicabilidade — não se aplica licitação
#   2: Diálogo Competitivo — raríssimo, procedimento complexo
#   3: Concurso — projetos intelectuais, não obras
#  12: Credenciamento — cadastro aberto, não licitação
#  15: Chamada Pública — programa agrícola (MAPA)
#  16-19: Internacionais — irrelevante para construtoras domésticas
MODALIDADES_BUSCA = {
    k: v for k, v in MODALIDADES.items()
    if k in {4, 5, 6, 7}
}

# CNAE keyword density gate: 1% minimum (lower than report's 2% for zero false negatives)
INTEL_DENSITY_MIN = 0.01

# Per-sector keyword density overrides (lower = more inclusive for niche terms)
SECTOR_DENSITY_OVERRIDES = {
    "impermeabilizacao": 0.005,
    "acustica": 0.005,
    "avaliacao_imoveis": 0.005,
    "geotecnia": 0.005,
    "topografia": 0.005,
    "demolicao": 0.005,
}

# Cross-sector exclusions loaded dynamically from YAML per sector.
# Each sector defines what is NOT relevant to it (e.g., engenharia excludes "medicamento").
# This replaces the old universal EXCLUSION_PATTERNS that blocked ALL sectors.
_EXCLUSION_PATTERNS_CACHE: dict[str, list] = {}


def _get_exclusion_patterns_for_sector(sector_keys: set[str] | None = None) -> list:
    """Build compiled exclusion patterns for given sector(s) from YAML config.

    Returns list of compiled regex patterns that should reject editais for these sectors.
    """
    cache_key = ",".join(sorted(sector_keys or {"_default"}))
    if cache_key in _EXCLUSION_PATTERNS_CACHE:
        return _EXCLUSION_PATTERNS_CACHE[cache_key]

    try:
        from intel_sector_loader import get_cross_sector_exclusions
        phrases: set[str] = set()
        for sk in (sector_keys or {"_default"}):
            phrases.update(get_cross_sector_exclusions(sk))

        if not phrases:
            _EXCLUSION_PATTERNS_CACHE[cache_key] = []
            return []

        # Compile each phrase as a case-insensitive regex with word boundaries.
        # The matching in apply_cnae_keyword_gate already strips accents from objeto.
        patterns = []
        for phrase in phrases:
            try:
                patterns.append(re.compile(re.escape(phrase), re.IGNORECASE))
            except re.error:
                continue

        _EXCLUSION_PATTERNS_CACHE[cache_key] = patterns
        return patterns
    except Exception:
        _EXCLUSION_PATTERNS_CACHE[cache_key] = []
        return []


# ============================================================
# ADAPTIVE RATE LIMITER (v1.3 — DescompLicita pattern)
# ============================================================

class AdaptiveRateLimiter:
    """Thread-safe adaptive rate limiter for PNCP API.

    Starts with a short base interval and adjusts dynamically:
    - Fast response (<2s): interval *= decay (gets faster)
    - Slow response (>5s): interval *= growth (slows down)
    - Consecutive timeouts: circuit breaker pauses all threads
    - 429 rate-limit (v1.5): independent aggressive backoff, starts at 2s,
      doubles each retry, max 30s. Tracked separately from other failures.
    """

    def __init__(
        self,
        base_interval: float = _RATE_LIMIT_BASE_S,
        max_interval: float = _RATE_LIMIT_MAX_S,
        slow_threshold: float = _RATE_LIMIT_SLOW_THRESHOLD_S,
        decay: float = _RATE_LIMIT_DECAY,
        growth: float = _RATE_LIMIT_GROWTH,
        cb_threshold: int = _CIRCUIT_BREAKER_THRESHOLD,
        cb_pause: float = _CIRCUIT_BREAKER_PAUSE_S,
        rl_429_initial: float = _RATE_LIMIT_429_INITIAL_S,
        rl_429_growth: float = _RATE_LIMIT_429_GROWTH,
        rl_429_max: float = _RATE_LIMIT_429_MAX_S,
    ):
        self._interval = base_interval
        self._min_interval = base_interval * 0.5
        self._max_interval = max_interval
        self._slow_threshold = slow_threshold
        self._decay = decay
        self._growth = growth
        self._cb_threshold = cb_threshold
        self._cb_pause = cb_pause
        self._consecutive_failures = 0
        # 429-specific state (v1.5)
        self._429_initial = rl_429_initial
        self._429_growth = rl_429_growth
        self._429_max = rl_429_max
        self._total_429_count = 0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Sleep for the current adaptive interval."""
        with self._lock:
            interval = self._interval
        if interval > 0.01:
            time.sleep(interval)

    def record_success(self, response_time: float) -> None:
        """Record a successful request and adjust interval."""
        with self._lock:
            self._consecutive_failures = 0
            if response_time < 2.0:
                # Fast response: speed up
                self._interval = max(self._min_interval, self._interval * self._decay)
            elif response_time > self._slow_threshold:
                # Slow response: slow down
                self._interval = min(self._max_interval, self._interval * self._growth)

    def record_failure(self) -> None:
        """Record a failed request. Triggers circuit breaker if threshold reached."""
        should_pause = False
        with self._lock:
            self._consecutive_failures += 1
            self._interval = min(self._max_interval, self._interval * self._growth)
            if self._consecutive_failures >= self._cb_threshold:
                should_pause = True
                self._consecutive_failures = 0  # Reset counter
        # Circuit breaker pause (outside lock to avoid blocking other threads unnecessarily)
        if should_pause:
            print(f"    ⚡ Circuit breaker: {self._cb_threshold} failures, pausing {self._cb_pause:.0f}s")
            time.sleep(self._cb_pause)

    def record_429(self) -> float:
        """Record a 429 Too Many Requests response.

        Applies aggressive progressive backoff:
          First 429: wait 2s
          Each subsequent 429: double the wait, cap at max 30s

        Returns the new wait interval in seconds.
        """
        wait_time = 0.0
        with self._lock:
            self._total_429_count += 1
            # Progressive backoff: start at initial, double each time, cap at max
            # Use total_429_count to determine backoff level
            self._interval = min(
                self._429_max,
                self._429_initial * (self._429_growth ** (self._total_429_count - 1))
            )
            wait_time = self._interval
            # Reset circuit breaker counter (429 is not a connection failure)
            self._consecutive_failures = 0
        print(f"    ⚡ 429 rate-limit: backoff {wait_time:.1f}s (total 429s: {self._total_429_count})")
        return wait_time

    @property
    def total_429_count(self) -> int:
        with self._lock:
            return self._total_429_count

    @property
    def current_interval(self) -> float:
        with self._lock:
            return self._interval


def _chunk_date_range(data_inicial: str, data_final: str, chunk_days: int = _DATE_CHUNK_DAYS) -> list[tuple[str, str]]:
    """Split a date range into smaller chunks to avoid pagination exhaustion.

    Args:
        data_inicial: Start date in YYYYMMDD format
        data_final: End date in YYYYMMDD format
        chunk_days: Max days per chunk (default: 14)

    Returns:
        List of (start_yyyymmdd, end_yyyymmdd) tuples covering the full range.
    """
    start = datetime.strptime(data_inicial, "%Y%m%d")
    end = datetime.strptime(data_final, "%Y%m%d")
    chunks = []
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        chunks.append((current.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        current = chunk_end + timedelta(days=1)
    return chunks


# ============================================================
# RETRY HELPER
# ============================================================

# Import retry decorator for HTTP call resilience
try:
    from lib.retry import retry_on_failure as _retry_decorator
except ImportError:
    # Fallback: no-op decorator if lib.retry is not available
    def _retry_decorator(**kwargs):  # type: ignore[misc]
        def _noop(func):
            return func
        return _noop


def _api_get_with_retry(
    api: ApiClient,
    url: str,
    params: dict | None = None,
    label: str = "",
    max_retries: int = 2,
    base_delay: float = 1.0,
) -> tuple:
    """Wrapper around api.get() with retry logic for transient failures.

    Retries on:
      - status == "API_FAILED" (network errors, timeouts)
      - Empty data with API status (intermittent PNCP issues)

    Does NOT retry on:
      - Successful responses (status == "API")
      - Non-transient errors (HTTP 400, 404)

    Returns: (data, status) tuple from api.get().
    """
    last_result = (None, "API_FAILED")
    for attempt in range(max_retries + 1):
        data, status = api.get(url, params=params, label=label)
        last_result = (data, status)

        # Success: return immediately
        if status == "API" and data is not None:
            return data, status

        # Transient failure: retry with backoff
        if attempt < max_retries:
            delay = min(base_delay * (2 ** attempt), 30.0)
            print(f"    [retry] {label}: attempt {attempt + 1}/{max_retries}, "
                  f"retrying in {delay:.1f}s (status={status})")
            time.sleep(delay)

    return last_result


def _pncp_direct_get(
    url: str,
    params: dict | None = None,
    label: str = "",
    max_retries: int = 2,
) -> tuple:
    """Direct HTTP GET for PNCP with status code visibility (v1.5).

    Bypasses ApiClient to expose HTTP status codes directly, allowing
    the caller to distinguish 429 Too Many Requests from other failures.

    Returns (data, status, http_status_code).
      status is "API" for success,
              "TOO_MANY_REQUESTS" for HTTP 429,
              "API_FAILED" for other failures/errors.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = _httpx.get(
                url,
                params=params,
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "Extra Consultoria-IntelCollector/1.0"},
            )

            if resp.status_code == 200:
                try:
                    return resp.json(), "API", 200
                except _httpx.JSONDecodeError:
                    if attempt < max_retries:
                        time.sleep(1.0)
                        continue
                    return None, "API_FAILED", 200

            if resp.status_code == 429:
                # Rate-limited: return immediately with special status
                return None, "TOO_MANY_REQUESTS", 429

            if resp.status_code in (500, 502, 503, 504, 422):
                # Transient server error, retry
                if attempt < max_retries:
                    delay = min(1.0 * (2 ** attempt), 30.0)
                    print(f"    [retry] {label}: HTTP {resp.status_code}, retry in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                return None, "API_FAILED", resp.status_code

            # Non-retryable error (4xx except 429)
            return None, "API_FAILED", resp.status_code

        except (_httpx.TimeoutException, _httpx.ConnectError, _httpx.ReadError) as e:
            if attempt < max_retries:
                delay = min(1.0 * (2 ** attempt), 30.0)
                print(f"    [retry] {label}: {type(e).__name__}, retry in {delay:.1f}s")
                time.sleep(delay)
                continue
            return None, "API_FAILED", None

    return None, "API_FAILED", None


# ============================================================
# HELPERS
# ============================================================

def _today() -> datetime:
    return datetime.now(UTC)


def _compute_dedup_hash(edital: dict) -> str:
    """Compute a cross-portal dedup hash based on objeto, valor, uf, and municipio.

    Strips portal-specific prefixes so the same edital published on both PNCP
    and Portal de Compras Públicas produces the same hash and can be deduplicated.
    """
    obj = (edital.get("objeto") or "").lower().strip()
    # Remove portal prefixes injected by PCP
    for prefix in ["[portal de compras públicas] - ", "[portal de compras publicas] - "]:
        if obj.startswith(prefix):
            obj = obj[len(prefix):]
    # Normalize: collapse extra whitespace, remove punctuation noise
    obj = re.sub(r'\s+', ' ', obj).strip()
    valor = str(edital.get("valor_estimado") or 0)
    uf = edital.get("uf") or ""
    municipio = (edital.get("municipio") or "").lower().strip()
    raw = f"{uf}|{municipio}|{valor}|{obj[:150]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Portuguese stop words for semantic dedup (minimal set)
_PT_STOP_WORDS = frozenset({
    "de", "da", "do", "das", "dos", "para", "com", "por", "em",
    "no", "na", "nos", "nas", "ao", "aos", "a", "o", "as", "os", "e", "ou",
})


def _token_overlap(text_a: str, text_b: str) -> float:
    """Compute token overlap ratio between two strings (excluding stop words).

    Returns intersection/union of lowercase word sets (Jaccard similarity).
    """
    words_a = {w for w in text_a.lower().split() if w not in _PT_STOP_WORDS and len(w) > 1}
    words_b = {w for w in text_b.lower().split() if w not in _PT_STOP_WORDS and len(w) > 1}
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def _semantic_dedup(editais: list[dict]) -> list[dict]:
    """Remove semantic duplicates within each UF.

    Two editais are considered semantic duplicates if:
      a. Same cnpj_orgao (same organ)
      b. valor_estimado within +/-15% of each other
      c. Token overlap of objeto > 65%

    When duplicates are found, the earlier one (by publication date) is kept.
    """
    # Group by UF
    by_uf: dict[str, list[dict]] = {}
    for ed in editais:
        uf = ed.get("uf", "XX")
        by_uf.setdefault(uf, []).append(ed)

    removed_ids: set[str] = set()
    n_semantic_dupes = 0

    for uf, uf_editais in by_uf.items():
        n = len(uf_editais)
        if n < 2:
            continue

        for i in range(n):
            ed_a = uf_editais[i]
            id_a = ed_a.get("_id", "")
            if id_a in removed_ids:
                continue

            for j in range(i + 1, n):
                ed_b = uf_editais[j]
                id_b = ed_b.get("_id", "")
                if id_b in removed_ids:
                    continue

                # Condition a: same organ
                cnpj_a = ed_a.get("cnpj_orgao", "")
                cnpj_b = ed_b.get("cnpj_orgao", "")
                if not cnpj_a or cnpj_a != cnpj_b:
                    continue

                # Condition b: valor within +/-15%
                val_a = _safe_float(ed_a.get("valor_estimado")) or 0.0
                val_b = _safe_float(ed_b.get("valor_estimado")) or 0.0
                if val_a > 0 and val_b > 0:
                    ratio = val_a / val_b if val_b > val_a else val_b / val_a
                    if ratio < 0.85:  # More than 15% difference
                        continue
                elif val_a != val_b:
                    # One is 0, other isn't — not similar
                    continue

                # Condition c: token overlap > 65%
                obj_a = ed_a.get("objeto", "")
                obj_b = ed_b.get("objeto", "")
                overlap = _token_overlap(obj_a, obj_b)
                if overlap <= 0.80:
                    continue

                # All 3 conditions met — mark the later one as duplicate
                date_a = ed_a.get("data_publicacao", "")
                date_b = ed_b.get("data_publicacao", "")
                # Keep earlier publication date, remove later
                if date_b < date_a and date_b:
                    # B is earlier — remove A
                    removed_ids.add(id_a)
                    ed_a["_dedup_semantic"] = True
                    n_semantic_dupes += 1
                    break  # A is removed, stop comparing it
                else:
                    # A is earlier or same — remove B
                    removed_ids.add(id_b)
                    ed_b["_dedup_semantic"] = True
                    n_semantic_dupes += 1

    if n_semantic_dupes > 0:
        print(f"  Dedup semantico: {n_semantic_dupes} duplicatas semanticas removidas")
    else:
        print("  Dedup semantico: sem duplicatas semanticas detectadas")

    return [ed for ed in editais if ed.get("_id", "") not in removed_ids]


def _date_compact(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _date_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


# ============================================================
# CHECKPOINT HELPERS (resume / fault-tolerance)
# ============================================================

def _checkpoint_key(cnpj14: str, ufs: list[str], dias: int) -> str:
    """Top-level checkpoint key: {cnpj}_{ufs_sorted}_{dias}."""
    ufs_sorted = ",".join(sorted(ufs))
    return f"{cnpj14}_{ufs_sorted}_{dias}"


def _subkey(mod_code: int, uf: str) -> str:
    return f"mod_{mod_code}_{uf}"


def _load_checkpoint() -> dict:
    """Load checkpoint file from disk. Returns {} on any error."""
    try:
        if _CHECKPOINT_FILE.exists():
            with open(_CHECKPOINT_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_checkpoint(data: dict) -> None:
    """Atomically write checkpoint to disk (tmp → rename)."""
    try:
        _CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CHECKPOINT_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        tmp.replace(_CHECKPOINT_FILE)
    except Exception as e:
        print(f"  WARN: Falha ao salvar checkpoint: {e}")


def _cleanup_old_checkpoints(data: dict) -> dict:
    """Remove top-level keys (and sub-keys) older than _CHECKPOINT_CLEANUP_HOURS."""
    cutoff = _today() - timedelta(hours=_CHECKPOINT_CLEANUP_HOURS)
    cleaned: dict = {}
    for top_key, sub_dict in data.items():
        if not isinstance(sub_dict, dict):
            continue
        # Keep if any sub-key is recent enough
        keep = False
        for sub_val in sub_dict.values():
            if isinstance(sub_val, dict):
                ts_str = sub_val.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    if ts > cutoff:
                        keep = True
                        break
                except Exception:
                    pass
        if keep:
            cleaned[top_key] = sub_dict
    return cleaned


# ============================================================
# STEP 3: DATALAKE SEARCH (preferred) or LIVE PNCP API (fallback)
# ============================================================


def search_datalake_for_intel(
    ufs: list[str],
    dias: int,
    modalidades: dict[int, str],
) -> tuple[list[dict], dict]:
    """Query the local datalake (pncp_raw_bids) instead of hitting the live PNCP API.

    Returns results in the same format as search_pncp_exhaustive() so downstream
    code (CNAE gate, temporal filter, dedup, etc.) works unchanged.

    Falls back gracefully: returns ([], {"datalake_error": msg}) on any failure
    so the caller can retry with the live API.
    """
    from datalake_helper import DatalakeClient

    dl = DatalakeClient()
    if not dl.is_enabled:
        return [], {"datalake_error": dl.init_error or "datalake disabled"}

    print(f"    DataLake search: ufs={ufs}, dias={dias}, "
          f"modalidades={sorted(modalidades.keys()) if modalidades else []}")

    rows, meta = dl.search_bids(
        ufs=list(ufs),
        dias=dias,
        modalidades=sorted(modalidades.keys()) if modalidades else None,
        limit=5000,
        paginate_by_uf_modalidade=True,
        verbose=True,
    )
    if rows is None:
        return [], {"datalake_error": meta.get("datalake_error", "unknown")}

    # Convert datalake rows to intel internal format (same as _parse_pncp_item output)
    all_items: list[dict] = []
    seen_ids: set[str] = set()

    for row in rows:
        parsed = _datalake_row_to_intel(row, modalidades, ufs)
        if parsed is None:
            continue
        dk = parsed["_dedup_key"]
        if dk in seen_ids:
            continue
        seen_ids.add(dk)
        all_items.append(parsed)

    source_meta = {
        "total_raw_api": len(rows),
        "total_after_dedup": len(all_items),
        "pages_fetched": 0,
        "errors": 0,
        "pagination_exhausted": [],
        "source": "datalake",
    }

    return all_items, source_meta


def _datalake_row_to_intel(row: dict, modalidades: dict[int, str], ufs: list[str]) -> dict | None:
    """Convert a search_datalake RPC row to the intel internal format.

    Must produce the same dict shape as _parse_pncp_item().
    """
    pncp_id = row.get("pncp_id") or ""
    if not pncp_id:
        return None

    uf = (row.get("uf") or "").upper()
    if ufs and uf and uf not in ufs:
        return None

    # Parse pncp_id into cnpj/ano/seq: format is "{cnpj}-{unidade}-{seq}/{ano}"
    cnpj_clean = ""
    ano = ""
    seq = ""
    match = re.match(r"^(\d+)-\d+-(\d+)/(\d+)$", pncp_id)
    if match:
        cnpj_clean = match.group(1)
        seq = match.group(2)
        ano = match.group(3)

    objeto = (row.get("objeto_compra") or "").strip()
    orgao = row.get("orgao_razao_social") or ""
    orgao_cnpj = row.get("orgao_cnpj") or cnpj_clean
    municipio = row.get("municipio") or ""
    valor = None
    raw_valor = row.get("valor_total_estimado")
    if raw_valor is not None:
        try:
            valor = float(raw_valor)
        except (TypeError, ValueError):
            pass

    mod_id = row.get("modalidade_id")
    mod_nome = row.get("modalidade_nome") or modalidades.get(mod_id, "")

    # Dates — datalake returns ISO timestamps
    data_pub_raw = str(row.get("data_publicacao") or "")
    data_abertura_raw = str(row.get("data_abertura") or "")
    data_enc_raw = str(row.get("data_encerramento") or "")

    data_publicacao = _parse_date_flexible(data_pub_raw) or ""

    # Link
    if cnpj_clean and ano and seq:
        link = f"https://pncp.gov.br/app/editais/{cnpj_clean}/{ano}/{seq}"
    else:
        link = row.get("link_pncp") or ""

    # Calculate status_temporal (same logic as _parse_pncp_item)
    status_temporal = "SEM_DATA"
    dias_restantes = None
    if data_enc_raw and data_enc_raw != "None":
        try:
            enc_str = data_enc_raw[:19]
            dt_enc = datetime.fromisoformat(enc_str)
            now = datetime.now()
            dias_restantes = (dt_enc.replace(tzinfo=None) - now.replace(tzinfo=None)).days
            if dias_restantes < 0:
                status_temporal = "EXPIRADO"
            elif dias_restantes <= 7:
                status_temporal = "URGENTE"
            elif dias_restantes <= 15:
                status_temporal = "IMINENTE"
            else:
                status_temporal = "PLANEJAVEL"
        except (ValueError, TypeError):
            status_temporal = "SEM_DATA"

    if status_temporal not in ("EXPIRADO",) and data_abertura_raw and data_abertura_raw != "None":
        try:
            ab_str = data_abertura_raw[:19]
            dt_ab = datetime.fromisoformat(ab_str)
            now_ab = datetime.now()
            if dt_ab.replace(tzinfo=None) < now_ab.replace(tzinfo=None):
                status_temporal = "SESSAO_REALIZADA"
        except (ValueError, TypeError):
            pass

    item_id = f"{cnpj_clean}/{ano}/{seq}" if (cnpj_clean and ano and seq) else f"dl/{pncp_id}"

    return {
        "_id": item_id,
        "objeto": objeto,
        "orgao": orgao,
        "cnpj_orgao": orgao_cnpj,
        "uf": uf,
        "municipio": municipio,
        "valor_estimado": valor,
        "modalidade_code": mod_id,
        "modalidade_nome": mod_nome,
        "data_publicacao": data_publicacao,
        "data_abertura_proposta": data_abertura_raw if data_abertura_raw != "None" else "",
        "data_encerramento_proposta": data_enc_raw if data_enc_raw != "None" else "",
        "link_pncp": link,
        "ano_compra": ano,
        "sequencial_compra": seq,
        "_dedup_key": f"{cnpj_clean}/{ano}/{seq}" if (cnpj_clean and ano and seq) else pncp_id,
        "status_temporal": status_temporal,
        "dias_restantes": dias_restantes,
    }


# ============================================================
# STEP 3 (fallback): EXHAUSTIVE LIVE PNCP SEARCH
# ============================================================

def _parse_pncp_item(item: dict, mod_code: int, mod_name: str, ufs: list[str]) -> dict | None:
    """Parse a raw PNCP API item into our internal format. Returns None if UF doesn't match."""
    orgao_entity = item.get("orgaoEntidade") or {}
    cnpj_compra = orgao_entity.get("cnpj") or item.get("cnpjCompra") or ""
    cnpj_clean = re.sub(r"[^0-9]", "", str(cnpj_compra))
    ano = str(item.get("anoCompra") or "")
    seq = str(item.get("sequencialCompra") or "")

    # Parse the raw item into our format
    unidade = item.get("unidadeOrgao") or {}
    uf = (unidade.get("ufSigla") or item.get("ufSigla") or "").upper()

    # UF filter (when not using server-side UF param)
    if ufs and uf and uf not in ufs:
        return None

    objeto = (item.get("objetoCompra") or item.get("objeto") or "").strip()
    orgao = (orgao_entity.get("razaoSocial") or
             unidade.get("nomeUnidade") or
             item.get("nomeOrgao") or "")
    municipio = unidade.get("municipioNome") or ""
    valor = _safe_float(item.get("valorTotalEstimado") or item.get("valorEstimado"))
    modalidade_nome = item.get("modalidadeNome") or mod_name

    # Dates
    data_pub_raw = item.get("dataPublicacaoPncp") or ""
    data_abertura_raw = item.get("dataAberturaProposta") or ""
    data_encerramento_raw = item.get("dataEncerramentoProposta") or ""

    data_publicacao = _parse_date_flexible(data_pub_raw) or ""
    data_abertura = data_abertura_raw  # Keep full ISO for proposals
    data_encerramento = data_encerramento_raw

    # Link
    link_sistema = item.get("linkSistemaOrigem") or ""
    if cnpj_clean and ano and seq:
        link = f"https://pncp.gov.br/app/editais/{cnpj_clean}/{ano}/{seq}"
    elif link_sistema:
        link = link_sistema
    else:
        link = ""

    # Calculate status_temporal
    status_temporal = "SEM_DATA"
    dias_restantes = None
    if data_encerramento_raw:
        try:
            # Parse ISO date (may have timezone)
            enc_str = data_encerramento_raw[:19]  # trim to YYYY-MM-DDTHH:MM:SS
            dt_enc = datetime.fromisoformat(enc_str)
            now = datetime.now()
            dias_restantes = (dt_enc.replace(tzinfo=None) - now.replace(tzinfo=None)).days
            if dias_restantes < 0:
                status_temporal = "EXPIRADO"
            elif dias_restantes <= 7:
                status_temporal = "URGENTE"
            elif dias_restantes <= 15:
                status_temporal = "IMINENTE"
            else:
                status_temporal = "PLANEJAVEL"
        except (ValueError, TypeError):
            status_temporal = "SEM_DATA"

    # Check if session (abertura) already happened — even if encerramento is still in the future
    if status_temporal not in ("EXPIRADO",) and data_abertura_raw:
        try:
            ab_str = data_abertura_raw[:19]  # trim to YYYY-MM-DDTHH:MM:SS
            dt_ab = datetime.fromisoformat(ab_str)
            now_ab = datetime.now()
            if dt_ab.replace(tzinfo=None) < now_ab.replace(tzinfo=None):
                status_temporal = "SESSAO_REALIZADA"
        except (ValueError, TypeError):
            pass  # unparseable date — leave status_temporal unchanged

    return {
        "_id": f"{cnpj_clean}/{ano}/{seq}" if (cnpj_clean and ano and seq) else f"unknown/{uuid.uuid4().hex[:12]}",
        "objeto": objeto,
        "orgao": orgao,
        "cnpj_orgao": cnpj_clean,
        "uf": uf,
        "municipio": municipio,
        "valor_estimado": valor,
        "modalidade_code": mod_code,
        "modalidade_nome": modalidade_nome,
        "data_publicacao": data_publicacao,
        "data_abertura_proposta": data_abertura,
        "data_encerramento_proposta": data_encerramento,
        "link_pncp": link,
        "ano_compra": ano,
        "sequencial_compra": seq,
        "_dedup_key": f"{cnpj_clean}/{ano}/{seq}",
        "status_temporal": status_temporal,
        "dias_restantes": dias_restantes,
    }


def search_pncp_exhaustive(
    api: ApiClient,
    ufs: list[str],
    dias: int,
    modalidades: dict[int, str],
    cnpj14: str = "",
    use_cache: bool = True,
    chunked: bool = False,
    batch_size: int = 1,
) -> tuple[list[dict], dict]:
    """Fetch ALL editais from PNCP for the given UFs, modalidades, and date range.

    v1.3 architecture (DescompLicita pattern):
    - Date chunking: splits range into 14-day windows to avoid pagination exhaustion
    - All (modalidade × UF × chunk) combos dispatched in parallel (ThreadPoolExecutor)
    - Adaptive rate limiting: starts fast (150ms), slows on timeouts, circuit breaker
    - NO keyword filtering: captures everything, deduplicates by organ/year/seq

    v1.5: Chunked execution mode (--chunked).
    When chunked=True, combos are processed in sequential batches (batch_size combos
    per batch) instead of all at once. Each batch has a 5s cool-down between batches
    to reduce PNCP API load and avoid 429 rate-limiting.

    Returns (raw_editais, source_meta).
    """
    data_inicial = _date_compact(_today() - timedelta(days=dias))
    data_final = _date_compact(_today())

    # ── Date chunking: split into 14-day windows ──
    date_chunks = _chunk_date_range(data_inicial, data_final, _DATE_CHUNK_DAYS)

    all_items: list[dict] = []
    seen_ids: set[str] = set()
    items_lock = threading.Lock()   # protects all_items + seen_ids

    source_meta = {
        "total_raw_api": 0,
        "total_after_dedup": 0,
        "pages_fetched": 0,
        "errors": 0,
        "errors_429": 0,          # v1.5: specific 429 count
        "combo_429_suspended": 0,  # v1.5: combos suspended due to excessive 429s
        "pagination_exhausted": [],
        "date_chunks": len(date_chunks),
    }
    # Per-combo 429 counter (shared across workers, v1.5)
    combo_429_lock = threading.Lock()
    combo_429_counts: dict[str, int] = {}
    meta_lock = threading.Lock()   # protects source_meta

    use_per_uf = 1 <= len(ufs) <= 10
    uf_iterations: list[str | None] = list(ufs) if use_per_uf else [None]
    max_pages = PNCP_MAX_PAGES_UF if use_per_uf else PNCP_MAX_PAGES

    # ── Adaptive rate limiter (shared across all workers) ──
    rate_limiter = AdaptiveRateLimiter()

    # ── Checkpoint setup ──
    top_key = _checkpoint_key(cnpj14, ufs, dias) if cnpj14 else ""
    checkpoint: dict = {}
    if use_cache and top_key:
        checkpoint = _load_checkpoint()
    cp_top: dict = checkpoint.get(top_key, {}) if top_key else {}
    cp_lock = threading.Lock()   # protects cp_top + checkpoint writes

    cutoff_ts = _today() - timedelta(hours=_CHECKPOINT_TTL_HOURS)

    def _is_cache_fresh(sub_k: str) -> bool:
        if not use_cache or not top_key:
            return False
        entry = cp_top.get(sub_k)
        if not isinstance(entry, dict):
            return False
        ts_str = entry.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            return ts > cutoff_ts
        except Exception:
            return False

    def _load_from_cache(sub_k: str) -> list[dict]:
        with cp_lock:
            return list(cp_top.get(sub_k, {}).get("items", []))

    def _save_to_cache(sub_k: str, items: list[dict], page_count: int) -> None:
        if not top_key:
            return
        entry = {
            "last_page": page_count,
            "items": items,
            "timestamp": _today().isoformat(),
        }
        with cp_lock:
            cp_top[sub_k] = entry
            checkpoint[top_key] = cp_top
        _save_checkpoint(checkpoint)

    def _fetch_combo(
        mod_code: int, mod_name: str, uf_filter: str | None,
        chunk_start: str, chunk_end: str,
    ) -> tuple[str, int, int, bool]:
        """Worker: fetch all pages for one (modalidade, UF, date_chunk) combo.

        v1.5: Uses direct HTTP for 429 detection. Tracks 429s per combo
        and suspends combo after _PNCP_429_MAX_PER_COMBO (10) consecutive
        429s. Combo suspension is non-fatal — the combo is skipped and
        can be retried in a later chunked batch.

        Returns (label, page_count, item_count, had_error).
        """
        uf_label = uf_filter or "ALL"
        sub_k = f"{_subkey(mod_code, uf_label)}:{chunk_start}"

        # Check checkpoint cache
        if _is_cache_fresh(sub_k):
            cached_items = _load_from_cache(sub_k)
            cached_pages = cp_top.get(sub_k, {}).get("last_page", 0)
            with meta_lock:
                source_meta["pages_fetched"] += cached_pages
                source_meta["total_raw_api"] += len(cached_items)
            with items_lock:
                for parsed in cached_items:
                    dk = parsed.get("_dedup_key", parsed.get("_id", ""))
                    if dk and dk not in seen_ids:
                        seen_ids.add(dk)
                        all_items.append(parsed)
            return (uf_label, cached_pages, len(cached_items), False)

        page_count = 0
        combo_items: list[dict] = []
        local_raw = 0
        error_occurred = False
        combo_429_local = 0  # Track 429s for this combo
        combo_key = _subkey(mod_code, uf_label)

        for page in range(1, max_pages + 1):
            params = {
                "dataInicial": chunk_start,
                "dataFinal": chunk_end,
                "codigoModalidadeContratacao": mod_code,
                "pagina": page,
                "tamanhoPagina": PNCP_MAX_PAGE_SIZE,
            }
            if uf_filter:
                params["uf"] = uf_filter

            # Adaptive rate limiting (replaces fixed time.sleep(0.5))
            if page > 1:
                rate_limiter.wait()

            # v1.5: Use direct HTTP to detect 429 vs other failures
            t0 = time.monotonic()
            data, status, http_code = _pncp_direct_get(
                f"{PNCP_BASE}/contratacoes/publicacao",
                params=params,
                label=f"PNCP mod={mod_code} uf={uf_label} p={page}",
                max_retries=2,
            )
            elapsed = time.monotonic() - t0

            if status == "TOO_MANY_REQUESTS":
                # 429 specific handling: aggressive backoff, per-combo tracking
                combo_429_local += 1
                # Update shared 429 counter
                with combo_429_lock:
                    combo_429_counts[combo_key] = combo_429_counts.get(combo_key, 0) + 1

                with meta_lock:
                    source_meta["errors_429"] = source_meta.get("errors_429", 0) + 1

                wait_time = rate_limiter.record_429()

                # Suspend combo if too many 429s
                if combo_429_local >= _PNCP_429_MAX_PER_COMBO:
                    print(f"    ⚡ Combo suspenso: {_PNCP_429_MAX_PER_COMBO}x 429 "
                          f"mod={mod_code} uf={uf_label} chunk={chunk_start} — "
                          f"reagendado para proximo batch")
                    source_meta["combo_429_suspended"] = source_meta.get("combo_429_suspended", 0) + 1
                    return (uf_label, page_count, len(combo_items), True)

                # Wait the backoff interval before retrying same page
                time.sleep(wait_time)
                # Retry the same page (don't increment page counter)
                continue

            if status != "API" or not data:
                rate_limiter.record_failure()
                with meta_lock:
                    source_meta["errors"] += 1
                error_occurred = True
                break

            rate_limiter.record_success(elapsed)

            items = data if isinstance(data, list) else data.get("data", data.get("resultado", []))
            if not isinstance(items, list) or not items:
                break

            page_count += 1
            local_raw += len(items)

            for item in items:
                parsed = _parse_pncp_item(item, mod_code, mod_name, ufs)
                if parsed is None:
                    continue
                dk = parsed["_dedup_key"]
                with items_lock:
                    if dk in seen_ids:
                        continue
                    seen_ids.add(dk)
                    all_items.append(parsed)
                combo_items.append(parsed)

            if len(items) < PNCP_MAX_PAGE_SIZE:
                break

        with meta_lock:
            source_meta["pages_fetched"] += page_count
            source_meta["total_raw_api"] += local_raw
            if page_count == max_pages:
                source_meta["pagination_exhausted"].append(
                    f"mod={mod_code} uf={uf_label} chunk={chunk_start}"
                )

        # Save checkpoint (even on partial error — preserves what we got)
        if not error_occurred or combo_items:
            _save_to_cache(sub_k, combo_items, page_count)

        return (uf_label, page_count, len(combo_items), error_occurred)

    # ── Build all tasks: modalidade × UF × date_chunk ──
    tasks = []
    for mod_code, mod_name in sorted(modalidades.items()):
        for uf_filter in uf_iterations:
            for chunk_start, chunk_end in date_chunks:
                tasks.append((mod_code, mod_name, uf_filter, chunk_start, chunk_end))

    n_tasks = len(tasks)
    n_workers = min(n_tasks, _PNCP_FETCH_WORKERS)
    print(f"\n  Busca paralela: {n_tasks} combos ({len(modalidades)} modalidades × "
          f"{len(uf_iterations)} UFs × {len(date_chunks)} chunks de {_DATE_CHUNK_DAYS} dias)")
    print(f"  Workers: {n_workers} | Rate limit: {_RATE_LIMIT_BASE_S:.0f}ms base (adaptativo)")

    # ── Dynamic max_pages: reduce when many tasks to cap total requests ──
    if n_tasks > 50:
        effective_max = max(10, 600 // n_tasks)
        if effective_max < max_pages:
            print(f"  Max pages/combo reduzido: {max_pages} → {effective_max} (cap 600 requests)")
            max_pages = effective_max

    # ── Dispatch combos: parallel (default) or chunked (v1.5) ──
    # Track per-modalidade stats for display
    mod_stats: dict[int, dict] = {}
    mod_stats_lock = threading.Lock()

    if chunked:
        # Chunked execution: process N combos per batch sequentially
        # Reduces PNCP API load by staggering batches with 5s cooldown
        print(f"  Chunked mode: {batch_size} combo(s) por batch, delay 5s entre batches")
        completed = 0
        for batch_start in range(0, n_tasks, batch_size):
            batch = tasks[batch_start:batch_start + batch_size]
            with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as pool:
                batch_futures = {
                    pool.submit(_fetch_combo, *task): task
                    for task in batch
                }
                for fut in concurrent.futures.as_completed(batch_futures):
                    task = batch_futures[fut]
                    mod_code, mod_name, uf_filter, chunk_start, chunk_end = task
                    completed += 1
                    try:
                        uf_label, pages, items, had_error = fut.result()
                        with mod_stats_lock:
                            if mod_code not in mod_stats:
                                mod_stats[mod_code] = {"name": mod_name, "pages": 0, "items": 0, "errors": 0}
                            mod_stats[mod_code]["pages"] += pages
                            mod_stats[mod_code]["items"] += items
                            if had_error:
                                mod_stats[mod_code]["errors"] += 1
                    except Exception as exc:
                        print(f"    ERRO: mod={mod_code} uf={uf_filter} chunk={chunk_start}: {exc}")
                        with meta_lock:
                            source_meta["errors"] += 1

            # Progress indicator after each batch
            print(f"  → Batch concluido: {completed}/{n_tasks} combos "
                  f"(rate: {rate_limiter.current_interval*1000:.0f}ms)")

            # Cooldown between batches (unless last batch)
            if batch_start + batch_size < n_tasks:
                print("    Cool-down: 5s antes do proximo batch...")
                time.sleep(5.0)
    else:
        # Default: dispatch ALL combos in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
            future_to_task = {
                pool.submit(_fetch_combo, *task): task
                for task in tasks
            }
            completed = 0
            for fut in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[fut]
                mod_code, mod_name, uf_filter, chunk_start, chunk_end = task
                completed += 1
                try:
                    uf_label, pages, items, had_error = fut.result()
                    with mod_stats_lock:
                        if mod_code not in mod_stats:
                            mod_stats[mod_code] = {"name": mod_name, "pages": 0, "items": 0, "errors": 0}
                        mod_stats[mod_code]["pages"] += pages
                        mod_stats[mod_code]["items"] += items
                        if had_error:
                            mod_stats[mod_code]["errors"] += 1
                except Exception as exc:
                    print(f"    ERRO: mod={mod_code} uf={uf_filter} chunk={chunk_start}: {exc}")
                    with meta_lock:
                        source_meta["errors"] += 1

                # Progress indicator every 10 tasks
                if completed % 10 == 0 or completed == n_tasks:
                    print(f"  → {completed}/{n_tasks} combos concluídos "
                          f"(rate: {rate_limiter.current_interval*1000:.0f}ms)")

    # ── Print per-modalidade summary ──
    for mod_code in sorted(mod_stats):
        ms = mod_stats[mod_code]
        err_note = f" ({ms['errors']} erros)" if ms["errors"] else ""
        source_429_note = ""
        if ms.get("errors_429"):
            source_429_note = f" ({ms['errors_429']}x 429)"
        print(f"    Modalidade {mod_code} ({ms['name']}): {ms['pages']} pages, "
              f"{ms['items']} editais{err_note}{source_429_note}")

    source_meta["total_after_dedup"] = len(all_items)

    # Cleanup stale checkpoint entries
    if top_key and use_cache:
        try:
            cleaned = _cleanup_old_checkpoints(checkpoint)
            if len(cleaned) != len(checkpoint):
                _save_checkpoint(cleaned)
        except Exception:
            pass

    return all_items, source_meta


# ============================================================
# STEP 4: CNAE KEYWORD GATE
# ============================================================

# ── Sector-specific heuristic patterns (data-driven from YAML) ──
# Loaded once at module level. Keys = sector_key, values = compiled regex.
_SECTOR_HEURISTIC_CACHE: dict[str, dict[str, re.Pattern | None]] = {}


def _get_sector_heuristic_patterns(sector_keys: set[str] | None = None) -> dict[str, re.Pattern | None]:
    """Build sector-aware heuristic patterns from intel_sectors_config.yaml.

    Returns dict with keys: strong_compat, weak_compat, strong_incompat.
    Patterns come exclusively from the YAML sector config. If a sector has no
    patterns defined, returns empty (LLM fallback handles ambiguous cases).
    """
    cache_key = ",".join(sorted(sector_keys or {"geral"}))
    if cache_key in _SECTOR_HEURISTIC_CACHE:
        return _SECTOR_HEURISTIC_CACHE[cache_key]

    # Try to load from YAML config
    try:
        from intel_sector_loader import load_intel_sectors_config
        config = load_intel_sectors_config()
        sectors_cfg = config.get("sectors", {})
    except (ImportError, FileNotFoundError):
        sectors_cfg = {}

    # Aggregate patterns from all active sector keys
    compat_pats: list[str] = []
    incompat_pats: list[str] = []
    weak_pats: list[str] = []

    for sk in (sector_keys or {"geral"}):
        sect = sectors_cfg.get(sk, {})
        if not isinstance(sect, dict):
            continue
        hp = sect.get("heuristic_patterns", {})
        if isinstance(hp, dict):
            compat_pats.extend(hp.get("strong_compat", []))
            incompat_pats.extend(hp.get("strong_incompat", []))
            weak_pats.extend(hp.get("weak_compat", []))

    # Build compiled patterns (None if no patterns)
    def _compile_list(pats: list[str]) -> re.Pattern | None:
        if not pats:
            return None
        joined = "|".join(f"({p})" for p in pats)
        return re.compile(joined, re.IGNORECASE)

    result = {
        "strong_compat": _compile_list(compat_pats),
        "weak_compat": _compile_list(weak_pats),
        "strong_incompat": _compile_list(incompat_pats),
    }

    # No hardcoded fallback — YAML heuristic_patterns is the sole source of truth.
    # If YAML has no patterns for a sector, return empty (LLM fallback handles ambiguous cases).

    _SECTOR_HEURISTIC_CACHE[cache_key] = result
    return result


def classify_by_object_heuristic(
    objeto: str,
    cnae_principal_desc: str,
    sector_keys: set[str] | None = None,
) -> str:
    """
    Sector-aware heuristic classifier for editais that didn't match keywords.

    Uses patterns from intel_sectors_config.yaml per sector. Falls back to
    hardcoded construction patterns only for engenharia sectors.

    Returns: 'COMPATIVEL', 'INCOMPATIVEL', or 'NEEDS_REVIEW'
    """
    obj_lower = (objeto or '').lower()
    pats = _get_sector_heuristic_patterns(sector_keys)

    has_strong_compat = bool(pats["strong_compat"] and pats["strong_compat"].search(obj_lower))
    has_weak_compat = bool(pats["weak_compat"] and pats["weak_compat"].search(obj_lower))
    has_strong_incompat = bool(pats["strong_incompat"] and pats["strong_incompat"].search(obj_lower))

    if has_strong_compat and not has_strong_incompat:
        return 'COMPATIVEL'
    if has_strong_incompat and not has_strong_compat:
        return 'INCOMPATIVEL'
    if has_weak_compat and not has_strong_incompat:
        return 'COMPATIVEL'
    return 'NEEDS_REVIEW'


def apply_cnae_keyword_gate(
    editais: list[dict],
    keywords: list[str],
    keyword_patterns: list[re.Pattern],
    sector_key: str,
    cnae_prefix: str,
    all_cnae_prefixes: set[str] | None = None,
    all_sector_keys: set[str] | None = None,
    confidence_threshold: float = 0.35,
) -> None:
    """Classify each edital as cnae_compatible or not. Mutates in place.

    Uses sector keywords + CNAE refinements for matching.
    All editais pass through -- we just flag them.
    When multiple CNAEs are provided, an edital is only excluded if it's
    incompatible with ALL CNAEs (not just the primary one).

    Computes a probabilistic cnae_confidence (0.0-1.0) for each edital:
      - Base from keyword density (caps at 60%)
      - Heuristic bonus (+20% strong_compatible, +10% weak_compatible)
      - Exclusion penalty (-30% for partial exclusion pattern match)
      - CNAE match bonus (+10% if objeto contains company CNAE description words)

    cnae_compatible is derived from cnae_confidence >= confidence_threshold.
    """
    _all_prefixes = all_cnae_prefixes or {cnae_prefix}
    _all_sectors = all_sector_keys or {sector_key}

    # Aggregate CNAE-specific exclude patterns from ALL CNAEs
    # An exclude only applies if it comes from the PRIMARY CNAE —
    # secondary CNAEs ADD coverage, they don't restrict it
    cnae_refinements = CNAE_KEYWORD_REFINEMENTS.get(cnae_prefix, {})
    exclude_terms = cnae_refinements.get("exclude_patterns", [])
    exclude_patterns = _compile_keyword_patterns(exclude_terms) if exclude_terms else []

    # CNAE-object incompatibility: only reject if ALL company CNAEs are incompatible
    # Build per-prefix compiled patterns
    per_cnae_incompat: dict[str, list[re.Pattern]] = {}
    for prefix in _all_prefixes:
        pats = CNAE_INCOMPATIBLE_OBJECTS.get(prefix, [])
        compiled = []
        for pat_str in pats:
            try:
                compiled.append(re.compile(pat_str, re.IGNORECASE))
            except re.error:
                pass
        if compiled:
            per_cnae_incompat[prefix] = compiled

    stats = {"compatible": 0, "incompatible": 0, "needs_llm": 0, "excluded_pattern": 0}

    for ed in editais:
        objeto = ed.get("objeto", "")
        objeto_lower = _strip_accents(objeto.lower())

        if not objeto_lower.strip():
            ed["cnae_compatible"] = False
            ed["cnae_confidence"] = 0.0
            ed["keyword_density"] = 0.0
            ed["match_keywords"] = []
            ed["needs_llm_review"] = True
            ed["exclusion_reason"] = "objeto vazio"
            stats["incompatible"] += 1
            stats["needs_llm"] += 1
            continue

        # Check hard exclusions (sector-level)
        exclusion = _check_hard_exclusions(objeto_lower, sector_key)
        if exclusion:
            ed["cnae_compatible"] = False
            ed["cnae_confidence"] = 0.0
            ed["keyword_density"] = 0.0
            ed["match_keywords"] = []
            ed["needs_llm_review"] = False
            ed["exclusion_reason"] = f"hard_exclusion: {exclusion}"
            stats["incompatible"] += 1
            continue

        # Check CNAE-object incompatibility — only reject if ALL CNAEs are incompatible
        if per_cnae_incompat:
            all_incompatible = True
            incompat_detail = ""
            for prefix, cpats in per_cnae_incompat.items():
                prefix_hit = False
                for cpat in cpats:
                    if cpat.search(objeto_lower):
                        prefix_hit = True
                        incompat_detail = cpat.pattern
                        break
                if not prefix_hit:
                    all_incompatible = False
                    break
            # Also compatible if some CNAEs have NO incompatibility patterns at all
            cnaes_without_rules = _all_prefixes - set(per_cnae_incompat.keys())
            if cnaes_without_rules:
                all_incompatible = False
            if all_incompatible:
                ed["cnae_compatible"] = False
                ed["cnae_confidence"] = 0.0
                ed["keyword_density"] = 0.0
                ed["match_keywords"] = []
                ed["needs_llm_review"] = False
                ed["exclusion_reason"] = f"cnae_incompatible_all: {incompat_detail}"
                stats["incompatible"] += 1
                continue

        # Check CNAE-refinement exclude patterns
        exclude_hit = False
        for ep in exclude_patterns:
            if ep.search(objeto_lower):
                exclude_hit = True
                break
        if exclude_hit:
            ed["cnae_compatible"] = False
            ed["cnae_confidence"] = 0.0
            ed["keyword_density"] = 0.0
            ed["match_keywords"] = []
            ed["needs_llm_review"] = False
            ed["exclusion_reason"] = "cnae_refinement_exclusion"
            stats["incompatible"] += 1
            continue

        # Keyword matching
        matched_kws = []
        for kw in keywords:
            kw_lower = _strip_accents(kw.lower().strip())
            if not kw_lower:
                continue
            # Simple word presence check for the match_keywords list
            if kw_lower in objeto_lower:
                matched_kws.append(kw)

        # Density via compiled patterns (more accurate, word-boundary)
        density = _compute_keyword_density(objeto_lower, keyword_patterns)

        # ── Probabilistic confidence scoring ──
        density_threshold = SECTOR_DENSITY_OVERRIDES.get(sector_key, INTEL_DENSITY_MIN)

        # Base confidence from keyword density (caps at 60%)
        confidence = min(1.0, density / density_threshold * 0.6) if density_threshold > 0 else 0.0

        # Heuristic bonus: check object classification (sector-aware)
        _cnae_desc = ed.get("cnae_principal_descricao") or ""
        _heuristic = classify_by_object_heuristic(objeto, _cnae_desc, sector_keys=all_sector_keys)
        heuristic_label = None
        if _heuristic == 'COMPATIVEL':
            # Determine strong vs weak using sector-aware patterns
            _obj_lower_h = (objeto or '').lower()
            _pats = _get_sector_heuristic_patterns(all_sector_keys)
            if _pats["strong_compat"] and _pats["strong_compat"].search(_obj_lower_h):
                confidence += 0.20  # strong_compatible
                heuristic_label = "strong_compatible"
            else:
                confidence += 0.10  # weak_compatible
                heuristic_label = "weak_compatible"

        # Exclusion pattern penalty: -30% for partial match (when not a full reject)
        _partial_exclusion_hit = False
        _sector_exclusions = _get_exclusion_patterns_for_sector(_all_sectors)
        if len(matched_kws) > 0:  # Has some keywords, so not a full reject candidate
            for _excl_pat in _sector_exclusions:
                if _excl_pat.search(objeto_lower):
                    confidence -= 0.30
                    _partial_exclusion_hit = True
                    break

        # CNAE match bonus: +10% if objeto contains company CNAE description words
        if _cnae_desc:
            _cnae_words = {w.lower() for w in _cnae_desc.split() if len(w) > 3}
            _obj_words = set(objeto_lower.split())
            if _cnae_words and _cnae_words & _obj_words:
                confidence += 0.10

        # Clamp to [0.0, 1.0]
        confidence = max(0.0, min(1.0, confidence))

        # ── Compatibility gate (derived from confidence) ──
        # Legacy check: at least 1 keyword match with density >= threshold
        is_compatible_legacy = len(matched_kws) >= 1 and density >= density_threshold
        # New: confidence-based
        is_compatible = confidence >= confidence_threshold or is_compatible_legacy

        ed["cnae_confidence"] = round(confidence, 4)
        ed["cnae_compatible"] = is_compatible
        ed["keyword_density"] = round(density, 4)
        ed["match_keywords"] = matched_kws
        ed["needs_llm_review"] = not is_compatible and len(matched_kws) == 0
        ed["exclusion_reason"] = None if is_compatible else (
            "zero_keyword_match" if len(matched_kws) == 0 else f"low_density_{density:.4f}"
        )

        # Exclusion pattern check: reject obviously incompatible editais BEFORE LLM review.
        # Only applies to zero-keyword-match editais that would otherwise be sent to LLM.
        if ed["needs_llm_review"]:
            for _excl_pat in _sector_exclusions:
                if _excl_pat.search(objeto_lower):
                    ed["cnae_compatible"] = False
                    ed["cnae_confidence"] = 0.0
                    ed["needs_llm_review"] = False
                    ed["exclusion_reason"] = f"exclusion_pattern: {_excl_pat.pattern}"
                    stats["excluded_pattern"] += 1
                    break

        # Secondary heuristic classifier: resolve remaining needs_llm_review editais.
        if ed["needs_llm_review"]:
            if _heuristic == 'COMPATIVEL':
                ed["cnae_compatible"] = True
                ed["needs_llm_review"] = False
                ed["gate2_decision"] = {
                    "compatible": True,
                    "reason": "COMPATIVEL_HEURISTIC",
                    "heuristic_strength": heuristic_label or "compatible",
                    "cnae_confidence": ed["cnae_confidence"],
                    "keyword_density": ed["keyword_density"],
                    "match_keywords": ed["match_keywords"][:5],
                    "timestamp": _today().isoformat(),
                }
                stats["compatible"] += 1
                stats["needs_llm_heuristic"] = stats.get("needs_llm_heuristic", 0) + 1
                continue
            elif _heuristic == 'INCOMPATIVEL':
                ed["cnae_compatible"] = False
                ed["cnae_confidence"] = max(0.0, ed["cnae_confidence"])
                ed["needs_llm_review"] = False
                ed["gate2_decision"] = {
                    "compatible": False,
                    "reason": "INCOMPATIVEL_HEURISTIC",
                    "cnae_confidence": ed["cnae_confidence"],
                    "keyword_density": ed["keyword_density"],
                    "match_keywords": ed["match_keywords"][:5],
                    "timestamp": _today().isoformat(),
                }
                stats["incompatible"] += 1
                stats["needs_llm_heuristic"] = stats.get("needs_llm_heuristic", 0) + 1
                continue
            # else: NEEDS_REVIEW — keep needs_llm_review=True, let LLM decide

        ed["gate2_decision"] = {
            "compatible": ed["cnae_compatible"],
            "reason": ed.get("exclusion_reason", "keyword_match" if ed["cnae_compatible"] else "low_density"),
            "cnae_confidence": ed["cnae_confidence"],
            "keyword_density": ed["keyword_density"],
            "match_keywords": ed["match_keywords"][:5],  # top 5 matches
            "timestamp": _today().isoformat(),
        }

        if is_compatible:
            stats["compatible"] += 1
        else:
            stats["incompatible"] += 1
            if ed["needs_llm_review"]:
                stats["needs_llm"] += 1

    _heuristic_total = stats.get("needs_llm_heuristic", 0)
    _heuristic_compat = sum(
        1 for ed in editais
        if ed.get("gate2_decision", {}).get("reason") == "COMPATIVEL_HEURISTIC"
    )
    _heuristic_incompat = _heuristic_total - _heuristic_compat
    print()
    print(
        "  CNAE Gate: %d compativeis, %d incompativeis, "
        "%d excluidos por padrao, %d precisam LLM review (threshold=%.0f%%)" % (
            stats['compatible'], stats['incompatible'],
            stats['excluded_pattern'], stats['needs_llm'],
            confidence_threshold * 100,
        )
    )
    if _heuristic_total:
        print(f"  Heuristic classifier: {_heuristic_compat} COMPATIVEL, "
              f"{_heuristic_incompat} INCOMPATIVEL "
              f"(de {_heuristic_total} restantes)")
        print("  Remaining needs_llm_review: 0")


# ============================================================
# STEP 4a: LLM FALLBACK FOR UNKNOWN SECTORS
# ============================================================

def _llm_classify_edital_relevance(
    cnae_description: str,
    objeto: str,
    model: str = "gpt-4.1-nano",
    timeout_s: float = 10.0,
) -> bool | None:
    """Use LLM to classify whether an edital is relevant for a given CNAE.

    Returns: True (relevant), False (not relevant), None (LLM failure).
    Fallback = None (caller decides: zero noise = reject).
    """
    try:
        from openai import OpenAI
    except ImportError:
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    prompt = (
        f"Você é um classificador de licitações públicas brasileiras.\n\n"
        f"A empresa tem o seguinte CNAE: {cnae_description}\n\n"
        f"O edital tem o seguinte objeto: {objeto}\n\n"
        f"O edital é relevante para uma empresa com esse CNAE?\n"
        f"Responda APENAS \"SIM\" ou \"NAO\" (sem acentos, sem explicação)."
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0,
            timeout=timeout_s,
        )
        answer = (response.choices[0].message.content or "").strip().upper()
        if "SIM" in answer:
            return True
        if "NAO" in answer or "NÃO" in answer:
            return False
        return None
    except Exception:
        return None


def apply_llm_fallback_gate(
    editais: list[dict],
    cnae_description: str,
    sector_key: str,
    max_concurrent: int = 5,
    model: str = "gpt-4.1-nano",
) -> dict[str, int]:
    """Apply LLM classification to editais with low confidence, any sector.

    Classifies editais with needs_llm_review=True using GPT.
    Now sector-agnostic: runs for ANY sector when there are ambiguous editais.
    Mutates editais in place.

    Returns: stats dict with counts.
    """
    stats = {"llm_reviewed": 0, "llm_accepted": 0, "llm_rejected": 0, "llm_failed": 0}

    # LLM fallback now applies to ANY sector with low-confidence editais
    needs_review = [ed for ed in editais if ed.get("needs_llm_review")]
    if not needs_review:
        return stats

    # Check if LLM is available
    try:
        from intel_sector_loader import get_llm_fallback_config
        llm_config = get_llm_fallback_config()
    except (ImportError, FileNotFoundError):
        llm_config = {"enabled": True, "model": model, "on_failure": "reject"}

    if not llm_config.get("enabled", True):
        print("  LLM fallback: desabilitado via config")
        return stats

    use_model = llm_config.get("model", model)
    on_failure = llm_config.get("on_failure", "reject")

    print(f"  LLM fallback: classificando {len(needs_review)} editais ambiguos "
          f"(setor={sector_key}, CNAE={cnae_description[:60]}...)")

    # Use ThreadPoolExecutor for parallel LLM calls
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_ed = {}
        for ed in needs_review:
            objeto = ed.get("objeto", "")
            future = executor.submit(
                _llm_classify_edital_relevance,
                cnae_description, objeto, use_model,
            )
            future_to_ed[future] = ed

        for future in concurrent.futures.as_completed(future_to_ed):
            ed = future_to_ed[future]
            stats["llm_reviewed"] += 1
            result = future.result()

            if result is True:
                ed["cnae_compatible"] = True
                ed["needs_llm_review"] = False
                ed["cnae_confidence"] = 0.50  # moderate confidence from LLM
                ed["exclusion_reason"] = None
                ed["gate2_decision"] = {
                    "compatible": True,
                    "reason": "LLM_FALLBACK_ACCEPT",
                    "cnae_description": cnae_description[:100],
                    "model": use_model,
                    "timestamp": _today().isoformat(),
                }
                stats["llm_accepted"] += 1
            elif result is False:
                ed["cnae_compatible"] = False
                ed["needs_llm_review"] = False
                ed["cnae_confidence"] = 0.0
                ed["exclusion_reason"] = "llm_fallback_reject"
                ed["gate2_decision"] = {
                    "compatible": False,
                    "reason": "LLM_FALLBACK_REJECT",
                    "cnae_description": cnae_description[:100],
                    "model": use_model,
                    "timestamp": _today().isoformat(),
                }
                stats["llm_rejected"] += 1
            else:
                # LLM failure: apply on_failure policy
                stats["llm_failed"] += 1
                if on_failure == "reject":
                    ed["cnae_compatible"] = False
                    ed["needs_llm_review"] = False
                    ed["cnae_confidence"] = 0.0
                    ed["exclusion_reason"] = "llm_fallback_failure_reject"
                    stats["llm_rejected"] += 1
                # else: keep needs_llm_review=True (pass-through)

    print(f"  LLM fallback: {stats['llm_accepted']} aceitos, "
          f"{stats['llm_rejected']} rejeitados, {stats['llm_failed']} falhas")
    return stats


# ============================================================
# STEP 1b-extra: TCU DUE DILIGENCE (v1.4 — free, no auth)
# ============================================================

_TCU_API_BASE = "https://api-certidoes.apps.tcu.gov.br/api"
_TCU_INIDONEOS_URL = "https://contas.tcu.gov.br/inidoneos/api/rest/inidoneo"


def _collect_tcu_due_diligence(api: ApiClient, cnpj14: str) -> dict:
    """Query TCU APIs for company due diligence (inidôneos + certidões APF).

    Both APIs are free and require no authentication.
    Returns dict with 'inidoneo', 'certidoes', 'certidoes_irregulares' keys
    and '_tcu_status' reflecting API health.

    v1.5: Sets TCU_INDISPONIVEL on failure so downstream knows data is missing
    due to API unavailability (not absence of records).
    """
    now_iso = _today().isoformat()
    result: dict[str, Any] = {
        "inidoneo": False,
        "inidoneo_detalhes": None,
        "certidoes": [],
        "certidoes_irregulares": False,
        "_source": "tcu_api",
        "_tcu_status": "OK",
    }

    # 1) Check inidôneos (declared ineligible by TCU)
    try:
        data, status = _api_get_with_retry(
            api,
            _TCU_INIDONEOS_URL,
            params={"cpfcnpj": cnpj14},
            label="TCU inidoneos",
            max_retries=1,
        )
        if status == "API" and data:
            items = data if isinstance(data, list) else data.get("items", [])
            if items:
                result["inidoneo"] = True
                result["inidoneo_detalhes"] = [
                    {
                        "nome": item.get("nome", ""),
                        "processo": item.get("processo", ""),
                        "deliberacao": item.get("deliberacao", ""),
                        "data_final": item.get("dataFinal", ""),
                    }
                    for item in (items[:5] if isinstance(items, list) else [])
                ]
        else:
            result["_tcu_status"] = "TCU_INDISPONIVEL"
            result["_tcu_status_detail"] = "API de inidoneos retornou status nao-OK"
            result["_tcu_timestamp"] = now_iso
    except Exception as exc:
        print(f"    WARN: TCU inidoneos falhou: {exc}")
        result["_tcu_status"] = "TCU_INDISPONIVEL"
        result["_tcu_status_detail"] = f"Excecao: {exc}"[:200]
        result["_tcu_timestamp"] = now_iso

    # 2) Certidões APF (consolidated check: TCU + CNJ + CGU CEIS + CGU CNEP)
    try:
        data, status = _api_get_with_retry(
            api,
            f"{_TCU_API_BASE}/certidoes/{cnpj14}",
            label="TCU certidoes APF",
            max_retries=1,
        )
        if status == "API" and isinstance(data, dict):
            certidoes_raw = data.get("certidoes", [])
            for cert in certidoes_raw:
                cert_entry = {
                    "emissor": cert.get("emissor", ""),
                    "tipo": cert.get("tipo", ""),
                    "situacao": cert.get("situacao", ""),
                }
                result["certidoes"].append(cert_entry)
                if cert.get("situacao") and cert["situacao"] != "NADA_CONSTA":
                    result["certidoes_irregulares"] = True
        else:
            result["_tcu_status"] = "TCU_INDISPONIVEL"
            result["_tcu_status_detail"] = "API de certidoes retornou status nao-OK"
            result["_tcu_timestamp"] = now_iso
    except Exception as exc:
        print(f"    WARN: TCU certidoes falhou: {exc}")
        result["_tcu_status"] = "TCU_INDISPONIVEL"
        result["_tcu_status_detail"] = f"Excecao: {exc}"[:200]
        result["_tcu_timestamp"] = now_iso

    return result


# ============================================================
# STEP 4b: COMPETITIVE INTELLIGENCE PER ORGAN
# ============================================================

def collect_competitive_intel(
    api: ApiClient,
    editais: list[dict],
    meses: int = 24,
    keywords: list[str] | None = None,
) -> None:
    """Collect competitive intelligence for each unique organ in the top editais.

    Queries PNCP /v1/contratos per organ CNPJ to find historical suppliers,
    compute concentration metrics (HHI), and assess competition level.

    FILTERS contracts by sector keywords (objetoContrato) before computing
    competitive metrics, so that top_suppliers, HHI, and predicted_bidders
    reflect only suppliers in the same industry as the target company.

    Mutates editais in place, adding 'competitive_intel' to each edital.
    Results are cached per organ CNPJ with a 7-day TTL.

    Args:
        api: ApiClient instance for HTTP requests.
        editais: List of edital dicts (must have 'cnpj_orgao').
        meses: Lookback period in months (default 24, split into yearly windows).
        keywords: Sector keywords for filtering contracts by objeto.
                  If None or empty, falls back to unfiltered (legacy behavior).
    """
    # Only process cnae_compatible editais
    compatible = [ed for ed in editais if ed.get("cnae_compatible")]
    if not compatible:
        print("  Competitive intel: nenhum edital compativel, pulando.")
        return

    # Group by cnpj_orgao, deduplicate
    organ_to_editais: dict[str, list[dict]] = {}
    for ed in compatible:
        cnpj = ed.get("cnpj_orgao", "")
        if cnpj and len(cnpj) >= 11:  # Valid CNPJ length
            organ_to_editais.setdefault(cnpj, []).append(ed)

    # Limit to top organs by edital count (then by value)
    organ_ranked = sorted(
        organ_to_editais.keys(),
        key=lambda c: (
            len(organ_to_editais[c]),
            sum(_safe_float(e.get("valor_estimado")) or 0 for e in organ_to_editais[c]),
        ),
        reverse=True,
    )
    organs_to_query = organ_ranked[:_COMPETITIVE_MAX_ORGANS]

    print(f"  Orgaos unicos: {len(organ_to_editais)}, consultando top {len(organs_to_query)}")

    # Load cache
    cache: dict = {}
    try:
        cache = _load_json_cache(_COMPETITIVE_CACHE_FILE)
    except Exception:
        pass

    now = _today()
    results_lock = threading.Lock()
    organ_results: dict[str, dict] = {}  # cnpj -> intel dict
    counters = {"cached": 0, "fetched": 0, "failed": 0}
    counter_lock = threading.Lock()

    def _is_cache_valid(entry: dict) -> bool:
        ts_str = entry.get("_cached_at", "")
        if not ts_str:
            return False
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            return (now - ts).days < _COMPETITIVE_CACHE_TTL_DAYS
        except Exception:
            return False

    def _build_date_windows(meses: int) -> list[tuple[str, str]]:
        """Build yearly date windows (max 365 days per PNCP query).

        Returns list of (dataInicial, dataFinal) pairs in YYYYMMDD format.
        """
        windows: list[tuple[str, str]] = []
        end = now
        total_days = meses * 30  # Approximate
        remaining = total_days

        while remaining > 0:
            window_days = min(remaining, 365)
            start = end - timedelta(days=window_days)
            windows.append((_date_compact(start), _date_compact(end)))
            end = start
            remaining -= window_days

        return windows

    # ── Sector keyword filter ──
    kw_patterns: list[re.Pattern] = []
    if keywords:
        for kw in keywords:
            kw_clean = kw.lower().strip()
            if kw_clean and len(kw_clean) >= 3:
                try:
                    kw_patterns.append(re.compile(r'\b' + re.escape(kw_clean) + r'\b', re.IGNORECASE))
                except re.error:
                    continue

    def _match_sector(objeto: str) -> bool:
        """Check if objeto matches any sector keyword (word-boundary)."""
        if not kw_patterns or not objeto:
            return False
        objeto_lower = objeto.lower()
        return any(pat.search(objeto_lower) for pat in kw_patterns)

    def _fetch_organ_contracts(cnpj_orgao: str) -> dict | None:
        """Fetch all contracts for a single organ, merging yearly windows."""
        # Check cache first — BUT skip when sector keywords active (need fresh filtered data)
        cached = cache.get(cnpj_orgao)
        if cached and not kw_patterns and _is_cache_valid(cached):
            with counter_lock:
                counters["cached"] += 1
            return cached

        windows = _build_date_windows(meses)
        all_contracts: list[dict] = []
        seen_ids: set[str] = set()

        for data_inicial, data_final in windows:
            page = 1
            max_pages = 20  # Safety limit per window

            while page <= max_pages:
                params = {
                    "cnpjOrgao": cnpj_orgao,
                    "dataInicial": data_inicial,
                    "dataFinal": data_final,
                    "pagina": page,
                    "tamanhoPagina": 50,
                }

                data, status = _api_get_with_retry(
                    api,
                    f"{PNCP_BASE}/contratos",
                    params=params,
                    label=f"Contratos orgao={cnpj_orgao[:8]}.. p={page}",
                    max_retries=1,
                )

                if status != "API" or not data:
                    break

                # Handle response structure
                items = []
                if isinstance(data, dict):
                    items = data.get("data", [])
                    if not isinstance(items, list):
                        items = []
                elif isinstance(data, list):
                    items = data

                if not items:
                    break

                for item in items:
                    ctrl = item.get("numeroControlePNCP", "")
                    if ctrl and ctrl in seen_ids:
                        continue
                    if ctrl:
                        seen_ids.add(ctrl)

                    contract = {
                        "fornecedor": item.get("nomeRazaoSocialFornecedor", ""),
                        "cnpj_fornecedor": item.get("niFornecedor", ""),
                        "valor_inicial": _safe_float(item.get("valorInicial")),
                        "valor_global": _safe_float(item.get("valorGlobal")),
                        "objeto": item.get("objetoContrato", ""),
                        "categoria": item.get("categoriaProcesso", ""),
                        "data_assinatura": item.get("dataAssinatura", ""),
                        "numero_controle": ctrl,
                    }
                    all_contracts.append(contract)

                # Check if more pages exist
                total_pages = 1
                if isinstance(data, dict):
                    total_pages = data.get("totalPaginas", 1)

                if page >= total_pages or len(items) < 50:
                    break

                page += 1
                time.sleep(0.3)  # Rate limit within pagination

            time.sleep(0.5)  # Rate limit between windows

        # Apply sector filter if keywords available
        sector_contracts = all_contracts
        if kw_patterns:
            sector_contracts = [c for c in all_contracts if _match_sector(c.get("objeto", ""))]
            if sector_contracts:
                print(f"    → {cnpj_orgao[:8]}..: {len(sector_contracts)}/{len(all_contracts)} contratos do setor")
            else:
                print(f"    → {cnpj_orgao[:8]}..: 0/{len(all_contracts)} contratos do setor — usando todos")

        result = _compute_intel_metrics(
            sector_contracts if sector_contracts else all_contracts,
            cnpj_orgao,
            total_unfiltered=len(all_contracts),
        )
        result["_cached_at"] = now.isoformat()

        with counter_lock:
            counters["fetched"] += 1

        return result

    def _compute_intel_metrics(
        contracts: list[dict],
        cnpj_orgao: str,
        total_unfiltered: int = 0,
    ) -> dict:
        """Compute competitive intelligence metrics from a list of contracts.

        When sector keywords are active, contracts are pre-filtered and
        total_unfiltered reflects the original (unfiltered) count.
        """
        if not contracts:
            return {
                "cnpj_orgao": cnpj_orgao,
                "total_contracts": 0,
                "total_contracts_unfiltered": total_unfiltered,
                "total_value": 0.0,
                "unique_suppliers": 0,
                "top_suppliers": [],
                "hhi": 0.0,
                "competition_level": "SEM_DADOS",
            }

        # Group by supplier CNPJ
        supplier_data: dict[str, dict] = {}  # cnpj -> {name, count, value}
        total_value = 0.0

        for c in contracts:
            cnpj_f = (c.get("cnpj_fornecedor") or "").strip()
            if not cnpj_f:
                continue
            nome = c.get("fornecedor", "")
            valor = _safe_float(c.get("valor_global")) or _safe_float(c.get("valor_inicial")) or 0.0
            total_value += valor

            if cnpj_f not in supplier_data:
                supplier_data[cnpj_f] = {"nome": nome, "cnpj": cnpj_f, "count": 0, "value": 0.0}
            supplier_data[cnpj_f]["count"] += 1
            supplier_data[cnpj_f]["value"] += valor
            # Keep the most recent name
            if nome:
                supplier_data[cnpj_f]["nome"] = nome

        unique_count = len(supplier_data)

        # Top 5 suppliers by contract count (tie-break by value)
        suppliers_ranked = sorted(
            supplier_data.values(),
            key=lambda s: (s["count"], s["value"]),
            reverse=True,
        )
        top_suppliers = [
            {
                "nome": s["nome"],
                "cnpj": s["cnpj"],
                "contratos": s["count"],
                "valor_total": round(s["value"], 2),
                "share_pct": round(s["value"] / total_value * 100, 1) if total_value > 0 else 0,
            }
            for s in suppliers_ranked[:5]
        ]

        # HHI (Herfindahl-Hirschman Index) based on value share
        hhi = 0.0
        if total_value > 0:
            for s in supplier_data.values():
                share = s["value"] / total_value
                hhi += share * share
        hhi = round(hhi, 4)

        # Competition level based on sector-filtered unique supplier count
        if unique_count <= 2:
            competition_level = "BAIXA"
        elif unique_count <= 5:
            competition_level = "MEDIA"
        elif unique_count <= 10:
            competition_level = "ALTA"
        else:
            competition_level = "MUITO_ALTA"

        # Price benchmark: spread between valor_global and valor_inicial
        # (already sector-filtered via contracts list)
        descontos: list[float] = []
        for c in contracts:
            v_global = _safe_float(c.get("valor_global")) or 0
            v_inicial = _safe_float(c.get("valor_inicial")) or 0
            if v_global > 0 and v_inicial > 0 and v_global != v_inicial:
                spread = 1.0 - (v_inicial / v_global)
                if -0.5 < spread < 0.8:  # Sanity check
                    descontos.append(spread)

        price_benchmark: dict[str, Any] = {}
        if len(descontos) >= 3:
            descontos_sorted = sorted(descontos)
            n = len(descontos_sorted)
            price_benchmark = {
                "desconto_mediano": round(statistics.median(descontos), 4),
                "desconto_p25": round(descontos_sorted[n // 4], 4),
                "desconto_p75": round(descontos_sorted[3 * n // 4], 4),
                "contratos_analisados": n,
            }

        # Predicted bidders — estimate from sector-filtered suppliers
        # Cap at unique_count (not flat 15) for realistic forecast
        predicted_bidders = max(2, min(unique_count, 15))

        return {
            "cnpj_orgao": cnpj_orgao,
            "total_contracts": len(contracts),
            "total_contracts_unfiltered": total_unfiltered,
            "total_value": round(total_value, 2),
            "unique_suppliers": unique_count,
            "top_suppliers": top_suppliers,
            "hhi": hhi,
            "competition_level": competition_level,
            "price_benchmark": price_benchmark,
            "predicted_bidders": predicted_bidders,
        }

    def _fetch_with_error_handling(cnpj_orgao: str) -> tuple[str, dict | None]:
        try:
            result = _fetch_organ_contracts(cnpj_orgao)
            return cnpj_orgao, result
        except Exception as exc:
            print(f"    WARN: Falha ao coletar contratos para orgao {cnpj_orgao}: {exc}")
            with counter_lock:
                counters["failed"] += 1
            return cnpj_orgao, None

    # Fetch in parallel (v1.4: increased from 3 to 6 workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=_COMPETITIVE_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_with_error_handling, cnpj): cnpj
            for cnpj in organs_to_query
        }
        for fut in concurrent.futures.as_completed(futures):
            cnpj_orgao, result = fut.result()
            if result is not None:
                with results_lock:
                    organ_results[cnpj_orgao] = result

    # Save updated cache
    for cnpj, result in organ_results.items():
        cache[cnpj] = result
    try:
        _save_json_cache(_COMPETITIVE_CACHE_FILE, cache)
    except Exception as e:
        print(f"  WARN: Falha ao salvar competitive cache: {e}")

    # Assign results to editais
    assigned = 0
    for ed in editais:
        cnpj = ed.get("cnpj_orgao", "")
        if cnpj in organ_results:
            intel = organ_results[cnpj]
            # Strip internal cache metadata from the edital copy
            ed["competitive_intel"] = {
                k: v for k, v in intel.items()
                if not k.startswith("_")
            }
            assigned += 1
        else:
            ed["competitive_intel"] = None

    print(f"  Competitive intel: {counters['cached']} do cache, "
          f"{counters['fetched']} da API, {counters['failed']} falhas, "
          f"{assigned} editais enriquecidos")



# ============================================================
# STEP 5: FETCH DOCUMENT LISTINGS (top 50 by valor)
# ============================================================

def fetch_documents_top50(api: ApiClient, editais: list[dict]) -> None:
    """Fetch document listings for top 50 cnae_compatible editais by valor. Mutates in place."""
    compatible = [ed for ed in editais if ed.get("cnae_compatible")]
    compatible_sorted = sorted(
        compatible,
        key=lambda e: (e.get("valor_estimado") or 0.0),
        reverse=True,
    )
    top50 = compatible_sorted[:50]
    top50_ids = {ed["_id"] for ed in top50}

    # Load docs cache
    docs_cache: dict = {}
    docs_cache_lock = threading.Lock()
    try:
        docs_cache = _load_json_cache(DOCS_CACHE_FILE)
        if docs_cache:
            print(f"  Docs cache: {len(docs_cache)} entradas carregadas do disco")
    except Exception:
        pass

    print(f"\n  Buscando documentos para top {len(top50)} editais compativeis por valor...")
    counter_lock = threading.Lock()
    counters = {"cached": 0, "fetched": 0, "failed": 0}

    def _fetch_single(ed: dict) -> None:
        cnpj_orgao = ed.get("cnpj_orgao", "")
        ano = ed.get("ano_compra", "")
        seq = ed.get("sequencial_compra", "")

        if not (cnpj_orgao and ano and seq):
            ed["documentos"] = []
            ed["documentos_source"] = _source_tag("UNAVAILABLE", "Dados insuficientes")
            return

        cache_key = f"{cnpj_orgao}/{ano}/{seq}"

        # Check cache
        with docs_cache_lock:
            cached = docs_cache.get(cache_key)

        if cached is not None:
            ed["documentos"] = cached
            ed["documentos_source"] = _source_tag("API", f"{len(cached)} documentos (cache)")
            with counter_lock:
                counters["cached"] += 1
            return

        data, status = _api_get_with_retry(
            api,
            f"{PNCP_FILES_BASE}/orgaos/{cnpj_orgao}/compras/{ano}/{seq}/arquivos",
            label=f"Docs: {cnpj_orgao}/{ano}/{seq}",
            max_retries=1,
        )

        if status == "API" and isinstance(data, list):
            docs = []
            for d in data:
                docs.append({
                    "tipo": d.get("tipoDocumentoNome") or d.get("tipoDocumentoDescricao") or "",
                    "tipo_id": d.get("tipoDocumentoId"),
                    "titulo": d.get("titulo", ""),
                    "sequencial": d.get("sequencialDocumento"),
                    "download_url": (
                        f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj_orgao}/compras/{ano}/{seq}"
                        f"/arquivos/{d.get('sequencialDocumento')}"
                    ) if d.get("sequencialDocumento") else None,
                    "ativo": d.get("statusAtivo", True),
                })
            ed["documentos"] = docs
            ed["documentos_source"] = _source_tag("API", f"{len(docs)} documentos encontrados")
            with docs_cache_lock:
                docs_cache[cache_key] = docs
            with counter_lock:
                counters["fetched"] += 1
        else:
            ed["documentos"] = []
            ed["documentos_source"] = _source_tag("API_FAILED")
            with counter_lock:
                counters["failed"] += 1

        time.sleep(0.05)

    # Only fetch for top 50
    to_fetch = [ed for ed in editais if ed["_id"] in top50_ids]

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
        list(pool.map(_fetch_single, to_fetch))

    print(f"  Documentos: {counters['cached']} do cache, {counters['fetched']} da API, {counters['failed']} falhas")

    # Save docs cache
    try:
        _save_json_cache(DOCS_CACHE_FILE, docs_cache)
    except Exception as e:
        print(f"  WARN: Falha ao salvar docs cache: {e}")


# ============================================================
# STEP 6: ASSEMBLE OUTPUT
# ============================================================

def assemble_output(
    empresa: dict,
    editais: list[dict],
    cnpj_formatted: str,
    ufs: list[str],
    dias: int,
    sector_name: str,
    sector_key: str,
    keywords: list[str],
    source_meta: dict,
    all_cnaes: list[str] | None = None,
    all_sector_keys: set[str] | None = None,
) -> dict:
    """Build the final JSON output structure."""
    now = _today()
    data_inicio = _date_iso(now - timedelta(days=dias))
    data_fim = _date_iso(now)

    # Statistics
    compatible = [ed for ed in editais if ed.get("cnae_compatible")]
    incompatible = [ed for ed in editais if not ed.get("cnae_compatible")]
    needs_llm = [ed for ed in editais if ed.get("needs_llm_review")]

    valor_total_compat = sum(_safe_float(ed.get("valor_estimado")) or 0.0 for ed in compatible)

    capital = _safe_float(empresa.get("capital_social")) or 0.0
    capacidade_10x = capital * 10.0 if capital > 0 else 0.0

    total_dentro_capacidade = 0
    if capacidade_10x > 0:
        for ed in compatible:
            v = _safe_float(ed.get("valor_estimado")) or 0.0
            if v == 0 or v <= capacidade_10x:
                total_dentro_capacidade += 1

    # Temporal status stats
    status_counts: dict[str, int] = {}
    for ed in compatible:
        st = ed.get("status_temporal", "SEM_DATA")
        status_counts[st] = status_counts.get(st, 0) + 1

    # Sort editais: compatible first (by valor desc), then incompatible (by valor desc)
    compatible_sorted = sorted(compatible, key=lambda e: (e.get("valor_estimado") or 0.0), reverse=True)
    incompatible_sorted = sorted(incompatible, key=lambda e: (e.get("valor_estimado") or 0.0), reverse=True)
    editais_sorted = compatible_sorted + incompatible_sorted

    return {
        "empresa": empresa,
        "busca": {
            "cnpj": cnpj_formatted,
            "ufs": ufs,
            "dias": dias,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "modalidades": sorted(MODALIDADES_BUSCA.keys()),
            "setor": sector_name,
            "sector_key": sector_key,
            "keywords_count": len(keywords),
            "keywords_sample": keywords[:20],
            "cnaes_count": len(all_cnaes) if all_cnaes else 1,
            "sector_keys": sorted(all_sector_keys) if all_sector_keys else [sector_key],
        },
        "estatisticas": {
            "total_publicacoes_consultadas": len(editais) + source_meta.get("total_expirados_removidos", 0),
            "total_bruto": len(editais) + source_meta.get("total_expirados_removidos", 0),  # deprecated alias
            "total_expirados_removidos": source_meta.get("total_expirados_removidos", 0),
            "total_expirados_encerrados": source_meta.get("total_expirados_encerrados", 0),
            "total_sessao_realizada": source_meta.get("total_sessao_realizada", 0),
            "total_apos_filtro_temporal": len(editais),
            "total_cnae_compativel": len(compatible),
            "total_cnae_incompativel": len(incompatible),
            "total_needs_llm_review": len(needs_llm),
            "valor_total_compativel": round(valor_total_compat, 2),
            "capacidade_10x": round(capacidade_10x, 2),
            "total_dentro_capacidade": total_dentro_capacidade,
            "total_nao_expirados": len(compatible),
            "pncp_pages_fetched": source_meta.get("pages_fetched", 0),
            "pncp_errors": source_meta.get("errors", 0),
            "pncp_errors_429": source_meta.get("errors_429", 0),
            "pncp_combo_429_suspended": source_meta.get("combo_429_suspended", 0),
            "pncp_pagination_exhausted": source_meta.get("pagination_exhausted", []),
            "total_after_dedup": source_meta.get("total_after_xdedup", len(editais)),
            "total_semantic_dedup_removed": source_meta.get("total_semantic_dedup_removed", 0),
            "status_temporal": status_counts,
            "total_expirados": source_meta.get("total_expirados_removidos", 0),
            "total_urgentes": status_counts.get("URGENTE", 0),
        },
        "editais": editais_sorted,
        "_metadata": {
            "generated_at": now.isoformat(),
            "script": "intel-collect.py",
            "version": VERSION,
            "sources": {
                "pncp": {
                    "source": source_meta.get("source", "live_api"),
                    "raw_api_items": source_meta.get("total_raw_api", 0),
                    "after_dedup": source_meta.get("total_after_dedup", 0),
                    "pages_fetched": source_meta.get("pages_fetched", 0),
                    "errors": source_meta.get("errors", 0),
                },
                "opencnpj": empresa.get("_source", {}).get("status", "UNKNOWN"),
            },
        },
    }



# ============================================================
# STEP 5b: PRICE BENCHMARKING (historical organ contracts)
# ============================================================

BENCHMARK_CACHE_FILE = str(_PROJECT_ROOT / "data" / "benchmark_cache.json")
_BENCHMARK_CACHE_TTL_DAYS = 7


def _parse_numero_controle_pncp(numero_controle: str) -> tuple[str, str, str] | None:
    """Parse numeroControlePncpCompra into (cnpj_orgao, ano, sequencial).

    Format: {cnpjOrgao}-{unidade}-{seq_padded}/{ano}
    Example: '12345678000190-1-000042/2025' -> ('12345678000190', '2025', '42')
    """
    if not numero_controle:
        return None
    try:
        # Split on '/' to get ano
        parts = numero_controle.rsplit("/", 1)
        if len(parts) != 2:
            return None
        left, ano = parts
        ano = ano.strip()

        # Split left on '-' to get cnpj_orgao and sequencial
        segments = left.split("-")
        if len(segments) < 3:
            return None

        cnpj_orgao = segments[0].strip()
        # Sequencial is the last segment, strip leading zeros
        seq_padded = segments[-1].strip()
        sequencial = str(int(seq_padded))  # remove leading zeros

        if not cnpj_orgao or not ano or not sequencial:
            return None
        return (cnpj_orgao, ano, sequencial)
    except (ValueError, IndexError):
        return None


def collect_price_benchmarks(
    api: ApiClient,
    editais: list[dict],
    keywords: list[str] | None = None,
) -> None:
    """Collect price benchmarking data from historical organ contracts.

    For each organ in the top-20 editais (by valor_estimado), queries PNCP
    for historical contracts and their procurement results to calculate
    typical discount percentages (homologado vs estimado).

    FILTERS procurement details by sector keywords (objeto field) so that
    discount statistics reflect only contracts in the same industry.

    v1.4: Parallelized via ThreadPoolExecutor (_BENCHMARK_WORKERS) — ~6x faster.
    v1.5: Sector-filtered benchmark — only contracts matching company keywords.

    Mutates editais in-place, adding 'price_benchmark' dict to top-20 editais.

    Args:
        api: ApiClient instance.
        editais: List of edital dicts.
        keywords: Sector keywords for filtering procurement objects.
                  If None/empty, falls back to unfiltered (legacy behavior).
    """
    compatible = [ed for ed in editais if ed.get("cnae_compatible")]
    compatible_sorted = sorted(
        compatible,
        key=lambda e: (e.get("valor_estimado") or 0.0),
        reverse=True,
    )
    top20 = compatible_sorted[:20]
    if not top20:
        print("  Price benchmark: nenhum edital compativel para analisar")
        return

    top20_ids = {ed["_id"] for ed in top20}

    # Group top20 editais by cnpj_orgao
    organ_editais: dict[str, list[dict]] = {}
    for ed in top20:
        cnpj = ed.get("cnpj_orgao", "")
        if cnpj:
            organ_editais.setdefault(cnpj, []).append(ed)

    if not organ_editais:
        print("  Price benchmark: nenhum orgao com CNPJ valido nos top 20")
        return

    print(f"\n  Price benchmark: analisando {len(organ_editais)} orgaos dos top {len(top20)} editais "
          f"({_BENCHMARK_WORKERS} workers)...")

    # Load benchmark cache
    bench_cache: dict = {}
    try:
        bench_cache = _load_json_cache(BENCHMARK_CACHE_FILE)
        if bench_cache:
            print(f"  Benchmark cache: {len(bench_cache)} orgaos carregados do disco")
    except Exception:
        pass

    now = _today()
    cache_cutoff = now - timedelta(days=_BENCHMARK_CACHE_TTL_DAYS)

    # Check if a cache entry is still fresh
    def _cache_fresh(cnpj: str) -> bool:
        entry = bench_cache.get(cnpj)
        if not isinstance(entry, dict):
            return False
        ts_str = entry.get("_cached_at", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            return ts > cache_cutoff
        except Exception:
            return False

    # Thread-safe containers for parallel benchmark collection
    bench_lock = threading.Lock()
    organ_benchmarks: dict[str, dict] = {}
    counters = {"cached": 0, "fetched": 0, "failed": 0}

    # ── Sector keyword filter for benchmark ──
    bench_kw_patterns: list[re.Pattern] = []
    if keywords:
        for kw in keywords:
            kw_clean = kw.lower().strip()
            if kw_clean and len(kw_clean) >= 3:
                try:
                    bench_kw_patterns.append(re.compile(r'\b' + re.escape(kw_clean) + r'\b', re.IGNORECASE))
                except re.error:
                    continue

    def _bench_match_sector(objeto: str) -> bool:
        if not bench_kw_patterns or not objeto:
            return False
        obj_lower = objeto.lower()
        return any(pat.search(obj_lower) for pat in bench_kw_patterns)

    def _fetch_organ_benchmark(cnpj_orgao: str) -> tuple[str, dict | None]:
        """Fetch and compute benchmark for a single organ (thread-safe)."""
        # Check cache first — skip cache when keywords active (to get sector-filtered data)
        if not bench_kw_patterns and _cache_fresh(cnpj_orgao):
            with bench_lock:
                counters["cached"] += 1
            return cnpj_orgao, bench_cache[cnpj_orgao]

        try:
            # Fetch contracts for this organ (2 yearly queries for 2-year coverage)
            all_contracts: list[dict] = []
            for year_offset in range(2):
                end_date = now - timedelta(days=365 * year_offset)
                start_date = end_date - timedelta(days=365)
                data_inicial = _date_compact(start_date)
                data_final = _date_compact(end_date)

                for page in range(1, 5):  # max 4 pages per year (200 contracts)
                    params = {
                        "cnpjOrgao": cnpj_orgao,
                        "dataInicial": data_inicial,
                        "dataFinal": data_final,
                        "pagina": page,
                        "tamanhoPagina": 50,
                    }
                    data, status = _api_get_with_retry(
                        api,
                        f"{PNCP_BASE}/contratos",
                        params=params,
                        label=f"Bench orgao={cnpj_orgao[:8]}.. yr={year_offset} p={page}",
                        max_retries=1,
                    )

                    if status != "API" or not data:
                        break

                    items = data if isinstance(data, list) else data.get("data", data.get("resultado", []))
                    if not isinstance(items, list) or not items:
                        break

                    all_contracts.extend(items)

                    if len(items) < 50:
                        break

                    time.sleep(0.3)

                time.sleep(0.3)

            if not all_contracts:
                with bench_lock:
                    counters["fetched"] += 1
                return cnpj_orgao, None

            # Extract procurement references from contracts
            procurement_refs: list[tuple[str, str, str]] = []
            seen_refs: set[str] = set()
            for contract in all_contracts:
                numero_controle = contract.get("numeroControlePncpCompra") or ""
                parsed = _parse_numero_controle_pncp(numero_controle)
                if parsed:
                    ref_key = f"{parsed[0]}/{parsed[1]}/{parsed[2]}"
                    if ref_key not in seen_refs:
                        seen_refs.add(ref_key)
                        procurement_refs.append(parsed)

            # Query procurement details (max 20 per organ when sector-filtering, else 10)
            max_procurements = 20 if bench_kw_patterns else 10
            descontos: list[float] = []
            contratos_com_resultado = 0
            total_analisados = 0
            sector_matches = 0

            for ref_cnpj, ref_ano, ref_seq in procurement_refs[:max_procurements]:
                data, status = _api_get_with_retry(
                    api,
                    f"{PNCP_BASE}/orgaos/{ref_cnpj}/compras/{ref_ano}/{ref_seq}",
                    label=f"Compra {ref_cnpj[:8]}../{ref_ano}/{ref_seq}",
                    max_retries=1,
                )

                if status == "API" and isinstance(data, dict):
                    total_analisados += 1

                    # Sector filter: skip procurements outside company's industry
                    proc_objeto = data.get("objeto", "") or data.get("descricao", "") or ""
                    if bench_kw_patterns and proc_objeto:
                        if not _bench_match_sector(proc_objeto):
                            continue
                    sector_matches += 1

                    existe_resultado = data.get("existeResultado", False)
                    if existe_resultado:
                        contratos_com_resultado += 1

                    valor_estimado = _safe_float(data.get("valorTotalEstimado"))
                    valor_homologado = _safe_float(data.get("valorTotalHomologado"))

                    if (valor_estimado and valor_estimado > 0
                            and valor_homologado and valor_homologado > 0):
                        desconto = 1.0 - (valor_homologado / valor_estimado)
                        if -1.0 <= desconto <= 1.0:
                            descontos.append(desconto)

                time.sleep(0.3)

            # Compute statistics
            if len(descontos) < 3:
                result = {
                    "contratos_analisados": total_analisados,
                    "contratos_com_resultado": contratos_com_resultado,
                    "descontos_encontrados": len(descontos),
                    "insuficiente": True,
                    "sector_filtered": bool(bench_kw_patterns),
                    "sector_matches": sector_matches,
                    "_cached_at": now.isoformat(),
                }
                with bench_lock:
                    counters["fetched"] += 1
                return cnpj_orgao, result

            desconto_medio = statistics.mean(descontos)
            desconto_mediano = statistics.median(descontos)
            quartiles = statistics.quantiles(descontos, n=4, method="inclusive")
            desconto_p25 = quartiles[0]
            desconto_p75 = quartiles[2]

            result = {
                "desconto_medio": round(desconto_medio, 4),
                "desconto_mediano": round(desconto_mediano, 4),
                "desconto_p25": round(desconto_p25, 4),
                "desconto_p75": round(desconto_p75, 4),
                "contratos_com_resultado": contratos_com_resultado,
                "total_analisados": total_analisados,
                "descontos_encontrados": len(descontos),
                "insuficiente": False,
                "sector_filtered": bool(bench_kw_patterns),
                "sector_matches": sector_matches,
                "_cached_at": now.isoformat(),
            }
            sector_tag = " [setor]" if bench_kw_patterns else ""
            print(f"    Orgao {cnpj_orgao}: desconto mediano {desconto_mediano:.1%} "
                  f"({len(descontos)} contratos com resultado{sector_tag})")
            with bench_lock:
                counters["fetched"] += 1
            return cnpj_orgao, result

        except Exception as exc:
            print(f"    WARN: Falha benchmark orgao {cnpj_orgao}: {exc}")
            with bench_lock:
                counters["failed"] += 1
            return cnpj_orgao, None

    # v1.4: Parallel benchmark collection via ThreadPoolExecutor
    n_workers = min(len(organ_editais), _BENCHMARK_WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_fetch_organ_benchmark, cnpj): cnpj
            for cnpj in organ_editais
        }
        for fut in concurrent.futures.as_completed(futures):
            cnpj_orgao, result = fut.result()
            if result is not None:
                with bench_lock:
                    organ_benchmarks[cnpj_orgao] = result
                    bench_cache[cnpj_orgao] = result

    print(f"  Benchmark: {counters['cached']} cache, {counters['fetched']} fetched, "
          f"{counters['failed']} failed")

    # Apply benchmarks to top-20 editais
    applied = 0
    for ed in editais:
        if ed["_id"] not in top20_ids:
            continue

        cnpj = ed.get("cnpj_orgao", "")
        bm = organ_benchmarks.get(cnpj)
        if not bm or bm.get("insuficiente"):
            continue

        valor_est = _safe_float(ed.get("valor_estimado")) or 0.0
        desconto_med = bm["desconto_mediano"]
        p25 = bm["desconto_p25"]
        p75 = bm["desconto_p75"]
        n_contratos = bm["descontos_encontrados"]

        benchmark_entry: dict[str, Any] = {
            "desconto_medio_orgao": bm["desconto_medio"],
            "desconto_mediano_orgao": desconto_med,
            "desconto_mediano": desconto_med,  # canonical key for bid_simulator compat
            "desconto_p25": p25,
            "desconto_p75": p75,
            "contratos_analisados": n_contratos,
        }

        if valor_est > 0:
            # Suggested price range based on historical discounts
            # p75 = higher discount -> lower price (min)
            # p25 = lower discount -> higher price (max)
            benchmark_entry["valor_sugerido_min"] = round(valor_est * (1.0 - p75), 2)
            benchmark_entry["valor_sugerido_max"] = round(valor_est * (1.0 - p25), 2)

        benchmark_entry["nota"] = (
            f"Orgao historicamente contrata com {abs(desconto_med):.0%} de "
            f"{'desconto' if desconto_med >= 0 else 'acrescimo'} "
            f"(mediana de {n_contratos} contratos nos ultimos 2 anos)"
        )

        ed["price_benchmark"] = benchmark_entry
        applied += 1

    # Save benchmark cache
    try:
        _save_json_cache(BENCHMARK_CACHE_FILE, bench_cache)
    except Exception as e:
        print(f"  WARN: Falha ao salvar benchmark cache: {e}")

    # Compute lance_sugerido from benchmark data
    lance_count = 0
    for ed in editais:
        if ed["_id"] not in top20_ids:
            continue
        bench = ed.get("price_benchmark", {})
        desc_mediano = bench.get("desconto_mediano_orgao")
        contratos = bench.get("contratos_analisados", 0)
        valor = _safe_float(ed.get("valor_estimado")) or 0

        if desc_mediano and contratos >= 3 and valor > 0:
            # 15% less aggressive than median discount
            desconto_sugerido = desc_mediano * 0.85
            ed["lance_sugerido"] = {
                "valor": round(valor * (1 - desconto_sugerido), 2),
                "desconto_pct": round(desconto_sugerido * 100, 1),
                "faixa_agressiva": round(valor * (1 - desc_mediano), 2),
                "faixa_conservadora": round(valor * (1 - desc_mediano * 0.5), 2),
                "margem_liquida_pct": round(((1 - desconto_sugerido) / 0.80 - 1) * 100, 1),  # custo ~80% do valor estimado (BDI ~25%)
                "confianca": "ALTA" if contratos >= 5 else "MEDIA",
                "base_contratos": contratos,
                "desconto_mediano_orgao": desc_mediano,
            }
            lance_count += 1

    print(f"  Price benchmark: {applied} editais enriquecidos de {len(top20)} top-20")
    if lance_count:
        print(f"  Lance sugerido: {lance_count} editais com lance calculado")


# ============================================================
# DELTA DETECTION (compare against previous runs)
# ============================================================

def _detect_delta(editais: list[dict], previous_json_path: str | None) -> dict:
    """Compare editais against a previous run to detect changes.

    Marks each edital with `_delta_status`:
      - "NOVO": not in previous run
      - "VENCENDO": dias_restantes <= 3 and previously > 3
      - "ATUALIZADO": valor_estimado changed by >5%
      - "INALTERADO": no significant changes

    Returns a summary dict with counts.
    """
    summary = {"novos": 0, "atualizados": 0, "vencendo": 0, "inalterados": 0}

    if not previous_json_path or not os.path.isfile(previous_json_path):
        # No previous run — all are new
        for ed in editais:
            ed["_delta_status"] = "NOVO"
        summary["novos"] = len(editais)
        return summary

    # Load previous data
    try:
        with open(previous_json_path, encoding="utf-8") as f:
            prev_data = json.load(f)
    except Exception as e:
        print(f"  WARN: Falha ao carregar run anterior ({previous_json_path}): {e}")
        for ed in editais:
            ed["_delta_status"] = "NOVO"
        summary["novos"] = len(editais)
        return summary

    # Extract previous editais by _id
    prev_editais = prev_data.get("editais", [])
    prev_by_id: dict[str, dict] = {}
    for ped in prev_editais:
        pid = ped.get("_id", "")
        if pid:
            prev_by_id[pid] = ped

    # Extract previous run date for metadata
    prev_generated = prev_data.get("_metadata", {}).get("generated_at", "")
    prev_date = prev_generated[:10] if prev_generated else "desconhecido"

    for ed in editais:
        eid = ed.get("_id", "")
        ed["_delta_previous_run"] = prev_date

        if eid not in prev_by_id:
            ed["_delta_status"] = "NOVO"
            summary["novos"] += 1
            continue

        prev_ed = prev_by_id[eid]

        # Check "VENCENDO": dias_restantes <= 3 now, but was > 3 previously
        dias_now = ed.get("dias_restantes")
        dias_prev = prev_ed.get("dias_restantes")
        if (dias_now is not None and dias_prev is not None
                and dias_now <= 3 and dias_prev > 3):
            ed["_delta_status"] = "VENCENDO"
            summary["vencendo"] += 1
            continue

        # Check "ATUALIZADO": valor_estimado changed by >5%
        val_now = _safe_float(ed.get("valor_estimado")) or 0.0
        val_prev = _safe_float(prev_ed.get("valor_estimado")) or 0.0
        if val_now > 0 and val_prev > 0:
            diff_ratio = abs(val_now - val_prev) / val_prev
            if diff_ratio > 0.05:
                ed["_delta_status"] = "ATUALIZADO"
                summary["atualizados"] += 1
                continue

        ed["_delta_status"] = "INALTERADO"
        summary["inalterados"] += 1

    return summary


def _find_previous_run(cnpj14: str) -> str | None:
    """Find the most recent intel JSON for the given CNPJ in data/intel/."""
    intel_dir = str(_PROJECT_ROOT / "docs" / "intel")
    if not os.path.isdir(intel_dir):
        return None

    pattern = os.path.join(intel_dir, f"intel-{cnpj14}*.json")
    matches = glob_mod.glob(pattern)
    if not matches:
        return None

    # Sort by modification time descending, return most recent
    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return matches[0]


# ============================================================
# MAIN
# ============================================================

def main():
    """Entry point for intel-collect CLI."""
    from lib.cli_validation import validate_cnpj, validate_dias, validate_ufs
    from lib.constants import INTEL_VERSION

    parser = argparse.ArgumentParser(
        description="Intel Collect — Busca exaustiva PNCP para /intel-busca.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exemplos:
  python scripts/intel-collect.py --cnpj 12345678000190 --ufs SC,PR,RS
  python scripts/intel-collect.py --cnpj 12.345.678/0001-90 --ufs SC --dias 60
  python scripts/intel-collect.py --cnpj 12345678000190 --ufs SC,PR --output out.json --quiet""",
    )
    parser.add_argument("--cnpj", required=True,
                        help="CNPJ da empresa, com ou sem formatacao (ex: 12345678000190 ou 12.345.678/0001-90)")
    parser.add_argument("--ufs", required=True,
                        help="UFs separadas por virgula — codigos de 2 letras (ex: SC,PR,RS)")
    parser.add_argument("--dias", type=int, default=90,
                        help="Periodo de busca em dias, 1-365 (default: 90)")
    parser.add_argument("--output", type=str, default=None,
                        help="Caminho do JSON de saida (default: auto-nomeado em docs/intel/)")
    parser.add_argument("--quiet", action="store_true",
                        help="Reduzir output no console (somente erros e resumo final)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignorar checkpoint salvo e forcar nova coleta completa")
    parser.add_argument("--skip-sicaf", action="store_true",
                        help="Pular coleta SICAF (evita captcha do navegador)")
    parser.add_argument("--no-datalake", action="store_true",
                        help="Forcar busca live na API PNCP (ignorar datalake local)")
    parser.add_argument("--chunked", action="store_true",
                        help="Modo chunked: processa 1 combo por vez em vez de todos em paralelo. "
                             "Reduz carga na API PNCP e evita 429 rate-limit.")
    parser.add_argument("--batch-size", type=int, default=1, metavar="N",
                        help="No modo chunked, processa N combos por batch (default: 1). "
                             "Delay entre batches: 5s.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {INTEL_VERSION}")
    args = parser.parse_args()

    # ── Validate arguments ──
    cnpj14 = validate_cnpj(args.cnpj)
    ufs = validate_ufs(args.ufs)
    validate_dias(args.dias)

    t0 = time.time()

    # ── Step 1: Parse args, fetch company data ──
    cnpj_formatted = _format_cnpj(cnpj14)
    dias = args.dias

    print(f"{'='*60}")
    print(f"  INTEL-COLLECT v{VERSION}")
    print(f"  CNPJ: {cnpj_formatted}")
    print(f"  UFs:  {', '.join(ufs)}")
    print(f"  Dias: {dias}")
    print(f"  Modalidades: {sorted(MODALIDADES_BUSCA.keys())}")
    print(f"  Cache:       {'desabilitado (--no-cache)' if args.no_cache else 'habilitado (2h TTL)'}")
    print(f"{'='*60}")

    api = ApiClient(verbose=not args.quiet)

    print("\n[1/7] Perfil da empresa...")
    empresa = collect_opencnpj(api, cnpj14)
    if empresa.get("_source", {}).get("status") == "API_FAILED":
        print(f"\nERROR: Nao foi possivel obter dados da empresa para CNPJ {cnpj_formatted}")
        print("Verifique o CNPJ e tente novamente.")
        api.close()
        sys.exit(1)

    razao = empresa.get("razao_social", "N/A")
    cnae_principal = empresa.get("cnae_principal", "")
    capital = empresa.get("capital_social", 0.0)
    uf_sede = empresa.get("uf_sede", "")
    print(f"  Empresa: {razao}")
    print(f"  CNAE: {cnae_principal}")
    print(f"  Capital: {_fmt_brl(capital)}")
    print(f"  UF Sede: {uf_sede}")

    # ── Step 1b: SICAF + Sanções (run early so user resolves captcha upfront) ──
    skip_sicaf = getattr(args, "skip_sicaf", False)
    if not skip_sicaf:
        print("\n[1b/7] Verificação cadastral SICAF + Sanções...")
        print("   Navegador vai abrir. Resolva o captcha quando solicitado.\n")

        # Portal da Transparência — Sanções
        pt_key = os.environ.get("PORTAL_TRANSPARENCIA_API_KEY", "")
        pt_data = collect_portal_transparencia(api, cnpj14, pt_key)
        empresa["sancoes"] = pt_data.get("sancoes", {})
        empresa["sancoes_source"] = pt_data.get("sancoes_source", {})
        empresa["historico_contratos_federais"] = pt_data.get("historico_contratos", [])

        sancionada = empresa["sancoes"].get("sancionada", False)
        empresa["sancionada"] = sancionada
        if sancionada:
            sancoes_ativas = [k for k, v in empresa["sancoes"].items() if v and k not in ("sancionada", "inconclusive")]
            print(f"\n  *** ALERTA: Empresa SANCIONADA ({', '.join(s.upper() for s in sancoes_ativas)}) ***")
            print("  *** Empresa IMPEDIDA de licitar ***")

        # SICAF
        sicaf_data = collect_sicaf(cnpj14, verbose=True)
        empresa["sicaf"] = sicaf_data
        restricao = sicaf_data.get("restricao", {})
        if isinstance(restricao, dict):
            empresa["restricao_sicaf"] = restricao.get("possui_restricao", None)
        elif isinstance(restricao, bool):
            empresa["restricao_sicaf"] = restricao
        else:
            empresa["restricao_sicaf"] = None

        crc_status = sicaf_data.get("crc_status", "N/D")
        restricao_str = "SIM" if empresa.get("restricao_sicaf") else "NÃO"
        print(f"  SICAF: CRC {crc_status} | Restrição: {restricao_str}")
        if empresa.get("restricao_sicaf"):
            print("  *** ALERTA: SICAF com RESTRIÇÃO ativa — risco de inabilitação ***")

        # TCU Due Diligence — Inidôneos + Certidões APF (v1.4, free API, no auth)
        print("  TCU: Verificando inidoneos e certidoes APF...")
        tcu_data = _collect_tcu_due_diligence(api, cnpj14)
        empresa["tcu"] = tcu_data
        if tcu_data.get("inidoneo"):
            print("  *** ALERTA: Empresa declarada INIDÔNEA pelo TCU ***")
        if tcu_data.get("certidoes_irregulares"):
            print("  *** ALERTA: Certidões APF com irregularidades ***")
        else:
            print("  TCU: Nada consta (inidoneos + certidoes APF)")
    else:
        print("\n[1b/7] SICAF pulado (--skip-sicaf)")
        empresa["sicaf"] = {"status": "PULADO"}
        empresa["sancionada"] = False
        empresa["sancoes"] = {}
        empresa["restricao_sicaf"] = None

    # ── Step 2: Map ALL CNAEs -> keywords (principal + secundários) ──
    print("\n[2/7] Mapeando TODOS os CNAEs para keywords...")

    # Collect all CNAEs (principal + secondary)
    all_cnaes: list[str] = []
    if cnae_principal:
        all_cnaes.append(cnae_principal)
    cnaes_sec_raw = empresa.get("cnaes_secundarios", "")
    if cnaes_sec_raw:
        # May be comma-separated string or list
        if isinstance(cnaes_sec_raw, list):
            all_cnaes.extend(str(c).strip() for c in cnaes_sec_raw if str(c).strip())
        else:
            all_cnaes.extend(c.strip() for c in str(cnaes_sec_raw).split(",") if c.strip())
    print(f"  CNAEs encontrados: {len(all_cnaes)} (1 principal + {len(all_cnaes)-1} secundarios)")

    # Map each CNAE to sector + keywords, aggregating all
    all_keywords: list[str] = []
    all_sector_keys: set[str] = set()
    all_cnae_prefixes: set[str] = set()
    primary_sector_name = ""
    primary_sector_key = ""

    for i, cnae_raw in enumerate(all_cnaes):
        s_name, s_keywords, s_key = map_sector(cnae_raw)
        all_keywords.extend(s_keywords)
        all_sector_keys.add(s_key)

        # Extract 4-digit prefix
        cnae_d = re.sub(r"[^0-9]", "", cnae_raw.split("-")[0].split(" ")[0])[:7]
        prefix = cnae_d[:4]
        if prefix:
            all_cnae_prefixes.add(prefix)

        # Add CNAE refinement extra keywords
        cnae_ref = CNAE_KEYWORD_REFINEMENTS.get(prefix, {})
        extra_inc = cnae_ref.get("extra_include", [])
        if extra_inc:
            all_keywords.extend(extra_inc)

        # Add CNAE description words
        cnae_desc_part = cnae_raw.split("-")[-1].split("/")[-1] if "-" in cnae_raw else cnae_raw
        desc_words = [w.strip().lower() for w in cnae_desc_part.split() if len(w.strip()) > 3]
        all_keywords.extend(desc_words)

        if i == 0:
            primary_sector_name = s_name
            primary_sector_key = s_key
            print(f"  CNAE principal: {cnae_raw} → {s_name} ({s_key})")
        elif s_key != "geral":
            print(f"  CNAE secundario: {prefix} → {s_name}")

    sector_name = primary_sector_name
    sector_key = primary_sector_key
    cnae_prefix = re.sub(r"[^0-9]", "", cnae_principal.split("-")[0].split(" ")[0])[:4]

    # Deduplicate keywords
    seen_kw: set[str] = set()
    unique_keywords: list[str] = []
    for kw in all_keywords:
        kw_low = kw.lower().strip()
        if kw_low and kw_low not in seen_kw:
            seen_kw.add(kw_low)
            unique_keywords.append(kw)
    keywords = unique_keywords

    print(f"  Setores cobertos: {', '.join(sorted(all_sector_keys))}")
    print(f"  Prefixos CNAE: {', '.join(sorted(all_cnae_prefixes))}")
    print(f"  Total keywords (dedup): {len(keywords)}")

    # Compile patterns
    keyword_patterns = _compile_keyword_patterns(keywords)
    print(f"  Patterns compilados: {len(keyword_patterns)}")

    # ── Step 3: PNCP search (datalake preferred, live API fallback) ──
    use_datalake = not args.no_datalake and os.getenv("DATALAKE_QUERY_ENABLED", "").lower() in ("true", "1")
    editais: list[dict] = []
    source_meta: dict = {}

    if use_datalake:
        print(f"\n[3/7] Busca via DATALAKE ({dias} dias, {len(ufs)} UFs, {len(MODALIDADES_BUSCA)} modalidades)...")
        editais, source_meta = search_datalake_for_intel(ufs, dias, MODALIDADES_BUSCA)
        if editais:
            print(f"  Datalake: {len(editais)} editais em <2s (0 requests PNCP)")
        else:
            dl_err = source_meta.get("datalake_error", "empty result")
            print(f"  Datalake indisponivel ({dl_err}) — fallback para API live")
            use_datalake = False

    if not use_datalake:
        print(f"\n[3/7] Busca exaustiva PNCP LIVE ({dias} dias, {len(ufs)} UFs, {len(MODALIDADES_BUSCA)} modalidades)...")
        if args.chunked:
            print(f"  Modo chunked ativado (batch_size={args.batch_size}) — combos processados em lotes sequenciais")
        editais, source_meta = search_pncp_exhaustive(
            api, ufs, dias, MODALIDADES_BUSCA,
            cnpj14=cnpj14,
            use_cache=not args.no_cache,
            chunked=args.chunked,
            batch_size=args.batch_size,
        )

    print(f"\n  Total bruto (dedup _id): {len(editais)} editais")
    if source_meta.get("pagination_exhausted"):
        print(f"  WARN: Paginacao esgotada em: {source_meta['pagination_exhausted']}")

    # ── Cross-portal dedup (between PNCP and PCP) ──
    # Same edital may appear on both portals with different _id values.
    # Group by (uf, municipio, valor, objeto[:150]) hash and keep the best copy.
    total_before_xdedup = len(editais)
    hash_to_editais: dict[str, list[dict]] = {}
    for ed in editais:
        h = _compute_dedup_hash(ed)
        ed["dedup_hash"] = h
        hash_to_editais.setdefault(h, []).append(ed)

    deduped_editais: list[dict] = []
    n_duplicatas = 0
    for h, group in hash_to_editais.items():
        if len(group) == 1:
            deduped_editais.append(group[0])
        else:
            # Keep the edital with more metadata (more non-None fields).
            # On tie, prefer PNCP source (link_pncp starting with pncp.gov.br).
            def _score(ed: dict) -> tuple[int, int]:
                filled = sum(1 for v in ed.values() if v is not None and v != "" and v != [])
                is_pncp = 1 if "pncp.gov.br" in (ed.get("link_pncp") or "") else 0
                return (filled, is_pncp)

            best = max(group, key=_score)
            best_id = best["_id"]
            for ed in group:
                if ed["_id"] != best_id:
                    ed["_duplicata_de"] = best_id
                    n_duplicatas += 1
            deduped_editais.append(best)

    editais = deduped_editais
    source_meta["total_after_xdedup"] = len(editais)
    if n_duplicatas > 0:
        print(f"  Dedup cross-portal: {n_duplicatas} duplicatas removidas de {total_before_xdedup} editais")
    else:
        print(f"  Dedup cross-portal: sem duplicatas detectadas ({total_before_xdedup} editais)")

    # ── Semantic dedup (token overlap within UF) ──
    n_before_semantic = len(editais)
    editais = _semantic_dedup(editais)
    n_semantic_removed = n_before_semantic - len(editais)
    source_meta["total_semantic_dedup_removed"] = n_semantic_removed

    # ── Step 3b: Remove expired + session-held tenders BEFORE any further processing ──
    # EXPIRADO: data_encerramento_proposta already passed
    # SESSAO_REALIZADA: data_abertura_proposta already passed (bidding session held, can't participate)
    n_before_expiry = len(editais)
    n_expirados = sum(1 for ed in editais if ed.get("status_temporal") == "EXPIRADO")
    n_sessao_realizada = sum(1 for ed in editais if ed.get("status_temporal") == "SESSAO_REALIZADA")
    editais = [ed for ed in editais if ed.get("status_temporal") not in ("EXPIRADO", "SESSAO_REALIZADA")]
    n_removed = n_expirados + n_sessao_realizada
    if n_removed > 0:
        print(f"\n  Filtro temporal: {n_removed} removidos de {n_before_expiry} editais ({len(editais)} restantes)")
        print(f"    {n_expirados} expirados + {n_sessao_realizada} sessao ja realizada")
    source_meta["total_expirados_removidos"] = n_removed
    source_meta["total_expirados_encerrados"] = n_expirados
    source_meta["total_sessao_realizada"] = n_sessao_realizada

    # ── Step 4: CNAE keyword gate ──
    print(f"\n[4/7] Aplicando gate de keywords CNAE ({len(all_cnae_prefixes)} prefixos, {len(all_sector_keys)} setores)...")
    apply_cnae_keyword_gate(
        editais, keywords, keyword_patterns, sector_key, cnae_prefix,
        all_cnae_prefixes=all_cnae_prefixes,
        all_sector_keys=all_sector_keys,
    )

    # ── Step 4a: LLM fallback for unknown sectors ──
    if sector_key == "geral":
        print(f"\n[4a/7] LLM fallback para setor desconhecido (CNAE: {cnae_principal[:60]})...")
        llm_stats = apply_llm_fallback_gate(
            editais, cnae_principal, sector_key,
        )
        source_meta["llm_fallback_stats"] = llm_stats

    # ── Steps 5+6+6b: Run competitive intel, documents, and benchmark IN PARALLEL ──
    # v1.4: These three steps are independent (mutate different fields on editais)
    # Running them concurrently saves 3-15 minutes depending on cache state.
    print("\n[5/7] Coletando inteligencia competitiva + documentos + price benchmark (paralelo)...")

    def _run_competitive():
        collect_competitive_intel(api, editais, keywords=keywords)

    def _run_documents():
        fetch_documents_top50(api, editais)

    def _run_benchmarks():
        collect_price_benchmarks(api, editais, keywords=keywords)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as step_pool:
        fut_comp = step_pool.submit(_run_competitive)
        fut_docs = step_pool.submit(_run_documents)
        fut_bench = step_pool.submit(_run_benchmarks)

        # Wait for all to complete, propagate exceptions
        for fut, name in [
            (fut_comp, "competitive intel"),
            (fut_docs, "documents"),
            (fut_bench, "price benchmark"),
        ]:
            try:
                fut.result()
            except Exception as exc:
                print(f"  WARN: {name} falhou: {exc}")


    # ── Step 6c: Delta detection (compare against previous run) ──
    print("\n[6c/7] Detectando delta com run anterior...")
    previous_run_path = _find_previous_run(cnpj14)
    if previous_run_path:
        print(f"  Run anterior encontrado: {previous_run_path}")
    else:
        print("  Nenhum run anterior encontrado — todos serao marcados como NOVO")
    delta_summary = _detect_delta(editais, previous_run_path)
    source_meta["_delta_summary"] = delta_summary
    print(f"  Delta: {delta_summary['novos']} novos, {delta_summary['atualizados']} atualizados, "
          f"{delta_summary['vencendo']} vencendo, {delta_summary['inalterados']} inalterados")

    # ── Step 7: Save output ──
    print("\n[7/7] Montando JSON de saida...")
    output = assemble_output(
        empresa=empresa,
        editais=editais,
        cnpj_formatted=cnpj_formatted,
        ufs=ufs,
        dias=dias,
        sector_name=sector_name,
        sector_key=sector_key,
        keywords=keywords,
        source_meta=source_meta,
        all_cnaes=all_cnaes,
        all_sector_keys=all_sector_keys,
    )

    # Add delta summary to output metadata
    output["_metadata"]["_delta_summary"] = delta_summary
    if previous_run_path:
        output["_metadata"]["_delta_previous_file"] = os.path.basename(previous_run_path)

    # Determine output path — include razao_social slug
    if args.output:
        out_path = args.output
    else:
        today_str = _date_iso(_today())
        slug = re.sub(r"[^\w\-]", "-", (razao or "empresa").lower())[:40].strip("-")
        slug = re.sub(r"-+", "-", slug)  # collapse multiple dashes
        out_dir = str(_PROJECT_ROOT / "data" / "intel")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"intel-{cnpj14}-{slug}-{today_str}.json")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    elapsed = time.time() - t0

    # Summary — lead with actionable numbers
    stats = output["estatisticas"]
    st_counts = stats.get("status_temporal", {})
    print(f"\n{'='*60}")
    print("  OPORTUNIDADES IDENTIFICADAS")
    print(f"{'='*60}")
    print(f"  Oportunidades abertas:  {stats['total_cnae_compativel']}")
    print(f"  Dentro da capacidade:   {stats['total_dentro_capacidade']}")
    print(f"  Valor total:            {_fmt_brl(stats['valor_total_compativel'])}")
    print(f"  Urgentes (<=7 dias):    {stats['total_urgentes']}")
    print(f"  Iminentes (7-15 dias):  {st_counts.get('IMINENTE', 0)}")
    print(f"  Planejaveis (>15 dias): {st_counts.get('PLANEJAVEL', 0)}")
    print(f"{'='*60}")
    print("  Detalhes da coleta:")
    print(f"    Publicacoes PNCP:     {stats['total_publicacoes_consultadas']}")
    _n_enc = stats.get("total_expirados_encerrados", stats["total_expirados_removidos"])
    _n_sr = stats.get("total_sessao_realizada", 0)
    print(f"    Descartadas:          {stats['total_expirados_removidos']} ({_n_enc} encerrados + {_n_sr} sessao realizada)")
    print(f"    Apos filtro temporal:  {stats['total_apos_filtro_temporal']}")
    print(f"    CNAE incompativeis:   {stats['total_cnae_incompativel']}")
    print(f"    Precisam LLM review:  {stats['total_needs_llm_review']}")
    print(f"    Paginas PNCP:         {stats['pncp_pages_fetched']}")
    print(f"    Erros PNCP:           {stats['pncp_errors']}")
    st_parts = ", ".join(f"{k}={v}" for k, v in sorted(st_counts.items()))
    print(f"    Status temporal:      {st_parts or 'N/A'}")
    _ds = delta_summary
    print(f"    Delta:                {_ds['novos']} novos, {_ds['atualizados']} atualizados, "
          f"{_ds['vencendo']} vencendo, {_ds['inalterados']} inalterados")
    print(f"    Semantic dedup:       {source_meta.get('total_semantic_dedup_removed', 0)} removidos")
    print(f"    Tempo total:          {elapsed:.1f}s")
    print(f"  Salvo em:               {out_path}")
    print(f"{'='*60}")

    api.print_stats()
    api.close()


if __name__ == "__main__":
    main()
