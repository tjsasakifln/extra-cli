#!/usr/bin/env python3
"""Dados Abertos SC (CKAN) crawler — real ingestion of DOE bulk publications.

Source: https://dados.sc.gov.br/ — CKAN Action API (no token for read).

Primary package:
    ``diario-oficial-sc-publicacoes`` (CSV/XLSX 2012–2025 on
    portal.doe.sea.sc.gov.br/repositorio/dadosabertos/).

Pipeline:
    package_show → prefer CSV per period → download to immutable raw zone →
    stream/parse CSV (encoding detection) → normalize + classify_act →
    checkpoint/resume → terminal JSON evidence under output/dados_abertos_sc/.

Interface expected by monitor.py:
    crawl(mode) -> list[dict]
    transform(records) -> list[dict]

Modes:
    smoke         — most recent 1 CSV resource; process first N rows
    incremental   — newest resource not yet processed (or hash-changed)
    backfill      — all preferred CSV resources oldest→newest
    full          — alias of backfill (compat)

Usage:
    python -m scripts.crawl.dados_abertos_sc_crawler --mode smoke
    python -m scripts.crawl.dados_abertos_sc_crawler --mode smoke --dry-run
    python -m scripts.crawl.dados_abertos_sc_crawler --mode incremental
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.act_classifier import classify_act  # noqa: E402
from scripts.crawl.run_evidence import (  # noqa: E402
    build_run_evidence,
    get_git_meta,
    new_run_id,
    sha256_file,
)
from scripts.crawl.security import USER_AGENT  # noqa: E402

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_NAME = "dados_abertos_sc"
PORTAL = "dados.sc.gov.br"

CKAN_BASE = "https://dados.sc.gov.br"
CKAN_API = f"{CKAN_BASE}/api/3/action"

PRIMARY_PACKAGE = "diario-oficial-sc-publicacoes"
RELATED_PACKAGES = (
    "diario-oficial-sc-publicacoes",
    "diario-oficial-sc-edicoes",
)

REQUEST_DELAY = 0.5  # seconds between CKAN / file requests
HTTP_TIMEOUT = 120
DOWNLOAD_TIMEOUT = 300

CHECKPOINT_DIR = _PROJECT_ROOT / "data" / "dados_sc_checkpoints"
RAW_ROOT = _PROJECT_ROOT / "data" / "raw" / "dados_abertos_sc"
NORMALIZED_ROOT = _PROJECT_ROOT / "data" / "normalized" / "dados_abertos_sc"
OUTPUT_DIR = _PROJECT_ROOT / "output" / "dados_abertos_sc"

ESFERA_ID_ESTADUAL = 2

# Smoke: process only first N publication rows after download
SMOKE_MAX_ROWS = 500

# CSV column aliases (uppercase keys after normalize)
_COL_MAP = {
    "DATA_PUBLICACAO": "data_publicacao",
    "PUBLICACAO": "numero_publicacao",
    "CATEGORIA": "categoria",  # organ/entity name in this dataset
    "ASSUNTO": "assunto",
    "EDICAO": "numero_edicao",
    "TITULO_PUBLICACAO": "titulo",
    # optional future columns
    "ORGAO": "orgao",
    "UNIDADE": "unidade",
    "TIPO_ATO": "tipo_ato",
    "DATA_EDICAO": "data_edicao",
    "TEXTO": "texto_ou_extrato",
    "EXTRATO": "texto_ou_extrato",
    "LINK_EXTRATO": "link_extrato",
    "LINK_EDICAO": "link_edicao",
}

_YEAR_RE = re.compile(r"(20\d{2}|19\d{2})")
_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")


# ---------------------------------------------------------------------------
# HTTP / CKAN client
# ---------------------------------------------------------------------------


def _ckan_get(action: str, params: dict[str, Any] | None = None) -> dict | None:
    """GET a CKAN Action API endpoint; return ``result`` or None."""
    query = urllib.parse.urlencode(params or {})
    url = f"{CKAN_API}/{action}"
    if query:
        url = f"{url}?{query}"
    req = urllib.request.Request(  # noqa: S310 — URL scheme validated for HTTPS CKAN
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 — fixed HTTPS CKAN
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        _logger.error("CKAN HTTP %s for %s: %s", e.code, url, e.reason)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        _logger.error("CKAN request failed for %s: %s", url, e)
        return None

    if not payload.get("success"):
        _logger.warning("CKAN success=false for %s: %s", url, payload.get("error"))
        return None
    return payload.get("result")


def package_search(q: str, rows: int = 10) -> dict | None:
    """CKAN package_search — returns full result dict (count + results)."""
    return _ckan_get("package_search", {"q": q, "rows": str(rows)})


def package_show(package_id: str) -> dict | None:
    """CKAN package_show."""
    return _ckan_get("package_show", {"id": package_id})


def resource_show(resource_id: str) -> dict | None:
    """CKAN resource_show."""
    return _ckan_get("resource_show", {"id": resource_id})


def status_show() -> dict | None:
    """CKAN status_show (health)."""
    return _ckan_get("status_show")


def list_resources(pkg: dict) -> list[dict]:
    """Normalize resource list from a package_show result."""
    out: list[dict] = []
    for r in pkg.get("resources") or []:
        out.append(
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "format": (r.get("format") or "").upper(),
                "last_modified": r.get("last_modified") or r.get("metadata_modified"),
                "url": r.get("url"),
                "size": r.get("size"),
                "datastore_active": r.get("datastore_active"),
                "mimetype": r.get("mimetype"),
                "package_id": pkg.get("name") or pkg.get("id"),
                "package_title": pkg.get("title"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Resource selection helpers
# ---------------------------------------------------------------------------


def detect_period(name: str | None) -> str | None:
    """Extract year/period from a resource name (e.g. publicacoes_2025.csv → 2025)."""
    if not name:
        return None
    m = _YEAR_RE.search(name)
    return m.group(1) if m else None


def prefer_csv_resources(resources: list[dict]) -> list[dict]:
    """Prefer CSV over XLSX for the same period; keep unique periods sorted ascending.

    Resources without a detectable period are kept if CSV (or sole format).
    """
    by_period: dict[str, dict] = {}
    no_period: list[dict] = []

    for res in resources:
        fmt = (res.get("format") or "").upper()
        period = detect_period(res.get("name") or "")
        if period is None:
            if fmt == "CSV" or fmt == "XLSX":
                no_period.append(res)
            continue
        existing = by_period.get(period)
        if existing is None:
            by_period[period] = res
            continue
        # Prefer CSV
        ex_fmt = (existing.get("format") or "").upper()
        if fmt == "CSV" and ex_fmt != "CSV":
            by_period[period] = res

    ordered = [by_period[p] for p in sorted(by_period.keys())]
    # Append no-period CSVs after dated ones
    for res in no_period:
        if (res.get("format") or "").upper() == "CSV":
            ordered.append(res)
    return ordered


def select_resources_for_mode(
    preferred: list[dict],
    mode: str,
    *,
    processed: dict[str, Any] | None = None,
) -> list[dict]:
    """Select which preferred resources to download for the given mode.

    - smoke: most recent period only
    - incremental: most recent period only (hash/checkpoint skip handles no-op)
    - backfill/full: all preferred CSVs oldest→newest; skip those already
      completed only at process-time (caller may filter)
    """
    if not preferred:
        return []
    processed = processed or {}
    mode = (mode or "smoke").lower()

    if mode in {"smoke", "incremental"}:
        return [preferred[-1]]  # most recent period

    # backfill / full — all periods; process-time resume skips identical hashes
    return list(preferred)


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


def _checkpoint_path(name: str = "last_smoke.json") -> Path:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR / name


def checkpoint_name_for_mode(mode: str) -> str:
    mode = (mode or "smoke").lower()
    if mode == "full":
        mode = "backfill"
    return f"ingest_{mode}.json"


def save_checkpoint(payload: dict, name: str = "last_smoke.json") -> Path:
    path = _checkpoint_path(name)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_checkpoint(name: str = "last_smoke.json") -> dict | None:
    path = _checkpoint_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        _logger.warning("Could not load checkpoint %s: %s", path, e)
        return None


def empty_checkpoint(*, mode: str, run_id: str) -> dict[str, Any]:
    return {
        "source": SOURCE_NAME,
        "mode": mode,
        "run_id": run_id,
        "processed_resources": {},
        "completed_resource_ids": [],
        "saved_at": None,
    }


# ---------------------------------------------------------------------------
# Raw zone download
# ---------------------------------------------------------------------------


def raw_resource_dir(resource_id: str) -> Path:
    return RAW_ROOT / str(resource_id)


def raw_body_path(resource_id: str, name: str | None = None) -> Path:
    ext = ".csv"
    if name and "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
    return raw_resource_dir(resource_id) / f"body{ext}"


def raw_meta_path(resource_id: str) -> Path:
    return raw_resource_dir(resource_id) / "meta.json"


def load_raw_meta(resource_id: str) -> dict | None:
    path = raw_meta_path(resource_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _head_or_get_headers(url: str) -> dict[str, str | None]:
    """Best-effort HEAD for ETag / Last-Modified / Content-Length."""
    out: dict[str, str | None] = {
        "etag": None,
        "last_modified": None,
        "content_length": None,
    }
    req = urllib.request.Request(  # noqa: S310 — HTTPS resource URL from CKAN
        url,
        method="HEAD",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
            out["etag"] = resp.headers.get("ETag")
            out["last_modified"] = resp.headers.get("Last-Modified")
            out["content_length"] = resp.headers.get("Content-Length")
            return out
    except Exception as e:  # noqa: BLE001 — HEAD often blocked; fall back silently
        _logger.debug("HEAD failed for %s: %s", url, e)
    return out


def download_resource_to_raw(
    res: dict,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Download resource body into immutable raw zone.

    Returns meta dict with keys:
        resource_id, url, name, path, sha256, size, etag, last_modified,
        skipped_identical, downloaded, error
    """
    rid = res.get("id") or ""
    url = res.get("url") or ""
    name = res.get("name") or ""
    result: dict[str, Any] = {
        "resource_id": rid,
        "url": url,
        "name": name,
        "format": res.get("format"),
        "path": None,
        "sha256": None,
        "size": None,
        "etag": None,
        "last_modified": res.get("last_modified"),
        "skipped_identical": False,
        "downloaded": False,
        "error": None,
    }
    if not rid or not url:
        result["error"] = "missing resource_id or url"
        return result

    body_path = raw_body_path(rid, name)
    meta_path = raw_meta_path(rid)
    existing = load_raw_meta(rid)

    # Skip if local file exists with registered hash
    if (
        not force
        and existing
        and existing.get("sha256")
        and body_path.is_file()
    ):
        local_hash = sha256_file(body_path)
        if local_hash and local_hash == existing.get("sha256"):
            result.update(
                {
                    "path": str(body_path),
                    "sha256": local_hash,
                    "size": existing.get("size") or body_path.stat().st_size,
                    "etag": existing.get("etag"),
                    "last_modified": existing.get("last_modified")
                    or result["last_modified"],
                    "skipped_identical": True,
                    "downloaded": False,
                }
            )
            _logger.info(
                "[%s] skip re-download resource_id=%s sha256=%s…",
                SOURCE_NAME,
                rid,
                local_hash[:12],
            )
            return result

    headers_meta = _head_or_get_headers(url)
    time.sleep(REQUEST_DELAY)

    req = urllib.request.Request(  # noqa: S310 — HTTPS resource from CKAN catalog
        url,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:  # noqa: S310
            etag = resp.headers.get("ETag") or headers_meta.get("etag")
            last_mod = resp.headers.get("Last-Modified") or headers_meta.get(
                "last_modified"
            )
            # Stream to temp then rename for atomicity
            raw_resource_dir(rid).mkdir(parents=True, exist_ok=True)
            tmp_path = body_path.with_suffix(body_path.suffix + ".part")
            h = hashlib.sha256()
            size = 0
            with tmp_path.open("wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    size += len(chunk)
            digest = h.hexdigest()
            # If identical to existing, remove temp and keep original
            if (
                not force
                and existing
                and existing.get("sha256") == digest
                and body_path.is_file()
            ):
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                result.update(
                    {
                        "path": str(body_path),
                        "sha256": digest,
                        "size": size,
                        "etag": etag,
                        "last_modified": last_mod,
                        "skipped_identical": True,
                        "downloaded": False,
                    }
                )
                return result

            tmp_path.replace(body_path)
            meta = {
                "resource_id": rid,
                "url": url,
                "name": name,
                "format": res.get("format"),
                "size": size,
                "etag": etag,
                "last_modified": last_mod,
                "sha256": digest,
                "path": str(body_path),
                "downloaded_at": datetime.now(UTC).isoformat(),
            }
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result.update(
                {
                    "path": str(body_path),
                    "sha256": digest,
                    "size": size,
                    "etag": etag,
                    "last_modified": last_mod,
                    "skipped_identical": False,
                    "downloaded": True,
                }
            )
            _logger.info(
                "[%s] downloaded resource_id=%s size=%s sha256=%s…",
                SOURCE_NAME,
                rid,
                size,
                digest[:12],
            )
            return result
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}: {e.reason}"
        _logger.error("[%s] download HTTP error %s: %s", SOURCE_NAME, url, result["error"])
        return result
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result["error"] = str(e)
        _logger.error("[%s] download failed %s: %s", SOURCE_NAME, url, e)
        return result


# ---------------------------------------------------------------------------
# CSV parse / encoding
# ---------------------------------------------------------------------------


def detect_encoding(path: Path | str, sample_size: int = 65536) -> str:
    """Detect encoding among utf-8/latin-1/cp1252 (prefer utf-8-sig)."""
    p = Path(path)
    raw = p.read_bytes()[:sample_size]
    for enc in _ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"  # always decodes


def detect_delimiter(sample: str) -> str:
    """Detect CSV delimiter (semicolon common in BR open data)."""
    header = sample.splitlines()[0] if sample else ""
    if header.count(";") >= header.count(",") and header.count(";") > 0:
        return ";"
    if header.count("\t") > header.count(","):
        return "\t"
    return ","


def iter_csv_rows(
    path: Path | str,
    *,
    max_rows: int | None = None,
    encoding: str | None = None,
) -> Iterable[dict[str, str]]:
    """Stream CSV rows as dicts (original column names preserved)."""
    p = Path(path)
    enc = encoding or detect_encoding(p)
    # Read a small sample for delimiter
    with p.open("r", encoding=enc, errors="replace", newline="") as f:
        sample = f.read(8192)
        delim = detect_delimiter(sample)
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delim)
        count = 0
        for row in reader:
            # Normalize None values to empty string
            clean = {str(k): ("" if v is None else str(v)) for k, v in row.items() if k}
            yield clean
            count += 1
            if max_rows is not None and count >= max_rows:
                break


