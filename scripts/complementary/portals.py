"""Municipal public-tender portals: Betha Atende, IPM, Betha e-Gov."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from scripts.complementary.contract import RunResult, classify_http_block, sha256_json

BETHA_ATENDE = "betha_atende"
IPM = "ipm"
BETHA_EGOV = "betha_egov"

_IPM_HOST = re.compile(r"(^|\.)ipm\.[a-z.]+$", re.I)
_IPAM_FALSE = re.compile(r"ipam", re.I)


def detect_platform(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("atende.net"):
        return BETHA_ATENDE
    if host.endswith("e-gov.betha.com.br"):
        return BETHA_EGOV
    if host.endswith("betha.com.br") and "e-gov" not in host:
        return None
    if _IPAM_FALSE.search(host):
        return None
    if (
        _IPM_HOST.search(host)
        or host.endswith("ipmbrasil.com.br")
        or "portaldecompras.ipm" in host
        or host.startswith("portaldecompras.ipm")
    ):
        return IPM
    return None


def bind_entity(url: str, *, cnpj: str, ibge: str, municipio: str) -> dict[str, Any]:
    platform = detect_platform(url)
    return {
        "url": url,
        "platform": platform,
        "cnpj": "".join(c for c in cnpj if c.isdigit()),
        "ibge": ibge,
        "municipio": municipio,
        "bound": platform is not None and bool(cnpj) and bool(ibge),
    }


def parse_list_payload(payload: dict[str, Any] | list[Any], *, platform: str) -> list[dict[str, Any]]:
    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        items = payload.get("licitacoes") if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("id") or raw.get("numero") or raw.get("codigo") or raw.get("source_id") or "")
        if not source_id:
            continue
        if raw.get("source") == platform and raw.get("source_id") == source_id:
            out.append(raw)
            continue
        out.append(
            {
                "source": platform,
                "source_id": source_id,
                "objeto": raw.get("objeto") or raw.get("descricao"),
                "status": raw.get("situacao") or raw.get("status"),
                "modalidade": raw.get("modalidade"),
                "documentos": raw.get("documentos") or raw.get("anexos") or [],
                "orgao": raw.get("orgao") or raw.get("entidade"),
                "content_hash": sha256_json(raw),
            }
        )
    return out


def run_portal(
    *,
    platform: str,
    pages: list[dict[str, Any]],
    binding: dict[str, Any] | None = None,
) -> RunResult:
    if binding and not binding.get("bound"):
        return RunResult(platform, "BLOCKED", 0, 0, 0, 0, reason="unbound_entity")
    fetched = 0
    records: list[dict[str, Any]] = []
    last_complete = True
    for page in pages:
        block = classify_http_block(
            status=page.get("status"),
            body=str(page.get("body") or ""),
            headers=page.get("headers") or {},
        )
        if block:
            return RunResult(platform, block, fetched, 0, 0, 0, reason=block.lower())
        last_complete = bool(page.get("complete", True))
        recs = parse_list_payload(page.get("payload") or page, platform=platform)
        fetched += len(recs)
        records.extend(recs)
    if not last_complete:
        terminal = "partial"
    elif fetched == 0:
        terminal = "ZERO_CONFIRMED"
    else:
        terminal = "success"
    return RunResult(
        platform,
        terminal,  # type: ignore[arg-type]
        fetched=fetched,
        persisted=fetched,
        deduplicated=0,
        failed=0,
        records=records,
        job={"raw_hash": sha256_json(pages)},
    )
