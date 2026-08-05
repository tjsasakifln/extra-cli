"""Legal regime classification for public contracts.

Regime of Lei 14.133/2021 must be proven by structured field or official
document excerpt — NOT by signature year or PNCP publication alone.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial.reajuste_14133 import (
    REGIME_8666,
    REGIME_10520,
    REGIME_14133,
    REGIME_CONFLICT,
    REGIME_RDC,
    REGIME_UNKNOWN,
)

RULE_VERSION = "legal-regime-v1"

_14133_PATTERNS = (
    r"lei\s*n?[ºo°.]?\s*14[\./]?133(?:/2021)?",
    r"lei\s*14[\./]?133\s*/?\s*2021",
    r"nova\s+lei\s+de\s+licita",
    r"lei\s+geral\s+de\s+licita[cç][oõ]es\s+e\s+contratos",
    r"regido\s+pela\s+lei\s*14",
)

_8666_PATTERNS = (
    r"lei\s*n?[ºo°.]?\s*8[\./]?666(?:/93|/1993)?",
    r"lei\s*8[\./]?666",
)

_10520_PATTERNS = (
    r"lei\s*n?[ºo°.]?\s*10[\./]?520(?:/2002)?",
    r"preg[aã]o\s+eletr[oô]nico\s+regido\s+pela\s+lei\s*10",
)

_RDC_PATTERNS = (
    r"\brdc\b",
    r"regime\s+diferenciado\s+de\s+contrata",
    r"lei\s*n?[ºo°.]?\s*12[\./]?462",
)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


@dataclass
class RegimeResult:
    regime: str
    confidence: float
    proven: bool
    evidence_method: str
    excerpts: list[str] = field(default_factory=list)
    source_fields: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    rule_version: str = RULE_VERSION
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_legal_regime(
    *,
    structured_regime: str | None = None,
    document_texts: list[str] | None = None,
    objeto: str | None = None,
    signature_year: int | None = None,
    published_on_pncp: bool = False,
) -> RegimeResult:
    """Classify legal regime with fail-closed proof rules.

    Structured field or explicit document citation is required for
    ``proven=True`` under Lei 14.133. Year/PNCP alone → UNKNOWN.
    """
    # 1) Structured field
    raw = (structured_regime or "").strip().upper()
    if raw:
        if "14133" in raw.replace(".", "").replace("/", "") or "14.133" in (structured_regime or ""):
            return RegimeResult(
                regime=REGIME_14133,
                confidence=0.95,
                proven=True,
                evidence_method="structured_field",
                source_fields=["structured_regime"],
                excerpts=[structured_regime or ""],
                reason_codes=["structured_14133"],
            )
        if "8666" in raw.replace(".", "") or "8.666" in (structured_regime or ""):
            return RegimeResult(
                regime=REGIME_8666,
                confidence=0.95,
                proven=True,
                evidence_method="structured_field",
                source_fields=["structured_regime"],
                excerpts=[structured_regime or ""],
                reason_codes=["structured_8666"],
            )
        if "10520" in raw.replace(".", "") or "10.520" in (structured_regime or ""):
            return RegimeResult(
                regime=REGIME_10520,
                confidence=0.9,
                proven=True,
                evidence_method="structured_field",
                source_fields=["structured_regime"],
                excerpts=[structured_regime or ""],
                reason_codes=["structured_10520"],
            )
        if "RDC" in raw:
            return RegimeResult(
                regime=REGIME_RDC,
                confidence=0.9,
                proven=True,
                evidence_method="structured_field",
                source_fields=["structured_regime"],
                excerpts=[structured_regime or ""],
                reason_codes=["structured_rdc"],
            )

    # 2) Document / object text citations
    blobs = list(document_texts or [])
    if objeto:
        blobs.append(objeto)
    joined = _norm("\n".join(blobs))

    def _search(patterns: tuple[str, ...]) -> list[str]:
        found: list[str] = []
        for pat in patterns:
            m = re.search(pat, joined, re.I)
            if m:
                start = max(0, m.start() - 40)
                end = min(len(joined), m.end() + 40)
                found.append(joined[start:end].strip())
        return found

    hits_14133 = _search(_14133_PATTERNS)
    hits_8666 = _search(_8666_PATTERNS)
    hits_10520 = _search(_10520_PATTERNS)
    hits_rdc = _search(_RDC_PATTERNS)

    # Contradictory explicit citations → LEGAL_REGIME_CONFLICT (blocks outreach)
    older = bool(hits_8666 or hits_rdc or hits_10520)
    if hits_14133 and older and document_texts:
        return RegimeResult(
            regime=REGIME_CONFLICT,
            confidence=0.5,
            proven=False,
            evidence_method="document_excerpt_conflict",
            excerpts=(hits_14133 + hits_8666 + hits_rdc + hits_10520)[:5],
            source_fields=["document_texts"],
            reason_codes=["legal_regime_conflict"],
            notes=(
                "Referências contraditórias a regimes distintos no acervo documental — "
                "impedir abordagem até revisão humana."
            ),
        )

    # Prefer explicit older regimes when present (exclusion)
    if hits_8666 and not hits_14133:
        return RegimeResult(
            regime=REGIME_8666,
            confidence=0.85,
            proven=True,
            evidence_method="document_excerpt",
            excerpts=hits_8666[:3],
            source_fields=["document_texts" if document_texts else "objeto"],
            reason_codes=["document_cites_8666"],
        )
    if hits_rdc and not hits_14133:
        return RegimeResult(
            regime=REGIME_RDC,
            confidence=0.8,
            proven=True,
            evidence_method="document_excerpt",
            excerpts=hits_rdc[:3],
            source_fields=["document_texts" if document_texts else "objeto"],
            reason_codes=["document_cites_rdc"],
        )
    if hits_10520 and not hits_14133:
        return RegimeResult(
            regime=REGIME_10520,
            confidence=0.75,
            proven=True,
            evidence_method="document_excerpt",
            excerpts=hits_10520[:3],
            source_fields=["document_texts" if document_texts else "objeto"],
            reason_codes=["document_cites_10520"],
        )
    if hits_14133:
        # Only proven if from document_texts (not mere object blurb without doc)
        from_docs = bool(document_texts)
        return RegimeResult(
            regime=REGIME_14133,
            confidence=0.9 if from_docs else 0.55,
            proven=from_docs,
            evidence_method="document_excerpt" if from_docs else "object_text_unverified",
            excerpts=hits_14133[:3],
            source_fields=["document_texts"] if from_docs else ["objeto"],
            reason_codes=["document_cites_14133" if from_docs else "object_mentions_14133_unproven"],
            notes=(
                ""
                if from_docs
                else "Menção no objeto sem documento oficial — não comprova regime para HOT_VERIFIED."
            ),
        )

    # 3) Year / PNCP alone are NEVER proof
    notes = []
    if signature_year is not None and signature_year >= 2021:
        notes.append(
            f"Assinatura em {signature_year} não comprova regime da Lei 14.133/2021."
        )
    if published_on_pncp:
        notes.append("Publicação no PNCP não comprova, isoladamente, o regime jurídico.")

    return RegimeResult(
        regime=REGIME_UNKNOWN,
        confidence=0.0,
        proven=False,
        evidence_method="insufficient",
        reason_codes=["regime_not_proven"],
        notes=" ".join(notes) or "Regime jurídico não comprovado por campo estruturado nem documento.",
    )
