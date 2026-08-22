"""Canonical versions, thresholds and reason codes for the CONFENGE dossier engine.

Grain is the supplier company (``cnpj14``), not a contract. The dossier composes
already-canonical DataLake reads into the deliverable behind the paid offer
``CFG-DIAG-EXP-v1`` (Diagnostico B2G de Expansao) and into a de-identified public
projection consumed by web-cfg.

No claim is invented here. Every section carries provenance, an observation
timestamp and an explicit state; missing evidence is UNKNOWN, never zero.
"""

from __future__ import annotations

SCHEMA = "confenge-dossier/1.0"
PUBLIC_SCHEMA = "public-read-confenge-dossier/1.0"
CONTRACT_VERSION = "v1.0.0"
METHOD_VERSION = "confenge-dossier-compose/1.0"
POLICY_VERSION = "confenge-dossier-policy/1.0"
GRAIN = "cnpj14"

PRODUCER_EXTRA_CLI = "extra-cli"
CONSUMER_WEB_CFG = "web-cfg/contract-analysis"
CONSUMER_WARMBLY = "warmbly/confenge-cohort"

OFFER_ID = "CFG-DIAG-EXP-v1"
OFFER_CATALOG = "CFG-OFFER-CATALOG-v1"

CATALOG_FIXTURE = "fixture"
CATALOG_OFFICIAL_LIVE = "official_live"
CATALOG_MODES = (CATALOG_FIXTURE, CATALOG_OFFICIAL_LIVE)

DATA_READY = "DATA_READY"
DATA_HOLD = "DATA_HOLD"
DATA_REJECT = "DATA_REJECT"
DATA_STATES = (DATA_READY, DATA_HOLD, DATA_REJECT)
# Worst-wins ordering when folding section states into the document state.
DATA_STATE_RANK = {DATA_READY: 0, DATA_HOLD: 1, DATA_REJECT: 2}

UNKNOWN = "UNKNOWN"

SECTION_IDENTITY = "identity"
SECTION_BUYER_MAP = "buyer_map"
SECTION_COMPETITORS = "competitors"
SECTION_PRICE_PANEL = "price_panel"
SECTION_EXPIRING = "expiring_contracts"
SECTION_OPPORTUNITIES = "open_opportunities"
SECTION_ORDER = (
    SECTION_IDENTITY,
    SECTION_BUYER_MAP,
    SECTION_COMPETITORS,
    SECTION_PRICE_PANEL,
    SECTION_EXPIRING,
    SECTION_OPPORTUNITIES,
)
# Sections the paid offer promises. A REJECT on any of these rejects the dossier.
REQUIRED_SECTIONS = (SECTION_IDENTITY, SECTION_BUYER_MAP, SECTION_PRICE_PANEL)

# Offer scope: "15 concorrentes".
COMPETITOR_LIMIT = 15
# Offer scope: "contratos a vencer". One year ahead is the planning horizon.
EXPIRING_WINDOW_DAYS = 365
# Offer scope: "editais triados".
OPPORTUNITY_LIMIT = 25
BUYER_LIMIT = 50
# A contract needs a signed/started date to have a reajuste anniversary.
ANNIVERSARY_MIN_MONTHS = 12

MIN_CONTRACTS_READY = 3
MIN_CONTRACTS_HOLD = 1
MIN_BUYERS_READY = 2

REASON_IDENTITY_NOT_FOUND = "identity_not_found"
REASON_NO_CONTRACTS = "no_canonical_contracts"
REASON_INSUFFICIENT_CONTRACTS = "insufficient_contracts"
REASON_INSUFFICIENT_BUYERS = "insufficient_buyers"
REASON_NO_COMPETITORS = "no_competitor_sample"
REASON_NO_PRICE_REFERENCE = "no_price_reference"
REASON_LOW_PRECISION_BUCKET = "category_bucket_low_precision"
REASON_BUYER_LIST_TRUNCATED = "buyer_list_truncated_for_display"
REASON_PANEL_OUT_OF_RANGE = "focal_outside_panel_range"
REASON_NO_PRIMARY_CATEGORY = "primary_category_undetermined"
REASON_NO_EXPIRING = "no_expiring_contracts_in_window"
REASON_NO_OPPORTUNITIES = "no_open_opportunities_for_buyers"
REASON_VALUE_UNKNOWN = "value_unknown_excluded_from_denominator"
REASON_DSN_UNAVAILABLE = "dsn_unavailable"
REASON_TABLE_MISSING = "official_table_missing"
REASON_FIXTURE_NOT_LIVE = "fixture_not_official_live"
REASON_FIXTURE_LABELED_LIVE = "fixture_labeled_official_live"
REASON_INVALID_CNPJ = "invalid_cnpj14"
REASON_STALE_WATERMARK = "source_watermark_stale"

