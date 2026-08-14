"""Decision-Unit Intelligence + Reachability for CONFENGE B2G outreach.

This package answers, per account and per CONFENGE offer:

    who probably participates in the buying decision,
    which real people match those roles,
    and by which defensible routes we can reach that unit now.

It does **not** treat “named email explicitly published” as the product.
Email is one reachability strategy. There is no AUTO_SEND.
"""

from __future__ import annotations

POLICY_VERSION = "dui.policy.v1"
PROVIDER_VERSION = "dui.providers.v1"
SCHEMA_ID = "confenge.decision_unit_intelligence.v1"
SCHEMA_VERSION = "1.0.0"

__all__ = [
    "POLICY_VERSION",
    "PROVIDER_VERSION",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
]
