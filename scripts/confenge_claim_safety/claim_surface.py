"""Claim surface extraction.

The published copy interpolates raw evidence (contract ``object``, ``agency``,
UF, values, dates) into the ``why_now`` template. A naive regex over the
rendered text therefore matches vigência vocabulary that lives *inside the
quoted evidence* — "execução de obras de EMPREENDIMENTOS HABITACIONAIS" is a
citation of the contract's object, not an assertion that the contract is
running. Measured false-positive rate of that naive detector: 43/43.

So we first remove the interpolated evidence spans, and only then evaluate the
remaining assertion surface. Evidence values are truncated by the generator at
different offsets (``why_now`` cuts ``object`` at 140 chars, ``fact_to_mention``
at another point), so spans are matched by longest common prefix, never by exact
substring equality.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

CLAIM_NONE = "NONE"
CLAIM_PRESENT = "PRESENT"
CLAIM_PAST = "PAST"

CLAIM_POLARITIES = (CLAIM_NONE, CLAIM_PRESENT, CLAIM_PAST)

# Shortest evidence prefix worth stripping. Below this the span stops being
# identifiable evidence and starts being ordinary language.
MIN_EVIDENCE_SPAN = 16

# Fields of the lead that carry *assertions*. ``fact_to_mention`` is excluded on
# purpose: it is a verbatim evidence quote, and treating it as an assertion is
# exactly the false positive this module exists to avoid.
ASSERTION_FIELDS: tuple[tuple[str, ...], ...] = (
    ("messaging_context", "why_now"),
    ("moment", "summary"),
)

# Present-tense assertions of contractual currency. The optional qualifier
# prefix ("recente ou ativo", "atualmente vigente") is part of the match so the
# neutralizer removes the whole clause instead of leaving a dangling conjunction.
PRESENT_QUALIFIER = r"(?:recente\s+ou\s+|atualmente\s+|ainda\s+|segue\s+|permanece\s+)?"
PRESENT_CORE = (
    r"(?:vig[êe]ncia\s+ativ[oa]|ativ[oa]s?|vigentes?|em\s+vigor|em\s+vig[êe]ncia"
    r"|em\s+execu[çc][ãa]o|em\s+andamento|em\s+curso)"
)
PRESENT_CLAIM_PATTERN = re.compile(
    rf"(?:,\s*|\s+)?\b{PRESENT_QUALIFIER}{PRESENT_CORE}\b",
    re.IGNORECASE,
)

# Past frame must be explicitly anchored — a bare "encerrado" with no date is not
# a dated historical frame, but it is still unambiguously not a present claim.
PAST_CLAIM_PATTERN = re.compile(
    r"\b(?:vig[êe]ncia\s+encerrada|encerrad[oa]s?|conclu[íi]d[oa]s?|finalizad[oa]s?"
    r"|rescindid[oa]s?|cancelad[oa]s?|expirad[oa]s?)\b",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    """Casefold and drop diacritics so token matching is accent-insensitive."""
    normalized = unicodedata.normalize("NFD", str(text or ""))
    stripped = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return stripped.casefold()


def _common_prefix_length(text: str, start: int, value: str) -> int:
    limit = min(len(value), len(text) - start)
    index = 0
    while index < limit and text[start + index] == value[index]:
        index += 1
    return index


def evidence_values(lead: dict[str, Any]) -> list[str]:
    """Every raw value the generator may interpolate into the copy."""
    values: list[str] = []
    company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
    for key in ("razao_social", "nome_fantasia", "municipio"):
        value = str(company.get(key) or "").strip()
        if value:
            values.append(value)
    for contract in lead.get("contracts") or []:
        if not isinstance(contract, dict):
            continue
        for key in ("object", "objeto", "objeto_contrato", "agency", "orgao", "orgao_nome"):
            value = str(contract.get(key) or "").strip()
            if value:
                values.append(value)
    messaging = lead.get("messaging_context") if isinstance(lead.get("messaging_context"), dict) else {}
    fact = str(messaging.get("fact_to_mention") or "").strip()
    if fact:
        # The fact line is itself a concatenation of evidence fragments.
        values.extend(part.strip() for part in re.split(r";\s*", fact) if part.strip())
    # Longest first: strip the widest evidence span before its own substrings.
    return sorted({value for value in values if value}, key=len, reverse=True)


def strip_evidence_spans(text: str, values: list[str]) -> str:
    """Remove interpolated evidence from ``text``, leaving the assertion surface.

    Every position that starts a known evidence head yields a candidate span, and
    the widest non-overlapping spans win. Both properties are load-bearing:

    * several contracts in one payload share a boilerplate opening ("Contratação
      de empresa especializada …"), so the *longest* extension at a position must
      be taken, not the first candidate's;
    * a left-to-right greedy pass would consume a short span (the ``fact_to_mention``
      fragment starting at "objeto: ") and block the 140-character span starting
      eight characters later, leaving the tail of the quoted object — including
      its "em execução" — standing in the assertion surface as a false present
      claim. That defect produced five false ``UNSAFE_PRESENT_CLAIM`` leads in the
      first production dry-run.
    """
    source = str(text or "")
    by_head: dict[str, list[str]] = {}
    for value in values:
        if len(value) >= MIN_EVIDENCE_SPAN:
            by_head.setdefault(value[:MIN_EVIDENCE_SPAN], []).append(value)

    spans: list[tuple[int, int]] = []
    for index in range(len(source)):
        candidates = by_head.get(source[index : index + MIN_EVIDENCE_SPAN])
        if not candidates:
            continue
        best = max(_common_prefix_length(source, index, value) for value in candidates)
        if best >= MIN_EVIDENCE_SPAN:
            spans.append((index, index + best))

    selected: list[tuple[int, int]] = []
    for start, end in sorted(spans, key=lambda span: (span[0] - span[1], span[0])):
        if all(end <= other_start or start >= other_end for other_start, other_end in selected):
            selected.append((start, end))
    kept: list[str] = []
    cursor = 0
    for start, end in sorted(selected):
        kept.append(source[cursor:start])
        kept.append(" ")
        cursor = end
    kept.append(source[cursor:])
    surface = "".join(kept)
    # Labels the generator emits around evidence carry no assertion of their own.
    surface = re.sub(r"\b(?:objeto|[óo]rg[ãa]o|UF|R\$)\s*:?", " ", surface, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", surface).strip()


def assertion_texts(lead: dict[str, Any]) -> list[str]:
    """Raw assertion-bearing copy fields present on the lead."""
    texts: list[str] = []
    for path in ASSERTION_FIELDS:
        node: Any = lead
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, str) and node.strip():
            texts.append(node)
    return texts


def claim_surface(lead: dict[str, Any]) -> str:
    """Assertion surface of a lead: every claim-bearing field, evidence removed."""
    values = evidence_values(lead)
    return " ".join(strip_evidence_spans(text, values) for text in assertion_texts(lead)).strip()


def detect_temporal_claim(surface: str) -> str:
    """Classify an already-stripped assertion surface as NONE / PRESENT / PAST.

    Present beats past: a copy asserting both is a present claim that must be
    proven, never a historical frame that happens to mention an end date.
    """
    folded = _fold(surface)
    if PRESENT_CLAIM_PATTERN.search(folded):
        return CLAIM_PRESENT
    if PAST_CLAIM_PATTERN.search(folded):
        return CLAIM_PAST
    return CLAIM_NONE


def lead_claim(lead: dict[str, Any]) -> tuple[str, str]:
    """``(claim_polarity, claim_surface)`` for a published lead."""
    surface = claim_surface(lead)
    return detect_temporal_claim(surface), surface


__all__ = [
    "ASSERTION_FIELDS",
    "CLAIM_NONE",
    "CLAIM_PAST",
    "CLAIM_POLARITIES",
    "CLAIM_PRESENT",
    "MIN_EVIDENCE_SPAN",
    "PAST_CLAIM_PATTERN",
    "PRESENT_CLAIM_PATTERN",
    "PRESENT_CORE",
    "PRESENT_QUALIFIER",
    "assertion_texts",
    "claim_surface",
    "detect_temporal_claim",
    "evidence_values",
    "lead_claim",
    "strip_evidence_spans",
]
