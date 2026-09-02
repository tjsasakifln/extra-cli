"""Versioned commercial authority over the last fully proven outreach population.

``PNCP_CONTRACT_FRESHNESS/1.0`` answers whether the crawler/maintenance plane
is healthy. This contract answers a different question: may the last
publication-ready feed still sustain new admissions and/or already-bound
transport?

A failed refresh degrades source health. It does not rewrite a previously
proven population into "never valid". Authority expires only by this policy
or an explicit factual revoke. New facts still require a publication-ready
candidate with live PNCP ``FRESH``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

CONTRACT_VERSION = "COMMERCIAL_AUTHORITY/1.0"
POLICY_VERSION = "COMMERCIAL_AUTHORITY_POLICY/1.0"

CommercialState = Literal[
    "CURRENT",
    "DEGRADED",
    "FROZEN_FOR_NEW_ADMISSION",
    "EXPIRED",
    "UNKNOWN",
]

STATES: tuple[CommercialState, ...] = (
    "CURRENT",
    "DEGRADED",
    "FROZEN_FOR_NEW_ADMISSION",
    "EXPIRED",
    "UNKNOWN",
)

REASON_CURRENT = "COMMERCIAL_AUTHORITY_CURRENT"
REASON_DEGRADED = "COMMERCIAL_AUTHORITY_DEGRADED"
REASON_FROZEN = "COMMERCIAL_AUTHORITY_FROZEN_FOR_NEW_ADMISSION"
REASON_EXPIRED = "COMMERCIAL_AUTHORITY_EXPIRED"
REASON_UNKNOWN = "COMMERCIAL_AUTHORITY_UNKNOWN"
REASON_NEW_ADMISSION_REQUIRES_EVIDENCE = "NEW_ADMISSION_REQUIRES_VALID_EVIDENCE_AND_NO_DRIFT"
REASON_NEW_ADMISSION_FROZEN = "NEW_ADMISSION_FROZEN"
REASON_EXISTING_BOUND_MAY_CONTINUE = "EXISTING_BOUND_TOUCH_MAY_CONTINUE"
REASON_ALL_NEW_TRANSPORT_EXPIRED = "ALL_NEW_TRANSPORT_EXPIRED"
REASON_EXPLICIT_REVOCATION = "EXPLICIT_REVOCATION"
REASON_BINDING_MISMATCH = "BINDING_MISMATCH"
REASON_MEMBERSHIP_HASH_MISMATCH = "MEMBERSHIP_HASH_MISMATCH"
REASON_SOURCE_RUN_MISMATCH = "SOURCE_RUN_MISMATCH"
REASON_SNAPSHOT_HASH_MISMATCH = "SNAPSHOT_HASH_MISMATCH"
REASON_SEMANTIC_HASH_MISMATCH = "PUBLICATION_SEMANTIC_HASH_MISMATCH"
REASON_PRODUCER_IDENTITY_MISMATCH = "PRODUCER_IDENTITY_MISMATCH"
REASON_MISSING_VALIDATED_AT = "MISSING_VALIDATED_AT"
REASON_ROOT_DEACTIVATED = "ROOT_EXPLICITLY_DEACTIVATED"


@dataclass(frozen=True)
class CommercialAuthorityPolicy:
    """Inclusive upper bounds: age <= N hours remains in that band."""

    version: str = POLICY_VERSION
    current_max_hours: float = 24.0
    degraded_max_hours: float = 72.0
    frozen_max_hours: float = 24.0 * 7

    def __post_init__(self) -> None:
        if not (0 < self.current_max_hours <= self.degraded_max_hours <= self.frozen_max_hours):
            raise ValueError("commercial authority policy windows must be strictly ordered and positive")


DEFAULT_POLICY = CommercialAuthorityPolicy()


@dataclass(frozen=True)
class CommercialAuthorityBinding:
    basis_source_run_id: str
    basis_snapshot_hash: str
    basis_membership_hash: str
    basis_publication_semantic_hash: str
    producer_identity: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "basis_source_run_id": self.basis_source_run_id,
            "basis_snapshot_hash": self.basis_snapshot_hash,
            "basis_membership_hash": self.basis_membership_hash,
            "basis_publication_semantic_hash": self.basis_publication_semantic_hash,
            "producer_identity": self.producer_identity,
        }


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return value.astimezone(UTC)


def parse_timestamp(value: Any, *, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is missing or invalid: {text!r}") from exc
    return _as_utc(parsed, field=field)


def source_operational_health_hash(snapshot: Mapping[str, Any] | None) -> str | None:
    if not snapshot:
        return None
    encoded = json.dumps(dict(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _age_hours(validated_at: datetime, now: datetime) -> float:
    return max(0.0, (now - validated_at).total_seconds() / 3600.0)


def _state_for_age(age_hours: float, policy: CommercialAuthorityPolicy) -> CommercialState:
    if age_hours <= policy.current_max_hours:
        return "CURRENT"
    if age_hours <= policy.degraded_max_hours:
        return "DEGRADED"
    if age_hours <= policy.frozen_max_hours:
        return "FROZEN_FOR_NEW_ADMISSION"
    return "EXPIRED"


def _valid_until(validated_at: datetime, state: CommercialState, policy: CommercialAuthorityPolicy) -> datetime:
    if state == "CURRENT":
        return validated_at + timedelta(hours=policy.current_max_hours)
    if state == "DEGRADED":
        return validated_at + timedelta(hours=policy.degraded_max_hours)
    return validated_at + timedelta(hours=policy.frozen_max_hours)


def _flags_and_reasons(state: CommercialState) -> tuple[bool, bool, list[str]]:
    if state == "CURRENT":
        return True, True, [REASON_CURRENT]
    if state == "DEGRADED":
        return (
            True,
            True,
            [
                REASON_DEGRADED,
                REASON_NEW_ADMISSION_REQUIRES_EVIDENCE,
            ],
        )
    if state == "FROZEN_FOR_NEW_ADMISSION":
        return (
            False,
            True,
            [
                REASON_FROZEN,
                REASON_NEW_ADMISSION_FROZEN,
                REASON_EXISTING_BOUND_MAY_CONTINUE,
            ],
        )
    if state == "EXPIRED":
        return False, False, [REASON_EXPIRED, REASON_ALL_NEW_TRANSPORT_EXPIRED]
    return False, False, [REASON_UNKNOWN]


def _unknown(
    *,
    policy: CommercialAuthorityPolicy,
    binding: CommercialAuthorityBinding | None,
    now: datetime,
    reasons: Sequence[str],
    source_health_hash: str | None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": CONTRACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "policy_version": policy.version,
        "state": "UNKNOWN",
        "new_admission_allowed": False,
        "existing_bound_touch_transport_allowed": False,
        "reason_codes": list(dict.fromkeys(reasons)),
        "validated_at": None,
        "valid_until": None,
        "age_hours": None,
        "classified_at": _rfc3339(now),
        "source_operational_health_hash": source_health_hash,
        **(binding.as_dict() if binding is not None else {}),
    }
    if extra:
        payload.update(extra)
    return payload


def classify_commercial_authority(
    *,
    validated_at: datetime | None,
    now: datetime,
    binding: CommercialAuthorityBinding | None = None,
    expected_binding: CommercialAuthorityBinding | None = None,
    explicit_revoked: bool = False,
    source_operational_health: Mapping[str, Any] | None = None,
    policy: CommercialAuthorityPolicy | None = None,
) -> dict[str, Any]:
    """Pure classifier. ``now`` must be injected; never reads wall clock."""
    resolved_policy = policy or DEFAULT_POLICY
    clock = _as_utc(now, field="now")
    health_hash = source_operational_health_hash(source_operational_health)

    if binding is None or not _binding_is_complete(binding):
        return _unknown(
            policy=resolved_policy,
            binding=binding,
            now=clock,
            reasons=[REASON_UNKNOWN, REASON_BINDING_MISMATCH],
            source_health_hash=health_hash,
        )
    if expected_binding is not None:
        mismatch_reasons = _binding_mismatch_reasons(binding, expected_binding)
        if mismatch_reasons:
            return _unknown(
                policy=resolved_policy,
                binding=binding,
                now=clock,
                reasons=mismatch_reasons,
                source_health_hash=health_hash,
            )
    if validated_at is None:
        return _unknown(
            policy=resolved_policy,
            binding=binding,
            now=clock,
            reasons=[REASON_UNKNOWN, REASON_MISSING_VALIDATED_AT],
            source_health_hash=health_hash,
        )

    proven_at = _as_utc(validated_at, field="validated_at")
    if proven_at > clock + timedelta(minutes=5):
        return _unknown(
            policy=resolved_policy,
            binding=binding,
            now=clock,
            reasons=[REASON_UNKNOWN, "VALIDATED_AT_IN_THE_FUTURE"],
            source_health_hash=health_hash,
        )

    age_hours = _age_hours(proven_at, clock)
    state = _state_for_age(age_hours, resolved_policy)
    new_admission, existing_bound, reasons = _flags_and_reasons(state)
    valid_until = _valid_until(proven_at, state, resolved_policy)
    if explicit_revoked:
        new_admission = False
        existing_bound = False
        reasons = [REASON_EXPLICIT_REVOCATION, *reasons]
        state = "EXPIRED"
        valid_until = clock

    return {
        "schema": CONTRACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "policy_version": resolved_policy.version,
        "state": state,
        "new_admission_allowed": new_admission,
        "existing_bound_touch_transport_allowed": existing_bound,
        "reason_codes": reasons,
        "validated_at": _rfc3339(proven_at),
        "valid_until": _rfc3339(valid_until),
        "age_hours": round(age_hours, 6),
        "classified_at": _rfc3339(clock),
        "source_operational_health_hash": health_hash,
        **binding.as_dict(),
        "windows_hours": {
            "current_max_hours": resolved_policy.current_max_hours,
            "degraded_max_hours": resolved_policy.degraded_max_hours,
            "frozen_max_hours": resolved_policy.frozen_max_hours,
        },
    }


def _binding_is_complete(binding: CommercialAuthorityBinding) -> bool:
    return bool(
        binding.basis_source_run_id.strip()
        and binding.basis_snapshot_hash.strip()
        and binding.basis_membership_hash.strip()
        and binding.basis_publication_semantic_hash.strip()
        and binding.producer_identity.strip()
    )


def _binding_mismatch_reasons(
    observed: CommercialAuthorityBinding,
    expected: CommercialAuthorityBinding,
) -> list[str]:
    reasons: list[str] = []
    if observed.basis_source_run_id != expected.basis_source_run_id:
        reasons.append(REASON_SOURCE_RUN_MISMATCH)
    if observed.basis_snapshot_hash != expected.basis_snapshot_hash:
        reasons.append(REASON_SNAPSHOT_HASH_MISMATCH)
    if observed.basis_membership_hash != expected.basis_membership_hash:
        reasons.append(REASON_MEMBERSHIP_HASH_MISMATCH)
    if observed.basis_publication_semantic_hash != expected.basis_publication_semantic_hash:
        reasons.append(REASON_SEMANTIC_HASH_MISMATCH)
    if observed.producer_identity != expected.producer_identity:
        reasons.append(REASON_PRODUCER_IDENTITY_MISMATCH)
    if reasons:
        reasons.insert(0, REASON_BINDING_MISMATCH)
    return reasons


def binding_from_manifest(
    manifest: Mapping[str, Any],
    *,
    producer_identity: str = "",
    publication_semantic_hash: str = "",
) -> CommercialAuthorityBinding:
    source_raw = manifest.get("source")
    source = source_raw if isinstance(source_raw, dict) else {}
    membership_raw = manifest.get("authoritative_target_membership")
    membership = membership_raw if isinstance(membership_raw, dict) else {}
    return CommercialAuthorityBinding(
        basis_source_run_id=str(source.get("run_id") or "").strip(),
        basis_snapshot_hash=str(source.get("snapshot_hash") or "").strip(),
        basis_membership_hash=str(membership.get("membership_hash") or "").strip(),
        basis_publication_semantic_hash=publication_semantic_hash,
        producer_identity=producer_identity,
    )


def authority_from_manifest(
    manifest: Mapping[str, Any],
    *,
    now: datetime,
    producer_identity: str = "",
    publication_semantic_hash: str = "",
    expected_binding: CommercialAuthorityBinding | None = None,
    explicit_revoked: bool = False,
    source_operational_health: Mapping[str, Any] | None = None,
    policy: CommercialAuthorityPolicy | None = None,
) -> dict[str, Any]:
    binding = binding_from_manifest(
        manifest,
        producer_identity=producer_identity,
        publication_semantic_hash=publication_semantic_hash,
    )
    if not all(
        (
            binding.basis_source_run_id,
            binding.basis_snapshot_hash,
            binding.basis_membership_hash,
            binding.basis_publication_semantic_hash,
            binding.producer_identity,
        )
    ):
        return classify_commercial_authority(
            validated_at=None,
            now=now,
            binding=None,
            source_operational_health=source_operational_health,
            policy=policy,
        )
    try:
        validated_at = parse_timestamp(manifest.get("generated_at"), field="manifest.generated_at")
    except ValueError:
        validated_at = None
    return classify_commercial_authority(
        validated_at=validated_at,
        now=now,
        binding=binding,
        expected_binding=expected_binding,
        explicit_revoked=explicit_revoked,
        source_operational_health=source_operational_health,
        policy=policy,
    )


def root_transport_allowed(
    authority: Mapping[str, Any],
    *,
    cnpj_root8: str,
    deactivated_roots: Sequence[str] = (),
    new_admission: bool,
) -> tuple[bool, list[str]]:
    """Per-root gate. Explicit deactivation always beats commercial grace."""
    root = "".join(char for char in cnpj_root8 if char.isdigit())[:8]
    deactivated = {"".join(char for char in item if char.isdigit())[:8] for item in deactivated_roots}
    if root and root in deactivated:
        return False, [REASON_ROOT_DEACTIVATED, REASON_EXPLICIT_REVOCATION]
    if new_admission:
        allowed = bool(authority.get("new_admission_allowed"))
        reasons = list(authority.get("reason_codes") or [])
        if not allowed:
            reasons = list(dict.fromkeys([*reasons, REASON_NEW_ADMISSION_FROZEN]))
        return allowed, reasons
    allowed = bool(authority.get("existing_bound_touch_transport_allowed"))
    reasons = list(authority.get("reason_codes") or [])
    if not allowed:
        reasons = list(dict.fromkeys([*reasons, REASON_ALL_NEW_TRANSPORT_EXPIRED]))
    return allowed, reasons


def source_health_attestation_present(freshness: Mapping[str, Any] | None) -> None:
    """Require an accountable source-health envelope, not a FRESH verdict.

    PNCP freshness is acquisition telemetry: it says whether the crawler closed
    a window, not whether a persisted population is still commercially valid.
    A feed must therefore always *carry* the envelope it was built under — a
    build that cannot say what the source was doing is unaccountable — but a
    STALE/UNKNOWN verdict cannot revoke authority that
    ``COMMERCIAL_AUTHORITY/1.0`` grants over already-proven membership.
    """
    if not isinstance(freshness, dict):
        raise ValueError("feed is missing its source operational health attestation")
    if freshness.get("contract_version") != "PNCP_CONTRACT_FRESHNESS/1.0":
        raise ValueError("feed has an unsupported source operational health contract")
    status = str(freshness.get("status") or "").strip()
    if not status:
        raise ValueError("feed source operational health attestation has no status")


def historical_source_was_proven_fresh(freshness: Mapping[str, Any] | None) -> None:
    """Last-good must have been FRESH at publication. Do not re-test expires_at against now."""
    if not isinstance(freshness, dict):
        raise ValueError("last-good feed is missing historical PNCP freshness attestation")
    if freshness.get("contract_version") != "PNCP_CONTRACT_FRESHNESS/1.0":
        raise ValueError("last-good feed has an unsupported PNCP freshness contract")
    if freshness.get("status") != "FRESH":
        raise ValueError(
            f"last-good feed was never proven FRESH at publication; observed={freshness.get('status') or 'MISSING'}"
        )
