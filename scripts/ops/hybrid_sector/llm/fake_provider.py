"""Fake LLM provider for offline tests — deterministic, no network."""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from scripts.ops.hybrid_sector.llm.protocol import LLMError
from scripts.ops.hybrid_sector.llm.schema import (
    PROMPT_VERSION,
    SectorArbitrationRequest,
    SectorLLMDecision,
)
from scripts.ops.sector_classifier import normalize_text


class FakeLLMProvider:
    """Rule-based offline arbiter for CI. Configurable error injection."""

    def __init__(
        self,
        *,
        force_error: str | None = None,
        force_decision: SectorLLMDecision | None = None,
        invent_evidence: bool = False,
        low_confidence: bool = False,
        custom: Callable[[SectorArbitrationRequest], SectorLLMDecision] | None = None,
    ) -> None:
        self.force_error = force_error
        self.force_decision = force_decision
        self.invent_evidence = invent_evidence
        self.low_confidence = low_confidence
        self.custom = custom
        self.prompt_version = PROMPT_VERSION
        self.model = "offline-fake"
        self.call_log: list[dict[str, Any]] = []

    def classify(self, request: SectorArbitrationRequest) -> SectorLLMDecision:
        self.call_log.append(
            {
                "id": request.canonical_id,
                "variant": request.prompt_variant,
                "prompt_version": self.prompt_version,
            }
        )
        if self.force_error:
            raise LLMError(self.force_error, kind=self.force_error)
        if self.force_decision is not None:
            return self.force_decision
        if self.custom is not None:
            return self.custom(request)

        blob = normalize_text(request.trusted_source_blob())
        # Detect injection attempts in source — still classify on content, never follow
        _ = bool(
            re.search(
                r"ignore\s+(as\s+)?instru[cç][oõ]es|ignore\s+previous|"
                r"system\s*prompt|responda\s+apenas\s+match|"
                r"\{\s*\"decision\"\s*:\s*\"MATCH\"",
                request.source_text or request.objeto or "",
                re.I,
            )
        )

        pos = any(
            k in blob
            for k in (
                "paviment",
                "drenagem",
                "terraplen",
                "saneamento basico",
                "rede de esgoto",
                "obra de engenharia",
                "reforma predial",
                "construcao de escola",
                "construcao de predio",
                "ampliacao de escola",
                "manutencao predial",
                "contencao",
                "muro de arrimo",
                "revitalizacao",
                "requalificacao",
                "empreitada",
                "recuperacao estrutural",
                "ponte",
                "viaduto",
                "implantacao de rede",
                "galeria pluvial",
            )
        )
        neg = any(
            k in blob
            for k in (
                "software",
                "medicamento",
                "exame laborator",
                "curso de",
                "computador",
                "notebook",
                "combustivel",
                "gasolina",
                "uniforme",
                "vestuario",
                "servicos bancarios",
                "arrecadacao bancaria",
                "construcao de conhecimento",
                "voip",
                "seguro de frota",
            )
        )
        mixed = bool(
            re.search(
                r"fornecimento.{0,40}instala|aquisicao.{0,40}(obra|implanta)|"
                r"equipamento.{0,40}obra",
                blob,
            )
        )
        short = len(blob.split()) <= 6

        if self.invent_evidence:
            return SectorLLMDecision(
                decision="MATCH",
                confidence=90,
                evidence=["trecho inventado que nao existe no edital XYZ-999"],
                reasoning="invented",
                missing_information=[],
                needs_more_data=False,
            )

        if mixed or short or (pos and neg):
            ev = _literal_snip(request, blob)
            return SectorLLMDecision(
                decision="REVIEW",
                confidence=40 if self.low_confidence else 55,
                evidence=ev,
                reasoning="escopo misto, texto curto ou sinais conflitantes",
                missing_information=["anexos_tecnicos"] if short else [],
                needs_more_data=short,
            )
        if pos and not neg:
            ev = _literal_snip(request, blob)
            conf = 35 if self.low_confidence else 85
            return SectorLLMDecision(
                decision="MATCH" if conf >= 60 else "REVIEW",
                confidence=conf,
                evidence=ev,
                reasoning="evidência positiva de obras/engenharia",
                missing_information=[],
                needs_more_data=False,
            )
        if neg and not pos:
            ev = _literal_snip(request, blob)
            return SectorLLMDecision(
                decision="NO_MATCH",
                confidence=35 if self.low_confidence else 88,
                evidence=ev,
                reasoning="evidência de objeto alheio ao mercado Extra",
                missing_information=[],
                needs_more_data=False,
            )
        return SectorLLMDecision(
            decision="REVIEW",
            confidence=40,
            evidence=_literal_snip(request, blob),
            reasoning="dúvida — REVIEW por padrão",
            missing_information=["mais_contexto"],
            needs_more_data=True,
        )


def _literal_snip(request: SectorArbitrationRequest, blob: str) -> list[str]:
    raw = request.objeto or request.titulo or request.trusted_source_blob()
    if not raw:
        return []
    snip = raw.strip()[:120]
    return [snip] if snip else []
