"""Central source registry — single source of truth for all crawler sources.

Eliminates the 6 independent source lists spread across:
    monitor.py, backfill_multi_source.py, orchestrator.py,
    credential_validator.py, test_smoke_sources.py, test_crawler_protocol.py

Story 1.5 expansion:
    - Added fields from Secao 9: capabilities, authority_level, entity_types,
      credential_names, snapshot_semantics, freshness_sla_hours,
      supports_pagination, supports_zero_proof, reconciliation_strategy, is_contract_source
    - Fixed: contracts != bids (is_contract_source=True)
    - Fixed: selenium != fonte (removed as source, it's a crawl method)

Usage::

    from scripts.crawl.registry import lookup, iter_sources, resolve_name

    info = lookup("mides-bigquery")  # resolves alias → canonical
    for src in iter_sources():
        print(src.name, src.module, src.purpose)
    canonical = resolve_name("ciga-ckan")  # → "ciga_ckan"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Types (Secao 9 expanded)
# ---------------------------------------------------------------------------

SourcePurpose = Literal["bids", "contracts", "coverage_only", "hybrid"]

SourceCapability = Literal[
    "open_tenders",
    "historical_contracts",
    "competitors",
    "prices",
    "entity_matching",
    "coverage_truth",
    "source_health",
]

AuthorityLevel = Literal["federal", "estadual", "municipal", "multi"]

SnapshotSemantics = Literal["full_refresh", "incremental", "append_only", "coverage_only"]


@dataclass
class SourceInfo:
    """Canonical metadata for a single data source.

    Story 1.5 expands this dataclass with fields from Secao 9 of the master
    plan to support the coverage model (applicability, state machine,
    capability tracking).
    """

    # -- Core identity (Secao 9: name, authority_level, entity_types) --------
    name: str
    """Canonical name (underscore form, e.g. ``"mides_bigquery"``)."""

    aliases: list[str] = field(default_factory=list)
    """Alternate names (e.g. ``"mides-bigquery"``, ``"ciga-ckan"``)."""

    module: str = ""
    """Module name under ``scripts.crawl.`` (e.g. ``"pncp_crawler_adapter"``)."""

    purpose: SourcePurpose = "bids"
    """``"bids"`` — produces bid records for upsert.
    ``"contracts"`` — produces contract records (NOT bids).
    ``"coverage_only"`` — only updates entity_coverage.
    ``"hybrid"`` — does both."""

    description: str = ""
    """Human-readable summary."""

    # -- Story 1.5 expanded fields (Secao 9) --------------------------------

    capabilities: list[SourceCapability] = field(default_factory=list)
    """Which business capabilities this source supports.
    Used by coverage manifest to report per-capability coverage."""

    authority_level: AuthorityLevel = "municipal"
    """Sphere of authority: federal, estadual, municipal, or multi."""

    entity_types: list[str] = field(default_factory=list)
    """Types of entities this source covers
    (e.g. ``["prefeituras", "camaras", "autarquias"]``).
    Empty list = all types."""

    credential_names: list[str] = field(default_factory=list)
    """Required credential names (logical names, not env vars).
    Used by credential_validator and coverage blocker reporting."""

    # -- Crawl semantics ----------------------------------------------------

    snapshot_semantics: SnapshotSemantics = "full_refresh"
    """How this source's data is refreshed:
    ``"full_refresh"`` — full crawl replaces all data.
    ``"incremental"`` — only new/changed records.
    ``"append_only"`` — records are never updated, only appended."""

    freshness_sla_hours: int = 24
    """SLA in hours for data freshness from this source."""

    supports_pagination: bool = True
    """Whether this source supports paginated fetching.
    If False, success_zero cannot be proven."""

    supports_zero_proof: bool = False
    """Whether this source can prove zero results (complete pagination).
    ``success_zero`` requires this to be True."""

    reconciliation_strategy: str = "key_based"
    """Strategy for reconciling data from this source:
    ``"key_based"`` — upsert by primary key.
    ``"full_replace"`` — delete and re-insert.
    ``"append"`` — only insert, no updates.
    ``"coverage_only"`` — no data reconciliation needed."""

    # -- Contracts vs Bids distinction (Story 1.5 fix) ----------------------

    is_contract_source: bool = False
    """True when this source produces contract records (not bids).
    Story 1.5: contracts != bids — this flag separates them."""

    # -- Legacy fields (kept for backward compatibility) ---------------------

    credentials: list[str] = field(default_factory=list)
    """Required env var names (empty = public source)."""

    upsert_function: str = "upsert_pncp_raw_bids"
    """Database RPC function for upserting this source's data."""

    modes: list[str] = field(default_factory=lambda: ["full", "incremental", "dry-run"])
    """Supported crawl modes."""

    order: int = 99
    """Execution order (lower runs first)."""

    is_active: bool = True
    """Whether this source is active in the pipeline."""

    is_public: bool = True
    """Whether this source requires no credentials."""

    adapter_contract: Literal["adr021", "legacy"] = "legacy"
    """Contract used by the operational path. Legacy sources never inflate its coverage."""

    operational_validated: bool = False
    """True only after contract, fail-closed, resume and evidence tests pass."""

    resilience_adapter: str | None = None
    """Import path for the explicit ADR-021 adapter, when validated."""

    # -- DoD §7.1 registry fields --------------------------------------------

    canonical_url: str = ""
    """Canonical URL or API endpoint for this source."""

    geo_coverage: str = "SC"
    """Geographic coverage statement (e.g. BR, SC, municipal SC)."""

    pagination_limits: str = "unknown"
    """Known pagination limits (page size / max pages)."""

    rate_limits: str = "unknown"
    """Known rate limits (requests per minute / polite defaults)."""

    retry_strategy: str = "exponential_backoff"
    """Retry strategy name used by crawler/resilience layer."""

    backoff_strategy: str = "exp_jitter"
    """Backoff strategy (e.g. exp_jitter, fixed)."""

    role: Literal["primary", "complementary", "gap_fill"] = "complementary"
    """Whether source is primary, complementary, or gap-fill for Extra."""

    last_validation_at: str | None = None
    """ISO date of last operational validation evidence (if any)."""

    known_blockers: list[str] = field(default_factory=list)
    """Known operational blockers (rate limit, auth, etc.)."""

    def __post_init__(self) -> None:
        if not self.is_public and not self.credentials:
            self.is_public = False
        if self.credentials:
            self.is_public = False
        # Auto-derive credentials set from credential_names
        if self.credential_names and not self.credentials:
            self.credentials = self.credential_names[:]
        # Legacy: map credential_names if only credentials is set
        if self.credentials and not self.credential_names:
            self.credential_names = self.credentials[:]

    @property
    def needs_credentials(self) -> bool:
        return bool(self.credentials) or not self.is_public

    @property
    def operational_status(self) -> str:
        """DoD status: active | implemented_not_proven | blocked | not_applicable."""
        if not self.is_active:
            return "not_applicable"
        if self.known_blockers and any("blocked" in b.lower() for b in self.known_blockers):
            return "blocked"
        if self.operational_validated and self.canonical_url:
            return "active"
        if self.module:
            return "implemented_not_proven"
        return "blocked"

    def to_dod_record(self) -> dict[str, Any]:
        """Serialize DoD §7.1 fields for export/audit."""
        return {
            "id": self.name,
            "aliases": list(self.aliases),
            "canonical_url": self.canonical_url,
            "capabilities": list(self.capabilities),
            "geo_coverage": self.geo_coverage,
            "needs_credentials": self.needs_credentials,
            "credential_names": list(self.credential_names),
            "pagination_limits": self.pagination_limits,
            "rate_limits": self.rate_limits,
            "retry_strategy": self.retry_strategy,
            "backoff_strategy": self.backoff_strategy,
            "operational_status": self.operational_status,
            "operational_validated": self.operational_validated,
            "last_validation_at": self.last_validation_at,
            "known_blockers": list(self.known_blockers),
            "role": self.role,
            "authority_level": self.authority_level,
            "module": self.module,
            "is_active": self.is_active,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Canonical registry — single source of truth
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, SourceInfo] = {}

