"""CONFENGE commercial leads queue — observable signals only, never purchase propensity."""

from __future__ import annotations

CAMPAIGN_ID = "CONFENGE-COMMERCIAL-READY-01"
MODULE_VERSION = "1.1.0"

COMMERCIAL_STATES = (
    "NEW",
    "REVIEWED",
    "QUALIFIED",
    "DISQUALIFIED",
    "CONTACTED",
    "REPLIED",
    "MEETING",
    "PROPOSAL",
    "WON",
    "LOST",
    "DO_NOT_CONTACT",
)

FORBIDDEN_LANGUAGE = (
    "propensão",
    "propensao",
    "probabilidade de compra",
    "intenção de compra",
    "intencao de compra",
    "empresa interessada",
    "lead quente",
    "chance de conversão",
    "chance de conversao",
    "necessidade comprovada de consultoria",
)

__all__ = [
    "CAMPAIGN_ID",
    "MODULE_VERSION",
    "COMMERCIAL_STATES",
    "FORBIDDEN_LANGUAGE",
]
