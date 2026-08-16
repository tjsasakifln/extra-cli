"""Last-known-good policy.

LKG exists only after a prior AUTHORIZED decision. A stale payload never
authorizes the current claim. Material universe/method/source changes
invalidate LKG. Prior evidence is never deleted — invalidation is a stamp.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.national_claims.models import (
    LKG_DEFAULT_TTL_HOURS,
    LkgRecord,
    VersionedUniverse,
)
from scripts.national_claims.universe import universe_diff

LKG_VALID = "valid"
LKG_EXPIRED = "expired"
LKG_INVALIDATED = "invalidated"
LKG_ABSENT = "absent"
LKG_NOT_AUTHORIZED = "not_prior_authorized"


def parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def lkg_expiry(*, authorized_at: str, ttl_hours: int = LKG_DEFAULT_TTL_HOURS) -> str:
    expires = parse_iso(authorized_at) + timedelta(hours=ttl_hours)
    return expires.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_lkg(
    *,
    claim_id: str,
    national_universe_id: str,
    catalog_hash: str,
    method_version: str,
    source_version: str,
    content_hash: str,
    authorized_at: str,
    ttl_hours: int = LKG_DEFAULT_TTL_HOURS,
) -> LkgRecord:
    return LkgRecord(
        claim_id=claim_id,
        authorization_state="AUTHORIZED",
        national_universe_id=national_universe_id,
        catalog_hash=catalog_hash,
        method_version=method_version,
        source_version=source_version,
        content_hash=content_hash,
        authorized_at=authorized_at,
        expires_at=lkg_expiry(authorized_at=authorized_at, ttl_hours=ttl_hours),
    )


def evaluate_lkg(
    prior: LkgRecord | None,
    *,
    current_universe: VersionedUniverse,
    source_version: str,
    as_of: str,
) -> tuple[str, tuple[str, ...], LkgRecord | None]:
    """Return (status, invalidation_triggers, record_or_none)."""
    if prior is None:
        return LKG_ABSENT, (), None
    if prior.authorization_state != "AUTHORIZED":
        return LKG_NOT_AUTHORIZED, ("lkg_requires_prior_authorized",), None
    triggers: list[str] = []
    if prior.invalidated_at:
        return LKG_INVALIDATED, (prior.invalidation_reason or "lkg_already_invalidated",), prior
    if parse_iso(as_of) > parse_iso(prior.expires_at):
        triggers.append("lkg_expired")
        return LKG_EXPIRED, tuple(triggers), prior
    if prior.catalog_hash != current_universe.catalog_hash:
        triggers.append("universe_hash_change")
    if prior.method_version != current_universe.method_version:
        triggers.append("method_version_change")
    if prior.source_version != source_version:
        triggers.append("source_version_change")
    if prior.national_universe_id != current_universe.universe_id:
        triggers.append("national_universe_id_change")
    diff = universe_diff(
        VersionedUniverse(
            universe_id=prior.national_universe_id,
            universe_kind="national",
            official_source=current_universe.official_source,
            cutoff=current_universe.cutoff,
            competence=current_universe.competence,
            catalog_hash=prior.catalog_hash,
            method_version=prior.method_version,
            expected_orgs=current_universe.expected_orgs,
            expected_units=current_universe.expected_units,
            expected_partitions=current_universe.expected_partitions,
            inclusion_rules=current_universe.inclusion_rules,
            exclusion_rules=current_universe.exclusion_rules,
            version_changes=(),
            owner=current_universe.owner,
            review_cadence=current_universe.review_cadence,
        ),
        current_universe,
    )
    if diff["material"] and "catalog_hash" in diff["changed"] and "universe_hash_change" not in triggers:
        triggers.append("universe_hash_change")
    if triggers:
        return LKG_INVALIDATED, tuple(triggers), prior
    return LKG_VALID, (), prior


def consumer_view(*, current_authorized: bool, lkg_status: str) -> str:
    if current_authorized:
        return "current"
    if lkg_status == LKG_VALID:
        return "lkg"
    return "blocked"