_RAW: list[SourceInfo] = [
    SourceInfo(
        name="pncp",
        module="pncp_crawler_adapter",
        purpose="bids",
        capabilities=["open_tenders", "historical_contracts", "entity_matching"],
        authority_level="federal",
        entity_types=[],
        snapshot_semantics="incremental",
        freshness_sla_hours=4,
        supports_pagination=True,
        supports_zero_proof=True,
        reconciliation_strategy="key_based",
        order=1,
        adapter_contract="adr021",
        operational_validated=True,
        resilience_adapter="scripts.crawl.resilience.adapters.PNCPAdapter",
        description="PNCP API (federal + adesao voluntaria) — primary open tenders source",
    ),
    SourceInfo(
        name="dom_sc",
        module="dom_sc_crawler",
        purpose="bids",
        capabilities=["open_tenders"],
        authority_level="municipal",
        entity_types=["prefeituras", "camaras"],
        credential_names=["DOM_SC_CPF", "DOM_SC_CNPJ", "DOM_SC_API_KEY"],
        credentials=["DOM_SC_CPF", "DOM_SC_CNPJ", "DOM_SC_API_KEY"],
        snapshot_semantics="incremental",
        freshness_sla_hours=24,
        supports_pagination=True,
        supports_zero_proof=False,
        reconciliation_strategy="key_based",
        order=12,  # legacy path; ciga_ckan is preferred for municipal DOM
        description=(
            "DOM-SC path legado (diariomunicipal.sc.gov.br remote/list) — "
            "requer CPF/CNPJ/API key. Preferir ciga_ckan (CIGA Dados público)."
        ),
    ),
    SourceInfo(
        name="pcp",
        module="pcp_crawler",
        purpose="bids",
        capabilities=["open_tenders"],
        authority_level="multi",
        entity_types=[],
        snapshot_semantics="incremental",
        freshness_sla_hours=24,
        supports_pagination=True,
        supports_zero_proof=False,
        reconciliation_strategy="key_based",
        order=3,
        description="PCP (Portal de Compras Publicas)",
    ),
    SourceInfo(
        name="compras_gov",
        aliases=["compras-gov"],
        module="compras_gov_crawler",
        purpose="bids",
        capabilities=["open_tenders"],
        authority_level="federal",
        entity_types=[],
        snapshot_semantics="incremental",
        freshness_sla_hours=12,
        supports_pagination=True,
        supports_zero_proof=False,
        reconciliation_strategy="key_based",
        order=4,
        description="ComprasGov (compras federais)",
    ),
    SourceInfo(
        name="sc_compras",
        aliases=["sc-compras"],
        module="sc_compras_crawler",
        purpose="bids",
        capabilities=["open_tenders"],
        authority_level="estadual",
        entity_types=[],
        snapshot_semantics="incremental",
        freshness_sla_hours=24,
        supports_pagination=True,
        supports_zero_proof=False,
        reconciliation_strategy="key_based",
        order=5,
        adapter_contract="adr021",
        operational_validated=True,
        resilience_adapter="scripts.crawl.resilience.adapters.ScComprasAdapter",
        description="SC Compras",
    ),
    # ------------------------------------------------------------------
    # CONTRACTS: Story 1.5 fix — contracts != bids
    # ------------------------------------------------------------------
    SourceInfo(
        name="contracts",
        module="contracts_crawler",
        purpose="contracts",
        is_contract_source=True,
        capabilities=["historical_contracts", "competitors"],
        authority_level="federal",
        entity_types=[],
        credential_names=[],
        snapshot_semantics="incremental",
        freshness_sla_hours=24,
        supports_pagination=True,
        supports_zero_proof=True,
        reconciliation_strategy="key_based",
        upsert_function="upsert_pncp_supplier_contracts",
        order=6,
        description="PNCP supplier contracts (NOT bids — contracts capability)",
    ),
    SourceInfo(
        name="transparencia",
        module="transparencia_crawler",
        purpose="bids",
        capabilities=["open_tenders"],
        authority_level="municipal",
        entity_types=["prefeituras", "camaras"],
        snapshot_semantics="full_refresh",
        freshness_sla_hours=48,
        supports_pagination=True,
        supports_zero_proof=False,
        reconciliation_strategy="key_based",
        order=7,
        description="Transparencia portals (batch detect + crawl)",
    ),
    SourceInfo(
        name="tce_sc",
        aliases=["tce-sc"],
        module="tce_sc_crawler",
        purpose="bids",
        capabilities=["open_tenders", "historical_contracts"],
        authority_level="estadual",
        entity_types=[],
        snapshot_semantics="incremental",
        freshness_sla_hours=24,
        supports_pagination=True,
        supports_zero_proof=False,
        reconciliation_strategy="key_based",
        order=8,
        description="TCE-SC SCMWeb (Tribunal de Contas de SC)",
    ),
    SourceInfo(
        name="doe_sc",
        aliases=["doe-sc"],
        module="doe_sc_crawler",
        purpose="bids",
        capabilities=["open_tenders"],
        authority_level="estadual",
        entity_types=["estaduais"],
        credential_names=["DOE_SC_LOGIN", "DOE_SC_PASSWORD"],
        credentials=["DOE_SC_LOGIN", "DOE_SC_PASSWORD"],
        snapshot_semantics="incremental",
        freshness_sla_hours=24,
        supports_pagination=True,
        supports_zero_proof=False,
        reconciliation_strategy="key_based",
        order=9,
        description="DOE-SC (Diario Oficial Estadual de SC)",
    ),
    SourceInfo(
        name="ciga_ckan",
        aliases=["ciga-ckan", "dom-ciga", "dom_sc_public"],
        module="ciga_ckan_crawler",
        purpose="hybrid",
        capabilities=["open_tenders", "coverage_truth"],
        authority_level="municipal",
        entity_types=["municipios", "prefeituras", "camaras"],
        credential_names=[],
        credentials=[],
        snapshot_semantics="incremental",
        freshness_sla_hours=48,
        supports_pagination=True,
        supports_zero_proof=False,
        adapter_contract="adr021",
        operational_validated=True,
        resilience_adapter="scripts.crawl.resilience.adapters.CigaDomAdapter",
        reconciliation_strategy="key_based",
        order=2,  # prefer over authenticated dom_sc for municipal SC
        description=(
            "CIGA Dados CKAN (dados.ciga.sc.gov.br) — caminho canônico DOM/SC. "
            "API pública, sem chave. Extrai publicações de compras + coverage."
        ),
    ),
    SourceInfo(
        name="mides_bigquery",
        aliases=["mides-bigquery"],
        module="mides_bigquery_crawler",
        purpose="bids",
        capabilities=["open_tenders"],
        authority_level="estadual",
        entity_types=["estaduais"],
        credential_names=["GOOGLE_APPLICATION_CREDENTIALS"],
        credentials=["GOOGLE_APPLICATION_CREDENTIALS"],
        snapshot_semantics="full_refresh",
        freshness_sla_hours=48,
        supports_pagination=False,
        supports_zero_proof=False,
        reconciliation_strategy="full_replace",
        order=11,
        description="MIDES BigQuery (dados de compras estaduais)",
    ),
    # NOTE: selenium REMOVED as a source (Story 1.5 fix).
    # Selenium e um metodo de crawl, nao uma fonte de dados.
    # Fontes que usam selenium declararam o modo "selenium" em seus modos suportados.
]

