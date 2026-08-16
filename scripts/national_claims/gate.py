"""Unique inbound arbiter for national claims.

``decide()`` is pure: claim + universe + partitions + classified evidence +
freshness + prior LKG in, one of six tokens + versioned payload out.
It never paints coverage green from a row count or Extra's 1.093 entes.
"""

from __future__ import annotations

from typing import Any

from scripts.national_claims.freshness import FRESHNESS_STALE, evaluate_freshness
from scripts.national_claims.hashing import content_hash
from scripts.national_claims.identity import (
    dual_coverage_from_rows,
    identity_reason_codes,
    identity_report,
    split_evidence,
)
from scripts.national_claims.lkg import (
    consumer_view,
    evaluate_lkg,
)
from scripts.national_claims.models import (
    AUTHORIZATION_STATES,
    CONTRACT_VERSION,
    FORBIDDEN_NATIONAL_DENOMINATORS,
    LIMITED_SCOPES,
    NATIONAL_SCOPES,
    POLICY_VERSION,
    ClaimRequest,
    PartitionReconciliation,
    universe_to_dict,
)
from scripts.national_claims.partitions import (
    counts_close,
    reconcile_claim_partitions,
)
from scripts.national_claims.universe import UniverseSeparationError, assert_national_denominator
from scripts.national_contract_truth.national_universe import (
    EXTRA_COMMERCIAL_DENOMINATOR,
    NationalUniverseError,
)

REASON_ORDER = (
    "malformed_request",
    "inconsistent_scope_geography",
    "inconsistent_denominator_extra_1093",
    "inconsistent_denominator",
    "forbidden_national_denominator",
    "row_count_completeness_forbidden",
    "unmappable_evidence_cannot_drop",
    "source_wide_aggregate_without_identity",
    "aggregated_evidence_not_entity_coverage",
    "missing_evidence",
    "failed_partitions",
    "blocked_partitions",
    "unknown_partitions",
    "zero_without_pagination_proof",
    "partition_counts_do_not_close",
    "national_denominator_incomplete",
    "freshness_stale",
    "lkg_expired",
    "universe_hash_change",
    "method_version_change",
    "source_version_change",
    "national_universe_id_change",
    "lkg_requires_prior_authorized",
    "lkg_already_invalidated",
    "scoped_partitions_incomplete",
)


def _ordered_reasons(codes: set[str]) -> tuple[str, ...]:
    ordered = [code for code in REASON_ORDER if code in codes]
    extras = sorted(codes - set(ordered))
    return tuple(ordered + extras)


def _is_national(request: ClaimRequest) -> bool:
    return request.claim.scope in NATIONAL_SCOPES


def _scoped_ids(request: ClaimRequest) -> frozenset[str] | None:
    if request.claim.scope not in LIMITED_SCOPES:
        return None
    geography = request.claim.geography.strip().upper()
    if request.claim.scope in {"geo_limited", "geo_period_limited"} and geography not in {
        "",
        "BR",
        "BRASIL",
        "NATIONAL",
    }:
        matched = {
            org.org_id
            for org in request.universes.national.expected_orgs
            if (org.geography or "").strip().upper() == geography
        }
        return frozenset(matched)
    return None


def _numerator(reconciliation: PartitionReconciliation) -> int:
    return int(reconciliation.by_status.get("FOUND", 0)) + int(reconciliation.by_status.get("ZERO_CONFIRMED", 0))


def decide(request: ClaimRequest) -> dict[str, Any]:
    """Return the versioned claim payload. Never invents nacional_completo."""
    reasons: set[str] = set()
    limitations: list[str] = []
    state: str = "FAILED"
    try:
        return _decide_inner(request, reasons, limitations, state)
    except (NationalUniverseError, UniverseSeparationError, ValueError, KeyError, TypeError) as exc:
        reasons.add("malformed_request")
        payload = _envelope(
            request=request,
            state="FAILED",
            reasons=_ordered_reasons(reasons),
            limitations=tuple(limitations),
            reconciliation=PartitionReconciliation(
                expected=0,
                attempted=0,
                closed=0,
                by_status={},
                records=(),
                blockers=(str(exc),),
                next_actions=("fix_request",),
            ),
            identity={"mapped": 0, "source_wide": 0, "unmappable": 0},
            freshness_status="UNKNOWN",
            freshness_reason=str(exc),
            lkg_status="absent",
            lkg_triggers=(),
            dual_gate={},
        )
        return payload


