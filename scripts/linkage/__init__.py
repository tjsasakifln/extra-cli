"""Canonical entity linkage — identity resolution and auditable relations.

Campaign: CANONICAL-ENTITY-LINKAGE-01

Layers:
  1. Official strong keys (CNPJ14/CNPJ8/CPF/IBGE/PNCP)
  2. Deterministic composite (key + geography + name)
  3. Heuristic reviewable (score + reason codes + review queue)

Never auto-merge conflicting strong identifiers.
Never claim unobserved tender participation.
"""

from __future__ import annotations

RULE_VERSION = "linkage-v1"

__all__ = ["RULE_VERSION"]
