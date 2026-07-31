"""Multi-layer AEC taxonomy classifier (precision-first for indexable pages).

Classes:
  aec_confirmed | aec_probable | non_aec | ambiguous | insufficient_context

Only aec_confirmed feeds indexable market/price/competition aggregates.
Broad inclusive regex alone is never enough for aec_confirmed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Negative patterns: force non_aec or block false positives
# ---------------------------------------------------------------------------
NEGATIVE_STRONG: list[tuple[str, str]] = [
    (r"\bloca[cç][aã]o\s+de\s+(im[oó]vel|sala|pr[eé]dio|espa[cç]o|galp[aã]o)", "locacao_imovel"),
    (r"\baluguel\s+de\s+(im[oó]vel|sala|pr[eé]dio)", "aluguel_imovel"),
    (r"\bcleaning\b|\blimpeza\s+(e\s+)?conserva|\bhigieni[zs]a[cç]", "limpeza"),
    (r"\bcopas?\s+e\s+cozinha\b|\brefei[cç][aã]o\s+coletiv", "alimentacao"),
    (r"\bcredenciamento\s+de\s+(escolas?|institui[cç]|fornecedor|empresas?)", "credenciamento_escolas"),
    (r"\b[oô]nibus\b|\bmicro[oô]nibus\b|\bvan\s+escolar\b|\btransporte\s+escolar\b", "onibus_transporte"),
    (r"\bve[ií]culo\s+rodovi[aá]rio\b|\bfrota\s+rodovi", "veiculo_rodoviario"),
    (r"\baquisi[cç][aã]o\s+de\s+(material|materiais|equipamento|medicamento|g[eê]nero|ferramentas?)", "aquisicao_material"),
    (r"\bfornecimento\s+de\s+(material|materiais|medicamento|g[eê]nero\s+aliment|ferramentas?)", "fornecimento_material"),
    (r"\bcompra\s+de\s+(material|materiais|medicamento|equipamento|ferramentas?|ar[- ]condicionado)", "compra_material"),
    (r"\bcompra\s+de\s+ar\b|\baquisi[cç][aã]o\s+de\s+ar[- ]condicionado\b", "compra_equipamento"),
    (r"\baquisi[cç][aã]o\s+de\s+equipamento|\bcompra\s+de\s+equipamento", "compra_equipamento"),
    (r"\bfornecimento\s+de\s+equipamento|\bfornecimento\s+de\s+aparelho", "compra_equipamento"),
    (r"\blicen[cç]a\s+de\s+software\b|\bassinatura\s+(anual\s+)?(de\s+)?(software|ferramenta|sistema|saas)\b", "software"),
    (r"\bsoftware\s+(de\s+)?(gest[aã]o|or[cç]amento|cloud)\b|\bferramenta\s+de\s+software\b|\bsaas\b", "software"),
    (r"\bcurso\s+de\s+capacita|\btreinamento\s+presencial\b|\bworkshop\b", "treinamento"),
    (r"\bseguro\s+(de\s+)?vida\b|\bplano\s+de\s+sa[uú]de\b", "seguro_saude"),
    (r"\bpublicidade\b|\bpropaganda\b|\bmidia\s+outdoor\b", "publicidade"),
    (r"\bvigil[aâ]ncia\s+(armada|desarmada|patrimonial)\b", "vigilancia"),
    (r"\bmerenda\s+escolar\b|\buniforme\s+escolar\b", "merenda_uniforme"),
]

# Pure supply/purchase verbs without engineering execution
PURCHASE_ONLY = re.compile(
    r"\b(compra|aquisi[cç][aã]o|fornecimento|aquisi[cç][aã]o\s+de\s+bem)\b",
    re.I,
)
INSTALLATION_SIGNAL = re.compile(
    r"\b(instala[cç][aã]o|instalar|montagem|execu[cç][aã]o\s+de\s+obra|"
    r"empreitada|obra\s+de|infraestrutura\s+de\s+dutos|rede\s+de\s+ductos|"
    r"projeto\s+e\s+execu[cç]|servi[cç]os?\s+de\s+instala[cç])\b",
    re.I,
)

# Strong positive engineering/works terms (require object substance)
STRONG_WORKS: list[tuple[str, str]] = [
    (r"\bpavimenta[cç]", "pavimentacao"),
    (r"\basfalt", "asfalto"),
    (r"\brecapeamento\b|\brecape\b", "recape"),
    (r"\bterraplena(gem)?\b", "terraplenagem"),
    (r"\bdrenagem\s+(pluvial|superficial|urbana)", "drenagem"),
    (r"\brede\s+de\s+(esgoto|[aá]gua\s+pot[aá]vel|[aá]gua)", "rede_agua_esgoto"),
    (r"\bsaneamento\s+(b[aá]sico|ambiental)", "saneamento"),
    (r"\b\beta\b|\b\bete\b|\badutora\b", "eta_ete"),
    (r"\bexecu[cç][aã]o\s+(da\s+)?obra\b|\bobra\s+de\s+engenharia\b", "obra_engenharia"),
    (r"\bempreitada\b", "empreitada"),
    (r"\balvenaria\b", "alvenaria"),
    (r"\bestrutura\s+de\s+concreto\b|\bconcreto\s+armado\b", "concreto"),
    (r"\bviaduto\b|\bpontes?\b\s+(sobre|em)\b", "ponte_viaduto"),
    # Installation/system context — not bare "ar-condicionado" product purchase
    (r"\bclimatiza[cç][aã]o\s+(predial|central|de\s+ambientes?|do\s+pr[eé]dio)", "climatizacao"),
    (r"\binstala[cç][aã]o\s+de\s+ar[- ]condicionado\b|\bar[- ]condicionado\s+central\b", "climatizacao"),
    (r"\bsistema\s+de\s+(climatiza[cç]|ar[- ]condicionado)\b", "climatizacao"),
    (r"\binstala[cç][oõ]es\s+el[eé]tric", "instal_eletrica"),
    (r"\binstala[cç][oõ]es\s+hidr[aá]ulic", "instal_hidraulica"),
    (r"\bspda\b|\bpara[-\s]?raios\b", "spda"),
    (r"\bmanuten[cç][aã]o\s+predial\b", "manut_predial"),
    (r"\bconserva[cç][aã]o\s+predial\b", "manut_predial"),
    (r"\bmanuten[cç][aã]o\s+de\s+edif", "manut_predial"),
    # Engineering *services* — exclude software/assinatura contexts via negatives
    (r"\bservi[cç]os\s+t[eé]cnicos\s+de\s+engenharia\b|\bprest[aã][cç][aã]o\s+de\s+servi[cç]os\s+de\s+engenharia\b", "serv_engenharia"),
    (r"\bapoio\s+t[eé]cnico\s+em\s+engenharia\b|\bfiscaliza[cç][aã]o\s+de\s+obras?\b", "serv_engenharia"),
    (r"\bprojeto\s+executivo\s+(de\s+)?(engenharia|arquitetura|obra)", "projeto_executivo"),
    (r"\breforma\s+(e\s+)?(amplia[cç]|adapta[cç]|recupera[cç])", "reforma_obra"),
    (r"\bconstru[cç][aã]o\s+(e\s+)?(reforma|amplia[cç]|de\s+(escola|creche|ubs|pr[eé]dio|gin[aá]sio|unidade))", "construcao_edificacao"),
    (r"\bamplia[cç][aã]o\s+(de\s+)?(escola|creche|ubs|pr[eé]dio|unidade|hospital)", "ampliacao_edificacao"),
    (r"\breforma\s+(de\s+)?(escola|creche|ubs|pr[eé]dio|unidade|hospital|gin[aá]sio)", "reforma_edificacao"),
    (r"\bpasseios?\s+p[uú]blicos?\b|\bcal[cç]adas?\b|\bpasseio\s+em\s+concreto\b", "calcada"),
    (r"\bsinaliza[cç][aã]o\s+vi[aá]ria\b", "sinalizacao_viaria"),
]

# Contextual positives that need a works co-signal
CONTEXTUAL_NEEDS_WORKS: list[tuple[str, str]] = [
    (r"\bescola\b|\bcreche\b|\bubs\b|\bposto\s+de\s+sa[uú]de\b|\bgin[aá]sio\b|\bpr[eé]dio\b", "edificio_contexto"),
    (r"\brodovi", "rodovi_contexto"),  # alone is NOT pavimentação
    (r"\bconstru[cç][aã]o\s+de\b", "construcao_de_contexto"),
    (r"\breforma\s+d[eo]\b", "reforma_de_contexto"),
]

# Works co-signals for contextual terms
WORKS_CO_SIGNAL = re.compile(
    r"obra|engenharia|execu[cç]|empreitada|paviment|asfalt|alvenaria|"
    r"concreto|estrutura|reforma\s+(e\s+)?amplia|constru[cç][aã]o\s+(civil|da\s+unidade)|"
    r"projeto\s+executivo|fundações|cobertura|telhado|impermeabiliza|"
    r"instala[cç][oõ]es|hidr[aá]ulic|el[eé]tric|saneamento|drenagem|"
    r"manuten[cç][aã]o\s+predial|recuperação\s+estrutural|recuperacao\s+estrutural",
    re.I,
)

# Map archetype id -> strong pattern ids that confirm it
ARCHETYPE_STRONG: dict[str, list[str]] = {
    "pavimentacao-infraestrutura-viaria": [
        "pavimentacao", "asfalto", "recape", "terraplenagem", "drenagem",
        "ponte_viaduto", "calcada", "sinalizacao_viaria",
    ],
    "edificacoes-publicas": [
        "obra_engenharia", "empreitada", "alvenaria", "concreto",
        "construcao_edificacao", "ampliacao_edificacao", "reforma_edificacao",
        "reforma_obra", "projeto_executivo",
    ],
    "saneamento-hidraulica": [
        "rede_agua_esgoto", "saneamento", "eta_ete", "drenagem",
    ],
    "climatizacao-instalacoes": [
        "climatizacao", "instal_eletrica", "instal_hidraulica", "spda",
    ],
    "manutencao-predial-engenharia": [
        "manut_predial", "serv_engenharia",
    ],
}

# Material supply of medicines etc. without works
NEGATIVE_STRONG.append(
    (r"\bmedicamento|\bg[eê]nero\s+aliment|\bfarm[aá]cia\s+b[aá]sica\b", "medicamento_alimento")
)

INSUFFICIENT_MIN_LEN = 20


@dataclass
class ClassificationResult:
    label: str  # aec_confirmed | aec_probable | non_aec | ambiguous | insufficient_context
    archetypes: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)
    positive_hits: list[str] = field(default_factory=list)
    object_nature: str | None = None  # obra | servico | fornecimento | locacao | outros

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "archetypes": list(self.archetypes),
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "negative_hits": list(self.negative_hits),
            "positive_hits": list(self.positive_hits),
            "object_nature": self.object_nature,
        }


def _hits(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    out: list[str] = []
    for pat, name in patterns:
        if re.search(pat, text, re.I):
            out.append(name)
    return out


def infer_object_nature(objeto: str) -> str:
    t = objeto or ""
    if re.search(r"\bloca[cç][aã]o\b|\baluguel\b", t, re.I):
        return "locacao"
    if re.search(r"\baquisi[cç][aã]o\b|\bfornecimento\s+de\s+material|\bcompra\s+de\b", t, re.I):
        if not WORKS_CO_SIGNAL.search(t):
            return "fornecimento"
    if re.search(r"\bobra\b|\bempreitada\b|\bpaviment|\bconstru[cç]|\breforma\b|\bexecu[cç][aã]o\b", t, re.I):
        return "obra"
    if re.search(r"\bservi[cç]o|\bmanuten[cç]|\binstala[cç]", t, re.I):
        return "servico"
    return "outros"


def classify_objeto(objeto: str | None, *, extra: dict[str, Any] | None = None) -> ClassificationResult:
    """Classify a single public object string into AEC taxonomy classes."""
    text = re.sub(r"\s+", " ", (objeto or "").strip())
    if len(text) < INSUFFICIENT_MIN_LEN:
        return ClassificationResult(
            label="insufficient_context",
            confidence=0.0,
            reasons=["object_too_short"],
            object_nature=None,
        )

    nature = infer_object_nature(text)
    neg = _hits(text, NEGATIVE_STRONG)
    strong = _hits(text, STRONG_WORKS)
    contextual = _hits(text, CONTEXTUAL_NEEDS_WORKS)
    has_works_co = bool(WORKS_CO_SIGNAL.search(text))
    is_purchase = bool(PURCHASE_ONLY.search(text))
    has_install = bool(INSTALLATION_SIGNAL.search(text))

    # Software / SaaS / assinatura always non_aec even if "engenharia" appears
    if "software" in neg or re.search(r"\bassinatura\s+anual\b|\blicen[cç]a\s+de\s+uso\b", text, re.I):
        return ClassificationResult(
            label="non_aec",
            confidence=0.97,
            reasons=["software_or_subscription"],
            negative_hits=neg + ["software"],
            positive_hits=strong,
            object_nature="fornecimento",
        )

    # Hard negatives (locação, limpeza, transporte, etc.) dominate without real install
    hard_non = {
        "locacao_imovel", "aluguel_imovel", "limpeza", "alimentacao",
        "credenciamento_escolas", "onibus_transporte", "veiculo_rodoviario",
        "software", "treinamento", "seguro_saude", "publicidade", "vigilancia",
        "merenda_uniforme", "medicamento_alimento",
    }
    if any(n in hard_non for n in neg) and not has_install:
        return ClassificationResult(
            label="non_aec",
            confidence=0.95,
            reasons=[f"negative:{n}" for n in neg],
            negative_hits=neg,
            positive_hits=strong,
            object_nature=nature,
        )

    # Equipment / material purchase without installation/execution → non_aec
    # (even if product keywords like ar-condicionado or manutenção predial appear)
    supply_tags = {
        "aquisicao_material", "fornecimento_material", "compra_material", "compra_equipamento",
    }
    if any(n in supply_tags for n in neg) or (is_purchase and not has_install):
        if not has_install:
            return ClassificationResult(
                label="non_aec",
                confidence=0.93,
                reasons=["equipment_or_material_purchase_without_installation"],
                negative_hits=neg + (["purchase_only"] if is_purchase else []),
                positive_hits=strong,
                object_nature="fornecimento",
            )

    # Nature fornecimento without install never reaches aec_confirmed later
    if nature == "fornecimento" and not has_install:
        return ClassificationResult(
            label="non_aec",
            confidence=0.9,
            reasons=["fornecimento_without_installation"],
            negative_hits=neg,
            positive_hits=strong,
            object_nature="fornecimento",
        )

    # escola / rodovi / construção de alone → not confirmed
    if "edificio_contexto" in contextual and not strong and not has_works_co:
        # pure mention of school without construction language
        if not re.search(r"constru[cç]|reforma|amplia[cç]|obra|engenharia|empreitada", text, re.I):
            return ClassificationResult(
                label="non_aec",
                confidence=0.85,
                reasons=["escola_or_building_name_without_works"],
                negative_hits=neg,
                positive_hits=strong + contextual,
                object_nature=nature,
            )

    if "rodovi_contexto" in contextual and not strong:
        # ônibus rodoviário / transporte rodoviário without pavement works
        if re.search(r"[oô]nibus|transporte|ve[ií]culo|passagem|bilhete", text, re.I):
            return ClassificationResult(
                label="non_aec",
                confidence=0.95,
                reasons=["rodovi_transport_not_pavement"],
                negative_hits=neg + ["rodovi_transporte"],
                positive_hits=strong + contextual,
                object_nature=nature,
            )
        if not has_works_co:
            return ClassificationResult(
                label="ambiguous",
                confidence=0.4,
                reasons=["rodovi_without_works_context"],
                positive_hits=contextual,
                object_nature=nature,
            )

    if "construcao_de_contexto" in contextual and not strong and not has_works_co:
        return ClassificationResult(
            label="ambiguous",
            confidence=0.35,
            reasons=["construcao_de_without_material_object"],
            positive_hits=contextual,
            object_nature=nature,
        )

    # Map to archetypes from strong hits
    arches: list[str] = []
    for arch_id, strong_ids in ARCHETYPE_STRONG.items():
        if any(s in strong for s in strong_ids):
            arches.append(arch_id)

    # Contextual + works co-signal can yield probable (not confirmed alone)
    if not arches and has_works_co and contextual:
        if "edificio_contexto" in contextual or "construcao_de_contexto" in contextual or "reforma_de_contexto" in contextual:
            arches.append("edificacoes-publicas")
        if "rodovi_contexto" in contextual and re.search(r"paviment|asfalt|estrada|via\s+p[uú]blica", text, re.I):
            arches.append("pavimentacao-infraestrutura-viaria")

    if strong and arches:
        # Never confirm pure supply/purchase even if a strong product keyword hit
        if is_purchase and not has_install:
            return ClassificationResult(
                label="non_aec",
                confidence=0.9,
                reasons=["strong_keyword_but_purchase_without_install"],
                positive_hits=strong,
                negative_hits=neg,
                object_nature="fornecimento",
            )
        # confirmed only with strong engineering evidence
        conf = min(0.99, 0.75 + 0.05 * len(strong))
        return ClassificationResult(
            label="aec_confirmed",
            archetypes=sorted(set(arches)),
            confidence=conf,
            reasons=[f"strong:{s}" for s in strong],
            positive_hits=strong + contextual,
            negative_hits=neg,
            object_nature=nature if nature not in {"outros", "fornecimento"} else "obra",
        )

    if arches and has_works_co:
        return ClassificationResult(
            label="aec_probable",
            archetypes=sorted(set(arches)),
            confidence=0.6,
            reasons=["contextual_with_works_cosignal"],
            positive_hits=strong + contextual,
            negative_hits=neg,
            object_nature=nature,
        )

    if strong and not arches:
        return ClassificationResult(
            label="aec_probable",
            archetypes=[],
            confidence=0.55,
            reasons=["strong_without_archetype_map"],
            positive_hits=strong,
            negative_hits=neg,
            object_nature=nature,
        )

    if contextual or has_works_co:
        return ClassificationResult(
            label="ambiguous",
            confidence=0.3,
            reasons=["weak_signals_only"],
            positive_hits=strong + contextual,
            negative_hits=neg,
            object_nature=nature,
        )

    return ClassificationResult(
        label="insufficient_context",
        confidence=0.1,
        reasons=["no_aec_signals"],
        object_nature=nature,
        negative_hits=neg,
    )


def classify_object(objeto: str | None) -> list[str]:
    """Backward-compatible: return archetype ids only for aec_confirmed."""
    r = classify_objeto(objeto)
    if r.label == "aec_confirmed":
        return list(r.archetypes)
    return []


def classify_object_probable(objeto: str | None) -> list[str]:
    """Archetypes for confirmed + probable (review / auxiliary only)."""
    r = classify_objeto(objeto)
    if r.label in {"aec_confirmed", "aec_probable"}:
        return list(r.archetypes)
    return []


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def evaluate_classifier(
    gold: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate against stratified gold set.

    Each gold item: {objeto, expected_label, expected_archetypes?, segment?}
    expected_label in aec_confirmed | aec_probable | non_aec | ambiguous | insufficient_context
    For precision of aec_confirmed: predicted confirmed that are truly AEC works.
    """
    tp = fp = fn = tn = 0
    confusion: dict[str, dict[str, int]] = {}
    by_segment: dict[str, dict[str, int]] = {}
    details: list[dict[str, Any]] = []

    for row in gold:
        obj = row["objeto"]
        expected = row["expected_label"]
        pred = classify_objeto(obj)
        predicted = pred.label
        confusion.setdefault(expected, {})
        confusion[expected][predicted] = confusion[expected].get(predicted, 0) + 1

        # Binary: is aec_confirmed correctly used?
        exp_pos = expected == "aec_confirmed"
        pred_pos = predicted == "aec_confirmed"
        if pred_pos and exp_pos:
            tp += 1
        elif pred_pos and not exp_pos:
            fp += 1
        elif not pred_pos and exp_pos:
            fn += 1
        else:
            tn += 1

        seg = row.get("segment") or "all"
        st = by_segment.setdefault(seg, {"tp": 0, "fp": 0, "fn": 0, "n": 0})
        st["n"] += 1
        if pred_pos and exp_pos:
            st["tp"] += 1
        elif pred_pos and not exp_pos:
            st["fp"] += 1
        elif not pred_pos and exp_pos:
            st["fn"] += 1

        details.append(
            {
                "objeto": obj[:120],
                "expected": expected,
                "predicted": predicted,
                "archetypes": pred.archetypes,
                "reasons": pred.reasons,
                "match": expected == predicted,
            }
        )

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    seg_metrics = {}
    for seg, st in by_segment.items():
        p = st["tp"] / (st["tp"] + st["fp"]) if (st["tp"] + st["fp"]) else 1.0
        r = st["tp"] / (st["tp"] + st["fn"]) if (st["tp"] + st["fn"]) else 1.0
        seg_metrics[seg] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "n": st["n"],
            "tp": st["tp"],
            "fp": st["fp"],
            "fn": st["fn"],
        }

    return {
        "n": len(gold),
        "precision_aec_confirmed": round(precision, 4),
        "recall_aec_confirmed": round(recall, 4),
        "f1_aec_confirmed": round(f1, 4),
        "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) else 0.0,
        "false_negative_rate": round(fn / (fn + tp), 4) if (fn + tp) else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "confusion": confusion,
        "by_segment": seg_metrics,
        "details": details,
        "gates": {
            "precision_global_ok": precision >= 0.97,
            "precision_threshold": 0.97,
            "segment_precision_threshold": 0.95,
        },
    }