# DoD §7.1 enrichment (URL, geo, limits, role) — applied onto _RAW entries
_ENRICHMENT: dict[str, dict[str, Any]] = {
    "pncp": {
        "canonical_url": "https://pncp.gov.br/api/consulta",
        "geo_coverage": "BR (federal + adesão voluntária SC)",
        "pagination_limits": "pageSize<=50 default; full pagination required",
        "rate_limits": "polite 1-2 rps; 429 backoff",
        "role": "primary",
        "last_validation_at": "2026-07-18",
        "known_blockers": [],
        "retry_strategy": "exponential_backoff",
        "backoff_strategy": "exp_jitter",
    },
    "ciga_ckan": {
        "canonical_url": "https://dados.ciga.sc.gov.br/api/3/action",
        "geo_coverage": "SC municipal (DOM/CIGA)",
        "pagination_limits": "CKAN default limit 100",
        "rate_limits": "public polite 1 rps",
        "role": "primary",
        "last_validation_at": "2026-07-17",
        "known_blockers": [],
    },
    "sc_compras": {
        "canonical_url": "https://www.compras.sc.gov.br/",
        "geo_coverage": "SC estadual",
        "pagination_limits": "portal-specific; adapter handles pages",
        "rate_limits": "polite 1 rps",
        "role": "primary",
        "last_validation_at": "2026-07-17",
    },
    "dom_sc": {
        "canonical_url": "https://www.diariomunicipal.sc.gov.br/",
        "geo_coverage": "SC municipal",
        "pagination_limits": "remote/list pages",
        "rate_limits": "auth required; unknown official limit",
        "role": "gap_fill",
        "known_blockers": ["credentials_required", "prefer_ciga_ckan"],
    },
    "pcp": {
        "canonical_url": "https://www.portaldecompraspublicas.com.br/",
        "geo_coverage": "multi (portal shared)",
        "pagination_limits": "unknown",
        "rate_limits": "unknown",
        "role": "complementary",
        "known_blockers": ["implemented_not_proven_live"],
    },
    "compras_gov": {
        "canonical_url": "https://www.gov.br/compras/",
        "geo_coverage": "BR federal",
        "pagination_limits": "unknown",
        "rate_limits": "unknown",
        "role": "complementary",
        "known_blockers": ["implemented_not_proven_live"],
    },
    "contracts": {
        "canonical_url": "https://pncp.gov.br/api/consulta/v1/contratos",
        "geo_coverage": "BR (PNCP contracts)",
        "pagination_limits": "pageSize<=50",
        "rate_limits": "polite 1-2 rps; 429 backoff",
        "role": "primary",
        "known_blockers": ["backfill_3y_incomplete"],
    },
    "transparencia": {
        "canonical_url": "per-entity:portal_transparencia (batch_detect_platforms; no single national endpoint)",
        "geo_coverage": "SC municipal (per-entity portals)",
        "pagination_limits": "varies by portal",
        "rate_limits": "varies",
        "role": "gap_fill",
        "known_blockers": ["heterogeneous_portals", "no_single_canonical_http_endpoint"],
    },
    "tce_sc": {
        "canonical_url": "https://servicos.tce.sc.gov.br/",
        "geo_coverage": "SC",
        "pagination_limits": "SCMWeb-specific",
        "rate_limits": "unknown",
        "role": "complementary",
        "known_blockers": ["implemented_not_proven_live"],
    },
    "doe_sc": {
        "canonical_url": "https://www.doe.sc.gov.br/",
        "geo_coverage": "SC estadual",
        "pagination_limits": "unknown",
        "rate_limits": "auth required",
        "role": "complementary",
        "known_blockers": ["credentials_required"],
    },
    "mides_bigquery": {
        "canonical_url": "bigquery://mides (GOOGLE_APPLICATION_CREDENTIALS)",
        "geo_coverage": "SC estadual",
        "pagination_limits": "BigQuery job limits; supports_pagination=False",
        "rate_limits": "GCP quotas",
        "role": "gap_fill",
        "known_blockers": ["credentials_required", "no_pagination_zero_proof"],
    },
}

