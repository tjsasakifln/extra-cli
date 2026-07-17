#!/usr/bin/env python3
"""CIGA DOM-SC publication-level ingestion (real municipal publications).

Source: https://dados.ciga.sc.gov.br/api/3/action/  (public CKAN, no token)

Downloads monthly ZIP resources containing ``autopublicacoes`` JSON and
persists immutable raw bytes + normalized publication records (JSONL).

This module is intentionally separate from ``ciga_ckan_crawler.py``
(entity coverage). It reuses CKAN helpers from that module without modifying
it when possible.

Usage:
    python3 -m scripts.crawl.ciga_dom_publications --mode smoke
    python3 -m scripts.crawl.ciga_dom_publications --mode incremental
    python3 -m scripts.crawl.ciga_dom_publications --mode full --max-zips 5
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.act_classifier import classify_act  # noqa: E402
from scripts.crawl.ciga_ckan_crawler import (  # noqa: E402
    CKAN_API,
    REQUEST_DELAY,
    classify_month,
    get_package,
    get_package_resources,
    list_domsc_months,
)
from scripts.crawl.run_evidence import (  # noqa: E402
    build_run_evidence,
    new_run_id,
    sha256_bytes,
    sha256_file,
)
from scripts.crawl.security import USER_AGENT  # noqa: E402

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / paths
# ---------------------------------------------------------------------------

SOURCE_NAME = "ciga_dom"
SOURCE_LABEL = "CIGA DOM-SC publicações municipais"

RAW_DIR = _PROJECT_ROOT / "data" / "raw" / "ciga_dom"
CHECKPOINT_DIR = _PROJECT_ROOT / "data" / "ciga_dom_checkpoints"
OUTPUT_DIR = _PROJECT_ROOT / "output" / "ciga_dom"

IBGE_CACHE_PATH = _PROJECT_ROOT / "data" / "ibge_cache.json"
MUNICIPIOS_SC_PATH = _PROJECT_ROOT / "data" / "municipios_sc.json"

HTTP_TIMEOUT = 90
SMOKE_MAX_ZIPS = 2
DEFAULT_MAX_ZIPS_FULL = 0  # 0 = no limit

_ZIP_FORMATS = frozenset({"ZIP", "APPLICATION/ZIP", "APPLICATION/X-ZIP-COMPRESSED"})
_JSON_FORMATS = frozenset({"JSON", "APPLICATION/JSON"})
_CSV_FORMATS = frozenset({"CSV", "TEXT/CSV"})

# Month name fragments in package ids: domsc-publicacoes-de-{mm}-{yyyy}
_MONTH_RE = re.compile(
    r"(?:domsc|dom-sc)-(?:auto)?publicacoes-de-(\d{1,2})-(\d{4})",
    re.I,
)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def parse_package_month(package_id: str) -> tuple[int, int] | None:
    """Return (year, month) from a DOM-SC package id, or None."""
    m = _MONTH_RE.search(package_id or "")
    if not m:
        label = classify_month(package_id or "")
        if not label:
            return None
        try:
            mm_s, yyyy_s = label.split("-", 1)
            return int(yyyy_s), int(mm_s)
        except (ValueError, TypeError):
            return None
    try:
        return int(m.group(2)), int(m.group(1))
    except (ValueError, TypeError):
        return None


def sort_domsc_packages(package_ids: list[str]) -> list[str]:
    """Sort package ids oldest → newest by (year, month). Unknowns last."""

    def key(pid: str) -> tuple[int, int, str]:
        ym = parse_package_month(pid)
        if ym is None:
            return (0, 0, pid)
        return (ym[0], ym[1], pid)

    return sorted(package_ids, key=key)


def discover_latest_package(
    *,
    package_ids: list[str] | None = None,
) -> str | None:
    """Auto-discover the most recent monthly DOM-SC package id."""
    ids = package_ids if package_ids is not None else list_domsc_months()
    if not ids:
        _logger.error("No DOM-SC packages found via CKAN package_list")
        return None
    ordered = sort_domsc_packages(ids)
    latest = ordered[-1]
    _logger.info("Latest DOM-SC package: %s (of %d)", latest, len(ordered))
    return latest


def resource_kind(resource: dict[str, Any]) -> str:
    """Classify a CKAN resource as zip | json | csv | other."""
    fmt = (resource.get("format") or "").strip().upper()
    url = (resource.get("url") or "").strip().lower()
    name = (resource.get("name") or "").strip().lower()
    if fmt in _ZIP_FORMATS or url.endswith(".zip") or name.endswith(".zip"):
        return "zip"
    if fmt in _JSON_FORMATS or url.endswith(".json") or name.endswith(".json"):
        return "json"
    if fmt in _CSV_FORMATS or url.endswith(".csv") or name.endswith(".csv"):
        return "csv"
    return "other"


def list_ingestible_resources(pkg: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ZIP/JSON/CSV resources with kind annotation, stable order."""
    out: list[dict[str, Any]] = []
    for r in get_package_resources(pkg):
        kind = resource_kind(r)
        if kind not in {"zip", "json", "csv"}:
            continue
        out.append(
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "format": (r.get("format") or "").upper(),
                "url": r.get("url"),
                "size": r.get("size"),
                "last_modified": r.get("last_modified") or r.get("metadata_modified"),
                "kind": kind,
            }
        )
    # Prefer later days of the month for smoke freshness: reverse by name/url
    out.sort(key=lambda x: (x.get("name") or "", x.get("url") or ""))
    return out


