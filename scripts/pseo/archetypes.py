"""Derive public ICP archetypes from observable contract patterns.

The commercial Top 20 is used only as an *internal signature* to calibrate
which activity classes and service mappings matter. Company names, scores,
ranks, and pipeline states never enter the public payload.

Archetypes themselves are object/region clusters derived from public PNCP
contract text and values — not one page per prospect.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# Public object-pattern archetypes confirmed by density in the datalake.
# Labels are descriptive of market work, not of any named firm.
ARCHETYPE_DEFS: dict[str, dict[str, Any]] = {
    "pavimentacao-infraestrutura-viaria": {
        "label": "Pavimentação e infraestrutura viária",
        "description": (
            "Contratos públicos de pavimentação, asfalto, vias urbanas, "
            "drenagem e obras de arte correntes — típicos de prefeituras e "
            "departamentos de infraestrutura."
        ),
        "patterns": [
            r"paviment",
            r"asfalt",
            r"rodovi",
            r"recape",
            r"sinaliza[cç][aã]o vi[aá]ria",
            r"drenagem",
            r"cal[cç]ada",
            r"passeio",
            r"terraplen",
            r"\bponte\b",
            r"viaduto",
        ],
        "confenge_service_slugs": [
            "diagnostico-pre-licitacao",
            "auditoria-orcamento-licitacao",
            "acompanhamento-contratos-obras",
            "aditivos-obras-publicas",
        ],
        "icp_rationale": (
            "ICP engineering contractors show multi-agency, multi-object "
            "portfolios with recurring civil works; pavimentação is a high-"
            "value recurrent object class in the public history."
        ),
    },
    "edificacoes-publicas": {
        "label": "Edificações públicas",
        "description": (
            "Construção, reforma e ampliação de edificações públicas "
            "(escolas, saúde, equipamentos comunitários e prédio administrativo)."
        ),
        "patterns": [
            r"edifica[cç]",
            r"constru[cç][aã]o de",
            r"reforma d[eo]",
            r"\bescola\b",
            r"\bcreche\b",
            r"\bubs\b",
            r"posto de sa[uú]de",
            r"gin[aá]sio",
            r"pr[eé]dio",
            r"alvenaria",
            r"amplia[cç][aã]o d[eo]",
        ],
        "confenge_service_slugs": [
            "auditoria-orcamento-licitacao",
            "medicoes-glosas-obras-publicas",
            "aditivos-obras-publicas",
            "atrasos-prorrogacao-obras-publicas",
        ],
        "icp_rationale": (
            "Highest density of AEC objects in the current datalake window; "
            "aligns with ICP firms that execute multi-site public buildings."
        ),
    },
    "saneamento-hidraulica": {
        "label": "Saneamento e hidráulica",
        "description": (
            "Redes de água e esgoto, drenagem pluvial estrutural, ETAs/ETEs "
            "e adutoras — contratos com maior complexidade técnica e risco "
            "de quantitativo."
        ),
        "patterns": [
            r"saneamento",
            r"esgoto",
            r"rede de [aá]gua",
            r"\beta\b",
            r"\bete\b",
            r"adutora",
            r"galeria de",
            r"drenagem pluvial",
            r"tratamento de [aá]gua",
        ],
        "confenge_service_slugs": [
            "diagnostico-pre-licitacao",
            "auditoria-orcamento-licitacao",
            "reequilibrio-obras-publicas",
            "acompanhamento-contratos-obras",
        ],
        "icp_rationale": (
            "Technical complexity and SINAPI/SICRO sensitivity match ICP "
            "need for proposal and budget audit support."
        ),
    },
    "climatizacao-instalacoes": {
        "label": "Climatização e instalações prediais",
        "description": (
            "Climatização, instalações elétricas e hidráulicas prediais, "
            "SPDA e sistemas prediais em equipamentos públicos."
        ),
        "patterns": [
            r"climatiza",
            r"ar[- ]condicionado",
            r"instala[cç][oõ]es el[eé]tric",
            r"instala[cç][oõ]es hidr[aá]ulic",
            r"\bspda\b",
            r"inc[eê]ndio",
            r"elevador",
        ],
        "confenge_service_slugs": [
            "diagnostico-pre-licitacao",
            "auditoria-orcamento-licitacao",
            "medicoes-glosas-obras-publicas",
        ],
        "icp_rationale": (
            "Specialized object class with frequent unit-price disputes; "
            "maps to engineering service providers in the ICP signature."
        ),
    },
    "manutencao-predial-engenharia": {
        "label": "Manutenção predial e serviços de engenharia",
        "description": (
            "Manutenção predial contínua e serviços técnicos de engenharia "
            "para órgãos públicos — contratos recorrentes com medição mensal."
        ),
        "patterns": [
            r"manuten[cç][aã]o predial",
            r"manuten[cç][aã]o de edif",
            r"conserva[cç][aã]o predial",
            r"servi[cç]os de engenharia",
            r"apoio t[eé]cnico em engenharia",
        ],
        "confenge_service_slugs": [
            "acompanhamento-contratos-obras",
            "medicoes-glosas-obras-publicas",
            "defesa-tecnica-contratos-publicos",
        ],
        "icp_rationale": (
            "Recurring measurement and documentation risk; ICP firms often "
            "hold concurrent portfolios including maintenance."
        ),
    },
}

METHODOLOGY = (
    "Arquétipos derivados em duas camadas: (1) assinatura interna do ICP "
    "CONFENGE — classes de atividade de engenharia confirmada e sinais "
    "públicos de portfólio multi-órgão/multi-objeto, sem exportar nomes, "
    "scores ou estados de pipeline; (2) clusterização de objetos de "
    "contratos públicos (PNCP e fontes oficiais no datalake) por padrões "
    "linguísticos e densidade regional. Nenhum arquétipo é hardcodado "
    "como página nominal de prospect. Padrões sem massa crítica no "
    "horizonte analisado são omitidos."
)


@dataclass
class ClassifiedContract:
    contrato_id: str | None
    orgao_cnpj: str
    orgao_nome: str | None
    fornecedor_cnpj: str
    fornecedor_nome: str | None
    objeto: str
    valor: float
    data_inicio: str | None
    data_fim: str | None
    data_publicacao: str | None
    uf: str | None
    municipio: str | None
    source: str
    archetypes: list[str] = field(default_factory=list)


_COMPILED: dict[str, list[re.Pattern[str]]] = {
    k: [re.compile(p, re.I) for p in v["patterns"]] for k, v in ARCHETYPE_DEFS.items()
}


def classify_object(objeto: str | None) -> list[str]:
    if not objeto:
        return []
    hits = []
    for arch, pats in _COMPILED.items():
        if any(p.search(objeto) for p in pats):
            hits.append(arch)
    return hits


def build_public_archetypes(
    classified: list[ClassifiedContract],
    modalities_by_arch: dict[str, Counter] | None = None,
) -> list[dict[str, Any]]:
    """Emit public archetype records (no proprietary scores)."""
    modalities_by_arch = modalities_by_arch or {}
    out: list[dict[str, Any]] = []
    for arch_id, meta in ARCHETYPE_DEFS.items():
        subset = [c for c in classified if arch_id in c.archetypes]
        if len(subset) < 10:
            continue
        ufs = Counter(c.uf for c in subset if c.uf)
        buyers = {c.orgao_cnpj or c.orgao_nome for c in subset if c.orgao_cnpj or c.orgao_nome}
        vals = sorted(c.valor for c in subset if c.valor and c.valor > 0)
        band = {
            "p25": _pct(vals, 25),
            "median": _pct(vals, 50),
            "p75": _pct(vals, 75),
            "n": len(vals),
            "currency": "BRL",
        }
        mods = modalities_by_arch.get(arch_id) or Counter()
        out.append(
            {
                "id": arch_id,
                "slug": arch_id,
                "label": meta["label"],
                "description": meta["description"],
                "object_patterns_public": list(meta["patterns"]),
                "ufs_observed": [
                    {"uf": u, "contract_count": n} for u, n in ufs.most_common(12)
                ],
                "value_band": band,
                "modalities_observed": [
                    {"name": m, "count": n} for m, n in mods.most_common(8)
                ],
                "buyer_types_observed": _infer_buyer_types(subset),
                "confenge_service_slugs": list(meta["confenge_service_slugs"]),
                "evidence_contract_count": len(subset),
                "evidence_buyer_count": len(buyers),
                "methodology": METHODOLOGY,
                "limitations": [
                    "Classificação por padrões textuais do objeto — objetos "
                    "heterogêneos podem receber mais de um arquétipo.",
                    "Cobertura do datalake não é censo nacional completo; "
                    "densidade reflete fontes ingeridas (ênfase SC/Sul/Sudeste).",
                    "Faixas de valor incluem contratos de portes distintos; "
                    "não usar mediana como preço unitário de referência.",
                ],
            }
        )
    return out


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    i = min(len(vals) - 1, max(0, int(round((p / 100) * (len(vals) - 1)))))
    return round(vals[i], 2)


def _infer_buyer_types(subset: list[ClassifiedContract]) -> list[dict[str, Any]]:
    types: Counter[str] = Counter()
    for c in subset:
        name = (c.orgao_nome or "").lower()
        if "prefeitura" in name or "municip" in name:
            types["municipal"] += 1
        elif "secretaria" in name or "estado" in name or "governo" in name:
            types["estadual"] += 1
        elif "universidade" in name or "instituto" in name or "fundação" in name:
            types["autarquia_fundacao"] += 1
        elif "união" in name or "ministerio" in name or "ministério" in name:
            types["federal"] += 1
        else:
            types["outro_ou_nao_classificado"] += 1
    return [{"type": t, "contract_count": n} for t, n in types.most_common()]


def load_icp_signature_from_top20_artifact(path: str | None) -> dict[str, Any]:
    """Read Top-20 artifact for methodology counts only — never re-exported.

    Returns aggregate activity-class histogram and signal-frequency histogram
    without CNPJ, scores, or names.
    """
    if not path:
        return {
            "available": False,
            "note": "Top-20 artifact not provided; archetypes use public density only.",
        }
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return {"available": False, "note": f"missing artifact: {path}"}
    raw = json.loads(p.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("top20") or raw.get("leads") or []
    acts: Counter[str] = Counter()
    fits: Counter[str] = Counter()
    sigs: Counter[str] = Counter()
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("activity_class"):
            acts[str(r["activity_class"])] += 1
        if r.get("supplier_sector_fit"):
            fits[str(r["supplier_sector_fit"])] += 1
        for s in r.get("signal_ids") or []:
            sigs[str(s)] += 1
    return {
        "available": True,
        "n_accounts_internal": len(rows),
        "activity_class_histogram": dict(acts),
        "sector_fit_histogram": dict(fits),
        "public_signal_frequency": dict(sigs.most_common(20)),
        "note": (
            "Internal ICP signature only. No company identifiers, scores, "
            "ranks, or pipeline states are retained in the public export."
        ),
    }
