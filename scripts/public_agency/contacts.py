"""Institutional contacts only — reject personal data enrichment."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "hotmail.com",
    "yahoo.com",
    "yahoo.com.br",
    "outlook.com",
    "live.com",
    "icloud.com",
    "uol.com.br",
    "bol.com.br",
    "terra.com.br",
}


@dataclass
class ContactRecord:
    channel: str  # email | phone | form | sector
    value: str
    institutional: bool
    source: str | None = None
    rejected_reason: str | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContactValidation:
    accepted: list[ContactRecord] = field(default_factory=list)
    rejected: list[ContactRecord] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": [c.as_dict() for c in self.accepted],
            "rejected": [c.as_dict() for c in self.rejected],
            "has_institutional": bool(self.accepted),
        }


def _is_personal_email(email: str) -> bool:
    m = re.search(r"@([^>\s]+)$", email.strip().lower())
    if not m:
        return True
    domain = m.group(1).lower()
    if domain in PERSONAL_EMAIL_DOMAINS:
        return True
    # institutional heuristics
    if any(x in domain for x in (".gov.br", "prefeitura", "pm.", "sc.gov", "edu.br")):
        return False
    # unknown domain → require explicit institutional marker
    return not any(x in domain for x in ("municipio", "camara", "autarquia", "org.br"))


def validate_contact(
    *,
    channel: str,
    value: str,
    source: str | None = None,
    officially_published: bool = False,
) -> ContactRecord:
    v = (value or "").strip()
    if not v:
        return ContactRecord(
            channel=channel,
            value=v,
            institutional=False,
            source=source,
            rejected_reason="empty",
        )

    if channel == "email":
        if _is_personal_email(v):
            return ContactRecord(
                channel=channel,
                value=v,
                institutional=False,
                source=source,
                rejected_reason="personal_email_not_allowed",
                notes="Apenas e-mails institucionais publicamente divulgados.",
            )
        return ContactRecord(channel=channel, value=v, institutional=True, source=source)

    if channel == "phone":
        digits = re.sub(r"\D", "", v)
        if not officially_published:
            return ContactRecord(
                channel=channel,
                value=v,
                institutional=False,
                source=source,
                rejected_reason="phone_not_officially_published",
                notes="Telefone só se publicado como canal institucional.",
            )
        if len(digits) < 10:
            return ContactRecord(
                channel=channel,
                value=v,
                institutional=False,
                source=source,
                rejected_reason="invalid_phone",
            )
        return ContactRecord(channel=channel, value=v, institutional=True, source=source)

    if channel == "whatsapp":
        if not officially_published:
            return ContactRecord(
                channel=channel,
                value=v,
                institutional=False,
                source=source,
                rejected_reason="whatsapp_not_official_channel",
                notes="WhatsApp somente se número for canal institucional oficial.",
            )
        return ContactRecord(channel=channel, value=v, institutional=True, source=source)

    if channel in {"form", "sector", "gabinete"}:
        return ContactRecord(
            channel=channel,
            value=v,
            institutional=True,
            source=source,
            notes="Canal institucional declarado." if channel != "gabinete" else "Gabinete somente se canal institucional apropriado.",
        )

    return ContactRecord(
        channel=channel,
        value=v,
        institutional=False,
        source=source,
        rejected_reason="unknown_channel",
    )


def validate_contacts(contacts: list[dict[str, Any]]) -> ContactValidation:
    result = ContactValidation()
    for c in contacts:
        rec = validate_contact(
            channel=str(c.get("channel") or "email"),
            value=str(c.get("value") or ""),
            source=c.get("source"),
            officially_published=bool(c.get("officially_published", False)),
        )
        if rec.institutional and not rec.rejected_reason:
            result.accepted.append(rec)
        else:
            result.rejected.append(rec)
    return result


def default_institutional_research_contact(uf: str | None, municipio: str | None) -> ContactRecord:
    """Placeholder research action — not a personal contact."""
    label = municipio or "município"
    u = (uf or "SC").upper()
    return ContactRecord(
        channel="sector",
        value=f"Pesquisar e-mail institucional do setor de licitações/obras de {label}/{u} em portal oficial",
        institutional=True,
        source="research_action",
        notes="Justificativa de pesquisa adicional — sem contato pessoal.",
    )
