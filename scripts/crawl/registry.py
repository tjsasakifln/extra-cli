"""Central source registry — single source of truth for all crawler sources.

Eliminates the 6 independent source lists spread across:
    monitor.py, backfill_multi_source.py, orchestrator.py,
    credential_validator.py, test_smoke_sources.py, test_crawler_protocol.py

Usage::

    from scripts.crawl.registry import lookup, iter_sources, resolve_name

    info = lookup("mides-bigquery")  # resolves alias → canonical
    for src in iter_sources():
        print(src.name, src.module, src.purpose)
    canonical = resolve_name("ciga-ckan")  # → "ciga_ckan"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

SourcePurpose = Literal["bids", "coverage_only", "hybrid"]


@dataclass
class SourceInfo:
    """Canonical metadata for a single data source."""

    name: str
    """Canonical name (underscore form, e.g. ``"mides_bigquery"``)."""

    aliases: list[str] = field(default_factory=list)
    """Alternate names (e.g. ``"mides-bigquery"``, ``"ciga-ckan"``)."""

    module: str = ""
    """Module name under ``scripts.crawl.`` (e.g. ``"pncp_crawler_adapter"``)."""

    purpose: SourcePurpose = "bids"
    """``"bids"`` — produces bid records for upsert.
    ``"coverage_only"`` — only updates entity_coverage.
    ``"hybrid"`` — does both."""

    credentials: list[str] = field(default_factory=list)
    """Required env var names (empty = public source)."""

    upsert_function: str = "upsert_pncp_raw_bids"
    """Database RPC function for upserting this source's data."""

    modes: list[str] = field(default_factory=lambda: ["full", "incremental", "dry-run"])
    """Supported crawl modes."""

    order: int = 99
    """Execution order (lower runs first)."""

    description: str = ""
    """Human-readable summary."""

    is_active: bool = True
    """Whether this source is active in the pipeline."""

    is_public: bool = True
    """Whether this source requires no credentials."""

    def __post_init__(self):
        if not self.is_public and not self.credentials:
            self.is_public = False
        if self.credentials:
            self.is_public = False


# ---------------------------------------------------------------------------
# Canonical registry — single source of truth
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, SourceInfo] = {}

_RAW: list[SourceInfo] = [
    SourceInfo(
        name="pncp",
        module="pncp_crawler_adapter",
        purpose="bids",
        order=1,
        description="PNCP API (federal + adesao voluntaria)",
    ),
    SourceInfo(
        name="dom_sc",
        module="dom_sc_crawler",
        purpose="bids",
        credentials=["DOM_SC_CPF", "DOM_SC_CNPJ", "DOM_SC_API_KEY"],
        order=2,
        description="DOM-SC (Diario Oficial dos Municipios de SC)",
    ),
    SourceInfo(
        name="pcp",
        module="pcp_crawler",
        purpose="bids",
        order=3,
        description="PCP (Portal de Compras Publicas)",
    ),
    SourceInfo(
        name="compras_gov",
        aliases=["compras-gov"],
        module="compras_gov_crawler",
        purpose="bids",
        order=4,
        description="ComprasGov (compras federais)",
    ),
    SourceInfo(
        name="sc_compras",
        aliases=["sc-compras"],
        module="sc_compras_crawler",
        purpose="bids",
        order=5,
        description="SC Compras",
    ),
    SourceInfo(
        name="contracts",
        module="contracts_crawler",
        purpose="bids",
        upsert_function="upsert_pncp_supplier_contracts",
        order=6,
        description="PNCP supplier contracts",
    ),
    SourceInfo(
        name="transparencia",
        module="transparencia_crawler",
        purpose="bids",
        order=7,
        description="Transparencia portals (batch detect + crawl)",
    ),
    SourceInfo(
        name="tce_sc",
        aliases=["tce-sc"],
        module="tce_sc_crawler",
        purpose="bids",
        order=8,
        description="TCE-SC SCMWeb (Tribunal de Contas de SC)",
    ),
    SourceInfo(
        name="doe_sc",
        aliases=["doe-sc"],
        module="doe_sc_crawler",
        purpose="bids",
        credentials=["DOE_SC_LOGIN", "DOE_SC_PASSWORD"],
        order=9,
        description="DOE-SC (Diario Oficial Estadual de SC)",
    ),
    SourceInfo(
        name="ciga_ckan",
        aliases=["ciga-ckan"],
        module="ciga_ckan_crawler",
        purpose="coverage_only",
        order=10,
        description="CIGA CKAN (coverage assessment only — no bids extracted)",
    ),
    SourceInfo(
        name="mides_bigquery",
        aliases=["mides-bigquery"],
        module="mides_bigquery_crawler",
        purpose="bids",
        credentials=["GOOGLE_APPLICATION_CREDENTIALS"],
        order=11,
        description="MIDES BigQuery (dados de compras estaduais)",
    ),
    SourceInfo(
        name="selenium",
        module="selenium_crawler_adapter",
        purpose="bids",
        modes=["full", "incremental", "dry-run", "selenium"],
        order=12,
        description="Selenium batch crawler (JS-rendered portals)",
    ),
]

