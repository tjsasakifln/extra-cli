from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scripts.crawl.pncp_contract import ModalidadePNCP, normalize_text

CLASSIFIER_VERSION = "engineering-rules-v1"

_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "CONSTRUCAO_NOVA": ("construcao", "construir", "implantacao", "edificacao nova"),
    "REFORMA": ("reforma", "reformar", "revitalizacao", "restauracao", "recuperacao"),
    "AMPLIACAO": ("ampliacao", "expansao", "acrescimo"),
    "MANUTENCAO_PREDIAL": ("manutencao predial", "manutencao preventiva", "manutencao corretiva"),
    "INFRAESTRUTURA_URBANA": ("infraestrutura urbana", "urbanizacao", "calcada", "acessibilidade"),
    "INFRAESTRUTURA_RODOVIARIA": ("rodovia", "estrada", "sinalizacao viaria", "infraestrutura viaria"),
    "PAVIMENTACAO": ("pavimentacao", "asfalto", "paver", "recapeamento"),
    "DRENAGEM": ("drenagem", "drenagem pluvial", "galeria pluvial"),
    "SANEAMENTO": ("saneamento",),
    "ABASTECIMENTO_DE_AGUA": ("rede de agua", "abastecimento de agua"),
    "ESGOTAMENTO_SANITARIO": ("rede de esgoto", "esgotamento sanitario"),
    "PONTES_E_OBRAS_DE_ARTE": ("ponte", "viaduto", "passarela", "obra de arte"),
    "CONTENCAO_E_GEOTECNIA": ("contencao", "muro de arrimo", "gabiao", "estabilizacao de encosta"),
    "TERRAPLENAGEM": ("terraplenagem",),
    "EDIFICACOES_PUBLICAS": ("escola", "hospital", "unidade de saude", "creche", "ginasio", "praca"),
    "INSTALACOES_ELETRICAS": ("instalacao eletrica", "iluminacao publica", "subestacao", "spda"),
    "INSTALACOES_HIDROSSANITARIAS": ("instalacao hidraulica", "hidrossanitario"),
    "CLIMATIZACAO": ("climatizacao", "ar condicionado", "hvac"),
    "PREVENCAO_CONTRA_INCENDIO": ("ppci", "preventivo contra incendio", "combate a incendio"),
    "PROJETOS_DE_ENGENHARIA": ("projeto executivo", "projeto basico", "projeto estrutural", "servicos de engenharia"),
    "FISCALIZACAO_E_SUPERVISAO": ("fiscalizacao de obra", "supervisao de obra", "gerenciamento de obra"),
    "LAUDOS_E_PERICIAS": ("laudo", "pericia",),
    "TOPOGRAFIA": ("topografia", "levantamento planialtimetrico"),
    "SONDAGEM": ("sondagem",),
    "ENGENHARIA_AMBIENTAL": ("engenharia ambiental", "licenciamento ambiental"),
    "OUTROS_SERVICOS_DE_ENGENHARIA_CIVIL": ("engenharia civil", "obra", "obras"),
}

_STRONG_TERMS = (
    "obra",
    "obras",
    "construcao",
    "reforma",
    "ampliacao",
    "pavimentacao",
    "drenagem",
    "terraplenagem",
    "ponte",
    "rede de agua",
    "rede de esgoto",
    "engenharia civil",
    "servicos de engenharia",
    "projeto executivo",
    "fiscalizacao de obra",
)

_EXCLUDED_TERMS = {
    "engenharia de software": "software_only",
    "engenharia de dados": "software_only",
    "engenharia social": "software_only",
    "engenharia reversa de software": "software_only",
    "licenca de software": "software_only",
    "desenvolvimento de sistemas": "software_only",
    "sistema informatizado": "software_only",
    "manutencao de veiculos": "vehicle_only",
    "equipamento medico": "equipment_only",
}

_MATERIAL_ONLY_TERMS = ("cimento", "brita", "areia", "tinta", "tubos", "cabos", "blocos", "cimento")
_SERVICE_OR_WORK_RESCUE = (
    "execucao",
    "fornecimento de material e mao de obra",
    "mao de obra",
    "prestacao de servicos",
    "instalacao",
    "obra",
    "reforma",
    "construcao",
)


@dataclass
class EngineeringClassification:
    is_engineering: bool
    score: int
    confidence: str
    categories: list[str]
    exclusion_reason: str | None
    reasons: dict[str, Any]


