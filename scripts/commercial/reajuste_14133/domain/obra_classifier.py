"""Hybrid construction / civil engineering object classifier.

Combines:
- strong engineering phrases (Layer A)
- weak tokens + positive context (Layer B)
- negative vocabulary (supply-only, continuous labor, IP consultancy)
- reuse of commercial_leads.contract_relevance and coverage.sector_engineering

Never qualifies on a single weak keyword alone.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

RULE_VERSION = "obra-classifier-v2"

# Construction execution — strong positive
STRONG_PHRASES: tuple[str, ...] = (
    "obra de engenharia",
    "execucao de obra",
    "execucao de obras",
    "execucao das obras",
    "construcao civil",
    "construcao de edificio",
    "construcao de predio",
    "construcao de escola",
    "construcao de ponte",
    "construcao e implantacao",
    "pavimentacao",
    "pavimentacao asfaltica",
    "drenagem urbana",
    "drenagem",
    "saneamento",
    "terraplenagem",
    "terraplanagem",
    "fundacao",
    "edificacao",
    "reforma predial",
    "reforma e ampliacao",
    "recuperacao estrutural",
    "empreitada",
    "infraestrutura viaria",
    "infraestrutura urbana",
    "infraestrutura de saneamento",
    "obras de infraestrutura",
    "obras e servicos de engenharia",
    "servicos de engenharia",
    "servico de engenharia",
    "concreto armado",
    "alvenaria estrutural",
    "estruturas metalicas",
    "ponte",
    "viaduto",
    "passarela",
    "barragem",
    "adutora",
    "estacao de tratamento",
    "rede de agua",
    "rede de esgoto",
    "rede coletora",
    "asfalto",
    "asfaltica",
    "rodovia",
    "estrada vicinal",
    "muro de arrimo",
    "contencao",
    "instalacoes prediais",
    "instalacoes hidraulicas",
    "instalacoes eletricas prediais",
    "urbanizacao",
    "revitalizacao de imovel",
    "reabilitacao funcional",
    "ampliacao de edificio",
    "manutencao rodoviaria",
    "conservacao rodoviaria",
    "recuperacao de rodovia",
    "obra para construcao",
    "execucao de servicos de engenharia",
)

STRONG_TOKENS: tuple[str, ...] = (
    "pavimentacao",
    "terraplenagem",
    "terraplanagem",
    "saneamento",
    "drenagem",
    "edificacao",
    "fundacao",
    "empreitada",
    "construtora",
    "engenharia",
    "viaduto",
    "barragem",
    "adutora",
)

# Weak: need positive engineering context
WEAK_TOKENS: tuple[str, ...] = (
    "obra",
    "obras",
    "reforma",
    "ampliacao",
    "construcao",
    "manutencao",
    "recuperacao",
    "servico",
    "servicos",
    "projeto",
)

POSITIVE_CONTEXT: tuple[str, ...] = (
    "engenharia",
    "engenheir",
    "construcao",
    "civil",
    "estrutural",
    "predial",
    "ponte",
    "viaduto",
    "edificio",
    "edificacao",
    "paviment",
    "saneamento",
    "drenagem",
    "terraplenagem",
    "obra publica",
    "obras publicas",
    "fundacao",
    "hidraulica",
    "instalacoes prediais",
    "arquitetura",
    "rodovia",
    "asfalt",
    "concreto",
    "alvenaria",
)

# Hard negatives — supply, continuous labor, pure IP, non-construction
NEGATIVE: tuple[str, ...] = (
    "fornecimento de materiais",
    "aquisicao de materiais",
    "materiais de construcao",
    "materiais para construcao",
    "aquisicao de cimento",
    "fornecimento de cimento",
    "locacao de maquinas",
    "locacao de equipamentos",
    "locacao de guindaste",
    "locacao de veiculos",
    "locacao de veiculo",
    "veiculos especiais",
    "aluguel de veiculos",
    "fornecimento de gas",
    "gas natural canalizado",
    "fornecimento de agua canalizada",
    "software",
    "licenca de uso",
    "licenciamento de software",
    "sistema de gestao",
    "sistemas de gestao",
    "gestao de obras",  # software de gestão ≠ execução
    "tecnologia da informacao",
    "infraestrutura de ti",
    "desenvolvimento de sistema",
    "implantacao de software",
    "solucao de software",
    "vigilancia",
    "seguranca patrimonial",
    "limpeza predial",
    "conservacao e limpeza",
    "terceirizacao",
    "mao de obra exclusiva",
    "dedicacao exclusiva de mao de obra",
    "medicamento",
    "medicamentos",
    "lisdexanfetamina",
    "farmaceutic",
    "principio ativo",
    "generos alimenticios",
    "merenda",
    "combustivel",
    "uniforme",
    "publicidade",
    "engenharia clinica",
    "laudo sem execucao",
    "consultoria intelectual",
    "elaboracao de projeto basico sem",
    "elaboracao de estudos tecnicos",
    "projeto cultural",
    "direitos de exibicao",
    "documentario",
    "servicos contabeis",
    "contabilidade",
    "telecomunicacoes",
    "barbearia",
    "cabeleireiro",
    # Aggregate / mining without obra execution
    "fornecimento de brita",
    "fornecimento de agregado",
    "fornecimento de areia",
    "fornecimento de pedra",
    "mineracao de areia",
    # Sector false positives (regression pack)
    "motor aeronautico",
    "motores aeronauticos",
    "aeronautic",
    "suporte logistico de motores",
    "componente de aeronave",
    "aeronave",
    "ppp de operacao",
    "parceria publico privada",
    "concessao hospitalar",
    "concessao de hospital",
    "concessao de longo prazo",
    "operacao e manutencao de escolas",
    "manutencao de equipamento",
    "manutencao de equipamentos",
    "manutencao de usina",
    "equipamento de usina",
    "sem execucao de obra",
    "sem execucao material",
    "sem execucao das obras",
    # Concessão de serviço público contínuo ≠ empreitada
    "concessao comum",
    "concessao de servico",
    "concessao de agua",
    "concessao de esgoto",
    "concessao de saneamento",
    "outorga de concessao",
    "servico publico de abastecimento",
    "distribuicao de agua",
    "abastecimento de agua",
    "servicos de agua e esgoto",
    "operacao de sistema de esgoto",
)

# Pure intellectual services without material execution
IP_ONLY: tuple[str, ...] = (
    "elaboracao de projeto",
    "projeto executivo",
    "projeto basico",
    "projeto arquitetonico",
    "consultoria em engenharia",
    "fiscalizacao de obra",
    "supervisao de obra",
    "laudo tecnico",
    "sondagem",
    "levantamento topografico",
    "orcamento de obra",
)

# Material obra maintenance / engineering-by-scope (in scope)
ENGINEERING_MAINTENANCE: tuple[str, ...] = (
    "manutencao rodoviaria",
    "manutencao de engenharia",
    "manutencao predial com execucao",
    "recuperacao de pavimento",
    "conservacao rodoviaria",
    "reabilitacao funcional",
)

WORK_CATEGORY_MAP: list[tuple[str, tuple[str, ...]]] = [
    ("pavimentacao_rodoviaria", ("paviment", "asfalt", "rodovia", "estrada", "capeamento")),
    ("saneamento_redes", ("saneamento", "esgoto", "adutora", "rede de agua", "rede coletora", "estacao de tratamento")),
    ("drenagem_urbanizacao", ("drenagem", "urbaniza", "galeria pluvial", "meio fio")),
    ("edificacoes", ("edific", "predio", "escola", "reforma", "ampliacao", "alvenaria", "concreto")),
    ("pontes_estruturas", ("ponte", "viaduto", "passarela", "estrutura metal")),
    ("terraplenagem_contencao", ("terraplen", "terraplan", "contenc", "arrimo", "gabiao")),
    ("instalacoes_prediais", ("instalacoes prediais", "instalacoes hidraul", "instalacoes eletr")),
    ("obras_infraestrutura", ("infraestrutura", "empreitada", "obra de engenharia", "obras e servicos")),
]


@dataclass
class ConstructionClassification:
    is_construction: bool
    confidence: float
    category: str
    strong_hits: list[str] = field(default_factory=list)
    weak_hits: list[str] = field(default_factory=list)
    positive_context: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    rule_version: str = RULE_VERSION
    normalized_object: str = ""
    method: str = "hybrid_rules"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s/.-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _hits(norm: str, patterns: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for p in patterns:
        if p in norm and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _category(norm: str, strong: list[str], weak: list[str], pos: list[str]) -> str:
    blob = " ".join([norm] + strong + weak + pos)
    for cat, keys in WORK_CATEGORY_MAP:
        if any(k in blob for k in keys):
            return cat
    if strong or (weak and pos):
        return "obras_engenharia_geral"
    return "nao_construcao"


# Company-name tokens that NEVER prove sector by themselves
_NAME_ONLY_NOT_SECTOR = (
    "betha",  # software vendor name
    "localiza",  # vehicle rental brand
)


def classify_construction(
    objeto: str | None,
    *,
    object_code: str | None = None,
    allow_pure_ip: bool = False,
    razao_social: str | None = None,
    cnae: str | None = None,
    supplier_type: str | None = None,
    remuneracao_natureza: str | None = None,
    document_text: str | None = None,
) -> ConstructionClassification:
    """Classify whether the object is construction / engineering-by-scope work.

    ``allow_pure_ip=False`` excludes pure design/fiscalization without material
    execution (CONFENGE campaign focuses on construction contractors).

    Company trade name alone is NEVER sector proof. Cross-check object,
    optional CNAE, documents, supplier type and remuneration nature.
    """
    # Material evidence = contract object + optional official docs (not company name)
    material_blob = " ".join(
        filter(None, [objeto or "", document_text or "", remuneracao_natureza or ""])
    )
    norm = normalize_text(material_blob)
    name_norm = normalize_text(razao_social)
    cnae_norm = normalize_text(cnae)
    if not norm:
        return ConstructionClassification(
            is_construction=False,
            confidence=0.0,
            category="nao_construcao",
            reason_codes=["empty_object"],
            normalized_object="",
        )

    # Explicit name-brand false positives when object is non-obra
    if name_norm:
        if "betha" in name_norm and any(
            t in norm for t in ("software", "sistema", "licenc", "informatica", "ti ")
        ):
            return ConstructionClassification(
                is_construction=False,
                confidence=0.0,
                category="nao_construcao",
                reason_codes=["software_vendor_betha_regression"],
                negative_hits=["betha_software"],
                normalized_object=norm[:600],
            )
        if "localiza" in name_norm and any(
            t in norm for t in ("veiculo", "locacao", "aluguel", "frota")
        ):
            return ConstructionClassification(
                is_construction=False,
                confidence=0.0,
                category="nao_construcao",
                reason_codes=["vehicle_rental_localiza_regression"],
                negative_hits=["localiza_veiculos"],
                normalized_object=norm[:600],
            )

    # CNAE hard excludes (software, vehicle rental, pharma, mining-only)
    if cnae_norm:
        soft_cnae = any(
            x in cnae_norm
            for x in (
                "6201",
                "6202",
                "6203",
                "6204",  # software/TI
                "6311",
                "6319",
                "7711",
                "7719",  # vehicle rental
                "2121",
                "2122",
                "4644",  # pharma
            )
        )
        # only hard-exclude when object also lacks material obra language
        if soft_cnae and not any(
            t in norm
            for t in (
                "execucao de obra",
                "execucao de obras",
                "empreitada",
                "pavimentacao",
                "obra de engenharia",
            )
        ):
            return ConstructionClassification(
                is_construction=False,
                confidence=0.0,
                category="nao_construcao",
                reason_codes=["cnae_non_construction_without_material_obra"],
                negative_hits=[cnae_norm[:40]],
                normalized_object=norm[:600],
            )

    # Supplier type hints
    st = normalize_text(supplier_type)
    if st and any(t in st for t in ("software", "locadora", "farmaceut", "consultoria pura")):
        if not any(t in norm for t in ("execucao de obra", "empreitada", "pavimentacao")):
            return ConstructionClassification(
                is_construction=False,
                confidence=0.0,
                category="nao_construcao",
                reason_codes=["supplier_type_non_obra"],
                normalized_object=norm[:600],
            )

    strong = _hits(norm, STRONG_PHRASES) + _hits(norm, STRONG_TOKENS)
    # de-dupe preserve order
    seen: set[str] = set()
    strong_u: list[str] = []
    for h in strong:
        if h not in seen:
            seen.add(h)
            strong_u.append(h)
    strong = strong_u

    weak = _hits(norm, WEAK_TOKENS)
    pos = _hits(norm, POSITIVE_CONTEXT)
    neg = _hits(norm, NEGATIVE)
    ip_only = _hits(norm, IP_ONLY)
    eng_maint = _hits(norm, ENGINEERING_MAINTENANCE)

    # Supply-only materials/equipment: hard exclude even if "construção" appears
    supply_only = _hits(norm, (
        "fornecimento de materiais",
        "aquisicao de materiais",
        "materiais de construcao",
        "materiais para construcao",
        "aquisicao de cimento",
        "fornecimento de cimento",
        "locacao de maquinas",
        "locacao de equipamentos",
    ))
    if supply_only and not any(
        x in norm
        for x in (
            "execucao de obra",
            "execucao de obras",
            "empreitada",
            "obra de engenharia",
            "servicos de engenharia",
        )
    ):
        return ConstructionClassification(
            is_construction=False,
            confidence=0.0,
            category="nao_construcao",
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_hits=neg + supply_only,
            reason_codes=["materials_or_rental_supply_only"],
            normalized_object=norm[:600],
        )

    # Hard negative supply/labor without construction execution language
    hard_neg = bool(neg) and not any(
        x in norm
        for x in (
            "execucao de obra",
            "execucao de obras",
            "empreitada",
            "pavimentacao",
            "obra de engenharia",
            "servicos de engenharia",
        )
    )
    if hard_neg and not eng_maint:
        return ConstructionClassification(
            is_construction=False,
            confidence=0.0,
            category="nao_construcao",
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_hits=neg,
            reason_codes=["negative_vocabulary"],
            normalized_object=norm[:600],
        )

    # Explicit "sem execução" / PPP / concession / aircraft / equipment maintenance
    sector_fp = _hits(
        norm,
        (
            "sem execucao de obra",
            "sem execucao material",
            "sem execucao das obras",
            "parceria publico privada",
            "ppp de operacao",
            "concessao hospitalar",
            "concessao de hospital",
            "concessao de longo prazo",
            "operacao e manutencao de escolas",
            "manutencao de equipamento",
            "manutencao de equipamentos",
            "manutencao de usina",
            "motor aeronautico",
            "motores aeronauticos",
            "suporte logistico de motores",
            "aeronave",
            "licenciamento de software",
            "software de gestao",
            "licenca de uso de software",
            "implantacao de software",
            "solucao de software",
            "lisdexanfetamina",
            "medicamento",
            "medicamentos",
            "locacao de veiculos",
            "veiculos especiais",
            "fornecimento de brita",
            "fornecimento de agregado",
            "concessao comum",
            "concessao de servico",
            "concessao de agua",
            "concessao de esgoto",
            "concessao de saneamento",
            "outorga de concessao",
            "abastecimento de agua",
            "distribuicao de agua",
            "servicos de agua e esgoto",
            "modelagem bim sem execucao",
            "consultoria bim",
            # Cartography / survey / remote sensing without material obra
            "aerolevantamento",
            "fotogrametrico",
            "fotogrametria",
            "perfilamento a laser",
            "perfilamento laser",
            "lidar",
            "base cartografica",
            "engenharia cartografica",
            "mapeamento cartografico",
            "levantamento aerofotogrametrico",
        ),
    )
    # software + gestão de obras / engenharia (not material execution)
    if ("software" in norm or "licenc" in norm) and (
        "gestao de obra" in norm
        or "gestao de obras" in norm
        or "engenharia" in norm
        or "sistema" in norm
    ):
        sector_fp = list(sector_fp) + ["software_gestao_obras"]
    # mining / aggregate supply without material obra
    if any(t in norm for t in ("brita", "agregado", "mineracao")) and not any(
        t in norm for t in ("execucao de obra", "empreitada", "pavimentacao", "construcao de")
    ):
        sector_fp = list(sector_fp) + ["aggregate_or_mining_without_obra"]
    # BIM / consultoria consortia without material execution
    if ("bim" in norm or "consultoria" in norm) and not any(
        t in norm for t in ("execucao de obra", "empreitada", "execucao de obras")
    ):
        if "consultoria" in norm or "modelagem" in norm:
            sector_fp = list(sector_fp) + ["consultancy_or_bim_without_obra"]
    # concessionária de água/esgoto (nome ou objeto)
    if re.search(r"\baguas?\s+de\b|\bcompanhia\s+de\s+agua\b|\bsaneamento\s+de\b", norm) and (
        "concess" in norm or "servico publico" in norm or "distribuicao" in norm
    ):
        sector_fp = list(sector_fp) + ["concessao_agua_esgoto"]
    if "concessao" in norm and any(
        x in norm for x in ("agua", "esgoto", "saneamento", "abastecimento", "servico publico")
    ):
        sector_fp = list(sector_fp) + ["concessao_servico_publico"]
    # Cartography / LiDAR / photogrammetry without material civil obra
    carto_hits = _hits(
        norm,
        (
            "aerolevantamento",
            "fotogrametric",
            "fotogrametria",
            "perfilamento a laser",
            "perfilamento laser",
            "lidar",
            "base cartografica",
            "engenharia cartografica",
            "mapeamento cartografico",
            "levantamento aerofotogrametrico",
            "cartografica",
        ),
    )
    if carto_hits and not any(
        t in norm
        for t in (
            "execucao de obra",
            "execucao de obras",
            "empreitada",
            "pavimentacao",
            "construcao de",
            "recuperacao de rodovia",
            "ponte",
            "edificacao",
            "obra de engenharia civil",
        )
    ):
        sector_fp = list(sector_fp) + carto_hits + ["cartography_survey_without_material_obra"]
    if sector_fp:
        return ConstructionClassification(
            is_construction=False,
            confidence=0.0,
            category="nao_construcao",
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_hits=neg + sector_fp,
            reason_codes=["sector_false_positive_regression"],
            normalized_object=norm[:600],
        )

    # Pure IP consultancy without material works
    if ip_only and not eng_maint and not allow_pure_ip:
        # "sem execução" or negated execution must not count as material_exec
        negated_exec = bool(
            re.search(r"sem\s+execuc", norm)
            or re.search(r"nao\s+inclui\s+execuc", norm)
            or re.search(r"exclu[ií]da?\s+a\s+execuc", norm)
        )
        material_exec = (not negated_exec) and any(
            t in norm
            for t in (
                "execucao de obra",
                "execucao de obras",
                "execucao das obras",
                "empreitada",
                "construcao de",
                "paviment",
                "reforma e ampliacao",
            )
        )
        if not material_exec:
            return ConstructionClassification(
                is_construction=False,
                confidence=0.15,
                category="servico_intelectual",
                strong_hits=strong,
                weak_hits=weak,
                positive_context=pos,
                negative_hits=ip_only,
                reason_codes=["intellectual_service_without_material_execution"],
                normalized_object=norm[:600],
            )

    # Equipment maintenance with engineering vocabulary (not predial/rodoviária)
    if re.search(r"manutencao\s+de\s+equipamento", norm) and not eng_maint:
        return ConstructionClassification(
            is_construction=False,
            confidence=0.0,
            category="nao_construcao",
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_hits=["manutencao_equipamento"],
            reason_codes=["equipment_maintenance_not_obra"],
            normalized_object=norm[:600],
        )

    if strong or eng_maint:
        conf = min(1.0, 0.72 + 0.04 * len(strong) + (0.1 if eng_maint else 0.0))
        cat = _category(norm, strong, weak, pos)
        return ConstructionClassification(
            is_construction=True,
            confidence=conf,
            category=cat,
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_hits=neg,
            reason_codes=["strong_engineering_layer"],
            normalized_object=norm[:600],
        )

    if weak and pos:
        # "construcao" as weak + context can pass; lone "obra" with engineering context
        return ConstructionClassification(
            is_construction=True,
            confidence=0.55 + 0.05 * min(3, len(pos)),
            category=_category(norm, strong, weak, pos),
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_hits=neg,
            reason_codes=["weak_with_positive_context"],
            normalized_object=norm[:600],
        )

    if weak and not pos:
        return ConstructionClassification(
            is_construction=False,
            confidence=0.1,
            category="nao_construcao",
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_hits=neg,
            reason_codes=["weak_token_alone"],
            normalized_object=norm[:600],
        )

    # Optional object code signal (never sole basis for HOT)
    if object_code and str(object_code).strip():
        return ConstructionClassification(
            is_construction=False,
            confidence=0.2,
            category="codigo_sem_texto",
            reason_codes=["object_code_only_insufficient"],
            normalized_object=norm[:600],
        )

    return ConstructionClassification(
        is_construction=False,
        confidence=0.0,
        category="nao_construcao",
        reason_codes=["no_engineering_signal"],
        normalized_object=norm[:600],
    )
