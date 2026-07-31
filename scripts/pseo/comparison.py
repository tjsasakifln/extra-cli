"""Price benchmark comparability keys — prevent mixing incomparable objects."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from scripts.pseo.classifiers import classify_objeto, infer_object_nature
from scripts.pseo.normalization import iso_date

MIN_COMPARABLE_OBS = 12
MIN_COMPARISON_CONFIDENCE = 0.55


@dataclass
class ComparisonKey:
    comparison_group: str
    comparison_confidence: float
    nature: str
    typology: str
    scope: str  # execucao | manutencao | reforma | obra_nova | misto | desconhecido
    regime: str
    inclusion: list[str] = field(default_factory=list)
    exclusion: list[str] = field(default_factory=list)
    heterogeneity_flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "comparison_group": self.comparison_group,
            "comparison_confidence": round(self.comparison_confidence, 3),
            "nature": self.nature,
            "typology": self.typology,
            "scope": self.scope,
            "regime": self.regime,
            "inclusion_criteria": list(self.inclusion),
            "exclusion_criteria": list(self.exclusion),
            "heterogeneity_flags": list(self.heterogeneity_flags),
        }


def _scope(objeto: str) -> str:
    t = objeto.lower()
    if re.search(r"manuten[cç]|conserva[cç][aã]o predial", t):
        return "manutencao"
    if re.search(r"reforma|recupera[cç]|restauro", t):
        return "reforma"
    if re.search(r"constru[cç][aã]o\s+nova|obra\s+nova|implanta[cç][aã]o", t):
        return "obra_nova"
    if re.search(r"execu[cç]|empreitada|paviment", t):
        return "execucao"
    return "desconhecido"


def _typology(objeto: str, archetypes: list[str]) -> str:
    """Fine-grained typology — never mix CBUQ asphalt with paralelepípedo."""
    t = objeto.lower()
    # Pavement materials must be distinct comparison groups
    if re.search(r"\bcbuq\b|concreto\s+betuminoso|asfalt[oa]\s+(em\s+)?quente|capp?eamento\s+asf[aá]lt", t):
        return "cbuq_asfalto"
    if re.search(r"paralelep[ií]pedo|poliedric|pedra\s+irregular", t):
        return "paralelepipedo"
    if re.search(r"intertravad|bloco\s+de\s+concreto\s+paviment|paver\b", t):
        return "intertravado"
    if re.search(r"recape|recapeamento", t):
        return "recape_asfaltico"
    if re.search(r"paviment.*asfalt|asfalt.*paviment|pavimenta[cç][aã]o\s+asf", t):
        return "cbuq_asfalto"
    if re.search(r"paviment", t):
        return "pavimentacao_generica"
    if re.search(r"drenagem", t):
        return "drenagem"
    if re.search(r"escola|creche", t) and re.search(r"constru[cç]|reforma|obra|amplia", t):
        return "educacao_edificacao"
    if re.search(r"ubs|posto de sa[uú]de|hospital", t) and re.search(r"constru[cç]|reforma|obra|amplia", t):
        return "saude_edificacao"
    if re.search(r"esgoto|adutora|eta\b|ete\b|rede de [aá]gua", t):
        return "saneamento_rede"
    if re.search(r"instala[cç].*ar[- ]condicionado|climatiza[cç].*predial|ar[- ]condicionado\s+central", t):
        return "climatizacao_instalacao"
    if re.search(r"manuten[cç][aã]o predial", t):
        return "manutencao_predial"
    if archetypes:
        return archetypes[0]
    return "generico"


def _regime(objeto: str) -> str:
    t = objeto.lower()
    if re.search(r"empreitada\s+global|pre[cç]o\s+global", t):
        return "empreitada_global"
    if re.search(r"empreitada\s+por\s+pre[cç]o\s+unit[aá]rio|unit[aá]rio", t):
        return "preco_unitario"
    if re.search(r"registro\s+de\s+pre[cç]o", t):
        return "registro_precos"
    if re.search(r"integral|projeto\s+e\s+execu[cç]", t):
        return "integral"
    return "nao_informado"


def comparison_key_for_object(
    objeto: str,
    *,
    archetype: str | None = None,
    uf: str | None = None,
) -> ComparisonKey:
    clf = classify_objeto(objeto)
    nature = clf.object_nature or infer_object_nature(objeto)
    arches = list(clf.archetypes) or ([archetype] if archetype else [])
    typ = _typology(objeto, arches)
    scope = _scope(objeto)
    regime = _regime(objeto)
    flags: list[str] = []
    conf = 0.5

    if nature in {"locacao", "fornecimento"}:
        conf = 0.1
        flags.append(f"nature_{nature}_not_comparable_as_works")
    if clf.label != "aec_confirmed":
        conf = min(conf, 0.35)
        flags.append(f"classification_{clf.label}")
    if scope == "desconhecido":
        flags.append("scope_unknown")
        conf -= 0.1
    if regime == "nao_informado":
        flags.append("regime_unknown")
        conf -= 0.05
    if typ == "generico":
        flags.append("typology_generic")
        conf -= 0.15
    else:
        conf += 0.2
    if clf.label == "aec_confirmed":
        conf += 0.25

    conf = max(0.0, min(1.0, conf))
    arch_part = archetype or (arches[0] if arches else "na")
    group = f"{arch_part}|{typ}|{scope}|{nature}|{uf or 'BR'}"

    return ComparisonKey(
        comparison_group=group,
        comparison_confidence=conf,
        nature=nature,
        typology=typ,
        scope=scope,
        regime=regime,
        inclusion=[
            f"typology={typ}",
            f"scope={scope}",
            f"nature={nature}",
            f"archetype={arch_part}",
            f"uf={uf or 'any'}",
        ],
        exclusion=[
            "locacao_imovel",
            "credenciamento",
            "limpeza_sem_obra",
            "fornecimento_material_isolado",
            "classes_semanticas_conflitantes",
        ],
        heterogeneity_flags=flags,
    )


def build_comparable_prices(
    contracts: list[Any],
    *,
    min_obs: int = MIN_COMPARABLE_OBS,
    min_confidence: float = MIN_COMPARISON_CONFIDENCE,
) -> list[dict[str, Any]]:
    """Aggregate prices only within comparable groups with sufficient confidence.

    contracts: objects with .objeto, .valor, .uf, .archetypes, .orgao_nome,
    .municipio, .data_publicacao, .source, .contrato_id (optional)
    """
    buckets: dict[str, list[tuple[Any, ComparisonKey]]] = defaultdict(list)
    for c in contracts:
        arches = getattr(c, "archetypes", None) or []
        if not arches:
            continue
        valor = float(getattr(c, "valor", 0) or 0)
        if valor < 5_000:
            continue
        uf = getattr(c, "uf", None)
        for arch in arches:
            key = comparison_key_for_object(
                getattr(c, "objeto", "") or "",
                archetype=arch,
                uf=uf,
            )
            if key.nature in {"locacao", "fornecimento"}:
                continue
            if key.comparison_confidence < min_confidence * 0.5:
                continue
            buckets[key.comparison_group].append((c, key))

    out: list[dict[str, Any]] = []
    for group, pairs in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if len(pairs) < min_obs:
            continue
        # Reject if conflicting natures/scopes mix heavily
        natures = Counter(k.nature for _, k in pairs)
        scopes = Counter(k.scope for _, k in pairs)
        typs = Counter(k.typology for _, k in pairs)
        flags: list[str] = []
        if len([n for n, c in natures.items() if c >= 2]) > 2:
            flags.append("mixed_natures")
        if "locacao" in natures or "fornecimento" in natures:
            flags.append("contaminated_nature")
        # Semantic material classes must not mix in one public benchmark
        pavement_materials = {
            "cbuq_asfalto", "paralelepipedo", "intertravado", "recape_asfaltico",
            "pavimentacao_generica",
        }
        present_pav = [t for t in typs if t in pavement_materials]
        if len(present_pav) > 1:
            flags.append("mixed_pavement_materials")
        if len([t for t, c in typs.items() if c >= 2]) > 1 and len(typs) > 1:
            # Dominant typology must be ≥80% of observations
            top_typ, top_n = typs.most_common(1)[0]
            if top_n / len(pairs) < 0.8:
                flags.append("mixed_typologies")
        if (
            "contaminated_nature" in flags
            or "mixed_natures" in flags
            or "mixed_pavement_materials" in flags
            or "mixed_typologies" in flags
        ):
            continue

        confs = [k.comparison_confidence for _, k in pairs]
        avg_conf = sum(confs) / len(confs)
        if avg_conf < min_confidence:
            continue

        items = [c for c, _ in pairs]
        vals = sorted(float(c.valor) for c in items)
        # IQR outlier trim for display stats (keep count of raw)
        p25 = _pct(vals, 25)
        p75 = _pct(vals, 75)
        med = _pct(vals, 50)
        iqr = (p75 - p25) if p25 is not None and p75 is not None else None
        outliers = []
        if iqr and p25 is not None and p75 is not None:
            lo, hi = p25 - 1.5 * iqr, p75 + 1.5 * iqr
            outliers = [v for v in vals if v < lo or v > hi]

        sample_key = pairs[0][1]
        arch = sample_key.comparison_group.split("|")[0]
        uf = getattr(items[0], "uf", None) or "BR"
        # Prefer stable slug: archetype-uf-typology when possible
        slug = f"{arch}-{str(uf).lower()}-{sample_key.typology}"
        slug = re.sub(r"[^a-z0-9\-]+", "-", slug.lower())[:80]

        examples = []
        for c in sorted(items, key=lambda x: -float(x.valor))[:5]:
            examples.append(
                {
                    "objeto": (getattr(c, "objeto", "") or "")[:200],
                    "valor": float(c.valor),
                    "uf": getattr(c, "uf", None),
                    "municipio": getattr(c, "municipio", None),
                    "orgao_nome": getattr(c, "orgao_nome", None),
                    "data_publicacao": iso_date(getattr(c, "data_publicacao", None)),
                    "source": getattr(c, "source", None) or "pncp",
                    "contrato_id": getattr(c, "contrato_id", None),
                    "link_oficial": getattr(c, "link_oficial", None),
                }
            )

        dates = [iso_date(getattr(c, "data_publicacao", None)) for c in items]
        dates = [d for d in dates if d]
        out.append(
            {
                "id": f"price-{slug}",
                "slug": slug,
                "object_label": f"{sample_key.typology.replace('_', ' ')} ({arch})",
                "object_pattern": arch,
                "region": uf,
                "region_label": uf,
                "period_start": min(dates) if dates else None,
                "period_end": max(dates) if dates else None,
                "observation_count": len(vals),
                "median_value": med,
                "p25_value": p25,
                "p75_value": p75,
                "min_value": round(min(vals), 2),
                "max_value": round(max(vals), 2),
                "dispersion_iqr": round(iqr, 2) if iqr is not None else None,
                "outlier_count": len(outliers),
                "comparison_group": group,
                "comparison_confidence": round(avg_conf, 3),
                "comparison_meta": sample_key.as_dict(),
                "scope_distribution": dict(scopes),
                "inclusion_criteria": sample_key.inclusion
                + [
                    f"n>={min_obs}",
                    f"comparison_confidence>={min_confidence}",
                    "somente aec_confirmed",
                ],
                "exclusion_criteria": sample_key.exclusion
                + [
                    "grupos com naturezas conflitantes",
                    "confiança abaixo do limiar",
                ],
                "public_examples": examples,
                "sources": sorted({getattr(c, "source", None) or "pncp" for c in items}),
                "limitations": [
                    "Observações são contratos integrais, não preços unitários.",
                    "Grupo de comparabilidade semântico — ainda não substitui orçamento técnico.",
                    "Outliers identificados por regra IQR 1.5×.",
                ],
                "warning": (
                    "Não use a mediana como preço de referência aplicável a qualquer "
                    "caso. Compare escopo, quantitativos, regime, data-base e localidade. "
                    "Este benchmark não substitui orçamento técnico."
                ),
                "heterogeneity_flags": flags + sample_key.heterogeneity_flags,
            }
        )
    return out


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    i = min(len(vals) - 1, max(0, int(round((p / 100) * (len(vals) - 1)))))
    return round(vals[i], 2)
