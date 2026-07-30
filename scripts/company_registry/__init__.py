"""Official RFB CNPJ company registry mirror for CONFENGE commercial enrichment.

Authority: Receita Federal public open-data CNPJ release (primary).
Redistributors may fill selective mode only when labeled and never inflate
bulk-completeness claims.

This package does NOT replace scripts.commercial_leads — it feeds
supplier_registry with RFB-authority rows and provides typed lookup + coverage.
"""

from __future__ import annotations

from scripts.company_registry.models import (
    MATCH_STATUSES,
    OfficialCompanyRecord,
    OfficialMatchStatus,
    ReleaseStatus,
)
from scripts.company_registry.normalization import (
    is_valid_cnpj14,
    normalize_cnpj14,
    normalize_cnpj_root,
)

__all__ = [
    "MATCH_STATUSES",
    "OfficialCompanyRecord",
    "OfficialMatchStatus",
    "ReleaseStatus",
    "is_valid_cnpj14",
    "normalize_cnpj14",
    "normalize_cnpj_root",
]

SCHEMA_VERSION = "company-registry-v1"
SOURCE_AUTHORITY = "RECEITA_FEDERAL"
DEFAULT_SOURCE_LABEL = "rfb_public_cadastral"
