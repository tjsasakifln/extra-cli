"""Golden fixture corpus: twenty adversarial cases. Catalog mode is always fixture."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from scripts.historical_contract_authority.schema import sha256_bytes, sha256_text

PNCP = "https://pncp.gov.br/app/contratos"
DOE = "https://portal.doe.sea.sc.gov.br/edicoes"
ORG = {
    "orgao_cnpj": "82940433000194",
    "orgao_nome": "Municipio de Brusque",
    "fornecedor_cnpj": "07894512000133",
    "fornecedor_nome": "Construtora Vale Verde Ltda",
    "municipio": "Brusque",
    "uf": "SC",
}


def _doc(doc_id: str, klass: str, family: str, *, page: str, section: str, text: str, **extra: Any) -> dict[str, Any]:
    payload_bytes = text.encode("utf-8")
    payload = {
        "document_id": doc_id,
        "title": extra.pop("title", doc_id),
        "class": klass,
        "family": family,
        "url": extra.pop("url", f"{PNCP}/{doc_id}"),
        "locator": {"page": page, "section": section},
        "published_at": extra.pop("published_at", "2024-02-10"),
        "effective_at": extra.pop("effective_at", "2024-03-01"),
        "binary_sha256": extra.pop("binary_sha256", sha256_bytes(payload_bytes)),
        "text_sha256": extra.pop("text_sha256", sha256_text(text)),
        "mime": extra.pop("mime", "application/pdf"),
        "bytes_len": extra.pop("bytes_len", len(payload_bytes)),
        "extract_status": extra.pop("extract_status", "ok"),
        "relation": extra.pop("relation", "primary"),
        "ocr_used": extra.pop("ocr_used", False),
        "text": text,
    }
    payload.update(extra)
    return payload


def _claim(claim_id: str, klass: str, text: str, refs: list[str], locs: list[str], **extra: Any) -> dict[str, Any]:
    payload = {
        "claim_id": claim_id,
        "class": klass,
        "text": text,
        "source_refs": refs,
        "locators": locs,
        "confidence": extra.pop("confidence", 0.9 if klass == "FACT" else 0.5),
        "publication_fit": extra.pop("publication_fit", "internal"),
    }
    payload.update(extra)
    return payload


def _event(
    event_id: str, kind: str, at: str, summary: str, refs: list[str], locs: list[str], **extra: Any
) -> dict[str, Any]:
    payload = {"event_id": event_id, "kind": kind, "at": at, "summary": summary, "source_refs": refs, "locators": locs}
    payload.update(extra)
    return payload


def _peer(suffix: str, valor: str) -> dict[str, Any]:
    return {
        "identity": {
            "contract_id": f"SC-PEER-{suffix}",
            "objeto": "Pavimentacao asfaltica de vias urbanas em Brusque",
            "uf": "SC",
            "municipio": "Brusque" if suffix != "06" else "Gaspar",
            "orgao_cnpj": "82940433000194",
            "fornecedor_cnpj": f"111111110001{suffix}",
        },
        "values": {
            "valor_atual": valor,
            "valor_semantic": "valor_integral_nominal",
            "unidade": "BRL_TOTAL",
            "regime": "empreitada_global",
            "modalidade": "pregao",
            "porte": "medio",
            "value_basis": "original",
        },
        "dates": {"reference": "2024-03-01"},
        "evidence_ref": f"{PNCP}/SC-PEER-{suffix}",
    }


RICH_DOCS = [
    _doc(
        "inst-001",
        "instrument",
        "instrument",
        page="1-12",
        section="cl.4",
        text="Contrato de pavimentacao asfaltica. Valor original R$ 4.250.000,00. Prazo 360 dias.",
    ),
    _doc(
        "adt-prazo-001",
        "amendment_term",
        "amendment",
        page="1",
        section="art.1",
        text="Termo aditivo de prazo: acrescimo de 120 dias. Fundamento: readequacao de cronograma fisico.",
        url=f"{DOE}/adt-prazo-001",
    ),
    _doc(
        "adt-valor-001",
        "amendment_value",
        "amendment",
        page="1",
        section="art.2",
        text="Termo aditivo de valor: acrescimo de R$ 510.000,00 sobre 4.250.000,00.",
        url=f"{DOE}/adt-valor-001",
    ),
    _doc(
        "doe-001",
        "official_publication",
        "publication",
        page="3",
        section="secao-contratos",
        text="Publicacao dos termos aditivos de prazo e valor no diario oficial estadual.",
        url=f"{DOE}/2024-10-03",
    ),
]

RICH_CLAIMS = [
    _claim("c-valor-orig", "FACT", "Valor original contratado e 4250000.00 BRL.", ["inst-001"], ["p.1-12|cl.4"]),
    _claim("c-valor-atual", "FACT", "Valor atual apos aditivo e 4760000.00 BRL.", ["adt-valor-001"], ["p.1|art.2"]),
    _claim(
        "c-delta-valor",
        "CALCULATION",
        "Delta de valor = 510000.00 BRL (12.00%).",
        ["inst-001", "adt-valor-001"],
        ["p.1|art.2"],
        formula="delta_value",
        inputs={"valor_original": "4250000.00", "valor_atual": "4760000.00"},
        unit="BRL",
        rounding="ROUND_HALF_EVEN:0.01",
    ),
    _claim("c-prazo-orig", "FACT", "Prazo original e 360 dias.", ["inst-001"], ["p.1-12|cl.4"]),
    _claim("c-prazo-adt", "FACT", "Aditivo de prazo acresce 120 dias.", ["adt-prazo-001"], ["p.1|art.1"]),
    _claim("c-objeto", "FACT", "Objeto e pavimentacao asfaltica de vias urbanas.", ["inst-001"], ["p.1-12|cl.4"]),
    _claim(
        "c-chuva",
        "INFERENCE",
        "A extensao de prazo pode relacionar-se a regime de chuvas; o aditivo cita readequacao de cronograma fisico.",
        ["adt-prazo-001"],
        ["p.1|art.1"],
        confidence=0.35,
        publication_fit="labeled_inference",
    ),
    _claim(
        "c-ocr", "UNKNOWN", "Clausula de medicao na pagina 9 permanece ilegivel.", ["inst-001"], ["p.9"], confidence=0.1
    ),
]

RICH_EVENTS = [
    _event("e-assina", "signature", "2024-02-10", "Assinatura do instrumento.", ["inst-001"], ["p.1"]),
    _event("e-inicio", "start", "2024-03-01", "Inicio da execucao.", ["inst-001"], ["p.2"]),
    _event(
        "e-prazo",
        "amendment_term",
        "2024-09-15",
        "Aditivo de prazo +120 dias.",
        ["adt-prazo-001"],
        ["p.1|art.1"],
        delta_days=120,
    ),
    _event(
        "e-valor",
        "amendment_value",
        "2024-10-02",
        "Aditivo de valor +510000.00.",
        ["adt-valor-001"],
        ["p.1|art.2"],
        delta_value="510000.00",
    ),
    _event("e-pub", "publication", "2024-10-03", "Publicacao dos aditivos.", ["doe-001"], ["p.3"]),
]

RICH_EDITORIAL = {
    "central_question": "Como o aditivo de prazo de 120 dias e o aditivo de valor de 12% se combinam no cronograma fisico original, e o que permanece incalculavel sem unidade e quantitativo?",
    "theses": [
        "O contrato documenta dois aditivos de natureza distinta (prazo e valor) com publicacao oficial propria.",
        "O fundamento textual do aditivo de prazo e readequacao de cronograma, nao chuva.",
        "Sem unidade e quantitativo o impacto unitario permanece NOT_COMPUTABLE.",
    ],
    "why_singular": "Ha cadeia oficial de instrumento + aditivo de prazo + aditivo de valor + publicacao, permitindo separar efeitos de prazo e valor.",
    "transferable_utility": "Construtoras B2G podem usar a separacao prazo/valor para montar defesa de cronograma sem misturar reequilibrio de preco.",
    "possible_implications": ["acompanhar medicao futura", "nao inferir sobrepreco"],
    "reputational_risks": ["nao acusar irregularidade a partir de aditivo"],
    "forbidden_terms": ["irregular", "fraude", "sobrepreco"],
    "cannot_assert": [
        "nao se pode concluir sobrepreco",
        "nao se pode concluir irregularidade",
        "nao se pode calcular preco unitario",
    ],
    "plausible_intent": "entender interacao prazo/valor em contrato de pavimentacao",
}


def rich_base(case_id: str, contract_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "catalog_mode": "fixture",
        "identity": {
            "contract_id": contract_id,
            "process_id": f"PROC-{contract_id}",
            "objeto": "Pavimentacao asfaltica de vias urbanas em Brusque",
            **ORG,
        },
        "values": {
            "valor_original": "4250000.00",
            "valor_atual": "4760000.00",
            "moeda": "BRL",
            "valor_semantic": "valor_integral_nominal",
            "unidade": "BRL_TOTAL",
            "regime": "empreitada_global",
            "modalidade": "pregao",
            "porte": "medio",
            "value_basis": "original",
        },
        "dates": {
            "reference": "2024-02-10",
            "assinatura": "2024-02-10",
            "inicio": "2024-03-01",
            "fim": "2025-06-26",
            "observed_at": "2024-10-03T12:00:00Z",
        },
        "documents": deepcopy(RICH_DOCS),
        "claims": deepcopy(RICH_CLAIMS),
        "events": deepcopy(RICH_EVENTS),
        "contradictions": [
            {
                "contradiction_id": "alt-chuva",
                "description": "O aditivo de prazo nao menciona chuva; cita readequacao de cronograma fisico.",
                "sources": ["adt-prazo-001"],
                "alternatives": ["atraso de desapropriacao", "reescalonamento de frentes"],
                "weakens": ["c-chuva"],
                "pending": ["relatorio climatico oficial nao localizado"],
                "decision": "preserve_inference_as_labeled_only",
            }
        ],
        "editorial": deepcopy(RICH_EDITORIAL),
        "maintenance": {
            "owner": "historical-contract-authority",
            "refresh_triggers": ["new_official_document", "new_amendment"],
            "invalidation_keys": [contract_id, "inst-001"],
            "expires_at": "2026-11-15T00:00:00Z",
            "withdrawal_rule": "withdraw_on_identity_conflict_or_supersession",
            "estimated_cost": "low",
        },
        "technical_question": RICH_EDITORIAL["central_question"],
        "limitations": RICH_EDITORIAL["cannot_assert"],
        "comparable_peers": [
            _peer(f"{i:02d}", valor)
            for i, valor in enumerate(
                ["4100000.00", "4300000.00", "4500000.00", "3900000.00", "4700000.00", "4400000.00"], start=1
            )
        ],
        "amendments": [
            {"id": "adt-prazo-001", "at": "2024-09-15", "ref": f"{DOE}/adt-prazo-001"},
            {"id": "adt-valor-001", "at": "2024-10-02", "ref": f"{DOE}/adt-valor-001"},
        ],
        "value_changes": [
            {"id": "vc-1", "at": "2024-10-02", "ref": f"{DOE}/adt-valor-001", "from": "4250000.00", "to": "4760000.00"}
        ],
        "term_changes": [{"id": "tc-1", "at": "2024-09-15", "ref": f"{DOE}/adt-prazo-001", "delta_days": 120}],
    }


def case_handoff_ready() -> dict[str, Any]:
    case = rich_base("handoff_ready", "SC-2024-BRU-4411")
    case["documents"][0]["ocr_used"] = True
    case["documents"][0]["ocr_tool"] = "fixture-ocr/0.0"
    case["documents"][0]["ocr_confidence"] = 0.21
    case["documents"][0]["ocr_pages"] = ("9",)
    return case


def case_large_no_insight() -> dict[str, Any]:
    case = rich_base("large_no_insight", "SC-2024-BIG-9999")
    case["values"] = {"valor_original": "180000000.00", "valor_atual": "180000000.00", "moeda": "BRL"}
    case["documents"] = [
        _doc(
            "inst-big",
            "instrument",
            "instrument",
            page="1",
            section="cl.1",
            text="Contrato de grande valor sem aditivos.",
        )
    ]
    case["claims"] = [_claim("c1", "FACT", "Valor 180000000.00 BRL.", ["inst-big"], ["p.1|cl.1"])]
    case["events"] = [_event("e1", "signature", "2024-01-01", "Assinatura.", ["inst-big"], ["p.1"])]
    case["contradictions"] = []
    case["editorial"] = {
        "central_question": "what is the contract value?",
        "theses": ["contrato publico de grande valor"],
        "why_singular": "contrato de grande valor",
        "transferable_utility": "nenhuma",
        "cannot_assert": ["nada alem da ficha"],
    }
    case["technical_question"] = "what is the contract value?"
    case["comparable_peers"] = []
    return case


def case_insufficient_docs() -> dict[str, Any]:
    case = rich_base("insufficient_docs", "SC-2024-THIN-01")
    case["documents"] = [deepcopy(RICH_DOCS[0])]
    case["events"] = [RICH_EVENTS[0]]
    return case


def case_identity_divergent() -> dict[str, Any]:
    case = rich_base("identity_divergent", "SC-2024-SWAP-01")
    case["identity"]["identity_swap"] = True
    case["identity"]["alt_orgao_cnpj"] = "00000000000191"
    case["identity"]["alt_municipio"] = "Joinville"
    return case


def case_value_no_semantic() -> dict[str, Any]:
    case = rich_base("value_no_semantic", "SC-2024-SEM-01")
    case["values"]["valor_semantic"] = "unknown"
    case["values"]["unidade"] = None
    case["values"]["regime"] = None
    case["require_value_semantic"] = True
    case["comparable_peers"] = []
    return case


def case_conflicting_dates() -> dict[str, Any]:
    case = rich_base("conflicting_dates", "SC-2024-DATE-01")
    case["dates"]["conflicts"] = ["2024-02-10", "2024-03-22"]
    case["dates"]["conflict_hidden"] = True
    return case


def case_prazo_additive() -> dict[str, Any]:
    return rich_base("prazo_additive", "SC-2024-PRZ-01")


def case_valor_additive() -> dict[str, Any]:
    return rich_base("valor_additive", "SC-2024-VAL-01")


def case_scope_changed() -> dict[str, Any]:
    case = rich_base("scope_changed", "SC-2024-SCP-01")
    case["documents"].append(
        _doc(
            "adt-escopo-001",
            "amendment_scope",
            "amendment",
            page="1",
            section="art.3",
            text="Exclui drenagem profunda do lote 2 e inclui recape em 1,2 km adicionais.",
            url=f"{DOE}/adt-escopo-001",
        )
    )
    case["events"].append(
        _event(
            "e-escopo",
            "scope_change",
            "2024-08-01",
            "Alteracao de escopo documentada.",
            ["adt-escopo-001"],
            ["p.1|art.3"],
        )
    )
    case["claims"].append(
        _claim(
            "c-escopo",
            "FACT",
            "Escopo alterado: exclusao de drenagem profunda e inclusao de recape.",
            ["adt-escopo-001"],
            ["p.1|art.3"],
        )
    )
    case["scope_changes"] = [{"id": "sc-1", "at": "2024-08-01", "ref": f"{DOE}/adt-escopo-001"}]
    return case


def case_superseded_document() -> dict[str, Any]:
    case = rich_base("superseded_document", "SC-2024-SUP-01")
    old = _doc(
        "doe-000",
        "official_publication",
        "publication",
        page="2",
        section="secao-contratos",
        text="Versao anterior do valor: 4250000.00.",
        url=f"{DOE}/2024-02-11",
        superseded_by="doe-001",
    )
    case["documents"].append(old)
    case["claims"].append(
        _claim(
            "c-old",
            "FACT",
            "Publicacao anterior do valor original.",
            ["doe-000"],
            ["p.2"],
            superseded_by="doe-001",
            conflict="superseded",
        )
    )
    case["events"].append(
        _event("e-old", "publication", "2024-02-11", "Publicacao supersedida.", ["doe-000"], ["p.2"], superseded=True)
    )
    return case


def case_weak_ocr() -> dict[str, Any]:
    case = rich_base("weak_ocr", "SC-2024-OCR-01")
    case["documents"][0]["ocr_used"] = True
    case["documents"][0]["ocr_tool"] = "tesseract/5.fixture"
    case["documents"][0]["ocr_confidence"] = 0.18
    case["documents"][0]["ocr_pages"] = ("9", "10")
    case["documents"][0]["extract_status"] = "weak_ocr"
    case["documents"][0]["text"] = "████ clausula ilegivel ████"
    return case


def case_calculation_replay() -> dict[str, Any]:
    return rich_base("calculation_replay", "SC-2024-CALC-01")


def case_irregularity_inference() -> dict[str, Any]:
    case = rich_base("irregularity_inference", "SC-2024-INF-01")
    case["claims"].append(
        _claim(
            "c-irr",
            "INFERENCE",
            "Diferenca estatistica de valor nao autoriza concluir irregularidade.",
            ["adt-valor-001"],
            ["p.1|art.2"],
            confidence=0.2,
            publication_fit="labeled_inference",
        )
    )
    return case


def case_comparison_no_unit() -> dict[str, Any]:
    case = rich_base("comparison_no_unit", "SC-2024-NOUN-01")
    case["values"]["unidade"] = None
    case["values"]["regime"] = None
    case["values"]["valor_semantic"] = "unknown"
    case["comparable_peers"] = [_peer("11", "4100000.00")]
    return case


def case_valid_comparable() -> dict[str, Any]:
    return rich_base("valid_comparable", "SC-2024-CMP-01")


def case_counter_evidence() -> dict[str, Any]:
    return rich_base("counter_evidence", "SC-2024-CTR-01")


def case_claim_no_locator() -> dict[str, Any]:
    case = rich_base("claim_no_locator", "SC-2024-LOC-01")
    case["claims"].append(_claim("c-bare", "FACT", "Afirmacao sem locator.", ["inst-001"], []))
    return case


def case_duplication_replay() -> dict[str, Any]:
    return rich_base("duplication_replay", "SC-2024-DUP-01")


def case_stable_hash() -> dict[str, Any]:
    return rich_base("stable_hash", "SC-2024-HSH-01")


def case_consumer_import() -> dict[str, Any]:
    return rich_base("consumer_import", "SC-2024-IMP-01")


def case_no_publishable() -> dict[str, Any]:
    return rich_base("no_publishable", "SC-2024-NPB-01")


CASE_BUILDERS = {
    "large_no_insight": case_large_no_insight,
    "insufficient_docs": case_insufficient_docs,
    "identity_divergent": case_identity_divergent,
    "value_no_semantic": case_value_no_semantic,
    "conflicting_dates": case_conflicting_dates,
    "prazo_additive": case_prazo_additive,
    "valor_additive": case_valor_additive,
    "scope_changed": case_scope_changed,
    "superseded_document": case_superseded_document,
    "weak_ocr": case_weak_ocr,
    "calculation_replay": case_calculation_replay,
    "irregularity_inference": case_irregularity_inference,
    "comparison_no_unit": case_comparison_no_unit,
    "valid_comparable": case_valid_comparable,
    "counter_evidence": case_counter_evidence,
    "claim_no_locator": case_claim_no_locator,
    "duplication_replay": case_duplication_replay,
    "stable_hash": case_stable_hash,
    "consumer_import": case_consumer_import,
    "no_publishable": case_no_publishable,
    "handoff_ready": case_handoff_ready,
}


def all_cases() -> list[dict[str, Any]]:
    return [builder() for builder in CASE_BUILDERS.values()]


def fixture_corpus() -> list[dict[str, Any]]:
    return all_cases()
