"""analysis_mode and comparability policy. Comparative language reactivates the peer gate."""

from __future__ import annotations

import re
from typing import Any, Literal

AnalysisMode = Literal["DOCUMENT_CHAIN", "TIMELINE", "COMPARATIVE"]

ANALYSIS_MODES: tuple[str, ...] = ("DOCUMENT_CHAIN", "TIMELINE", "COMPARATIVE")

COMPARATIVE_PATTERNS = (
    re.compile(r"\boutlier\b", re.I),
    re.compile(r"\branking\b", re.I),
    re.compile(r"\bbenchmark\b", re.I),
    re.compile(r"\bpercentil\b", re.I),
    re.compile(r"\bpeers?\b", re.I),
    re.compile(r"grupo compar", re.I),
    re.compile(r"compar[aá]ve", re.I),
    re.compile(r"acima da mediana", re.I),
    re.compile(r"abaixo da mediana", re.I),
    re.compile(r"fora da distribui", re.I),
    re.compile(r"delta de peer", re.I),
    re.compile(r"frente (aos|a os|aos seus) pares", re.I),
    re.compile(r"at[ií]pico frente", re.I),
)

COMMERCIAL_ADJACENCY = {
    "aditivo": ("aditiv", "apostila"),
    "reequilibrio": ("reequilibr", "recomposi"),
    "reajuste": ("reajuste", "repactu"),
    "prazo": ("aditivo de prazo", "prorrog", "amplia[cç][aã]o de prazo"),
    "medicao_glosa": ("medi[cç][aã]o", "glosa"),
    "bdi": (r"\bbdi\b",),
    "defesa_margem": ("defesa de margem", "margem de contribui"),
}


_NEGATION = re.compile(
    r"(n[aã]o\s+(um|uma|é|e|ha|há|se)?\s*|sem\s+|aus[eê]ncia de\s+|nunca\s+)",
    re.I,
)


def detect_comparative_language(*texts: str | None) -> tuple[str, ...]:
    hits: list[str] = []
    for text in texts:
        if not text:
            continue
        for pattern in COMPARATIVE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            prefix = text[max(0, match.start() - 24) : match.start()]
            if _NEGATION.search(prefix):
                continue
            hits.append(pattern.pattern)
    return tuple(dict.fromkeys(hits))


def commercial_adjacency(*texts: str | None) -> tuple[str, ...]:
    blob = " ".join(item for item in texts if item).casefold()
    found: list[str] = []
    for name, tokens in COMMERCIAL_ADJACENCY.items():
        if any(re.search(token, blob, re.I) for token in tokens):
            found.append(name)
    return tuple(found)


def resolve_analysis_mode(
    *,
    requested: str | None,
    claims: tuple[str, ...],
    insight: str | None,
    limitations: tuple[str, ...],
    comparative_engine_used: bool,
) -> tuple[str, tuple[str, ...]]:
    requested_mode = (requested or "").strip().upper() or None
    comparative_hits = detect_comparative_language(insight, *claims, *limitations)
    if comparative_engine_used or requested_mode == "COMPARATIVE" or comparative_hits:
        return "COMPARATIVE", comparative_hits
    if requested_mode in ANALYSIS_MODES:
        return requested_mode, ()
    return "DOCUMENT_CHAIN", ()


def resolve_comparability(
    *,
    analysis_mode: str,
    comparative_hits: tuple[str, ...],
    singular_insight: str | None,
    limitations_declare_no_comparison: bool,
    engine_status: str | None,
    engine_reason_codes: tuple[str, ...],
    unit_compatible: bool,
    regime_compatible: bool,
    scope_compatible: bool,
    period_compatible: bool,
) -> dict[str, Any]:
    if analysis_mode == "COMPARATIVE" or comparative_hits:
        if not (unit_compatible and regime_compatible and scope_compatible and period_compatible):
            return {
                "status": "NOT_COMPARABLE",
                "reason_codes": (
                    "comparative_language_requires_peer_gate",
                    *engine_reason_codes,
                    *(("incompatible_unit",) if not unit_compatible else ()),
                    *(("incompatible_regime",) if not regime_compatible else ()),
                    *(("incompatible_scope",) if not scope_compatible else ()),
                    *(("incompatible_period",) if not period_compatible else ()),
                ),
                "justification": (
                    "Comparative language or COMPARATIVE mode reactivates the peer gate; "
                    "compatible unit/regime/scope/period were not demonstrated."
                ),
                "peer_gate": "active",
            }
        status = (
            engine_status if engine_status in {"COMPARABLE", "HOLD_FOR_DATA", "NOT_COMPARABLE"} else "NOT_COMPARABLE"
        )
        return {
            "status": status,
            "reason_codes": engine_reason_codes or ("peer_engine",),
            "justification": "COMPARATIVE mode uses the fail-closed peer gate.",
            "peer_gate": "active",
        }
    if analysis_mode in {"DOCUMENT_CHAIN", "TIMELINE"}:
        if not singular_insight or not limitations_declare_no_comparison:
            return {
                "status": "HOLD_FOR_DATA",
                "reason_codes": ("missing_singular_insight_or_comparison_limitation",),
                "justification": "Non-comparative mode still needs a document-backed insight and an explicit no-comparison limitation.",
                "peer_gate": "not_applicable",
            }
        return {
            "status": "NOT_APPLICABLE",
            "reason_codes": ("no_comparative_claim", "singular_document_insight"),
            "justification": (
                "DOCUMENT_CHAIN/TIMELINE emits no ranking, outlier, benchmark or peer delta; "
                "absence of comparison is an explicit limitation."
            ),
            "peer_gate": "not_applicable",
        }
    return {
        "status": "NOT_COMPARABLE",
        "reason_codes": ("unknown_analysis_mode",),
        "justification": "Unknown analysis_mode cannot authorize comparison.",
        "peer_gate": "active",
    }
