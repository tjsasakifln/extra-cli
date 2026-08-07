"""Service-aware explainable ranking — not purchase probability.

Best contact depends on service context. DNC/bounce dominate and block
recommendation. Pattern-guessed emails are never recommended primary.
"""

from __future__ import annotations

from scripts.confenge_contact_resolution.models import (
    ContactCandidate,
    RoleClass,
    ServiceContext,
    VerificationStatus,
)

# Role priority weights by service (higher = better fit). Explainable tables.
_ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    ServiceContext.CLAIMS_REAJUSTE.value: {
        RoleClass.CONTRATOS.value: 1.0,
        RoleClass.DIRETORIA.value: 0.9,
        RoleClass.ENGENHARIA.value: 0.75,
        RoleClass.FINANCEIRO.value: 0.7,
        RoleClass.OWNER.value: 0.65,
        RoleClass.COMERCIAL.value: 0.45,
        RoleClass.LICITACOES.value: 0.4,
        RoleClass.GENERIC.value: 0.25,
    },
    ServiceContext.LICITACOES.value: {
        RoleClass.LICITACOES.value: 1.0,
        RoleClass.COMERCIAL.value: 0.9,
        RoleClass.DIRETORIA.value: 0.8,
        RoleClass.OWNER.value: 0.7,
        RoleClass.CONTRATOS.value: 0.55,
        RoleClass.ENGENHARIA.value: 0.45,
        RoleClass.FINANCEIRO.value: 0.35,
        RoleClass.GENERIC.value: 0.25,
    },
    ServiceContext.ORCAMENTO_MEDICOES.value: {
        RoleClass.ENGENHARIA.value: 1.0,
        RoleClass.CONTRATOS.value: 0.85,
        RoleClass.DIRETORIA.value: 0.7,
        RoleClass.OWNER.value: 0.65,
        RoleClass.FINANCEIRO.value: 0.5,
        RoleClass.COMERCIAL.value: 0.4,
        RoleClass.LICITACOES.value: 0.35,
        RoleClass.GENERIC.value: 0.25,
    },
    ServiceContext.GENERIC.value: {
        RoleClass.DIRETORIA.value: 0.85,
        RoleClass.OWNER.value: 0.8,
        RoleClass.COMERCIAL.value: 0.75,
        RoleClass.CONTRATOS.value: 0.7,
        RoleClass.LICITACOES.value: 0.65,
        RoleClass.ENGENHARIA.value: 0.6,
        RoleClass.FINANCEIRO.value: 0.55,
        RoleClass.GENERIC.value: 0.35,
    },
}

_SOURCE_WEIGHT: dict[str, float] = {
    "registry": 0.9,
    "human_outcome": 1.0,
    "contact_page": 0.75,
    "site": 0.7,
    "public_docs": 0.65,
    "web_search": 0.45,
    "unknown": 0.2,
}


def role_weight(role_class: str, service_context: str, *, small_firm: bool = False) -> float:
    table = _ROLE_WEIGHTS.get(service_context) or _ROLE_WEIGHTS[ServiceContext.GENERIC.value]
    w = table.get(role_class, table.get(RoleClass.GENERIC.value, 0.25))
    # Small-firm owner/diretoria boost only for generic context — must not
    # override specialized service priorities (licitações, contratos, etc.).
    if (
        small_firm
        and service_context in {ServiceContext.GENERIC.value, ""}
        and role_class in {RoleClass.OWNER.value, RoleClass.DIRETORIA.value}
    ):
        w = min(1.0, w + 0.15)
    return w


