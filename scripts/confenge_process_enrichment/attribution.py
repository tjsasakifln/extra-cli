"""Entity attribution — prevent government/competitor false positives.

Finding an email in a process PDF does NOT mean it belongs to the lead.
"""

from __future__ import annotations

import re
from typing import Any

from scripts.confenge_process_enrichment.identifiers import (
    digits_only,
    normalize_cnpj,
    normalize_company_name,
)
from scripts.confenge_process_enrichment.models import EpistemicClass

# Government / public-body email domains and role cues
_GOV_DOMAIN_SUFFIXES = (
    ".gov.br",
    ".mil.br",
    ".jus.br",
    ".leg.br",
    ".mp.br",
    ".def.br",
)
_GOV_LOCAL_HINTS = re.compile(
    r"(?i)\b(prefeitura|camara|c[aâ]mara|governo|secretaria|tribunal|"
    r"ministerio|minist[eé]rio|autarquia|fundacao|funda[cç][aã]o|"
    r"instituto federal|universidade federal|procuradoria|"
    r"comissao de licit|comiss[aã]o de licit|pregoeiro|equipe de apoio|"
    r"fiscal do contrato|gestor do contrato|servidor)\b"
)
_COMPANY_REP_HINTS = re.compile(
    r"(?i)\b(representante legal|procurador|preposto|respons[aá]vel t[eé]cnico|"
    r"s[oó]cio|diretor|propriet[aá]rio|licitante|contratad[ao]|"
    r"pela empresa|da empresa|em nome da)\b"
)
_COMPANY_DOC_HINTS = re.compile(
    r"(?i)\b(proposta|declara[cç][aã]o|procura[cç][aã]o|credenciamento|"
    r"carta proposta|requerimento|pedido de aditivo|pedido de reajuste)\b"
)
_OTHER_BIDDER_HINTS = re.compile(
    r"(?i)\b(concorrente|outra licitante|demais licitantes|classificad[oa]s?)\b"
)
_FREEMAIL = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "hotmail.com",
        "outlook.com",
        "yahoo.com",
        "yahoo.com.br",
        "live.com",
        "icloud.com",
        "uol.com.br",
        "bol.com.br",
        "terra.com.br",
        "ig.com.br",
    }
)


def email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1].strip().lower()


def is_gov_domain(domain: str | None) -> bool:
    if not domain:
        return False
    d = domain.lower()
    return any(d.endswith(sfx) for sfx in _GOV_DOMAIN_SUFFIXES)


def is_freemail(domain: str | None) -> bool:
    return bool(domain and domain.lower() in _FREEMAIL)


def domain_matches_company(
    domain: str | None,
    *,
    company_name: str | None = None,
    known_domains: list[str] | None = None,
) -> bool:
    if not domain:
        return False
    d = domain.lower()
    if is_gov_domain(d) or is_freemail(d):
        return False
    for kd in known_domains or []:
        if d == kd.lower() or d.endswith("." + kd.lower()):
            return True
    # Name heuristic: significant tokens (≥4 chars) vs domain base / full domain
    name = normalize_company_name(company_name)
    stop = {
        "CONSTRUTORA",
        "CONSTRUCOES",
        "CONSTRUCAO",
        "ENGENHARIA",
        "SERVICOS",
        "COMERCIO",
        "INDUSTRIA",
        "EMPRESA",
        "GRUPO",
        "BRASIL",
        "LIMITADA",
    }
    tokens = [t for t in name.split() if len(t) >= 4 and t not in stop][:5]
    base = d.split(".")[0].replace("-", "")
    for t in tokens:
        tl = t.lower().replace("-", "")
        if len(tl) >= 4 and (tl in base or base in tl or tl in d.replace(".", "")):
            return True
    return False


