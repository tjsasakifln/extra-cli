"""CIGA DOM municipio expansion — shared portal covers all municipal entities.

REAL strategy: the municipal official diary (CIGA DOM SC / dados.ciga.sc.gov.br)
publishes acts for the whole município. Once a município is on the monitoring
path, every prefeitura/câmara/secretaria/autarquia in that IBGE code inherits
the shared portal as a collection channel.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from scripts.source_registry.builder import group_by_municipio, persist_registry
from scripts.source_registry.models import EntitySourceRecord

logger = logging.getLogger(__name__)

CIGA_CKAN_URL = "https://dados.ciga.sc.gov.br"
CIGA_PLATFORM = "ciga_ckan"
DOM_PLATFORM = "dom_sc"

MUNICIPAL_TYPES = frozenset(
    {
        "prefeitura",
        "camara_municipal",
        "secretaria_municipal",
        "fundacao_municipal",
        "autarquia_municipal",
    }
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_municipal(rec: EntitySourceRecord) -> bool:
    if rec.natureza_juridica in MUNICIPAL_TYPES:
        return True
    sphere = (rec.external_ids or {}).get("sphere")
    return sphere == "municipal"


def _needs_ciga(rec: EntitySourceRecord) -> bool:
    if not _is_municipal(rec):
        return False
    if rec.access_status in {"accessible", "collected"}:
        # Still ensure platform is linked, but don't count as uncovered
        return CIGA_PLATFORM not in (rec.plataformas or [])
    return True


def expand_ciga_by_municipio(
    records: list[EntitySourceRecord],
    *,
    limit: int = 0,
    persist: bool = True,
    only_uncovered: bool = True,
) -> dict[str, Any]:
    """Link município → all municipal entities as CIGA shared-portal monitoring path.

    Args:
        records: Full registry (mutated in place).
        limit: Max municípios to expand (0 = all).
        persist: Rewrite registry JSONL.
        only_uncovered: When True, only update entities that still need CIGA path.

    Returns:
        Summary stats.
    """
    groups = group_by_municipio(records)
    # Prefer groups that contain a prefeitura (anchor entity)
    municipio_keys = sorted(
        groups.keys(),
        key=lambda k: (
            0 if any(r.natureza_juridica == "prefeitura" for r in groups[k]) else 1,
            min((r.priority for r in groups[k]), default=9),
            k,
        ),
    )
    if limit and limit > 0:
        municipio_keys = municipio_keys[:limit]

    updated = 0
    municipios_touched = 0
    entities_linked = 0
    skipped_non_municipal = 0
    ts = _now_iso()

    for key in municipio_keys:
        members = groups[key]
        municipal_members = [r for r in members if _is_municipal(r)]
        if not municipal_members:
            skipped_non_municipal += 1
            continue

        # Anchor: prefeitura if present, else highest priority municipal
        anchor = next(
            (r for r in municipal_members if r.natureza_juridica == "prefeitura"),
            sorted(municipal_members, key=lambda r: r.priority)[0],
        )
        municipios_touched += 1

        for rec in municipal_members:
            if only_uncovered and not _needs_ciga(rec) and CIGA_PLATFORM in (rec.plataformas or []):
                continue

            platforms = list(rec.plataformas or [])
            for p in (CIGA_PLATFORM, DOM_PLATFORM):
                if p not in platforms:
                    platforms.append(p)
            rec.plataformas = platforms
            rec.diario_oficial = rec.diario_oficial or CIGA_CKAN_URL
            rec.integration_type = rec.integration_type if rec.integration_type != "unknown" else "ckan"
            rec.collection_strategy = "ciga_ckan_shared_municipio"
            rec.external_ids = dict(rec.external_ids or {})
            rec.external_ids["ciga_municipio_key"] = key
            rec.external_ids["ciga_anchor_canonical_id"] = anchor.canonical_id
            rec.external_ids["ciga_shared_portal"] = CIGA_CKAN_URL

            evidence = {
                "type": "ciga_municipio_expand",
                "municipio_key": key,
                "anchor_canonical_id": anchor.canonical_id,
                "anchor_name": anchor.razao_social,
                "shared_portal": CIGA_CKAN_URL,
                "attempted_at": ts,
                "note": "Municipal diary covers all municipal entities in the city",
            }
            rec.evidences = list(rec.evidences or []) + [evidence]
            rec.last_attempt_at = ts

            # Shared portal is a real *monitoring path* (mapped), not operational coverage.
            # Operational requires collect+normalize+reconcile+verify of publications.
            if rec.access_status in {"unknown", "source_not_identified", "failed"}:
                rec.access_status = "mapped"
                rec.current_blocker = "pending_collection"
                rec.next_action = "ingest_ciga_dom_publications_for_municipio_then_reconcile"
                rec.mapping_confidence = min(1.0, max(rec.mapping_confidence, 0.65))
                # Do NOT set last_success_at — path known ≠ collection succeeded
                updated += 1
            elif rec.access_status == "mapped":
                rec.next_action = "ingest_ciga_dom_publications_for_municipio_then_reconcile"
                if rec.current_blocker in {None, "none", "no_api", "fragmented"}:
                    rec.current_blocker = "pending_collection"
                updated += 1
            entities_linked += 1

    summary: dict[str, Any] = {
        "strategy": "ciga_municipio_expand",
        "municipios_touched": municipios_touched,
        "entities_linked": entities_linked,
        "status_upgraded": updated,
        "skipped_non_municipal_groups": skipped_non_municipal,
        "total_groups": len(groups),
        "limit": limit or "all",
    }

    if persist:
        persist_registry(records)
        summary["persisted"] = True
    else:
        summary["persisted"] = False

    logger.info(
        "CIGA expand: %s municípios, %s entities linked, %s status upgrades",
        municipios_touched,
        entities_linked,
        updated,
    )
    return summary
