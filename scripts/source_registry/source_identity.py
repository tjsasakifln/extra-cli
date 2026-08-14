"""#281 — canonical source IDs, aliases and fail-closed pack totals.

Observations count once under the canonical source_id. An alias never
creates a second inventory row or a second pack total. Orphan aliases
and divergent inventory vs lineage counts fail closed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "source-identity/1.0"

# Canonical sources and the labels that must collapse into them.
CANONICAL_SOURCES: dict[str, frozenset[str]] = {
    "pncp": frozenset({"pncp", "pncp_opportunities", "pncp-oportunidades", "pncp_contratacoes"}),
    "ciga": frozenset({"ciga", "ciga_ckan", "dados_abertos_ciga"}),
    "sc_compras": frozenset({"sc_compras", "compras_sc", "sc-compras"}),
    "compras_gov": frozenset({"compras_gov", "comprasnet", "compras.gov"}),
}

CAPABILITIES = frozenset(
    {
        "opportunities",
        "contracts",
        "documents",
        "atas",
        "official_gazette",
    }
)


class SourceIdentityError(ValueError):
    """Pack totals cannot be published."""


@dataclass(frozen=True)
class SourceObservation:
    observation_id: str
    raw_source: str
    capability: str
    entity_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InventoryRecord:
    source_id: str
    capability: str
    observation_count: int
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class PackTotals:
    by_source: dict[str, int]
    by_source_capability: dict[str, int]
    observation_count: int
    canonicalized: tuple[dict[str, str], ...]
    blockers: tuple[str, ...]
    closed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "by_source": dict(self.by_source),
            "by_source_capability": dict(self.by_source_capability),
            "observation_count": self.observation_count,
            "canonicalized": list(self.canonicalized),
            "blockers": list(self.blockers),
            "closed": self.closed,
        }


def _fold(value: str) -> str:
    return " ".join(value.strip().casefold().replace("-", "_").split())


def alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical, aliases in CANONICAL_SOURCES.items():
        for alias in aliases:
            mapping[_fold(alias)] = canonical
    return mapping


def canonical_source_id(raw: str) -> str:
    token = _fold(raw)
    if not token:
        raise SourceIdentityError("empty source token")
    mapped = alias_map().get(token)
    if mapped is None:
        raise SourceIdentityError(f"orphan_alias:{raw}")
    return mapped


def resolve_observation(obs: SourceObservation) -> dict[str, str]:
    if obs.capability not in CAPABILITIES:
        raise SourceIdentityError(f"unknown_capability:{obs.capability}")
    source_id = canonical_source_id(obs.raw_source)
    return {
        "observation_id": obs.observation_id,
        "source_id": source_id,
        "capability": obs.capability,
        "raw_source": obs.raw_source,
    }


def reconcile_pack_totals(
    observations: tuple[SourceObservation, ...],
    inventory: tuple[InventoryRecord, ...],
) -> PackTotals:
    """Derive pack totals from lineage. Inventory must match or we fail closed."""
    blockers: list[str] = []
    resolved: list[dict[str, str]] = []
    by_source: dict[str, int] = {}
    by_cap: dict[str, int] = {}
    seen_ids: set[str] = set()

    for obs in observations:
        if obs.observation_id in seen_ids:
            blockers.append(f"duplicate_observation:{obs.observation_id}")
            continue
        seen_ids.add(obs.observation_id)
        try:
            row = resolve_observation(obs)
        except SourceIdentityError as exc:
            blockers.append(str(exc))
            continue
        resolved.append(row)
        by_source[row["source_id"]] = by_source.get(row["source_id"], 0) + 1
        cap_key = f"{row['source_id']}:{row['capability']}"
        by_cap[cap_key] = by_cap.get(cap_key, 0) + 1

    inventory_by_source: dict[str, int] = {}
    inventory_by_cap: dict[str, int] = {}
    for rec in inventory:
        try:
            source_id = canonical_source_id(rec.source_id)
        except SourceIdentityError as exc:
            blockers.append(f"inventory_{exc}")
            continue
        if _fold(rec.source_id) != source_id:
            blockers.append(f"inventory_alias_used_as_source_id:{rec.source_id}")
            continue
        if rec.capability not in CAPABILITIES:
            blockers.append(f"inventory_unknown_capability:{rec.capability}")
            continue
        # Aliases listed on the record must point at the same canonical id.
        for alias in rec.aliases:
            try:
                aliased = canonical_source_id(alias)
            except SourceIdentityError as exc:
                blockers.append(f"inventory_{exc}")
                continue
            if aliased != source_id:
                blockers.append(f"alias_divergent:{alias}->{aliased}!={source_id}")
        inventory_by_source[source_id] = inventory_by_source.get(source_id, 0) + rec.observation_count
        cap_key = f"{source_id}:{rec.capability}"
        inventory_by_cap[cap_key] = inventory_by_cap.get(cap_key, 0) + rec.observation_count

    if inventory_by_source != by_source:
        blockers.append(f"divergent_source_counts:{sorted(by_source.items())}!={sorted(inventory_by_source.items())}")
    if inventory_by_cap != by_cap:
        blockers.append("divergent_capability_counts")

    totals = PackTotals(
        by_source=dict(sorted(by_source.items())),
        by_source_capability=dict(sorted(by_cap.items())),
        observation_count=len(resolved),
        canonicalized=tuple(resolved),
        blockers=tuple(blockers),
        closed=not blockers,
    )
    if blockers:
        raise SourceIdentityError(";".join(blockers))
    return totals
