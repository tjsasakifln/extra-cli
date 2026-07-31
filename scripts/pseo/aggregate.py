"""Read-only aggregation of public contract and bid data for pSEO export."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from scripts.pseo.archetypes import (
    ARCHETYPE_DEFS,
    ClassifiedContract,
    build_public_archetypes,
    classify_object,
)

MIN_VALOR_BENCHMARK = 5_000.0  # exclude trivial/noise values from price stats


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round((p / 100) * (len(s) - 1)))))
    return round(s[i], 2)


def _slugify(text: str, max_len: int = 80) -> str:
    t = (text or "").lower()
    t = re.sub(r"[àáâãä]", "a", t)
    t = re.sub(r"[èéêë]", "e", t)
    t = re.sub(r"[ìíîï]", "i", t)
    t = re.sub(r"[òóôõö]", "o", t)
    t = re.sub(r"[ùúûü]", "u", t)
    t = re.sub(r"[ç]", "c", t)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:max_len].strip("-") or "item"


def _cnpj8(cnpj: str | None) -> str:
    d = re.sub(r"\D", "", cnpj or "")
    return d[:8] if len(d) >= 8 else d


def classify_rows(rows: Iterable[dict[str, Any]]) -> list[ClassifiedContract]:
    out: list[ClassifiedContract] = []
    for r in rows:
        obj = r.get("objeto_contrato") or r.get("objeto") or ""
        arches = classify_object(obj)
        if not arches:
            continue
        valor = r.get("valor_total") if r.get("valor_total") is not None else r.get("valor")
        try:
            valor_f = float(valor) if valor is not None else 0.0
        except (TypeError, ValueError):
            valor_f = 0.0
        if valor_f <= 0:
            continue
        out.append(
            ClassifiedContract(
                contrato_id=r.get("contrato_id"),
                orgao_cnpj=_cnpj8(r.get("orgao_cnpj")),
                orgao_nome=r.get("orgao_nome"),
                fornecedor_cnpj=re.sub(r"\D", "", r.get("fornecedor_cnpj") or "")[:14],
                fornecedor_nome=r.get("fornecedor_nome"),
                objeto=str(obj),
                valor=valor_f,
                data_inicio=_iso(r.get("data_inicio")),
                data_fim=_iso(r.get("data_fim")),
                data_publicacao=_iso(r.get("data_publicacao")),
                uf=(r.get("uf") or None),
                municipio=r.get("municipio"),
                source=str(r.get("source") or "pncp"),
                archetypes=arches,
            )
        )
    return out


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    s = str(v)
    return s[:10] if s else None


def period_bounds(classified: list[ClassifiedContract]) -> tuple[str | None, str | None]:
    dates = [c.data_publicacao for c in classified if c.data_publicacao]
    if not dates:
        return None, None
    return min(dates), max(dates)


def build_markets(
    classified: list[ClassifiedContract],
    open_bids: list[dict[str, Any]],
    min_contracts: int = 15,
    min_buyers: int = 3,
) -> list[dict[str, Any]]:
    """Regional market pages: archetype × UF with critical mass."""
    # Count by arch×uf
    buckets: dict[tuple[str, str], list[ClassifiedContract]] = defaultdict(list)
    for c in classified:
        if not c.uf:
            continue
        for a in c.archetypes:
            buckets[(a, c.uf)].append(c)

    markets: list[dict[str, Any]] = []
    for (arch, uf), items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        buyers = {c.orgao_cnpj or c.orgao_nome for c in items if c.orgao_cnpj or c.orgao_nome}
        if len(items) < min_contracts or len(buyers) < min_buyers:
            continue
        vals = [c.valor for c in items]
        p_start, p_end = period_bounds(items)
        # top buyers
        bstats: dict[str, dict[str, Any]] = {}
        for c in items:
            key = c.orgao_cnpj or c.orgao_nome or "?"
            st = bstats.setdefault(
                key,
                {
                    "name": c.orgao_nome,
                    "cnpj8": c.orgao_cnpj,
                    "uf": c.uf,
                    "municipio": c.municipio,
                    "contract_count": 0,
                    "total_value": 0.0,
                },
            )
            st["contract_count"] += 1
            st["total_value"] = round(st["total_value"] + c.valor, 2)
        top_buyers = sorted(bstats.values(), key=lambda x: -x["contract_count"])[:8]
        for b in top_buyers:
            b["total_value"] = round(b["total_value"], 2)

        # top objects (tokenized short labels)
        obj_counter: Counter[str] = Counter()
        obj_examples: dict[str, ClassifiedContract] = {}
        for c in items:
            label = _short_object_label(c.objeto)
            obj_counter[label] += 1
            obj_examples.setdefault(label, c)
        top_objects = []
        for label, n in obj_counter.most_common(8):
            ex = obj_examples[label]
            top_objects.append(
                {
                    "label": label,
                    "count": n,
                    "median_value": None,
                    "example_objeto": (ex.objeto or "")[:200],
                }
            )

        by_year: Counter[str] = Counter()
        value_year: dict[str, float] = defaultdict(float)
        for c in items:
            y = (c.data_publicacao or "")[:4]
            if y:
                by_year[y] += 1
                value_year[y] += c.valor
        value_by_year = [
            {"year": y, "contract_count": by_year[y], "total_value": round(value_year[y], 2)}
            for y in sorted(by_year.keys())
        ]

        open_n = sum(
            1
            for b in open_bids
            if arch in (b.get("archetypes") or []) and b.get("uf") == uf
        )
        label = ARCHETYPE_DEFS[arch]["label"]
        slug = f"{arch}-{uf.lower()}"
        suppliers = {c.fornecedor_cnpj for c in items if c.fornecedor_cnpj}
        markets.append(
            {
                "id": f"market-{slug}",
                "slug": slug,
                "archetype_id": arch,
                "segment": label,
                "region": uf,
                "region_label": _uf_label(uf),
                "period_start": p_start,
                "period_end": p_end,
                "contract_count": len(items),
                "buyer_count": len(buyers),
                "supplier_count": len(suppliers),
                "total_value": round(sum(vals), 2),
                "median_value": _pct(vals, 50),
                "p25_value": _pct(vals, 25),
                "p75_value": _pct(vals, 75),
                "top_buyers": top_buyers,
                "top_objects": top_objects,
                "value_by_year": value_by_year,
                "modalities": [],  # filled when bid/modalidade join available
                "open_opportunity_count": open_n,
                "sources": sorted({c.source for c in items if c.source}),
                "limitations": [
                    f"Base: {len(items)} contratos classificados no arquétipo "
                    f"em {uf}; não representa o universo total de contratações.",
                    "Valores nominais sem deflacionamento.",
                    "Objetos heterogêneos; mediana não é preço unitário.",
                ],
                "interpretation_hooks": [
                    f"Concentração em {len(buyers)} órgãos compradores distintos.",
                    f"{len(suppliers)} fornecedores observados no recorte.",
                    f"Oportunidades abertas no radar (mesmo recorte): {open_n}.",
                ],
            }
        )
    return markets


def build_agencies(
    classified: list[ClassifiedContract],
    open_bids: list[dict[str, Any]],
    min_contracts: int = 12,
) -> list[dict[str, Any]]:
    by_agency: dict[str, list[ClassifiedContract]] = defaultdict(list)
    for c in classified:
        key = c.orgao_cnpj or _slugify(c.orgao_nome or "")
        if not key:
            continue
        by_agency[key].append(c)

    agencies: list[dict[str, Any]] = []
    for key, items in sorted(by_agency.items(), key=lambda kv: -len(kv[1])):
        if len(items) < min_contracts:
            continue
        name = items[0].orgao_nome or key
        uf = items[0].uf
        mun = items[0].municipio
        vals = [c.valor for c in items]
        p_start, p_end = period_bounds(items)
        mix = Counter()
        for c in items:
            for a in c.archetypes:
                mix[a] += 1
        # seasonality by month
        months: Counter[str] = Counter()
        for c in items:
            if c.data_publicacao and len(c.data_publicacao) >= 7:
                months[c.data_publicacao[:7]] += 1
        seasonality = [
            {"period": m, "contract_count": n} for m, n in sorted(months.items())[-18:]
        ]
        obj_counter: Counter[str] = Counter()
        for c in items:
            obj_counter[_short_object_label(c.objeto)] += 1
        top_objects = [
            {"label": lab, "count": n, "median_value": None, "example_objeto": lab}
            for lab, n in obj_counter.most_common(8)
        ]
        suppliers = {c.fornecedor_cnpj for c in items if c.fornecedor_cnpj}
        cnpj8 = items[0].orgao_cnpj
        open_ops = [
            {
                "pncp_id": b.get("pncp_id"),
                "objeto": (b.get("objeto") or "")[:220],
                "valor_estimado": b.get("valor_estimado"),
                "modalidade": b.get("modalidade"),
                "uf": b.get("uf"),
                "municipio": b.get("municipio"),
                "orgao_nome": b.get("orgao_nome"),
                "data_encerramento": b.get("data_encerramento"),
                "link_pncp": b.get("link_pncp"),
                "source": b.get("source") or "pncp",
            }
            for b in open_bids
            if _cnpj8(b.get("orgao_cnpj")) == cnpj8
            or (b.get("orgao_nome") and name and b.get("orgao_nome") == name)
        ][:10]

        slug = _slugify(f"{name}-{uf or 'br'}")
        agencies.append(
            {
                "id": f"agency-{cnpj8 or slug}",
                "slug": slug,
                "agency_name": name,
                "agency_cnpj8": cnpj8 or None,
                "uf": uf,
                "municipio": mun,
                "period_start": p_start,
                "period_end": p_end,
                "contract_count": len(items),
                "total_value": round(sum(vals), 2),
                "median_value": _pct(vals, 50),
                "p25_value": _pct(vals, 25),
                "p75_value": _pct(vals, 75),
                "archetype_mix": [
                    {"archetype_id": a, "contract_count": n} for a, n in mix.most_common()
                ],
                "top_objects": top_objects,
                "modalities": [],
                "seasonality": seasonality,
                "supplier_count": len(suppliers),
                "open_opportunities": open_ops,
                "official_channels": _official_channels(uf),
                "sources": sorted({c.source for c in items if c.source}),
                "limitations": [
                    "Histórico restrito aos contratos ingeridos no datalake.",
                    "Nome do órgão conforme fonte; pode haver variação cadastral.",
                ],
                "practical_notes": [
                    "Verifique edital vigente e anexos no portal oficial antes de precificar.",
                    "Compare objetos e regimes semelhantes; evite extrapolar ticket mediano.",
                    "Documente premissas de produtividade e BDI para o órgão específico.",
                ],
            }
        )
    return agencies


def build_prices(
    classified: list[ClassifiedContract],
    min_obs: int = 20,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[ClassifiedContract]] = defaultdict(list)
    for c in classified:
        if not c.uf or c.valor < MIN_VALOR_BENCHMARK:
            continue
        for a in c.archetypes:
            buckets[(a, c.uf)].append(c)

    prices: list[dict[str, Any]] = []
    for (arch, uf), items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if len(items) < min_obs:
            continue
        vals = [c.valor for c in items]
        p25, med, p75 = _pct(vals, 25), _pct(vals, 50), _pct(vals, 75)
        iqr = round((p75 or 0) - (p25 or 0), 2) if p25 is not None and p75 is not None else None
        p_start, p_end = period_bounds(items)
        examples = []
        for c in sorted(items, key=lambda x: -x.valor)[:5]:
            examples.append(
                {
                    "objeto": (c.objeto or "")[:200],
                    "valor": c.valor,
                    "uf": c.uf,
                    "municipio": c.municipio,
                    "orgao_nome": c.orgao_nome,
                    "data_publicacao": c.data_publicacao,
                    "source": c.source,
                }
            )
        label = ARCHETYPE_DEFS[arch]["label"]
        slug = f"{arch}-{uf.lower()}"
        prices.append(
            {
                "id": f"price-{slug}",
                "slug": slug,
                "object_label": label,
                "object_pattern": arch,
                "region": uf,
                "region_label": _uf_label(uf),
                "period_start": p_start,
                "period_end": p_end,
                "observation_count": len(items),
                "median_value": med,
                "p25_value": p25,
                "p75_value": p75,
                "min_value": round(min(vals), 2),
                "max_value": round(max(vals), 2),
                "dispersion_iqr": iqr,
                "inclusion_criteria": [
                    f"Objeto classificado no arquétipo {label}",
                    f"UF = {uf}",
                    f"valor_total >= {MIN_VALOR_BENCHMARK:.0f} BRL",
                    "Fonte pública no datalake CONFENGE/extra-cli",
                ],
                "exclusion_criteria": [
                    "Contratos com valor nulo, zero ou abaixo do piso amostral",
                    "Objetos sem classificação de arquétipo AEC",
                    "Média aritmética não é publicada como referência",
                ],
                "public_examples": examples,
                "sources": sorted({c.source for c in items if c.source}),
                "limitations": [
                    "Observações são contratos integrais, não preços unitários de serviço.",
                    "Objetos dentro do mesmo arquétipo podem ser tecnicamente incomparáveis.",
                ],
                "warning": (
                    "Não use a mediana como preço de referência aplicável a qualquer "
                    "caso. Compare escopo, quantitativos, regime, data-base e localidade "
                    "antes de qualquer decisão de proposta."
                ),
            }
        )
    return prices


def build_competition(
    classified: list[ClassifiedContract],
    min_contracts: int = 15,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[ClassifiedContract]] = defaultdict(list)
    for c in classified:
        if not c.uf:
            continue
        for a in c.archetypes:
            buckets[(a, c.uf)].append(c)

    out: list[dict[str, Any]] = []
    for (arch, uf), items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if len(items) < min_contracts:
            continue
        by_sup: dict[str, dict[str, Any]] = {}
        for c in items:
            key = c.fornecedor_cnpj or c.fornecedor_nome or "?"
            st = by_sup.setdefault(
                key,
                {
                    "display_name": _mask_supplier_name(c.fornecedor_nome),
                    "contract_count": 0,
                    "total_value": 0.0,
                    "agencies": set(),
                },
            )
            st["contract_count"] += 1
            st["total_value"] += c.valor
            if c.orgao_cnpj or c.orgao_nome:
                st["agencies"].add(c.orgao_cnpj or c.orgao_nome)
        ranked = sorted(by_sup.values(), key=lambda x: -x["contract_count"])
        total_c = sum(s["contract_count"] for s in ranked) or 1
        top3 = ranked[:3]
        share = round(sum(s["contract_count"] for s in top3) / total_c, 4)
        observed = []
        for s in ranked[:12]:
            band = _value_band(s["total_value"])
            observed.append(
                {
                    "display_name": s["display_name"],
                    "contract_count": s["contract_count"],
                    "total_value": round(s["total_value"], 2),
                    "agencies_count": len(s["agencies"]),
                    "value_band": band,
                }
            )
        agencies = {c.orgao_cnpj or c.orgao_nome for c in items if c.orgao_cnpj or c.orgao_nome}
        p_start, p_end = period_bounds(items)
        label = ARCHETYPE_DEFS[arch]["label"]
        slug = f"{arch}-{uf.lower()}"
        # recent changes: compare last 12m vs prior if dates allow
        recent_changes = _recent_supplier_changes(items)
        out.append(
            {
                "id": f"comp-{slug}",
                "slug": slug,
                "segment": label,
                "region": uf,
                "region_label": _uf_label(uf),
                "period_start": p_start,
                "period_end": p_end,
                "supplier_count": len(ranked),
                "contract_count": len(items),
                "observed_suppliers": observed,
                "concentration_top3_share": share,
                "agencies_with_activity": len(agencies),
                "value_bands": _band_histogram(items),
                "recent_changes": recent_changes,
                "sources": sorted({c.source for c in items if c.source}),
                "limitations": [
                    "Lista de fornecedores observados, não ranking de qualidade.",
                    "Ausência na lista não implica ausência de atuação no mercado real.",
                ],
                "language_note": (
                    "Linguagem neutra e verificável. Não se atribui competência, "
                    "qualidade, risco, intenção ou probabilidade de compra a qualquer fornecedor."
                ),
            }
        )
    return out


def build_opportunities(
    open_bids: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    min_open: int = 3,
) -> list[dict[str, Any]]:
    """Evergreen radar pages by segment×region (not one URL per tender)."""
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for b in open_bids:
        uf = b.get("uf")
        if not uf:
            continue
        for a in b.get("archetypes") or []:
            buckets[(a, uf)].append(b)

    market_slugs = {m["slug"] for m in markets}
    out: list[dict[str, Any]] = []
    from datetime import date

    as_of = date.today().isoformat()
    for (arch, uf), items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if len(items) < min_open:
            continue
        label = ARCHETYPE_DEFS.get(arch, {}).get("label", arch)
        slug = f"{arch}-{uf.lower()}"
        related = slug if slug in market_slugs else None
        pub_items = []
        for b in items[:25]:
            pub_items.append(
                {
                    "pncp_id": b.get("pncp_id"),
                    "objeto": (b.get("objeto") or "")[:220],
                    "valor_estimado": b.get("valor_estimado"),
                    "modalidade": b.get("modalidade"),
                    "uf": b.get("uf"),
                    "municipio": b.get("municipio"),
                    "orgao_nome": b.get("orgao_nome"),
                    "data_encerramento": b.get("data_encerramento"),
                    "link_pncp": b.get("link_pncp"),
                    "source": b.get("source") or "pncp",
                }
            )
        out.append(
            {
                "id": f"radar-{slug}",
                "slug": slug,
                "segment": label,
                "region": uf,
                "region_label": _uf_label(uf),
                "as_of": as_of,
                "open_count": len(items),
                "items": pub_items,
                "historical_count": 0,
                "sources": ["pncp"],
                "limitations": [
                    "Oportunidades sujeitas a alteração ou encerramento no portal de origem.",
                    "Não é monitoramento em tempo real; data de referência no campo as_of.",
                    "Página evergreen: não indexa um edital por URL.",
                ],
                "related_market_slug": related,
            }
        )
    return out


def build_problem_service_bridges() -> list[dict[str, Any]]:
    """Cross public patterns with existing CONFENGE technical clusters.

    Themes are only those sustainably linked to recurrent public contracting
    risk — not generic SEO filler.
    """
    return [
        {
            "id": "prob-orcamento-edital",
            "slug": "inconsistencia-orcamento-edital",
            "theme": "orcamento-edital",
            "problem_label": "Inconsistência entre orçamento de referência e edital",
            "observed_pattern": (
                "Contratos e editais de edificações e infraestrutura frequentemente "
                "exigem auditoria de planilha, data-base e composições antes da proposta. "
                "O padrão aparece em objetos com alta dispersão de valor no mesmo arquétipo."
            ),
            "evidence_count": None,  # filled by scorer from linked markets
            "related_archetypes": [
                "edificacoes-publicas",
                "pavimentacao-infraestrutura-viaria",
                "saneamento-hidraulica",
            ],
            "confenge_service_slug": "auditoria-orcamento-licitacao",
            "technical_guide_paths": [
                "/conteudos/orcamento-incompleto-edital-obra-publica/",
                "/conteudos/sinapi-ou-sicro-obra-publica/",
                "/conteudos/analise-edital-obra-publica-construtora/",
            ],
            "sources": ["pncp_supplier_contracts", "site-confenge-guides"],
            "limitations": [
                "Página de enquadramento problema→serviço; não substitui análise do edital concreto."
            ],
        },
        {
            "id": "prob-sinapi-sicro",
            "slug": "referencia-sinapi-sicro-margem",
            "theme": "sinapi-sicro",
            "problem_label": "Referência SINAPI/SICRO e risco de margem na proposta",
            "observed_pattern": (
                "Mercados de pavimentação e edificações usam referências distintas "
                "por natureza de serviço. Erro de referência ou produtividade vira "
                "deságio real após a assinatura."
            ),
            "evidence_count": None,
            "related_archetypes": [
                "pavimentacao-infraestrutura-viaria",
                "edificacoes-publicas",
            ],
            "confenge_service_slug": "auditoria-orcamento-licitacao",
            "technical_guide_paths": [
                "/conteudos/sinapi-ou-sicro-obra-publica/",
                "/conteudos/produtividade-sinapi-obra-publica/",
                "/conteudos/bdi-obra-publica/",
            ],
            "sources": ["site-confenge-guides", "pncp_supplier_contracts"],
            "limitations": [
                "Não publica coeficientes proprietários; orienta critério de escolha da referência."
            ],
        },
        {
            "id": "prob-medicao-glosa",
            "slug": "medicao-glosa-contratos-recorrentes",
            "theme": "medicao-glosa",
            "problem_label": "Medição e glosa em contratos com execução contínua",
            "observed_pattern": (
                "Arquétipos de manutenção predial e edificações com múltiplas medições "
                "concentram disputas de critério, diário de obra e parcela incontroversa."
            ),
            "evidence_count": None,
            "related_archetypes": [
                "manutencao-predial-engenharia",
                "edificacoes-publicas",
            ],
            "confenge_service_slug": "medicoes-glosas-obras-publicas",
            "technical_guide_paths": [
                "/conteudos/glosa-de-medicao-obra-publica/",
                "/conteudos/medicao-de-obra-publica-rejeitada/",
                "/conteudos/parcela-incontroversa-medicao-contrato-publico/",
            ],
            "sources": ["site-confenge-guides"],
            "limitations": [
                "Padrão qualitativo cruzado com densidade de contratos recorrentes no datalake."
            ],
        },
        {
            "id": "prob-aditivos-margem",
            "slug": "aditivos-e-risco-de-margem",
            "theme": "aditivos",
            "problem_label": "Aditivos, serviços extras e erosão de margem",
            "observed_pattern": (
                "Obras de edificações e saneamento concentram alterações de projeto e "
                "quantitativo. Sem registro contemporâneo, o aditivo vira custo absorvido."
            ),
            "evidence_count": None,
            "related_archetypes": [
                "edificacoes-publicas",
                "saneamento-hidraulica",
                "pavimentacao-infraestrutura-viaria",
            ],
            "confenge_service_slug": "aditivos-obras-publicas",
            "technical_guide_paths": [
                "/conteudos/aditivo-qualitativo-quantitativo/",
                "/conteudos/servico-nao-previsto-na-planilha-obra-publica/",
                "/conteudos/limite-aditivo-25-50-obra-publica/",
            ],
            "sources": ["site-confenge-guides"],
            "limitations": [
                "Não estima taxa de aditivo por órgão sem denominador documental completo."
            ],
        },
        {
            "id": "prob-reequilibrio",
            "slug": "reequilibrio-e-dispersao-de-precos",
            "theme": "reequilibrio",
            "problem_label": "Reequilíbrio diante de dispersão de preços e insumos",
            "observed_pattern": (
                "Alta dispersão (IQR) em benchmarks regionais sinaliza sensibilidade a "
                "insumos e logística — cenário em que reequilíbrio e matriz de riscos "
                "precisam estar preparados antes da execução."
            ),
            "evidence_count": None,
            "related_archetypes": [
                "pavimentacao-infraestrutura-viaria",
                "saneamento-hidraulica",
            ],
            "confenge_service_slug": "reequilibrio-obras-publicas",
            "technical_guide_paths": [
                "/conteudos/reequilibrio-economico-financeiro-obra-publica/",
                "/conteudos/matriz-de-riscos-reequilibrio-economico-financeiro/",
                "/conteudos/documentos-reequilibrio-obra-publica/",
            ],
            "sources": ["pncp_supplier_contracts", "site-confenge-guides"],
            "limitations": [
                "Dispersão de valor contratual não prova, por si, desequilíbrio em um contrato específico."
            ],
        },
    ]


def _short_object_label(obj: str, max_len: int = 72) -> str:
    t = re.sub(r"\s+", " ", (obj or "").strip())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rsplit(" ", 1)[0] + "…"


def _uf_label(uf: str) -> str:
    names = {
        "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
        "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
        "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
        "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
        "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
        "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina",
        "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
    }
    return names.get(uf, uf)


def _official_channels(uf: str | None) -> list[dict[str, str]]:
    channels = [
        {"name": "PNCP", "url": "https://pncp.gov.br/"},
        {"name": "Portal Nacional de Contratações Públicas — consultas", "url": "https://www.gov.br/pncp/pt-br"},
    ]
    if uf == "SC":
        channels.append(
            {"name": "Portal de Compras SC / transparência estadual", "url": "https://www.sc.gov.br/"}
        )
    return channels


def _mask_supplier_name(name: str | None) -> str:
    """Publish observed supplier names as they appear in public contracts.

    Names in PNCP awards are public. We still avoid attaching ICP scores.
    """
    if not name:
        return "Fornecedor não identificado na fonte"
    return re.sub(r"\s+", " ", name).strip()[:120]


def _value_band(total: float) -> str:
    if total < 100_000:
        return "ate_100k"
    if total < 1_000_000:
        return "100k_1m"
    if total < 10_000_000:
        return "1m_10m"
    return "acima_10m"


def _band_histogram(items: list[ClassifiedContract]) -> list[dict[str, Any]]:
    c: Counter[str] = Counter()
    for x in items:
        c[_value_band(x.valor)] += 1
    order = ["ate_100k", "100k_1m", "1m_10m", "acima_10m"]
    return [{"band": b, "contract_count": c.get(b, 0)} for b in order]


def _recent_supplier_changes(items: list[ClassifiedContract]) -> list[str]:
    # Split by year of publication if possible
    by_year: dict[str, set[str]] = defaultdict(set)
    for c in items:
        y = (c.data_publicacao or "")[:4]
        if y and c.fornecedor_cnpj:
            by_year[y].add(c.fornecedor_cnpj)
    years = sorted(by_year.keys())
    notes: list[str] = []
    if len(years) >= 2:
        prev, last = years[-2], years[-1]
        new = by_year[last] - by_year[prev]
        gone = by_year[prev] - by_year[last]
        notes.append(
            f"Entre {prev} e {last}: {len(new)} fornecedores novos observados e "
            f"{len(gone)} sem contrato no ano mais recente (no recorte do datalake)."
        )
    else:
        notes.append("Série temporal insuficiente para comparar entrada/saída de fornecedores.")
    return notes


def classify_bids(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        obj = r.get("objeto_compra") or r.get("objeto") or ""
        arches = classify_object(obj)
        if not arches:
            continue
        item = dict(r)
        item["objeto"] = obj
        item["archetypes"] = arches
        if item.get("valor_total_estimado") is not None and item.get("valor_estimado") is None:
            try:
                item["valor_estimado"] = float(item["valor_total_estimado"])
            except (TypeError, ValueError):
                item["valor_estimado"] = None
        out.append(item)
    return out


def attach_problem_evidence(
    problems: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    prices: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for p in problems:
        arches = set(p.get("related_archetypes") or [])
        n = sum(m["contract_count"] for m in markets if m.get("archetype_id") in arches)
        # boost with price dispersion evidence for reequilibrio theme
        if p.get("theme") == "reequilibrio":
            n += sum(
                1
                for pr in prices
                if pr.get("dispersion_iqr") and pr["dispersion_iqr"] > 0
                and pr.get("object_pattern") in arches
            )
        p["evidence_count"] = n
    return problems


def assemble_public_payload(
    classified: list[ClassifiedContract],
    open_bids: list[dict[str, Any]],
) -> dict[str, Any]:
    markets = build_markets(classified, open_bids)
    agencies = build_agencies(classified, open_bids)
    prices = build_prices(classified)
    competition = build_competition(classified)
    opportunities = build_opportunities(open_bids, markets)
    problems = attach_problem_evidence(build_problem_service_bridges(), markets, prices)
    archetypes = build_public_archetypes(classified)
    return {
        "archetypes": archetypes,
        "markets": markets,
        "agencies": agencies,
        "prices": prices,
        "competition": competition,
        "opportunities": opportunities,
        "problem_service": problems,
    }