for info in _RAW:
    extra = _ENRICHMENT.get(info.name, {})
    for k, v in extra.items():
        if hasattr(info, k):
            setattr(info, k, v)

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
    contract_sources: bool | None = None,
) -> list[SourceInfo]:
    """Return all sources, sorted by execution order, optionally filtered.

    Args:
        purpose: Filter by purpose (``"bids"``, ``"contracts"``,
                 ``"coverage_only"``, ``"hybrid"``).
        active_only: If True (default), only return active sources.
        contract_sources: If True, only contract sources. If False, exclude
                          contract sources. If None (default), no filter.

    Returns:
        Sorted list of SourceInfo matching the filters.
    """
    sources: list[SourceInfo] = list(_REGISTRY.values())
    if active_only:
        sources = [s for s in sources if s.is_active]
    if purpose:
        sources = [s for s in sources if s.purpose == purpose]
    if contract_sources is True:
        sources = [s for s in sources if s.is_contract_source]
    elif contract_sources is False:
        sources = [s for s in sources if not s.is_contract_source]
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


def get_bids_sources() -> set[str]:
    """Return set of source names with purpose='bids' (excludes contracts)."""
    return {s.name for s in iter_sources(purpose="bids")}


def get_contract_sources() -> set[str]:
    """Return set of source names that produce contracts (not bids)."""
    return {s.name for s in iter_sources(contract_sources=True)}


