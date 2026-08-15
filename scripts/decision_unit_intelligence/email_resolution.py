"""Email discovery as ONE reachability strategy.

Inferred addresses stay INFERRED. MX never proves a mailbox or a person.
A single observed sample is not a corporate pattern fact.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from scripts.decision_unit_intelligence.models import EpistemicClass, fold_text, normalize_email, normalize_name
from scripts.decision_unit_intelligence.reachability import (
    FREEMAIL_DOMAINS,
    email_domain,
    is_generic_mailbox,
    is_role_mailbox,
)

PatternFn = Callable[[str, str, str], str | None]


def _strip_accents(value: str) -> str:
    s = unicodedata.normalize("NFKD", value)
    return "".join(c for c in s if not unicodedata.combining(c))


LEGAL_FORM_TOKENS = frozenset(
    {
        "ltda",
        "sa",
        "eireli",
        "mei",
        "me",
        "epp",
        "participacoes",
        "participacao",
        "holding",
        "cia",
        "companhia",
        "administradora",
        "bens",
        "representacoes",
    }
)

THIRD_PARTY_DOMAIN_MARKERS = (
    "contabil",
    "contador",
    "contabilidade",
    "advocacia",
    "advogados",
    "despachante",
)
THIRD_PARTY_DOMAIN_SUFFIXES = (
    ".adv.br",
    ".cnt.br",
    ".leg.br",
)


def is_third_party_professional_domain(domain: str | None) -> bool:
    if not domain:
        return False
    folded = fold_text(domain)
    if any(folded.endswith(suffix) for suffix in THIRD_PARTY_DOMAIN_SUFFIXES):
        return True
    return any(marker in folded for marker in THIRD_PARTY_DOMAIN_MARKERS)


def name_tokens(person_name: str | None) -> list[str]:
    raw = normalize_name(person_name) or ""
    folded = _strip_accents(raw).lower()
    folded = re.sub(r"[^a-z\s\-']", " ", folded)
    parts = [p for p in re.split(r"[\s\-]+", folded) if p]
    stop = {"da", "de", "do", "das", "dos", "e", "di", "du"} | LEGAL_FORM_TOKENS
    return [p for p in parts if p not in stop]


def first_last(tokens: list[str]) -> tuple[str, str] | None:
    if len(tokens) < 2:
        return None
    return tokens[0], tokens[-1]


def pattern_first_dot_last(first: str, last: str, domain: str) -> str:
    return f"{first}.{last}@{domain}"


def pattern_first_last(first: str, last: str, domain: str) -> str:
    return f"{first}{last}@{domain}"


def pattern_f_last(first: str, last: str, domain: str) -> str:
    return f"{first[0]}{last}@{domain}"


def pattern_first_l(first: str, last: str, domain: str) -> str:
    return f"{first}{last[0]}@{domain}"


def pattern_last(first: str, last: str, domain: str) -> str:
    return f"{last}@{domain}"


def pattern_first(first: str, last: str, domain: str) -> str:
    return f"{first}@{domain}"


KNOWN_PATTERNS: list[tuple[str, PatternFn]] = [
    ("first.last", pattern_first_dot_last),
    ("firstlast", pattern_first_last),
    ("flast", pattern_f_last),
    ("firstl", pattern_first_l),
    ("last", pattern_last),
    ("first", pattern_first),
]


@dataclass
class ObservedOrgEmail:
    email: str
    source_type: str
    source_url: str | None = None
    person_name: str | None = None


@dataclass
class EmailInference:
    email: str
    pattern_id: str
    epistemic_class: EpistemicClass
    domain: str
    domain_epistemic: EpistemicClass
    pattern_epistemic: EpistemicClass
    technically_validated: bool
    corroborated: bool
    reason_codes: list[str] = field(default_factory=list)
    signals: dict[str, str] = field(default_factory=dict)
    mx_valid: bool = False

    @property
    def verified_class(self) -> str | None:
        if (
            self.epistemic_class == EpistemicClass.INFERRED
            and self.technically_validated
            and self.corroborated
        ):
            return "INFERRED_DIRECT_EMAIL_VERIFIED"
        return None


def official_domain_from_emails(emails: list[str], *, company_site: str | None = None) -> tuple[str | None, EpistemicClass, list[str]]:
    reasons: list[str] = []
    site_domain = None
    if company_site:
        m = re.search(r"(?:https?://)?(?:www\.)?([^/\s]+)", company_site.lower())
        if m:
            site_domain = m.group(1)
            reasons.append("DOMAIN_FROM_COMPANY_SITE")
    corp = []
    for e in emails:
        d = email_domain(e)
        if d and d not in FREEMAIL_DOMAINS:
            corp.append(d)
    if site_domain and is_third_party_professional_domain(site_domain):
        reasons.append("THIRD_PARTY_PROFESSIONAL_SITE_DOMAIN")
        site_domain = None
    corp = [d for d in corp if not is_third_party_professional_domain(d)]
    if site_domain and site_domain not in FREEMAIL_DOMAINS:
        if corp and site_domain not in corp:
            reasons.append("DOMAIN_CONFLICT_SITE_VS_EMAIL")
        return site_domain, EpistemicClass.OBSERVED, reasons
    if not corp:
        return None, EpistemicClass.UNKNOWN, reasons + ["NO_CORPORATE_DOMAIN"]
    counted = Counter(corp)
    if len(counted) > 1:
        reasons.append("MULTIPLE_ORG_DOMAINS")
    domain, _ = counted.most_common(1)[0]
    return domain, EpistemicClass.OBSERVED, reasons


def detect_pattern(email: str, person_name: str | None) -> str | None:
    tokens = name_tokens(person_name)
    pair = first_last(tokens)
    domain = email_domain(email)
    normalized = normalize_email(email) or ""
    local = normalized.split("@", 1)[0] if "@" in normalized else ""
    if not domain or not pair:
        return None
    first, last = pair
    for pid, fn in KNOWN_PATTERNS:
        built = fn(first, last, domain)
        if built and built.split("@", 1)[0] == local:
            return pid
    # compound last name: try last two tokens as last
    if len(tokens) >= 3:
        last2 = "".join(tokens[-2:])
        if pattern_first_dot_last(first, last2, domain).split("@", 1)[0] == local:
            return "first.compoundlast"
    return None


def derive_org_patterns(observed: list[ObservedOrgEmail]) -> dict[str, list[str]]:
    """Return pattern_id → supporting emails. A single sample is flagged, not a fact."""
    hits: dict[str, list[str]] = {}
    for item in observed:
        email = normalize_email(item.email)
        if not email or is_role_mailbox(email) or is_generic_mailbox(email):
            continue
        if is_third_party_professional_domain(email_domain(email)):
            continue
        pid = detect_pattern(email, item.person_name)
        if pid:
            hits.setdefault(pid, []).append(email)
    return hits


def generate_inferred_emails(
    *,
    person_name: str,
    domain: str,
    observed: list[ObservedOrgEmail],
    mx_valid: bool = False,
    catch_all: bool = False,
    public_hits: list[str] | None = None,
    independent_corroborations: list[str] | None = None,
) -> list[EmailInference]:
    if is_third_party_professional_domain(domain):
        return []
    from scripts.decision_unit_intelligence.decision_policy import is_legal_entity_name

    if is_legal_entity_name(person_name):
        return []
    tokens = name_tokens(person_name)
    pair = first_last(tokens)
    if not pair or not domain or domain in FREEMAIL_DOMAINS:
        return []
    first, last = pair
    patterns = derive_org_patterns(observed)
    public_hits = [normalize_email(x) or "" for x in (public_hits or [])]
    corroborations = independent_corroborations or []
    results: list[EmailInference] = []

    def _compound(first_n: str, _last: str, domain_n: str, *, c: str = "".join(tokens[-2:])) -> str:
        return f"{first_n}.{c}@{domain_n}"

    candidates: list[tuple[str, PatternFn]] = list(KNOWN_PATTERNS)
    if len(tokens) >= 3:
        candidates.append(("first.compoundlast", _compound))

    for pid, fn in candidates:
        addr = normalize_email(fn(first, last, domain))
        if not addr:
            continue
        reasons = ["INFERRED_FROM_NAME_AND_DOMAIN", f"PATTERN:{pid}"]
        signals = {"domain": domain, "pattern": pid}
        support = patterns.get(pid, [])
        if len(support) == 0:
            pattern_ep = EpistemicClass.INFERRED
            reasons.append("PATTERN_NOT_OBSERVED_IN_ORG")
        elif len(support) == 1:
            pattern_ep = EpistemicClass.INFERRED
            reasons.append("SINGLE_SAMPLE_PATTERN")
            signals["supporting_email"] = support[0]
        else:
            pattern_ep = EpistemicClass.CORROBORATED
            reasons.append("PATTERN_CORROBORATED_BY_ORG_EMAILS")
            signals["supporting_count"] = str(len(support))
        if catch_all:
            reasons.append("CATCH_ALL_DOMAIN")
        if mx_valid:
            reasons.append("MX_VALID_NOT_MAILBOX_PROOF")
            signals["mx"] = "valid"
        if addr in public_hits:
            reasons.append("CANDIDATE_SEEN_IN_PUBLIC_SOURCE")
        if any("holding" in fold_text(c) or "grupo" in fold_text(c) for c in corroborations):
            reasons.append("HOLDING_OR_GROUP_SIGNAL")

        technically = bool(mx_valid) and not catch_all
        corroborated = pattern_ep == EpistemicClass.CORROBORATED and addr in public_hits
        if technically:
            reasons.append("TECHNICALLY_VALIDATED_DOMAIN_ONLY")
        results.append(
            EmailInference(
                email=addr,
                pattern_id=pid,
                epistemic_class=EpistemicClass.INFERRED,
                domain=domain,
                domain_epistemic=EpistemicClass.OBSERVED,
                pattern_epistemic=pattern_ep,
                technically_validated=technically,
                corroborated=corroborated,
                reason_codes=reasons,
                signals=signals,
                mx_valid=mx_valid,
            )
        )
    return results


def mx_never_proves_mailbox(inference: EmailInference) -> bool:
    """Invariant: MX validity is not mailbox/person proof."""
    if inference.mx_valid and inference.epistemic_class == EpistemicClass.OBSERVED:
        return False
    if "MX_VALID_NOT_MAILBOX_PROOF" in inference.reason_codes:
        return inference.epistemic_class == EpistemicClass.INFERRED
    return inference.epistemic_class != EpistemicClass.OBSERVED
