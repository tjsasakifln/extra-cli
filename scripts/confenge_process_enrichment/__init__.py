"""Process-first commercial enrichment for CONFENGE.

Cascade: company → contracts → procurement → administrative process →
public documents → company-authored-first extraction → contact graph →
EMAIL_SEND_READY / REFERRAL_ROUTE / process-exhausted states.

extra-cli is the source of truth; Warmbly only receives commercially usable
contacts with provenance (never raw process PDFs or unnecessary PII).
"""

from __future__ import annotations

from scripts.confenge_process_enrichment.models import (
    EpistemicClass,
    InvestigationState,
    TerminalState,
)
from scripts.confenge_process_enrichment.pipeline import ProcessFirstEnricher, enrich_account
from scripts.confenge_process_enrichment.states import can_declare_no_contact

__all__ = [
    "EpistemicClass",
    "InvestigationState",
    "ProcessFirstEnricher",
    "TerminalState",
    "can_declare_no_contact",
    "enrich_account",
]

__version__ = "1.0.0"
