"""Assemble claims/events from official document text. Never invent FACT."""

from __future__ import annotations

import re
from typing import Any

from scripts.historical_contract_authority.models import Claim, DocumentRecord, TimelineEvent

_BRL = re.compile(r"R\$\s*([\d.]{1,18},\d{2})")
_DAYS = re.compile(r"(\d{1,4})\s*dias", re.I)
_ADT_PRAZO = re.compile(r"aditivo de prazo|acrescimo de\s+\d+\s+dias|prorrog", re.I)
_ADT_VALOR = re.compile(r"aditivo de valor|acrescimo de R\$", re.I)
_ESCOPO = re.compile(r"alteracao de escopo|exclusao de|inclusao de recape", re.I)
_ASSINA = re.compile(r"assinatura", re.I)


def _locator(doc: DocumentRecord) -> str:
    return doc.locator.as_text()


def _brl_to_plain(raw: str) -> str:
    digits = raw.replace(".", "").replace(",", ".")
    try:
        return f"{float(digits):.2f}"
    except ValueError:
        return raw


def assemble_from_documents(documents: tuple[DocumentRecord, ...], case: dict[str, Any]) -> dict[str, Any]:
    claims: list[Claim] = []
    events: list[TimelineEvent] = []
    found_prazo = False
    found_valor_adt = False
    found_escopo = False
    for doc in documents:
        text = doc.text or ""
        loc = _locator(doc)
        if not loc or loc == "UNSPECIFIED":
            continue
        if doc.ocr_used and doc.ocr_confidence is not None and doc.ocr_confidence < 0.50:
            claims.append(
                Claim(
                    claim_id=f"unk-{doc.document_id}",
                    klass="UNKNOWN",
                    text="Trecho ilegivavel permanece UNKNOWN.",
                    source_refs=(doc.document_id,),
                    locators=(loc,),
                    confidence=float(doc.ocr_confidence),
                    publication_fit="internal",
                )
            )
        money = _BRL.findall(text)
        if money:
            claims.append(
                Claim(
                    claim_id=f"fact-valor-{doc.document_id}",
                    klass="FACT",
                    text=f"Valor mencionado no documento: {_brl_to_plain(money[0])} BRL.",
                    source_refs=(doc.document_id,),
                    locators=(loc,),
                    confidence=0.7,
                    publication_fit="internal",
                )
            )
        if _ADT_PRAZO.search(text):
            found_prazo = True
            days = _DAYS.search(text)
            events.append(
                TimelineEvent(
                    event_id=f"evt-prazo-{doc.document_id}",
                    kind="amendment_term",
                    at=doc.effective_at or doc.published_at,
                    summary="Aditivo de prazo mencionado no documento oficial.",
                    source_refs=(doc.document_id,),
                    locators=(loc,),
                    delta_days=int(days.group(1)) if days else None,
                )
            )
            claims.append(
                Claim(
                    claim_id=f"fact-prazo-{doc.document_id}",
                    klass="FACT",
                    text="Documento oficial registra aditivo de prazo.",
                    source_refs=(doc.document_id,),
                    locators=(loc,),
                    confidence=0.75,
                    publication_fit="internal",
                )
            )
        if _ADT_VALOR.search(text):
            found_valor_adt = True
            events.append(
                TimelineEvent(
                    event_id=f"evt-valor-{doc.document_id}",
                    kind="amendment_value",
                    at=doc.effective_at or doc.published_at,
                    summary="Aditivo de valor mencionado no documento oficial.",
                    source_refs=(doc.document_id,),
                    locators=(loc,),
                    delta_value=_brl_to_plain(money[0]) if money else None,
                )
            )
            claims.append(
                Claim(
                    claim_id=f"fact-adt-valor-{doc.document_id}",
                    klass="FACT",
                    text="Documento oficial registra aditivo de valor.",
                    source_refs=(doc.document_id,),
                    locators=(loc,),
                    confidence=0.75,
                    publication_fit="internal",
                )
            )
        if _ESCOPO.search(text):
            found_escopo = True
            events.append(
                TimelineEvent(
                    event_id=f"evt-escopo-{doc.document_id}",
                    kind="scope_change",
                    at=doc.effective_at or doc.published_at,
                    summary="Alteracao de escopo mencionada no documento oficial.",
                    source_refs=(doc.document_id,),
                    locators=(loc,),
                )
            )
        if doc.klass in {"instrument", "registry", "contract"} and _ASSINA.search(text):
            events.append(
                TimelineEvent(
                    event_id=f"evt-assina-{doc.document_id}",
                    kind="signature",
                    at=(case.get("dates") or {}).get("assinatura") or doc.published_at,
                    summary="Assinatura mencionada no instrumento.",
                    source_refs=(doc.document_id,),
                    locators=(loc,),
                )
            )
    question = ""
    if found_prazo and found_valor_adt:
        question = (
            "Como o aditivo de prazo e o aditivo de valor documentados se combinam "
            "no cronograma original, e o que permanece NOT_COMPUTABLE sem unidade?"
        )
    elif found_prazo:
        question = "Como o aditivo de prazo documentado altera o cronograma original, e o que permanece NOT_COMPUTABLE?"
    elif found_valor_adt:
        question = (
            "Qual o delta de valor documentado no aditivo, e o que permanece NOT_COMPUTABLE sem semântica unitária?"
        )
    elif found_escopo:
        question = (
            "Qual alteração de escopo o documento oficial registra, e o que não se pode concluir sobre quantitativos?"
        )
    return {
        "claims": tuple(claims),
        "events": tuple(events),
        "technical_question": question,
    }