HARD_REJECT_REASONS = frozenset(
    {
        REASON_IDENTITY_NOT_FOUND,
        REASON_NO_CONTRACTS,
        REASON_INVALID_CNPJ,
        REASON_FIXTURE_LABELED_LIVE,
        REASON_DSN_UNAVAILABLE,
    }
)

# Findings are facts plus the question they open. They never assert a right,
# an imbalance, a loss, or that an adjustment is due.
FINDING_ANNIVERSARY = "contract_anniversary_reached"
FINDING_EXPIRING_WINDOW = "contract_ending_within_window"
FINDING_BUYER_CONCENTRATION = "buyer_concentration_high"
FINDING_PRICE_POSITION = "value_position_in_category"
FINDING_OPPORTUNITY_SAME_BUYER = "open_opportunity_from_known_buyer"
FINDING_LONG_HORIZON = "contract_horizon_beyond_window"

FINDING_ORDER = (
    FINDING_ANNIVERSARY,
    FINDING_EXPIRING_WINDOW,
    FINDING_BUYER_CONCENTRATION,
    FINDING_PRICE_POSITION,
    FINDING_OPPORTUNITY_SAME_BUYER,
    FINDING_LONG_HORIZON,
)

# HHI over this threshold is reported as concentration. Standard antitrust band.
HHI_CONCENTRATION_THRESHOLD = 0.25

# The category ladder is coarse: a road-maintenance contract and a mop purchase
# both land in FACILITIES. When the focal median sits more than this many times
# outside the panel's interquartile band, the panel is not a comparable
# reference and no percentile position is claimed.
PANEL_OUT_OF_RANGE_FACTOR = 10
POSITION_OUT_OF_PANEL_RANGE = "OUT_OF_PANEL_RANGE"

# The TI rung of the category ladder matches the bare substring "ti" and sits
# above SAUDE and ALIMENTACAO, so it swallows "domesticos", "didaticos" and a
# slice of health contracts: 84% of that bucket carries no TI keyword. A panel
# built from household goods cannot price anything. Positions are not claimed
# for these buckets until the upstream view is corrected.
LOW_PRECISION_CATEGORIES = frozenset({"TI"})
POSITION_LOW_PRECISION_BUCKET = "LOW_PRECISION_BUCKET"

# Reused verbatim from contract_comparables: the dossier is bound by the same
# no-claim policy as every other consumer-bound artifact in this repository.
FORBIDDEN_CLAIM_TOKENS = (
    "sobrepreco",
    "sobrepreço",
    "overprice",
    "fraude",
    "fraud",
    "irregularidade",
    "irregularity",
    "irregular",
    "caro",
    "barato",
    "custo/km",
    "custo/m2",
    "custo/m²",
    "custo por km",
    "custo por m",
    "preco unitario",
    "preço unitário",
    "ranking nacional",
    "market share",
    "reajuste devido",
    "valor devido",
    "prejuizo",
    "prejuízo",
    "direito adquirido",
)

FORBIDDEN_METRIC_KEYS = frozenset(
    {
        "cost_per_km",
        "cost_per_m2",
        "custo_por_km",
        "custo_por_m2",
        "unit_price",
        "preco_unitario",
        "sobrepreco",
        "reajuste_devido",
        "valor_devido",
    }
)

# Fields removed from the public projection. The prospect is not the subject of
# a public page; public bodies and their published contracts are.
PUBLIC_REDACTED_FIELDS = frozenset(
    {
        "cnpj14",
        "cnpj_raiz",
        "razao_social",
        "nome_fantasia",
        "supplier_cnpj",
        "supplier_nome",
        "fornecedor_cnpj",
        "fornecedor_nome",
        "municipio",
    }
)