# ---------------------------------------------------------------------------
# Normalize + classify
# ---------------------------------------------------------------------------


def _get_field(row: dict[str, str], *keys: str) -> str:
    """Case-insensitive field lookup."""
    upper_map = {str(k).strip().upper(): v for k, v in row.items()}
    for k in keys:
        if k.upper() in upper_map:
            return (upper_map[k.upper()] or "").strip()
    return ""


def _parse_br_date(value: str) -> str | None:
    """Parse DD/MM/YYYY or ISO → ISO date (YYYY-MM-DD) when possible."""
    v = (value or "").strip()
    if not v:
        return None
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", v)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mo}-{d}"
    if re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return v[:10]
    return v


def record_hash_for(parts: dict[str, Any]) -> str:
    key = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def normalize_publication_row(
    row: dict[str, str],
    *,
    resource_id: str,
    resource_name: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Map one CSV row to the normalized DOE publication schema."""
    ts = now or datetime.now(UTC).isoformat()
    data_pub_raw = _get_field(row, "DATA_PUBLICACAO", "data_publicacao")
    data_pub = _parse_br_date(data_pub_raw)
    data_ed_raw = _get_field(row, "DATA_EDICAO", "data_edicao")
    data_ed = _parse_br_date(data_ed_raw) or data_pub

    numero_pub = _get_field(row, "PUBLICACAO", "numero_publicacao", "NUMERO_PUBLICACAO")
    numero_ed = _get_field(row, "EDICAO", "numero_edicao", "NUMERO_EDICAO")
    # In this dataset CATEGORIA holds the organ/entity name
    categoria = _get_field(row, "CATEGORIA", "categoria")
    orgao = _get_field(row, "ORGAO", "orgao") or categoria
    unidade = _get_field(row, "UNIDADE", "unidade") or None
    assunto = _get_field(row, "ASSUNTO", "assunto")
    tipo_ato = _get_field(row, "TIPO_ATO", "tipo_ato") or assunto or None
    titulo = _get_field(row, "TITULO_PUBLICACAO", "titulo", "TITULO")
    texto = (
        _get_field(row, "TEXTO", "EXTRATO", "texto_ou_extrato")
        or titulo
        or None
    )
    link_extrato = _get_field(row, "LINK_EXTRATO", "link_extrato") or None
    link_edicao = _get_field(row, "LINK_EDICAO", "link_edicao") or None

    # Prefer structured fields for weighted classifier when available
    try:
        cls = classify_act(
            texto or titulo or "",
            title=titulo or None,
            official_type=tipo_ato or None,
            subject=assunto or None,
            category=categoria or None,
        )
    except TypeError:
        # Backward-compatible signature: classify_act(text, secondary=...)
        classify_blob = " ".join(
            x for x in (titulo or "", assunto or "", tipo_ato or "", categoria or "") if x
        )
        cls = classify_act(classify_blob)

    hash_parts = {
        "fonte": SOURCE_NAME,
        "resource_id": resource_id,
        "numero_publicacao": numero_pub,
        "numero_edicao": numero_ed,
        "data_publicacao": data_pub,
        "titulo": titulo,
        "assunto": assunto,
    }
    rhash = record_hash_for(hash_parts)

    # Preserve original columns under raw_columns
    original = {str(k): v for k, v in row.items()}

    confidence = cls.get("confidence")
    confidence_label = cls.get("confidence_label")
    if confidence_label is None and isinstance(confidence, str):
        confidence_label = confidence

    return {
        "fonte": SOURCE_NAME,
        "portal": PORTAL,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "numero_publicacao": numero_pub or None,
        "numero_edicao": numero_ed or None,
        "data_edicao": data_ed,
        "data_publicacao": data_pub,
        "orgao": orgao or None,
        "unidade": unidade,
        "categoria": categoria or None,
        "assunto": assunto or None,
        "tipo_ato": tipo_ato,
        "titulo": titulo or None,
        "texto_ou_extrato": texto,
        "link_extrato": link_extrato,
        "link_edicao": link_edicao,
        "record_hash": rhash,
        "first_seen": ts,
        "last_seen": ts,
        "ingested_at": ts,
        "act_category": cls.get("category"),
        "act_confidence": confidence,
        "act_confidence_label": confidence_label,
        "act_evidence": cls.get("evidence"),
        "raw_columns": original,
        "record_type": "publication",
        "source": SOURCE_NAME,
    }


def process_resource_csv(
    download_meta: dict[str, Any],
    *,
    max_rows: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse raw CSV and return (normalized_records, metrics)."""
    path = download_meta.get("path")
    rid = download_meta.get("resource_id") or ""
    name = download_meta.get("name")
    metrics: dict[str, Any] = {
        "resource_id": rid,
        "rows_read": 0,
        "rows_normalized": 0,
        "encoding": None,
        "error": None,
    }
    if not path or not Path(path).is_file():
        metrics["error"] = "raw body missing"
        return [], metrics

    enc = detect_encoding(path)
    metrics["encoding"] = enc
    now = datetime.now(UTC).isoformat()
    records: list[dict[str, Any]] = []
    try:
        for row in iter_csv_rows(path, max_rows=max_rows, encoding=enc):
            metrics["rows_read"] += 1
            rec = normalize_publication_row(
                row, resource_id=rid, resource_name=name, now=now
            )
            records.append(rec)
        metrics["rows_normalized"] = len(records)
    except Exception as e:  # noqa: BLE001
        metrics["error"] = str(e)
        _logger.error("[%s] CSV process error resource=%s: %s", SOURCE_NAME, rid, e)
    return records, metrics


def write_normalized_jsonl(
    records: list[dict[str, Any]],
    *,
    resource_id: str,
    run_id: str,
) -> Path | None:
    """Persist normalized rows as JSONL under data/normalized/."""
    if not records:
        return None
    out_dir = NORMALIZED_ROOT / str(resource_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            # Drop bulky act_evidence from disk? keep full for QA
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return path


# ---------------------------------------------------------------------------
# Discovery helpers (dry-run / catalog)
# ---------------------------------------------------------------------------


def _resource_record(res: dict, *, mode: str) -> dict:
    """One raw record describing a CKAN resource (catalog row, not file body)."""
    return {
        "record_type": "ckan_resource",
        "source": SOURCE_NAME,
        "mode": mode,
        "package_id": res.get("package_id"),
        "package_title": res.get("package_title"),
        "resource_id": res.get("id"),
        "name": res.get("name"),
        "format": res.get("format"),
        "last_modified": res.get("last_modified"),
        "url": res.get("url"),
        "size": res.get("size"),
        "datastore_active": res.get("datastore_active"),
        "mimetype": res.get("mimetype"),
        "period": detect_period(res.get("name")),
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def _discovery_crawl(mode: str) -> list[dict]:
    """Legacy discovery-only path (used when dry_run=True)."""
    records: list[dict] = []
    packages_seen: list[str] = []

    if mode in {"smoke", "full", "backfill"}:
        status = status_show()
        time.sleep(REQUEST_DELAY)
        if status is not None:
            records.append(
                {
                    "record_type": "ckan_status",
                    "source": SOURCE_NAME,
                    "mode": mode,
                    "status": status,
                    "fetched_at": datetime.now(UTC).isoformat(),
                }
            )

        search = package_search("diario", rows=10)
        time.sleep(REQUEST_DELAY)
        if search:
            hits = search.get("results") or []
            records.append(
                {
                    "record_type": "package_search",
                    "source": SOURCE_NAME,
                    "mode": mode,
                    "q": "diario",
                    "count": search.get("count"),
                    "package_ids": [h.get("name") for h in hits],
                    "fetched_at": datetime.now(UTC).isoformat(),
                }
            )

    pkg_ids = list(RELATED_PACKAGES) if mode in {"full", "backfill"} else [PRIMARY_PACKAGE]
    resource_summary: list[dict] = []
    for pkg_id in pkg_ids:
        pkg = package_show(pkg_id)
        time.sleep(REQUEST_DELAY)
        if not pkg:
            _logger.error("[%s] package_show failed for %s", SOURCE_NAME, pkg_id)
            continue
        packages_seen.append(pkg.get("name") or pkg_id)
        resources = list_resources(pkg)
        for res in resources:
            rec = _resource_record(res, mode=mode)
            records.append(rec)
            resource_summary.append(
                {
                    "id": res.get("id"),
                    "name": res.get("name"),
                    "format": res.get("format"),
                    "last_modified": res.get("last_modified"),
                    "url": res.get("url"),
                    "period": detect_period(res.get("name")),
                }
            )

    cp = {
        "source": SOURCE_NAME,
        "mode": mode,
        "dry_run": True,
        "packages": packages_seen,
        "resource_count": len(resource_summary),
        "resources": resource_summary,
        "saved_at": datetime.now(UTC).isoformat(),
    }
    path = save_checkpoint(cp, name="last_smoke.json")
    _logger.info(
        "[%s] discovery done: %d records, %d resources, checkpoint=%s",
        SOURCE_NAME,
        len(records),
        len(resource_summary),
        path,
    )
    return records


# ---------------------------------------------------------------------------
# Metrics / evidence
# ---------------------------------------------------------------------------


def _count_act_categories(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        cat = r.get("act_category") or "outros"
        counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def write_terminal_artifact(
    report: dict[str, Any],
    *,
    mode: str,
    run_id: str,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{mode}-{run_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Crawl / transform
# ---------------------------------------------------------------------------


def crawl(
    mode: str = "smoke",
    *,
    dry_run: bool = False,
    max_rows: int | None = None,
    run_id: str | None = None,
    force_download: bool = False,
) -> list[dict]:
    """Crawl dados.sc.gov.br DOE bulk publications.

    Args:
        mode: ``smoke`` | ``incremental`` | ``backfill`` | ``full``
        dry_run: if True, only list catalog resources (no file download).
        max_rows: optional row cap per resource (smoke default = SMOKE_MAX_ROWS).
        run_id: optional fixed run id.
        force_download: re-download even if local hash matches.

    Returns:
        dry_run: catalog metadata records.
        live: normalized publication records.
    """
    mode = (mode or "smoke").strip().lower()
    if mode not in {"smoke", "full", "incremental", "backfill"}:
        _logger.warning("Unknown mode %r — falling back to smoke", mode)
        mode = "smoke"

    if dry_run:
        return _discovery_crawl(mode)

    run_id = run_id or new_run_id(prefix=f"dados-sc-{mode}")
    started_at = datetime.now(UTC).isoformat()
    git = get_git_meta()
    _logger.info(
        "[%s] crawl mode=%s run_id=%s git_sha=%s",
        SOURCE_NAME,
        mode,
        run_id,
        (git.get("git_sha") or "")[:12],
    )

    if max_rows is None and mode == "smoke":
        max_rows = SMOKE_MAX_ROWS

    errors: list[str] = []
    cp_name = checkpoint_name_for_mode(mode)
    cp = load_checkpoint(cp_name) or empty_checkpoint(mode=mode, run_id=run_id)
    # Allow resume across runs — keep processed_resources map
    processed: dict[str, Any] = dict(cp.get("processed_resources") or {})
    completed_ids: list[str] = list(cp.get("completed_resource_ids") or [])

    pkg = package_show(PRIMARY_PACKAGE)
    time.sleep(REQUEST_DELAY)
    if not pkg:
        errors.append(f"package_show failed for {PRIMARY_PACKAGE}")
        artifact = _finalize_run(
            mode=mode,
            run_id=run_id,
            started_at=started_at,
            records=[],
            preferred=[],
            selected=[],
            download_results=[],
            process_metrics=[],
            processed=processed,
            completed_ids=completed_ids,
            errors=errors,
            cp_name=cp_name,
            live_fetch=True,
            status="error",
        )
        _logger.error("[%s] abort: %s artifact=%s", SOURCE_NAME, errors, artifact)
        return []

    resources = list_resources(pkg)
    preferred = prefer_csv_resources(resources)
    selected = select_resources_for_mode(preferred, mode, processed=processed)

    if not selected:
        errors.append("no resources selected")
        _finalize_run(
            mode=mode,
            run_id=run_id,
            started_at=started_at,
            records=[],
            preferred=preferred,
            selected=selected,
            download_results=[],
            process_metrics=[],
            processed=processed,
            completed_ids=completed_ids,
            errors=errors,
            cp_name=cp_name,
            live_fetch=True,
            status="error",
        )
        return []

    all_records: list[dict] = []
    download_results: list[dict] = []
    process_metrics: list[dict] = []

    for res in selected:
        rid = res.get("id") or ""
        # Resume: if already completed with same local hash and not smoke re-sample
        if (
            mode != "smoke"
            and rid in processed
            and not force_download
        ):
            prev = processed[rid]
            body = raw_body_path(rid, res.get("name"))
            if body.is_file() and prev.get("sha256"):
                local = sha256_file(body)
                if local == prev.get("sha256"):
                    _logger.info(
                        "[%s] checkpoint resume skip resource_id=%s",
                        SOURCE_NAME,
                        rid,
                    )
                    download_results.append(
                        {
                            "resource_id": rid,
                            "name": res.get("name"),
                            "skipped_identical": True,
                            "downloaded": False,
                            "sha256": local,
                            "path": str(body),
                            "resumed": True,
                        }
                    )
                    continue

        dl = download_resource_to_raw(res, force=force_download)
        download_results.append(dl)
        if dl.get("error"):
            errors.append(f"{rid}: {dl['error']}")
            continue
        if not dl.get("path"):
            errors.append(f"{rid}: no path after download")
            continue

        # If hash unchanged and already processed (incremental/backfill), skip parse
        if (
            mode != "smoke"
            and dl.get("skipped_identical")
            and rid in processed
            and processed[rid].get("sha256") == dl.get("sha256")
            and processed[rid].get("rows_processed", 0) > 0
        ):
            _logger.info(
                "[%s] skip re-process identical hash resource_id=%s",
                SOURCE_NAME,
                rid,
            )
            process_metrics.append(
                {
                    "resource_id": rid,
                    "rows_read": 0,
                    "rows_normalized": 0,
                    "skipped_identical": True,
                    "encoding": None,
                }
            )
            continue

        recs, metrics = process_resource_csv(dl, max_rows=max_rows)
        process_metrics.append(metrics)
        if metrics.get("error"):
            errors.append(f"{rid}: process {metrics['error']}")

        write_normalized_jsonl(recs, resource_id=rid, run_id=run_id)
        all_records.extend(recs)

        processed[rid] = {
            "sha256": dl.get("sha256"),
            "name": res.get("name"),
            "url": res.get("url"),
            "period": detect_period(res.get("name")),
            "size": dl.get("size"),
            "etag": dl.get("etag"),
            "last_modified": dl.get("last_modified"),
            "processed_at": datetime.now(UTC).isoformat(),
            "rows_processed": metrics.get("rows_normalized", 0),
            "encoding": metrics.get("encoding"),
            "skipped_identical": bool(dl.get("skipped_identical")),
            "max_rows": max_rows,
        }
        if rid not in completed_ids:
            completed_ids.append(rid)

        # Persist checkpoint after each resource (resume-friendly)
        cp_payload = {
            "source": SOURCE_NAME,
            "mode": mode,
            "run_id": run_id,
            "processed_resources": processed,
            "completed_resource_ids": completed_ids,
            "saved_at": datetime.now(UTC).isoformat(),
        }
        save_checkpoint(cp_payload, name=cp_name)

    status = "ok" if all_records and not errors else ("partial" if all_records else "error")
    artifact = _finalize_run(
        mode=mode,
        run_id=run_id,
        started_at=started_at,
        records=all_records,
        preferred=preferred,
        selected=selected,
        download_results=download_results,
        process_metrics=process_metrics,
        processed=processed,
        completed_ids=completed_ids,
        errors=errors,
        cp_name=cp_name,
        live_fetch=True,
        status=status,
    )
    _logger.info(
        "[%s] crawl done status=%s records=%d artifact=%s",
        SOURCE_NAME,
        status,
        len(all_records),
        artifact,
    )
    return all_records


def _finalize_run(
    *,
    mode: str,
    run_id: str,
    started_at: str,
    records: list[dict],
    preferred: list[dict],
    selected: list[dict],
    download_results: list[dict],
    process_metrics: list[dict],
    processed: dict[str, Any],
    completed_ids: list[str],
    errors: list[str],
    cp_name: str,
    live_fetch: bool,
    status: str,
) -> Path:
    completed_at = datetime.now(UTC).isoformat()
    cp_payload = {
        "source": SOURCE_NAME,
        "mode": mode,
        "run_id": run_id,
        "processed_resources": processed,
        "completed_resource_ids": completed_ids,
        "saved_at": completed_at,
    }
    cp_path = save_checkpoint(cp_payload, name=cp_name)
    # Also write last_smoke.json for smoke convenience
    if mode == "smoke":
        save_checkpoint(cp_payload, name="last_smoke.json")

    counts = {
        "resources_listed": len(preferred),
        "resources_selected": len(selected),
        "resources_downloaded": sum(1 for d in download_results if d.get("downloaded")),
        "resources_skipped_identical": sum(
            1 for d in download_results if d.get("skipped_identical")
        ),
        "resources_resumed": sum(1 for d in download_results if d.get("resumed")),
        "rows_normalized": len(records),
        "rows_read": sum(int(m.get("rows_read") or 0) for m in process_metrics),
        "errors": len(errors),
        "act_categories": _count_act_categories(records),
    }

    sample = records[:5]
    # strip bulky raw_columns from sample in artifact
    sample_light = []
    for s in sample:
        slim = {k: v for k, v in s.items() if k != "raw_columns"}
        sample_light.append(slim)

    report: dict[str, Any] = {
        "run_id": run_id,
        "source": SOURCE_NAME,
        "portal": PORTAL,
        "package": PRIMARY_PACKAGE,
        "mode": mode,
        "status": status,
        "live_fetch": live_fetch,
        "started_at": started_at,
        "completed_at": completed_at,
        "counts": counts,
        "errors": errors,
        "selected_resources": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "format": r.get("format"),
                "period": detect_period(r.get("name")),
                "url": r.get("url"),
            }
            for r in selected
        ],
        "download_results": [
            {
                "resource_id": d.get("resource_id"),
                "name": d.get("name"),
                "sha256": d.get("sha256"),
                "size": d.get("size"),
                "etag": d.get("etag"),
                "last_modified": d.get("last_modified"),
                "skipped_identical": d.get("skipped_identical"),
                "downloaded": d.get("downloaded"),
                "resumed": d.get("resumed"),
                "error": d.get("error"),
                "path": d.get("path"),
            }
            for d in download_results
        ],
        "process_metrics": process_metrics,
        "sample_records": sample_light,
        "checkpoint_path": str(cp_path),
    }

    out_path = write_terminal_artifact(report, mode=mode, run_id=run_id)
    evidence = build_run_evidence(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        command="python -m scripts.crawl.dados_abertos_sc_crawler",
        args={"mode": mode, "live_fetch": live_fetch},
        checkpoint_path=str(cp_path),
        output_path=str(out_path),
        counts_after=counts,
        status=status,
        errors=errors,
        claims_allowed=[
            "live CKAN package_show",
            "raw zone SHA-256 registered",
            "publications normalized + classified",
        ],
        claims_forbidden=["DB upsert official_acts (schema owned elsewhere)"],
        live_fetch=live_fetch,
        source=SOURCE_NAME,
    )
    report["evidence"] = evidence
    # rewrite with evidence + output hash
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    # refresh evidence.output_hash after final write
    report["evidence"]["output_hash"] = sha256_file(out_path)
    report["evidence"]["checkpoint_hash"] = sha256_file(cp_path)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return out_path


def _content_hash(raw: dict) -> str:
    key = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()


def transform_record(raw: dict) -> dict | None:
    """Normalize one raw catalog or publication record for monitor compatibility."""
    if not isinstance(raw, dict):
        return None

    rtype = raw.get("record_type")
    if rtype in {"ckan_status", "package_search", "download_candidate"}:
        return {
            "pncp_id": None,
            "metadata_only": True,
            "record_type": rtype,
            "source": SOURCE_NAME,
            "objeto_compra": f"[dados_sc] {rtype}",
            "payload": raw,
            "content_hash": _content_hash(raw),
        }

    # Normalized publication rows from live crawl
    if rtype == "publication" or (
        raw.get("fonte") == SOURCE_NAME and raw.get("record_hash")
    ):
        rid = raw.get("resource_id") or ""
        num = raw.get("numero_publicacao") or raw.get("record_hash") or ""
        pncp_id_input = f"{SOURCE_NAME}|pub|{rid}|{num}|{raw.get('record_hash')}"
        pncp_id = hashlib.md5(
            pncp_id_input.encode("utf-8"), usedforsecurity=False
        ).hexdigest()
        objeto = (raw.get("titulo") or raw.get("assunto") or raw.get("tipo_ato") or "")[
            :500
        ]
        return {
            "pncp_id": pncp_id,
            "objeto_compra": objeto or f"DOE-SC publicação {num}",
            "valor_total_estimado": None,
            "modalidade_id": 0,
            "modalidade_nome": raw.get("act_category") or "Publicação DOE",
            "esfera_id": ESFERA_ID_ESTADUAL,
            "uf": "SC",
            "municipio": None,
            "codigo_municipio_ibge": "",
            "orgao_razao_social": raw.get("orgao")
            or "Diário Oficial do Estado de Santa Catarina",
            "orgao_cnpj": None,
            "data_publicacao": raw.get("data_publicacao"),
            "data_abertura": None,
            "data_encerramento": None,
            "link_pncp": raw.get("link_extrato")
            or raw.get("link_edicao")
            or f"{CKAN_BASE}/dataset/{PRIMARY_PACKAGE}",
            "content_hash": raw.get("record_hash") or _content_hash(raw),
            "source_id": str(num or raw.get("record_hash")),
            "source": SOURCE_NAME,
            "act_category": raw.get("act_category"),
            "act_confidence": raw.get("act_confidence"),
            "metadata_only": False,
        }

    if rtype != "ckan_resource" and not raw.get("resource_id"):
        return None

    rid = raw.get("resource_id") or raw.get("id")
    if not rid:
        return None

    name = (raw.get("name") or "").strip()
    pkg = raw.get("package_id") or PRIMARY_PACKAGE
    fmt = raw.get("format") or ""
    url = raw.get("url") or ""
    pncp_id_input = f"{SOURCE_NAME}|{pkg}|{rid}"
    pncp_id = hashlib.md5(pncp_id_input.encode("utf-8"), usedforsecurity=False).hexdigest()

    return {
        "pncp_id": pncp_id,
        "objeto_compra": f"DOE-SC dados abertos: {name or rid} ({fmt})",
        "valor_total_estimado": None,
        "modalidade_id": 0,
        "modalidade_nome": "Publicação DOE (bulk CKAN)",
        "esfera_id": ESFERA_ID_ESTADUAL,
        "uf": "SC",
        "municipio": None,
        "codigo_municipio_ibge": "",
        "orgao_razao_social": "Diário Oficial do Estado de Santa Catarina",
        "orgao_cnpj": None,
        "data_publicacao": (raw.get("last_modified") or "")[:10] or None,
        "data_abertura": None,
        "data_encerramento": None,
        "link_pncp": url or f"{CKAN_BASE}/dataset/{pkg}",
        "content_hash": _content_hash(raw),
        "source_id": str(rid),
        "source": SOURCE_NAME,
        "ckan_package": pkg,
        "ckan_format": fmt,
        "metadata_only": True,  # catalog row — not a single publication act
    }


def transform(records: list[dict]) -> list[dict]:
    """Monitor-compatible transform."""
    out: list[dict] = []
    skipped = 0
    for rec in records:
        t = transform_record(rec)
        if t:
            out.append(t)
        else:
            skipped += 1
    _logger.info(
        "[%s] transform: %d kept, %d skipped",
        SOURCE_NAME,
        len(out),
        skipped,
    )
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(
        description="Dados Abertos SC CKAN crawler — DOE bulk publications"
    )
    p.add_argument(
        "--mode",
        default="smoke",
        choices=["smoke", "full", "incremental", "backfill"],
        help="Crawl mode (default: smoke)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List resources only, do not download bodies",
    )
    p.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Force live download/ingest (default behavior)",
    )
    p.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help=f"Max rows per resource (smoke default {SMOKE_MAX_ROWS})",
    )
    p.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download even if local SHA-256 matches",
    )
    p.add_argument("--json", action="store_true", help="Print summary JSON to stdout")
    args = p.parse_args(argv)

    dry_run = bool(args.dry_run) and not args.no_dry_run
    git = get_git_meta()
    run_id = new_run_id(prefix=f"dados-sc-{args.mode}")
    print(
        f"SOURCE={SOURCE_NAME} mode={args.mode} dry_run={dry_run} "
        f"run_id={run_id} git_sha={(git.get('git_sha') or '')[:12]}"
    )

    records = crawl(
        mode=args.mode,
        dry_run=dry_run,
        max_rows=args.max_rows,
        run_id=run_id,
        force_download=args.force_download,
    )
    transformed = transform(records)

    pubs = [r for r in records if r.get("record_type") == "publication"]
    resources = [r for r in records if r.get("record_type") == "ckan_resource"]

    print(f"raw_records={len(records)} transformed={len(transformed)}")
    if dry_run:
        print(f"resources_listed={len(resources)}")
        for r in resources[:15]:
            print(
                f"  - {r.get('name')} | {r.get('format')} | "
                f"id={r.get('resource_id')} | period={r.get('period')}"
            )
        if len(resources) > 15:
            print(f"  ... +{len(resources) - 15} more")
    else:
        print(f"publications={len(pubs)}")
        cats = _count_act_categories(pubs)
        print(f"act_categories={cats}")
        for r in pubs[:5]:
            print(
                f"  - pub={r.get('numero_publicacao')} ed={r.get('numero_edicao')} "
                f"cat={r.get('act_category')} | {(r.get('titulo') or '')[:80]}"
            )
        # locate latest artifact
        artifacts = sorted(OUTPUT_DIR.glob(f"{args.mode}-{run_id}.json"))
        if artifacts:
            print(f"artifact={artifacts[-1]}")

    if args.json:
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "count": len(records),
                    "publications": len(pubs),
                    "transformed": len(transformed),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    if dry_run:
        return 0 if resources else 1
    return 0 if pubs else 1


if __name__ == "__main__":
    raise SystemExit(main())
