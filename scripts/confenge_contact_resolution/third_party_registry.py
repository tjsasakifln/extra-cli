"""Growing registry of known third-party contact holders (accounting, legal, …).

Fed by ownership resolution outcomes; blocks or penalizes later matches.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.email_policy import domain_of
from scripts.confenge_contact_resolution.ownership import RegistryHit, detect_third_party_type
from scripts.confenge_contact_resolution.phone_policy import normalize_br_e164


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_domain(d: str | None) -> str | None:
    if not d:
        return None
    x = d.strip().lower().removeprefix("www.")
    return x or None


def _norm_email(e: str | None) -> str | None:
    if not e or "@" not in e:
        return None
    return e.strip().lower()


def _norm_phone(p: str | None) -> str | None:
    if not p:
        return None
    return normalize_br_e164(p) or re.sub(r"\D", "", p) or None


@dataclass
class ThirdPartyEntry:
    domain: str | None = None
    phone: str | None = None
    email: str | None = None
    entity_name: str | None = None
    third_party_type: str = "OTHER"
    evidence: list[str] = field(default_factory=list)
    associated_cnpjs: list[str] = field(default_factory=list)
    confidence: float = 0.7
    first_seen_at: str | None = None
    last_seen_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ThirdPartyRegistry:
    """Keyed by domain / phone / email for O(1) lookups."""

    def __init__(self) -> None:
        self.by_domain: dict[str, ThirdPartyEntry] = {}
        self.by_phone: dict[str, ThirdPartyEntry] = {}
        self.by_email: dict[str, ThirdPartyEntry] = {}
        self.entries: list[ThirdPartyEntry] = []

    def lookup(
        self,
        *,
        domain: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> RegistryHit | None:
        e = _norm_email(email)
        d = _norm_domain(domain) or (domain_of(e) if e else None)
        p = _norm_phone(phone)

        hit: ThirdPartyEntry | None = None
        if e and e in self.by_email:
            hit = self.by_email[e]
        elif d and d in self.by_domain:
            hit = self.by_domain[d]
        elif p and p in self.by_phone:
            hit = self.by_phone[p]

        if hit is None:
            # Lexical domain classification even without prior entry
            tp, evidence = detect_third_party_type(d, e)
            if tp and d:
                return RegistryHit(
                    entity_name=d,
                    third_party_type=tp,
                    confidence=0.75,
                    evidence=evidence or [f"lex_domain:{d}"],
                )
            return None

        return RegistryHit(
            entity_name=hit.entity_name,
            third_party_type=hit.third_party_type,
            confidence=hit.confidence,
            evidence=list(hit.evidence or []) + [f"registry_entry:{hit.domain or hit.email or hit.phone}"],
        )

    def register(
        self,
        *,
        domain: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        entity_name: str | None = None,
        third_party_type: str = "OTHER",
        evidence: list[str] | None = None,
        cnpj14: str | None = None,
        confidence: float = 0.7,
    ) -> ThirdPartyEntry:
        d = _norm_domain(domain) or (domain_of(email) if email else None)
        e = _norm_email(email)
        p = _norm_phone(phone)
        now = _now()

        existing: ThirdPartyEntry | None = None
        if d and d in self.by_domain:
            existing = self.by_domain[d]
        elif e and e in self.by_email:
            existing = self.by_email[e]
        elif p and p in self.by_phone:
            existing = self.by_phone[p]

        if existing:
            if cnpj14 and cnpj14 not in existing.associated_cnpjs:
                existing.associated_cnpjs.append(cnpj14)
            if evidence:
                for ev in evidence:
                    if ev not in existing.evidence:
                        existing.evidence.append(ev)
            existing.last_seen_at = now
            existing.confidence = max(existing.confidence, confidence)
            if entity_name and not existing.entity_name:
                existing.entity_name = entity_name
            if third_party_type and third_party_type != "OTHER":
                existing.third_party_type = third_party_type
            return existing

        entry = ThirdPartyEntry(
            domain=d,
            phone=p,
            email=e,
            entity_name=entity_name or d,
            third_party_type=third_party_type,
            evidence=list(evidence or []),
            associated_cnpjs=[cnpj14] if cnpj14 else [],
            confidence=confidence,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.entries.append(entry)
        if d:
            self.by_domain[d] = entry
        if e:
            self.by_email[e] = entry
        if p:
            self.by_phone[p] = entry
        return entry

    def register_from_rejection(
        self,
        *,
        email: str | None,
        phone: str | None,
        third_party_type: str | None,
        reason: str | None,
        cnpj14: str | None,
        entity_name: str | None = None,
    ) -> None:
        if not third_party_type:
            return
        self.register(
            domain=domain_of(email) if email else None,
            email=email,
            phone=phone,
            entity_name=entity_name,
            third_party_type=third_party_type,
            evidence=[reason] if reason else [],
            cnpj14=cnpj14,
            confidence=0.8,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "confenge-third-party-registry-v1",
            "entries": [e.as_dict() for e in self.entries],
            "count": len(self.entries),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThirdPartyRegistry:
        reg = cls()
        for raw in data.get("entries") or []:
            if not isinstance(raw, dict):
                continue
            reg.register(
                domain=raw.get("domain"),
                phone=raw.get("phone"),
                email=raw.get("email"),
                entity_name=raw.get("entity_name"),
                third_party_type=raw.get("third_party_type") or "OTHER",
                evidence=list(raw.get("evidence") or []),
                cnpj14=(raw.get("associated_cnpjs") or [None])[0],
                confidence=float(raw.get("confidence") or 0.7),
            )
            # re-add remaining cnpjs
            entry = None
            d = _norm_domain(raw.get("domain"))
            if d and d in reg.by_domain:
                entry = reg.by_domain[d]
            if entry:
                for c in raw.get("associated_cnpjs") or []:
                    if c and c not in entry.associated_cnpjs:
                        entry.associated_cnpjs.append(c)
                entry.first_seen_at = raw.get("first_seen_at") or entry.first_seen_at
                entry.last_seen_at = raw.get("last_seen_at") or entry.last_seen_at
        return reg

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> ThirdPartyRegistry:
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return cls()

    # Seed a few well-known generic patterns for offline runs
    def seed_defaults(self) -> None:
        seeds = [
            ("contabilidade", "ACCOUNTING"),
            ("contador", "ACCOUNTING"),
            ("escritoriocontabil", "ACCOUNTING"),
            ("advocacia", "LEGAL"),
            ("advogados", "LEGAL"),
            ("despachante", "OTHER"),
            ("consultoria", "CONSULTING"),
        ]
        for token, tp in seeds:
            # not registered as full domains — lexical path handles these
            _ = (token, tp)
