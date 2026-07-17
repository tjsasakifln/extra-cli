"""Semi-automatic source discovery for uncovered entities.

Combines domain heuristics (municipal URL patterns, CIGA, PNCP, transparency)
and optional HTTP HEAD probes. Does NOT invent live URLs without evidence —
candidates are marked with confidence and saved for human review.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.source_registry.models import DiscoveryResult, EntitySourceRecord

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "data" / "source_discovery_candidates.jsonl"

HEAD_TIMEOUT_S = 5


def _slug_municipio(municipio: str) -> str:
    decomposed = unicodedata.normalize("NFKD", municipio or "")
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-z0-9]+", "", ascii_text.lower())
    return cleaned


def _candidate(
    kind: str,
    url: str,
    confidence: float,
    *,
    evidence: str,
    platform: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "url": url,
        "confidence": round(confidence, 3),
        "evidence": evidence,
        "platform": platform,
        "status": "candidate",  # not verified live
    }


def build_candidates(record: EntitySourceRecord) -> list[dict[str, Any]]:
    """Heuristic candidates for one entity (no network)."""
    candidates: list[dict[str, Any]] = []
    sphere = (record.external_ids or {}).get("sphere") or "unknown"
    mun_slug = _slug_municipio(record.municipio)

    # Existing known portals → high confidence
    if record.portal_transparencia:
        candidates.append(
            _candidate(
                "portal_transparencia",
                record.portal_transparencia,
                0.9,
                evidence="registry_portal_transparencia",
                platform="transparencia",
            )
        )
    if record.portal_institucional:
        candidates.append(
            _candidate(
                "portal_institucional",
                record.portal_institucional,
                0.85,
                evidence="registry_portal_institucional",
            )
        )
    if record.diario_oficial:
        candidates.append(
            _candidate(
                "diario_oficial",
                record.diario_oficial,
                0.8,
                evidence="registry_diario_oficial",
                platform="ciga_ckan",
            )
        )

    # Municipal domain patterns — candidates only
    if sphere == "municipal" and mun_slug:
        candidates.append(
            _candidate(
                "prefeitura_domain",
                f"https://{mun_slug}.sc.gov.br",
                0.35,
                evidence="heuristic_municipal_domain",
            )
        )
        candidates.append(
            _candidate(
                "prefeitura_domain_alt",
                f"https://prefeitura.{mun_slug}.sc.gov.br",
                0.3,
                evidence="heuristic_prefeitura_subdomain",
            )
        )
        candidates.append(
            _candidate(
                "transparencia_atende",
                f"https://{mun_slug}.atende.net/transparencia",
                0.4,
                evidence="heuristic_betha_atende_pattern",
                platform="betha",
            )
        )
        # Shared CIGA DOM — real shared portal for all municipal entities
        candidates.append(
            _candidate(
                "ciga_ckan_shared",
                "https://dados.ciga.sc.gov.br",
                0.7,
                evidence="ciga_dom_covers_all_municipal_entities_in_sc",
                platform="ciga_ckan",
            )
        )
    elif record.natureza_juridica in {
        "prefeitura",
        "camara_municipal",
        "secretaria_municipal",
        "autarquia_municipal",
        "fundacao_municipal",
    }:
        candidates.append(
            _candidate(
                "ciga_ckan_shared",
                "https://dados.ciga.sc.gov.br",
                0.7,
                evidence="ciga_dom_covers_all_municipal_entities_in_sc",
                platform="ciga_ckan",
            )
        )
        if mun_slug:
            candidates.append(
                _candidate(
                    "prefeitura_domain",
                    f"https://{mun_slug}.sc.gov.br",
                    0.35,
                    evidence="heuristic_municipal_domain",
                )
            )

    # PNCP by CNPJ pattern
    if record.cnpj:
        candidates.append(
            _candidate(
                "pncp_orgao",
                f"https://pncp.gov.br/api/pncp/v1/orgaos/{{cnpj14_from_{record.cnpj}}}",
                0.45,
                evidence="pncp_orgao_endpoint_requires_full_cnpj",
                platform="pncp",
            )
        )

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in candidates:
        if c["url"] in seen:
            continue
        seen.add(c["url"])
        unique.append(c)
    return unique


def probe_url(url: str, *, timeout: float = HEAD_TIMEOUT_S) -> dict[str, Any]:
    """HTTP HEAD (fallback GET) probe. Never raises — returns structured result."""
    if "{" in url or "}" in url:
        return {
            "url": url,
            "probed": False,
            "reason": "template_url_not_probeable",
        }
    result: dict[str, Any] = {
        "url": url,
        "probed": True,
        "method": "HEAD",
        "status_code": None,
        "ok": False,
        "error": None,
        "probed_at": datetime.now(UTC).isoformat(),
    }
    try:
        req = Request(  # noqa: S310 — public portal HEAD probe
            url,
            method="HEAD",
            headers={"User-Agent": "extra-consultoria-source-discovery/1.0"},
        )
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — intentional probe of public portals
            result["status_code"] = getattr(resp, "status", None) or resp.getcode()
            result["ok"] = 200 <= int(result["status_code"]) < 400
            return result
    except HTTPError as exc:
        result["status_code"] = exc.code
        result["ok"] = 200 <= int(exc.code) < 400
        # Some portals reject HEAD — try GET lightly
        if exc.code in {405, 403, 501}:
            try:
                req = Request(  # noqa: S310 — public portal GET fallback
                    url,
                    method="GET",
                    headers={"User-Agent": "extra-consultoria-source-discovery/1.0"},
                )
                with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                    result["method"] = "GET"
                    result["status_code"] = getattr(resp, "status", None) or resp.getcode()
                    result["ok"] = 200 <= int(result["status_code"]) < 400
            except Exception as get_exc:  # noqa: BLE001
                result["error"] = f"HEAD={exc.code}; GET={get_exc!s}"
        else:
            result["error"] = str(exc.reason or exc)
        return result
    except (URLError, TimeoutError, OSError) as exc:
        result["error"] = str(exc)
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"unexpected:{exc!s}"
        return result


def discover_sources_for_entity(
    record: EntitySourceRecord,
    *,
    dry_run: bool = True,
    probe: bool = False,
) -> DiscoveryResult:
    """Discover candidate sources for one entity.

    Args:
        record: Entity source record.
        dry_run: When True (default), skip HTTP probes even if probe=True.
        probe: When True and dry_run=False, HEAD-probe candidate URLs.
    """
    candidates = build_candidates(record)
    probed: list[dict[str, Any]] = []
    notes: list[str] = []

    should_probe = probe and not dry_run
    if dry_run:
        notes.append("dry_run=true — HTTP probes skipped")
    if should_probe:
        for c in candidates:
            if c.get("confidence", 0) < 0.3:
                continue
            if "{" in c["url"]:
                continue
            p = probe_url(c["url"])
            probed.append(p)
            if p.get("ok"):
                c["status"] = "probe_ok"
                c["confidence"] = min(1.0, float(c["confidence"]) + 0.25)
                c["probe"] = p
            elif p.get("probed"):
                c["status"] = "probe_failed"
                c["probe"] = p

    best = None
    if candidates:
        best = max(candidates, key=lambda c: float(c.get("confidence") or 0))

    confidence = float(best["confidence"]) if best else 0.0
    return DiscoveryResult(
        canonical_id=record.canonical_id,
        candidates=candidates,
        probed=probed,
        best_candidate=best,
        confidence=confidence,
        notes=notes,
    )


def append_discovery_candidates(
    results: list[DiscoveryResult],
    path: str | Path | None = None,
) -> Path:
    """Append discovery results to the review JSONL."""
    out = Path(path) if path else DEFAULT_CANDIDATES_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).isoformat()
    with out.open("a", encoding="utf-8") as fh:
        for r in results:
            payload = r.to_dict()
            payload["recorded_at"] = ts
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return out


def discover_batch(
    records: list[EntitySourceRecord],
    *,
    limit: int = 50,
    dry_run: bool = True,
    only_gaps: bool = True,
    save: bool = True,
) -> list[DiscoveryResult]:
    """Run discovery for up to ``limit`` entities (priority order)."""
    pool = records
    if only_gaps:
        from scripts.source_registry.models import OPERATIONAL_STATUSES

        pool = [r for r in records if r.access_status not in OPERATIONAL_STATUSES]
    pool = sorted(pool, key=lambda r: (r.priority, r.razao_social or ""))
    selected = pool[: max(0, limit)]

    results = [discover_sources_for_entity(r, dry_run=dry_run, probe=not dry_run) for r in selected]
    if save and results:
        append_discovery_candidates(results)
    return results
