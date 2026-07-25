"""Phase 4 — selective deterministic classifier.

Maps champion sector_classifier labels into:
  CLEAR_POSITIVE | GRAY_ZONE | CLEAR_NEGATIVE

Negative rules cannot auto-win when explicit execution/implantação signals exist.
Absence of known keywords is never automatic NO_MATCH / CLEAR_NEGATIVE alone.
"""
from __future__ import annotations

import re
from typing import Any

from scripts.ops.hybrid_sector.models import CandidateRecord, DeterministicResult, RawOpportunity
from scripts.ops.sector_classifier import (
    RULE_VERSION,
    classify_object,
    normalize_text,
)

# Explicit execution / obra signals that block irreversible CLEAR_NEGATIVE
_EXECUTION_SIGNAL = re.compile(
    r"\b("
    r"execu[cç][aã]o|implanta[cç][aã]o|instala[cç][aã]o|montagem|"
    r"obra\s+civil|reforma|adequa[cç][aã]o|recupera[cç][aã]o|"
    r"constru[cç][aã]o|amplia[cç][aã]o|revitaliza[cç][aã]o|"
    r"fornecimento\s+com\s+servi[cç]o|contrata[cç][aã]o\s+integrada|"
    r"empreitada|comissionamento|requalifica[cç]"
    r")\b",
    re.I,
)

_MIXED_SCOPE = re.compile(
    r"\b(fornecimento|aquisicao|aquisi[cç][aã]o).{0,60}\b(instala[cç]|implanta[cç]|montagem|obra)\b|"
    r"\b(instala[cç]|implanta[cç]|montagem).{0,60}\b(fornecimento|aquisicao|equipamento)\b",
    re.I,
)

_SHORT_TEXT_WORDS = 6


def _blob(rec: RawOpportunity) -> str:
    return normalize_text(rec.text_blob())


