"""#381 — versioned ICP universe and reachability denominator.

extra-cli owns ICP membership, canonical account identity, evidence and
pre-contact reachability. Warmbly owns CONTACTED and later outcomes; those
counts are consumed as facts, never re-derived. UNKNOWN stays visible.
No invented TAM.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

SCHEMA_VERSION = "icp-denominator/1.0"
RULES_VERSION = "icp.rules.v1"

STAGES = (
    "ICP_ACCOUNT",
    "DECISION_UNIT_KNOWN",
    "ACTIONABLE_ROUTE",
    "CONTACTED",
    "QUALIFIED_CONVERSATION",
    "MEETING",
    "PROPOSAL",
    "CLIENT",
    "EXPANDED_CLIENT",
)

Stage = Literal[
    "ICP_ACCOUNT",
    "DECISION_UNIT_KNOWN",
    "ACTIONABLE_ROUTE",
    "CONTACTED",
    "QUALIFIED_CONVERSATION",
    "MEETING",
    "PROPOSAL",
    "CLIENT",
    "EXPANDED_CLIENT",
    "UNKNOWN",
]


class PenetrationError(ValueError):
    """Snapshot cannot be published."""


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IcpRules:
    version: str
    required_uf: frozenset[str]
    require_public_portfolio: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "required_uf": sorted(self.required_uf),
            "require_public_portfolio": self.require_public_portfolio,
        }


DEFAULT_RULES = IcpRules(version=RULES_VERSION, required_uf=frozenset({"SC"}))


@dataclass(frozen=True)
class AccountFact:
    account_id: str
    uf: str | None
    has_public_portfolio: bool
    decision_unit_known: bool
    actionable_route: bool
    warmbly_stage: str | None
    evidence: tuple[str, ...]


def classify_stage(fact: AccountFact, rules: IcpRules = DEFAULT_RULES) -> Stage:
    """Strict evidence rule per stage. Missing evidence is UNKNOWN, not a skip."""
    if not fact.account_id:
        raise PenetrationError("account_id required")
    if not fact.evidence:
        return "UNKNOWN"
    uf_ok = bool(fact.uf) and fact.uf.upper() in rules.required_uf
    if not uf_ok or (rules.require_public_portfolio and not fact.has_public_portfolio):
        return "UNKNOWN"
    # Warmbly facts are authoritative from CONTACTED onward.
    warmbly = (fact.warmbly_stage or "").upper() or None
    if warmbly in STAGES and STAGES.index(warmbly) >= STAGES.index("CONTACTED"):
        return warmbly  # type: ignore[return-value]
    if fact.actionable_route:
        return "ACTIONABLE_ROUTE"
    if fact.decision_unit_known:
        return "DECISION_UNIT_KNOWN"
    return "ICP_ACCOUNT"


def snapshot_penetration(
    facts: tuple[AccountFact, ...],
    *,
    as_of: str,
    rules: IcpRules = DEFAULT_RULES,
) -> dict[str, Any]:
    """Reproducible denominator + observed stage counts. No invented TAM."""
    if not as_of:
        raise PenetrationError("as_of is required")
    seen: set[str] = set()
    by_stage: dict[str, int] = {stage: 0 for stage in (*STAGES, "UNKNOWN")}
    uncaptured: list[str] = []
    for fact in facts:
        if fact.account_id in seen:
            raise PenetrationError(f"duplicate_account:{fact.account_id}")
        seen.add(fact.account_id)
        stage = classify_stage(fact, rules)
        by_stage[stage] += 1
        if stage in {"UNKNOWN", "ICP_ACCOUNT"}:
            uncaptured.append(fact.account_id)

    icp = sum(by_stage[s] for s in STAGES)
    reachable = (
        by_stage["ACTIONABLE_ROUTE"]
        + by_stage["CONTACTED"]
        + by_stage["QUALIFIED_CONVERSATION"]
        + by_stage["MEETING"]
        + by_stage["PROPOSAL"]
        + by_stage["CLIENT"]
        + by_stage["EXPANDED_CLIENT"]
    )
    if icp + by_stage["UNKNOWN"] != len(facts):
        raise PenetrationError("stage_counts_do_not_close")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "rules_version": rules.version,
        "as_of": as_of,
        "denominator": {
            "icp_accounts": icp,
            "rules": rules.as_dict(),
            "invented_tam": False,
        },
        "counts": {
            "X_icp": icp,
            "Y_reachable": reachable,
            "Z_contacted": by_stage["CONTACTED"],
            "N_conversations": by_stage["QUALIFIED_CONVERSATION"],
            "P_proposals": by_stage["PROPOSAL"],
            "C_clients": by_stage["CLIENT"] + by_stage["EXPANDED_CLIENT"],
            "UNKNOWN": by_stage["UNKNOWN"],
        },
        "by_stage": by_stage,
        "uncaptured_account_ids": uncaptured,
        "warmbly_authoritative_from": "CONTACTED",
    }
    payload["snapshot_hash"] = sha256_payload(payload)
    return payload
