"""Explicit public-field allowlist and forbidden-field denylist.

Anything not on the allowlist is stripped before export. Forbidden fields
are also checked post-serialization so accidental nesting fails closed.
"""

from __future__ import annotations

# Fields that must never appear in any public JSON artifact (case-insensitive
# key match after normalizing snake/camel).
FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "score_total",
        "score",
        "priority",
        "rank",
        "rank_position",
        "suggested_offer",
        "next_human_step",
        "commercial_state",
        "human_decision",
        "human_notes",
        "reviewer",
        "reviewer_classification",
        "reviewer_reason",
        "model_classification",
        "do_not_contact",
        "authorization",
        "contato",
        "telefone",
        "email",
        "whatsapp",
        "phone",
        "pipeline_state",
        "commercial_ledger",
        "outreach",
        "kit",
        "label_humano",
        "human_label",
        "top20",
        "top_20",
        "top10",
        "top_10",
        "cnpj14",  # supplier identity from commercial ranking
        "razao_social_fornecedor_icp",
        "signals_fired",
        "signal_ids",
        "offer_scores",
        "selected_offer",
        "score_decomposition",
        "supplier_sector_confidence",
        "agreement",
        "allowed_labels",
        "data_revisao",
        "revisor",
        "evidence_checked",
    }
)

# Public allowlist by table/artifact type (top-level keys permitted).
MANIFEST_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "generated_at",
        "source_run_id",
        "source_commit_sha",
        "dataset_hash",
        "sources",
        "counts",
        "denominators",
        "freshness",
        "limitations",
        "checksums",
        "horizon",
        "methodology_notes",
    }
)

ARCHETYPE_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "slug",
        "label",
        "description",
        "object_patterns_public",
        "ufs_observed",
        "value_band",
        "modalities_observed",
        "buyer_types_observed",
        "confenge_service_slugs",
        "evidence_contract_count",
        "evidence_buyer_count",
        "methodology",
        "limitations",
    }
)

MARKET_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "slug",
        "archetype_id",
        "segment",
        "region",
        "region_label",
        "period_start",
        "period_end",
        "contract_count",
        "buyer_count",
        "supplier_count",
        "total_value",
        "median_value",
        "p25_value",
        "p75_value",
        "top_buyers",
        "top_objects",
        "value_by_year",
        "modalities",
        "open_opportunity_count",
        "sources",
        "limitations",
        "interpretation_hooks",
    }
)

AGENCY_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "slug",
        "agency_name",
        "agency_cnpj8",
        "uf",
        "municipio",
        "period_start",
        "period_end",
        "contract_count",
        "total_value",
        "median_value",
        "p25_value",
        "p75_value",
        "archetype_mix",
        "top_objects",
        "modalities",
        "seasonality",
        "supplier_count",
        "open_opportunities",
        "official_channels",
        "sources",
        "limitations",
        "practical_notes",
    }
)

PRICE_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "slug",
        "object_label",
        "object_pattern",
        "region",
        "region_label",
        "period_start",
        "period_end",
        "observation_count",
        "median_value",
        "p25_value",
        "p75_value",
        "min_value",
        "max_value",
        "dispersion_iqr",
        "inclusion_criteria",
        "exclusion_criteria",
        "public_examples",
        "sources",
        "limitations",
        "warning",
    }
)

COMPETITION_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "slug",
        "segment",
        "region",
        "region_label",
        "period_start",
        "period_end",
        "supplier_count",
        "contract_count",
        "observed_suppliers",
        "concentration_top3_share",
        "agencies_with_activity",
        "value_bands",
        "recent_changes",
        "sources",
        "limitations",
        "language_note",
    }
)

OPPORTUNITY_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "slug",
        "segment",
        "region",
        "region_label",
        "as_of",
        "open_count",
        "items",
        "historical_count",
        "sources",
        "limitations",
        "related_market_slug",
    }
)

PROBLEM_SERVICE_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "slug",
        "theme",
        "problem_label",
        "observed_pattern",
        "evidence_count",
        "related_archetypes",
        "confenge_service_slug",
        "technical_guide_paths",
        "sources",
        "official_references",
        "limitations",
    }
)

# Nested public object keys
PUBLIC_BUYER_REF_KEYS: frozenset[str] = frozenset(
    {"name", "cnpj8", "uf", "municipio", "contract_count", "total_value"}
)
PUBLIC_OBJECT_REF_KEYS: frozenset[str] = frozenset(
    {"label", "count", "median_value", "example_objeto"}
)
PUBLIC_SUPPLIER_OBS_KEYS: frozenset[str] = frozenset(
    {
        "display_name",
        "contract_count",
        "total_value",
        "agencies_count",
        "value_band",
    }
)
PUBLIC_OPP_ITEM_KEYS: frozenset[str] = frozenset(
    {
        "pncp_id",
        "objeto",
        "valor_estimado",
        "modalidade",
        "uf",
        "municipio",
        "orgao_nome",
        "data_encerramento",
        "link_pncp",
        "source",
    }
)
PUBLIC_EXAMPLE_KEYS: frozenset[str] = frozenset(
    {"objeto", "valor", "uf", "municipio", "orgao_nome", "data_publicacao", "source"}
)