def score_candidate(
    c: ContactCandidate,
    *,
    service_context: str = ServiceContext.GENERIC.value,
    small_firm: bool = False,
) -> tuple[float, list[str]]:
    """Return (score, explanation bullets). Score is fit for outreach channel decision, not P(buy)."""
    explain: list[str] = []
    if c.dnc or c.bounce:
        reason = "DNC" if c.dnc else "bounce"
        explain.append(f"blocked_by_{reason}")
        return -1.0, explain

    if c.verification_status == VerificationStatus.CANDIDATE_UNVERIFIED.value:
        explain.append("pattern_guessed_not_primary")
        # keep low positive score so it can appear as candidate but not win
        base = 0.05 * c.freshness
        return base, explain

    if c.verification_status == VerificationStatus.SYNTAX_INVALID.value:
        explain.append("syntax_invalid")
        return 0.0, explain

    rw = role_weight(c.role_class, service_context, small_firm=small_firm)
    explain.append(f"role_weight[{c.role_class}]={rw:.2f} for service={service_context}")
    if (
        small_firm
        and service_context in {ServiceContext.GENERIC.value, ""}
        and c.role_class in {RoleClass.OWNER.value, RoleClass.DIRETORIA.value}
    ):
        explain.append("small_firm_owner_diretoria_boost")

    src = (c.source.source_type if c.source else "unknown") or "unknown"
    sw = _SOURCE_WEIGHT.get(src, 0.2)
    explain.append(f"source_weight[{src}]={sw:.2f}")

    contact_signal = 0.0
    if c.email and c.verification_status == VerificationStatus.OBSERVED.value:
        contact_signal += 0.35
        explain.append("observed_email")
        if c.email_layers and c.email_layers.pattern_guessed:
            contact_signal -= 0.3
        if not c.enrollable:
            contact_signal -= 0.2
    if c.phone_e164:
        contact_signal += 0.25 if c.phone_type == "mobile" else 0.18
        explain.append(f"phone_{c.phone_type}")

    if not c.email and not c.phone_e164:
        explain.append("no_channel")
        contact_signal = 0.0

    freshness = max(0.0, min(1.0, c.freshness))
    explain.append(f"freshness={freshness:.2f}")

    # confidence already encodes quality; blend lightly
    conf = max(0.0, min(1.0, c.confidence))
    score = (0.45 * rw + 0.2 * sw + 0.25 * contact_signal + 0.1 * conf) * freshness
    # Named decision-maker slightly preferred over nameless functional when roles equal
    if c.name and c.role_class != RoleClass.GENERIC.value:
        score += 0.03
        explain.append("named_role_holder")
    explain.append(f"score={score:.4f}")
    return round(score, 6), explain


def select_recommended(
    candidates: list[ContactCandidate],
    *,
    service_context: str = ServiceContext.GENERIC.value,
    small_firm: bool = False,
    account_dnc: bool = False,
    account_bounce: bool = False,
) -> tuple[list[ContactCandidate], str | None]:
    """Score, sort, mark exactly one recommended when viable. Mutates candidates.

    Hard rules:
    - ``CANDIDATE_UNVERIFIED`` (pattern-guessed) is never recommended primary.
    - Account-level DNC/bounce (human outcome / DO_NOT_CONTACT without channel)
      blocks *all* recommendations for the account.
    - Channel-level DNC/bounce only blocks that candidate.
    """
    if not candidates:
        return [], None

    scored: list[ContactCandidate] = []
    for c in candidates:
        sc, expl = score_candidate(c, service_context=service_context, small_firm=small_firm)
        c.rank_score = sc
        c.rank_explain = expl
        c.recommended = False
        c.recommendation_reason = None
        scored.append(c)

    scored.sort(key=lambda x: x.rank_score, reverse=True)

    if account_dnc or account_bounce:
        reason = "account_dnc" if account_dnc else "account_bounce"
        for c in scored:
            c.rank_explain = list(c.rank_explain or []) + [f"blocked_by_{reason}"]
            c.recommended = False
            c.recommendation_reason = None
        return scored, None

    recommended_id: str | None = None
    for c in scored:
        if c.rank_score < 0:
            continue
        if c.dnc or c.bounce:
            continue
        # Pattern-guessed personal email is never recommended primary (even with phone).
        if c.verification_status == VerificationStatus.CANDIDATE_UNVERIFIED.value:
            continue
        if not c.email and not c.phone_e164:
            continue
        if c.verification_status == VerificationStatus.SYNTAX_INVALID.value and not c.phone_e164:
            continue
        # Non-enrollable email without a phone channel cannot be primary
        if c.email and not c.enrollable and not c.phone_e164:
            continue

        c.recommended = True
        reason_parts = [
            f"Melhor fit para serviço «{service_context}»",
            f"role_class={c.role_class}",
            f"score={c.rank_score:.3f}",
        ]
        if c.email and c.enrollable:
            reason_parts.append("e-mail observado utilizável")
        elif c.email and not c.enrollable:
            reason_parts.append(
                "e-mail não enrollable; canal via telefone" if c.phone_e164 else "e-mail não enrollable"
            )
        if c.phone_e164:
            reason_parts.append(f"telefone {c.phone_type} E.164")
        c.recommendation_reason = "; ".join(reason_parts)
        recommended_id = c.candidate_id
        break

    return scored, recommended_id