# ---------------------------------------------------------------------------
# HTTP download (soft failures)
# ---------------------------------------------------------------------------


def download_bytes(url: str, *, timeout: int = HTTP_TIMEOUT) -> tuple[bytes | None, str | None]:
    """Download URL body. Returns (bytes, error_message). Soft-fails on HTTP errors."""
    if not url:
        return None, "empty url"
    req = urllib.request.Request(  # noqa: S310 — CIGA HTTPS resource URLs
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read(), None
    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code}: {e.reason}"
        _logger.error("Download failed %s — %s", url, msg)
        return None, msg
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        msg = f"{type(e).__name__}: {e}"
        _logger.error("Download failed %s — %s", url, msg)
        return None, msg


# ---------------------------------------------------------------------------
# Safe ZIP extract (zip-slip prevention)
# ---------------------------------------------------------------------------


def is_safe_zip_member(dest_dir: Path, member_name: str) -> bool:
    """Return True if member_name resolves inside dest_dir (zip-slip safe)."""
    if not member_name:
        return False
    # Reject absolute paths (posix or windows) and drive letters
    if member_name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", member_name):
        return False
    # Normalize separators and reject parent traversal in the declared name
    parts = Path(member_name.replace("\\", "/")).parts
    if ".." in parts:
        return False
    try:
        dest_resolved = dest_dir.resolve()
        target = (dest_dir / member_name).resolve()
    except (OSError, RuntimeError):
        return False
    try:
        target.relative_to(dest_resolved)
    except ValueError:
        return False
    return True

def safe_extract_zip(
    raw: bytes,
    dest_dir: Path,
    *,
    members_filter: set[str] | None = None,
) -> list[Path]:
    """Extract ZIP bytes into dest_dir with zip-slip rejection.

    Returns list of extracted file paths. Raises ValueError on invalid ZIP or
    if any member fails safety check (nothing extracted on unsafe member).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise ValueError(f"invalid zip: {e}") from e

    names = zf.namelist()
    if not names:
        return []

    # Pre-validate all members before writing anything
    to_extract: list[str] = []
    for name in names:
        if name.endswith("/"):
            if not is_safe_zip_member(dest_dir, name):
                raise ValueError(f"zip-slip rejected: {name!r}")
            continue
        if members_filter is not None and name not in members_filter:
            continue
        if not is_safe_zip_member(dest_dir, name):
            raise ValueError(f"zip-slip rejected: {name!r}")
        to_extract.append(name)

    extracted: list[Path] = []
    for name in to_extract:
        target = dest_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src, target.open("wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        extracted.append(target)
    return extracted


def _zip_member_name_is_safe(member_name: str) -> bool:
    """Path-safety check independent of destination (for streaming reads)."""
    if not member_name:
        return False
    if member_name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", member_name):
        return False
    parts = Path(member_name.replace("\\", "/")).parts
    return ".." not in parts


def iter_zip_json_members(raw: bytes) -> Iterator[tuple[str, bytes]]:
    """Yield (member_name, json_bytes) from a ZIP without full-month buffering.

    Still loads each member into memory individually (typical DOM-SC member
    is a single JSON file of a few MB).
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise ValueError(f"invalid zip: {e}") from e
    for name in zf.namelist():
        if not _zip_member_name_is_safe(name):
            raise ValueError(f"zip-slip rejected: {name!r}")
        if name.endswith("/"):
            continue
        if not name.lower().endswith((".json", ".csv")):
            continue
        yield name, zf.read(name)

# ---------------------------------------------------------------------------
# Parse / normalize
# ---------------------------------------------------------------------------


def _strip_html(html: str, max_len: int = 0) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def iter_autopublicacoes(payload: Any) -> Iterator[dict[str, Any]]:
    """Yield publication dicts from a parsed JSON payload."""
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if not isinstance(payload, dict):
        return
    pubs = payload.get("autopublicacoes")
    if isinstance(pubs, list):
        for item in pubs:
            if isinstance(item, dict):
                yield item
        return
    # Fallback: single-record shapes
    if any(k in payload for k in ("codigo", "titulo", "municipio", "entidade")):
        yield payload


