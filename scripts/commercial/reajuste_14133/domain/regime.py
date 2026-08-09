"""Legal regime classification for public contracts.

Evidence hierarchy R-A…R-X. Regime of Lei 14.133/2021 must be proven by
structured field or official document excerpt — NEVER by signature year or
PNCP publication alone. Year may only mark transitional investigation context.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from scripts.commercial.reajuste_14133 import (
    EVIDENCE_LEVEL_RA,
    EVIDENCE_LEVEL_RB,
    EVIDENCE_LEVEL_RC,
    EVIDENCE_LEVEL_RD,
    EVIDENCE_LEVEL_RX,
    LEGAL_CONF_CONFLICT,
    LEGAL_CONF_HIGH,
    LEGAL_CONF_MEDIUM,
    LEGAL_CONF_NONE,
    LEGAL_CONF_UNRESOLVED,
    POST_TRANSITION_AMBIGUITY_YEAR,
    REGIME_10520,
    REGIME_14133,
    REGIME_8666,
    REGIME_CONFLICT,
    REGIME_LIKELY_14133,
    REGIME_RDC,
    REGIME_TRANSITIONAL_UNRESOLVED,
    REGIME_UNKNOWN,
    TRANSITION_END_YEAR,
    TRANSITION_START_YEAR,
)

RULE_VERSION = "legal-regime-v2"

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

# Priority documents when regime is unresolved
PRIORITY_REGIME_DOCUMENTS = (
    "edital",
    "aviso_de_licitacao",
    "termo_de_referencia",
    "projeto_basico",
    "contrato",
    "ato_de_autorizacao",
    "parecer_juridico",
    "fundamento_legal_no_processo",
    "numero_e_ano_contratacao_originaria",
)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


def _year_of(value: date | int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1900 <= value <= 2100 else None
    if isinstance(value, date):
        return value.year
    s = str(value).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})", s)
    if m:
        y = int(m.group(1))
        return y if 1900 <= y <= 2100 else None
    return None


def in_transition_or_ambiguity_window(
    *,
    signature_year: int | None,
    origin_process_year: int | None = None,
    origin_edital_year: int | None = None,
) -> bool:
    """True when dual-regime / legacy-process risk is material.

    Dual regime optionality: 2021–2023. Signatures in 2024 may still stem from
    2023 (or earlier) processes. Origin year in the window also qualifies.
    """
    years = [
        y
        for y in (signature_year, origin_process_year, origin_edital_year)
        if y is not None
    ]
    if not years:
        return False
    for y in years:
        if TRANSITION_START_YEAR <= y <= POST_TRANSITION_AMBIGUITY_YEAR:
            return True
    return False


def origin_is_legacy_regime(
    *,
    origin_process_year: int | None = None,
    origin_edital_year: int | None = None,
    origin_document_texts: list[str] | None = None,
) -> bool:
    """True when origin process/edital is legacy (pre-14.133 exclusive or cites 8.666/RDC)."""
    for y in (origin_process_year, origin_edital_year):
        if y is not None and y < TRANSITION_START_YEAR:
            return True
    joined = _norm("\n".join(origin_document_texts or []))
    if not joined:
        return False
    if re.search(_8666_PATTERNS[0], joined, re.I) or re.search(
        _8666_PATTERNS[1], joined, re.I
    ):
        return True
    if re.search(_RDC_PATTERNS[0], joined, re.I) or re.search(
        _RDC_PATTERNS[2], joined, re.I
    ):
        return True
    return False


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
    evidence_level: str = EVIDENCE_LEVEL_RD
    legal_confidence: str = LEGAL_CONF_NONE
    # Chronological context only — never elevates legal_confidence
    chronological_context: list[str] = field(default_factory=list)
    priority_documents: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _search_hits(joined: str, patterns: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for pat in patterns:
        m = re.search(pat, joined, re.I)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(joined), m.end() + 40)
            found.append(joined[start:end].strip())
    return found


def _chronological_notes(
    *,
    signature_year: int | None,
    published_on_pncp: bool,
    origin_process_year: int | None,
    origin_edital_year: int | None,
) -> list[str]:
    """Context for investigation priority — must not elevate legal confidence."""
    notes: list[str] = []
    if signature_year is not None:
        notes.append(
            f"Assinatura em {signature_year} é contexto cronológico; "
            f"não comprova regime da Lei 14.133/2021."
        )
        if TRANSITION_START_YEAR <= signature_year <= TRANSITION_END_YEAR:
            notes.append(
                f"Ano {signature_year} está no período de transição dual "
                f"(8.666/RDC/14.133) — investigar fundamento do processo originário."
            )
        elif signature_year == POST_TRANSITION_AMBIGUITY_YEAR:
            notes.append(
                "Assinatura em 2024 pode decorrer de edital/processo legado de 2023 "
                "ou anterior — ano não presume Lei 14.133."
            )
    if published_on_pncp:
        notes.append(
            "Publicação no PNCP não comprova, isoladamente, o regime jurídico."
        )
    if origin_edital_year is not None:
        notes.append(f"Edital/processo originário: ano {origin_edital_year}.")
    if origin_process_year is not None and origin_process_year != origin_edital_year:
        notes.append(f"Processo originário: ano {origin_process_year}.")
    return notes


def classify_legal_regime(
    *,
    structured_regime: str | None = None,
    document_texts: list[str] | None = None,
    objeto: str | None = None,
    signature_year: int | None = None,
    published_on_pncp: bool = False,
    origin_process_year: int | None = None,
    origin_edital_year: int | None = None,
    origin_document_texts: list[str] | None = None,
    initiation_act_date: date | int | str | None = None,
    document_link_validated: bool = False,
    has_official_linked_document: bool | None = None,
) -> RegimeResult:
    """Classify legal regime with fail-closed evidence hierarchy R-A…R-X.

    Year/PNCP alone never prove or presume Lei 14.133. Legacy origin process
    (edital 8.666, process year) wins over a later signature year.
    """
    chrono = _chronological_notes(
        signature_year=signature_year,
        published_on_pncp=published_on_pncp,
        origin_process_year=origin_process_year,
        origin_edital_year=origin_edital_year,
    )
    initiation_year = _year_of(initiation_act_date)
    official_linked = (
        has_official_linked_document
        if has_official_linked_document is not None
        else bool(document_texts)
    )

    # --- Origin legacy overrides signature year (2024 contract from 2023 edital) ---
    origin_texts = list(origin_document_texts or [])
    origin_joined = _norm("\n".join(origin_texts))
    origin_8666 = _search_hits(origin_joined, _8666_PATTERNS) if origin_joined else []
    origin_rdc = _search_hits(origin_joined, _RDC_PATTERNS) if origin_joined else []
    origin_14133 = _search_hits(origin_joined, _14133_PATTERNS) if origin_joined else []

    if origin_8666 and not origin_14133:
        return RegimeResult(
            regime=REGIME_8666,
            confidence=0.9,
            proven=True,
            evidence_method="origin_process_document",
            excerpts=origin_8666[:3],
            source_fields=["origin_document_texts"],
            reason_codes=["origin_process_cites_8666", "signature_year_does_not_override"],
            notes=(
                "Fundamento do processo/edital originário sob Lei 8.666 prevalece "
                "sobre o ano de assinatura do contrato."
            ),
            evidence_level=EVIDENCE_LEVEL_RA,
            legal_confidence=LEGAL_CONF_HIGH,
            chronological_context=chrono,
        )
    if origin_rdc and not origin_14133:
        return RegimeResult(
            regime=REGIME_RDC,
            confidence=0.85,
            proven=True,
            evidence_method="origin_process_document",
            excerpts=origin_rdc[:3],
            source_fields=["origin_document_texts"],
            reason_codes=["origin_process_cites_rdc", "signature_year_does_not_override"],
            notes="Processo originário sob RDC — ano de assinatura não altera o regime.",
            evidence_level=EVIDENCE_LEVEL_RA,
            legal_confidence=LEGAL_CONF_HIGH,
            chronological_context=chrono,
        )
    if origin_is_legacy_regime(
        origin_process_year=origin_process_year,
        origin_edital_year=origin_edital_year,
        origin_document_texts=origin_document_texts,
    ) and not origin_14133:
        # Pre-2021 origin year without 14.133 citation → legacy presumption of 8.666 family
        legacy_year = origin_edital_year or origin_process_year
        return RegimeResult(
            regime=REGIME_8666,
            confidence=0.8,
            proven=True,
            evidence_method="origin_process_year",
            source_fields=["origin_edital_year", "origin_process_year"],
            reason_codes=["origin_process_pre_14133", "signature_year_does_not_override"],
            notes=(
                f"Processo/edital originário de {legacy_year} (anterior à Lei 14.133) "
                f"prevalece sobre assinatura posterior."
            ),
            evidence_level=EVIDENCE_LEVEL_RA,
            legal_confidence=LEGAL_CONF_HIGH,
            chronological_context=chrono,
            excerpts=[f"origin_year={legacy_year}"],
        )

    # 1) Structured field — R-A when explicit
    raw = (structured_regime or "").strip().upper()
    if raw:
        compact = raw.replace(".", "").replace("/", "").replace(" ", "")
        if "14133" in compact or "14.133" in (structured_regime or ""):
            return RegimeResult(
                regime=REGIME_14133,
                confidence=0.95,
                proven=True,
                evidence_method="structured_field",
                source_fields=["structured_regime"],
                excerpts=[structured_regime or ""],
                reason_codes=["structured_14133", "evidence_level_r_a"],
                evidence_level=EVIDENCE_LEVEL_RA,
                legal_confidence=LEGAL_CONF_HIGH,
                chronological_context=chrono,
            )
        if "8666" in compact or "8.666" in (structured_regime or ""):
            return RegimeResult(
                regime=REGIME_8666,
                confidence=0.95,
                proven=True,
                evidence_method="structured_field",
                source_fields=["structured_regime"],
                excerpts=[structured_regime or ""],
                reason_codes=["structured_8666"],
                evidence_level=EVIDENCE_LEVEL_RA,
                legal_confidence=LEGAL_CONF_HIGH,
                chronological_context=chrono,
            )
        if "10520" in compact or "10.520" in (structured_regime or ""):
            return RegimeResult(
                regime=REGIME_10520,
                confidence=0.9,
                proven=True,
                evidence_method="structured_field",
                source_fields=["structured_regime"],
                excerpts=[structured_regime or ""],
                reason_codes=["structured_10520"],
                evidence_level=EVIDENCE_LEVEL_RA,
                legal_confidence=LEGAL_CONF_HIGH,
                chronological_context=chrono,
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
                evidence_level=EVIDENCE_LEVEL_RA,
                legal_confidence=LEGAL_CONF_HIGH,
                chronological_context=chrono,
            )

    # 2) Document / object text citations
    blobs = list(document_texts or [])
    if objeto:
        blobs.append(objeto)
    joined = _norm("\n".join(blobs))

    hits_14133 = _search_hits(joined, _14133_PATTERNS) if joined else []
    hits_8666 = _search_hits(joined, _8666_PATTERNS) if joined else []
    hits_10520 = _search_hits(joined, _10520_PATTERNS) if joined else []
    hits_rdc = _search_hits(joined, _RDC_PATTERNS) if joined else []

    # R-X — contradictory explicit citations in official documents
    older = bool(hits_8666 or hits_rdc or hits_10520)
    if hits_14133 and older and document_texts:
        return RegimeResult(
            regime=REGIME_CONFLICT,
            confidence=0.5,
            proven=False,
            evidence_method="document_excerpt_conflict",
            excerpts=(hits_14133 + hits_8666 + hits_rdc + hits_10520)[:5],
            source_fields=["document_texts"],
            reason_codes=["legal_regime_conflict", "evidence_level_r_x"],
            notes=(
                "Referências contraditórias a regimes distintos no acervo documental — "
                "impedir abordagem jurídica específica até revisão humana."
            ),
            evidence_level=EVIDENCE_LEVEL_RX,
            legal_confidence=LEGAL_CONF_CONFLICT,
            chronological_context=chrono,
            priority_documents=list(PRIORITY_REGIME_DOCUMENTS),
        )

    # Explicit older regimes (exclusion of 14.133)
    if hits_8666 and not hits_14133:
        return RegimeResult(
            regime=REGIME_8666,
            confidence=0.85,
            proven=True,
            evidence_method="document_excerpt",
            excerpts=hits_8666[:3],
            source_fields=["document_texts" if document_texts else "objeto"],
            reason_codes=["document_cites_8666"],
            evidence_level=EVIDENCE_LEVEL_RA,
            legal_confidence=LEGAL_CONF_HIGH,
            chronological_context=chrono,
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
            evidence_level=EVIDENCE_LEVEL_RA,
            legal_confidence=LEGAL_CONF_HIGH,
            chronological_context=chrono,
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
            evidence_level=EVIDENCE_LEVEL_RA,
            legal_confidence=LEGAL_CONF_HIGH,
            chronological_context=chrono,
        )

    # R-A — explicit 14.133 in official linked documents
    if hits_14133 and document_texts and official_linked:
        return RegimeResult(
            regime=REGIME_14133,
            confidence=0.9,
            proven=True,
            evidence_method="document_excerpt",
            excerpts=hits_14133[:3],
            source_fields=["document_texts"],
            reason_codes=["document_cites_14133", "evidence_level_r_a"],
            evidence_level=EVIDENCE_LEVEL_RA,
            legal_confidence=LEGAL_CONF_HIGH,
            chronological_context=chrono,
        )

    # Object-only 14.133 mention — NOT proof, NOT R-B (insufficient official link)
    object_only_14133 = bool(hits_14133) and not document_texts

    # R-B — strongly indicated by convergent official signals (never proven).
    # Express 14.133 in official linked docs already returned R-A above.
    #
    # MUST have ≥1 positive official normative/fundamento signal compatible with
    # Lei 14.133 (citation in origin process or in docs when not full R-A).
    # Post-transition year + absence of legacy + non-empty docs alone is NOT enough
    # (year must never be the decisive positive signal for probable 14.133).
    initiation_after_transition = False
    for y in (
        initiation_year,
        origin_edital_year,
        origin_process_year,
    ):
        if y is not None and y > TRANSITION_END_YEAR:
            initiation_after_transition = True
            break

    # Positive normative signal (not year, not silence):
    # - origin process/edital cites 14.133; or
    # - contract-side docs cite 14.133 but official_linked is false (not R-A yet)
    positive_normative_14133 = bool(origin_14133) or (
        bool(hits_14133) and bool(document_texts) and not official_linked
    )
    if (
        positive_normative_14133
        and document_link_validated
        and bool(document_texts or origin_document_texts)
        and not older
        and initiation_after_transition
        and not hits_8666
        and not hits_rdc
        and not hits_10520
    ):
        excerpts_rb = (hits_14133 or origin_14133)[:3]
        return RegimeResult(
            regime=REGIME_LIKELY_14133,
            confidence=0.7,
            proven=False,
            evidence_method="convergent_official_signals",
            excerpts=excerpts_rb,
            source_fields=[
                "document_texts" if hits_14133 else "origin_document_texts",
                "document_link_validated",
                "initiation_act_or_edital_year",
            ],
            reason_codes=[
                "evidence_level_r_b",
                "convergent_post_transition_signals",
                "positive_normative_14133_signal",
                "regime_not_proven",
            ],
            notes=(
                "Sinais oficiais convergentes (fundamento/normativo 14.133 + vínculo "
                "documental + pós-transição, sem legado) indicam possível enquadramento; "
                "regime_proven=false — confirmar com prova R-A."
            ),
            evidence_level=EVIDENCE_LEVEL_RB,
            legal_confidence=LEGAL_CONF_MEDIUM,
            chronological_context=chrono,
            priority_documents=list(PRIORITY_REGIME_DOCUMENTS),
        )

    if object_only_14133:
        # Weak object mention — does not prove, does not elevate to LIKELY_14133
        chrono = chrono + [
            "Menção no objeto sem documento oficial — não comprova regime."
        ]

    # R-C — transitional regime unresolved
    transitional = in_transition_or_ambiguity_window(
        signature_year=signature_year,
        origin_process_year=origin_process_year,
        origin_edital_year=origin_edital_year,
    )
    if transitional and not (hits_14133 and document_texts):
        return RegimeResult(
            regime=REGIME_TRANSITIONAL_UNRESOLVED,
            confidence=0.0,
            proven=False,
            evidence_method="transitional_unresolved",
            reason_codes=[
                "evidence_level_r_c",
                "transitional_regime_unresolved",
                "year_does_not_prove_regime",
            ],
            notes=(
                "Contratação no período de transição ou logo após; não há documento "
                "oficial com fundamento legal suficiente. Possibilidade concreta de "
                "edital/processo legado (8.666/RDC/14.133). Solicitar documentos de regime."
            ),
            evidence_level=EVIDENCE_LEVEL_RC,
            legal_confidence=LEGAL_CONF_UNRESOLVED,
            chronological_context=chrono,
            priority_documents=list(PRIORITY_REGIME_DOCUMENTS),
        )

    # R-D — unknown
    notes_parts = list(chrono)
    if object_only_14133:
        notes_parts.append(
            "Menção no objeto sem documento oficial — não comprova regime para HOT/VERIFIED."
        )
    if not notes_parts:
        notes_parts.append(
            "Regime jurídico não comprovado por campo estruturado nem documento."
        )

    return RegimeResult(
        regime=REGIME_UNKNOWN,
        confidence=0.0,
        proven=False,
        evidence_method="insufficient",
        reason_codes=["regime_not_proven", "evidence_level_r_d"],
        notes=" ".join(notes_parts),
        evidence_level=EVIDENCE_LEVEL_RD,
        legal_confidence=LEGAL_CONF_NONE,
        chronological_context=chrono,
        priority_documents=list(PRIORITY_REGIME_DOCUMENTS),
        excerpts=hits_14133[:2] if object_only_14133 else [],
        source_fields=["objeto"] if object_only_14133 else [],
    )


def regime_allows_likely_opportunity(result: RegimeResult | None = None, *, regime: str | None = None, proven: bool = False) -> bool:
    """True only for R-A proven 14.133 or R-B LIKELY_14133 — never year/PNCP."""
    if result is not None:
        if result.regime == REGIME_14133 and result.proven:
            return True
        if result.regime == REGIME_LIKELY_14133:
            return True
        return False
    if regime == REGIME_14133 and proven:
        return True
    if regime == REGIME_LIKELY_14133:
        return True
    return False


def is_14133_specific_outreach_allowed(result: RegimeResult) -> bool:
    """Specific Lei 14.133 diagnostic language only for R-A or R-B."""
    return regime_allows_likely_opportunity(result)
