"""Document-source discovery for all 1.093 entities (cadastral, not operational).

Zero ``unknown`` allowed in the final discovery report. Reuses the canonical
entity source registry — does not create a second registry.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.models import (
    PORTAL_FAMILIES,
    EntityDocumentDiscovery,
    classify_portal_family,
)
from scripts.process_documents.statuses import DiscoveryStatus
from scripts.process_documents.storage import DEFAULT_META_ROOT, ensure_roots, write_json
from scripts.source_registry.builder import DEFAULT_REGISTRY_JSONL, load_registry
from scripts.source_registry.models import EntitySourceRecord

EXPECTED_UNIVERSE = 1093
CAPABILITY = "procurement_process_documents"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _pncp_url(cnpj: str) -> str:
    digits = "".join(ch for ch in (cnpj or "") if ch.isdigit())
    if len(digits) == 8:
        # org endpoint prefers 14 digits; keep root for discovery record
        return f"https://pncp.gov.br/app/orgaos/{digits}"
    if len(digits) >= 14:
        return f"https://pncp.gov.br/api/pncp/v1/orgaos/{digits[:14]}"
    return "https://pncp.gov.br"


def _dispute_platform(platforms: list[str]) -> str | None:
    for name in ("compras_gov", "sc_compras", "pcp", "licitanet", "bll", "bbmnet"):
        if name in {p.lower() for p in platforms}:
            return name
    return None


def _admin_process_system(platforms: list[str], external_ids: dict[str, Any]) -> str | None:
    for name in ("sei", "processo_eletronico", "protocolo"):
        if name in {p.lower() for p in platforms} or name in external_ids:
            return name
    if external_ids.get("ciga_municipio_key"):
        return "ciga_shared_portal"
    return None


def _access_status(record: EntitySourceRecord) -> str:
    """Map registry access_status to discovery vocabulary; never return unknown."""
    status = (record.access_status or "").lower()
    mapping = {
        "mapped": DiscoveryStatus.MAPPED.value,
        "accessible": DiscoveryStatus.ACCESSIBLE.value,
        "collected": DiscoveryStatus.COLLECTED.value,
        "verified": DiscoveryStatus.VERIFIED.value,
        "operational": DiscoveryStatus.OPERATIONAL.value,
        "failed": DiscoveryStatus.FAILED.value,
        "blocked": DiscoveryStatus.BLOCKED.value,
        "source_not_identified": DiscoveryStatus.SOURCE_NOT_IDENTIFIED.value,
    }
    if status in mapping:
        return mapping[status]
    # unknown / empty → explicit source_not_identified or mapped via PNCP default
    platforms = [p.lower() for p in (record.plataformas or [])]
    if "pncp" in platforms or record.cnpj:
        return DiscoveryStatus.MAPPED.value
    return DiscoveryStatus.SOURCE_NOT_IDENTIFIED.value


def _blocker(record: EntitySourceRecord, access: str) -> str | None:
    if record.current_blocker and record.current_blocker not in ("none", ""):
        return record.current_blocker
    if access == DiscoveryStatus.BLOCKED.value:
        return "access_blocked"
    if access == DiscoveryStatus.SOURCE_NOT_IDENTIFIED.value:
        return "no_primary_document_source"
    if access in (DiscoveryStatus.MAPPED.value, DiscoveryStatus.ACCESSIBLE.value):
        return "pending_live_document_collection"
    return None


def _strategy(record: EntitySourceRecord, family: str) -> tuple[str, str]:
    base = record.collection_strategy or "pending_review"
    primary = f"document_collect:{family}"
    if family == "pncp":
        primary = "pncp_compra_arquivos"
    elif family.startswith("ciga"):
        primary = "ciga_ckan_or_dom_publications"
    fallback = "pncp_gap_fill" if family != "pncp" else "portal_institucional_html_index"
    if base and base != "pending_review":
        return primary, f"{fallback}|registry:{base}"
    return primary, fallback


def classify_entity(record: EntitySourceRecord) -> EntityDocumentDiscovery:
    """Produce a non-unknown document discovery decision for one entity."""
    platforms = list(record.plataformas or [])
    family = classify_portal_family(
        platforms,
        has_institutional=bool(record.portal_institucional),
    )
    family_meta = PORTAL_FAMILIES.get(family, PORTAL_FAMILIES["generic_public_html"])
    access = _access_status(record)
    # Applicability: all entities in the 200km universe are applicable for
    # public document discovery unless explicitly marked not_applicable.
    applicability = "applicable"
    reason = "entity_in_canonical_200km_universe"
    if record.current_blocker == "not_applicable":
        applicability = "not_applicable"
        reason = "registry_blocker_not_applicable"
        access = DiscoveryStatus.NOT_APPLICABLE.value

    primary, fallback = _strategy(record, family)
    caps = list(family_meta.get("capabilities") or [])
    if "pncp" in {p.lower() for p in platforms} and "notice_documents" not in caps:
        caps.append("notice_documents")

    return EntityDocumentDiscovery(
        canonical_id=record.canonical_id,
        razao_social=record.razao_social,
        cnpj=record.cnpj,
        municipio=record.municipio or "",
        uf=record.uf or "SC",
        applicability=applicability,
        applicability_reason=reason,
        institutional_site=record.portal_institucional,
        transparency_portal=record.portal_transparencia,
        procurement_portal=record.portal_licitacoes or record.portal_institucional,
        dispute_platform=_dispute_platform(platforms),
        admin_process_system=_admin_process_system(platforms, record.external_ids or {}),
        pncp_source=_pncp_url(record.cnpj),
        portal_family=family,
        capabilities=sorted(set(caps)),
        access_status=access,
        last_verified_at=_now(),
        blocker=_blocker(record, access),
        collection_strategy=primary,
        fallback_strategy=fallback,
        platforms=platforms,
        mapping_confidence=float(record.mapping_confidence or 0.0),
        evidences=list(record.evidences or [])
        + [
            {
                "type": "document_discovery",
                "capability": CAPABILITY,
                "portal_family": family,
                "classified_at": _now(),
            }
        ],
    )


def discover_all(
    registry_path: Path | str | None = None,
    *,
    persist: bool = True,
    output_dir: Path | str | None = None,
) -> tuple[list[EntityDocumentDiscovery], dict[str, Any]]:
    """Classify all registry entities for document discovery (expect 1093)."""
    records = load_registry(Path(registry_path) if registry_path else DEFAULT_REGISTRY_JSONL)
    discoveries = [classify_entity(r) for r in records]
    report = build_discovery_report(discoveries)
    if persist:
        _, meta = ensure_roots()
        out = Path(output_dir or meta)
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "document-source-registry.json", report)
        write_json(
            out / "document-source-registry.md.json",
            {"markdown_path": str(out / "document-source-registry.md")},
        )
        (out / "document-source-registry.md").write_text(
            render_discovery_markdown(report),
            encoding="utf-8",
        )
        # Sidecar JSONL (extends registry, not a second SoT of identity)
        jsonl_path = out / "entity-document-discovery.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for d in sorted(discoveries, key=lambda x: x.canonical_id):
                fh.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")
        report["artifacts"] = {
            "json": str(out / "document-source-registry.json"),
            "md": str(out / "document-source-registry.md"),
            "jsonl": str(jsonl_path),
        }
    return discoveries, report


def ordered_id_hash(ids: list[str]) -> str:
    payload = "\n".join(sorted(ids)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_discovery_report(discoveries: list[EntityDocumentDiscovery]) -> dict[str, Any]:
    ids = [d.canonical_id for d in discoveries]
    unknown = [d.canonical_id for d in discoveries if d.access_status == "unknown"]
    unknown_applicability = [d.canonical_id for d in discoveries if d.applicability == "unknown"]
    by_family: dict[str, int] = {}
    by_access: dict[str, int] = {}
    for d in discoveries:
        by_family[d.portal_family] = by_family.get(d.portal_family, 0) + 1
        by_access[d.access_status] = by_access.get(d.access_status, 0) + 1

    n = len(discoveries)
    discovery_coverage = (n / EXPECTED_UNIVERSE) if EXPECTED_UNIVERSE else 0.0
    # 100% only if n==1093, zero unknown access, zero unknown applicability
    clean = n == EXPECTED_UNIVERSE and not unknown and not unknown_applicability
    if clean:
        discovery_coverage = 1.0

    return {
        "metric": "entity_source_discovery_coverage",
        "capability": CAPABILITY,
        "denominator": EXPECTED_UNIVERSE,
        "numerator": n if clean else max(0, n - len(unknown) - len(unknown_applicability)),
        "entity_count": n,
        "entity_source_discovery_coverage": discovery_coverage,
        "entity_source_discovery_coverage_percent": round(discovery_coverage * 100, 4),
        "meets_100_percent": clean and discovery_coverage >= 1.0,
        "unknown_access_count": len(unknown),
        "unknown_access_ids": unknown[:50],
        "unknown_applicability_count": len(unknown_applicability),
        "canonical_ids_sha256": ordered_id_hash(ids),
        "canonical_ids_sorted": sorted(ids),
        "by_portal_family": dict(sorted(by_family.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_access_status": dict(sorted(by_access.items(), key=lambda kv: (-kv[1], kv[0]))),
        "generated_at": _now(),
        "entities": [d.to_dict() for d in sorted(discoveries, key=lambda x: x.canonical_id)],
    }


def render_discovery_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Document source registry (discovery cadastral)",
        "",
        f"- Metric: `{report['metric']}`",
        f"- Denominator: **{report['denominator']}**",
        f"- Entity count: **{report['entity_count']}**",
        f"- Coverage: **{report['entity_source_discovery_coverage_percent']}%**",
        f"- Meets 100%: **{report['meets_100_percent']}**",
        f"- Unknown access: **{report['unknown_access_count']}**",
        f"- Canonical IDs SHA-256: `{report['canonical_ids_sha256']}`",
        f"- Generated at: {report['generated_at']}",
        "",
        "## Portal families",
        "",
    ]
    for fam, count in (report.get("by_portal_family") or {}).items():
        lines.append(f"- `{fam}`: {count}")
    lines += ["", "## Access status", ""]
    for st, count in (report.get("by_access_status") or {}).items():
        lines.append(f"- `{st}`: {count}")
    lines += [
        "",
        "> Cadastral discovery proves investigation/classification only.",
        "> It does **not** prove operational document collection.",
        "",
    ]
    return "\n".join(lines) + "\n"


def load_discovery(path: Path | str | None = None) -> list[EntityDocumentDiscovery]:
    p = Path(path or (DEFAULT_META_ROOT / "entity-document-discovery.jsonl"))
    if not p.is_file():
        discoveries, _ = discover_all(persist=True)
        return discoveries
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(EntityDocumentDiscovery.from_dict(json.loads(line)))
    return rows
