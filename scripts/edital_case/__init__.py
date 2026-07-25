"""Edital technical triage case pack — isolated campaign package.

Campaign: EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01

Immutable file-based case store with content-addressed objects, evidence-linked
checklist analysis, and fail-closed recommendation (GO/REVIEW/NO_GO).

Does NOT touch PostgreSQL, VPS, soak, or hot shared files.
"""

from __future__ import annotations

__version__ = "0.1.0"
CAMPAIGN_ID = "EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01"
CAMPAIGN_BRANCH = "campaign/edital-technical-triage-case-pack-01"
DEFAULT_CAMPAIGN_DIR = "artifacts/campaigns/EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01"

DISCLAIMER = (
    "AVISO: este case pack é triagem técnica operacional e NÃO substitui "
    "análise jurídica, responsabilidade técnica, ART/RRT, parecer formal "
    "nem decisão comercial humana. Validação humana obrigatória."
)
