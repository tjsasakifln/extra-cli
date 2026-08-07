"""Factual outreach eligibility — never commercial tier as discard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.confenge_universe import (
    DNC,
    ELIGIBLE,
    INVALID_IDENTITY,
    NATURAL_PERSON,
    NOT_CONSTRUCTION,
    PUBLIC_ORGAN,
    UNIVERSE_MEMBER_STATES,
)
from scripts.confenge_universe.construction import ConstructionEvidence
from scripts.confenge_universe.identity import Identity


@dataclass(frozen=True)
class EligibilityDecision:
    outreach_eligibility: str
    in_universe: bool
    reason: str
    dominant_human_state: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "outreach_eligibility": self.outreach_eligibility,
            "in_universe": self.in_universe,
            "reason": self.reason,
            "dominant_human_state": self.dominant_human_state,
        }


def decide_eligibility(
    *,
    identity: Identity | None,
    construction: ConstructionEvidence | None,
    dnc: bool = False,
    human_state: str | None = None,
) -> EligibilityDecision:
    """Compute factual eligibility.

    DNC / DO_NOT_CONTACT is dominant for outreach but does NOT remove the firm
    from the research universe when construction evidence exists.
    """
    state = (human_state or "").strip().upper()
    if state == "DO_NOT_CONTACT":
        dnc = True

    if identity is not None and not identity.valid:
        code = identity.exclusion_code or INVALID_IDENTITY
        if code == PUBLIC_ORGAN:
            return EligibilityDecision(
                outreach_eligibility=PUBLIC_ORGAN,
                in_universe=False,
                reason=identity.exclusion_detail or "public_organ",
            )
        if code == NATURAL_PERSON:
            return EligibilityDecision(
                outreach_eligibility=NATURAL_PERSON,
                in_universe=False,
                reason=identity.exclusion_detail or "natural_person",
            )
        if code == NOT_CONSTRUCTION:
            return EligibilityDecision(
                outreach_eligibility=NOT_CONSTRUCTION,
                in_universe=False,
                reason=identity.exclusion_detail or "non_construction_supplier",
            )
        return EligibilityDecision(
            outreach_eligibility=INVALID_IDENTITY,
            in_universe=False,
            reason=identity.exclusion_detail or "invalid_identity",
        )

    if construction is None or not construction.is_construction:
        return EligibilityDecision(
            outreach_eligibility=NOT_CONSTRUCTION,
            in_universe=False,
            reason=(
                ";".join((construction.reason_codes if construction else [])[:5])
                or "no_construction_evidence"
            ),
        )

    if dnc:
        return EligibilityDecision(
            outreach_eligibility=DNC,
            in_universe=True,
            reason="human_do_not_contact_dominant",
            dominant_human_state="DO_NOT_CONTACT",
        )

    return EligibilityDecision(
        outreach_eligibility=ELIGIBLE,
        in_universe=True,
        reason="construction_b2g_private_supplier",
    )


def is_universe_member(outreach_eligibility: str) -> bool:
    return outreach_eligibility in UNIVERSE_MEMBER_STATES


def load_dnc_set(path: str | None) -> set[str]:
    """Load CNPJ14 / root set from a simple text/JSONL file (one id per line or JSON)."""
    if not path:
        return set()
    import json
    import re
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        return set()
    out: set[str] = set()
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    out.add(re.sub(r"\D", "", item)[:14])
                elif isinstance(item, dict):
                    raw = item.get("cnpj14") or item.get("cnpj") or item.get("cnpj_root")
                    if raw:
                        out.add(re.sub(r"\D", "", str(raw))[:14])
        elif isinstance(data, dict):
            for raw in data.get("dnc") or data.get("cnpjs") or []:
                out.add(re.sub(r"\D", "", str(raw))[:14])
        return {x for x in out if x}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                raw = obj.get("cnpj14") or obj.get("cnpj") or obj.get("cnpj_root")
                if raw:
                    out.add(re.sub(r"\D", "", str(raw))[:14])
            except json.JSONDecodeError:
                continue
        else:
            out.add(re.sub(r"\D", "", line)[:14])
    return {x for x in out if x}


def is_dnc_cnpj(cnpj14: str | None, cnpj_root: str | None, dnc_set: set[str]) -> bool:
    if not dnc_set:
        return False
    if cnpj14 and cnpj14 in dnc_set:
        return True
    if cnpj_root and cnpj_root in dnc_set:
        return True
    if cnpj14 and cnpj14[:8] in dnc_set:
        return True
    return False
