"""Specialized parsers for signature blocks and structured rep forms.

Extracts commercial identity; CPF may be used internally for entity resolution
but is never required for contact and must not be exported.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_EMAIL_RE = re.compile(
    r"(?i)\b([a-z0-9][a-z0-9._%+\-]{0,63}@[a-z0-9][a-z0-9.\-]{1,63}\.[a-z]{2,24})\b"
)
_PHONE_RE = re.compile(
    r"(?i)(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)(?:9\s?)?\d{4,5}[-\s]?\d{4}"
)
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_NAME_LINE = re.compile(
    r"^(?:nome|representante(?:\s+legal)?|preposto|respons[aá]vel(?:\s+t[eé]cnico)?)\s*[:\-]\s*(.+)$",
    re.I,
)
_ROLE_LINE = re.compile(
    r"^(?:cargo|fun[cç][aã]o|qualidade)\s*[:\-]\s*(.+)$",
    re.I,
)
_EMAIL_LINE = re.compile(r"^(?:e-?mail|email|correio)\s*[:\-]\s*(.+)$", re.I)
_PHONE_LINE = re.compile(r"^(?:telefone|fone|celular|whatsapp|tel\.?)\s*[:\-]\s*(.+)$", re.I)
_CLOSING = re.compile(
    r"(?i)\b(atenciosamente|cordialmente|respeitosamente|sem mais)\b"
)
_ROLE_HINT = re.compile(
    r"(?i)\b(diretor|s[oó]cio|gerente|coordenador|engenheiro|preposto|"
    r"representante legal|procurador|respons[aá]vel t[eé]cnico|comercial|"
    r"financeiro|administrativo|licita[cç][oõ]es|contratos)\b"
)


@dataclass
class SignatureHit:
    person_name: str | None = None
    role_observed: str | None = None
    email: str | None = None
    phone: str | None = None
    company_name: str | None = None
    cpf_internal: str | None = None  # never export
    evidence_text: str = ""
    page: int | None = None
    kind: str = "signature_block"  # signature_block | structured_form
    extra: dict[str, Any] = field(default_factory=dict)

    def evidence_hash(self) -> str:
        return hashlib.sha256(self.evidence_text.encode("utf-8")).hexdigest()

    def to_public_dict(self) -> dict[str, Any]:
        """Export-safe dict — no CPF."""
        return {
            "person_name": self.person_name,
            "role_observed": self.role_observed,
            "email": self.email,
            "phone": self.phone,
            "company_name": self.company_name,
            "evidence_text_hash": self.evidence_hash(),
            "page": self.page,
            "kind": self.kind,
        }


def _clean_name(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip(" \t-:;,.|")
    v = _CPF_RE.sub("", v).strip()
    if len(v) < 3 or len(v) > 80:
        return None
    if "@" in v or re.search(r"\d{5,}", v):
        return None
    return v


def parse_structured_forms(text: str, *, page: int | None = None) -> list[SignatureHit]:
    """Parse labeled forms: Representante legal / Preposto / etc."""
    hits: list[SignatureHit] = []
    lines = [ln.strip() for ln in (text or "").splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        header = re.match(
            r"(?i)^(representante legal|preposto(?: da contratada)?|respons[aá]vel t[eé]cnico|"
            r"dados do licitante|dados da empresa)\s*:?\s*$",
            line,
        )
        if not header and not _NAME_LINE.match(line):
            i += 1
            continue
        block_lines = [line]
        person = role = email = phone = cpf = None
        # scan next 12 lines for fields
        for j in range(i, min(i + 12, len(lines))):
            ln = lines[j]
            block_lines.append(ln)
            m = _NAME_LINE.match(ln)
            if m:
                person = _clean_name(m.group(1))
            m = _ROLE_LINE.match(ln)
            if m:
                role = m.group(1).strip()[:80]
            m = _EMAIL_LINE.match(ln)
            if m:
                em = _EMAIL_RE.search(m.group(1))
                email = em.group(1) if em else None
            m = _PHONE_LINE.match(ln)
            if m:
                ph = _PHONE_RE.search(m.group(1))
                phone = ph.group(0) if ph else m.group(1).strip()[:30]
            cm = _CPF_RE.search(ln)
            if cm and re.search(r"(?i)cpf", ln):
                cpf = re.sub(r"\D", "", cm.group(0))
            # also bare email/phone on line
            if not email:
                em = _EMAIL_RE.search(ln)
                if em:
                    email = em.group(1)
            if not phone:
                ph = _PHONE_RE.search(ln)
                if ph:
                    phone = ph.group(0)
        if person or email or phone:
            if not role and header:
                role = header.group(1)
            hits.append(
                SignatureHit(
                    person_name=person,
                    role_observed=role,
                    email=email.lower() if email else None,
                    phone=phone,
                    cpf_internal=cpf,
                    evidence_text="\n".join(block_lines)[:2000],
                    page=page,
                    kind="structured_form",
                )
            )
            i += 6
            continue
        i += 1
    return hits


def parse_closing_signature_blocks(text: str, *, page: int | None = None) -> list[SignatureHit]:
    """Parse 'Atenciosamente,' style blocks."""
    hits: list[SignatureHit] = []
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    for i, line in enumerate(lines):
        if not _CLOSING.search(line):
            continue
        window = lines[i : i + 8]
        person = role = email = phone = company = None
        for ln in window[1:]:
            s = ln.strip()
            if not s:
                continue
            em = _EMAIL_RE.search(s)
            if em and not email:
                email = em.group(1).lower()
                continue
            ph = _PHONE_RE.search(s)
            if ph and not phone:
                phone = ph.group(0)
                continue
            if _ROLE_HINT.search(s) and not role and "@" not in s:
                role = s[:80]
                continue
            if re.search(r"(?i)\b(ltda|s\.?a\.?|eireli|me|epp)\b", s) and not company:
                company = s[:120]
                continue
            if not person and not re.search(r"\d{3,}", s) and 3 <= len(s) <= 60:
                person = _clean_name(s)
        if person or email or phone:
            hits.append(
                SignatureHit(
                    person_name=person,
                    role_observed=role,
                    email=email,
                    phone=phone,
                    company_name=company,
                    evidence_text="\n".join(window)[:2000],
                    page=page,
                    kind="signature_block",
                )
            )
    return hits


def extract_signature_intelligence(text: str, *, page: int | None = None) -> list[SignatureHit]:
    """Run all signature/form parsers; de-dupe by email+name."""
    hits = parse_structured_forms(text, page=page) + parse_closing_signature_blocks(text, page=page)
    seen: set[str] = set()
    out: list[SignatureHit] = []
    for h in hits:
        key = f"{(h.email or '').lower()}|{(h.person_name or '').lower()}|{h.kind}"
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out