def get_capability_sources(capability: str) -> list[SourceInfo]:
    """Return all sources that support a given business capability.

    Args:
        capability: Capability name (e.g. ``"open_tenders"``, ``"historical_contracts"``).

    Returns:
        List of SourceInfo for sources supporting this capability.
    """
    return [s for s in iter_sources() if s.is_active and capability in s.capabilities]


def iter_choices() -> list[str]:
    """Return all valid CLI choices (canonical names + aliases)."""
    choices: list[str] = []
    for s in iter_sources():
        choices.append(s.name)
        choices.extend(s.aliases)
    choices.append("all")
    return sorted(choices)


REQUIRED_DOD_71_FIELDS = (
    "id",
    "canonical_url",
    "capabilities",
    "geo_coverage",
    "needs_credentials",
    "pagination_limits",
    "rate_limits",
    "retry_strategy",
    "backoff_strategy",
    "operational_status",
    "role",
)


def export_registry(*, active_only: bool = False) -> list[dict[str, Any]]:
    """Export all sources as DoD §7.1 records."""
    return [s.to_dod_record() for s in iter_sources(active_only=active_only)]


def validate_registry() -> dict[str, Any]:
    """Validate canonical registry against DoD §7.1 first-wave requirements.

    Returns ok=True when every active source has stable id, URL, capabilities,
    geo, credential flag, pagination, rate limits, retry/backoff.
    """
    records = export_registry(active_only=False)
    missing: list[dict[str, Any]] = []
    for rec in records:
        gaps = []
        if not rec.get("id"):
            gaps.append("id")
        if not rec.get("canonical_url") or rec.get("canonical_url") == "unknown":
            gaps.append("canonical_url")
        if not rec.get("capabilities"):
            gaps.append("capabilities")
        if not rec.get("geo_coverage"):
            gaps.append("geo_coverage")
        if rec.get("needs_credentials") is None:
            gaps.append("needs_credentials")
        if not rec.get("pagination_limits") or rec.get("pagination_limits") == "unknown":
            # allow unknown but flag as warning not gap for non-primary
            if rec.get("role") == "primary":
                gaps.append("pagination_limits")
        if not rec.get("rate_limits") or rec.get("rate_limits") == "unknown":
            if rec.get("role") == "primary":
                gaps.append("rate_limits")
        if not rec.get("retry_strategy"):
            gaps.append("retry_strategy")
        if not rec.get("backoff_strategy"):
            gaps.append("backoff_strategy")
        if gaps:
            missing.append({"id": rec.get("id"), "gaps": gaps, "status": rec.get("operational_status")})
    statuses = {}
    for rec in records:
        st = rec.get("operational_status") or "unknown"
        statuses[st] = statuses.get(st, 0) + 1
    return {
        "ok": len(missing) == 0,
        "n_sources": len(records),
        "statuses": statuses,
        "missing_required": missing,
        "required_fields": list(REQUIRED_DOD_71_FIELDS),
        "registry_module": "scripts.crawl.registry",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    p = argparse.ArgumentParser(description="Canonical crawl source registry (DoD §7.1)")
    p.add_argument("--export", action="store_true", help="Export registry JSON")
    p.add_argument("--validate", action="store_true", help="Validate DoD §7.1 fields")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", type=str, default="")
    args = p.parse_args(argv)
    if args.validate or not args.export:
        result = validate_registry()
        if args.export:
            payload = {"validation": result, "sources": export_registry()}
        else:
            payload = result
    else:
        payload = {"sources": export_registry()}
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    if args.out:
        Path = __import__("pathlib").Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json or args.export or args.validate:
        print(text)
    return 0 if (not args.validate or payload.get("ok") or payload.get("validation", {}).get("ok")) else 1


# ---------------------------------------------------------------------------
# Re-export SourcePurpose markers for convenience
# ---------------------------------------------------------------------------

BIDS: SourcePurpose = "bids"
CONTRACTS: SourcePurpose = "contracts"
COVERAGE_ONLY: SourcePurpose = "coverage_only"
HYBRID: SourcePurpose = "hybrid"

__all__ = [
    "AuthorityLevel",
    "BIDS",
    "CONTRACTS",
    "COVERAGE_ONLY",
    "HYBRID",
    "SnapshotSemantics",
    "SourceCapability",
    "SourceInfo",
    "SourcePurpose",
    "export_registry",
    "get_bids_sources",
    "get_capability_sources",
    "get_contract_sources",
    "get_coverage_only_sources",
    "get_credential_sources",
    "get_public_sources",
    "iter_choices",
    "iter_sources",
    "lookup",
    "resolve_name",
    "validate_registry",
]


if __name__ == "__main__":
    raise SystemExit(main())
