"""CONFENGE public business contact resolution.

Resolve legitimate commercial contacts for outreach without inventing identity.
Produces versioned candidates (``confenge-contact-candidates-v1``) with provenance,
verification status, service-aware ranking, and WhatsApp consent defaults.

Reuses official company registry (RFB) when available. Optional web search sits
behind a provider interface and is disabled by default in tests.
"""

from __future__ import annotations

SCHEMA_ID = "confenge-contact-candidates-v1"
SCHEMA_VERSION = "1.0.0"
PACKAGE_VERSION = "1.0.0"

__all__ = [
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "PACKAGE_VERSION",
]