# Build registry + alias index
_ALIAS_MAP: dict[str, str] = {}
for info in _RAW:
    _REGISTRY[info.name] = info
    _ALIAS_MAP[info.name] = info.name
    for alias in info.aliases:
        _ALIAS_MAP[alias] = info.name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lookup(key: str) -> SourceInfo | None:
    """Resolve a source name or alias to its SourceInfo, or None.

    Accepts both canonical (underscore) and alias (hyphen) forms::

        lookup("mides-bigquery")  → SourceInfo(name="mides_bigquery")
        lookup("ciga-ckan")       → SourceInfo(name="ciga_ckan")
        lookup("nonexistent")      → None
    """
    # Direct match
    canonical = _ALIAS_MAP.get(key)
    if canonical:
        return _REGISTRY[canonical]
    # Fallback: normalize hyphens to underscores
    normalized = key.replace("-", "_")
    canonical = _ALIAS_MAP.get(normalized)
    if canonical:
        return _REGISTRY[canonical]
    return None


def resolve_name(key: str) -> str:
    """Normalize a source name (hyphen or underscore) to canonical form.

    Returns the original key if no match found.
    """
    info = lookup(key)
    return info.name if info else key.replace("-", "_")


def iter_sources(
    purpose: SourcePurpose | None = None,
    active_only: bool = True,
) -> list[SourceInfo]:
    """Return all sources, sorted by execution order, optionally filtered.

    Args:
        purpose: Filter by purpose (``"bids"``, ``"coverage_only"``, ``"hybrid"``).
        active_only: If True (default), only return active sources.
    """
    sources = _REGISTRY.values()
    if active_only:
        sources = [s for s in sources if s.is_active]
    if purpose:
        sources = [s for s in sources if s.purpose == purpose]
    return sorted(sources, key=lambda s: s.order)


def get_credential_sources() -> set[str]:
    """Return set of source names that require credentials."""
    return {s.name for s in iter_sources() if s.credentials}


def get_public_sources() -> set[str]:
    """Return set of source names that are public (no credentials)."""
    return {s.name for s in iter_sources() if not s.credentials}


def get_coverage_only_sources() -> set[str]:
    """Return set of source names with purpose='coverage_only'."""
    return {s.name for s in iter_sources(purpose="coverage_only")}


def iter_choices() -> list[str]:
    """Return all valid CLI choices (canonical names + aliases)."""
    choices: list[str] = []
    for s in iter_sources():
        choices.append(s.name)
        choices.extend(s.aliases)
    choices.append("all")
    return sorted(choices)


# ---------------------------------------------------------------------------
# Re-export SourcePurpose markers for convenience
# ---------------------------------------------------------------------------

BIDS: SourcePurpose = "bids"
COVERAGE_ONLY: SourcePurpose = "coverage_only"
HYBRID: SourcePurpose = "hybrid"

__all__ = [
    "BIDS",
    "COVERAGE_ONLY",
    "HYBRID",
    "SourceInfo",
    "SourcePurpose",
    "get_coverage_only_sources",
    "get_credential_sources",
    "get_public_sources",
    "iter_choices",
    "iter_sources",
    "lookup",
    "resolve_name",
]
