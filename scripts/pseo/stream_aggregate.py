"""Memory-bounded aggregation from SQLite staging — no full classified/bids lists.

Streams ``StagingStore.iter_*`` batches and keeps only reducer state:
- float value vectors per bucket (for exact percentiles)
- counters / limited sample strings
- open bids list capped for public opportunities

Never calls ``load_all_classified`` / ``load_all_bids``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import date
from typing import Any

from scripts.pseo.aggregate import (
    MIN_VALOR_BENCHMARK,
    _cnpj8,
    _official_channels,
    _pct,
    _short_object_label,
    _slugify,
    _uf_label,
)
from scripts.pseo.archetypes import ARCHETYPE_DEFS, METHODOLOGY, ClassifiedContract
from scripts.pseo.classifiers import primary_archetype
from scripts.pseo.opportunities import classify_bid_status
from scripts.pseo.staging import StagingStore

# Max closed bids retained for opportunity context (public samples only)
_MAX_CLOSED_KEEP = 1000
_MAX_OPEN_KEEP = 5000
_MAX_EXAMPLES = 5
_MAX_TOP = 8


def _mask_supplier_name(name: str | None) -> str:
    if not name:
        return "Fornecedor"
    s = str(name).strip()
    if len(s) <= 4:
        return "Fornecedor"
    return s[:3] + "…"


def stream_filter_bids(
    store: StagingStore,
    *,
    as_of: date,
    max_open: int = _MAX_OPEN_KEEP,
    max_closed: int = _MAX_CLOSED_KEEP,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int], int]:
    open_bids: list[dict[str, Any]] = []
    closed_bids: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    n_total = 0
    n_open_all = 0
    n_closed_all = 0
    for batch in store.iter_bids(chunk_size=5_000):
        n_total += len(batch)
        for b in batch:
            decision = classify_bid_status(b, as_of=as_of)
            enriched = dict(b)
            enriched["open_decision"] = decision
            bucket = decision["status_bucket"]
            counts[bucket] = counts.get(bucket, 0) + 1
            if decision["is_open"]:
                n_open_all += 1
                if len(open_bids) < max_open:
                    open_bids.append(enriched)
            else:
                n_closed_all += 1
                if len(closed_bids) < max_closed:
                    closed_bids.append(enriched)
    counts["open_total"] = n_open_all
    counts["closed_total"] = n_closed_all
    counts["open_retained"] = len(open_bids)
    counts["closed_retained"] = len(closed_bids)
    return open_bids, closed_bids, counts, n_total


def _iter_contracts(store: StagingStore) -> Iterator[ClassifiedContract]:
    for batch in store.iter_classified(chunk_size=5_000):
        yield from batch
        # batch goes out of scope after yield-from completes each batch


def build_markets_streaming(
    store: StagingStore,
    open_bids: list[dict[str, Any]],
    *,
    min_contracts: int = 10,
    min_buyers: int = 3,
) -> list[dict[str, Any]]:
    """Single pass over staging classified → market reducers (no full list)."""
    # reducer: (arch, uf) → state
    vals: dict[tuple[str, str], list[float]] = defaultdict(list)
    buyers: dict[tuple[str, str], set[str]] = defaultdict(set)
    suppliers: dict[tuple[str, str], set[str]] = defaultdict(set)
    sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    bstats: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    obj_counter: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    obj_example: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    by_year: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    value_year: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    dates: dict[tuple[str, str], list[str]] = defaultdict(list)

    for c in _iter_contracts(store):
        if not c.uf:
            continue
        primary = primary_archetype(c.archetypes, c.objeto)
        if not primary:
            continue
        key = (primary, c.uf)
        vals[key].append(c.valor)
        bk = c.orgao_cnpj or c.orgao_nome
        if bk:
            buyers[key].add(bk)
        if c.fornecedor_cnpj:
            suppliers[key].add(c.fornecedor_cnpj)
        if c.source:
            sources[key].add(c.source)
        bkey = c.orgao_cnpj or c.orgao_nome or "?"
        st = bstats[key].setdefault(
            bkey,
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
        label = _short_object_label(c.objeto)
        obj_counter[key][label] += 1
        obj_example[key].setdefault(label, (c.objeto or "")[:200])
        y = (c.data_publicacao or "")[:4]
        if y:
            by_year[key][y] += 1
            value_year[key][y] += c.valor
        if c.data_publicacao:
            dates[key].append(str(c.data_publicacao)[:10])

    markets: list[dict[str, Any]] = []
    for key, vlist in sorted(vals.items(), key=lambda kv: -len(kv[1])):
        arch, uf = key
        if len(vlist) < min_contracts or len(buyers[key]) < min_buyers:
            continue
        dlist = dates[key]
        p_start = min(dlist) if dlist else None
        p_end = max(dlist) if dlist else None
        top_buyers = sorted(bstats[key].values(), key=lambda x: -x["contract_count"])[:_MAX_TOP]
        for b in top_buyers:
            b["total_value"] = round(b["total_value"], 2)
        top_objects = [
            {
                "label": lab,
                "count": n,
                "median_value": None,
                "example_objeto": obj_example[key].get(lab, lab),
            }
            for lab, n in obj_counter[key].most_common(_MAX_TOP)
        ]
        value_by_year = [
            {
                "year": y,
                "contract_count": by_year[key][y],
                "total_value": round(value_year[key][y], 2),
            }
            for y in sorted(by_year[key].keys())
        ]
        open_n = sum(
            1
            for b in open_bids
            if primary_archetype(b.get("archetypes") or [], b.get("objeto")) == arch
            and b.get("uf") == uf
        )
        label = ARCHETYPE_DEFS[arch]["label"]
        slug = f"{arch}-{uf.lower()}"
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
                "contract_count": len(vlist),
                "buyer_count": len(buyers[key]),
                "supplier_count": len(suppliers[key]),
                "total_value": round(sum(vlist), 2),
                "median_value": _pct(vlist, 50),
                "p25_value": _pct(vlist, 25),
                "p75_value": _pct(vlist, 75),
                "top_buyers": top_buyers,
                "top_objects": top_objects,
                "value_by_year": value_by_year,
                "modalities": [],
                "open_opportunity_count": open_n,
                "sources": sorted(sources[key]),
                "limitations": [
                    f"Base: {len(vlist)} contratos com arquétipo primário {arch} em {uf}; "
                    "multi-rótulo entra só no primário.",
                    "Não representa o universo total de contratações.",
                    "Valores nominais sem deflacionamento.",
                    "Objetos heterogêneos; mediana não é preço unitário.",
                ],
                "interpretation_hooks": [
                    f"Concentração em {len(buyers[key])} órgãos compradores distintos.",
                    f"{len(suppliers[key])} fornecedores observados no recorte.",
                    f"Oportunidades abertas no radar (mesmo recorte): {open_n}.",
                ],
            }
        )
    return markets


def build_agencies_streaming(
    store: StagingStore,
    open_bids: list[dict[str, Any]],
    *,
    min_contracts: int = 12,
) -> list[dict[str, Any]]:
    vals: dict[str, list[float]] = defaultdict(list)
    meta: dict[str, dict[str, Any]] = {}
    mix: dict[str, Counter[str]] = defaultdict(Counter)
    months: dict[str, Counter[str]] = defaultdict(Counter)
    obj_counter: dict[str, Counter[str]] = defaultdict(Counter)
    suppliers: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, set[str]] = defaultdict(set)
    dates: dict[str, list[str]] = defaultdict(list)

    for c in _iter_contracts(store):
        key = c.orgao_cnpj or _slugify(c.orgao_nome or "")
        if not key:
            continue
        vals[key].append(c.valor)
        if key not in meta:
            meta[key] = {
                "name": c.orgao_nome or key,
                "uf": c.uf,
                "municipio": c.municipio,
                "cnpj8": c.orgao_cnpj,
            }
        for a in c.archetypes:
            mix[key][a] += 1
        if c.data_publicacao and len(c.data_publicacao) >= 7:
            months[key][c.data_publicacao[:7]] += 1
        obj_counter[key][_short_object_label(c.objeto)] += 1
        if c.fornecedor_cnpj:
            suppliers[key].add(c.fornecedor_cnpj)
        if c.source:
            sources[key].add(c.source)
        if c.data_publicacao:
            dates[key].append(str(c.data_publicacao)[:10])

    agencies: list[dict[str, Any]] = []
    for key, vlist in sorted(vals.items(), key=lambda kv: -len(kv[1])):
        if len(vlist) < min_contracts:
            continue
        m = meta[key]
        name = m["name"]
        uf = m["uf"]
        mun = m["municipio"]
        cnpj8 = m["cnpj8"]
        dlist = dates[key]
        p_start = min(dlist) if dlist else None
        p_end = max(dlist) if dlist else None
        seasonality = [
            {"period": mo, "contract_count": n}
            for mo, n in sorted(months[key].items())[-18:]
        ]
        top_objects = [
            {"label": lab, "count": n, "median_value": None, "example_objeto": lab}
            for lab, n in obj_counter[key].most_common(_MAX_TOP)
        ]
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
                "name": name,
                "cnpj8": cnpj8 or None,
                "orgao_nome": name,
                "uf": uf,
                "municipio": mun,
                "period_start": p_start,
                "period_end": p_end,
                "contract_count": len(vlist),
                "total_value": round(sum(vlist), 2),
                "median_value": _pct(vlist, 50),
                "p25_value": _pct(vlist, 25),
                "p75_value": _pct(vlist, 75),
                "archetype_ids": [a for a, _ in mix[key].most_common()],
                "related_archetypes": [a for a, _ in mix[key].most_common()],
                "archetype_mix": [
                    {"archetype_id": a, "contract_count": n}
                    for a, n in mix[key].most_common()
                ],
                "top_objects": top_objects,
                "modalities": [],
                "seasonality": seasonality,
                "supplier_count": len(suppliers[key]),
                "open_opportunities": open_ops,
                "official_channels": _official_channels(uf),
                "sources": sorted(sources[key]),
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


def build_prices_streaming(
    store: StagingStore,
    *,
    min_obs: int = 12,
) -> list[dict[str, Any]]:
    vals: dict[tuple[str, str], list[float]] = defaultdict(list)
    sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    dates: dict[tuple[str, str], list[str]] = defaultdict(list)
    examples: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for c in _iter_contracts(store):
        if not c.uf or c.valor < MIN_VALOR_BENCHMARK:
            continue
        for a in c.archetypes:
            key = (a, c.uf)
            vals[key].append(c.valor)
            if c.source:
                sources[key].add(c.source)
            if c.data_publicacao:
                dates[key].append(str(c.data_publicacao)[:10])
            ex = examples[key]
            if len(ex) < _MAX_EXAMPLES * 3:
                ex.append(
                    {
                        "objeto": (c.objeto or "")[:200],
                        "valor": c.valor,
                        "uf": c.uf,
                        "municipio": c.municipio,
                        "orgao_nome": c.orgao_nome,
                        "data_publicacao": c.data_publicacao,
                        "source": c.source,
                        "contrato_id": c.contrato_id,
                    }
                )

    prices: list[dict[str, Any]] = []
    for key, vlist in sorted(vals.items(), key=lambda kv: -len(kv[1])):
        if len(vlist) < min_obs:
            continue
        arch, uf = key
        p25, med, p75 = _pct(vlist, 25), _pct(vlist, 50), _pct(vlist, 75)
        iqr = (
            round((p75 or 0) - (p25 or 0), 2)
            if p25 is not None and p75 is not None
            else None
        )
        dlist = dates[key]
        p_start = min(dlist) if dlist else None
        p_end = max(dlist) if dlist else None
        ex_sorted = sorted(examples[key], key=lambda x: -float(x.get("valor") or 0))[
            :_MAX_EXAMPLES
        ]
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
                "observation_count": len(vlist),
                "n": len(vlist),
                "median_value": med,
                "mediana": med,
                "p25_value": p25,
                "p25": p25,
                "p75_value": p75,
                "p75": p75,
                "min_value": round(min(vlist), 2),
                "min": round(min(vlist), 2),
                "max_value": round(max(vlist), 2),
                "max": round(max(vlist), 2),
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
                "public_examples": ex_sorted,
                "sources": sorted(sources[key]),
                "limitations": [
                    "Observações são contratos integrais, não preços unitários de serviço.",
                    "Objetos dentro do mesmo arquétipo podem ser tecnicamente incomparáveis.",
                    "Percentis: ordenação exata sobre valores do bucket (streaming staging).",
                ],
                "warning": (
                    "Não use a mediana como preço de referência aplicável a qualquer "
                    "caso. Compare escopo, quantitativos, regime, data-base e localidade "
                    "antes de qualquer decisão de proposta."
                ),
            }
        )
    return prices


def build_competition_streaming(
    store: StagingStore,
    *,
    min_contracts: int = 15,
) -> list[dict[str, Any]]:
    from scripts.pseo.aggregate import _band_histogram, _value_band

    by_sup: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    n_contracts: dict[tuple[str, str], int] = defaultdict(int)
    sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    agencies: dict[tuple[str, str], set[str]] = defaultdict(set)
    dates: dict[tuple[str, str], list[str]] = defaultdict(list)
    # lightweight rows for value_bands only (valor floats + primary already keyed)
    band_vals: dict[tuple[str, str], list[float]] = defaultdict(list)

    for c in _iter_contracts(store):
        if not c.uf:
            continue
        primary = primary_archetype(c.archetypes, c.objeto)
        if not primary:
            continue
        key = (primary, c.uf)
        n_contracts[key] += 1
        band_vals[key].append(c.valor)
        sk = c.fornecedor_cnpj or c.fornecedor_nome or "?"
        st = by_sup[key].setdefault(
            sk,
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
            agencies[key].add(c.orgao_cnpj or c.orgao_nome)
        if c.source:
            sources[key].add(c.source)
        if c.data_publicacao:
            dates[key].append(str(c.data_publicacao)[:10])

    out: list[dict[str, Any]] = []
    for key, n in sorted(n_contracts.items(), key=lambda kv: -kv[1]):
        if n < min_contracts:
            continue
        arch, uf = key
        ranked = sorted(by_sup[key].values(), key=lambda x: -x["contract_count"])
        total_c = sum(s["contract_count"] for s in ranked) or 1
        top3 = ranked[:3]
        share = round(sum(s["contract_count"] for s in top3) / total_c, 4)
        observed = []
        for s in ranked[:12]:
            observed.append(
                {
                    "display_name": s["display_name"],
                    "contract_count": s["contract_count"],
                    "total_value": round(s["total_value"], 2),
                    "agencies_count": len(s["agencies"]),
                    "value_band": _value_band(s["total_value"]),
                }
            )
        dlist = dates[key]
        p_start = min(dlist) if dlist else None
        p_end = max(dlist) if dlist else None
        # synthetic ClassifiedContract-like for band histogram via floats only
        class _V:
            def __init__(self, v: float) -> None:
                self.valor = v

        value_bands = _band_histogram([_V(v) for v in band_vals[key]])  # type: ignore[list-item]
        label = ARCHETYPE_DEFS[arch]["label"]
        slug = f"{arch}-{uf.lower()}"
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
                "contract_count": n,
                "observed_suppliers": observed,
                "concentration_top3_share": share,
                "agencies_with_activity": len(agencies[key]),
                "value_bands": value_bands,
                "recent_changes": [],
                "sources": sorted(sources[key]),
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


def build_archetypes_streaming(store: StagingStore) -> list[dict[str, Any]]:
    per_arch_vals: dict[str, list[float]] = defaultdict(list)
    per_arch_ufs: dict[str, Counter[str]] = defaultdict(Counter)
    per_arch_buyers: dict[str, set[str]] = defaultdict(set)
    per_arch_buyer_types: dict[str, Counter[str]] = defaultdict(Counter)

    for c in _iter_contracts(store):
        for arch_id in c.archetypes:
            if arch_id not in ARCHETYPE_DEFS:
                continue
            if c.valor and c.valor > 0:
                per_arch_vals[arch_id].append(c.valor)
            if c.uf:
                per_arch_ufs[arch_id][c.uf] += 1
            bk = c.orgao_cnpj or c.orgao_nome
            if bk:
                per_arch_buyers[arch_id].add(bk)
            name = (c.orgao_nome or "").lower()
            if "prefeitura" in name or "municip" in name:
                per_arch_buyer_types[arch_id]["municipal"] += 1
            elif "secretaria" in name or "estado" in name or "governo" in name:
                per_arch_buyer_types[arch_id]["estadual"] += 1
            elif "universidade" in name or "instituto" in name or "fundação" in name:
                per_arch_buyer_types[arch_id]["autarquia_fundacao"] += 1
            elif "união" in name or "ministerio" in name or "ministério" in name:
                per_arch_buyer_types[arch_id]["federal"] += 1
            else:
                per_arch_buyer_types[arch_id]["outro"] += 1

    out: list[dict[str, Any]] = []
    for arch_id, meta in ARCHETYPE_DEFS.items():
        vals = sorted(per_arch_vals.get(arch_id) or [])
        if len(vals) < 10:
            continue
        ufs = per_arch_ufs[arch_id]
        buyers = per_arch_buyers[arch_id]
        types = per_arch_buyer_types[arch_id]
        band = {
            "p25": _pct(vals, 25),
            "median": _pct(vals, 50),
            "p75": _pct(vals, 75),
            "n": len(vals),
            "currency": "BRL",
        }
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
                "modalities_observed": [],
                "buyer_types_observed": [
                    {"type": t, "contract_count": n} for t, n in types.most_common()
                ],
                "confenge_service_slugs": list(meta["confenge_service_slugs"]),
                "evidence_contract_count": len(vals),
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


def freshness_dates_streaming(
    store: StagingStore,
) -> tuple[list[str], list[str]]:
    """Collect date strings only (scalars) — not full rows."""
    contract_dates: list[str] = []
    bid_dates: list[str] = []
    for batch in store.iter_classified(chunk_size=5_000):
        for c in batch:
            if c.data_publicacao:
                contract_dates.append(str(c.data_publicacao)[:10])
    for batch in store.iter_bids(chunk_size=5_000):
        for b in batch:
            for k in ("data_publicacao", "data_encerramento", "data_abertura"):
                if b.get(k):
                    bid_dates.append(str(b[k])[:10])
    return contract_dates, bid_dates
