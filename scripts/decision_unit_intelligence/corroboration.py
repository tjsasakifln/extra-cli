"""Isolated current-affiliation corroboration.

Pure transform: candidate person + dated public evidence → per-field
confidences, reason codes, and contradictions. Never invents cargo or
empresa. Never promotes email. Highest confidence does not erase
disagreement — contradiction is CONFLICTING_EVIDENCE, never an average.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

from scripts.decision_unit_intelligence.affiliation_policy import (
    ASSOCIATION_REFUSED_WHEN,
    DATA_BROKER_HOST_MARKERS,
    FORBIDDEN_SOURCE_TYPES,
    OWNERSHIP_ROLE_CLASSES,
    POLICY_ID,
    QSA_ECHO_HOST_MARKERS,
    QSA_SOURCE_TYPES,
    RECENCY_AGING_DAYS,
    RECENCY_FRESH_DAYS,
    SCHEMA_ID,
    SOURCE_TYPE_CLASS,
    SPECIFIC_EXECUTIVE_ROLE_CLASSES,
    STALE_SIGNAL_PATTERNS,
    STOP_THE_LINE_CODES,
    SYNDICATION_HOST_MARKERS,
    AffiliationReasonCode,
    AllowedSourceClass,
    EntityKind,
    ForbiddenSourceClass,
)
from scripts.decision_unit_intelligence.decision_policy import (
    is_legal_entity_name,
    normalize_observed_role,
)
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ConfidenceLevel,
    ConflictRecord,
    DecisionRoleClass,
    EpistemicClass,
    PersonObservation,
    fold_text,
    normalize_cnpj,
    normalize_name,
    stable_id,
)


def independent_source_count(items: list[PersonObservation | ChannelObservation]) -> int:
    keys = set()
    for item in items:
        keys.add((item.source_type, item.source_url or item.document_id or item.observation_id))
    return len(keys)


def detect_person_conflicts(observations: list[PersonObservation]) -> list[ConflictRecord]:
    conflicts: list[ConflictRecord] = []
    by_name: dict[str, list[PersonObservation]] = defaultdict(list)
    for obs in observations:
        if obs.person_name:
            by_name[obs.person_name.strip().lower()].append(obs)
    for name, group in by_name.items():
        roles = {(g.normalized_role_class.value, g.observed_role) for g in group}
        if len({r[0] for r in roles if r[0] != "unknown"}) > 1:
            values = sorted({r[0] for r in roles})
            conflicts.append(
                ConflictRecord(
                    conflict_id=stable_id("role", name, *values),
                    topic="role",
                    left=values[0],
                    right=values[1],
                    resolution="PRESERVE_BOTH",
                    reason_codes=["CONFLICTING_OBSERVED_ROLES"],
                )
            )
    return conflicts


def detect_channel_conflicts(observations: list[ChannelObservation]) -> list[ConflictRecord]:
    conflicts: list[ConflictRecord] = []
    emails = [o for o in observations if o.channel_value and "@" in o.channel_value]
    by_person: dict[str, set[str]] = defaultdict(set)
    for obs in emails:
        if obs.person_name and obs.epistemic_class != EpistemicClass.INFERRED:
            by_person[obs.person_name.strip().lower()].add((obs.channel_value or "").lower())
    for person, addrs in by_person.items():
        if len(addrs) > 1:
            values = sorted(addrs)
            conflicts.append(
                ConflictRecord(
                    conflict_id=stable_id("email", person, *values),
                    topic="email",
                    left=values[0],
                    right=values[1],
                    resolution="PRESERVE_BOTH",
                    reason_codes=["MULTIPLE_OBSERVED_EMAILS"],
                )
            )
    return conflicts


def evidence_quality_label(*, source_count: int, has_document: bool, contradicted: bool) -> str:
    if contradicted:
        return "LOW"
    if source_count >= 2 and has_document:
        return "HIGH"
    if source_count >= 1 and has_document:
        return "MEDIUM"
    if source_count >= 1:
        return "LOW"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Isolated affiliation corroboration
# ---------------------------------------------------------------------------

_STALE_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.I), label) for pattern, label in STALE_SIGNAL_PATTERNS
)
_HOLDING_RE = re.compile(r"holding|participa[cç][oõ]es|administradora de bens", re.I)
_OPERATIONAL_RE = re.compile(
    r"engenharia|construtora|constru[cç][oõ]es|paviment|terraplan|minera[cç]|incorporadora|empreiteira",
    re.I,
)
_UNIT_RE = re.compile(r"\b(?:filial|unidade|sucursal|regional)\b", re.I)
_BRAND_RE = re.compile(r"\b(?:marca|brand)\b", re.I)
_CONSORTIUM_RE = re.compile(r"cons[oó]rcio|\bspe\b", re.I)


@dataclass
class DatedEvidenceItem:
    """One dated public observation about identity, affiliation, or role."""

    evidence_id: str
    source_type: str
    field: str
    value: str | None = None
    source_url: str | None = None
    origin_id: str | None = None
    document_id: str | None = None
    observed_at: str | None = None
    published_at: str | None = None
    snippet: str | None = None
    company_cnpj: str | None = None
    company_name: str | None = None
    role_text: str | None = None
    entity_kind: str | None = None
    stale_signal: str | None = None
    extraction_method: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidatePerson:
    """Person the caller wants to place at a target company. Never invent names."""

    canonical_name: str
    target_company_cnpj: str
    target_company_name: str | None = None
    aliases: list[str] = field(default_factory=list)
    claimed_role: str | None = None
    target_entity_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RoleCandidate:
    role_text: str
    canonical_role: str | None
    source_ids: list[str]
    evidence_date: str | None
    origin_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FieldConfidenceRecord:
    field: str
    level: ConfidenceLevel
    reason_codes: list[str]
    independent_origin_count: int
    latest_evidence_date: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["level"] = self.level.value
        return payload


@dataclass
class AffiliationContradiction:
    topic: str
    left: str
    right: str
    reason_codes: list[str]
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmailAssociationDecision:
    """Gate for the email promoter. Does not promote, validate, or send email."""

    allowed: bool
    stop_the_line: bool
    reason_codes: tuple[str, ...]
    person_name: str
    company_cnpj: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "stop_the_line": self.stop_the_line,
            "reason_codes": list(self.reason_codes),
            "person_name": self.person_name,
            "company_cnpj": self.company_cnpj,
            "promotes_email": False,
            "marks_email_validated": False,
            "auto_send": False,
        }


@dataclass
class AffiliationCorroboration:
    """Per-person current-affiliation record. Isolated from email promotion."""

    person_id: str
    canonical_name: str
    aliases: list[str]
    company_cnpj: str
    company_name: str | None
    company_kind: str | None
    role_candidates: list[RoleCandidate]
    canonical_decision_role: str | None
    evidence: list[DatedEvidenceItem]
    rejected_evidence: list[dict[str, Any]]
    contradictions: list[AffiliationContradiction]
    identity_confidence: ConfidenceLevel
    affiliation_confidence: ConfidenceLevel
    role_confidence: ConfidenceLevel
    recency_confidence: ConfidenceLevel
    reason_codes: list[str]
    association_allowed: bool
    stop_reasons: list[str]
    field_records: list[FieldConfidenceRecord]
    policy_id: str = POLICY_ID
    schema_id: str = SCHEMA_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "policy_id": self.policy_id,
            "person_id": self.person_id,
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "company_cnpj": self.company_cnpj,
            "company_name": self.company_name,
            "company_kind": self.company_kind,
            "role_candidates": [item.to_dict() for item in self.role_candidates],
            "canonical_decision_role": self.canonical_decision_role,
            "evidence": [item.to_dict() for item in self.evidence],
            "rejected_evidence": list(self.rejected_evidence),
            "contradictions": [item.to_dict() for item in self.contradictions],
            "identity_confidence": self.identity_confidence.value,
            "affiliation_confidence": self.affiliation_confidence.value,
            "role_confidence": self.role_confidence.value,
            "recency_confidence": self.recency_confidence.value,
            "reason_codes": list(self.reason_codes),
            "association_allowed": self.association_allowed,
            "stop_reasons": list(self.stop_reasons),
            "field_records": [item.to_dict() for item in self.field_records],
            "promotes_email": False,
        }


def classify_source_type(source_type: str | None) -> str | None:
    raw = fold_text(source_type)
    if not raw:
        return None
    if raw in FORBIDDEN_SOURCE_TYPES or source_type in FORBIDDEN_SOURCE_TYPES:
        return None
    return SOURCE_TYPE_CLASS.get(raw) or SOURCE_TYPE_CLASS.get(source_type or "")


def host_of(url: str | None) -> str:
    if not url:
        return ""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_forbidden_source(item: DatedEvidenceItem) -> tuple[bool, str | None]:
    raw = fold_text(item.source_type)
    method = fold_text(item.extraction_method)
    if raw in FORBIDDEN_SOURCE_TYPES or item.source_type in FORBIDDEN_SOURCE_TYPES:
        return True, item.source_type
    if "authenticated" in raw and "linkedin" in raw:
        return True, ForbiddenSourceClass.AUTHENTICATED_LINKEDIN.value
    if "linkedin_scrape" in raw or "linkedin_authenticated" in raw:
        return True, ForbiddenSourceClass.AUTHENTICATED_LINKEDIN.value
    if any(tok in method for tok in ("local_part", "local-part", "cargo_from_local")):
        return True, ForbiddenSourceClass.LOCAL_PART_AS_ROLE.value
    if raw in {"local_part_as_role", "cargo_from_local_part", "local_part_as_cargo"}:
        return True, ForbiddenSourceClass.LOCAL_PART_AS_ROLE.value
    host = host_of(item.source_url)
    if any(marker in host for marker in DATA_BROKER_HOST_MARKERS):
        return True, ForbiddenSourceClass.DATA_BROKER.value
    if item.field == "identity" and is_legal_entity_name(item.value):
        return True, ForbiddenSourceClass.QSA_PJ_AS_PERSON.value
    if raw == ForbiddenSourceClass.QSA_PJ_AS_PERSON.value:
        return True, ForbiddenSourceClass.QSA_PJ_AS_PERSON.value
    return False, None


def is_qsa_source(item: DatedEvidenceItem) -> bool:
    raw = fold_text(item.source_type)
    if raw in QSA_SOURCE_TYPES or item.source_type in QSA_SOURCE_TYPES:
        return True
    if classify_source_type(item.source_type) == AllowedSourceClass.QSA_CADASTRE.value:
        return True
    host = host_of(item.source_url)
    return any(marker in host for marker in QSA_ECHO_HOST_MARKERS)


def detect_entity_kind(name: str | None, *, explicit: str | None = None) -> str:
    if explicit and explicit in {kind.value for kind in EntityKind}:
        return explicit
    text = fold_text(name)
    if not text:
        return EntityKind.UNKNOWN.value
    if _CONSORTIUM_RE.search(text):
        return EntityKind.CONSORTIUM.value
    if _HOLDING_RE.search(text):
        return EntityKind.HOLDING.value
    if _UNIT_RE.search(text):
        return EntityKind.UNIT.value
    if _BRAND_RE.search(text):
        return EntityKind.BRAND.value
    if _OPERATIONAL_RE.search(text):
        return EntityKind.OPERATIONAL.value
    return EntityKind.UNKNOWN.value


def detect_stale_signals(*blobs: str | None) -> list[str]:
    text = " ".join(blob for blob in blobs if blob)
    if not text:
        return []
    hits: list[str] = []
    for pattern, label in _STALE_COMPILED:
        if pattern.search(text):
            hits.append(label)
    return list(dict.fromkeys(hits))


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if "T" in raw:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.date()
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def evidence_date_of(item: DatedEvidenceItem) -> date | None:
    return parse_iso_date(item.published_at) or parse_iso_date(item.observed_at)


def independence_origin(item: DatedEvidenceItem) -> str:
    """Cluster by origin, not URL count. Copies of one origin share a key."""
    if item.origin_id:
        return fold_text(item.origin_id)
    extra = item.extra or {}
    for key in ("origin_id", "copies_origin", "reprints_origin"):
        if extra.get(key):
            return fold_text(str(extra[key]))
    if is_qsa_source(item):
        return f"qsa:{normalize_cnpj(item.company_cnpj) or 'unknown'}"
    if item.document_id:
        return f"doc:{fold_text(item.document_id)}"
    host = host_of(item.source_url)
    path = urlsplit(item.source_url or "").path.lower().rstrip("/")
    source_class = classify_source_type(item.source_type) or fold_text(item.source_type)
    if host and any(marker in host for marker in SYNDICATION_HOST_MARKERS):
        # Without an explicit origin, syndication hosts still do not mint a new
        # origin from query-string variants of the same path.
        return f"synd:{host}{path}"
    return f"{source_class}:{host}{path or item.evidence_id}"


def names_match(left: str | None, right: str | None) -> bool:
    a = fold_text(normalize_name(left))
    b = fold_text(normalize_name(right))
    return bool(a) and a == b


def person_name_matches(person: CandidatePerson, value: str | None) -> bool:
    if names_match(person.canonical_name, value):
        return True
    return any(names_match(alias, value) for alias in person.aliases)


def roles_conflict(left: DecisionRoleClass, right: DecisionRoleClass) -> bool:
    if left == right or left == DecisionRoleClass.UNKNOWN or right == DecisionRoleClass.UNKNOWN:
        return False
    if left.value in OWNERSHIP_ROLE_CLASSES or right.value in OWNERSHIP_ROLE_CLASSES:
        return False
    if left == DecisionRoleClass.DIRETOR and right.value in SPECIFIC_EXECUTIVE_ROLE_CLASSES:
        return False
    if right == DecisionRoleClass.DIRETOR and left.value in SPECIFIC_EXECUTIVE_ROLE_CLASSES:
        return False
    if left.value in SPECIFIC_EXECUTIVE_ROLE_CLASSES and right.value in SPECIFIC_EXECUTIVE_ROLE_CLASSES:
        return left != right
    if left != right and left in {
        DecisionRoleClass.DIRETOR_COMERCIAL,
        DecisionRoleClass.DIRETOR_ENGENHARIA,
        DecisionRoleClass.DIRETOR_OPERACOES,
        DecisionRoleClass.GERENTE_CONTRATOS,
        DecisionRoleClass.GERENTE_LICITACOES,
    } and right in {
        DecisionRoleClass.DIRETOR_COMERCIAL,
        DecisionRoleClass.DIRETOR_ENGENHARIA,
        DecisionRoleClass.DIRETOR_OPERACOES,
        DecisionRoleClass.GERENTE_CONTRATOS,
        DecisionRoleClass.GERENTE_LICITACOES,
    }:
        return True
    return False


def _as_of_date(as_of: date | str | None) -> date:
    if as_of is None:
        return datetime.now(UTC).date()
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        return as_of
    parsed = parse_iso_date(str(as_of))
    return parsed or datetime.now(UTC).date()


def _age_days(when: date | None, as_of: date) -> int | None:
    if when is None:
        return None
    return (as_of - when).days


def _never_average_confidence(
    *,
    independent_current: int,
    contradicted: bool,
    stale: bool,
    qsa_only: bool,
    insufficient: bool,
    ownership_only: bool = False,
) -> ConfidenceLevel:
    """Contradiction and staleness win. HIGH+LOW never becomes HIGH."""
    if contradicted:
        return ConfidenceLevel.LOW
    if stale:
        return ConfidenceLevel.LOW
    if qsa_only or ownership_only:
        return ConfidenceLevel.LOW
    if insufficient and independent_current == 0:
        return ConfidenceLevel.LOW
    if independent_current >= 2:
        return ConfidenceLevel.HIGH
    if independent_current == 1:
        return ConfidenceLevel.MEDIUM
    if insufficient:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.UNKNOWN


def evidence_items_from_observations(
    observations: Sequence[PersonObservation],
    *,
    company_name: str | None = None,
    company_kind: str | None = None,
) -> list[DatedEvidenceItem]:
    """Project existing DUI person observations into dated evidence items."""
    items: list[DatedEvidenceItem] = []
    for obs in observations:
        name = normalize_name(obs.person_name)
        if not name:
            continue
        kind = detect_entity_kind(company_name, explicit=company_kind)
        stale_hits = detect_stale_signals(obs.snippet, obs.observed_role, obs.signature_context)
        extra = dict(obs.extra or {})
        shared = dict(
            source_type=obs.source_type,
            source_url=obs.source_url,
            origin_id=(extra.get("origin_id") or extra.get("copies_origin")),
            document_id=obs.document_id,
            observed_at=obs.observed_at,
            published_at=extra.get("published_at"),
            snippet=obs.snippet,
            company_cnpj=normalize_cnpj(obs.company_entity_id),
            company_name=company_name,
            role_text=obs.observed_role,
            entity_kind=kind,
            stale_signal=stale_hits[0] if stale_hits else None,
            extraction_method=extra.get("extraction_method"),
            extra=extra,
        )
        items.append(
            DatedEvidenceItem(
                evidence_id=obs.evidence_id or obs.observation_id,
                field="identity",
                value=name,
                **shared,
            )
        )
        items.append(
            DatedEvidenceItem(
                evidence_id=f"{obs.evidence_id or obs.observation_id}:aff",
                field="affiliation",
                value=company_name or obs.company_entity_id,
                **shared,
            )
        )
        if obs.observed_role:
            items.append(
                DatedEvidenceItem(
                    evidence_id=f"{obs.evidence_id or obs.observation_id}:role",
                    field="role",
                    value=obs.observed_role,
                    **shared,
                )
            )
    return items


def _collect_aliases(person: CandidatePerson, accepted: Sequence[DatedEvidenceItem]) -> list[str]:
    aliases = [alias for alias in person.aliases if normalize_name(alias)]
    for item in accepted:
        if item.field != "identity":
            continue
        name = normalize_name(item.value)
        if name and not names_match(name, person.canonical_name) and person_name_matches(person, name):
            aliases.append(name)
    return list(dict.fromkeys(aliases))


def _company_matches(person: CandidatePerson, item: DatedEvidenceItem) -> bool:
    target = normalize_cnpj(person.target_company_cnpj)
    observed = normalize_cnpj(item.company_cnpj)
    if target and observed:
        return target == observed
    if person.target_company_name and item.company_name:
        return fold_text(person.target_company_name) == fold_text(item.company_name)
    return bool(target) and not observed


def corroborate_affiliation(
    person: CandidatePerson,
    evidence: Sequence[DatedEvidenceItem],
    *,
    as_of: date | str | None = None,
) -> AffiliationCorroboration:
    """Candidate person + dated evidence → per-field verdicts.

    Does not invent cargo/empresa. Does not promote email. Copies of one
    origin count once. Contradiction is explicit.
    """
    as_of_date = _as_of_date(as_of)
    target_cnpj = normalize_cnpj(person.target_company_cnpj)
    target_kind = detect_entity_kind(person.target_company_name, explicit=person.target_entity_kind)
    accepted: list[DatedEvidenceItem] = []
    rejected: list[dict[str, Any]] = []
    for item in evidence:
        forbidden, reason = is_forbidden_source(item)
        if forbidden:
            rejected.append(
                {
                    "evidence_id": item.evidence_id,
                    "source_type": item.source_type,
                    "reason": reason,
                    "source_url": item.source_url,
                }
            )
            continue
        if classify_source_type(item.source_type) is None and not is_qsa_source(item):
            rejected.append(
                {
                    "evidence_id": item.evidence_id,
                    "source_type": item.source_type,
                    "reason": "SOURCE_NOT_IN_ALLOWED_POLICY",
                    "source_url": item.source_url,
                }
            )
            continue
        accepted.append(item)

    relevant = [
        item
        for item in accepted
        if item.field in {"identity", "affiliation", "role", "recency", "company_kind"}
        and (item.field != "identity" or person_name_matches(person, item.value) or item.value is None)
    ]
    # Affiliation/role items apply when they belong to this person via extra or
    # when bundled with a matching identity on the same origin.
    person_origins = {
        independence_origin(item)
        for item in accepted
        if item.field == "identity" and person_name_matches(person, item.value)
    }
    scoped: list[DatedEvidenceItem] = []
    for item in accepted:
        if item.field == "identity" and person_name_matches(person, item.value):
            scoped.append(item)
            continue
        if item.field in {"affiliation", "role", "recency", "company_kind"}:
            named = item.extra.get("person_name") if item.extra else None
            if named and not person_name_matches(person, str(named)):
                continue
            if named or independence_origin(item) in person_origins or person_name_matches(person, item.value):
                scoped.append(item)
                continue
            if item.field == "affiliation" and _company_matches(person, item) and not named:
                # Affiliation without a person name is company-level, not personal.
                continue
            if item.role_text and person_name_matches(person, item.value):
                scoped.append(item)
    if not scoped:
        scoped = [item for item in relevant if person_name_matches(person, item.value)]

    contradictions: list[AffiliationContradiction] = []
    reason_codes: list[str] = []

    identity_items = [item for item in scoped if item.field == "identity"]
    affiliation_items = [item for item in scoped if item.field == "affiliation"]
    role_items = [item for item in scoped if item.field == "role"]

    other_company_current: list[DatedEvidenceItem] = []
    target_affiliation: list[DatedEvidenceItem] = []
    for item in affiliation_items:
        if _company_matches(person, item):
            target_affiliation.append(item)
        elif item.company_cnpj and normalize_cnpj(item.company_cnpj) != target_cnpj:
            other_company_current.append(item)
        elif item.company_name and person.target_company_name:
            if fold_text(item.company_name) != fold_text(person.target_company_name):
                other_company_current.append(item)

    stale_hits: list[str] = []
    for item in scoped:
        stale_hits.extend(detect_stale_signals(item.snippet, item.value, item.role_text, item.stale_signal))
        if item.stale_signal:
            stale_hits.append(item.stale_signal)
    stale_hits = list(dict.fromkeys(stale_hits))
    stale = bool(stale_hits)

    qsa_items = [item for item in scoped if is_qsa_source(item)]
    public_items = [item for item in scoped if not is_qsa_source(item)]
    qsa_only = bool(scoped) and not public_items and bool(qsa_items)

    def _current_public(items: Iterable[DatedEvidenceItem]) -> list[DatedEvidenceItem]:
        out: list[DatedEvidenceItem] = []
        for item in items:
            if is_qsa_source(item):
                continue
            if detect_stale_signals(item.snippet, item.value, item.role_text, item.stale_signal) or item.stale_signal:
                continue
            out.append(item)
        return out

    affiliation_origins = {
        independence_origin(item) for item in _current_public(target_affiliation)
    }
    public_identity_at_target = [
        item
        for item in _current_public(identity_items)
        if _company_matches(person, item) or not item.company_cnpj
    ]

    # Homonym / other-company current affiliation.
    other_current_public = _current_public(other_company_current)
    if other_current_public and not _current_public(target_affiliation) and not qsa_items:
        contradictions.append(
            AffiliationContradiction(
                topic="affiliation",
                left=target_cnpj or person.target_company_name or "",
                right=other_current_public[0].company_cnpj or other_current_public[0].company_name or "",
                reason_codes=[AffiliationReasonCode.CONFLICTING_EVIDENCE.value],
                evidence_ids=[item.evidence_id for item in other_current_public],
            )
        )
        reason_codes.append(AffiliationReasonCode.CONFLICTING_EVIDENCE.value)
    elif other_current_public and (_current_public(target_affiliation) or qsa_items):
        # Same person claimed current at two companies → conflict, do not average.
        contradictions.append(
            AffiliationContradiction(
                topic="affiliation",
                left=target_cnpj or person.target_company_name or "",
                right=other_current_public[0].company_cnpj or other_current_public[0].company_name or "",
                reason_codes=[AffiliationReasonCode.CONFLICTING_EVIDENCE.value],
                evidence_ids=[item.evidence_id for item in other_current_public + target_affiliation],
            )
        )
        reason_codes.append(AffiliationReasonCode.CONFLICTING_EVIDENCE.value)

    if other_current_public and not _current_public(target_affiliation) and not qsa_only:
        # Do not affiliate the homonym to the target company.
        affiliation_origins = set()

    role_candidates: list[RoleCandidate] = []
    role_by_class: dict[str, list[DatedEvidenceItem]] = defaultdict(list)
    for item in role_items:
        text = item.value or item.role_text
        if not text:
            continue
        klass = normalize_observed_role(text)
        canonical = klass.value if klass != DecisionRoleClass.UNKNOWN else None
        # Never invent a canonical role without observed text mapping.
        role_by_class[canonical or "unknown"].append(item)
        existing = next((c for c in role_candidates if c.role_text == text), None)
        origin = independence_origin(item)
        if existing:
            existing.source_ids.append(item.evidence_id)
            if origin not in existing.origin_ids:
                existing.origin_ids.append(origin)
            continue
        when = evidence_date_of(item)
        role_candidates.append(
            RoleCandidate(
                role_text=text,
                canonical_role=canonical,
                source_ids=[item.evidence_id],
                evidence_date=when.isoformat() if when else item.published_at or item.observed_at,
                origin_ids=[origin],
            )
        )

    public_role_classes = {
        klass: [item for item in items if not is_qsa_source(item)]
        for klass, items in role_by_class.items()
        if klass != "unknown"
    }
    current_public_role_classes = {
        klass: _current_public(items) for klass, items in public_role_classes.items() if _current_public(items)
    }
    role_conflict = False
    live_classes = [DecisionRoleClass(klass) for klass in current_public_role_classes]
    for i, left in enumerate(live_classes):
        for right in live_classes[i + 1 :]:
            if roles_conflict(left, right):
                role_conflict = True
                contradictions.append(
                    AffiliationContradiction(
                        topic="role",
                        left=left.value,
                        right=right.value,
                        reason_codes=[
                            AffiliationReasonCode.CONFLICTING_EVIDENCE.value,
                            AffiliationReasonCode.CONFLICTING_ROLE.value,
                        ],
                        evidence_ids=[
                            item.evidence_id
                            for item in current_public_role_classes[left.value]
                            + current_public_role_classes[right.value]
                        ],
                    )
                )
    if role_conflict:
        reason_codes.extend(
            [
                AffiliationReasonCode.CONFLICTING_EVIDENCE.value,
                AffiliationReasonCode.CONFLICTING_ROLE.value,
            ]
        )

    # Holding / operational / unit / brand / consortium mismatch.
    observed_kinds = {
        detect_entity_kind(item.company_name, explicit=item.entity_kind)
        for item in scoped
        if item.company_name or item.entity_kind
    }
    observed_kinds.discard(EntityKind.UNKNOWN.value)
    mismatch = False
    if target_kind != EntityKind.UNKNOWN.value:
        for kind in observed_kinds:
            if kind != target_kind and {kind, target_kind} & {
                EntityKind.HOLDING.value,
                EntityKind.OPERATIONAL.value,
                EntityKind.UNIT.value,
                EntityKind.BRAND.value,
                EntityKind.CONSORTIUM.value,
            }:
                if kind != target_kind:
                    mismatch = True
                    contradictions.append(
                        AffiliationContradiction(
                            topic="entity_kind",
                            left=target_kind,
                            right=kind,
                            reason_codes=[
                                AffiliationReasonCode.CONFLICTING_EVIDENCE.value,
                                AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value,
                            ],
                        )
                    )
    if mismatch:
        reason_codes.extend(
            [
                AffiliationReasonCode.CONFLICTING_EVIDENCE.value,
                AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value,
            ]
        )

    if stale:
        reason_codes.append(AffiliationReasonCode.STALE_AFFILIATION.value)

    public_dates = [evidence_date_of(item) for item in public_items]
    public_dates = [when for when in public_dates if when]
    latest_public = max(public_dates) if public_dates else None
    latest_any_dates = [evidence_date_of(item) for item in scoped]
    latest_any_dates = [when for when in latest_any_dates if when]
    latest_any = max(latest_any_dates) if latest_any_dates else None
    latest_age = _age_days(latest_public, as_of_date)
    insufficient_recency = False
    if qsa_only:
        insufficient_recency = True
    elif latest_public is None and not public_items:
        insufficient_recency = True
    elif latest_age is None and public_items and not latest_public:
        insufficient_recency = True
    elif latest_age is not None and latest_age > RECENCY_AGING_DAYS:
        insufficient_recency = True
    if insufficient_recency:
        reason_codes.append(AffiliationReasonCode.INSUFFICIENT_RECENCY.value)

    if qsa_only:
        reason_codes.append(AffiliationReasonCode.QSA_ONLY.value)

    contradicted_affiliation = any(item.topic == "affiliation" for item in contradictions)
    contradicted_identity = contradicted_affiliation and not _current_public(target_affiliation)
    contradicted_role = role_conflict

    identity_level = _never_average_confidence(
        independent_current=len({independence_origin(item) for item in public_identity_at_target}),
        contradicted=contradicted_identity,
        stale=stale and not public_identity_at_target,
        qsa_only=qsa_only,
        insufficient=False,
    )
    if qsa_only and identity_items:
        # Cadastre names the person at this CNPJ — identity is observed, not
        # independently corroborated, and never HIGH from QSA echoes.
        identity_level = ConfidenceLevel.LOW
    if len({independence_origin(item) for item in public_identity_at_target}) >= 2 and not contradicted_identity:
        identity_level = ConfidenceLevel.HIGH
        reason_codes.append(AffiliationReasonCode.IDENTITY_CORROBORATED.value)
    elif public_identity_at_target and not qsa_only and not contradicted_identity:
        identity_level = ConfidenceLevel.MEDIUM

    affiliation_level = _never_average_confidence(
        independent_current=len(affiliation_origins),
        contradicted=contradicted_affiliation,
        stale=stale,
        qsa_only=qsa_only,
        insufficient=insufficient_recency,
    )
    if len(affiliation_origins) >= 2 and not contradicted_affiliation and not stale and not mismatch:
        affiliation_level = ConfidenceLevel.HIGH
        reason_codes.append(AffiliationReasonCode.AFFILIATION_CORROBORATED.value)
    elif len(affiliation_origins) == 1 and not contradicted_affiliation and not stale and not qsa_only:
        affiliation_level = ConfidenceLevel.MEDIUM

    public_role_origins = {
        independence_origin(item)
        for items in current_public_role_classes.values()
        for item in items
    }
    # Agreed role: largest non-conflicting class.
    agreed_role: str | None = None
    if not role_conflict:
        scored = sorted(
            (
                (
                    len({independence_origin(item) for item in items}),
                    klass,
                )
                for klass, items in current_public_role_classes.items()
            ),
            reverse=True,
        )
        if scored:
            agreed_role = scored[0][1]
        elif qsa_items and not public_items:
            qsa_roles = [klass for klass in role_by_class if klass != "unknown"]
            # QSA maps cadastral role only; never invent operational buyer.
            agreed_role = qsa_roles[0] if qsa_roles else None

    role_level = _never_average_confidence(
        independent_current=len(public_role_origins),
        contradicted=contradicted_role,
        stale=stale,
        qsa_only=qsa_only,
        insufficient=False,
        ownership_only=qsa_only,
    )
    if role_conflict:
        role_level = ConfidenceLevel.LOW
        agreed_role = None
    elif len(public_role_origins) >= 2 and agreed_role:
        role_level = ConfidenceLevel.HIGH
        reason_codes.append(AffiliationReasonCode.ROLE_CORROBORATED.value)
    elif len(public_role_origins) == 1 and agreed_role:
        role_level = ConfidenceLevel.MEDIUM
    elif not agreed_role and not role_items:
        role_level = ConfidenceLevel.UNKNOWN

    if latest_age is not None and latest_age <= RECENCY_FRESH_DAYS and public_items and not stale:
        recency_level = ConfidenceLevel.HIGH
    elif latest_age is not None and latest_age <= RECENCY_AGING_DAYS and public_items and not stale:
        recency_level = ConfidenceLevel.MEDIUM
    elif stale or insufficient_recency:
        recency_level = ConfidenceLevel.LOW
    elif qsa_only:
        recency_level = ConfidenceLevel.LOW
    else:
        recency_level = ConfidenceLevel.UNKNOWN

    # Claimed role is recorded only when observed; never invented from silence.
    claimed = person.claimed_role
    if claimed and not any(candidate.role_text == claimed for candidate in role_candidates):
        mapped = normalize_observed_role(claimed)
        if mapped != DecisionRoleClass.UNKNOWN:
            role_candidates.append(
                RoleCandidate(
                    role_text=claimed,
                    canonical_role=mapped.value,
                    source_ids=[],
                    evidence_date=None,
                )
            )
            # Unsourced claimed role is not evidence — drop it from canonical.
            if not agreed_role:
                pass

    if claimed and not role_items:
        # A claimed role without evidence is ignored (zero invention).
        agreed_role = None
        role_candidates = [c for c in role_candidates if c.source_ids]

    aliases = _collect_aliases(person, identity_items)
    company_name = person.target_company_name
    if not company_name:
        named = next((item.company_name for item in target_affiliation if item.company_name), None)
        company_name = named

    latest_iso = None
    if latest_public:
        latest_iso = latest_public.isoformat()
    elif latest_any:
        latest_iso = latest_any.isoformat()

    field_records = [
        FieldConfidenceRecord(
            "identity",
            identity_level,
            [code for code in reason_codes if code.startswith("IDENTITY") or code == AffiliationReasonCode.QSA_ONLY.value],
            len({independence_origin(item) for item in public_identity_at_target}),
            latest_iso,
        ),
        FieldConfidenceRecord(
            "company_affiliation",
            affiliation_level,
            [
                code
                for code in reason_codes
                if code
                in {
                    AffiliationReasonCode.AFFILIATION_CORROBORATED.value,
                    AffiliationReasonCode.STALE_AFFILIATION.value,
                    AffiliationReasonCode.QSA_ONLY.value,
                    AffiliationReasonCode.CONFLICTING_EVIDENCE.value,
                    AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value,
                }
            ],
            len(affiliation_origins),
            latest_iso,
        ),
        FieldConfidenceRecord(
            "role",
            role_level,
            [
                code
                for code in reason_codes
                if code
                in {
                    AffiliationReasonCode.ROLE_CORROBORATED.value,
                    AffiliationReasonCode.CONFLICTING_ROLE.value,
                    AffiliationReasonCode.QSA_ONLY.value,
                }
            ],
            len(public_role_origins),
            latest_iso,
        ),
        FieldConfidenceRecord(
            "recency",
            recency_level,
            [
                code
                for code in reason_codes
                if code
                in {
                    AffiliationReasonCode.INSUFFICIENT_RECENCY.value,
                    AffiliationReasonCode.STALE_AFFILIATION.value,
                }
            ],
            len({independence_origin(item) for item in public_items}),
            latest_iso,
        ),
    ]

    reason_codes = list(dict.fromkeys(reason_codes))
    stop_reasons = [code for code in reason_codes if code in STOP_THE_LINE_CODES]
    # Homonym with no target affiliation is also stop-the-line (false vínculo).
    if contradicted_identity or (other_current_public and not affiliation_origins and not qsa_only):
        if AffiliationReasonCode.CONFLICTING_EVIDENCE.value not in stop_reasons:
            stop_reasons.append(AffiliationReasonCode.CONFLICTING_EVIDENCE.value)
        if AffiliationReasonCode.CONFLICTING_EVIDENCE.value not in reason_codes:
            reason_codes.append(AffiliationReasonCode.CONFLICTING_EVIDENCE.value)

    association_allowed = not any(code in ASSOCIATION_REFUSED_WHEN for code in reason_codes)
    if other_current_public and not affiliation_origins:
        association_allowed = False
    if identity_level in {ConfidenceLevel.NONE, ConfidenceLevel.UNKNOWN} and not qsa_only:
        association_allowed = False
    if affiliation_level in {ConfidenceLevel.NONE} or (affiliation_level == ConfidenceLevel.UNKNOWN and not qsa_only):
        if not affiliation_origins:
            association_allowed = False

    person_id = stable_id("aff", target_cnpj, fold_text(person.canonical_name))
    return AffiliationCorroboration(
        person_id=person_id,
        canonical_name=normalize_name(person.canonical_name) or person.canonical_name,
        aliases=aliases,
        company_cnpj=target_cnpj,
        company_name=company_name,
        company_kind=target_kind,
        role_candidates=role_candidates,
        canonical_decision_role=agreed_role,
        evidence=scoped,
        rejected_evidence=rejected,
        contradictions=contradictions,
        identity_confidence=identity_level,
        affiliation_confidence=affiliation_level,
        role_confidence=role_level,
        recency_confidence=recency_level,
        reason_codes=reason_codes,
        association_allowed=association_allowed,
        stop_reasons=list(dict.fromkeys(stop_reasons)),
        field_records=field_records,
    )


def email_association_gate(
    corroboration: AffiliationCorroboration,
    *,
    email: str | None = None,
) -> EmailAssociationDecision:
    """Consumable by the email promoter. Never promotes or validates email."""
    del email  # local-part is never consulted
    reasons = list(corroboration.reason_codes)
    stop = bool(corroboration.stop_reasons) or not corroboration.association_allowed
    allowed = bool(corroboration.association_allowed) and not stop
    if not allowed and AffiliationReasonCode.QSA_ONLY.value in reasons:
        stop = True
    return EmailAssociationDecision(
        allowed=allowed,
        stop_the_line=stop,
        reason_codes=tuple(dict.fromkeys(reasons)),
        person_name=corroboration.canonical_name,
        company_cnpj=corroboration.company_cnpj,
    )


def may_associate_email(
    person: CandidatePerson,
    evidence: Sequence[DatedEvidenceItem],
    *,
    email: str | None = None,
    as_of: date | str | None = None,
) -> EmailAssociationDecision:
    """One-shot gate: corroborate then decide. Does not write affiliation or email."""
    record = corroborate_affiliation(person, evidence, as_of=as_of)
    return email_association_gate(record, email=email)

