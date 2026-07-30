"""Discover the current RFB public CNPJ open-data release listing."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from scripts.company_registry.models import empty_release_manifest

UA = "extra-cli-company-registry/1.0 (+release-discovery)"

# Canonical candidates — discovery must not assume permanent filenames.
DEFAULT_INDEX_URLS: tuple[str, ...] = (
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/",
    "https://dadosabertos.rfb.gov.br/CNPJ/",
    "http://200.152.38.155/CNPJ/",
)

# Domain / layout tables often published alongside monthly bulk zips
DOMAIN_FILE_PREFIXES = (
    "Cnaes",
    "Motivos",
    "Municipios",
    "Naturezas",
    "Paises",
    "Qualificacoes",
)
BULK_FILE_PREFIXES = (
    "Empresas",
    "Estabelecimentos",
    "Socios",
    "Simples",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_html(url: str, *, timeout: float = 25.0) -> tuple[bool, str, list[str]]:
    try:
        req = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read(2_000_000).decode("utf-8", errors="replace")
            return True, body, []
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return False, "", [f"{url}: {type(exc).__name__}: {exc}"]


def _hrefs(html: str) -> list[str]:
    return re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)


def _month_like(name: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}/?$", name.strip()))


def classify_file_name(name: str) -> str | None:
    base = name.split("/")[-1]
    stem = base.replace(".zip", "").replace(".ZIP", "")
    for p in BULK_FILE_PREFIXES:
        if stem.startswith(p) or stem.lower().startswith(p.lower()):
            return p.lower()
    for p in DOMAIN_FILE_PREFIXES:
        if stem.startswith(p) or stem.lower().startswith(p.lower()):
            return "domain"
    if stem.lower().endswith(".zip") or base.lower().endswith(".zip"):
        return "unknown_zip"
    return None


def discover_release(
    *,
    index_urls: list[str] | None = None,
    preferred_month: str | None = None,
    timeout: float = 25.0,
) -> dict[str, Any]:
    """Discover latest RFB open-data release folder and file listing.

    Returns a release manifest skeleton with status DISCOVERED or FAILED.
    """
    errors: list[str] = []
    urls = list(index_urls or DEFAULT_INDEX_URLS)
    chosen_index: str | None = None
    months: list[str] = []
    files: list[dict[str, Any]] = []
    published_ref: str | None = None

    for index in urls:
        ok, html, err = _fetch_html(index, timeout=timeout)
        errors.extend(err)
        if not ok:
            continue
        hrefs = _hrefs(html)
        month_hrefs = [h for h in hrefs if _month_like(h.rstrip("/").split("/")[-1] + "/") or _month_like(h)]
        # Also accept direct zip listing on flat index
        zip_hrefs = [h for h in hrefs if h.lower().endswith(".zip")]
        if month_hrefs:
            months = sorted(
                {
                    (h.rstrip("/").split("/")[-1] if not h.endswith("/") else h.rstrip("/").split("/")[-1])
                    for h in month_hrefs
                }
            )
            # Prefer explicit month or latest
            month = preferred_month or (months[-1] if months else None)
            if not month:
                continue
            published_ref = month
            month_url = urljoin(index if index.endswith("/") else index + "/", month + "/")
            ok2, html2, err2 = _fetch_html(month_url, timeout=timeout)
            errors.extend(err2)
            if not ok2:
                continue
            chosen_index = month_url
            for h in _hrefs(html2):
                if not h.lower().endswith(".zip"):
                    continue
                name = h.split("/")[-1]
                kind = classify_file_name(name)
                files.append(
                    {
                        "file_name": name,
                        "url": urljoin(month_url, h),
                        "kind": kind,
                    }
                )
            break
        if zip_hrefs:
            chosen_index = index
            published_ref = preferred_month or utc_now()[:7]
            for h in zip_hrefs:
                name = h.split("/")[-1]
                files.append(
                    {
                        "file_name": name,
                        "url": urljoin(index if index.endswith("/") else index + "/", h),
                        "kind": classify_file_name(name),
                    }
                )
            break

    release_id = f"rfb-cnpj-{published_ref or 'unknown'}"
    manifest = empty_release_manifest(release_id, source_authority="RECEITA_FEDERAL")
    manifest["discovered_at"] = utc_now()
    manifest["published_reference_date"] = published_ref
    manifest["source_urls"] = [chosen_index] if chosen_index else list(urls)
    manifest["files_expected"] = [f["file_name"] for f in files]
    manifest["file_names"] = [f["file_name"] for f in files]
    manifest["discovery"] = {
        "index_urls_tried": urls,
        "months_seen": months,
        "chosen_index": chosen_index,
        "files": files,
        "errors": errors,
    }

    if not files:
        manifest["status"] = "FAILED"
        manifest["errors"] = errors or ["no_files_discovered"]
        manifest["warnings"].append(
            "RFB open-data listing unreachable or empty from this environment. "
            "Stage local ZIPs under data/company_registry/raw/<release_id>/ or use selective mode."
        )
        return manifest

    # Require at least empresas + estabelecimentos for commercial function
    kinds = {f.get("kind") for f in files}
    if "empresas" not in kinds or "estabelecimentos" not in kinds:
        manifest["warnings"].append(
            "listing_missing_empresas_or_estabelecimentos_prefixes — verify layout"
        )
    manifest["status"] = "DISCOVERED"
    return manifest


def discover_or_stage_hint() -> dict[str, Any]:
    """Convenience wrapper used by CLI health/docs."""
    return discover_release()