def classify_selective(
    rec: RawOpportunity | CandidateRecord,
    *,
    profile: dict[str, Any] | None = None,
    channel_conflict: bool = False,
    semantic_without_keyword: bool = False,
) -> DeterministicResult:
    """Deterministic selective decision — never commercial MATCH/NO_MATCH directly."""
    if isinstance(rec, CandidateRecord):
        candidate = rec
        raw = rec.record
        retrieved = set(candidate.retrieved_by)
        semantic_without_keyword = semantic_without_keyword or (
            "semantic" in retrieved
            and "lexical" not in retrieved
            and not candidate.zero_match_rescue
        )
        channel_conflict = channel_conflict or (
            len(retrieved - {"full_universe", "zero_match"}) >= 2
            and "lexical" in retrieved
            and ("semantic" in retrieved or "metadata" in retrieved)
        )
    else:
        raw = rec
        retrieved = set()

    blob = _blob(raw)
    items_blob = normalize_text(" ".join(raw.items))
    short = len(blob.split()) <= _SHORT_TEXT_WORDS if blob else True
    has_exec = bool(_EXECUTION_SIGNAL.search(blob) or _EXECUTION_SIGNAL.search(items_blob))
    mixed = bool(_MIXED_SCOPE.search(blob))

    champion = classify_object(
        objeto=raw.objeto,
        titulo=raw.titulo,
        itens=" ".join(raw.items) if raw.items else None,
        profile=profile,
    )

    pos = list(champion.positive_terms or [])
    neg = list(champion.negative_terms or [])
    # Approximate margin from champion confidence + hit counts
    margin = abs(len(pos) * 0.35 - len(neg) * 0.4)

    evidence: list[str] = []
    if champion.textual_evidence:
        evidence.append(champion.textual_evidence[:200])
    for t in pos[:5]:
        evidence.append(f"pos:{t}")
    for t in neg[:5]:
        evidence.append(f"neg:{t}")

    # Map champion → selective
    label = champion.label
    decision: str
    reason: str
    conf = float(champion.confidence)

    # Empty / missing critical text → gray
    if not blob:
        return DeterministicResult(
            decision="GRAY_ZONE",
            confidence=0.2,
            reason="texto vazio ou ausente — ausência de keyword não é NO_MATCH",
            rule_version=RULE_VERSION,
            short_text=True,
            champion_label=label,
            evidence=evidence,
        )

    if label == "ENGINEERING_HIGH_CONFIDENCE" and not mixed and conf >= 0.75 and pos:
        decision = "CLEAR_POSITIVE"
        reason = champion.reason or "evidência suficiente de execução aderente"
    elif label in {"NON_ENGINEERING", "EXCLUDED_CATEGORY"}:
        # Negative cannot auto-win over execution signals
        if has_exec or mixed:
            decision = "GRAY_ZONE"
            reason = (
                "sinal negativo presente mas há execução/implantação/instalação/obra — "
                "mínimo GRAY_ZONE (negativo não vence sozinho)"
            )
            conf = min(conf, 0.55)
        elif short and (raw.has_tr or raw.has_anexos or raw.categories):
            decision = "GRAY_ZONE"
            reason = "texto curto com documentos/categoria — não CLEAR_NEGATIVE irreversível"
            conf = min(conf, 0.5)
        elif semantic_without_keyword:
            decision = "GRAY_ZONE"
            reason = "sem keyword lexical mas recuperado semanticamente — não CLEAR_NEGATIVE"
            conf = min(conf, 0.55)
        elif not pos and not neg and short:
            # Absence of keywords alone ≠ CLEAR_NEGATIVE certainty
            decision = "GRAY_ZONE"
            reason = "ausência de keyword conhecida não é ausência de oportunidade"
            conf = 0.4
        else:
            decision = "CLEAR_NEGATIVE"
            reason = champion.reason or "objeto inequivocamente alheio sem sinal de execução"
    elif label in {"ENGINEERING_REVIEW", "AMBIGUOUS"}:
        decision = "GRAY_ZONE"
        reason = champion.reason or "zona cinzenta do champion / ambíguo"
    else:
        decision = "GRAY_ZONE"
        reason = f"label champion não mapeado limpo: {label}"

    # Force gray conditions
    force_gray_reasons: list[str] = []
    if short and decision == "CLEAR_POSITIVE":
        force_gray_reasons.append("texto_curto")
    if mixed:
        force_gray_reasons.append("escopo_misto")
    if channel_conflict and decision != "CLEAR_POSITIVE":
        force_gray_reasons.append("divergencia_canais")
    if margin < 0.15 and pos and neg:
        force_gray_reasons.append("baixa_margem")
    if raw.categories and not pos and any(
        normalize_text(c) for c in raw.categories
        if any(k in normalize_text(c) for k in ("obra", "engenharia", "infra", "saneamento"))
    ):
        force_gray_reasons.append("categoria_oficial_texto_insuficiente")
    if items_blob and has_exec and not pos:
        force_gray_reasons.append("execucao_apenas_nos_itens")

    if force_gray_reasons and decision == "CLEAR_NEGATIVE":
        decision = "GRAY_ZONE"
        reason = f"{reason}; forced_gray={','.join(force_gray_reasons)}"
    elif force_gray_reasons and decision == "CLEAR_POSITIVE" and (
        "escopo_misto" in force_gray_reasons or "texto_curto" in force_gray_reasons
    ):
        decision = "GRAY_ZONE"
        reason = f"{reason}; forced_gray={','.join(force_gray_reasons)}"

    return DeterministicResult(
        decision=decision,  # type: ignore[arg-type]
        confidence=conf,
        positive_signals=pos,
        negative_signals=neg,
        evidence=evidence,
        reason=reason,
        rule_version=RULE_VERSION,
        margin=margin,
        has_execution_signal=has_exec,
        short_text=short,
        champion_label=label,
        mixed_scope=mixed,
    )