def classify_observation(
    *,
    email: str | None = None,
    person_name: str | None = None,
    role_text: str | None = None,
    surrounding_text: str | None = None,
    document_title: str | None = None,
    document_category: str | None = None,
    company_cnpj: str | None = None,
    company_name: str | None = None,
    known_company_domains: list[str] | None = None,
    org_cnpj: str | None = None,
    other_bidder_cnpjs: list[str] | None = None,
    document_produced_by_company: bool | None = None,
    explicit_company_rep: bool | None = None,
) -> EpistemicClass:
    """Classify association between an extracted channel and the lead company."""
    blob = " ".join(
        x for x in (role_text, surrounding_text, document_title, document_category, person_name) if x
    )
    domain = email_domain(email)

    # Explicit public official signals (gov domain, or gov role cues without freemail)
    if is_gov_domain(domain):
        return EpistemicClass.PUBLIC_OFFICIAL
    if _GOV_LOCAL_HINTS.search(blob or "") and not is_freemail(domain):
        # Government role language near a non-freemail address — likely organ staff
        if domain and domain_matches_company(
            domain, company_name=company_name, known_domains=known_company_domains
        ):
            pass
        else:
            return EpistemicClass.PUBLIC_OFFICIAL

    # Competitor
    if _OTHER_BIDDER_HINTS.search(blob or ""):
        return EpistemicClass.OTHER_BIDDER
    if other_bidder_cnpjs and company_cnpj:
        # If text contains another bidder CNPJ near the contact, treat as other bidder
        digits_blob = digits_only(blob)
        lead = normalize_cnpj(company_cnpj)
        for other in other_bidder_cnpjs:
            od = normalize_cnpj(other)
            if od and od != lead and od in digits_blob:
                return EpistemicClass.OTHER_BIDDER

    # Org CNPJ in text without company CNPJ → likely organ document mentioning public staff
    if org_cnpj and company_cnpj:
        d_blob = digits_only(blob)
        if normalize_cnpj(org_cnpj) in d_blob and normalize_cnpj(company_cnpj) not in d_blob:
            if _GOV_LOCAL_HINTS.search(blob or ""):
                return EpistemicClass.PUBLIC_OFFICIAL

    # Company domain observed
    if domain_matches_company(domain, company_name=company_name, known_domains=known_company_domains):
        return EpistemicClass.COMPANY_DOMAIN_OBSERVED

    cnpj_in_blob = bool(company_cnpj and normalize_cnpj(company_cnpj) in digits_only(blob))
    rep_hint = bool(_COMPANY_REP_HINTS.search(blob or ""))

    # Explicit rep recorded by admin
    if explicit_company_rep or (rep_hint and cnpj_in_blob):
        return EpistemicClass.ADMIN_RECORDED_COMPANY_REP

    # Company-authored document
    if document_produced_by_company or _COMPANY_DOC_HINTS.search(
        " ".join(x for x in (document_title, document_category) if x)
    ):
        if email or person_name:
            # Require some company binding for freemail
            if domain and is_freemail(domain):
                if cnpj_in_blob or rep_hint:
                    return EpistemicClass.COMPANY_DECLARED
                return EpistemicClass.THIRD_PARTY_REFERENCE
            return EpistemicClass.COMPANY_DECLARED

    # Non-gov private domain co-located with supplier CNPJ in process docs is
    # often the contractor contact block (contract PDF / qualification).
    if (
        email
        and domain
        and not is_gov_domain(domain)
        and cnpj_in_blob
        and (rep_hint or not is_freemail(domain))
    ):
        if is_freemail(domain) and rep_hint:
            return EpistemicClass.ADMIN_RECORDED_COMPANY_REP
        if not is_freemail(domain):
            return EpistemicClass.COMPANY_DOMAIN_OBSERVED

    if email and cnpj_in_blob and rep_hint:
        return EpistemicClass.ADMIN_RECORDED_COMPANY_REP

    if email or person_name:
        return EpistemicClass.THIRD_PARTY_REFERENCE
    return EpistemicClass.UNKNOWN_ENTITY


def is_exportable_to_warmbly(epistemic: EpistemicClass | str) -> bool:
    cls = EpistemicClass(epistemic) if not isinstance(epistemic, EpistemicClass) else epistemic
    return cls in {
        EpistemicClass.COMPANY_DECLARED,
        EpistemicClass.ADMIN_RECORDED_COMPANY_REP,
        EpistemicClass.COMPANY_DOMAIN_OBSERVED,
    }
