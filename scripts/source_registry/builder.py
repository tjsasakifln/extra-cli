"""Build the canonical entity source registry from the target universe CSV.

Usage::

    from scripts.source_registry.builder import build_registry_from_csv
    records = build_registry_from_csv()
"""

from __future__ import annotations

import csv
import json
import logging
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scripts.source_registry.models import EntitySourceRecord

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = PROJECT_ROOT / "config" / "target_entities_200km.csv"
DEFAULT_APPLICABILITY = PROJECT_ROOT / "config" / "source_applicability.yaml"
DEFAULT_TRANSPARENCIA = PROJECT_ROOT / "config" / "transparencia_config.yaml"
DEFAULT_PLATFORMS_JSON = PROJECT_ROOT / "data" / "transparencia_platforms.json"
DEFAULT_PLATFORM_DETECTION = PROJECT_ROOT / "data" / "platform_detection_results_final.json"
DEFAULT_RESIDUAL_PORTALS = PROJECT_ROOT / "data" / "residual_portals.csv"
DEFAULT_REGISTRY_JSONL = PROJECT_ROOT / "data" / "entity_source_registry.jsonl"
DEFAULT_REGISTRY_SUMMARY = PROJECT_ROOT / "data" / "entity_source_registry_summary.json"

# Expected universe size (authoritative seed).
EXPECTED_ENTITY_COUNT = 1093

# ---------------------------------------------------------------------------
# Entity type → sphere / nature classification
# ---------------------------------------------------------------------------

MUNICIPAL_TYPES = frozenset(
    {
        "prefeitura",
        "camara_municipal",
        "secretaria_municipal",
        "fundacao_municipal",
        "autarquia_municipal",
    }
)
ESTADUAL_TYPES = frozenset(
    {
        "orgao_estadual",
        "poder_judiciario_estadual",
        "fundo_estadual",
        "autarquia_estadual",
        "fundacao_estadual",
        "governo_estadual",
        "assembleia_legislativa",
    }
)
FEDERAL_TYPES = frozenset(
    {
        "orgao_federal",
        "autarquia_federal",
        "fundacao_federal",
        "poder_judiciario_federal",
        "camara_federal",
        "fundo_federal",
    }
)

# Priority: 1 highest commercial value
PRIORITY_BY_TYPE: dict[str, int] = {
    "prefeitura": 1,
    "camara_municipal": 1,
    "secretaria_municipal": 2,
    "autarquia_municipal": 2,
    "fundacao_municipal": 2,
    "consorcio_publico": 2,
    "orgao_estadual": 3,
    "autarquia_estadual": 3,
    "governo_estadual": 3,
    "assembleia_legislativa": 3,
    "fundo_estadual": 3,
    "fundacao_estadual": 3,
    "poder_judiciario_estadual": 4,
    "orgao_federal": 4,
    "autarquia_federal": 4,
    "fundacao_federal": 4,
    "empresa_publica": 4,
    "sociedade_economia_mista": 4,
    "servico_social_autonomo": 5,
    "orgao_autonomo": 5,
    "poder_judiciario_federal": 5,
    "camara_federal": 5,
    "fundo_federal": 5,
}


def _slug(text: str) -> str:
    """ASCII slug for stable identifiers."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").upper()
    return cleaned[:80] or "ENTITY"


def _digits(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", str(value))


def _safe_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sphere_for(entity_type: str) -> str:
    if entity_type in MUNICIPAL_TYPES:
        return "municipal"
    if entity_type in ESTADUAL_TYPES:
        return "estadual"
    if entity_type in FEDERAL_TYPES:
        return "federal"
    # Mixed / ambiguous types — treat as multi for applicability
    if entity_type in {"consorcio_publico", "empresa_publica", "sociedade_economia_mista"}:
        return "multi"
    return "unknown"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml  # lazy — optional at import time

        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001 — config is best-effort
        logger.warning("Failed to load YAML %s: %s", path, exc)
        return {}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load JSON %s: %s", path, exc)
        return None


def _index_transparencia_by_ibge(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map IBGE code → portal config entry from transparencia_config.yaml."""
    out: dict[str, dict[str, Any]] = {}
    municipios = cfg.get("municipios") or {}
    if not isinstance(municipios, dict):
        return out
    for slug, entry in municipios.items():
        if not isinstance(entry, dict):
            continue
        ibge = _digits(str(entry.get("ibge") or ""))
        if not ibge:
            continue
        out[ibge] = {**entry, "slug": slug}
    return out


