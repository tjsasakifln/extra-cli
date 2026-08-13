"""Contact discovery coverage over TARGET_CONFIRMED / ACTIONABLE_NOW reservoir.

Measures attempted vs never attempted — never accept "41 send-ready" without
answering "41 of how many companies effectively enriched?".

Continuous enrichment should advance the reservoir without hard cap at 50.
`max_companies` on batch runners is a smoke/batch bound only.
"""

from __future__ import annotations

from typing import Any

# Pilot quality sample — NOT system capacity.
MINIMUM_PILOT_ACCEPTANCE_SAMPLE = 50


def measure_contact_coverage(
    *,
    population_keys: list[str] | set[str],
    attempted_keys: list[str] | set[str],
    real_email_keys: list[str] | set[str] | None = None,
    company_owned_keys: list[str] | set[str] | None = None,
    identity_safe_keys: list[str] | set[str] | None = None,
    email_send_ready_keys: list[str] | set[str] | None = None,
    rejection_reasons: dict[str, int] | None = None,
    population_name: str = "TARGET_CONFIRMED",
) -> dict[str, Any]:
    """Closed-sum contact coverage metrics for the commercial reservoir."""
    population = {str(k) for k in population_keys}
    attempted = {str(k) for k in attempted_keys}
    real_email = {str(k) for k in (real_email_keys or [])}
    company_owned = {str(k) for k in (company_owned_keys or [])}
    identity_safe = {str(k) for k in (identity_safe_keys or [])}
    send_ready = {str(k) for k in (email_send_ready_keys or [])}

    never = population - attempted
    attempted_in_population = attempted & population
    real_in_population = real_email & population
    owned_in_population = company_owned & population
    identity_in_population = identity_safe & population
    esr_in_population = send_ready & population

    n_population = len(population)
    n_att = len(attempted_in_population)
    n_never = len(never)

    def _rate(num: int, den: int) -> float | None:
        if den <= 0:
            return None
        return float(num) / float(den)

    reasons = dict(rejection_reasons or {})
    # Ensure standard buckets exist (0 if unknown) — no silent holes
    for key in (
        "no_email_found",
        "identity_rejected",
        "third_party_rejected",
        "mailbox_purpose_rejected",
        "provenance_rejected",
        "network_failure",
        "crawl_failure",
        "no_official_domain",
    ):
        reasons.setdefault(key, 0)

    population_key = str(population_name or "TARGET_CONFIRMED").strip().upper()
    result = {
        "schema": "confenge.contact_coverage.v1",
        "population_name": population_key,
        "population_total": n_population,
        "contact_discovery_attempted": n_att,
        "contact_discovery_not_attempted": n_never,
        "contact_discovery_attempt_rate": _rate(n_att, n_population),
        "real_email_found": len(real_in_population),
        "real_email_rate_of_attempted": _rate(len(real_in_population), n_att),
        "company_owned_email": len(owned_in_population),
        "identity_safe": len(identity_in_population),
        "email_send_ready": len(esr_in_population),
        "email_send_ready_of_population": _rate(len(esr_in_population), n_population),
        "email_send_ready_of_attempted": _rate(len(esr_in_population), n_att),
        "rejection_reasons": reasons,
        "MINIMUM_PILOT_ACCEPTANCE_SAMPLE": MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
        "pilot_sample_met": len(esr_in_population) >= MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
        "note": (
            "EMAIL_SEND_READY reservoir is not capped at 50. "
            "50 is MINIMUM_PILOT_ACCEPTANCE_SAMPLE only."
        ),
        "closed_sum_check": {
            "population_eq_attempted_plus_never": n_population == n_att + n_never,
            "attempted_subset_of_population": attempted <= population,
        },
    }
    if population_key == "TARGET_CONFIRMED":
        result["TARGET_CONFIRMED_total"] = n_population
        result["email_send_ready_of_confirmed"] = _rate(
            len(esr_in_population), n_population
        )
        result["closed_sum_check"].update(
            {
                "confirmed_eq_attempted_plus_never": n_population == n_att + n_never,
                "attempted_subset_of_confirmed": attempted <= population,
            }
        )
    return result


def assert_no_send_ready_hard_cap(limit: int | None, *, context: str = "") -> None:
    """Fail closed if operational code tries to treat 50 as reservoir capacity."""
    if limit is None:
        return
    if int(limit) == MINIMUM_PILOT_ACCEPTANCE_SAMPLE:
        raise ValueError(
            f"Refusing operational hard cap of {limit} on commercial reservoir "
            f"({context}). Use MINIMUM_PILOT_ACCEPTANCE_SAMPLE only as a quality "
            "sample size, never as EMAIL_SEND_READY capacity."
        )
