"""Brazilian person-name folding for corporate email patterns.

Particles, compound surnames, accents, titles and common abbreviations are
normalized. This never invents a mailbox.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from scripts.decision_unit_intelligence.email_resolution import LEGAL_FORM_TOKENS
from scripts.decision_unit_intelligence.models import normalize_name

PARTICLES = frozenset({"da", "de", "do", "das", "dos", "e", "di", "du", "del", "della", "van", "von"})
TITLES = frozenset({"dr", "dra", "sr", "sra", "srta", "eng", "engenharia", "prof", "profa", "pe", "frei"})
# Nickname → canonical first name. Only these aliases may be recognized when observed.
OBSERVED_ALIAS_MAP = {
    "ze": "jose",
    "zeh": "jose",
    "zecao": "jose",
    "bia": "beatriz",
    "nanda": "fernanda",
    "nando": "fernando",
    "beto": "roberto",
    "gui": "guilherme",
    "chico": "francisco",
    "toninho": "antonio",
    "tonho": "antonio",
    "duda": "eduarda",
    "gabi": "gabriel",
    "pati": "patricia",
    "paty": "patricia",
}
CANONICAL_TO_ALIASES: dict[str, tuple[str, ...]] = {}
for _alias, _canon in OBSERVED_ALIAS_MAP.items():
    CANONICAL_TO_ALIASES.setdefault(_canon, ())
    CANONICAL_TO_ALIASES[_canon] = tuple(dict.fromkeys([*CANONICAL_TO_ALIASES[_canon], _alias]))


def fold_token(value: str) -> str:
    stripped = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in stripped if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def _raw_parts(person_name: str | None) -> list[str]:
    raw = normalize_name(person_name) or ""
    folded = unicodedata.normalize("NFKD", raw)
    folded = "".join(char for char in folded if not unicodedata.combining(char)).lower()
    folded = re.sub(r"[^a-z\s\-'.]", " ", folded)
    return [part for part in re.split(r"[\s]+", folded) if part]


@dataclass(frozen=True)
class ParsedPersonName:
    original: str
    first: str
    last: str
    tokens: tuple[str, ...]
    particles: tuple[str, ...]
    compound_last: str
    first_initial: str
    last_initial: str
    abbreviations: tuple[str, ...]
    known_aliases: tuple[str, ...]

    def usable_for_pattern(self, pattern_id: str) -> bool:
        if not self.first:
            return False
        if pattern_id == "first":
            return len(self.first) >= 3
        if pattern_id in {"first.last", "firstlast", "last.first", "first.compoundlast"}:
            return bool(self.last) and len(self.last) >= 2
        if pattern_id == "first_initial+last":
            return bool(self.first_initial and self.last)
        if pattern_id == "first+last_initial":
            return bool(self.first and self.last_initial)
        if pattern_id == "alias":
            return bool(self.known_aliases and self.last)
        return False


def parse_person_name(person_name: str | None) -> ParsedPersonName | None:
    original = normalize_name(person_name)
    if not original:
        return None
    parts = _raw_parts(original)
    particles: list[str] = []
    abbreviations: list[str] = []
    tokens: list[str] = []
    for part in parts:
        clean = part.strip(".-'")
        folded = fold_token(clean)
        if not folded or folded in TITLES or folded in LEGAL_FORM_TOKENS:
            continue
        if folded in PARTICLES:
            particles.append(folded)
            continue
        if len(folded) == 1:
            abbreviations.append(folded)
            tokens.append(folded)
            continue
        tokens.append(folded)
    if not tokens:
        return None
    first = tokens[0]
    last = tokens[-1] if len(tokens) >= 2 else ""
    compound = "".join(tokens[-2:]) if len(tokens) >= 3 else last
    aliases = CANONICAL_TO_ALIASES.get(first, ())
    return ParsedPersonName(
        original=original,
        first=first,
        last=last,
        tokens=tuple(tokens),
        particles=tuple(particles),
        compound_last=compound,
        first_initial=first[:1] if first else "",
        last_initial=last[:1] if last else "",
        abbreviations=tuple(abbreviations),
        known_aliases=aliases,
    )


def local_part(email: str) -> str:
    return email.split("@", 1)[0].lower() if "@" in email else email.lower()


def detect_supported_pattern(email: str, person_name: str | None) -> tuple[str, str] | None:
    """Return (pattern_id, separator) when the local-part matches a supported shape."""
    parsed = parse_person_name(person_name)
    if parsed is None:
        return None
    local = local_part(email)
    if not local or not parsed.first:
        return None
    first, last = parsed.first, parsed.last
    candidates: list[tuple[str, str, str]] = []
    if last:
        candidates.extend(
            [
                ("first.last", f"{first}.{last}", "."),
                ("firstlast", f"{first}{last}", ""),
                ("first_initial+last", f"{parsed.first_initial}{last}", ""),
                ("first_initial+last", f"{parsed.first_initial}.{last}", "."),
                ("first+last_initial", f"{first}{parsed.last_initial}", ""),
                ("last.first", f"{last}.{first}", "."),
                ("last.first", f"{last}{first}", ""),
            ]
        )
        if parsed.compound_last and parsed.compound_last != last:
            candidates.extend(
                [
                    ("first.compoundlast", f"{first}.{parsed.compound_last}", "."),
                    ("first.compoundlast", f"{first}{parsed.compound_last}", ""),
                ]
            )
        for alias in parsed.known_aliases:
            candidates.extend(
                [
                    ("alias", f"{alias}.{last}", "."),
                    ("alias", f"{alias}{last}", ""),
                ]
            )
    candidates.append(("first", first, ""))
    for pattern_id, built, separator in candidates:
        if built == local:
            return pattern_id, separator
    return None


def render_pattern_email(
    *,
    pattern_id: str,
    parsed: ParsedPersonName,
    domain: str,
    separator: str = "",
    alias_token: str | None = None,
) -> str | None:
    if not parsed.usable_for_pattern(pattern_id):
        return None
    first, last = parsed.first, parsed.last
    if pattern_id == "first.last":
        local = f"{first}.{last}"
    elif pattern_id == "firstlast":
        local = f"{first}{last}"
    elif pattern_id == "first_initial+last":
        local = f"{parsed.first_initial}{separator}{last}"
    elif pattern_id == "first+last_initial":
        local = f"{first}{parsed.last_initial}"
    elif pattern_id == "last.first":
        local = f"{last}{separator or '.'}{first}"
    elif pattern_id == "first":
        local = first
    elif pattern_id == "first.compoundlast":
        local = f"{first}.{parsed.compound_last}"
    elif pattern_id == "alias":
        token = alias_token or (parsed.known_aliases[0] if parsed.known_aliases else None)
        if not token or token not in parsed.known_aliases:
            return None
        local = f"{token}{separator or '.'}{last}"
    else:
        return None
    if not local or local.endswith(".") or local.startswith("."):
        return None
    return f"{local}@{domain}"