def _index_platform_detection(data: Any) -> dict[str, dict[str, Any]]:
    """Map IBGE → platform detection result."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(data, dict):
        return out
    lists: list[Any] = []
    for key in ("detected_list_pass1", "detected_list_pass2", "detected_list"):
        val = data.get(key)
        if isinstance(val, list):
            lists.extend(val)
    # Also from transparencia_platforms.json shape
    detected = data.get("detected")
    if isinstance(detected, list):
        lists.extend(detected)
    for item in lists:
        if not isinstance(item, dict):
            continue
        ibge = _digits(str(item.get("ibge") or ""))
        if not ibge:
            continue
        # Prefer entries with a real URL
        prev = out.get(ibge)
        if prev is None or (item.get("url") and not prev.get("url")):
            out[ibge] = item
    return out


def _index_residual_portals(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            ibge = _digits(row.get("ibge"))
            if ibge:
                out[ibge] = row
    return out


def _seed_platforms(
    entity_type: str,
    sphere: str,
    has_portal_evidence: bool,
    applicability: dict[str, Any],
) -> tuple[list[str], str, int | None]:
    """Return (platforms, primary_integration_type, sla_hours)."""
    platforms: list[str] = []
    sources_cfg = (applicability.get("sources") or {}) if applicability else {}

    def _sla(name: str, default: int | None = None) -> int | None:
        src = sources_cfg.get(name) or {}
        val = src.get("sla_hours")
        return int(val) if val is not None else default

    # PNCP is a potential federal source for ALL entities
    platforms.append("pncp")
    integration = "api_json"
    sla = _sla("pncp", 4)

    if sphere == "municipal" or entity_type in MUNICIPAL_TYPES:
        platforms.extend(["ciga_ckan", "dom_sc"])
        if entity_type in {"prefeitura", "camara_municipal", "secretaria_municipal"}:
            platforms.append("transparencia")
        integration = "ckan" if not has_portal_evidence else "html"
        sla = min(x for x in [sla, _sla("ciga_ckan", 48), _sla("dom_sc", 24)] if x is not None)

    if sphere == "estadual" or entity_type in ESTADUAL_TYPES:
        platforms.extend(["sc_compras", "tce_sc", "doe_sc"])
        integration = "api_json"
        sla = min(x for x in [sla, _sla("sc_compras", 24), _sla("doe_sc", 24)] if x is not None)

    if sphere == "federal" or entity_type in FEDERAL_TYPES:
        platforms.extend(["compras_gov"])
        integration = "api_json"
        sla = min(x for x in [sla, _sla("compras_gov", 12)] if x is not None)

    if sphere == "multi" or entity_type in {
        "consorcio_publico",
        "empresa_publica",
        "sociedade_economia_mista",
    }:
        platforms.extend(["sc_compras", "pcp"])
        integration = "api_json"

    # Deduplicate preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for p in platforms:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered, integration, sla


def _decide_status_and_strategy(
    *,
    entity_type: str,
    sphere: str,
    platforms: list[str],
    portal_transparencia: str | None,
    portal_institucional: str | None,
    diario_oficial: str | None,
    has_detection: bool,
) -> tuple[str, str, str | None, str, float, list[dict[str, Any]]]:
    """Return (access_status, strategy, blocker, next_action, confidence, evidences)."""
    evidences: list[dict[str, Any]] = []
    confidence = 0.15  # base: seed row exists

    has_portal = bool(portal_transparencia or portal_institucional or diario_oficial)
    if has_portal:
        confidence += 0.35
        evidences.append(
            {
                "type": "portal_config",
                "portal_transparencia": portal_transparencia,
                "portal_institucional": portal_institucional,
                "diario_oficial": diario_oficial,
            }
        )
    if has_detection:
        confidence += 0.2
        evidences.append({"type": "platform_detection", "matched": True})

    # Heuristic platform seeds always add a little confidence
    if platforms:
        confidence += 0.1
        evidences.append(
            {
                "type": "heuristic_platforms",
                "platforms": list(platforms),
                "sphere": sphere,
            }
        )

    confidence = min(1.0, round(confidence, 3))

    if has_portal or has_detection:
        # Mapped: we have concrete portal/platform evidence
        status = "mapped"
        if sphere == "municipal":
            strategy = "ciga_ckan_municipio_expand"
            next_action = "verify_ciga_dom_and_transparencia_portals"
            blocker = "none" if has_portal else "fragmented"
        elif sphere == "estadual":
            strategy = "sc_compras_and_doe_sc"
            next_action = "probe_sc_compras_orgao"
            blocker = "none"
        elif sphere == "federal":
            strategy = "pncp_cnpj_lookup"
            next_action = "probe_pncp_orgao_by_cnpj"
            blocker = "none"
        else:
            strategy = "multi_source_probe"
            next_action = "pncp_cnpj_lookup"
            blocker = "fragmented"
        return status, strategy, blocker, next_action, confidence, evidences

    # No portal evidence — PNCP is still a potential source for everyone
    if "pncp" in platforms:
        status = "unknown"
        strategy = "pncp_cnpj_lookup"
        next_action = "probe_pncp_for_publication_history"
        # Municipal without portal still has CIGA path
        if sphere == "municipal":
            strategy = "ciga_ckan_municipio_expand"
            next_action = "expand_ciga_dom_by_municipio"
            blocker = "no_api"
        elif sphere == "estadual":
            strategy = "sc_compras_and_doe_sc"
            next_action = "collect_public_sc_compras_and_doe_ckan"
            blocker = "pending_collection"
        elif sphere == "federal":
            blocker = "none"
        else:
            blocker = "fragmented"
        return status, strategy, blocker, next_action, confidence, evidences

    # Truly nothing identified
    return (
        "source_not_identified",
        "manual_source_research",
        "not_applicable",
        "research_entity_publication_channels",
        confidence,
        evidences,
    )


def build_registry_from_csv(
    csv_path: str | Path | None = None,
    *,
    persist: bool = True,
    registry_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> list[EntitySourceRecord]:
    """Load the seed CSV and build one EntitySourceRecord per row.

    Args:
        csv_path: Path to ``target_entities_200km.csv`` (default project config).
        persist: When True, write JSONL + summary under ``data/``.
        registry_path: Override JSONL output path.
        summary_path: Override summary JSON path.

    Returns:
        List of EntitySourceRecord (length MUST equal seed row count).
    """
    path = Path(csv_path) if csv_path else DEFAULT_CSV
    if not path.exists():
        raise FileNotFoundError(f"Target entities CSV not found: {path}")

    applicability = _load_yaml(DEFAULT_APPLICABILITY)
    transparencia = _load_yaml(DEFAULT_TRANSPARENCIA)
    transp_by_ibge = _index_transparencia_by_ibge(transparencia)

    platform_det = _load_json(DEFAULT_PLATFORM_DETECTION) or {}
    platforms_json = _load_json(DEFAULT_PLATFORMS_JSON) or {}
    # Merge both detection sources
    det_by_ibge = _index_platform_detection(platform_det)
    det_by_ibge.update(
        {k: v for k, v in _index_platform_detection(platforms_json).items() if k not in det_by_ibge or v.get("url")}
    )

    residual_by_ibge = _index_residual_portals(DEFAULT_RESIDUAL_PORTALS)

    records: list[EntitySourceRecord] = []
    seen_ids: set[str] = set()

    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for idx, row in enumerate(reader, start=1):
            cnpj = _digits(row.get("cnpj"))
            name = (row.get("canonical_name") or row.get("name") or "").strip()
            entity_type = (row.get("entity_type") or "unknown").strip()
            municipio = (row.get("municipio") or "").strip()
            uf = (row.get("uf") or "SC").strip() or "SC"
            ibge = _digits(row.get("ibge_code"))
            lat = _safe_float(row.get("lat"))
            lon = _safe_float(row.get("lon"))
            distance_km = _safe_float(row.get("distance_km"))

            canonical_id = f"{cnpj}:{_slug(name)}"
            if canonical_id in seen_ids:
                canonical_id = f"{canonical_id}:{idx}"
            seen_ids.add(canonical_id)

            sphere = _sphere_for(entity_type)

            # Portal evidence from configs
            transp_entry = transp_by_ibge.get(ibge) if ibge else None
            det_entry = det_by_ibge.get(ibge) if ibge else None
            residual = residual_by_ibge.get(ibge) if ibge else None

            portal_transparencia: str | None = None
            portal_institucional: str | None = None
            portal_licitacoes: str | None = None
            diario_oficial: str | None = None
            integration_hint: str | None = None

            if transp_entry:
                portal_transparencia = transp_entry.get("portal_url") or None
                if transp_entry.get("requires_js"):
                    integration_hint = "js"
                else:
                    integration_hint = "html"

            if det_entry and det_entry.get("url"):
                url = det_entry["url"]
                platform_name = (det_entry.get("platform") or "").lower()
                if "transparencia" in url or platform_name in {"betha", "portal_transparencia_net", "e_gov_net"}:
                    portal_transparencia = portal_transparencia or url
                else:
                    portal_institucional = portal_institucional or url
                if platform_name in {"betha", "portal_transparencia_net"}:
                    integration_hint = integration_hint or "js"

            if residual and residual.get("url"):
                portal_institucional = portal_institucional or residual["url"]

            # Municipal diary heuristic (CIGA DOM SC) — candidate URL pattern only
            if sphere == "municipal" and entity_type in {
                "prefeitura",
                "camara_municipal",
                "secretaria_municipal",
                "autarquia_municipal",
                "fundacao_municipal",
            }:
                diario_oficial = "https://dados.ciga.sc.gov.br"  # shared CKAN portal

            has_portal = bool(portal_transparencia or portal_institucional or diario_oficial)
            has_detection = bool(det_entry and (det_entry.get("url") or det_entry.get("status") == "detected"))

            platforms, integration, sla = _seed_platforms(entity_type, sphere, has_portal, applicability)
            if integration_hint:
                integration = integration_hint

            status, strategy, blocker, next_action, confidence, evidences = _decide_status_and_strategy(
                entity_type=entity_type,
                sphere=sphere,
                platforms=platforms,
                portal_transparencia=portal_transparencia,
                portal_institucional=portal_institucional,
                diario_oficial=diario_oficial,
                has_detection=has_detection,
            )

            # url_patterns — candidates, not invented as live URLs
            url_patterns: dict[str, str] = {}
            if municipio and sphere == "municipal":
                slug_mun = _slug(municipio).lower().replace("_", "")
                url_patterns["prefeitura_candidate"] = f"https://{slug_mun}.sc.gov.br"
                url_patterns["prefeitura_alt_candidate"] = f"https://prefeitura.{slug_mun}.sc.gov.br"
            if cnpj:
                url_patterns["pncp_orgao_pattern"] = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj14}"

            external_ids: dict[str, Any] = {
                "cnpj8": cnpj[:8] if cnpj else None,
                "seed_sources": row.get("sources"),
                "zone": row.get("zone"),
                "sphere": sphere,
            }
            if ibge:
                external_ids["ibge_code"] = ibge
            if transp_entry:
                external_ids["transparencia_slug"] = transp_entry.get("slug")
                external_ids["transparencia_template"] = transp_entry.get("template")

            record = EntitySourceRecord(
                canonical_id=canonical_id,
                razao_social=name,
                nome_fantasia=None,
                cnpj=cnpj,
                natureza_juridica=entity_type,
                municipio=municipio,
                uf=uf,
                ibge_code=ibge or None,
                lat=lat,
                lon=lon,
                distance_km=distance_km,
                portal_institucional=portal_institucional,
                portal_transparencia=portal_transparencia,
                portal_licitacoes=portal_licitacoes,
                diario_oficial=diario_oficial,
                plataformas=platforms,
                external_ids=external_ids,
                url_patterns=url_patterns,
                integration_type=integration,
                access_status=status,
                last_success_at=None,
                last_attempt_at=None,
                sla_hours=sla,
                collection_strategy=strategy,
                current_blocker=blocker,
                next_action=next_action,
                priority=PRIORITY_BY_TYPE.get(entity_type, 5),
                mapping_confidence=confidence,
                evidences=evidences,
            )
            records.append(record)

    if len(records) != EXPECTED_ENTITY_COUNT:
        logger.warning(
            "Registry size %s != expected %s (CSV=%s)",
            len(records),
            EXPECTED_ENTITY_COUNT,
            path,
        )

    if persist:
        out_jsonl = Path(registry_path) if registry_path else DEFAULT_REGISTRY_JSONL
        out_summary = Path(summary_path) if summary_path else DEFAULT_REGISTRY_SUMMARY
        persist_registry(records, out_jsonl, out_summary)

    return records


def persist_registry(
    records: list[EntitySourceRecord],
    jsonl_path: Path | str = DEFAULT_REGISTRY_JSONL,
    summary_path: Path | str = DEFAULT_REGISTRY_SUMMARY,
) -> dict[str, Any]:
    """Write JSONL registry + summary stats."""
    jsonl_path = Path(jsonl_path)
    summary_path = Path(summary_path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with jsonl_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False, default=str) + "\n")

    summary = summarize_registry(records)
    summary["registry_path"] = str(jsonl_path)
    summary["summary_path"] = str(summary_path)
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    return summary


def summarize_registry(records: list[EntitySourceRecord]) -> dict[str, Any]:
    """Aggregate counts by status, blocker, platform, strategy."""
    total = len(records)
    by_status = Counter(r.access_status for r in records)
    by_blocker = Counter(r.current_blocker or "none" for r in records)
    by_strategy = Counter(r.collection_strategy for r in records)
    by_priority = Counter(r.priority for r in records)
    by_type = Counter(r.natureza_juridica for r in records)
    platform_counts: Counter[str] = Counter()
    for r in records:
        platform_counts.update(r.plataformas)

    mapped = by_status.get("mapped", 0) + by_status.get("accessible", 0) + by_status.get("collected", 0)
    operational = sum(1 for r in records if r.is_operational)

    return {
        "total_entities": total,
        "expected_entities": EXPECTED_ENTITY_COUNT,
        "mapped_or_better": mapped,
        "mapped_pct": round(100.0 * mapped / total, 2) if total else 0.0,
        "operational": operational,
        "operational_pct": round(100.0 * operational / total, 2) if total else 0.0,
        "by_status": dict(by_status.most_common()),
        "by_blocker": dict(by_blocker.most_common()),
        "by_strategy": dict(by_strategy.most_common()),
        "by_priority": {str(k): v for k, v in sorted(by_priority.items())},
        "by_entity_type": dict(by_type.most_common()),
        "platform_mentions": dict(platform_counts.most_common()),
        "with_portal_transparencia": sum(1 for r in records if r.portal_transparencia),
        "with_portal_institucional": sum(1 for r in records if r.portal_institucional),
        "with_diario_oficial": sum(1 for r in records if r.diario_oficial),
        "avg_mapping_confidence": (round(sum(r.mapping_confidence for r in records) / total, 4) if total else 0.0),
    }


def load_registry(path: str | Path | None = None) -> list[EntitySourceRecord]:
    """Load registry from JSONL (or build if missing)."""
    jsonl = Path(path) if path else DEFAULT_REGISTRY_JSONL
    if not jsonl.exists():
        return build_registry_from_csv(persist=True)
    records: list[EntitySourceRecord] = []
    with jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(EntitySourceRecord.from_dict(json.loads(line)))
    return records


def find_by_cnpj(records: list[EntitySourceRecord], cnpj: str) -> list[EntitySourceRecord]:
    """Find records matching a CNPJ (partial or full)."""
    needle = _digits(cnpj)
    if not needle:
        return []
    return [
        r for r in records if r.cnpj and (r.cnpj == needle or r.cnpj.startswith(needle) or needle.startswith(r.cnpj))
    ]


def group_by_municipio(records: list[EntitySourceRecord]) -> dict[str, list[EntitySourceRecord]]:
    """Group records by IBGE code (fallback municipio name)."""
    groups: dict[str, list[EntitySourceRecord]] = defaultdict(list)
    for r in records:
        key = r.ibge_code or r.municipio or "UNKNOWN"
        groups[key].append(r)
    return dict(groups)
