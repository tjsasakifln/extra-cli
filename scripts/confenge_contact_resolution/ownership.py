"""Contact ownership resolver: company-owned vs third-party / shared.

Conservative on identity: absence preferred over attributing a third-party channel.
Explainable score → ownership_status + enrollable gate.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from scripts.confenge_contact_resolution.email_policy import (
    domain_of,
    is_freemail,
    is_functional_mailbox,
)
from scripts.confenge_contact_resolution.models import (
    ENROLLABLE_OWNERSHIP,
    ContactCandidate,
    FreshnessClass,
    OwnershipStatus,
    ThirdPartyType,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.provenance_trust import (
    is_demo_or_fixture_domain,
    is_demo_or_fixture_email,
)

# Domain / entity tokens that strongly signal a third-party service provider.
_THIRD_PARTY_LEXICON: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"contabil(?:idade|ista|i|istica)?|contador(?:es)?|escritorio\s+contabil|"
            r"assessoria\s+contabil|bpo\s+financeir|servicos?\s+contabeis",
            re.I,
        ),
        ThirdPartyType.ACCOUNTING.value,
    ),
    (
        re.compile(
            r"advocacia|advogad[oa]s?|juridico\s+externo|escritorio\s+juridico|"
            r"\boab\b|legal\s+office",
            re.I,
        ),
        ThirdPartyType.LEGAL.value,
    ),
    (
        re.compile(
            r"despachante|correspondente\s+cadastral|representante\s+cadastral",
            re.I,
        ),
        ThirdPartyType.OTHER.value,
    ),
    (
        re.compile(
            r"consultoria|consultor(?:es)?\b|assessoria\s+empresarial|"
            r"business\s+advisor",
            re.I,
        ),
        ThirdPartyType.CONSULTING.value,
    ),
    (
        re.compile(r"escritorio\s+virtual|virtual\s+office|coworking\s+fiscal", re.I),
        ThirdPartyType.VIRTUAL_OFFICE.value,
    ),
    (
        re.compile(
            r"software|saas|erp\b|marketplace|portal\s+de\s+fornecedor|"
            r"plataforma\s+de\s+licitac",
            re.I,
        ),
        ThirdPartyType.SOFTWARE.value,
    ),
    (
        re.compile(r"sindicato|associacao|federacao|camara\s+de\s+comercio", re.I),
        ThirdPartyType.ASSOCIATION.value,
    ),
]

_STOP_TOKENS = frozenset(
    {
        "ltda",
        "limitada",
        "sa",
        "s/a",
        "me",
        "epp",
        "eireli",
        "ss",
        "cia",
        "company",
        "comercio",
        "comércio",
        "servicos",
        "serviços",
        "servico",
        "serviço",
        "construtora",
        "engenharia",
        "construcoes",
        "construções",
        "construcao",
        "construção",
        "transportadora",
        "transportes",
        "mineracao",
        "mineração",
        "pavimentacao",
        "pavimentação",
        "instalacoes",
        "instalações",
        "locacao",
        "locação",
        "empreendimentos",
        "participacoes",
        "participações",
        "incorporadora",
        "industria",
        "indústria",
        "infraestrutura",
        "saneamento",
        "www",
        "http",
        "https",
        "com",
        "br",
        "org",
        "net",
        "the",
        "and",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "em",
    }
)

_OFFICIAL_SOURCES = frozenset({"site", "contact_page", "registry", "public_docs", "human_outcome"})
_DOC_SOURCES = frozenset({"public_docs", "human_outcome"})
_STRONG_PAGE_SOURCES = frozenset({"site", "contact_page"})


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def tokens_from_text(text: str | None) -> set[str]:
    if not text:
        return set()
    folded = _fold(text)
    # Split on punctuation and digit↔letter boundaries (demo000obra → demo, 000, obra)
    parts = re.split(r"[^a-z0-9]+", folded)
    expanded: list[str] = []
    for p in parts:
        if not p:
            continue
        expanded.extend(re.findall(r"[a-z]+|\d+", p))
    return {p for p in expanded if len(p) >= 3 and p not in _STOP_TOKENS and not p.isdigit()}


def domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    s = str(url).strip()
    if not s:
        return None
    if "://" not in s:
        s = "https://" + s
    try:
        host = urlparse(s).hostname or ""
    except ValueError:
        return None
    host = host.lower().removeprefix("www.")
    return host or None


def domain_token_overlap(domain: str | None, company_name: str | None) -> float:
    """Jaccard-like overlap between domain labels and company name tokens."""
    if not domain or not company_name:
        return 0.0
    d_tokens = tokens_from_text(domain.replace(".", " "))
    c_tokens = tokens_from_text(company_name)
    if not d_tokens or not c_tokens:
        return 0.0
    inter = d_tokens & c_tokens
    if not inter:
        # substring containment (construtoraalpha in construtoraalpha.com.br;
        # demo/obra in demo000obra.com.br)
        dflat = domain.replace(".", "")
        hits = 0
        for t in c_tokens:
            if len(t) >= 4 and t in dflat:
                hits += 1
        if hits >= 2:
            return 0.55
        if hits == 1:
            return 0.4
        return 0.0
    union = d_tokens | c_tokens
    return len(inter) / max(1, len(union))


def detect_third_party_type(
    *texts: str | None,
) -> tuple[str | None, list[str]]:
    """Return (third_party_type, matched_evidence) from lexical signals."""
    blob = " ".join(_fold(t) for t in texts if t)
    if not blob:
        return None, []
    hits: list[str] = []
    found_type: str | None = None
    for pat, tp in _THIRD_PARTY_LEXICON:
        m = pat.search(blob)
        if m:
            hits.append(f"lex:{m.group(0)}")
            if found_type is None:
                found_type = tp
    return found_type, hits


def cnpj_root(cnpj14: str | None) -> str:
    d = re.sub(r"\D", "", cnpj14 or "")
    return d[:8] if len(d) >= 8 else d


def freshness_class_from_days(age_days: int | None) -> str:
    if age_days is None:
        return FreshnessClass.UNKNOWN_DATE.value
    if age_days <= 90:
        return FreshnessClass.CURRENT.value
    if age_days <= 365:
        return FreshnessClass.RECENT.value
    return FreshnessClass.STALE.value


@dataclass
class OwnershipContext:
    """Company-side facts used while classifying a candidate."""

    cnpj14: str
    razao_social: str | None = None
    nome_fantasia: str | None = None
    official_domain: str | None = None
    economic_group_id: str | None = None
    related_cnpjs: set[str] = field(default_factory=set)  # matriz/filial / group
    human_confirmed: bool = False


@dataclass
class ReuseSignal:
    """How many unrelated companies share this channel."""

    channel_key: str
    associated_cnpjs: list[str] = field(default_factory=list)
    unrelated_count: int = 0
    same_root_count: int = 0
    same_group_count: int = 0


@dataclass
class RegistryHit:
    entity_name: str | None = None
    third_party_type: str | None = None
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class OwnershipResult:
    ownership_status: str
    ownership_reason: str
    verification_reason: str
    confidence: float
    enrollable: bool
    third_party_type: str | None = None
    domain_matches_company: bool | None = None
    found_on_official_source: bool = False
    found_on_company_document: bool = False
    score_parts: list[str] = field(default_factory=list)
    associated_company_count: int = 1


def resolve_ownership(
    candidate: ContactCandidate,
    *,
    ctx: OwnershipContext,
    reuse: ReuseSignal | None = None,
    registry_hit: RegistryHit | None = None,
    context_text: str | None = None,
    art_crea_only: bool = False,
    independent_sources_count: int | None = None,
) -> OwnershipResult:
    """Classify ownership for one candidate. Pure function — no I/O."""
    parts: list[str] = []
    score = 0

    src_type = (candidate.source.source_type if candidate.source else "unknown") or "unknown"
    email = candidate.email
    domain = domain_of(email) if email else None
    source_url = candidate.source.source_url if candidate.source else None
    # Site host from page we scraped (not official_domain fallback — that masks residual FPs)
    scrape_host = domain_from_url(candidate.site) or domain_from_url(source_url)
    site_dom = scrape_host or ctx.official_domain
    razao = (ctx.razao_social or "").strip()
    fantasia = (ctx.nome_fantasia or "").strip()
    company_label = " ".join(x for x in (razao, fantasia) if x).strip()
    # Identity alignment uses razao_social first; fantasia-only matches (LED+CACTUS→cactus.com)
    # are not enough for COMPANY_OWNED enrollable.
    identity_label = razao or company_label

    # --- hard invalid / pattern guess ---
    if (
        candidate.verification_status
        in {
            VerificationStatus.SYNTAX_INVALID.value,
            VerificationStatus.NOT_AVAILABLE.value,
        }
        and not candidate.phone_e164
    ):
        return OwnershipResult(
            ownership_status=OwnershipStatus.INVALID.value
            if candidate.verification_status == VerificationStatus.SYNTAX_INVALID.value
            else OwnershipStatus.UNRESOLVED.value,
            ownership_reason="no_usable_channel",
            verification_reason=candidate.verification_status,
            confidence=0.0,
            enrollable=False,
            score_parts=["no_channel"],
        )

    # --- demo/fixture channel never enrollable even if labeled VERIFIED ---
    # Ownership only hard-blocks on the *channel* looking synthetic (email/domain)
    # or explicit fixture source_type. URL heuristics like example.com remain a
    # send-readiness concern (evaluate_email_send_ready), not ownership identity.
    src_type_early = ((candidate.source.source_type if candidate.source else "") or "").strip().lower()
    if is_demo_or_fixture_email(email) or is_demo_or_fixture_domain(domain) or is_demo_or_fixture_domain(
        ctx.official_domain
    ):
        return OwnershipResult(
            ownership_status=OwnershipStatus.INVALID.value,
            ownership_reason="demo_or_fixture_channel_never_enrollable",
            verification_reason="PROVENANCE_TAINT_DEMO",
            confidence=0.0,
            enrollable=False,
            domain_matches_company=False,
            score_parts=["demo_fixture_domain"],
        )
    if src_type_early in {
        "fixture",
        "fixtures",
        "test_fixture",
        "test",
        "demo",
        "synthetic",
        "mock",
        "sample",
        "example",
        "fake",
        "seed",
        "generated",
        "cached_synthetic",
    }:
        return OwnershipResult(
            ownership_status=OwnershipStatus.INVALID.value,
            ownership_reason=f"provenance_tainted_source_type:{src_type_early}",
            verification_reason="PROVENANCE_TAINT",
            confidence=0.0,
            enrollable=False,
            domain_matches_company=False,
            score_parts=[f"taint_source:{src_type_early}"],
        )
    if (candidate.epistemic_class or "").upper() in {"SYNTHETIC", "FIXTURE", "DEMO"}:
        return OwnershipResult(
            ownership_status=OwnershipStatus.INVALID.value,
            ownership_reason=f"provenance_tainted_epistemic:{candidate.epistemic_class}",
            verification_reason="PROVENANCE_TAINT",
            confidence=0.0,
            enrollable=False,
            domain_matches_company=False,
            score_parts=["taint_epistemic"],
        )

    is_guess = bool(
        candidate.email_layers and candidate.email_layers.pattern_guessed
    ) or candidate.verification_status in {
        VerificationStatus.CANDIDATE_UNVERIFIED.value,
        VerificationStatus.PATTERN_GUESS.value,
    }
    if is_guess and email:
        parts.append("pattern_guess=-100")
        return OwnershipResult(
            ownership_status=OwnershipStatus.UNRESOLVED.value,
            ownership_reason="pattern_guessed_email_never_enrollable",
            verification_reason="PATTERN_GUESS",
            confidence=0.05,
            enrollable=False,
            score_parts=parts,
            domain_matches_company=False,
        )

    freemail = bool(email and is_freemail(email))
    official_src = src_type in _OFFICIAL_SOURCES
    doc_src = src_type in _DOC_SOURCES
    strong_page = src_type in _STRONG_PAGE_SOURCES
    found_official = official_src
    found_doc = doc_src

    # Third-party signals on domain/context FIRST (always, never gated on domain_match).
    # Prevents circular false positives: email@contabilidade.com on site contabilidade.com
    # must not become COMPANY_OWNED for Construtora X merely because email domain == site.
    tp_type, tp_hits = detect_third_party_type(
        domain,
        context_text,
        candidate.source.notes if candidate.source else None,
        site_dom,
    )
    if domain:
        tp_dom, hits2 = detect_third_party_type(domain)
        if tp_dom:
            tp_type = tp_dom
            tp_hits = list(dict.fromkeys(list(hits2) + list(tp_hits)))
    if site_dom:
        tp_site, hits_site = detect_third_party_type(site_dom)
        if tp_site and not tp_type:
            tp_type = tp_site
            tp_hits = list(dict.fromkeys(list(hits_site) + list(tp_hits)))
    if registry_hit and registry_hit.third_party_type:
        tp_type = registry_hit.third_party_type
        tp_hits = (
            list(tp_hits) + list(registry_hit.evidence or []) + [f"registry:{registry_hit.entity_name or 'known'}"]
        )

    if found_official:
        score += 40
        parts.append("official_source=+40")
    if strong_page:
        score += 15
        parts.append("company_page=+15")
    if found_doc:
        score += 20
        parts.append("company_document=+20")

    # domain_match = domain represents the TARGET company (name/official), never site alone.
    domain_match = False
    overlap = 0.0
    if domain and not freemail:
        overlap = domain_token_overlap(domain, company_label)
        official = (ctx.official_domain or "").removeprefix("www.").lower()
        site_norm = (site_dom or "").removeprefix("www.").lower() if site_dom else ""

        # Domain match requires residual-safe brand alignment vs razao_social (not fantasia alone).
        from scripts.confenge_contact_resolution.discovery.official_domain import (
            email_domain_aligned_with_company,
        )

        aligned = email_domain_aligned_with_company(
            domain,
            identity_label,
            official_domain=official or None,
        )
        if not aligned and fantasia and razao:
            # Fantasia-only residual match is never identity for enrollable COMPANY_OWNED
            fantasia_only = email_domain_aligned_with_company(
                domain,
                fantasia,
                official_domain=official or None,
            )
            if fantasia_only:
                parts.append("fantasia_only_domain_match_not_identity=0")
        # Strong: official company domain — require real name alignment (no short/generic FPs)
        if official and domain == official and overlap >= 0.35 and not tp_type and aligned:
            domain_match = True
            score += 25
            parts.append("email_domain_eq_official_company=+25")
        elif official and domain == official and overlap >= 0.2 and not tp_type and aligned:
            domain_match = True
            score += 15
            parts.append("email_domain_eq_official_weak_overlap=+15")
        elif official and domain == official and not aligned:
            parts.append("email_domain_eq_official_but_unaligned_with_company=0")
        elif aligned and overlap >= 0.35:
            domain_match = True
            score += 25
            parts.append(f"domain_name_overlap_aligned={overlap:.2f}=+25")
        elif overlap >= 0.35 and not aligned:
            # Overlap alone is not enough when residual is foreign product (hotelparaiso)
            parts.append(f"domain_overlap_but_residual_foreign={overlap:.2f}=0")
        elif overlap > 0:
            score += 5
            parts.append(f"weak_domain_overlap={overlap:.2f}=+5")
        else:
            parts.append("domain_unmatched_vs_company=0")

        # email domain == page host is NOT ownership proof by itself (third-party sites do this).
        # Only reinforce when we already matched the company, or site domain matches company name.
        if site_norm and domain == site_norm:
            site_overlap = domain_token_overlap(site_norm, company_label)
            if domain_match or (aligned and site_overlap >= 0.35):
                score += 10
                parts.append("email_domain_eq_company_aligned_site=+10")
            else:
                parts.append("email_domain_eq_site_circular_not_company_proof=0")

        # Residual-foreign / unaligned: revoke additive site credits (score soup).
        # Without this, official_source+40 + company_page+15 + weak_hint+8 >= 60
        # enrolls emkoelektronik/hotelparaiso/alcicafe via strong_page alone.
        if not domain_match and not aligned:
            if strong_page:
                score -= 15
                parts.append("unaligned_page_credit_revoked=-15")
            if found_official and not found_doc:
                score -= 40
                parts.append("unaligned_official_source_credit_revoked=-40")
        elif domain_match and strong_page and not tp_type:
            # Reinforce only when residual-safe domain_match already holds
            score += 8
            parts.append("aligned_page_company_hint=+8")

    if freemail:
        score -= 15
        parts.append("freemail=-15")
        # freemail needs stronger proof
        if found_doc and official_src:
            score += 25
            parts.append("freemail_doc_proof=+25")
        if independent_sources_count and independent_sources_count >= 2:
            score += 15
            parts.append(f"freemail_multi_source={independent_sources_count}=+15")

    if email and is_functional_mailbox(email) and domain_match:
        score += 8
        parts.append("functional_on_company_domain=+8")

    # Always penalize third-party domain/entity signals (not only when unmatched).
    if registry_hit and registry_hit.third_party_type:
        score -= 60
        parts.append("third_party_registry=-60")
    elif tp_hits:
        score -= 50
        parts.append(f"third_party_lexicon={tp_hits[0]}=-50")

    # Reuse graph
    associated = 1
    if reuse:
        associated = max(1, len(reuse.associated_cnpjs) or reuse.unrelated_count + 1)
        if reuse.unrelated_count >= 3 and reuse.same_root_count == 0 and reuse.same_group_count == 0:
            # Strong shared-external signal (threshold is soft; combined with other signals)
            penalty = min(55, 15 + reuse.unrelated_count * 5)
            score -= penalty
            parts.append(f"shared_unrelated={reuse.unrelated_count}=-{penalty}")
        elif reuse.same_root_count > 0 or reuse.same_group_count > 0:
            score += 10
            parts.append("shared_same_root_or_group=+10")

    # Aggregator-only weak sources
    if src_type in {"web_search", "unknown"} and not found_doc:
        score -= 30
        parts.append("aggregator_or_weak_source=-30")

    # Stale
    if candidate.freshness_days is not None and candidate.freshness_days > 730:
        score -= 25
        parts.append("stale_gt_2y=-25")
    elif candidate.freshness < 0.4:
        score -= 15
        parts.append("low_freshness=-15")

    # ART/CREA engineer not commercial
    if art_crea_only:
        score -= 40
        parts.append("art_crea_only_not_commercial=-40")
        if not candidate.role_class or candidate.role_class in {
            "engenharia",
            "generic",
            "unknown",
        }:
            # force non-enrollable commercial promotion path
            parts.append("art_crea_role_not_promoted")

    # Human confirmation
    if ctx.human_confirmed or src_type == "human_outcome":
        # Only elevate to HUMAN_CONFIRMED when human outcome affirms this channel
        if candidate.dnc or candidate.bounce:
            pass
        elif src_type == "human_outcome" and not candidate.dnc:
            return OwnershipResult(
                ownership_status=OwnershipStatus.HUMAN_CONFIRMED.value,
                ownership_reason="human_outcome_confirmation",
                verification_reason="HUMAN_CONFIRMED",
                confidence=0.95,
                enrollable=True,
                third_party_type=None,
                domain_matches_company=domain_match,
                found_on_official_source=True,
                found_on_company_document=found_doc,
                score_parts=parts + ["human_confirmed"],
                associated_company_count=associated,
            )

    # Domain/entity is a third-party service provider and is NOT the target company.
    # Company-is-the-accountant edge case: high name↔domain overlap keeps non-reject
    # (e.g. Silva Contabilidade Ltda @ silvacontabilidade.com.br). Construction
    # leads with contabilidade/advocacia domains never clear that bar.
    company_is_tp_entity = bool(tp_type and domain and not freemail and overlap >= 0.45)
    if tp_type and domain and not freemail and not company_is_tp_entity:
        return OwnershipResult(
            ownership_status=OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value,
            ownership_reason=(
                f"Domain/entity signals third-party ({tp_type}); does not match target company. "
                f"evidence={tp_hits}; company_overlap={overlap:.2f}"
            ),
            verification_reason="THIRD_PARTY_REJECT",
            confidence=max(0.0, min(0.4, score / 100.0)),
            enrollable=False,
            third_party_type=tp_type,
            domain_matches_company=False,
            found_on_official_source=found_official,
            found_on_company_document=found_doc,
            score_parts=parts,
            associated_company_count=associated,
        )

    if registry_hit and registry_hit.third_party_type and not company_is_tp_entity:
        return OwnershipResult(
            ownership_status=OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value,
            ownership_reason=(
                f"Known third-party registry hit: {registry_hit.entity_name} ({registry_hit.third_party_type})"
            ),
            verification_reason="THIRD_PARTY_REGISTRY",
            confidence=0.1,
            enrollable=False,
            third_party_type=registry_hit.third_party_type,
            domain_matches_company=False,
            found_on_official_source=found_official,
            found_on_company_document=found_doc,
            score_parts=parts,
            associated_company_count=associated,
        )

    # Shared external: many unrelated CNPJs, not same group/root
    if (
        reuse
        and reuse.unrelated_count >= 5
        and reuse.same_root_count == 0
        and reuse.same_group_count == 0
        and not domain_match
    ):
        return OwnershipResult(
            ownership_status=OwnershipStatus.SHARED_EXTERNAL_CONTACT.value,
            ownership_reason=(
                f"Channel shared by {reuse.unrelated_count} unrelated CNPJs "
                f"without known economic group or matriz/filial relation"
            ),
            verification_reason="SHARED_EXTERNAL",
            confidence=max(0.0, min(0.35, score / 100.0)),
            enrollable=False,
            third_party_type=tp_type or ThirdPartyType.OTHER.value,
            domain_matches_company=domain_match,
            found_on_official_source=found_official,
            found_on_company_document=found_doc,
            score_parts=parts,
            associated_company_count=associated,
        )

    # Soft shared band (3–4) with third-party lexicon → third party
    if reuse and reuse.unrelated_count >= 3 and reuse.same_root_count == 0 and tp_type and not domain_match:
        return OwnershipResult(
            ownership_status=OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value,
            ownership_reason=(f"Shared by {reuse.unrelated_count} unrelated companies with third-party type {tp_type}"),
            verification_reason="SHARED_THIRD_PARTY",
            confidence=0.15,
            enrollable=False,
            third_party_type=tp_type,
            domain_matches_company=False,
            found_on_official_source=found_official,
            found_on_company_document=found_doc,
            score_parts=parts,
            associated_company_count=associated,
        )

    # Phone-only path: registry landline without domain match needs multi-signal.
    # Unrelated>=4 is enough when there is no group/root exemption (combined signal,
    # not a crude "N>5 = accountant" rule alone).
    if not email and candidate.phone_e164:
        if reuse and reuse.unrelated_count >= 4 and reuse.same_root_count == 0 and reuse.same_group_count == 0:
            return OwnershipResult(
                ownership_status=OwnershipStatus.SHARED_EXTERNAL_CONTACT.value,
                ownership_reason=(f"Phone shared by {reuse.unrelated_count} unrelated CNPJs"),
                verification_reason="SHARED_PHONE",
                confidence=0.15,
                enrollable=False,
                third_party_type=tp_type,
                found_on_official_source=found_official,
                found_on_company_document=found_doc,
                score_parts=parts,
                associated_company_count=associated,
            )
        if official_src and (not reuse or reuse.unrelated_count <= 1 or reuse.same_root_count > 0):
            score += 10
            parts.append("phone_official_single_holder=+10")

    conf = max(0.0, min(1.0, score / 100.0))

    # Map score bands → ownership
    if art_crea_only and score < 70:
        return OwnershipResult(
            ownership_status=OwnershipStatus.UNRESOLVED.value,
            ownership_reason="art_crea_engineer_not_auto_promoted_to_commercial",
            verification_reason="ART_CREA_HINT_ONLY",
            confidence=conf,
            enrollable=False,
            domain_matches_company=domain_match,
            found_on_official_source=found_official,
            found_on_company_document=found_doc,
            score_parts=parts,
            associated_company_count=associated,
        )

    # Freemail COMPANY_OWNED only with company-authored document + official source.
    # Multi-source page counts alone are inflated by crawl and never enroll freemail.
    if freemail:
        strong_freemail = bool(found_doc and found_official and score >= 55)
        if strong_freemail:
            status = OwnershipStatus.COMPANY_OWNED.value
            reason = "freemail_with_company_document_proof"
            vreason = "VERIFIED_FREEMAIL"
        elif score >= 40 or ((independent_sources_count or 0) >= 2 and found_official and score >= 30):
            status = OwnershipStatus.LIKELY_COMPANY_OWNED.value
            reason = "freemail_partial_proof_review_required"
            vreason = "REVIEW_REQUIRED"
        else:
            status = OwnershipStatus.UNRESOLVED.value
            reason = "freemail_insufficient_ownership_proof"
            vreason = "UNRESOLVED_FREEMAIL"
        return OwnershipResult(
            ownership_status=status,
            ownership_reason=reason,
            verification_reason=vreason,
            confidence=conf,
            enrollable=status in ENROLLABLE_OWNERSHIP,
            third_party_type=None,
            domain_matches_company=domain_match,
            found_on_official_source=found_official,
            found_on_company_document=found_doc,
            score_parts=parts,
            associated_company_count=associated,
        )

    # Non-freemail email: hard conjunctive gate — score alone never enrolls.
    # COMPANY_OWNED requires residual-safe domain_match OR (document + domain alignment).
    # Site-only weak brand hits stay LIKELY (review) and never enrollable.
    if email:
        identity_ok = bool(domain_match)
        if not identity_ok and found_doc and domain:
            from scripts.confenge_contact_resolution.discovery.official_domain import (
                email_domain_aligned_with_company as _eda,
            )

            identity_ok = _eda(
                domain,
                identity_label,
                official_domain=(ctx.official_domain or None),
            )
        if identity_ok and score >= 55:
            status = OwnershipStatus.COMPANY_OWNED.value
            reason = "domain_match_company_owned" if domain_match else "document_proof_company_owned"
            vreason = "VERIFIED" if score >= 70 else "OBSERVED_COMPANY"
            parts.append(f"identity_gate_ok score={score}")
        elif score >= 40:
            status = OwnershipStatus.LIKELY_COMPANY_OWNED.value
            reason = "consistent_but_not_definitive_ownership_signals"
            vreason = "REVIEW_REQUIRED"
            if not identity_ok:
                parts.append("identity_gate_blocked_company_owned")
        elif score >= 15:
            status = OwnershipStatus.UNRESOLVED.value
            reason = "insufficient_ownership_evidence"
            vreason = "UNRESOLVED"
            if not identity_ok:
                parts.append("identity_gate_blocked_company_owned")
        else:
            status = OwnershipStatus.UNRESOLVED.value
            reason = "weak_or_conflicting_ownership_signals"
            vreason = "UNRESOLVED"
            if not identity_ok:
                parts.append("identity_gate_blocked_company_owned")
    else:
        # Phone-only: scrape host (site/source_url) must be residual-safe vs razao.
        # Preferring official_domain over residual site allowed caiafafacilities phones
        # when official_domain=connector.eng.br — site host is authoritative.
        from scripts.confenge_contact_resolution.discovery.official_domain import (
            is_credible_company_domain as _icd,
        )

        phone_scrape = (scrape_host or "").removeprefix("www.").lower() if scrape_host else ""
        if phone_scrape:
            phone_host_ok = _icd(phone_scrape, identity_label)
            if not phone_host_ok:
                parts.append(f"phone_scrape_host_unaligned={phone_scrape}")
        else:
            # No page host (registry-only): never COMPANY_OWNED from registry alone
            phone_host_ok = False
            parts.append("phone_no_scrape_host")
        if not phone_host_ok and (strong_page or found_official):
            if strong_page:
                score -= 15
                parts.append("phone_unaligned_page_credit_revoked=-15")
            if found_official and not found_doc:
                score -= 40
                parts.append("phone_unaligned_official_source_credit_revoked=-40")
            conf = max(0.0, min(1.0, score / 100.0))

        if phone_host_ok and score >= 60 and (strong_page or found_doc or official_src):
            status = OwnershipStatus.LIKELY_COMPANY_OWNED.value
            reason = "phone_signals_review_or_company"
            vreason = "REVIEW_REQUIRED"
        elif phone_host_ok and score >= 40:
            status = OwnershipStatus.LIKELY_COMPANY_OWNED.value
            reason = "consistent_but_not_definitive_ownership_signals"
            vreason = "REVIEW_REQUIRED"
        elif not phone_host_ok:
            status = OwnershipStatus.UNRESOLVED.value
            reason = "phone_source_host_not_company_aligned"
            vreason = "UNRESOLVED"
            parts.append("phone_identity_gate_blocked")
        else:
            status = OwnershipStatus.UNRESOLVED.value
            reason = "insufficient_ownership_evidence"
            vreason = "UNRESOLVED"

        # Phone-only company-owned: residual-safe scrape host + site/doc (not registry alone)
        if (
            candidate.phone_e164
            and phone_host_ok
            and status == OwnershipStatus.LIKELY_COMPANY_OWNED.value
            and (strong_page or found_doc)
            and (not reuse or reuse.unrelated_count <= 1)
        ):
            status = OwnershipStatus.COMPANY_OWNED.value
            reason = "phone_on_official_company_source_single_holder"
            vreason = "VERIFIED_PHONE"

    return OwnershipResult(
        ownership_status=status,
        ownership_reason=reason,
        verification_reason=vreason,
        confidence=conf,
        enrollable=status in ENROLLABLE_OWNERSHIP and not candidate.dnc and not candidate.bounce,
        third_party_type=tp_type if status == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value else None,
        domain_matches_company=domain_match if email else None,
        found_on_official_source=found_official,
        found_on_company_document=found_doc,
        score_parts=parts,
        associated_company_count=associated,
    )


def apply_ownership_to_candidate(
    candidate: ContactCandidate,
    result: OwnershipResult,
    *,
    independent_sources_count: int = 1,
    source_urls: list[str] | None = None,
    source_types: list[str] | None = None,
) -> ContactCandidate:
    """Mutate candidate with ownership fields and enrollable gate."""
    candidate.ownership_status = result.ownership_status
    candidate.ownership_reason = result.ownership_reason
    candidate.verification_reason = result.verification_reason
    candidate.third_party_type = result.third_party_type
    candidate.domain_matches_company = result.domain_matches_company
    candidate.found_on_official_source = result.found_on_official_source
    candidate.found_on_company_document = result.found_on_company_document
    candidate.associated_company_count = result.associated_company_count
    candidate.independent_sources_count = independent_sources_count
    candidate.confidence = round(max(candidate.confidence * 0.35, result.confidence), 4)
    candidate.freshness_class = freshness_class_from_days(candidate.freshness_days)
    if source_urls is not None:
        candidate.source_urls = source_urls
    elif candidate.source and candidate.source.source_url:
        candidate.source_urls = [candidate.source.source_url]
    if source_types is not None:
        candidate.source_types = source_types
    elif candidate.source and candidate.source.source_type:
        candidate.source_types = [candidate.source.source_type]

    if candidate.email and candidate.phone_e164:
        candidate.contact_type = "BOTH"
    elif candidate.email:
        candidate.contact_type = "EMAIL"
    elif candidate.phone_e164:
        candidate.contact_type = "PHONE"
    else:
        candidate.contact_type = "UNKNOWN"

    # Enrollable only COMPANY_OWNED / HUMAN_CONFIRMED; pattern guess always false
    is_guess = bool(candidate.email_layers and candidate.email_layers.pattern_guessed)
    if is_guess or candidate.verification_status in {
        VerificationStatus.CANDIDATE_UNVERIFIED.value,
        VerificationStatus.PATTERN_GUESS.value,
    }:
        candidate.enrollable = False
        # Keep CANDIDATE_UNVERIFIED for wire compatibility; PATTERN_GUESS in reason.
        if candidate.verification_status == VerificationStatus.PATTERN_GUESS.value:
            candidate.verification_status = VerificationStatus.CANDIDATE_UNVERIFIED.value
        if not candidate.verification_reason:
            candidate.verification_reason = "PATTERN_GUESS"
    else:
        candidate.enrollable = bool(result.enrollable) and not candidate.dnc and not candidate.bounce
        if candidate.enrollable and result.ownership_status == OwnershipStatus.COMPANY_OWNED.value:
            if candidate.email:
                candidate.verification_status = VerificationStatus.VERIFIED.value
        elif result.ownership_status == OwnershipStatus.LIKELY_COMPANY_OWNED.value:
            if candidate.verification_status == VerificationStatus.OBSERVED.value:
                candidate.verification_status = VerificationStatus.REVIEW_REQUIRED.value

    candidate.limitations = list(candidate.limitations or [])
    if result.score_parts:
        candidate.limitations.append("ownership_score:" + ",".join(result.score_parts[:12]))
    if not candidate.enrollable and result.ownership_reason:
        candidate.limitations.append(f"not_enrollable:{result.ownership_status}")
    return candidate


def primary_rejection_reason(candidate: ContactCandidate) -> str:
    """Single primary rejection bucket for metrics (partition, not multi-count)."""
    is_guess = bool(candidate.email_layers and candidate.email_layers.pattern_guessed)
    vs = (candidate.verification_status or "").upper()
    vreason = (candidate.verification_reason or "").upper()
    # Pattern guess wins as primary when present (even if also CANDIDATE_UNVERIFIED)
    if (
        is_guess
        or vs == VerificationStatus.PATTERN_GUESS.value
        or vreason == "PATTERN_GUESS"
        or "pattern_guess" in (candidate.ownership_reason or "").lower()
    ):
        return "PATTERN_GUESS"

    tp = (candidate.third_party_type or "").upper()
    own = (candidate.ownership_status or "").upper()
    reason = (candidate.ownership_reason or "").upper()
    if tp == "ACCOUNTING" or "ACCOUNTING" in reason or "CONTAB" in reason:
        return "ACCOUNTING"
    if tp == "LEGAL" or "LEGAL" in reason or "ADVOCAC" in reason:
        return "LEGAL"
    if own == OwnershipStatus.SHARED_EXTERNAL_CONTACT.value or "SHARED_EXTERNAL" in reason:
        return "SHARED_EXTERNAL"
    if own == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value or tp:
        return "OTHER_THIRD_PARTY"
    return "INVALID"


def rejected_contact_dict(candidate: ContactCandidate) -> dict[str, Any]:
    """Serialize a rejected/non-enrollable candidate for rejected_contacts."""
    primary = primary_rejection_reason(candidate)
    secondary: list[str] = []
    tp = (candidate.third_party_type or "").upper()
    if tp and primary != "ACCOUNTING" and tp == "ACCOUNTING":
        secondary.append("ACCOUNTING")
    if tp and primary not in {tp, "OTHER_THIRD_PARTY"}:
        secondary.append(tp)
    if candidate.email_layers and candidate.email_layers.pattern_guessed and primary != "PATTERN_GUESS":
        secondary.append("PATTERN_GUESS")
    if (candidate.ownership_status or "") == OwnershipStatus.SHARED_EXTERNAL_CONTACT.value:
        if primary != "SHARED_EXTERNAL":
            secondary.append("SHARED_EXTERNAL")
    return {
        "type": candidate.contact_type
        if candidate.contact_type != "UNKNOWN"
        else ("EMAIL" if candidate.email else "PHONE" if candidate.phone_e164 else "UNKNOWN"),
        "value": candidate.email or candidate.phone_e164 or candidate.phone_raw,
        "ownership_status": candidate.ownership_status,
        "third_party_type": candidate.third_party_type,
        "enrollable": False,
        "reason": candidate.ownership_reason,
        "primary_rejection_reason": primary,
        "secondary_signals": secondary,
        "verification_status": candidate.verification_status,
        "confidence": candidate.confidence,
        "associated_company_count": candidate.associated_company_count,
        "sources": [
            {
                "source_type": candidate.source.source_type if candidate.source else None,
                "source_url": candidate.source.source_url if candidate.source else None,
                "source_document": candidate.source.source_document if candidate.source else None,
                "source_date": candidate.source.source_date if candidate.source else None,
            }
        ],
        "role_class": candidate.role_class,
        "candidate_id": candidate.candidate_id,
    }


def commercial_state_for_resolution(
    candidates: list[ContactCandidate],
    rejected: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return (processing_state, commercial_contact_state)."""
    from scripts.confenge_contact_resolution.models import (
        CommercialContactState,
        CompanyProcessingState,
    )

    enrollable = [c for c in candidates if c.enrollable]
    likely = [c for c in candidates if c.ownership_status == OwnershipStatus.LIKELY_COMPANY_OWNED.value]
    if enrollable:
        return (
            CompanyProcessingState.FOUND_VERIFIED.value,
            CommercialContactState.CONTACT_READY.value,
        )
    if likely or any(
        c.ownership_status
        in {
            OwnershipStatus.UNRESOLVED.value,
            OwnershipStatus.SHARED_EXTERNAL_CONTACT.value,
            OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value,
        }
        for c in candidates
    ):
        # Has candidates but none enrollable
        if candidates or rejected:
            return (
                CompanyProcessingState.FOUND_REVIEW_REQUIRED.value,
                CommercialContactState.CONTACT_REVIEW_REQUIRED.value,
            )
    if not candidates and not rejected:
        return (
            CompanyProcessingState.NO_CONTACT.value,
            CommercialContactState.NO_CONTACT_YET.value,
        )
    return (
        CompanyProcessingState.FOUND_REVIEW_REQUIRED.value,
        CommercialContactState.CONTACT_REVIEW_REQUIRED.value,
    )
