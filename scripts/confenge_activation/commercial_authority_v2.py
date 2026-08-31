"""COMMERCIAL_AUTHORITY/2.0 — qualification by public contracting evidence.

A CONFENGE lead is qualified when public evidence shows it figured as the
CONTRACTED SUPPLIER (never as the contracting body) on an engineering work or
service inside a rolling three-year window.

``PNCP_CONTRACT_FRESHNESS/1.0`` answers a different question entirely: is the
acquisition plane still healthy? A failed, late or missing refresh degrades
source health and MUST NOT revoke, hold, dequeue or block transport for an
otherwise valid commercially-qualified member.

Nothing in this module expires because time passed since a crawl. The only
expiry is the natural one: the qualifying contract itself leaving the window.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

CONTRACT_VERSION = "COMMERCIAL_AUTHORITY/2.0"
POLICY_VERSION = "COMMERCIAL_AUTHORITY_POLICY/2.0"

QUALIFICATION_WINDOW_YEARS = 3

STATE_QUALIFIED = "QUALIFIED"
STATE_EXPIRED = "EXPIRED"
STATE_REVOKED = "REVOKED"
STATE_UNKNOWN = "UNKNOWN"

PARTY_ROLE_SUPPLIER = "SUPPLIER"

# Deterministic precedence for the CONTRACTING ACT over the canonical contracts
# view. data_fim is deliberately excluded: it is an execution-end estimate,
# frequently null, and would make the window non-deterministic.
QUALIFYING_DATE_PRECEDENCE: tuple[str, ...] = (
    "data_assinatura",
    "data_inicio",
    "data_publicacao",
    "data_publicacao_fonte",
)

REASON_QUALIFIED = "COMMERCIAL_QUALIFIED"
REASON_EXPIRED = "commercial_qualification_expired"
REASON_REVOKED = "commercial_qualification_revoked"
REASON_MISSING = "commercial_authority_missing"
REASON_ROLE_INVALID = "commercial_qualification_party_role_invalid"
REASON_NO_QUALIFYING_CONTRACT = "commercial_qualification_no_contract_in_window"
REASON_EVIDENCE_DRIFT = "commercial_qualification_evidence_drift"
REASON_WINDOW_INVALID = "commercial_qualification_window_invalid"
REASON_POLICY_UNSUPPORTED = "commercial_authority_policy_unsupported"

EVIDENCE_SOURCE = "extra-cli:v_contracts_canonical_v2"


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def cnpj_root8(value: Any) -> str:
    return _digits(value)[:8]


def add_years_go(value: date, years: int) -> date:
    """Replicate Go's ``time.Time.AddDate`` normalization exactly.

    Go adds the year component and then normalizes an out-of-range day forward,
    so 2024-02-29 + 3y is 2027-03-01, not 2027-02-28. Warmbly derives
    ``qualified_until`` the Go way and refuses any other value, so the producer
    must agree byte for byte.
    """
    year = value.year + years
    month = value.month
    day = value.day
    try:
        return date(year, month, day)
    except ValueError:
        # Feb 29 -> Mar 1 in a non-leap year, matching Go's normalization.
        overflow = day - _days_in_month(year, month)
        return date(year, month, _days_in_month(year, month)) + _timedelta_days(overflow)


def _days_in_month(year: int, month: int) -> int:
    import calendar

    return calendar.monthrange(year, month)[1]


def _timedelta_days(days: int):
    from datetime import timedelta

    return timedelta(days=days)


def qualified_until(contract_date: date) -> date:
    """Natural expiry of one qualifying fact. No grace period is added."""
    return add_years_go(contract_date, QUALIFICATION_WINDOW_YEARS)


def window_floor(now: datetime) -> date:
    """First date still inside the rolling window as of ``now``."""
    return add_years_go(now.astimezone(UTC).date(), -QUALIFICATION_WINDOW_YEARS)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for parser in (
        lambda t: datetime.fromisoformat(t.replace("Z", "+00:00")),
        lambda t: datetime.strptime(t, "%Y-%m-%d"),
    ):
        try:
            parsed = parser(text)
        except ValueError:
            continue
        return parsed.astimezone(UTC).date() if parsed.tzinfo else parsed.date()
    return None


def contracting_date(contract: Mapping[str, Any]) -> tuple[date | None, str]:
    """Resolve the contracting act date by the canonical precedence."""
    for field_name in QUALIFYING_DATE_PRECEDENCE:
        resolved = _as_date(contract.get(field_name))
        if resolved is not None:
            return resolved, field_name
    return None, ""


@dataclass(frozen=True)
class RootQualification:
    """The qualifying public fact for one CNPJ root."""

    cnpj_root8: str
    target_fit_class: str
    party_role: str
    qualifying_contract_id: str
    qualifying_contract_date: str
    qualifying_date_field: str
    qualifying_contract_count: int
    qualified_until: str
    qualification_evidence_reference: str
    provenance: str
    deactivated: bool = False
    deactivation_reason: str = ""
    qualification_evidence_hash: str = field(default="")
    # Producer-only identity used to elect the exact supplier establishment.
    # It is deliberately not serialized or hashed: the wire authority is root
    # scoped, while contractor_role carries the branch-specific evidence.
    supplier_cnpj14: str = field(default="", repr=False, compare=False)
    buyer_cnpj14: str = field(default="", repr=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cnpj_root8": self.cnpj_root8,
            "target_fit_class": self.target_fit_class,
            "party_role": self.party_role,
            "qualifying_contract_id": self.qualifying_contract_id,
            "qualifying_contract_date": self.qualifying_contract_date,
            "qualifying_date_field": self.qualifying_date_field,
            "qualifying_contract_count": self.qualifying_contract_count,
            "qualified_until": self.qualified_until,
            "qualification_evidence_hash": self.qualification_evidence_hash or evidence_hash(self),
            "qualification_evidence_reference": self.qualification_evidence_reference,
            "provenance": self.provenance,
        }
        if self.deactivated:
            payload["deactivated"] = True
            payload["deactivation_reason"] = self.deactivation_reason
        return payload


def evidence_hash(q: RootQualification) -> str:
    """Bind every material qualification byte, identically to Warmbly's Go.

    Field order and the NUL separator are part of the contract: any drift makes
    the runtime fail closed rather than silently accept a different fact.
    """
    parts = [
        q.cnpj_root8.strip(),
        q.party_role.strip().upper(),
        q.qualifying_contract_id.strip(),
        q.qualifying_contract_date.strip(),
        q.qualifying_date_field.strip(),
        q.qualified_until.strip(),
        q.qualification_evidence_reference.strip(),
    ]
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def corpus_hash(roots: Sequence[RootQualification]) -> str:
    """Population-level evidence hash: sorted per-root digests, newline joined."""
    digests = sorted(r.qualification_evidence_hash or evidence_hash(r) for r in roots)
    return hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()


def qualify_root(
    *,
    lead_cnpj14: Any,
    contracts: Sequence[Mapping[str, Any]],
    now: datetime,
    target_fit_class: str,
    party_role: str,
    deactivated: bool = False,
    deactivation_reason: str = "",
) -> tuple[RootQualification | None, list[str]]:
    """Pick the strongest qualifying contract inside the rolling window.

    Where several contracts qualify, the company stays active while at least one
    is inside the window, so the most recent contracting act is the one that
    carries the qualification.
    """
    root = cnpj_root8(lead_cnpj14)
    if str(party_role or "").strip().upper() != PARTY_ROLE_SUPPLIER:
        return None, [REASON_ROLE_INVALID]

    floor = window_floor(now)
    today = now.astimezone(UTC).date()
    qualifying: list[tuple[date, str, str]] = []
    for contract in contracts:
        if not isinstance(contract, Mapping):
            continue
        resolved, field_name = contracting_date(contract)
        if resolved is None or resolved < floor or resolved > today or qualified_until(resolved) <= today:
            continue
        contract_id = str(contract.get("id") or contract.get("contrato_id") or "").strip()
        if not contract_id:
            continue
        qualifying.append((resolved, field_name, contract_id))

    if not qualifying:
        return None, [REASON_NO_QUALIFYING_CONTRACT]

    qualifying.sort(key=lambda item: (item[0], item[2]), reverse=True)
    best_date, best_field, best_id = qualifying[0]
    reference = f"{EVIDENCE_SOURCE}:{best_id}"
    q = RootQualification(
        cnpj_root8=root,
        target_fit_class=str(target_fit_class or ""),
        party_role=PARTY_ROLE_SUPPLIER,
        qualifying_contract_id=best_id,
        qualifying_contract_date=best_date.isoformat(),
        qualifying_date_field=best_field,
        qualifying_contract_count=len(qualifying),
        qualified_until=qualified_until(best_date).isoformat(),
        qualification_evidence_reference=reference,
        provenance=EVIDENCE_SOURCE,
        deactivated=bool(deactivated),
        deactivation_reason=str(deactivation_reason or ""),
    )
    return (
        RootQualification(**{**q.__dict__, "qualification_evidence_hash": evidence_hash(q)}),
        [REASON_REVOKED] if deactivated else [REASON_QUALIFIED],
    )


def validate_root_qualification(q: RootQualification, *, as_of: date) -> list[str]:
    """Validate a qualification as a self-proving, currently usable fact."""
    reasons: list[str] = []
    if len(q.cnpj_root8) != 8 or not q.cnpj_root8.isdigit():
        reasons.append(REASON_EVIDENCE_DRIFT)
    if q.target_fit_class != "TARGET_CONFIRMED":
        reasons.append(REASON_POLICY_UNSUPPORTED)
    if q.party_role.strip().upper() != PARTY_ROLE_SUPPLIER:
        reasons.append(REASON_ROLE_INVALID)
    contract_date = _as_date(q.qualifying_contract_date)
    declared_until = _as_date(q.qualified_until)
    if contract_date is None or declared_until is None or declared_until != qualified_until(contract_date):
        reasons.append(REASON_WINDOW_INVALID)
    elif declared_until <= as_of:
        reasons.append(REASON_EXPIRED)
    if q.deactivated:
        reasons.append(REASON_REVOKED)
    if not q.qualifying_contract_id.strip() or not q.qualification_evidence_reference.strip():
        reasons.append(REASON_EVIDENCE_DRIFT)
    if q.qualification_evidence_hash.lower() != evidence_hash(q):
        reasons.append(REASON_EVIDENCE_DRIFT)
    return list(dict.fromkeys(reasons))


def qualification_from_mapping(value: Mapping[str, Any]) -> RootQualification:
    """Parse the exact JSON contract, rejecting implicit/default authority."""
    required = (
        "cnpj_root8",
        "target_fit_class",
        "party_role",
        "qualifying_contract_id",
        "qualifying_contract_date",
        "qualifying_date_field",
        "qualifying_contract_count",
        "qualified_until",
        "qualification_evidence_hash",
        "qualification_evidence_reference",
        "provenance",
    )
    missing = [name for name in required if value.get(name) in (None, "")]
    if missing:
        raise ValueError("commercial qualification missing fields: " + ",".join(missing))
    if str(value["qualifying_date_field"]) not in QUALIFYING_DATE_PRECEDENCE:
        raise ValueError("commercial qualification has a non-canonical date field")
    return RootQualification(
        cnpj_root8=str(value["cnpj_root8"]).strip(),
        target_fit_class=str(value["target_fit_class"]).strip(),
        party_role=str(value["party_role"]).strip(),
        qualifying_contract_id=str(value["qualifying_contract_id"]).strip(),
        qualifying_contract_date=str(value["qualifying_contract_date"]).strip(),
        qualifying_date_field=str(value["qualifying_date_field"]).strip(),
        qualifying_contract_count=int(value["qualifying_contract_count"]),
        qualified_until=str(value["qualified_until"]).strip(),
        qualification_evidence_hash=str(value["qualification_evidence_hash"]).strip().lower(),
        qualification_evidence_reference=str(value["qualification_evidence_reference"]).strip(),
        provenance=str(value["provenance"]).strip(),
        deactivated=bool(value.get("deactivated")),
        deactivation_reason=str(value.get("deactivation_reason") or "").strip(),
    )


def build_population_authority(
    *,
    roots: Sequence[RootQualification],
    basis_source_run_id: str,
    basis_snapshot_hash: str,
    basis_membership_hash: str,
    basis_publication_semantic_hash: str,
    producer_identity: str,
    now: datetime,
    explicit_revoked: bool = False,
) -> dict[str, Any]:
    """Population-level attestation. Carries provenance, never a TTL."""
    payload = {
        "schema": CONTRACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "policy_version": POLICY_VERSION,
        "basis_source_run_id": basis_source_run_id,
        "basis_snapshot_hash": basis_snapshot_hash,
        "basis_membership_hash": basis_membership_hash.lower(),
        "basis_publication_semantic_hash": basis_publication_semantic_hash.lower(),
        "producer_identity": producer_identity.lower(),
        "qualification_window_years": QUALIFICATION_WINDOW_YEARS,
        "qualification_evidence_hash": corpus_hash(roots),
        "qualified_root_count": len(roots),
        # Provenance only. Warmbly never ages the attestation by this field.
        "evaluated_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "state": STATE_REVOKED if explicit_revoked else STATE_QUALIFIED,
    }
    if explicit_revoked:
        payload["reason_codes"] = ["EXPLICIT_REVOCATION"]
    return payload
