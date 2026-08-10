"""Commercial identity extraction from document text with provenance."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from scripts.confenge_process_enrichment.attribution import classify_observation
from scripts.confenge_process_enrichment.identifiers import normalize_cnpj
from scripts.confenge_process_enrichment.models import ContactObservation, EpistemicClass, _now_iso
from scripts.confenge_process_enrichment.signature_blocks import extract_signature_intelligence

_EMAIL_RE = re.compile(
    r"(?i)\b([a-z0-9][a-z0-9._%+\-]{0,63}@[a-z0-9][a-z0-9.\-]{1,63}\.[a-z]{2,24})\b"
)
_PHONE_RE = re.compile(
    r"(?i)(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)(?:9\s?)?\d{4,5}[-\s]?\d{4}"
)
_CNPJ_RE = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")

# Roles useful for CONFENGE services
_ROLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)representante\s+legal"), "representante_legal"),
    (re.compile(r"(?i)\bpreposto\b"), "preposto"),
    (re.compile(r"(?i)respons[aá]vel\s+t[eé]cnico"), "responsavel_tecnico"),
    (re.compile(r"(?i)\bprocurador\b"), "procurador"),
    (re.compile(r"(?i)\bdiretor\b"), "diretor"),
    (re.compile(r"(?i)\bs[oó]cio\b|\bpropriet[aá]rio\b"), "socio"),
    (re.compile(r"(?i)\blicita[cç]"), "licitacoes"),
    (re.compile(r"(?i)\bor[cç]amento|\bbdi\b"), "orcamento"),
    (re.compile(r"(?i)\bcomercial\b"), "comercial"),
    (re.compile(r"(?i)\bcontratos?\b"), "contratos"),
    (re.compile(r"(?i)\bfinanceiro\b"), "financeiro"),
    (re.compile(r"(?i)\badministrativ"), "administrativo"),
    (re.compile(r"(?i)\bengenheir"), "engenheiro"),
]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _context_window(text: str, start: int, end: int, radius: int = 220) -> str:
    a = max(0, start - radius)
    b = min(len(text), end + radius)
    return text[a:b]


def _role_near(context: str) -> str | None:
    for pat, role in _ROLE_PATTERNS:
        if pat.search(context):
            return role
    return None


def extract_contacts_from_text(
    text: str,
    *,
    company_cnpj: str | None = None,
    company_name: str | None = None,
    known_company_domains: list[str] | None = None,
    org_cnpj: str | None = None,
    other_bidder_cnpjs: list[str] | None = None,
    source_document_id: str | None = None,
    source_url: str | None = None,
    document_title: str | None = None,
    document_type: str | None = None,
    document_produced_by_company: bool | None = None,
    observation_date: str | None = None,
    contract_id: str | None = None,
    page: int | None = None,
) -> list[ContactObservation]:
    """Extract provenanced contacts from free text + signature intelligence."""
    if not text or not text.strip():
        return []

    observations: list[ContactObservation] = []
    cnpj = normalize_cnpj(company_cnpj) if company_cnpj else None

    # Signature / form first (higher precision)
    for hit in extract_signature_intelligence(text, page=page):
        ctx = hit.evidence_text
        ep = classify_observation(
            email=hit.email,
            person_name=hit.person_name,
            role_text=hit.role_observed,
            surrounding_text=ctx,
            document_title=document_title,
            document_category=document_type,
            company_cnpj=cnpj,
            company_name=company_name or hit.company_name,
            known_company_domains=known_company_domains,
            org_cnpj=org_cnpj,
            other_bidder_cnpjs=other_bidder_cnpjs,
            document_produced_by_company=document_produced_by_company,
            explicit_company_rep=bool(hit.role_observed),
        )
        observations.append(
            ContactObservation(
                email=hit.email,
                phone=hit.phone,
                person_name=hit.person_name,
                role_observed=hit.role_observed,
                company_cnpj=cnpj,
                source_document_id=source_document_id,
                source_url=source_url,
                page=page if page is not None else hit.page,
                evidence_text_hash=hit.evidence_hash(),
                observation_date=observation_date or _now_iso()[:10],
                epistemic_class=ep,
                document_type=document_type,
                contract_id=contract_id,
                first_seen_at=observation_date,
                last_seen_at=observation_date,
                extra={"parser": hit.kind},
            )
        )

    # Free-text emails with local context
    seen_emails = {o.email for o in observations if o.email}
    full_digits = re.sub(r"\D", "", text)
    company_present = bool(cnpj and cnpj in full_digits)
    # Lightweight doc-level company name presence for attribution
    name_present = False
    if company_name:
        tokens = [t for t in re.findall(r"[A-Za-zÀ-ÿ]{5,}", company_name) if t.lower() not in {"ltda", "construtora", "engenharia"}]
        name_present = any(t.lower() in text.lower() for t in tokens[:3])

    for m in _EMAIL_RE.finditer(text):
        email = m.group(1).lower()
        if email in seen_emails:
            continue
        # skip obvious non-contact
        if email.endswith((".png", ".jpg", ".gif", ".css", ".js")):
            continue
        ctx = _context_window(text, m.start(), m.end(), radius=320)
        # If company is in the document but not in local window, append anchors
        if company_present and cnpj and cnpj not in re.sub(r"\D", "", ctx):
            ctx = f"{ctx}\nCNPJ_EMPRESA:{cnpj}"
        if name_present and company_name and company_name[:20].lower() not in ctx.lower():
            ctx = f"{ctx}\nEMPRESA:{company_name}"
        role = _role_near(ctx)
        ep = classify_observation(
            email=email,
            role_text=role,
            surrounding_text=ctx,
            document_title=document_title,
            document_category=document_type,
            company_cnpj=cnpj,
            company_name=company_name,
            known_company_domains=known_company_domains,
            org_cnpj=org_cnpj,
            other_bidder_cnpjs=other_bidder_cnpjs,
            document_produced_by_company=document_produced_by_company,
        )
        observations.append(
            ContactObservation(
                email=email,
                person_name=None,
                role_observed=role,
                company_cnpj=cnpj,
                source_document_id=source_document_id,
                source_url=source_url,
                page=page,
                evidence_text_hash=_hash_text(ctx),
                observation_date=observation_date or _now_iso()[:10],
                epistemic_class=ep,
                document_type=document_type,
                contract_id=contract_id,
                first_seen_at=observation_date,
                last_seen_at=observation_date,
                extra={"parser": "email_regex"},
            )
        )
        seen_emails.add(email)

    return observations


def is_functional_mailbox(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].lower()
    return local in {
        "contato",
        "contact",
        "comercial",
        "licitacao",
        "licitacoes",
        "engenharia",
        "orcamento",
        "financeiro",
        "administrativo",
        "contratos",
        "suporte",
        "sac",
        "ouvidoria",
        "rh",
        "vendas",
        "info",
        "office",
        "adm",
    } or local.startswith(("contato", "comercial", "licit"))


def pattern_guess_email(name: str, domain: str) -> str | None:
    """Generate investigation-only pattern guess — NEVER enrollable."""
    parts = re.findall(r"[a-zA-Z]+", name or "")
    if len(parts) < 2 or not domain:
        return None
    return f"{parts[0].lower()}.{parts[-1].lower()}@{domain.lower()}"