def parse_json_publications(data: bytes) -> list[dict[str, Any]]:
    """Parse JSON bytes into list of raw publication dicts."""
    try:
        payload = json.loads(data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid json: {e}") from e
    return list(iter_autopublicacoes(payload))


def _content_hash(raw: dict[str, Any]) -> str:
    key = "|".join(
        [
            str(raw.get("codigo") or ""),
            str(raw.get("titulo") or ""),
            str(raw.get("data") or "")[:19],
            str(raw.get("entidade") or ""),
            str(raw.get("municipio") or ""),
            str(raw.get("categoria") or ""),
            str(raw.get("link") or raw.get("url") or ""),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def extract_edicao(resource_name: str | None, data_pub: str | None) -> str | None:
    """Derive edition label from resource name or publication date."""
    name = resource_name or ""
    # "Publicações de 01/12/2025 entre 00:00 e 11:59 (598)"
    m = re.search(r"(\d{2}/\d{2}/\d{4})", name)
    if m:
        return m.group(1)
    m2 = re.search(r"(20\d{2}_\d{2}_\d{2})", name)
    if m2:
        y, mo, d = m2.group(1).split("_")
        return f"{d}/{mo}/{y}"
    if data_pub:
        d = data_pub[:10]
        if re.match(r"\d{4}-\d{2}-\d{2}", d):
            y, mo, day = d.split("-")
            return f"{day}/{mo}/{y}"
    return None


def normalize_publication(
    raw: dict[str, Any],
    *,
    package_id: str,
    resource: dict[str, Any] | None = None,
    source_file: str | None = None,
) -> dict[str, Any] | None:
    """Normalize one autopublicacoes row with act classification.

    Identifies: municipio, orgao/entidade, edicao, data, titulo, texto, url.
    """
    if not isinstance(raw, dict):
        return None

    codigo = raw.get("codigo")
    titulo = (raw.get("titulo") or "").strip()
    municipio = (raw.get("municipio") or "").strip()
    entidade = (raw.get("entidade") or raw.get("orgao") or "").strip()
    data_raw = str(raw.get("data") or "").strip()
    data_pub = data_raw[:10] if data_raw else None
    if data_pub and not re.match(r"\d{4}-\d{2}-\d{2}", data_pub):
        # keep original short form if not ISO
        data_pub = data_raw[:19] or None
    url = (raw.get("url") or raw.get("link") or "").strip()
    if not url and codigo is not None:
        url = f"https://diariomunicipal.sc.gov.br/?q=id:{codigo}"
    texto_html = raw.get("texto") or ""
    texto = _strip_html(str(texto_html)) if texto_html else ""
    categoria = (raw.get("categoria") or "").strip()
    res_name = (resource or {}).get("name")
    edicao = extract_edicao(res_name, data_pub)

    # Require at least some identity signal
    if not any([codigo, titulo, municipio, entidade, url]):
        return None

    classification = classify_act(
        f"{titulo} {categoria}".strip(),
        secondary=texto[:500] if texto else None,
    )

    record_id = str(codigo).strip() if codigo is not None and str(codigo).strip() else None
    if not record_id:
        record_id = _content_hash(raw)[:16]

    return {
        "source": SOURCE_NAME,
        "package_id": package_id,
        "resource_id": (resource or {}).get("id"),
        "resource_name": res_name,
        "source_file": source_file,
        "codigo": record_id,
        "municipio": municipio or None,
        "orgao": entidade or None,
        "entidade": entidade or None,
        "edicao": edicao,
        "data": data_pub,
        "data_raw": data_raw or None,
        "titulo": titulo or None,
        "texto": texto or None,
        "texto_html_present": bool(texto_html),
        "url": url or None,
        "categoria_dom": categoria or None,
        "cod_registro_info_sfinge": raw.get("cod_registro_info_sfinge"),
        "act_category": classification.get("category"),
        "act_confidence": classification.get("confidence"),
        "act_confidence_label": classification.get("confidence_label"),
        "act_evidence": classification.get("evidence"),
        "act_matched_rule": classification.get("matched_rule"),
        "act_needs_human_review": classification.get("needs_human_review"),
        "act_reason": classification.get("reason"),
        "content_hash": _content_hash(raw),
        "ingested_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------


def _default_checkpoint() -> dict[str, Any]:
    return {
        "meta": {
            "source": SOURCE_NAME,
            "run_id": None,
            "updated_at": None,
        },
        "completed_resources": {},
        "completed_files": {},
        "packages_seen": [],
    }


def checkpoint_path() -> Path:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR / "checkpoint.json"


def load_checkpoint() -> dict[str, Any]:
    path = checkpoint_path()
    if not path.exists():
        return _default_checkpoint()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_checkpoint()
        data.setdefault("meta", {})
        data.setdefault("completed_resources", {})
        data.setdefault("completed_files", {})
        data.setdefault("packages_seen", [])
        return data
    except (json.JSONDecodeError, OSError) as e:
        _logger.warning("Could not load checkpoint: %s", e)
        return _default_checkpoint()


def save_checkpoint(cp: dict[str, Any]) -> Path:
    path = checkpoint_path()
    cp = dict(cp)
    meta = dict(cp.get("meta") or {})
    meta["source"] = SOURCE_NAME
    meta["updated_at"] = datetime.now(UTC).isoformat()
    cp["meta"] = meta
    path.write_text(json.dumps(cp, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resource_done(cp: dict[str, Any], resource_id: str) -> bool:
    entry = (cp.get("completed_resources") or {}).get(resource_id)
    if not isinstance(entry, dict):
        return False
    return entry.get("status") == "completed"


def file_done(cp: dict[str, Any], resource_id: str, filename: str) -> bool:
    key = f"{resource_id}::{filename}"
    entry = (cp.get("completed_files") or {}).get(key)
    if isinstance(entry, dict) and entry.get("status") == "completed":
        return True
    # Also check nested under resource
    res = (cp.get("completed_resources") or {}).get(resource_id) or {}
    files = res.get("files") or {}
    fentry = files.get(filename)
    return isinstance(fentry, dict) and fentry.get("status") == "completed"


def mark_file_done(
    cp: dict[str, Any],
    *,
    resource_id: str,
    filename: str,
    records: int,
    sha256: str | None = None,
) -> None:
    key = f"{resource_id}::{filename}"
    cp.setdefault("completed_files", {})[key] = {
        "status": "completed",
        "records": records,
        "sha256": sha256,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    res = cp.setdefault("completed_resources", {}).setdefault(
        resource_id,
        {"status": "in_progress", "files": {}},
    )
    res.setdefault("files", {})[filename] = {
        "status": "completed",
        "records": records,
        "sha256": sha256,
    }


def mark_resource_done(
    cp: dict[str, Any],
    *,
    resource_id: str,
    records: int,
    sha256: str | None = None,
    error: str | None = None,
) -> None:
    entry = cp.setdefault("completed_resources", {}).setdefault(resource_id, {"files": {}})
    entry["status"] = "failed" if error else "completed"
    entry["records"] = records
    entry["sha256"] = sha256
    entry["error"] = error
    entry["completed_at"] = datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Municipalities / gaps
# ---------------------------------------------------------------------------


def load_sc_municipalities() -> set[str]:
    """Load static SC municipality names (normalized lower) if available."""
    names: set[str] = set()
    if IBGE_CACHE_PATH.is_file():
        try:
            data = json.loads(IBGE_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                names.update(str(k).strip().lower() for k in data if str(k).strip())
        except (json.JSONDecodeError, OSError) as e:
            _logger.warning("ibge_cache load failed: %s", e)
    if MUNICIPIOS_SC_PATH.is_file():
        try:
            data = json.loads(MUNICIPIOS_SC_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        names.add(item.strip().lower())
                    elif isinstance(item, dict):
                        n = item.get("nome") or item.get("municipio") or item.get("name")
                        if n:
                            names.add(str(n).strip().lower())
            elif isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, dict):
                        n = v.get("nome") or v.get("municipio") or k
                    else:
                        n = k
                    if n:
                        names.add(str(n).strip().lower())
        except (json.JSONDecodeError, OSError) as e:
            _logger.warning("municipios_sc load failed: %s", e)
    return names


def _muni_key(name: str) -> str:
    """Normalize municipality name for set comparison (case + accents)."""
    import unicodedata

    s = unicodedata.normalize("NFKD", (name or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def municipality_stats(
    observed: set[str],
    universe: set[str],
) -> dict[str, Any]:
    obs_norm = {_muni_key(m) for m in observed if m and str(m).strip()}
    obs_norm.discard("")
    if universe:
        uni_norm = {_muni_key(m) for m in universe if m and str(m).strip()}
        uni_norm.discard("")
        gaps = sorted(uni_norm - obs_norm)
        covered = sorted(obs_norm & uni_norm)
        return {
            "universe_source": "static_sc_list",
            "universe_count": len(uni_norm),
            "observed_count": len(obs_norm),
            "covered_in_universe": len(covered),
            "gap_count": len(gaps),
            "gaps_sample": gaps[:50],
            "observed_sample": sorted(obs_norm)[:50],
        }
    return {
        "universe_source": "observed_only",
        "universe_count": None,
        "observed_count": len(obs_norm),
        "covered_in_universe": len(obs_norm),
        "gap_count": None,
        "gaps_sample": [],
        "observed_sample": sorted(obs_norm)[:50],
    }

# ---------------------------------------------------------------------------
# Freshness manifest
# ---------------------------------------------------------------------------


def write_freshness_manifest(
    *,
    package_id: str,
    resources: list[dict[str, Any]],
    counts: dict[str, Any],
    run_id: str,
    status: str,
    path: Path | None = None,
) -> Path:
    """Write freshness manifest for the latest ingestion."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = path or (OUTPUT_DIR / "freshness_manifest.json")
    last_mod = None
    for r in resources:
        lm = r.get("last_modified")
        if lm and (last_mod is None or str(lm) > str(last_mod)):
            last_mod = lm
    ym = parse_package_month(package_id)
    manifest = {
        "source": SOURCE_NAME,
        "label": SOURCE_LABEL,
        "run_id": run_id,
        "package_id": package_id,
        "package_year_month": f"{ym[0]:04d}-{ym[1]:02d}" if ym else None,
        "resource_count": len(resources),
        "latest_resource_modified": last_mod,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "counts": counts,
        "ckan_api": CKAN_API,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Ingestion core
# ---------------------------------------------------------------------------


def _raw_resource_dir(package_id: str, resource_id: str) -> Path:
    safe_pkg = re.sub(r"[^\w.\-]+", "_", package_id)
    safe_res = re.sub(r"[^\w.\-]+", "_", resource_id or "unknown")
    return RAW_DIR / safe_pkg / safe_res


def process_zip_resource(
    raw: bytes,
    *,
    package_id: str,
    resource: dict[str, Any],
    cp: dict[str, Any],
    jsonl_fh: Any,
    skip_completed_files: bool,
) -> dict[str, Any]:
    """Process one ZIP resource: persist raw, extract safely, normalize, append JSONL."""
    resource_id = str(resource.get("id") or "unknown")
    dest = _raw_resource_dir(package_id, resource_id)
    dest.mkdir(parents=True, exist_ok=True)

    zip_name = Path(str(resource.get("url") or "resource.zip")).name or "resource.zip"
    if not zip_name.lower().endswith(".zip"):
        zip_name = f"{zip_name}.zip"
    raw_zip_path = dest / zip_name
    raw_zip_path.write_bytes(raw)  # immutable raw snapshot
    digest = sha256_bytes(raw)

    stats = {
        "resource_id": resource_id,
        "records": 0,
        "files": 0,
        "skipped_files": 0,
        "errors": [],
        "sha256": digest,
        "raw_path": str(raw_zip_path),
    }

    try:
        members = list(iter_zip_json_members(raw))
    except ValueError as e:
        stats["errors"].append(str(e))
        mark_resource_done(cp, resource_id=resource_id, records=0, sha256=digest, error=str(e))
        return stats

    if not members:
        # empty zip is valid — mark completed with 0 records
        mark_resource_done(cp, resource_id=resource_id, records=0, sha256=digest)
        return stats

    extract_dir = dest / "extracted"
    for member_name, member_bytes in members:
        if skip_completed_files and file_done(cp, resource_id, member_name):
            stats["skipped_files"] += 1
            continue
        # Safe extract this member
        try:
            if not is_safe_zip_member(extract_dir, member_name):
                raise ValueError(f"zip-slip rejected: {member_name!r}")
            out_path = extract_dir / member_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(member_bytes)
        except ValueError as e:
            stats["errors"].append(str(e))
            continue

        file_records = 0
        try:
            pubs = parse_json_publications(member_bytes)
        except ValueError as e:
            stats["errors"].append(f"{member_name}: {e}")
            continue

        for pub in pubs:
            norm = normalize_publication(
                pub,
                package_id=package_id,
                resource=resource,
                source_file=member_name,
            )
            if not norm:
                continue
            jsonl_fh.write(json.dumps(norm, ensure_ascii=False, default=str) + "\n")
            file_records += 1
            stats["records"] += 1

        mark_file_done(
            cp,
            resource_id=resource_id,
            filename=member_name,
            records=file_records,
            sha256=sha256_bytes(member_bytes),
        )
        stats["files"] += 1

    mark_resource_done(
        cp,
        resource_id=resource_id,
        records=stats["records"],
        sha256=digest,
        error="; ".join(stats["errors"]) if stats["errors"] else None,
    )
    return stats


def process_json_resource(
    raw: bytes,
    *,
    package_id: str,
    resource: dict[str, Any],
    cp: dict[str, Any],
    jsonl_fh: Any,
    skip_completed_files: bool,
) -> dict[str, Any]:
    """Process a bare JSON resource (non-ZIP)."""
    resource_id = str(resource.get("id") or "unknown")
    dest = _raw_resource_dir(package_id, resource_id)
    dest.mkdir(parents=True, exist_ok=True)
    filename = Path(str(resource.get("url") or "resource.json")).name or "resource.json"
    if not filename.lower().endswith(".json"):
        filename = f"{filename}.json"
    raw_path = dest / filename
    raw_path.write_bytes(raw)
    digest = sha256_bytes(raw)
    stats = {
        "resource_id": resource_id,
        "records": 0,
        "files": 0,
        "skipped_files": 0,
        "errors": [],
        "sha256": digest,
        "raw_path": str(raw_path),
    }
    if skip_completed_files and file_done(cp, resource_id, filename):
        stats["skipped_files"] = 1
        return stats
    try:
        pubs = parse_json_publications(raw)
    except ValueError as e:
        stats["errors"].append(str(e))
        mark_resource_done(cp, resource_id=resource_id, records=0, sha256=digest, error=str(e))
        return stats
    for pub in pubs:
        norm = normalize_publication(
            pub,
            package_id=package_id,
            resource=resource,
            source_file=filename,
        )
        if not norm:
            continue
        jsonl_fh.write(json.dumps(norm, ensure_ascii=False, default=str) + "\n")
        stats["records"] += 1
    mark_file_done(
        cp, resource_id=resource_id, filename=filename, records=stats["records"], sha256=digest
    )
    mark_resource_done(cp, resource_id=resource_id, records=stats["records"], sha256=digest)
    stats["files"] = 1
    return stats


def run_ingestion(
    *,
    mode: str = "smoke",
    package_id: str | None = None,
    max_zips: int | None = None,
    request_delay: float = REQUEST_DELAY,
) -> dict[str, Any]:
    """Run publication ingestion. Returns terminal result dict with evidence."""
    mode = (mode or "smoke").strip().lower()
    if mode not in {"smoke", "incremental", "full"}:
        _logger.warning("Unknown mode %r — using smoke", mode)
        mode = "smoke"

    started_at = datetime.now(UTC).isoformat()
    run_id = new_run_id(prefix="ciga-dom")
    errors: list[str] = []
    observed_municipios: set[str] = set()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    run_out = OUTPUT_DIR / run_id
    run_out.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_out / "publications.jsonl"
    evidence_path = run_out / "evidence.json"

    cp = load_checkpoint()
    cp.setdefault("meta", {})["run_id"] = run_id
    # Keep history of run ids
    run_ids = list(cp["meta"].get("run_ids") or [])
    if run_id not in run_ids:
        run_ids.append(run_id)
    cp["meta"]["run_ids"] = run_ids[-20:]

    # 1) Discover package
    if not package_id:
        package_id = discover_latest_package()
    if not package_id:
        errors.append("no_domsc_package")
        result = _finalize(
            run_id=run_id,
            mode=mode,
            package_id=None,
            started_at=started_at,
            errors=errors,
            counts={},
            jsonl_path=jsonl_path,
            evidence_path=evidence_path,
            checkpoint_file=checkpoint_path(),
            resources=[],
            status="failed",
            observed_municipios=observed_municipios,
            resource_stats=[],
        )
        return result

    if package_id not in (cp.get("packages_seen") or []):
        cp.setdefault("packages_seen", []).append(package_id)

    # 2) package_show + resource list
    pkg = get_package(package_id)
    time.sleep(request_delay)
    if not pkg:
        errors.append(f"package_show_failed:{package_id}")
        result = _finalize(
            run_id=run_id,
            mode=mode,
            package_id=package_id,
            started_at=started_at,
            errors=errors,
            counts={},
            jsonl_path=jsonl_path,
            evidence_path=evidence_path,
            checkpoint_file=checkpoint_path(),
            resources=[],
            status="failed",
            observed_municipios=observed_municipios,
            resource_stats=[],
        )
        return result

    resources = list_ingestible_resources(pkg)
    zip_resources = [r for r in resources if r.get("kind") == "zip"]
    other_resources = [r for r in resources if r.get("kind") != "zip"]

    # 3) Select resources by mode
    if max_zips is None:
        if mode == "smoke":
            max_zips = SMOKE_MAX_ZIPS
        else:
            max_zips = DEFAULT_MAX_ZIPS_FULL

    # Prefer most recent ZIP slices (last N of sorted list)
    selected: list[dict[str, Any]]
    if max_zips and max_zips > 0:
        selected = zip_resources[-max_zips:]
    else:
        selected = list(zip_resources)

    if mode == "full" and not max_zips:
        selected = list(zip_resources) + other_resources
    elif mode == "smoke":
        # smoke: only ZIPs (1-2)
        pass
    elif mode == "incremental":
        # skip already completed resources
        selected = [r for r in selected if not resource_done(cp, str(r.get("id")))]
        if not selected and zip_resources:
            # All selected were done — try next unfinished from full zip list
            pending = [r for r in zip_resources if not resource_done(cp, str(r.get("id")))]
            if max_zips and max_zips > 0:
                selected = pending[:max_zips]
            else:
                selected = pending

    counts_before = {
        "resources_available": len(resources),
        "zips_available": len(zip_resources),
        "selected": len(selected),
        "completed_resources_prior": sum(
            1
            for v in (cp.get("completed_resources") or {}).values()
            if isinstance(v, dict) and v.get("status") == "completed"
        ),
    }

    total_records = 0
    total_skipped_files = 0
    total_files = 0
    resources_ok = 0
    resources_failed = 0
    resources_skipped = 0
    resource_stats: list[dict[str, Any]] = []

    skip_completed_files = mode == "incremental"

    with jsonl_path.open("w", encoding="utf-8") as jsonl_fh:
        for res in selected:
            rid = str(res.get("id") or "")
            if mode == "incremental" and resource_done(cp, rid):
                resources_skipped += 1
                resource_stats.append(
                    {"resource_id": rid, "status": "skipped_checkpoint", "records": 0}
                )
                continue

            url = res.get("url")
            if not url:
                errors.append(f"missing_url:{rid}")
                resources_failed += 1
                continue

            _logger.info("Downloading resource %s (%s)", rid, res.get("name"))
            body, err = download_bytes(str(url))
            time.sleep(request_delay)
            if err or body is None:
                errors.append(f"download_failed:{rid}:{err}")
                mark_resource_done(cp, resource_id=rid, records=0, error=err or "download_failed")
                save_checkpoint(cp)
                resources_failed += 1
                resource_stats.append(
                    {"resource_id": rid, "status": "download_failed", "error": err, "records": 0}
                )
                continue

            kind = res.get("kind") or resource_kind(res)
            try:
                if kind == "zip":
                    st = process_zip_resource(
                        body,
                        package_id=package_id,
                        resource=res,
                        cp=cp,
                        jsonl_fh=jsonl_fh,
                        skip_completed_files=skip_completed_files,
                    )
                elif kind == "json":
                    st = process_json_resource(
                        body,
                        package_id=package_id,
                        resource=res,
                        cp=cp,
                        jsonl_fh=jsonl_fh,
                        skip_completed_files=skip_completed_files,
                    )
                else:
                    # CSV not fully parsed in v1 — store raw only
                    dest = _raw_resource_dir(package_id, rid)
                    dest.mkdir(parents=True, exist_ok=True)
                    fname = Path(str(url)).name or "resource.csv"
                    (dest / fname).write_bytes(body)
                    st = {
                        "resource_id": rid,
                        "records": 0,
                        "files": 1,
                        "skipped_files": 0,
                        "errors": ["csv_not_parsed"],
                        "sha256": sha256_bytes(body),
                    }
                    mark_resource_done(
                        cp, resource_id=rid, records=0, sha256=st["sha256"], error="csv_not_parsed"
                    )
            except Exception as e:  # noqa: BLE001 — soft-fail per resource
                _logger.exception("Resource processing failed %s", rid)
                errors.append(f"process_failed:{rid}:{e}")
                mark_resource_done(cp, resource_id=rid, records=0, error=str(e))
                save_checkpoint(cp)
                resources_failed += 1
                resource_stats.append(
                    {"resource_id": rid, "status": "process_failed", "error": str(e), "records": 0}
                )
                continue

            total_records += int(st.get("records") or 0)
            total_files += int(st.get("files") or 0)
            total_skipped_files += int(st.get("skipped_files") or 0)
            if st.get("errors"):
                errors.extend(str(x) for x in st["errors"])
            resources_ok += 1
            resource_stats.append(
                {
                    "resource_id": rid,
                    "status": "ok" if not st.get("errors") else "ok_with_errors",
                    "records": st.get("records"),
                    "files": st.get("files"),
                    "sha256": st.get("sha256"),
                    "raw_path": st.get("raw_path"),
                }
            )
            save_checkpoint(cp)

    # Collect municipios from written JSONL (stream re-read)
    if jsonl_path.is_file():
        with jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                muni = rec.get("municipio")
                if muni:
                    observed_municipios.add(str(muni).strip())

    counts = {
        **counts_before,
        "resources_processed_ok": resources_ok,
        "resources_failed": resources_failed,
        "resources_skipped_checkpoint": resources_skipped,
        "files_processed": total_files,
        "files_skipped_checkpoint": total_skipped_files,
        "records_normalized": total_records,
        "municipalities_observed": len(observed_municipios),
    }

    status = "success"
    if resources_ok == 0 and total_records == 0:
        status = "failed" if errors else "empty"
    elif errors and total_records > 0:
        status = "partial"

    save_checkpoint(cp)

    result = _finalize(
        run_id=run_id,
        mode=mode,
        package_id=package_id,
        started_at=started_at,
        errors=errors,
        counts=counts,
        jsonl_path=jsonl_path,
        evidence_path=evidence_path,
        checkpoint_file=checkpoint_path(),
        resources=resources,
        status=status,
        observed_municipios=observed_municipios,
        resource_stats=resource_stats,
        selected_ids=[str(r.get("id")) for r in selected],
    )
    return result


def _finalize(
    *,
    run_id: str,
    mode: str,
    package_id: str | None,
    started_at: str,
    errors: list[str],
    counts: dict[str, Any],
    jsonl_path: Path,
    evidence_path: Path,
    checkpoint_file: Path,
    resources: list[dict[str, Any]],
    status: str,
    observed_municipios: set[str],
    resource_stats: list[dict[str, Any]],
    selected_ids: list[str] | None = None,
) -> dict[str, Any]:
    completed_at = datetime.now(UTC).isoformat()
    universe = load_sc_municipalities()
    muni_stats = municipality_stats(observed_municipios, universe)

    freshness_path = write_freshness_manifest(
        package_id=package_id or "",
        resources=resources,
        counts={**counts, "municipalities": muni_stats},
        run_id=run_id,
        status=status,
    )

    summary_path = jsonl_path.parent / "summary.json"
    # Mode smoke/incremental/full against CIGA public API is live collection.
    live_fetch = True
    attestation = False
    summary = {
        "run_id": run_id,
        "source": SOURCE_NAME,
        "mode": mode,
        "package_id": package_id,
        "status": status,
        "live_fetch": live_fetch,
        "attestation": attestation,
        "counts": counts,
        "municipalities": muni_stats,
        "selected_resource_ids": selected_ids or [],
        "resource_stats": resource_stats,
        "errors": errors[:50],
        "jsonl_path": str(jsonl_path),
        "freshness_manifest": str(freshness_path),
        "started_at": started_at,
        "completed_at": completed_at,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    evidence = build_run_evidence(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        command="python3 -m scripts.crawl.ciga_dom_publications",
        args={"mode": mode, "package_id": package_id, "max_selected": selected_ids},
        checkpoint_path=str(checkpoint_file) if checkpoint_file.exists() else None,
        output_path=str(jsonl_path) if jsonl_path.exists() else None,
        counts_before={
            k: counts.get(k)
            for k in (
                "resources_available",
                "zips_available",
                "selected",
                "completed_resources_prior",
            )
            if k in counts
        },
        counts_after={
            "records_normalized": counts.get("records_normalized", 0),
            "resources_processed_ok": counts.get("resources_processed_ok", 0),
            "municipalities_observed": counts.get("municipalities_observed", 0),
            "files_processed": counts.get("files_processed", 0),
        },
        status=status,
        errors=errors[:50],
        criteria={
            "live_ciga_api": True,
            "publication_level": True,
            "zip_slip_safe": True,
            "classify_act": True,
            "checkpoint_per_resource_and_file": True,
        },
        claims_allowed=[
            "Ingested real CIGA DOM-SC publications from public CKAN ZIPs",
            "Normalized municipio/orgao/edicao/data/titulo/texto/url",
            "Classified acts via classify_act",
            "Persisted immutable raw + normalized JSONL",
        ],
        claims_forbidden=[
            "Do not claim full monthly coverage unless mode=full without max_zips",
            "Do not invent CNPJ or financial values",
        ],
        source=SOURCE_NAME,
        package_id=package_id,
        municipalities=muni_stats,
        freshness_manifest=str(freshness_path),
        summary_path=str(summary_path),
        resource_stats=resource_stats,
        output_hash=sha256_file(jsonl_path) if jsonl_path.exists() else None,
        checkpoint_hash=sha256_file(checkpoint_file) if checkpoint_file.exists() else None,
        live_fetch=live_fetch,
        attestation=attestation,
    )
    # build_run_evidence may ignore unknown kwargs — force required flags
    evidence["live_fetch"] = live_fetch
    evidence["attestation"] = attestation
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    # Convenience latest pointers
    latest_evidence = OUTPUT_DIR / "latest_evidence.json"
    latest_evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_summary = OUTPUT_DIR / "latest_summary.json"
    latest_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "run_id": run_id,
        "status": status,
        "package_id": package_id,
        "mode": mode,
        "counts": counts,
        "municipalities": muni_stats,
        "errors": errors,
        "jsonl_path": str(jsonl_path),
        "evidence_path": str(evidence_path),
        "freshness_manifest": str(freshness_path),
        "summary_path": str(summary_path),
        "checkpoint_path": str(checkpoint_file),
        "evidence": evidence,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(
        description="CIGA DOM-SC municipal publications ingestion (public CKAN)"
    )
    p.add_argument(
        "--mode",
        default="smoke",
        choices=["smoke", "incremental", "full"],
        help="smoke=1-2 latest ZIPs; incremental=skip checkpoints; full=all ZIPs",
    )
    p.add_argument(
        "--package-id",
        default=None,
        help="Override auto-discovered monthly package id",
    )
    p.add_argument(
        "--max-zips",
        type=int,
        default=None,
        help="Limit number of ZIP resources (smoke default 2; full default unlimited)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY,
        help=f"Delay between HTTP requests (default {REQUEST_DELAY}s)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print full result JSON to stdout",
    )
    args = p.parse_args(argv)

    result = run_ingestion(
        mode=args.mode,
        package_id=args.package_id,
        max_zips=args.max_zips,
        request_delay=args.delay,
    )

    print(f"SOURCE={SOURCE_NAME} mode={result.get('mode')} status={result.get('status')}")
    print(f"run_id={result.get('run_id')}")
    print(f"package_id={result.get('package_id')}")
    counts = result.get("counts") or {}
    print(
        "counts: "
        f"records={counts.get('records_normalized', 0)} "
        f"resources_ok={counts.get('resources_processed_ok', 0)} "
        f"resources_failed={counts.get('resources_failed', 0)} "
        f"skipped={counts.get('resources_skipped_checkpoint', 0)} "
        f"municipios={counts.get('municipalities_observed', 0)}"
    )
    muni = result.get("municipalities") or {}
    print(
        f"municipalities: observed={muni.get('observed_count')} "
        f"universe={muni.get('universe_count')} gaps={muni.get('gap_count')} "
        f"source={muni.get('universe_source')}"
    )
    print(f"jsonl={result.get('jsonl_path')}")
    print(f"evidence={result.get('evidence_path')}")
    print(f"freshness={result.get('freshness_manifest')}")
    print(f"checkpoint={result.get('checkpoint_path')}")
    if result.get("errors"):
        print(f"errors({len(result['errors'])}): {result['errors'][:5]}")

    if args.json:
        # evidence is large; print summary-oriented view
        printable = {k: v for k, v in result.items() if k not in {"evidence", "summary"}}
        printable["evidence_run_id"] = (result.get("evidence") or {}).get("run_id")
        print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))

    status = result.get("status")
    if status in {"success", "partial", "empty"}:
        return 0 if status != "empty" or counts.get("resources_available", 0) else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
