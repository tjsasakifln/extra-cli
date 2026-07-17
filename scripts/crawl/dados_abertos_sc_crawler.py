#!/usr/bin/env python3
"""Dados Abertos SC (CKAN) crawler — public DOE catalog on dados.sc.gov.br.

Source: https://dados.sc.gov.br/ — CKAN Action API (no token for read).

Primary package for DOE bulk publications:
    ``diario-oficial-sc-publicacoes`` (CSV/XLSX 2012–2025 on
    portal.doe.sea.sc.gov.br/repositorio/dadosabertos/).

This path does **not** replace the authenticated DOE-SC REST API
(``doe_sc_crawler.py``); it complements it with open bulk files.

Interface expected by monitor.py:
    crawl(mode) -> list[dict]
    transform(records) -> list[dict]

Modes:
    smoke         — package_search + package_show; list resources only
    full          — same as smoke + optional metadata for all DOE packages
    incremental   — package_show only for the primary package (resource list)

Usage:
    python -m scripts.crawl.dados_abertos_sc_crawler --mode smoke
    python -m scripts.crawl.dados_abertos_sc_crawler --mode smoke --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.security import USER_AGENT  # noqa: E402

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_NAME = "dados_abertos_sc"

CKAN_BASE = "https://dados.sc.gov.br"
CKAN_API = f"{CKAN_BASE}/api/3/action"

# Primary DOE open-data package (confirmed live 2026-07)
PRIMARY_PACKAGE = "diario-oficial-sc-publicacoes"
RELATED_PACKAGES = (
    "diario-oficial-sc-publicacoes",
    "diario-oficial-sc-edicoes",
)

REQUEST_DELAY = 0.5  # seconds between CKAN requests
HTTP_TIMEOUT = 45

CHECKPOINT_DIR = _PROJECT_ROOT / "data" / "dados_sc_checkpoints"

ESFERA_ID_ESTADUAL = 2


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
# Checkpoint
# ---------------------------------------------------------------------------


def _checkpoint_path(name: str = "last_smoke.json") -> Path:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR / name


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


# ---------------------------------------------------------------------------
# Crawl / transform
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
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def crawl(mode: str = "smoke", *, dry_run: bool = True) -> list[dict]:
    """Crawl dados.sc.gov.br CKAN catalog.

    Args:
        mode: ``smoke`` | ``full`` | ``incremental``
        dry_run: if True (default), only list resources — never download file bodies.
                 Set False only when explicitly downloading one small resource later.

    Returns:
        List of raw resource-metadata dicts (and optional search hits).
    """
    mode = (mode or "smoke").strip().lower()
    if mode not in {"smoke", "full", "incremental"}:
        _logger.warning("Unknown mode %r — falling back to smoke", mode)
        mode = "smoke"

    records: list[dict] = []
    packages_seen: list[str] = []

    _logger.info("[%s] crawl mode=%s dry_run=%s", SOURCE_NAME, mode, dry_run)

    # 1) Health + search (smoke / full)
    if mode in {"smoke", "full"}:
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

    # 2) package_show for primary (+ related on full)
    pkg_ids = list(RELATED_PACKAGES) if mode == "full" else [PRIMARY_PACKAGE]
    if mode == "smoke" and PRIMARY_PACKAGE not in pkg_ids:
        pkg_ids = [PRIMARY_PACKAGE]

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
                }
            )

        # Optional: on non-dry-run, "download" is still list-only for bodies —
        # we only HEAD/annotate the smallest CSV candidate if dry_run is False.
        if not dry_run and resources:
            csvs = [r for r in resources if (r.get("format") or "").upper() == "CSV"]
            candidate = sorted(csvs, key=lambda r: (r.get("size") is None, r.get("size") or 0))
            if candidate:
                one = candidate[0]
                records.append(
                    {
                        "record_type": "download_candidate",
                        "source": SOURCE_NAME,
                        "mode": mode,
                        "resource_id": one.get("id"),
                        "name": one.get("name"),
                        "url": one.get("url"),
                        "format": one.get("format"),
                        "note": "dry_run=False: candidate selected; body not streamed in smoke crawler",
                        "fetched_at": datetime.now(UTC).isoformat(),
                    }
                )

    cp = {
        "source": SOURCE_NAME,
        "mode": mode,
        "dry_run": dry_run,
        "packages": packages_seen,
        "resource_count": len(resource_summary),
        "resources": resource_summary,
        "saved_at": datetime.now(UTC).isoformat(),
    }
    path = save_checkpoint(cp)
    _logger.info(
        "[%s] crawl done: %d records, %d resources, checkpoint=%s",
        SOURCE_NAME,
        len(records),
        len(resource_summary),
        path,
    )
    return records


def _content_hash(raw: dict) -> str:
    key = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()


def transform_record(raw: dict) -> dict | None:
    """Normalize one raw catalog record.

    Resource rows become bid-shaped stubs for monitor compatibility where useful;
    search/status rows pass through as metadata (filtered out of bid upserts by
    consumers that require ``resource_id`` / object text).
    """
    if not isinstance(raw, dict):
        return None

    rtype = raw.get("record_type")
    if rtype in {"ckan_status", "package_search", "download_candidate"}:
        # Keep as opaque metadata — not a bid
        return {
            "pncp_id": None,
            "metadata_only": True,
            "record_type": rtype,
            "source": SOURCE_NAME,
            "objeto_compra": f"[dados_sc] {rtype}",
            "payload": raw,
            "content_hash": _content_hash(raw),
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
    p = argparse.ArgumentParser(description="Dados Abertos SC CKAN crawler (public)")
    p.add_argument(
        "--mode",
        default="smoke",
        choices=["smoke", "full", "incremental"],
        help="Crawl mode (default: smoke)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="List resources only, do not download bodies (default)",
    )
    p.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Allow download-candidate selection (still no full bulk stream)",
    )
    p.add_argument("--json", action="store_true", help="Print records as JSON")
    args = p.parse_args(argv)

    dry_run = not args.no_dry_run
    records = crawl(mode=args.mode, dry_run=dry_run)
    transformed = transform(records)

    print(f"SOURCE={SOURCE_NAME} mode={args.mode} dry_run={dry_run}")
    print(f"raw_records={len(records)} transformed={len(transformed)}")
    resources = [r for r in records if r.get("record_type") == "ckan_resource"]
    print(f"resources_listed={len(resources)}")
    for r in resources[:15]:
        print(
            f"  - {r.get('name')} | {r.get('format')} | "
            f"id={r.get('resource_id')} | {r.get('url')}"
        )
    if len(resources) > 15:
        print(f"  ... +{len(resources) - 15} more")

    if args.json:
        print(json.dumps({"records": records, "transformed": transformed}, ensure_ascii=False, indent=2))

    return 0 if resources else 1


if __name__ == "__main__":
    raise SystemExit(main())
