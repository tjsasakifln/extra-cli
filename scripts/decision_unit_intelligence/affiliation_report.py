"""Track A cohort / uplift / contradictions reporter for affiliation corroboration.

Honest delta of 0 is allowed. Fabricated positive delta is not. The reporter
never invents people, cargos, or empresas.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.decision_unit_intelligence.affiliation_policy import (
    COHORT_SCHEMA_ID,
    POLICY_ID,
    AffiliationReasonCode,
)
from scripts.decision_unit_intelligence.corroboration import (
    AffiliationCorroboration,
    CandidatePerson,
    corroborate_affiliation,
    email_association_gate,
    evidence_items_from_observations,
)
from scripts.decision_unit_intelligence.email_discovery import EmailDiscoveryClass
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    PersonObservation,
    normalize_cnpj,
    normalize_name,
)

AS_OF_CANARY = "2026-08-15"

PREVIOUSLY_AMBIGUOUS_CLASSES = frozenset(
    {
        EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_UNRESOLVED.value,
        EmailDiscoveryClass.UNKNOWN.value,
    }
)


def corroborate_account_people(
    account: AccountInvestigation,
    *,
    as_of: str = AS_OF_CANARY,
    people: list[PersonObservation] | None = None,
) -> list[AffiliationCorroboration]:
    """Build isolated corroboration records from account candidates + observations."""
    observations = list(people or [])
    if not observations:
        for payload in (account.extra or {}).get("person_observations") or []:
            if isinstance(payload, PersonObservation):
                observations.append(payload)
    records: list[AffiliationCorroboration] = []
    for candidate in account.candidates:
        name = normalize_name(candidate.person_name)
        if not name:
            continue
        person_obs = [
            obs
            for obs in observations
            if normalize_name(obs.person_name) == name
            and normalize_cnpj(obs.company_entity_id) == normalize_cnpj(account.cnpj)
        ]
        stored = (candidate.extra or {}).get("source_observations")
        if not person_obs and stored:
            person_obs = [obs for obs in stored if isinstance(obs, PersonObservation)]
        items = evidence_items_from_observations(
            person_obs,
            company_name=account.legal_name,
            company_kind=(candidate.extra or {}).get("company_kind"),
        )
        # Recover evidence already attached to the corroboration snapshot.
        if not items and isinstance((candidate.extra or {}).get("affiliation_corroboration"), dict):
            existing = candidate.extra["affiliation_corroboration"]
            records.append(_record_from_dict(existing))
            continue
        person = CandidatePerson(
            canonical_name=name,
            aliases=list((candidate.extra or {}).get("aliases") or []),
            target_company_cnpj=account.cnpj,
            target_company_name=account.legal_name,
            claimed_role=candidate.observed_roles[0] if candidate.observed_roles else None,
        )
        records.append(corroborate_affiliation(person, items, as_of=as_of))
    return records


def _record_from_dict(payload: dict[str, Any]) -> AffiliationCorroboration:
    from scripts.decision_unit_intelligence.corroboration import (
        AffiliationContradiction,
        DatedEvidenceItem,
        FieldConfidenceRecord,
        RoleCandidate,
    )
    from scripts.decision_unit_intelligence.models import ConfidenceLevel

    def _level(value: str) -> ConfidenceLevel:
        try:
            return ConfidenceLevel(value)
        except ValueError:
            return ConfidenceLevel.UNKNOWN

    return AffiliationCorroboration(
        person_id=str(payload.get("person_id") or ""),
        canonical_name=str(payload.get("canonical_name") or ""),
        aliases=list(payload.get("aliases") or []),
        company_cnpj=str(payload.get("company_cnpj") or ""),
        company_name=payload.get("company_name"),
        company_kind=payload.get("company_kind"),
        role_candidates=[
            RoleCandidate(
                role_text=str(item.get("role_text") or ""),
                canonical_role=item.get("canonical_role"),
                source_ids=list(item.get("source_ids") or []),
                evidence_date=item.get("evidence_date"),
                origin_ids=list(item.get("origin_ids") or []),
            )
            for item in payload.get("role_candidates") or []
        ],
        canonical_decision_role=payload.get("canonical_decision_role"),
        evidence=[
            DatedEvidenceItem(
                evidence_id=str(item.get("evidence_id") or ""),
                source_type=str(item.get("source_type") or ""),
                field=str(item.get("field") or ""),
                value=item.get("value"),
                source_url=item.get("source_url"),
                origin_id=item.get("origin_id"),
                document_id=item.get("document_id"),
                observed_at=item.get("observed_at"),
                published_at=item.get("published_at"),
                snippet=item.get("snippet"),
                company_cnpj=item.get("company_cnpj"),
                company_name=item.get("company_name"),
                role_text=item.get("role_text"),
                entity_kind=item.get("entity_kind"),
                stale_signal=item.get("stale_signal"),
                extraction_method=item.get("extraction_method"),
                extra=dict(item.get("extra") or {}),
            )
            for item in payload.get("evidence") or []
        ],
        rejected_evidence=list(payload.get("rejected_evidence") or []),
        contradictions=[
            AffiliationContradiction(
                topic=str(item.get("topic") or ""),
                left=str(item.get("left") or ""),
                right=str(item.get("right") or ""),
                reason_codes=list(item.get("reason_codes") or []),
                evidence_ids=list(item.get("evidence_ids") or []),
            )
            for item in payload.get("contradictions") or []
        ],
        identity_confidence=_level(str(payload.get("identity_confidence") or "UNKNOWN")),
        affiliation_confidence=_level(str(payload.get("affiliation_confidence") or "UNKNOWN")),
        role_confidence=_level(str(payload.get("role_confidence") or "UNKNOWN")),
        recency_confidence=_level(str(payload.get("recency_confidence") or "UNKNOWN")),
        reason_codes=list(payload.get("reason_codes") or []),
        association_allowed=bool(payload.get("association_allowed")),
        stop_reasons=list(payload.get("stop_reasons") or []),
        field_records=[
            FieldConfidenceRecord(
                field=str(item.get("field") or ""),
                level=_level(str(item.get("level") or "UNKNOWN")),
                reason_codes=list(item.get("reason_codes") or []),
                independent_origin_count=int(item.get("independent_origin_count") or 0),
                latest_evidence_date=item.get("latest_evidence_date"),
            )
            for item in payload.get("field_records") or []
        ],
    )


def _email_class(route: Any) -> str:
    extra = getattr(route, "extra", None) or {}
    klass = extra.get("email_discovery_class")
    if klass:
        return str(klass)
    value = getattr(route, "channel_value", None)
    if value and "@" in str(value):
        return EmailDiscoveryClass.UNKNOWN.value
    return ""


def _is_named_email(route: Any) -> bool:
    value = getattr(route, "channel_value", None)
    return bool(value and "@" in str(value))


def build_affiliation_cohort_report(
    accounts: list[AccountInvestigation],
    *,
    as_of: str = AS_OF_CANARY,
    people_by_cnpj: dict[str, list[PersonObservation]] | None = None,
) -> dict[str, Any]:
    """Deterministic cohort + uplift + contradictions + next recommendation."""
    people_by_cnpj = people_by_cnpj or {}
    rows: list[dict[str, Any]] = []
    remaining = Counter()
    contradictions: list[dict[str, Any]] = []
    prev_ambiguous = 0
    now_associable = 0
    refused = 0
    qsa_only_people = 0
    for account in accounts:
        cnpj = normalize_cnpj(account.cnpj)
        records = []
        stored = (account.extra or {}).get("affiliation_corroboration")
        if isinstance(stored, list) and stored and isinstance(stored[0], dict):
            records = [_record_from_dict(item) for item in stored]
        else:
            records = corroborate_account_people(
                account,
                as_of=as_of,
                people=people_by_cnpj.get(cnpj) or [],
            )
        person_rows = []
        for record in records:
            person_rows.append(
                {
                    "person_id": record.person_id,
                    "canonical_name": record.canonical_name,
                    "company_cnpj": record.company_cnpj,
                    "identity_confidence": record.identity_confidence.value,
                    "affiliation_confidence": record.affiliation_confidence.value,
                    "role_confidence": record.role_confidence.value,
                    "recency_confidence": record.recency_confidence.value,
                    "reason_codes": list(record.reason_codes),
                    "association_allowed": record.association_allowed,
                    "canonical_decision_role": record.canonical_decision_role,
                    "contradictions": [item.to_dict() for item in record.contradictions],
                }
            )
            for code in record.reason_codes:
                if code in {
                    AffiliationReasonCode.QSA_ONLY.value,
                    AffiliationReasonCode.INSUFFICIENT_RECENCY.value,
                    AffiliationReasonCode.CONFLICTING_EVIDENCE.value,
                    AffiliationReasonCode.CONFLICTING_ROLE.value,
                    AffiliationReasonCode.STALE_AFFILIATION.value,
                    AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value,
                }:
                    remaining[code] += 1
            if AffiliationReasonCode.QSA_ONLY.value in record.reason_codes:
                qsa_only_people += 1
            for item in record.contradictions:
                contradictions.append(
                    {
                        "cnpj": cnpj,
                        "person_name": record.canonical_name,
                        **item.to_dict(),
                    }
                )
        account_prev = 0
        account_now = 0
        account_refused = 0
        email_rows = []
        by_name = {normalize_name(record.canonical_name): record for record in records}
        for route in account.routes:
            if not _is_named_email(route):
                continue
            extra = route.extra or {}
            klass = _email_class(route)
            previously = (
                klass in PREVIOUSLY_AMBIGUOUS_CLASSES
                or bool(extra.get("identity_ambiguous"))
                or (
                    klass == EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_UNRESOLVED.value
                )
            )
            person_name = normalize_name(getattr(route, "person_name", None))
            record = by_name.get(person_name) if person_name else None
            if record is None and account.candidates:
                # Unresolved email: try matching via extra association name.
                assoc_name = normalize_name(extra.get("associated_person_name"))
                record = by_name.get(assoc_name) if assoc_name else None
            gate_allowed = False
            gate_codes: list[str] = []
            if record is not None:
                decision = email_association_gate(record, email=route.channel_value)
                gate_allowed = decision.allowed
                gate_codes = list(decision.reason_codes)
                if decision.stop_the_line or not decision.allowed:
                    account_refused += 1
            if previously:
                account_prev += 1
            if previously and gate_allowed:
                account_now += 1
            email_rows.append(
                {
                    "email": route.channel_value,
                    "discovery_class": klass,
                    "previously_unresolved_or_ambiguous": previously,
                    "now_defensibly_associable": bool(previously and gate_allowed),
                    "gate_allowed": gate_allowed,
                    "gate_reason_codes": gate_codes,
                }
            )
        prev_ambiguous += account_prev
        now_associable += account_now
        refused += account_refused
        rows.append(
            {
                "cnpj": cnpj,
                "legal_name": account.legal_name,
                "people": person_rows,
                "emails": {
                    "previously_unresolved_or_ambiguous": account_prev,
                    "now_defensibly_associable": account_now,
                    "refused_stop_the_line": account_refused,
                    "items": email_rows,
                },
                "reason_codes": sorted({code for record in records for code in record.reason_codes}),
            }
        )
    delta = now_associable  # previously ambiguous that are now associable
    next_rec = _next_recommendation(
        n=len(accounts),
        delta=delta,
        remaining=remaining,
        qsa_only_people=qsa_only_people,
    )
    return {
        "schema_id": COHORT_SCHEMA_ID,
        "policy_id": POLICY_ID,
        "as_of": as_of,
        "n": len(accounts),
        "cnpjs": [normalize_cnpj(account.cnpj) for account in accounts],
        "accounts": rows,
        "uplift": {
            "previously_identity_unresolved_or_ambiguous": prev_ambiguous,
            "now_defensibly_associable": now_associable,
            "delta": delta,
            "refused_stop_the_line": refused,
            "note": (
                "Delta counts only emails that were identity-unresolved/ambiguous "
                "and become associable when corroboration allows. Honest 0 is valid."
            ),
        },
        "contradictions": contradictions,
        "remaining_blockers": {
            AffiliationReasonCode.QSA_ONLY.value: remaining[AffiliationReasonCode.QSA_ONLY.value],
            AffiliationReasonCode.INSUFFICIENT_RECENCY.value: remaining[
                AffiliationReasonCode.INSUFFICIENT_RECENCY.value
            ],
            AffiliationReasonCode.CONFLICTING_EVIDENCE.value: remaining[
                AffiliationReasonCode.CONFLICTING_EVIDENCE.value
            ],
            AffiliationReasonCode.CONFLICTING_ROLE.value: remaining[AffiliationReasonCode.CONFLICTING_ROLE.value],
            AffiliationReasonCode.STALE_AFFILIATION.value: remaining[AffiliationReasonCode.STALE_AFFILIATION.value],
            AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value: remaining[
                AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value
            ],
        },
        "qsa_only_people": qsa_only_people,
        "next_recommendation": next_rec,
        "auto_send": False,
        "invented_cargo_or_empresa": False,
    }


def _next_recommendation(*, n: int, delta: int, remaining: Counter, qsa_only_people: int) -> str:
    if n == 0:
        return "Sem contas no cohort."
    if delta == 0 and remaining[AffiliationReasonCode.QSA_ONLY.value] >= 1:
        return (
            "Track A permanece majoritariamente QSA + caixa genérica. "
            "Próximo passo: evidência pública datada e independente "
            "(site/equipe, diário oficial, processo, associação) por pessoa, "
            "sem tratar QSA como comprador e sem inventar cargo ou empresa."
        )
    if remaining[AffiliationReasonCode.CONFLICTING_EVIDENCE.value] or remaining[
        AffiliationReasonCode.CONFLICTING_ROLE.value
    ]:
        return (
            "Há contradições explícitas de vínculo ou cargo. "
            "Não associar email até uma fonte pública atual resolver o conflito; "
            "não fazer média de confiança."
        )
    if delta > 0:
        return (
            f"{delta} email(s) antes ambíguos tornaram-se associáveis com corroboração. "
            "Manter o gate no promotor; não promover para EMAIL_VALIDATED nem auto_send."
        )
    return (
        "Nenhum email nominal passou o gate de corroboração. "
        "Continuar coletando evidência pública datada; QSA permanece cadastral."
    )


def verdicts_for_compare(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Stable per-account verdicts used to assert canary determinism."""
    rows = []
    for account in report.get("accounts") or []:
        people = [
            {
                "name": person.get("canonical_name"),
                "identity": person.get("identity_confidence"),
                "affiliation": person.get("affiliation_confidence"),
                "role": person.get("role_confidence"),
                "recency": person.get("recency_confidence"),
                "reason_codes": person.get("reason_codes"),
                "association_allowed": person.get("association_allowed"),
            }
            for person in account.get("people") or []
        ]
        people.sort(key=lambda item: item["name"] or "")
        rows.append({"cnpj": account.get("cnpj"), "people": people})
    rows.sort(key=lambda item: item["cnpj"] or "")
    return rows
