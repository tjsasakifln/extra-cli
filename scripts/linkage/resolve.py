"""Layered match decisions — pure functions (no DB).

Classifications:
  exact | deterministic_composite | heuristic_reviewable | ambiguous | unresolved
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from scripts.linkage import RULE_VERSION
from scripts.linkage.keys import (
    StrongKeys,
    conflicting_strong_ids,
    extract_organ_keys,
    extract_person_keys,
    normalize_name,
    organ_canonical_key,
    supplier_canonical_key,
)

Classification = Literal[
    "exact",
    "deterministic_composite",
    "heuristic_reviewable",
    "ambiguous",
    "unresolved",
]
ClaimLevel = Literal["fact", "similarity", "inference", "none"]

# Automatic accept only for exact/deterministic with high score
AUTO_ACCEPT_MIN_SCORE = 0.99
HEURISTIC_REVIEW_MIN = 0.75


@dataclass(frozen=True)
class LinkDecision:
    classification: Classification
    score: float
    reason_codes: tuple[str, ...]
    claim_level: ClaimLevel
    target_key: str | None
    rule_version: str = RULE_VERSION
    non_claims: tuple[str, ...] = ()
    source_record_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "score": self.score,
            "reason_codes": list(self.reason_codes),
            "claim_level": self.claim_level,
            "target_key": self.target_key,
            "rule_version": self.rule_version,
            "non_claims": list(self.non_claims),
            "source_record_ids": list(self.source_record_ids),
            "auto_accept": self.auto_accept,
        }

    @property
    def auto_accept(self) -> bool:
        return (
            self.classification in ("exact", "deterministic_composite")
            and self.score >= AUTO_ACCEPT_MIN_SCORE
            and self.target_key is not None
        )


def decide_opportunity_organ(
    opp_cnpj: str | None,
    opp_name: str | None,
    *,
    opp_ibge: str | None = None,
    pncp_control: str | None = None,
    source_record_id: str | None = None,
    candidate_keys: StrongKeys | None = None,
) -> LinkDecision:
    """Resolve open opportunity → organ golden key."""
    keys = extract_organ_keys(opp_cnpj, opp_name, opp_ibge, pncp_control)
    src = (source_record_id,) if source_record_id else ()

    if candidate_keys is not None:
        conflicts = conflicting_strong_ids(keys, candidate_keys)
        if any(c.startswith("conflict_") for c in conflicts):
            return LinkDecision(
                classification="ambiguous",
                score=0.0,
                reason_codes=tuple(conflicts) + ("refuse_strong_id_merge",),
                claim_level="none",
                target_key=None,
                source_record_ids=src,
            )

    if keys.cnpj14:
        ck = organ_canonical_key(keys)
        return LinkDecision(
            classification="exact",
            score=1.0,
            reason_codes=("exact_cnpj14",),
            claim_level="fact",
            target_key=ck,
            source_record_ids=src,
        )

    if keys.cnpj8 and keys.normalized_name:
        ck = organ_canonical_key(keys)
        return LinkDecision(
            classification="deterministic_composite",
            score=0.995,
            reason_codes=("deterministic_cnpj8_plus_name",),
            claim_level="fact",
            target_key=ck,
            source_record_ids=src,
        )

    if keys.cnpj8:
        # CNPJ8 without a distinctive name is weak for golden identity:
        # keep deterministic key for joins but do NOT auto-accept as fact merge.
        ck = organ_canonical_key(keys)
        return LinkDecision(
            classification="heuristic_reviewable",
            score=0.9,
            reason_codes=("cnpj8_only_requires_review", "weak_without_name"),
            claim_level="similarity",
            target_key=ck,
            source_record_ids=src,
            non_claims=("not_auto_merged_on_cnpj8_alone",),
        )

    if keys.normalized_name and keys.ibge7:
        # Name+IBGE without tax id is reviewable only — never auto golden merge
        return LinkDecision(
            classification="heuristic_reviewable",
            score=0.8,
            reason_codes=("heuristic_name_ibge_no_tax_id", "requires_review"),
            claim_level="similarity",
            target_key=None,
            source_record_ids=src,
            non_claims=("no_tax_id_merge",),
        )

    if keys.normalized_name:
        return LinkDecision(
            classification="unresolved",
            score=0.0,
            reason_codes=("name_only_insufficient",),
            claim_level="none",
            target_key=None,
            source_record_ids=src,
        )

    return LinkDecision(
        classification="unresolved",
        score=0.0,
        reason_codes=("missing_organ_identifiers",),
        claim_level="none",
        target_key=None,
        source_record_ids=src,
    )


def decide_contract_to_opportunity(
    *,
    opp_organ_cnpj: str | None,
    opp_organ_name: str | None,
    opp_objeto: str | None,
    opp_uf: str | None,
    contract_organ_cnpj: str | None,
    contract_organ_name: str | None,
    contract_objeto: str | None,
    contract_uf: str | None,
    contract_id: str | None = None,
    supplier_cnpj: str | None = None,
) -> LinkDecision:
    """Link historical contract to an open opportunity (relatedness, not participation)."""
    src = tuple(x for x in (contract_id, supplier_cnpj) if x)
    non_claims = (
        "not_observed_participant_of_open_tender",
        "similarity_not_participation",
    )

    opp_k = extract_organ_keys(opp_organ_cnpj, opp_organ_name)
    ctr_k = extract_organ_keys(contract_organ_cnpj, contract_organ_name)

    conflicts = conflicting_strong_ids(opp_k, ctr_k)
    if "conflict_cnpj14" in conflicts or "conflict_cnpj8" in conflicts:
        return LinkDecision(
            classification="unresolved",
            score=0.0,
            reason_codes=tuple(conflicts) + ("different_organ",),
            claim_level="none",
            target_key=None,
            source_record_ids=src,
            non_claims=non_claims,
        )

    reasons: list[str] = []
    score = 0.0
    classification: Classification = "unresolved"

    same_cnpj14 = bool(opp_k.cnpj14 and ctr_k.cnpj14 and opp_k.cnpj14 == ctr_k.cnpj14)
    same_cnpj8 = bool(opp_k.cnpj8 and ctr_k.cnpj8 and opp_k.cnpj8 == ctr_k.cnpj8)

    if same_cnpj14:
        reasons.append("same_organ_cnpj14")
        score = 1.0
        classification = "exact"
    elif same_cnpj8:
        reasons.append("same_organ_cnpj8")
        score = 0.995
        classification = "deterministic_composite"
    else:
        return LinkDecision(
            classification="unresolved",
            score=0.0,
            reason_codes=("no_shared_organ_key",),
            claim_level="none",
            target_key=None,
            source_record_ids=src,
            non_claims=non_claims,
        )

    # Optional object token boost (does not upgrade to participation claim)
    opp_obj = normalize_name(opp_objeto)
    ctr_obj = normalize_name(contract_objeto)
    if opp_obj and ctr_obj:
        opp_tokens = {t for t in opp_obj.split() if len(t) > 3}
        ctr_tokens = {t for t in ctr_obj.split() if len(t) > 3}
        if opp_tokens and ctr_tokens:
            inter = opp_tokens & ctr_tokens
            if len(inter) >= 2:
                reasons.append("shared_object_tokens")
                score = min(1.0, score + 0.0)  # keep exact/deterministic score
            elif len(inter) == 1:
                reasons.append("weak_shared_object_token")

    if opp_uf and contract_uf and opp_uf.upper() == contract_uf.upper():
        reasons.append("same_uf")

    organ_key = organ_canonical_key(opp_k if same_cnpj14 or same_cnpj8 else ctr_k)
    return LinkDecision(
        classification=classification,
        score=score,
        reason_codes=tuple(reasons),
        claim_level="similarity",  # related historical contract, not tender participation
        target_key=organ_key,
        source_record_ids=src,
        non_claims=non_claims,
    )


def decide_supplier_from_contract(
    supplier_tax_id: str | None,
    supplier_name: str | None,
    *,
    contract_id: str | None = None,
) -> LinkDecision:
    keys = extract_person_keys(supplier_tax_id, supplier_name)
    src = (contract_id,) if contract_id else ()
    ck = supplier_canonical_key(keys)
    non_claims = (
        "not_observed_participant_of_open_tender",
        "not_win_rate",
        "not_consortium_inference",
    )

    if keys.cnpj14 and ck:
        return LinkDecision(
            classification="exact",
            score=1.0,
            reason_codes=("exact_supplier_cnpj14", "observed_contract_winner"),
            claim_level="fact",
            target_key=ck,
            source_record_ids=src,
            non_claims=non_claims,
        )
    if keys.cpf11 and ck:
        return LinkDecision(
            classification="exact",
            score=1.0,
            reason_codes=("exact_supplier_cpf11", "observed_contract_winner"),
            claim_level="fact",
            target_key=ck,
            source_record_ids=src,
            non_claims=non_claims,
        )
    if keys.cnpj8 and keys.normalized_name and ck:
        return LinkDecision(
            classification="deterministic_composite",
            score=0.99,
            reason_codes=("deterministic_supplier_cnpj8_name", "observed_contract_winner"),
            claim_level="fact",
            target_key=ck,
            source_record_ids=src,
            non_claims=non_claims,
        )
    return LinkDecision(
        classification="unresolved",
        score=0.0,
        reason_codes=("supplier_keys_insufficient",),
        claim_level="none",
        target_key=None,
        source_record_ids=src,
        non_claims=non_claims,
    )


def refuse_merge_if_conflict(a: StrongKeys, b: StrongKeys) -> LinkDecision | None:
    """Return ambiguous decision if strong IDs conflict; else None."""
    codes = conflicting_strong_ids(a, b)
    hard = [c for c in codes if c.startswith("conflict_")]
    if hard:
        return LinkDecision(
            classification="ambiguous",
            score=0.0,
            reason_codes=tuple(hard) + ("refuse_strong_id_merge",),
            claim_level="none",
            target_key=None,
        )
    return None


@dataclass
class MatchMetrics:
    """Denominator-preserving counters for a run."""

    total: int = 0
    exact: int = 0
    deterministic_composite: int = 0
    heuristic_reviewable: int = 0
    ambiguous: int = 0
    unresolved: int = 0
    auto_accepted: int = 0

    def observe(self, d: LinkDecision) -> None:
        self.total += 1
        attr = d.classification
        setattr(self, attr, getattr(self, attr) + 1)
        if d.auto_accept:
            self.auto_accepted += 1

    def as_dict(self) -> dict[str, Any]:
        rate = (self.exact + self.deterministic_composite) / self.total if self.total else 0.0
        return {
            "total": self.total,
            "exact": self.exact,
            "deterministic_composite": self.deterministic_composite,
            "heuristic_reviewable": self.heuristic_reviewable,
            "ambiguous": self.ambiguous,
            "unresolved": self.unresolved,
            "auto_accepted": self.auto_accepted,
            "link_rate_deterministic": round(rate, 6),
            "unresolved_in_denominator": True,
            "hard_cases_excluded": False,
        }