def _collect_texts(record: dict, detail: dict | None, items: list[dict], documents: list[dict]) -> tuple[list[str], list[str]]:
    fields_used: list[str] = []
    texts: list[str] = []

    def add(field_name: str, value: str | None) -> None:
        if value:
            texts.append(normalize_text(value))
            fields_used.append(field_name)

    add("objetoCompra", record.get("objeto_compra") or record.get("objetoCompra"))
    add("informacaoComplementar", record.get("informacao_complementar") or record.get("informacaoComplementar"))
    add("modalidadeNome", record.get("modalidade_nome") or record.get("modalidadeNome"))
    add("nomeUnidade", record.get("unidade_nome") or ((record.get("unidadeOrgao") or {}).get("nomeUnidade")))
    add("orgao", record.get("orgao_razao_social") or ((record.get("orgaoEntidade") or {}).get("razaoSocial")))

    if detail:
        add("detail.objetoCompra", detail.get("objetoCompra"))
        add("detail.informacaoComplementar", detail.get("informacaoComplementar"))

    for item in items:
        add("itens", item.get("descricao"))
        add("itens", item.get("informacaoComplementar"))

    for document in documents:
        add("documentos", document.get("titulo"))
        add("documentos", document.get("tipoDocumentoNome"))

    return texts, fields_used


def classify_engineering(
    record: dict,
    *,
    detail: dict | None = None,
    items: list[dict] | None = None,
    documents: list[dict] | None = None,
) -> EngineeringClassification:
    items = items or []
    documents = documents or []
    texts, fields_used = _collect_texts(record, detail, items, documents)
    joined = " ".join(texts)

    matched_terms: list[str] = []
    excluded_terms: list[str] = []
    categories: list[str] = []
    score = 0
    exclusion_reason: str | None = None

    for term, reason in _EXCLUDED_TERMS.items():
        if term in joined:
            excluded_terms.append(term)
            exclusion_reason = reason

    rescue_hit = any(term in joined for term in _SERVICE_OR_WORK_RESCUE)
    if excluded_terms and not rescue_hit:
        return EngineeringClassification(
            is_engineering=False,
            score=0,
            confidence="nao_relacionado",
            categories=[],
            exclusion_reason=exclusion_reason,
            reasons={
                "matched_terms": [],
                "excluded_terms": excluded_terms,
                "fields_used": fields_used,
                "category": [],
                "classifier_version": CLASSIFIER_VERSION,
            },
        )

    for category, terms in _CATEGORY_TERMS.items():
        category_hits = [term for term in terms if term in joined]
        if category_hits:
            categories.append(category)
            matched_terms.extend(category_hits)
            score += 16 if category_hits[0] in _STRONG_TERMS else 10

    unique_strong_hits = [term for term in _STRONG_TERMS if term in joined]
    score += min(30, len(unique_strong_hits) * 8)

    if items:
        score += 12
    if documents:
        score += 4

    modalidade_id = record.get("modalidade_id") or record.get("modalidadeId")
    if modalidade_id in {
        ModalidadePNCP.CONCORRENCIA_ELETRONICA,
        ModalidadePNCP.CONCORRENCIA_PRESENCIAL,
        ModalidadePNCP.PREGAO_ELETRONICO,
        ModalidadePNCP.PREGAO_PRESENCIAL,
        ModalidadePNCP.DISPENSA,
        ModalidadePNCP.INEXIGIBILIDADE,
        ModalidadePNCP.CREDENCIAMENTO,
        ModalidadePNCP.PRE_QUALIFICACAO,
    }:
        score += 4

    value = record.get("valor_total_estimado") or 0
    try:
        value_num = float(value)
    except (TypeError, ValueError):
        value_num = 0.0
    if value_num >= 1_000_000:
        score += 8
    elif value_num >= 100_000:
        score += 4

    material_only = any(term in joined for term in _MATERIAL_ONLY_TERMS) and not rescue_hit
    if material_only and score < 60:
        exclusion_reason = "material_isolado"
        score = min(score, 25)

    score = max(0, min(100, score))
    categories = sorted(set(categories))
    matched_terms = sorted(set(matched_terms))

    if score >= 80 and categories and len(matched_terms) >= 2:
        is_engineering = True
        confidence = "engenharia_confirmada"
    elif score >= 60 and categories:
        is_engineering = True
        confidence = "engenharia_provavel"
    elif score >= 40 and categories:
        is_engineering = False
        confidence = "revisao_necessaria"
    else:
        is_engineering = False
        confidence = "nao_relacionado"

    return EngineeringClassification(
        is_engineering=is_engineering,
        score=score,
        confidence=confidence,
        categories=categories,
        exclusion_reason=exclusion_reason,
        reasons={
            "matched_terms": matched_terms,
            "excluded_terms": excluded_terms,
            "fields_used": sorted(set(fields_used)),
            "category": categories,
            "classifier_version": CLASSIFIER_VERSION,
        },
    )


def classification_to_record(classification: EngineeringClassification) -> dict[str, Any]:
    payload = asdict(classification)
    payload["classifier_version"] = CLASSIFIER_VERSION
    return payload
