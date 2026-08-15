"""Adjudication record for EMAIL_VALIDATED gold cases.

A gold-set verdict is a benchmark label. It does not authorize send and
must never be stored as HUMAN_REVIEW_APPROVED.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from enum import StrEnum
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.email_resolution import is_third_party_professional_domain
from scripts.decision_unit_intelligence.models import normalize_cnpj, normalize_email, normalize_name
from scripts.decision_unit_intelligence.reachability import (
    is_brand_mailbox,
    is_generic_mailbox,
    is_role_mailbox,
)

GOLD_SET_VERSION = "email-validated-gold.v1"
SCHEMA_ID = "confenge.email-validated-adjudication.v1"

HUMAN_VERDICTS = (
    "VALIDATED_DIRECT",
    "OBSERVED_BUT_STALE",
    "OBSERVED_BUT_IDENTITY_AMBIGUOUS",
    "INFERRED_HIGH",
    "INFERRED_UNVERIFIED",
    "GENERIC_ROLE",
    "WRONG_PERSON",
    "WRONG_COMPANY",
    "UNKNOWN",
)

EPISTEMIC_VALUES = ("OBSERVED", "INFERRED")
IDENTITY_VALUES = ("ASSOCIATED", "UNRESOLVED", "AMBIGUOUS", "NONE")
AFFILIATION_VALUES = ("DEFENSIBLE", "HOLDING", "THIRD_PARTY", "UNCLEAR", "NONE")
TECHNICAL_VALUES = ("NONE", "MX_PRESENT", "HARD_FAIL", "UNKNOWN")
FRESHNESS_VALUES = ("FRESH", "AGING", "STALE", "UNKNOWN")
SUPPRESSION_VALUES = ("NONE", "DNC", "OPT_OUT", "HARD_BOUNCE", "BLOCKED")
SPLIT_VALUES = ("development", "holdout")

# Minimum pack a human needs to adjudicate in under 60 seconds.
EVIDENCE_PACK_FIELDS = (
    "person_name",
    "company",
    "email",
    "source_url",
    "frozen_evidence",
    "source_date",
    "identity_association",
    "affiliation",
    "technical_status",
    "suppression",
    "freshness",
)

REQUIRED_RECORD_FIELDS = (
    "case_id",
    "account_id",
    "person_name",
    "role",
    "company",
    "email",
    "epistemic",
    "source",
    "source_date",
    "identity_association",
    "affiliation",
    "technical_status",
    "freshness",
    "human_verdict",
    "notes",
    "policy_version",
    "gold_set_version",
    "split",
    "suppression",
    "engine",
)


class HumanVerdict(StrEnum):
    VALIDATED_DIRECT = "VALIDATED_DIRECT"
    OBSERVED_BUT_STALE = "OBSERVED_BUT_STALE"
    OBSERVED_BUT_IDENTITY_AMBIGUOUS = "OBSERVED_BUT_IDENTITY_AMBIGUOUS"
    INFERRED_HIGH = "INFERRED_HIGH"
    INFERRED_UNVERIFIED = "INFERRED_UNVERIFIED"
    GENERIC_ROLE = "GENERIC_ROLE"
    WRONG_PERSON = "WRONG_PERSON"
    WRONG_COMPANY = "WRONG_COMPANY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AdjudicationRecord:
    case_id: str
    account_id: str
    company: str
    email: str | None
    epistemic: str
    source: str
    source_date: str | None
    identity_association: str
    affiliation: str
    technical_status: str
    freshness: str
    human_verdict: str
    notes: str
    policy_version: str
    gold_set_version: str
    split: str
    person_name: str | None = None
    role: str | None = None
    source_url: str | None = None
    frozen_evidence: str | None = None
    suppression: str = "NONE"
    engine: str | None = None
    score: float | None = None
    approved_exception: str | None = None
    account_legal_name: str | None = None
    third_party_echo: bool = False
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_id"] = SCHEMA_ID
        payload["gold_label_is_not_send_authorization"] = True
        payload["auto_send"] = False
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AdjudicationRecord:
        allowed = {item.name for item in fields(cls)}
        data = {key: raw.get(key) for key in allowed}
        data["account_id"] = normalize_cnpj(str(data.get("account_id") or raw.get("cnpj") or ""))
        if data.get("email"):
            data["email"] = normalize_email(str(data["email"]))
        if data.get("person_name"):
            data["person_name"] = normalize_name(str(data["person_name"]))
        if data.get("reason_codes") is not None and not isinstance(data["reason_codes"], tuple):
            data["reason_codes"] = tuple(data["reason_codes"])
        if not data.get("company"):
            data["company"] = raw.get("account_legal_name") or raw.get("legal_name") or ""
        if not data.get("gold_set_version"):
            data["gold_set_version"] = GOLD_SET_VERSION
        return cls(**data)

    def mailbox_kind(self) -> str:
        if not self.email:
            return "NONE"
        if is_role_mailbox(self.email):
            return "ROLE"
        if is_generic_mailbox(self.email) or is_brand_mailbox(self.email):
            return "GENERIC"
        domain = self.email.split("@", 1)[-1]
        if is_third_party_professional_domain(domain):
            return "THIRD_PARTY_DOMAIN"
        return "NOMINAL"

    def has_provenance(self) -> bool:
        url = (self.source_url or "").strip()
        snippet = (self.frozen_evidence or "").strip()
        return bool(url or snippet)

    def has_source_date(self) -> bool:
        return bool((self.source_date or "").strip())

    def evidence_pack(self) -> dict[str, Any]:
        return evidence_pack(self)


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    predicted_class: str
    policy_version: str
    epistemic: str
    reasons: tuple[str, ...]
    case_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "promote": self.promote,
            "predicted_class": self.predicted_class,
            "policy_version": self.policy_version,
            "epistemic": self.epistemic,
            "reasons": list(self.reasons),
            "case_id": self.case_id,
            "auto_send": False,
        }


def evidence_pack(record: AdjudicationRecord) -> dict[str, Any]:
    """Fields a reviewer must see to adjudicate in under 60 seconds."""
    return {
        "person_name": record.person_name,
        "company": record.company,
        "email": record.email,
        "source_url": record.source_url,
        "frozen_evidence": record.frozen_evidence,
        "source_date": record.source_date,
        "identity_association": record.identity_association,
        "affiliation": record.affiliation,
        "technical_status": record.technical_status,
        "suppression": record.suppression,
        "freshness": record.freshness,
        "epistemic": record.epistemic,
        "role": record.role,
        "engine": record.engine,
        "mailbox_kind": record.mailbox_kind(),
    }


def validate_record(raw: dict[str, Any] | AdjudicationRecord) -> list[str]:
    record = raw if isinstance(raw, AdjudicationRecord) else AdjudicationRecord.from_dict(raw)
    errors: list[str] = []
    payload = record.to_dict()
    for field in REQUIRED_RECORD_FIELDS:
        if field not in payload:
            errors.append(f"missing_field:{field}")
    if not record.case_id:
        errors.append("missing_case_id")
    if not record.account_id:
        errors.append("missing_account_id")
    if not record.company:
        errors.append("missing_company")
    if record.epistemic not in EPISTEMIC_VALUES:
        errors.append(f"invalid_epistemic:{record.epistemic}")
    if record.identity_association not in IDENTITY_VALUES:
        errors.append(f"invalid_identity_association:{record.identity_association}")
    if record.affiliation not in AFFILIATION_VALUES:
        errors.append(f"invalid_affiliation:{record.affiliation}")
    if record.technical_status not in TECHNICAL_VALUES:
        errors.append(f"invalid_technical_status:{record.technical_status}")
    if record.freshness not in FRESHNESS_VALUES:
        errors.append(f"invalid_freshness:{record.freshness}")
    if record.suppression not in SUPPRESSION_VALUES:
        errors.append(f"invalid_suppression:{record.suppression}")
    if record.human_verdict not in HUMAN_VERDICTS:
        errors.append(f"invalid_human_verdict:{record.human_verdict}")
    if record.split not in SPLIT_VALUES:
        errors.append(f"invalid_split:{record.split}")
    if not record.policy_version:
        errors.append("missing_policy_version")
    if not record.gold_set_version:
        errors.append("missing_gold_set_version")
    if not record.notes:
        errors.append("missing_notes")
    if not record.has_provenance():
        errors.append("missing_source_url_or_frozen_evidence")
    pack = record.evidence_pack()
    for field in ("person_name", "company", "email", "source_date", "identity_association", "affiliation"):
        if field not in pack:
            errors.append(f"missing_evidence_pack_field:{field}")
    return errors


def load_jsonl(path: str | Path) -> list[AdjudicationRecord]:
    records: list[AdjudicationRecord] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid json: {exc}") from exc
        records.append(AdjudicationRecord.from_dict(payload))
    return records


def write_jsonl(path: str | Path, records: list[AdjudicationRecord]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) for record in records]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
