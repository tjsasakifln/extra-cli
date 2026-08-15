"""Ingest OBSERVED person emails → derive patterns → emit INFERRED candidates.

This path never labels pattern-derived data OBSERVED. One example is not
high certainty. Substantial conflict is AMBIGUOUS. MX is not a mailbox.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from scripts.decision_unit_intelligence.email_discovery import EmailDiscoveryClass, classify_email_discovery
from scripts.decision_unit_intelligence.email_patterns.names import (
    detect_supported_pattern,
    parse_person_name,
    render_pattern_email,
)
from scripts.decision_unit_intelligence.email_patterns.types import (
    INFERRED_PATTERN_DISCOVERY_CLASSES,
    PATTERN_ENGINE_VERSION,
    SUBSTANTIAL_CONFLICT_RATIO,
    EmailPatternPolicy,
    EmailPatternResult,
    InferredGrade,
    InferredPatternState,
    KnownPerson,
    ObservedPersonEmail,
    PatternCandidate,
    PatternRecord,
    PatternState,
    PatternSupportExample,
    TechnicalCheck,
)
from scripts.decision_unit_intelligence.email_resolution import is_third_party_professional_domain
from scripts.decision_unit_intelligence.email_verification import PassiveEmailVerifier
from scripts.decision_unit_intelligence.evidence import assert_not_promoted_to_observed, make_evidence
from scripts.decision_unit_intelligence.models import (
    EpistemicClass,
    FieldEvidence,
    fold_text,
    normalize_email,
    normalize_name,
    now_iso,
)
from scripts.decision_unit_intelligence.reachability import (
    FREEMAIL_DOMAINS,
    email_domain,
    is_brand_mailbox,
    is_generic_mailbox,
    is_role_mailbox,
)


class TechnicalAdapter(Protocol):
    def check(self, email: str, *, smtp_authorized: bool = False) -> TechnicalCheck: ...


@dataclass(frozen=True)
class InjectedTechnicalAdapter:
    """Test/canary adapter. Does not mock the unit under test — only DNS/MX/SMTP."""

    mx_by_domain: dict[str, str]
    catch_all_by_domain: dict[str, str]
    smtp_by_email: dict[str, str] | None = None
    invalid_domains: frozenset[str] = frozenset()

    def check(self, email: str, *, smtp_authorized: bool = False) -> TechnicalCheck:
        normalized = normalize_email(email)
        if not normalized:
            return TechnicalCheck(
                syntax="INVALID",
                domain="UNKNOWN",
                dns="NOT_CHECKED",
                mx="NOT_CHECKED",
                catch_all="UNKNOWN_NOT_PROBED",
                smtp="SKIPPED_POLICY",
                reason_codes=("INVALID_SYNTAX", "SMTP_DISABLED_BY_POLICY"),
            )
        domain = email_domain(normalized) or ""
        if domain in self.invalid_domains:
            return TechnicalCheck(
                syntax="VALID",
                domain=domain,
                dns="NXDOMAIN",
                mx="MISSING",
                catch_all="UNKNOWN_NOT_PROBED",
                smtp="SKIPPED_POLICY",
                reason_codes=("NXDOMAIN", "SMTP_DISABLED_BY_POLICY"),
            )
        mx = self.mx_by_domain.get(domain, "MISSING")
        catch_all = self.catch_all_by_domain.get(domain, "UNKNOWN_NOT_PROBED")
        reasons = ["SYNTAX_VALID"]
        if mx == "MX_PRESENT":
            reasons.append("MX_PRESENT_NOT_MAILBOX_PROOF")
        elif mx == "MISSING":
            reasons.append("NO_MX_OR_ADDRESS_RECORD")
        if catch_all == "CATCH_ALL":
            reasons.append("CATCH_ALL_DOMAIN")
        if smtp_authorized:
            smtp = (self.smtp_by_email or {}).get(normalized, "SKIPPED_POLICY")
            if smtp == "ACCEPTED":
                reasons.append("SMTP_ACCEPT_NOT_IDENTITY_PROOF")
            elif smtp == "SKIPPED_POLICY":
                reasons.append("SMTP_DISABLED_BY_POLICY")
        else:
            smtp = "SKIPPED_POLICY"
            reasons.append("SMTP_DISABLED_BY_POLICY")
        return TechnicalCheck(
            syntax="VALID",
            domain=domain,
            dns="RESOLVED" if mx in {"MX_PRESENT", "IMPLICIT_MX_A"} else "UNKNOWN",
            mx=mx,
            catch_all=catch_all,
            smtp=smtp,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )


class PassiveVerifierAdapter:
    def __init__(self, verifier: PassiveEmailVerifier) -> None:
        self.verifier = verifier

    def check(self, email: str, *, smtp_authorized: bool = False) -> TechnicalCheck:
        report = self.verifier.verify(email)
        reasons = list(report.reason_codes)
        smtp = report.smtp
        if smtp_authorized:
            reasons.append("SMTP_ADAPTER_NOT_WIRED_STAYS_INFERRED")
        else:
            smtp = "SKIPPED_POLICY"
            if "SMTP_DISABLED_BY_POLICY" not in reasons:
                reasons.append("SMTP_DISABLED_BY_POLICY")
        return TechnicalCheck(
            syntax=report.syntax,
            domain=report.domain,
            dns=report.dns,
            mx=report.mx,
            catch_all=report.catch_all,
            smtp=smtp,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )


def _person_key(name: str | None, account_id: str | None = None, person_id: str | None = None) -> str:
    if person_id:
        return person_id
    folded = fold_text(normalize_name(name) or "")
    return f"{account_id or '_'}|{folded}"


def _is_unusable_mailbox(email: str) -> bool:
    return bool(
        is_role_mailbox(email)
        or is_generic_mailbox(email)
        or is_brand_mailbox(email)
        or is_third_party_professional_domain(email_domain(email))
    )


def ingest_observed_person_emails(
    raw: Sequence[ObservedPersonEmail],
    *,
    domain: str | None = None,
) -> tuple[tuple[ObservedPersonEmail, ...], tuple[str, ...]]:
    """Keep only OBSERVED same-domain person mailboxes. Everything else is an exclusion."""
    expected = (domain or "").lower().removeprefix("www.")
    kept: list[ObservedPersonEmail] = []
    exclusions: list[str] = []
    seen: set[str] = set()
    for item in raw:
        email = normalize_email(item.email)
        person = normalize_name(item.person_name)
        item_domain = (email_domain(email) or item.domain or "").lower().removeprefix("www.")
        if item.epistemic_class != EpistemicClass.OBSERVED:
            exclusions.append(f"NOT_OBSERVED:{item.email}")
            continue
        if not email:
            exclusions.append(f"INVALID_EMAIL:{item.email}")
            continue
        if not person:
            exclusions.append(f"NO_PERSON:{email}")
            continue
        if parse_person_name(person) is None:
            exclusions.append(f"UNPARSEABLE_PERSON:{email}")
            continue
        if not item_domain or item_domain in FREEMAIL_DOMAINS:
            exclusions.append(f"NON_CORPORATE_DOMAIN:{email}")
            continue
        if expected and item_domain != expected:
            exclusions.append(f"WRONG_DOMAIN:{email}")
            continue
        if _is_unusable_mailbox(email):
            exclusions.append(f"GENERIC_ROLE_OR_THIRD_PARTY:{email}")
            continue
        key = f"{email}|{_person_key(person, item.account_id, item.person_id)}"
        if key in seen:
            exclusions.append(f"DUPLICATE:{email}")
            continue
        seen.add(key)
        kept.append(
            ObservedPersonEmail(
                email=email,
                person_name=person,
                domain=item_domain,
                source_url=item.source_url,
                observed_at=item.observed_at,
                epistemic_class=EpistemicClass.OBSERVED,
                person_id=item.person_id,
                account_id=item.account_id,
                source_type=item.source_type,
            )
        )
    kept.sort(key=lambda item: (item.domain, item.email, item.person_name or ""))
    return tuple(kept), tuple(exclusions)


def _freshness_score(timestamps: Sequence[str | None]) -> float:
    known = [stamp for stamp in timestamps if stamp]
    if not known:
        return 0.7
    now = datetime.now(UTC)
    ages: list[float] = []
    for stamp in known:
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        ages.append((now - parsed).total_seconds() / 86400.0)
    if not ages:
        return 0.7
    newest = min(ages)
    if newest <= 365:
        return 1.0
    if newest <= 730:
        return 0.7
    return 0.45


def _score_pattern(
    *,
    independent: int,
    consistency: float,
    freshness: float,
    conflicted: bool,
    strong_min: int,
) -> float:
    sample = min(independent / float(strong_min), 1.0)
    score = 0.35 * sample + 0.25 * consistency + 0.20 * freshness + 0.20 * (0.0 if conflicted else 1.0)
    if independent < 2:
        score = min(score, 0.49)
    if conflicted:
        score = min(score, 0.40)
    return round(score, 4)


def derive_domain_patterns(
    ingested: Sequence[ObservedPersonEmail],
    *,
    domain: str,
    exclusions: Sequence[str] = (),
    policy: EmailPatternPolicy | None = None,
) -> tuple[PatternRecord, ...]:
    policy = policy or EmailPatternPolicy()
    usable = [item for item in ingested if item.domain == domain]
    classified: dict[str, list[ObservedPersonEmail]] = defaultdict(list)
    unmatched: list[str] = []
    separators: dict[str, str] = {}
    alias_tokens: dict[str, list[str]] = defaultdict(list)
    for item in usable:
        detected = detect_supported_pattern(item.email, item.person_name)
        if detected is None:
            unmatched.append(f"UNSUPPORTED_SHAPE:{item.email}")
            continue
        pattern_id, separator = detected
        classified[pattern_id].append(item)
        separators.setdefault(pattern_id, separator)
        if pattern_id == "alias":
            alias_tokens[pattern_id].append(item.email.split("@", 1)[0].split(".")[0])

    total = sum(len(items) for items in classified.values())
    independent_by_pattern: dict[str, set[str]] = {}
    for pattern_id, items in classified.items():
        independent_by_pattern[pattern_id] = {
            _person_key(item.person_name, item.account_id, item.person_id) for item in items
        }

    competing_ids = {
        "first.last",
        "firstlast",
        "first_initial+last",
        "first+last_initial",
        "last.first",
        "first",
    }
    substantial = {
        pattern_id: keys
        for pattern_id, keys in independent_by_pattern.items()
        if len(keys) >= 1 and pattern_id in competing_ids
    }
    # Distinct default formats with comparable support are a substantial conflict.
    # Alias / compound-last overlays do not veto the observed default format.
    conflict_ids: set[str] = set()
    ranked = sorted(substantial.items(), key=lambda item: (-len(item[1]), item[0]))
    if len(ranked) >= 2:
        top_id, top_keys = ranked[0]
        for other_id, other_keys in ranked[1:]:
            top_n = len(top_keys)
            other_n = len(other_keys)
            if other_n == 0:
                continue
            ratio = other_n / float(top_n) if top_n else 1.0
            if other_n >= 2 or (other_n >= 1 and top_n <= 2) or ratio >= SUBSTANTIAL_CONFLICT_RATIO:
                conflict_ids.add(top_id)
                conflict_ids.add(other_id)

    records: list[PatternRecord] = []
    for pattern_id, items in sorted(classified.items()):
        independent = independent_by_pattern[pattern_id]
        independent_n = len(independent)
        consistency = round(len(items) / float(total), 4) if total else 0.0
        freshness = _freshness_score([item.observed_at for item in items])
        conflicted = pattern_id in conflict_ids
        if conflicted:
            state = PatternState.PATTERN_AMBIGUOUS
            epistemic = EpistemicClass.INFERRED
            reasons = ["PATTERN_CONFLICT_AMBIGUOUS", "PATTERN_NOT_A_PERSON_FACT"]
        elif independent_n >= policy.strong_min_independent and consistency >= 0.67:
            state = PatternState.PATTERN_STRONG
            epistemic = EpistemicClass.CORROBORATED
            reasons = ["PATTERN_STRONG_MULTI_EXAMPLE", "PATTERN_NOT_A_PERSON_FACT"]
        else:
            state = PatternState.PATTERN_OBSERVED
            epistemic = EpistemicClass.INFERRED
            reasons = ["PATTERN_OBSERVED_NOT_HIGH_CERTAINTY", "PATTERN_NOT_A_PERSON_FACT"]
        if independent_n < 2:
            reasons.append("SINGLE_SAMPLE_PATTERN")
        if unmatched:
            reasons.append("UNMATCHED_SHAPES_EXCLUDED")
        score = _score_pattern(
            independent=independent_n,
            consistency=consistency,
            freshness=freshness,
            conflicted=conflicted,
            strong_min=policy.strong_min_independent,
        )
        examples = tuple(
            PatternSupportExample(
                email=item.email,
                person_name=item.person_name,
                person_id=item.person_id,
                source_url=item.source_url,
                observed_at=item.observed_at,
                account_id=item.account_id,
            )
            for item in items
        )
        records.append(
            PatternRecord(
                pattern_id=pattern_id,
                domain=domain,
                version=policy.pattern_version,
                state=state,
                score=score,
                supporting_examples=examples,
                supporting_emails=tuple(item.email for item in items),
                supporting_people=tuple(dict.fromkeys(item.person_name for item in items)),
                source_urls=tuple(dict.fromkeys(item.source_url or "" for item in items if item.source_url)),
                observed_at=tuple(item.observed_at or "" for item in items),
                exclusions=tuple(exclusions) + tuple(unmatched),
                conflicts=tuple(sorted(conflict_ids - {pattern_id})),
                independent_example_count=independent_n,
                consistency=consistency,
                freshness=freshness,
                reason_codes=tuple(dict.fromkeys(reasons)),
                epistemic_class=epistemic,
                separator=separators.get(pattern_id, ""),
                alias_tokens=tuple(dict.fromkeys(alias_tokens.get(pattern_id, ()))),
            )
        )
    records.sort(key=lambda rec: (-rec.score, rec.pattern_id))
    return tuple(records)


def _emit_for_person(
    person: KnownPerson,
    patterns: Sequence[PatternRecord],
    *,
    domain: str,
    already: set[str],
    policy: EmailPatternPolicy,
) -> list[PatternCandidate]:
    if not person.corroborated or person.already_has_observed_email:
        return []
    parsed = parse_person_name(person.person_name)
    if parsed is None:
        return []
    # Only supported patterns that are not ambiguous. No blind walk of unused shapes.
    usable = [
        record
        for record in patterns
        if record.domain == domain and record.state != PatternState.PATTERN_AMBIGUOUS and record.pattern_id != "alias"
    ]
    # Alias is person-specific: only emit if this person's known alias was actually observed.
    alias_records = [
        record for record in patterns if record.pattern_id == "alias" and record.state != PatternState.PATTERN_AMBIGUOUS
    ]
    emitted: list[PatternCandidate] = []
    for record in usable:
        address = render_pattern_email(
            pattern_id=record.pattern_id,
            parsed=parsed,
            domain=domain,
            separator=record.separator,
        )
        if not address or address in already:
            continue
        already.add(address)
        emitted.append(_candidate_from_pattern(address, person, record, domain))
        if len(emitted) >= policy.candidate_budget:
            return emitted
    for record in alias_records:
        for token in record.alias_tokens:
            if token not in parsed.known_aliases:
                continue
            address = render_pattern_email(
                pattern_id="alias",
                parsed=parsed,
                domain=domain,
                separator=record.separator,
                alias_token=token,
            )
            if not address or address in already:
                continue
            already.add(address)
            emitted.append(_candidate_from_pattern(address, person, record, domain))
            if len(emitted) >= policy.candidate_budget:
                return emitted
    return emitted


def _candidate_from_pattern(
    address: str,
    person: KnownPerson,
    record: PatternRecord,
    domain: str,
) -> PatternCandidate:
    reasons = [
        "INFERRED_FROM_SUPPORTED_PATTERN",
        f"PATTERN:{record.pattern_id}",
        *record.reason_codes,
    ]
    if record.state != PatternState.PATTERN_STRONG:
        reasons.append("NOT_HIGH_CERTAINTY")
    return PatternCandidate(
        email=address,
        person_name=normalize_name(person.person_name) or person.person_name,
        person_id=person.person_id,
        account_id=person.account_id,
        domain=domain,
        pattern_id=record.pattern_id,
        pattern_state=record.state,
        candidate_state=InferredPatternState.INFERRED_PATTERN_EMAIL,
        inferred_grade=InferredGrade.INFERRED_UNVERIFIED,
        epistemic_class=EpistemicClass.INFERRED,
        discovery_class=EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value,
        supporting_emails=record.supporting_emails,
        supporting_people=record.supporting_people,
        source_urls=record.source_urls,
        reason_codes=tuple(dict.fromkeys(reasons)),
        mx_is_not_mailbox_proof=True,
    )


def emit_pattern_candidates(
    *,
    known_people: Sequence[KnownPerson],
    patterns: Sequence[PatternRecord],
    domain: str,
    observed_emails: Sequence[str] = (),
    policy: EmailPatternPolicy | None = None,
) -> tuple[PatternCandidate, ...]:
    policy = policy or EmailPatternPolicy()
    already = {normalize_email(item) or item for item in observed_emails}
    out: list[PatternCandidate] = []
    for person in known_people:
        out.extend(_emit_for_person(person, patterns, domain=domain, already=already, policy=policy))
    out.sort(key=lambda item: (item.person_name or "", item.email, item.pattern_id))
    return tuple(out)


def apply_technical_checks(
    candidates: Sequence[PatternCandidate],
    adapter: TechnicalAdapter,
    *,
    policy: EmailPatternPolicy | None = None,
) -> tuple[PatternCandidate, ...]:
    policy = policy or EmailPatternPolicy()
    updated: list[PatternCandidate] = []
    for candidate in candidates:
        check = adapter.check(candidate.email, smtp_authorized=policy.smtp_authorized)
        reasons = list(candidate.reason_codes) + list(check.reason_codes)
        state = InferredPatternState.INFERRED_PATTERN_EMAIL
        grade = InferredGrade.INFERRED_UNVERIFIED
        discovery = EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value
        if check.syntax == "INVALID" or check.mx in {"MISSING", "NULL_MX"} or check.dns == "NXDOMAIN":
            state = InferredPatternState.INFERRED_PATTERN_REJECTED
            discovery = InferredPatternState.INFERRED_PATTERN_REJECTED.value
            reasons.append("INFERRED_PATTERN_REJECTED")
        elif check.catch_all == "CATCH_ALL":
            state = InferredPatternState.INFERRED_PATTERN_CATCH_ALL
            discovery = InferredPatternState.INFERRED_PATTERN_CATCH_ALL.value
            reasons.append("CATCH_ALL_REDUCES_EVIDENTIARY_VALUE")
        elif check.mx in {"MX_PRESENT", "IMPLICIT_MX_A"}:
            state = InferredPatternState.INFERRED_PATTERN_MX_OK
            discovery = InferredPatternState.INFERRED_PATTERN_MX_OK.value
            reasons.append("MX_PRESENT_NOT_MAILBOX_PROOF")
            if candidate.pattern_state == PatternState.PATTERN_STRONG and candidate.pattern_id != "alias":
                grade = InferredGrade.INFERRED_HIGH
                reasons.append("INFERRED_HIGH_PATTERN_STRONG_AND_MX")
        if check.smtp == "ACCEPTED":
            reasons.append("SMTP_ACCEPT_STILL_INFERRED")
            # SMTP never upgrades to OBSERVED and never becomes HIGH by itself.
        updated.append(
            PatternCandidate(
                email=candidate.email,
                person_name=candidate.person_name,
                person_id=candidate.person_id,
                account_id=candidate.account_id,
                domain=candidate.domain,
                pattern_id=candidate.pattern_id,
                pattern_state=candidate.pattern_state,
                candidate_state=state,
                inferred_grade=grade,
                epistemic_class=EpistemicClass.INFERRED,
                discovery_class=discovery,
                supporting_emails=candidate.supporting_emails,
                supporting_people=candidate.supporting_people,
                source_urls=candidate.source_urls,
                reason_codes=tuple(dict.fromkeys(reasons)),
                technical=check,
                mx_is_not_mailbox_proof=True,
            )
        )
    return tuple(updated)


def candidate_to_evidence(candidate: PatternCandidate) -> FieldEvidence:
    evidence = make_evidence(
        field="email",
        value=candidate.email,
        epistemic_class=EpistemicClass.INFERRED,
        source_type="email_pattern_inference",
        source_url=candidate.source_urls[0] if candidate.source_urls else None,
        extraction_method="org-email-pattern.v1",
        evidence_snippet=";".join(candidate.supporting_emails[:4]),
        extra={
            "pattern_id": candidate.pattern_id,
            "pattern_state": candidate.pattern_state.value,
            "candidate_state": candidate.candidate_state.value,
            "inferred_grade": candidate.inferred_grade.value,
            "reason_codes": list(candidate.reason_codes),
        },
    )
    assert_not_promoted_to_observed(evidence)
    assert_pattern_not_promoted_to_observed(
        evidence.epistemic_class,
        evidence.extraction_method or "",
    )
    return evidence


def assert_pattern_not_promoted_to_observed(
    epistemic: EpistemicClass | str,
    method: str = "org-email-pattern.v1",
) -> None:
    value = epistemic.value if isinstance(epistemic, EpistemicClass) else str(epistemic)
    if value == EpistemicClass.OBSERVED.value:
        raise ValueError(f"refusing OBSERVED label for pattern-derived method {method!r}")
    lowered = method.lower()
    if "pattern" in lowered and value == EpistemicClass.OBSERVED.value:
        raise ValueError(f"pattern method {method!r} cannot be OBSERVED")


def is_inferred_pattern_discovery_class(klass: str | EmailDiscoveryClass | None) -> bool:
    value = klass.value if isinstance(klass, EmailDiscoveryClass) else str(klass or "")
    return value in INFERRED_PATTERN_DISCOVERY_CLASSES or value.startswith("INFERRED_PATTERN_")


def run_email_patterns(
    *,
    observed: Sequence[ObservedPersonEmail],
    known_people: Sequence[KnownPerson],
    domain: str | None = None,
    policy: EmailPatternPolicy | None = None,
    technical: TechnicalAdapter | None = None,
) -> EmailPatternResult:
    policy = policy or EmailPatternPolicy()
    ingested, exclusions = ingest_observed_person_emails(observed, domain=domain)
    target = (domain or (ingested[0].domain if ingested else None) or "").lower().removeprefix("www.")
    if not target:
        return EmailPatternResult(
            domain=None,
            ingested=ingested,
            exclusions=exclusions,
            reason_codes=("NO_CORPORATE_DOMAIN",),
            policy=policy,
        )
    patterns = derive_domain_patterns(ingested, domain=target, exclusions=exclusions, policy=policy)
    observed_emails = [item.email for item in ingested]
    # People who already own an observed mailbox on this domain are not inference targets.
    owned_keys = {_person_key(item.person_name, item.account_id, item.person_id) for item in ingested}
    targets: list[KnownPerson] = []
    for person in known_people:
        key = _person_key(person.person_name, person.account_id, person.person_id)
        has_observed = person.already_has_observed_email or key in owned_keys
        targets.append(
            KnownPerson(
                person_name=person.person_name,
                corroborated=person.corroborated,
                person_id=person.person_id,
                account_id=person.account_id,
                already_has_observed_email=has_observed,
            )
        )
    candidates = emit_pattern_candidates(
        known_people=targets,
        patterns=patterns,
        domain=target,
        observed_emails=observed_emails,
        policy=policy,
    )
    if technical is not None:
        candidates = apply_technical_checks(candidates, technical, policy=policy)
    for record in patterns:
        assert_pattern_not_promoted_to_observed(record.epistemic_class, "org-email-pattern.v1")
    for candidate in candidates:
        assert_pattern_not_promoted_to_observed(candidate.epistemic_class, "org-email-pattern.v1")
        classify_email_discovery(
            candidate.email,
            epistemic=candidate.epistemic_class,
            inferred_pattern=True,
        )
    return EmailPatternResult(
        domain=target,
        ingested=ingested,
        exclusions=exclusions,
        patterns=patterns,
        candidates=candidates,
        reason_codes=("PATTERN_ENGINE_OK", PATTERN_ENGINE_VERSION),
        policy=policy,
    )


def default_technical_adapter() -> Callable[[], TechnicalAdapter] | None:
    return None


def result_checked_at() -> str:
    return now_iso()
