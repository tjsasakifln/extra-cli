"""Cross-contract account contact graph with dedup and freshness."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from scripts.confenge_process_enrichment.contact_extract import is_functional_mailbox
from scripts.confenge_process_enrichment.models import (
    AccountContactGraph,
    ContactObservation,
    EpistemicClass,
    PersonNode,
    _now_iso,
)


def _norm_email(email: str | None) -> str | None:
    if not email:
        return None
    return email.strip().lower()


def _norm_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    d = re.sub(r"\D", "", phone)
    if d.startswith("55") and len(d) > 11:
        d = d[2:]
    return d or None


def _norm_name(name: str | None) -> str | None:
    if not name:
        return None
    n = re.sub(r"\s+", " ", name.strip().lower())
    return n if len(n) >= 3 else None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    s = str(value)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def role_freshness_score(newest_source_date: str | None, *, as_of: datetime | None = None) -> float:
    """1.0 for recent, decays with age."""
    as_of = as_of or datetime.now(UTC)
    dt = _parse_date(newest_source_date)
    if not dt:
        return 0.4
    days = max(0, (as_of - dt).days)
    if days <= 180:
        return 1.0
    if days <= 365:
        return 0.85
    if days <= 730:
        return 0.6
    if days <= 1460:
        return 0.35
    return 0.15


def _person_key(obs: ContactObservation) -> str:
    email = _norm_email(obs.email)
    if email and not is_functional_mailbox(email):
        return f"email:{email}"
    phone = _norm_phone(obs.phone)
    name = _norm_name(obs.person_name)
    if name and phone:
        return f"name_phone:{name}|{phone}"
    if name and email:
        return f"name_email:{name}|{email}"
    if phone:
        return f"phone:{phone}"
    if name:
        # Name-only keys must NOT merge across companies — include cnpj
        return f"name_only:{obs.company_cnpj or 'unk'}|{name}"
    if email:
        return f"email:{email}"
    return f"anon:{id(obs)}"


def _confidence(obs_list: list[ContactObservation], freshness: float) -> float:
    rank = {
        EpistemicClass.COMPANY_DECLARED: 1.0,
        EpistemicClass.ADMIN_RECORDED_COMPANY_REP: 0.95,
        EpistemicClass.COMPANY_DOMAIN_OBSERVED: 0.9,
        EpistemicClass.THIRD_PARTY_REFERENCE: 0.2,
        EpistemicClass.PUBLIC_OFFICIAL: 0.0,
        EpistemicClass.OTHER_BIDDER: 0.0,
        EpistemicClass.UNKNOWN_ENTITY: 0.1,
    }
    base = max(rank.get(o.epistemic_class, 0.1) for o in obs_list)
    multi = min(0.15, 0.05 * (len({o.source_document_id for o in obs_list if o.source_document_id}) - 1))
    return min(1.0, base + multi) * (0.5 + 0.5 * freshness)


def build_account_contact_graph(
    observations: list[ContactObservation],
    *,
    account_cnpj: str,
    dnc_emails: set[str] | None = None,
    bounced_emails: set[str] | None = None,
) -> AccountContactGraph:
    """Merge observations into people + functional mailboxes; reject blocked classes."""
    dnc_emails = {e.lower() for e in (dnc_emails or set())}
    bounced_emails = {e.lower() for e in (bounced_emails or set())}

    rejected: list[ContactObservation] = []
    functional: list[ContactObservation] = []
    buckets: dict[str, list[ContactObservation]] = {}

    for obs in observations:
        if obs.pattern_guessed:
            rejected.append(obs)
            continue
        if obs.email and obs.email.lower() in dnc_emails:
            obs.extra = {**(obs.extra or {}), "dnc": True}
            rejected.append(obs)
            continue
        if obs.email and obs.email.lower() in bounced_emails:
            obs.extra = {**(obs.extra or {}), "bounce": True}
            rejected.append(obs)
            continue
        if obs.epistemic_class in {
            EpistemicClass.PUBLIC_OFFICIAL,
            EpistemicClass.OTHER_BIDDER,
            EpistemicClass.UNKNOWN_ENTITY,
        }:
            rejected.append(obs)
            continue
        if obs.email and is_functional_mailbox(obs.email) and not obs.person_name:
            if obs.epistemic_class == EpistemicClass.THIRD_PARTY_REFERENCE:
                rejected.append(obs)
                continue
            functional.append(obs)
            continue
        if obs.epistemic_class == EpistemicClass.THIRD_PARTY_REFERENCE:
            rejected.append(obs)
            continue
        key = _person_key(obs)
        buckets.setdefault(key, []).append(obs)

    people: list[PersonNode] = []
    for key, obs_list in buckets.items():
        # Homonym safety: never merge name-only across different emails/phones already keyed
        emails = sorted({_norm_email(o.email) for o in obs_list if o.email})
        emails = [e for e in emails if e]
        phones = sorted({_norm_phone(o.phone) for o in obs_list if o.phone})
        phones = [p for p in phones if p]
        names = [o.person_name for o in obs_list if o.person_name]
        roles = sorted({o.role_observed for o in obs_list if o.role_observed})
        dates = [o.observation_date or o.last_seen_at or o.first_seen_at for o in obs_list]
        dates_s = sorted(d for d in dates if d)
        newest = dates_s[-1] if dates_s else None
        oldest = dates_s[0] if dates_s else None
        fresh = role_freshness_score(newest)
        sources = {o.source_document_id or o.source_url for o in obs_list if o.source_document_id or o.source_url}
        ep_best = max(
            obs_list,
            key=lambda o: {
                EpistemicClass.COMPANY_DECLARED: 3,
                EpistemicClass.ADMIN_RECORDED_COMPANY_REP: 2,
                EpistemicClass.COMPANY_DOMAIN_OBSERVED: 1,
            }.get(o.epistemic_class, 0),
        ).epistemic_class.value
        people.append(
            PersonNode(
                person_key=key,
                name=names[0] if names else None,
                emails=emails,
                phones=phones,
                roles=roles,
                observations=obs_list,
                first_seen_at=oldest,
                last_seen_at=newest,
                observation_count=len(obs_list),
                source_count=len(sources),
                newest_source_date=newest,
                role_freshness=fresh,
                confidence=_confidence(obs_list, fresh),
                epistemic_best=ep_best,
            )
        )

    people.sort(key=lambda p: (p.confidence * p.role_freshness, p.source_count), reverse=True)
    return AccountContactGraph(
        account_cnpj=account_cnpj,
        people=people,
        functional_mailboxes=functional,
        rejected=rejected,
        built_at=_now_iso(),
    )


# Purpose-aware role ranking (configurable priors)
SERVICE_ROLE_PRIORITY: dict[str, list[str]] = {
    "reajuste": [
        "contratos",
        "diretor",
        "financeiro",
        "engenheiro",
        "representante_legal",
        "preposto",
        "socio",
    ],
    "orcamento": [
        "orcamento",
        "licitacoes",
        "engenheiro",
        "comercial",
        "diretor",
    ],
    "diretoria_b2g": [
        "socio",
        "diretor",
        "comercial",
        "administrativo",
        "representante_legal",
    ],
    "generic": [
        "diretor",
        "comercial",
        "representante_legal",
        "licitacoes",
        "preposto",
        "socio",
    ],
}


def select_best_for_service(
    graph: AccountContactGraph,
    service: str = "generic",
) -> dict[str, Any] | None:
    """Pick best named contact for a CONFENGE service; fall back to referral mailbox."""
    prio = SERVICE_ROLE_PRIORITY.get(service, SERVICE_ROLE_PRIORITY["generic"])
    best: tuple[float, PersonNode] | None = None
    for person in graph.people:
        if not person.emails:
            continue
        role_score = 0.0
        for i, role in enumerate(prio):
            if role in (person.roles or []):
                role_score = 1.0 - (i * 0.08)
                break
        if role_score == 0.0:
            role_score = 0.25
        score = person.confidence * person.role_freshness * role_score
        if best is None or score > best[0]:
            best = (score, person)
    if best:
        p = best[1]
        return {
            "person_name": p.name,
            "email": p.emails[0] if p.emails else None,
            "phone": p.phones[0] if p.phones else None,
            "roles": p.roles,
            "confidence": round(best[0], 4),
            "person_key": p.person_key,
            "epistemic_best": p.epistemic_best,
            "contact_class": "named_person",
            "freshness": p.role_freshness,
            "service": service,
        }
    # referral route
    for m in graph.functional_mailboxes:
        if m.email and m.is_commercially_usable():
            return {
                "person_name": None,
                "email": m.email,
                "phone": m.phone,
                "roles": [m.role_observed] if m.role_observed else [],
                "confidence": 0.45,
                "person_key": f"mailbox:{m.email}",
                "epistemic_best": m.epistemic_class.value,
                "contact_class": "referral_mailbox",
                "freshness": role_freshness_score(m.observation_date),
                "service": service,
            }
    return None
