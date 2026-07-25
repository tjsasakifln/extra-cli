"""Constants, allowlists and sheet classification labels."""

from __future__ import annotations

from typing import Final

CAMPAIGN_ID: Final = "ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01"
EXPECTED_BRANCH: Final = "campaign/engineering-budget-composition-bdi-audit-01"
LOCK_RELPATH: Final = (
    "artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01/worktree-lock.json"
)
ISOLATION_RELPATH: Final = (
    "artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01/isolation.json"
)

ALLOWED_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "scripts/budget_audit/",
    "tests/budget_audit/",
    "specs/008-engineering-budget-composition-bdi-audit/",
    "artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01/",
    "integration-handoff/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01/",
    "docs/architecture/adr/ADR-032-budget-audit-evidence-model.md",
)

# Exact files also allowed
ALLOWED_EXACT: Final[frozenset[str]] = frozenset(
    {
        "docs/architecture/adr/ADR-032-budget-audit-evidence-model.md",
    }
)

DENYLIST_PREFIXES: Final[tuple[str, ...]] = (
    "DOD.md",
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "Makefile",
    ".github/workflows/",
    "docs/DEVELOPMENT.md",
    "docs/canonical-entry-points.yaml",
    "docs/architecture/adr/INDEX.md",
    "config/client_profiles/extra.yaml",
    "scripts/workspace/",
    "scripts/ops/",
    "scripts/linkage/",
    "scripts/national_intel/",
    "scripts/edital_case/",
    "scripts/lib/bid_simulator.py",
    "db/",
    "deploy/",
    "specs/004-extra-live-consulting-pack/",
    "specs/006-canonical-entity-linkage/",
    "specs/007-edital-technical-triage/",
    "artifacts/campaigns/EXTRA-LIVE-CONSULTING-PACK-01/",
    "artifacts/campaigns/CANONICAL-ENTITY-LINKAGE-01/",
    "artifacts/campaigns/EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01/",
    "artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/",
    "artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/",
)

FORBIDDEN_ENV_KEYS: Final[tuple[str, ...]] = (
    "DATABASE_URL",
    "LOCAL_DATALAKE_DSN",
    "PROD_DSN",
    "PGPASSWORD",
    "POSTGRES_PASSWORD",
    "EXTRA_PROD_DSN",
)

FORBIDDEN_PATH_MARKERS: Final[tuple[str, ...]] = (
    "/opt/extra-consultoria",
    "ec-prod",
)

SHEET_TYPES: Final[tuple[str, ...]] = (
    "BUDGET_SUMMARY",
    "BUDGET_ANALYTICAL",
    "COMPOSITIONS",
    "INPUTS",
    "LABOR",
    "EQUIPMENT",
    "SOCIAL_CHARGES",
    "BDI",
    "SCHEDULE",
    "ABC_CURVE",
    "QUANTITY_MEMORY",
    "PROPOSAL",
    "REFERENCE_TABLE",
    "AUXILIARY",
    "UNKNOWN",
)

FORMULA_STATUSES: Final[tuple[str, ...]] = (
    "VALID",
    "MISSING_CACHE",
    "BROKEN_REFERENCE",
    "EXTERNAL_REFERENCE",
    "CIRCULAR_POSSIBLE",
    "UNSUPPORTED",
    "INCONSISTENT_WITH_VALUE",
    "NOT_EVALUATED",
)

ARITHMETIC_STATUSES: Final[tuple[str, ...]] = (
    "PASS",
    "ROUNDING_DIFFERENCE",
    "MATERIAL_DIFFERENCE",
    "NOT_EVALUATED",
    "SOURCE_ERROR",
)

GLOBAL_EXIT_STATUSES: Final[tuple[str, ...]] = ("PASS", "BLOCKED", "FAIL")

SENTINELS: Final[tuple[str, ...]] = (
    "NOT_AVAILABLE",
    "NOT_APPLICABLE",
    "NOT_EVALUATED",
    "SOURCE_ERROR",
)

DEFAULT_MATERIALITY: Final[dict[str, float]] = {
    "absolute_tolerance_brl": 0.01,
    "relative_tolerance_pct": 0.05,
    "rounding_tolerance": 0.005,
    "materiality_brl": 100.0,
    "materiality_pct_of_total": 0.1,
}

# Safety limits
MAX_ZIP_MEMBERS: Final = 500
MAX_ZIP_UNCOMPRESSED_BYTES: Final = 200 * 1024 * 1024  # 200 MB
MAX_SINGLE_FILE_BYTES: Final = 100 * 1024 * 1024  # 100 MB
MAX_SHEETS: Final = 200
MAX_CELLS_PER_SHEET: Final = 500_000
MAX_TOTAL_CELLS: Final = 2_000_000

UNITS_DICT_VERSION: Final = "1.0.0"
CLASSIFICATION_RULE_VERSION: Final = "1.0.0"

SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".xlsx", ".xlsm", ".csv", ".ods", ".pdf", ".zip"}
)

CONVERSION_REQUIRED_EXTENSIONS: Final[frozenset[str]] = frozenset({".xls"})