def _decide_inner(
    request: ClaimRequest,
    reasons: set[str],
    limitations: list[str],
    state: str,
) -> dict[str, Any]:
    claim = request.claim
    national = request.universes.national
    extra_1093 = request.universes.extra_1093_monitored
    observed = request.universes.observed_corpus

    if claim.policy_version != POLICY_VERSION:
        limitations.append(f"policy_version_input={claim.policy_version}")

    geography = claim.geography.strip().upper()
    national_claim = _is_national(request)
    if national_claim and geography not in {"BR", "BRASIL", "NATIONAL"}:
        reasons.add("inconsistent_scope_geography")
    if not national_claim and claim.scope in LIMITED_SCOPES:
        limitations.append(f"scope={claim.scope}")
        limitations.append(f"geography={claim.geography}")
        limitations.append(f"period={claim.period}")

    if claim.denominator_kind in FORBIDDEN_NATIONAL_DENOMINATORS:
        reasons.add("forbidden_national_denominator")
        if "1093" in claim.denominator_kind or claim.denominator_kind == "extra_commercial_1093":
            reasons.add("inconsistent_denominator_extra_1093")
    if national_claim:
        try:
            assert_national_denominator(claim.denominator_kind)
        except UniverseSeparationError:
            reasons.add("forbidden_national_denominator")
            reasons.add("inconsistent_denominator")
    if national.expected_partitions == EXTRA_COMMERCIAL_DENOMINATOR:
        reasons.add("inconsistent_denominator_extra_1093")
        reasons.add("inconsistent_denominator")
    if (
        national_claim
        and extra_1093.expected_partitions == EXTRA_COMMERCIAL_DENOMINATOR
        and claim.denominator_kind in {"extra_1093_monitored", "extra_commercial_1093"}
    ):
        reasons.add("inconsistent_denominator_extra_1093")
    if national_claim and claim.denominator_kind == "observed_corpus":
        reasons.add("forbidden_national_denominator")
    if claim.infer_completeness_from_row_count:
        reasons.add("row_count_completeness_forbidden")
    if national_claim and observed.expected_partitions == national.expected_partitions:
        if observed.catalog_hash == national.catalog_hash:
            reasons.add("forbidden_national_denominator")

    scoped = _scoped_ids(request)
    reconciliation = reconcile_claim_partitions(
        national,
        request.partitions,
        scoped_ids=scoped,
    )
    if not counts_close(reconciliation):
        reasons.add("partition_counts_do_not_close")
    if reconciliation.by_status.get("FAILED", 0):
        reasons.add("failed_partitions")
    if reconciliation.by_status.get("BLOCKED", 0):
        reasons.add("blocked_partitions")
    if reconciliation.by_status.get("UNKNOWN", 0):
        reasons.add("unknown_partitions")
    if any(item.reason == "zero_without_pagination_proof" for item in reconciliation.records):
        reasons.add("zero_without_pagination_proof")

    identity = split_evidence(request.evidence)
    dual_gate = dual_coverage_from_rows(request.evidence)
    reasons.update(identity_reason_codes(identity, dual_gate=dual_gate))

    freshness_status, freshness_reason = evaluate_freshness(request.freshness)
    if freshness_status == FRESHNESS_STALE:
        reasons.add("freshness_stale")

    closed_ok = reconciliation.closed == reconciliation.expected and reconciliation.expected > 0
    if national_claim and not closed_ok:
        reasons.add("national_denominator_incomplete")
    if not national_claim and not closed_ok:
        reasons.add("scoped_partitions_incomplete")

    lkg_status, lkg_triggers, lkg_record = evaluate_lkg(
        request.prior_lkg,
        current_universe=national,
        source_version=request.source_version,
        as_of=request.freshness.as_of,
    )
    reasons.update(lkg_triggers)

    hard_block = bool(
        reasons
        & {
            "inconsistent_scope_geography",
            "inconsistent_denominator_extra_1093",
            "inconsistent_denominator",
            "forbidden_national_denominator",
            "row_count_completeness_forbidden",
            "unmappable_evidence_cannot_drop",
        }
    )
    identity_refuses_yes = dual_gate.get("measurement_success") is False or bool(
        reasons
        & {
            "source_wide_aggregate_without_identity",
            "missing_evidence",
        }
    )

    if "failed_partitions" in reasons:
        state = "FAILED"
    elif hard_block or "blocked_partitions" in reasons:
        state = "BLOCKED"
    elif "freshness_stale" in reasons:
        state = "STALE"
    elif identity_refuses_yes or reasons & {
        "unknown_partitions",
        "zero_without_pagination_proof",
        "national_denominator_incomplete",
        "scoped_partitions_incomplete",
        "partition_counts_do_not_close",
        "source_wide_aggregate_without_identity",
        "missing_evidence",
    }:
        state = "NEEDS_DATA"
    elif national_claim and closed_ok:
        state = "AUTHORIZED"
    elif not national_claim and closed_ok:
        state = "AUTHORIZED_WITH_LIMITATIONS"
        limitations.append("not_a_national_claim")
    else:
        state = "NEEDS_DATA"

    if state == "AUTHORIZED" and limitations:
        state = "AUTHORIZED_WITH_LIMITATIONS"

    if state in {"AUTHORIZED", "AUTHORIZED_WITH_LIMITATIONS"} and identity_refuses_yes:
        state = "NEEDS_DATA"

    current_authorized = state in {"AUTHORIZED", "AUTHORIZED_WITH_LIMITATIONS"}
    view = consumer_view(current_authorized=current_authorized, lkg_status=lkg_status)

    if state == "AUTHORIZED" and national_claim:
        nacional_completo = True
    else:
        nacional_completo = False

    if nacional_completo and (
        "inconsistent_denominator_extra_1093" in reasons
        or "row_count_completeness_forbidden" in reasons
        or identity_refuses_yes
    ):
        nacional_completo = False
        state = "BLOCKED" if "inconsistent_denominator_extra_1093" in reasons else "NEEDS_DATA"
        view = consumer_view(current_authorized=False, lkg_status=lkg_status)

    if state not in AUTHORIZATION_STATES:
        state = "FAILED"

    return _envelope(
        request=request,
        state=state,
        reasons=_ordered_reasons(reasons),
        limitations=tuple(limitations),
        reconciliation=reconciliation,
        identity=identity_report(identity),
        freshness_status=freshness_status,
        freshness_reason=freshness_reason,
        lkg_status=lkg_status,
        lkg_triggers=lkg_triggers,
        dual_gate=dual_gate,
        nacional_completo=nacional_completo,
        consumer_view=view,
        lkg_record=lkg_record,
    )


