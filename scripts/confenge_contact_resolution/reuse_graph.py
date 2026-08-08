"""Reverse contact reuse graph: email|phone|domain → associated CNPJs.

Detects shared external contacts (accounting offices, virtual addresses, etc.)
without a crude fixed threshold alone — callers combine with ownership signals.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.email_policy import domain_of
from scripts.confenge_contact_resolution.ownership import ReuseSignal, cnpj_root
from scripts.confenge_contact_resolution.phone_policy import normalize_br_e164


def _norm_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.strip().lower()


def _norm_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    e164 = normalize_br_e164(phone)
    if e164:
        return e164
    d = re.sub(r"\D", "", phone)
    return d or None


def _norm_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    d = domain.strip().lower().removeprefix("www.")
    return d or None


@dataclass
class ChannelObservation:
    channel_kind: str  # email | phone | domain
    channel_key: str
    cnpj14: str
    razao_social: str | None = None
    economic_group_id: str | None = None


@dataclass
class ContactReuseGraph:
    """In-memory reverse indexes with optional persistence."""

    email_to_cnpjs: dict[str, set[str]] = field(default_factory=dict)
    phone_to_cnpjs: dict[str, set[str]] = field(default_factory=dict)
    domain_to_cnpjs: dict[str, set[str]] = field(default_factory=dict)
    cnpj_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    # cnpj14 → set of related cnpjs (group / matriz-filial)
    related_cnpjs: dict[str, set[str]] = field(default_factory=dict)

    def register_company(
        self,
        cnpj14: str,
        *,
        razao_social: str | None = None,
        economic_group_id: str | None = None,
        related: set[str] | None = None,
    ) -> None:
        c = re.sub(r"\D", "", cnpj14 or "")[:14]
        if len(c) != 14:
            return
        meta = self.cnpj_meta.setdefault(c, {})
        if razao_social:
            meta["razao_social"] = razao_social
        if economic_group_id:
            meta["economic_group_id"] = economic_group_id
        root = cnpj_root(c)
        meta["cnpj_root"] = root
        if related:
            self.related_cnpjs.setdefault(c, set()).update(related)
            for r in related:
                self.related_cnpjs.setdefault(r, set()).add(c)

    def observe_email(self, email: str | None, cnpj14: str) -> None:
        e = _norm_email(email)
        c = re.sub(r"\D", "", cnpj14 or "")[:14]
        if not e or len(c) != 14:
            return
        self.email_to_cnpjs.setdefault(e, set()).add(c)
        d = domain_of(e)
        if d:
            self.domain_to_cnpjs.setdefault(d, set()).add(c)

    def observe_phone(self, phone: str | None, cnpj14: str) -> None:
        p = _norm_phone(phone)
        c = re.sub(r"\D", "", cnpj14 or "")[:14]
        if not p or len(c) != 14:
            return
        self.phone_to_cnpjs.setdefault(p, set()).add(c)

    def observe_domain(self, domain: str | None, cnpj14: str) -> None:
        d = _norm_domain(domain)
        c = re.sub(r"\D", "", cnpj14 or "")[:14]
        if not d or len(c) != 14:
            return
        self.domain_to_cnpjs.setdefault(d, set()).add(c)

    def observe_candidate(
        self,
        cnpj14: str,
        *,
        email: str | None = None,
        phone: str | None = None,
        domain: str | None = None,
        razao_social: str | None = None,
        economic_group_id: str | None = None,
    ) -> None:
        self.register_company(cnpj14, razao_social=razao_social, economic_group_id=economic_group_id)
        self.observe_email(email, cnpj14)
        self.observe_phone(phone, cnpj14)
        if domain:
            self.observe_domain(domain, cnpj14)
        elif email:
            self.observe_domain(domain_of(email), cnpj14)

    def _partition(
        self,
        target_cnpj: str,
        others: set[str],
    ) -> tuple[list[str], int, int, int]:
        """Return (all_cnpjs, unrelated_count, same_root_count, same_group_count)."""
        target = re.sub(r"\D", "", target_cnpj)[:14]
        all_c = sorted(others | {target} if target else others)
        root = cnpj_root(target)
        group = self.cnpj_meta.get(target, {}).get("economic_group_id")
        related = self.related_cnpjs.get(target, set())

        same_root = 0
        same_group = 0
        unrelated = 0
        for c in others:
            if c == target:
                continue
            c_root = cnpj_root(c)
            c_group = self.cnpj_meta.get(c, {}).get("economic_group_id")
            if c_root and c_root == root:
                same_root += 1
            elif group and c_group and group == c_group:
                same_group += 1
            elif c in related:
                same_group += 1
            else:
                unrelated += 1
        return all_c, unrelated, same_root, same_group

    def signal_for_email(self, email: str | None, target_cnpj: str) -> ReuseSignal | None:
        e = _norm_email(email)
        if not e:
            return None
        cnpjs = self.email_to_cnpjs.get(e, set())
        all_c, unr, same_r, same_g = self._partition(target_cnpj, set(cnpjs))
        return ReuseSignal(
            channel_key=f"email:{e}",
            associated_cnpjs=all_c,
            unrelated_count=unr,
            same_root_count=same_r,
            same_group_count=same_g,
        )

    def signal_for_phone(self, phone: str | None, target_cnpj: str) -> ReuseSignal | None:
        p = _norm_phone(phone)
        if not p:
            return None
        cnpjs = self.phone_to_cnpjs.get(p, set())
        all_c, unr, same_r, same_g = self._partition(target_cnpj, set(cnpjs))
        return ReuseSignal(
            channel_key=f"phone:{p}",
            associated_cnpjs=all_c,
            unrelated_count=unr,
            same_root_count=same_r,
            same_group_count=same_g,
        )

    def signal_for_domain(self, domain: str | None, target_cnpj: str) -> ReuseSignal | None:
        d = _norm_domain(domain)
        if not d:
            return None
        cnpjs = self.domain_to_cnpjs.get(d, set())
        all_c, unr, same_r, same_g = self._partition(target_cnpj, set(cnpjs))
        return ReuseSignal(
            channel_key=f"domain:{d}",
            associated_cnpjs=all_c,
            unrelated_count=unr,
            same_root_count=same_r,
            same_group_count=same_g,
        )

    def best_signal(
        self,
        target_cnpj: str,
        *,
        email: str | None = None,
        phone: str | None = None,
        domain: str | None = None,
    ) -> ReuseSignal | None:
        """Pick the reuse signal with the highest unrelated_count (worst sharing)."""
        signals = [
            self.signal_for_email(email, target_cnpj),
            self.signal_for_phone(phone, target_cnpj),
            self.signal_for_domain(domain or domain_of(email), target_cnpj),
        ]
        present = [s for s in signals if s is not None]
        if not present:
            return None
        return max(present, key=lambda s: (s.unrelated_count, len(s.associated_cnpjs)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "email_to_cnpjs": {k: sorted(v) for k, v in sorted(self.email_to_cnpjs.items())},
            "phone_to_cnpjs": {k: sorted(v) for k, v in sorted(self.phone_to_cnpjs.items())},
            "domain_to_cnpjs": {k: sorted(v) for k, v in sorted(self.domain_to_cnpjs.items())},
            "cnpj_meta": self.cnpj_meta,
            "related_cnpjs": {k: sorted(v) for k, v in sorted(self.related_cnpjs.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContactReuseGraph:
        g = cls()
        for k, v in (data.get("email_to_cnpjs") or {}).items():
            g.email_to_cnpjs[k] = set(v)
        for k, v in (data.get("phone_to_cnpjs") or {}).items():
            g.phone_to_cnpjs[k] = set(v)
        for k, v in (data.get("domain_to_cnpjs") or {}).items():
            g.domain_to_cnpjs[k] = set(v)
        g.cnpj_meta = dict(data.get("cnpj_meta") or {})
        for k, v in (data.get("related_cnpjs") or {}).items():
            g.related_cnpjs[k] = set(v)
        return g

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> ContactReuseGraph:
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return cls()