def _envelope(
    *,
    request: ClaimRequest,
    state: str,
    reasons: tuple[str, ...],
    limitations: tuple[str, ...],
    reconciliation: PartitionReconciliation,
    identity: dict[str, Any],
    freshness_status: str,
    freshness_reason: str,
    lkg_status: str,
    lkg_triggers: tuple[str, ...],
    dual_gate: dict[str, Any],
    nacional_completo: bool = False,
    consumer_view: str = "blocked",
    lkg_record: Any = None,
) -> dict[str, Any]:
    national = request.universes.national
    denominator = reconciliation.expected
    numerator = _numerator(reconciliation)
    coverage_pct = (100.0 * numerator / denominator) if denominator else 0.0
    missingness_pct = 100.0 - coverage_pct
    lkg_ref = None
    if lkg_record is not None:
        lkg_ref = {
            "claim_id": lkg_record.claim_id,
            "content_hash": lkg_record.content_hash,
            "catalog_hash": lkg_record.catalog_hash,
            "expires_at": lkg_record.expires_at,
            "status": lkg_status,
        }
    next_action = reconciliation.next_actions[0] if reconciliation.next_actions else "none"
    if state == "STALE":
        next_action = "refresh_complete_run"
    elif state == "BLOCKED" and "inconsistent_denominator_extra_1093" in reasons:
        next_action = "use_versioned_national_denominator"
    elif state == "NEEDS_DATA" and "unknown_partitions" in reasons:
        next_action = "consult_unknown_partitions"

    payload: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "claim_id": request.claim.claim_id,
        "scope": request.claim.scope,
        "period": request.claim.period,
        "sources": list(request.claim.sources),
        "typology": request.claim.typology,
        "geography": request.claim.geography,
        "snapshot": request.claim.snapshot,
        "cutoff": request.claim.cutoff,
        "national_universe_id": national.universe_id,
        "catalog_hash": national.catalog_hash,
        "numerator": numerator,
        "denominator": denominator,
        "partitions_expected": reconciliation.expected,
        "partitions_attempted": reconciliation.attempted,
        "partitions_closed": reconciliation.closed,
        "coverage_pct": round(coverage_pct, 4),
        "missingness_pct": round(missingness_pct, 4),
        "freshness_status": freshness_status,
        "freshness_reason": freshness_reason,
        "as_of": request.freshness.as_of,
        "source_version": request.source_version,
        "method_version": national.method_version,
        "policy_version": POLICY_VERSION,
        "authorization_state": state,
        "nacional_completo": nacional_completo,
        "consumer_view": consumer_view,
        "limitations": list(limitations),
        "reason_codes": list(reasons),
        "lkg_ref": lkg_ref,
        "lkg_status": lkg_status,
        "invalidation_triggers": list(lkg_triggers),
        "producer_sha": request.producer_sha,
        "universes": {
            "national": universe_to_dict(request.universes.national),
            "icp_commercial": universe_to_dict(request.universes.icp_commercial),
            "extra_1093_monitored": universe_to_dict(request.universes.extra_1093_monitored),
            "observed_corpus": universe_to_dict(request.universes.observed_corpus),
        },
        "partitions": [
            {
                "partition_id": item.partition_id,
                "expected": item.expected,
                "attempted": item.attempted,
                "status": item.status,
                "pages_fetched": item.pages_fetched,
                "pages_expected": item.pages_expected,
                "records": item.records,
                "pagination_complete": item.pagination_complete,
                "request_complete": item.request_complete,
                "raw_ref": item.raw_ref,
                "evidence_ref": item.evidence_ref,
                "checked_at": item.checked_at,
                "as_of": item.as_of,
                "freshness_status": item.freshness_status,
                "identity_mapped": item.identity_mapped,
                "reason": item.reason,
                "next_action": item.next_action,
            }
            for item in reconciliation.records
        ],
        "identity": identity,
        "dual_coverage_gate": {
            "classification": dual_gate.get("classification"),
            "reason": dual_gate.get("reason"),
            "measurement_success": dual_gate.get("measurement_success"),
            "identified_count": dual_gate.get("identified_count"),
            "source_wide_count": dual_gate.get("source_wide_count"),
            "unmapped_count": dual_gate.get("unmapped_count"),
        },
        "blockers": list(reconciliation.blockers),
        "next_action": next_action,
        "extra_1093_used_as_denominator": (
            request.claim.denominator_kind in {"extra_1093_monitored", "extra_commercial_1093"}
            or "inconsistent_denominator_extra_1093" in reasons
        ),
        "observed_corpus_used_as_denominator": request.claim.denominator_kind == "observed_corpus",
        "row_count_used_as_completeness": request.claim.infer_completeness_from_row_count,
    }
    payload["content_hash"] = content_hash(payload)
    return payload
