"""Organic Opportunity Engine — facts + demand graph → scored SEO opportunities.

Input: pSEO export snapshot (markets, problem_service, opportunities, agencies…)
       optional GSC query/page signals (list of dicts)
Output: SEO_OPPORTUNITIES document ordered by commercial Content Value Score.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from scripts.organic.demand_graph import DEMAND_NODES, demand_map, match_queries_to_nodes
from scripts.organic.gates import gate_from_opportunity
from scripts.organic.insights import insight_from_market, insight_from_problem_service
from scripts.organic.score import compute_content_value_score

SCHEMA_VERSION = "seo-opportunities-v1"


def load_pseo_snapshot(pseo_dir: Path | str) -> dict[str, Any]:
    """Load pSEO JSON bodies from a directory (web-cfg data/pseo or fixture)."""
    root = Path(pseo_dir)
    out: dict[str, Any] = {"_dir": str(root)}
    for name in (
        "markets",
        "problem_service",
        "opportunities",
        "agencies",
        "prices",
        "competition",
        "archetypes",
        "manifest",
        "registry",
    ):
        path = root / f"{name}.json"
        if path.exists():
            out[name] = json.loads(path.read_text(encoding="utf-8"))
        else:
            out[name] = [] if name != "manifest" and name != "registry" else {}
    return out


def _as_list(payload: Any, keys: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in keys:
            if isinstance(payload.get(k), list):
                return [x for x in payload[k] if isinstance(x, dict)]
    return []


def _service_fit_for_slug(slug: str | None) -> float:
    if not slug:
        return 0.2
    # Direct service pages = high fit
    high = {
        "reequilibrio-obras-publicas",
        "aditivos-obras-publicas",
        "medicoes-glosas-obras-publicas",
        "auditoria-orcamento-licitacao",
        "atrasos-prorrogacao-obras-publicas",
        "defesa-margem-contratos-publicos",
        "bid-room-licitacoes-obras",
        "acompanhamento-contratos-obras",
        "diretoria-b2g",
    }
    mid = {"metodologia-inteligencia", "diagnostico-pre-licitacao", "diagnostico-b2g-360"}
    if slug in high:
        return 0.95
    if slug in mid:
        return 0.7
    return 0.45


def _gsc_demand_strength(impressions: float, clicks: float, position: float) -> float:
    """Map sparse GSC signals to 0–1. High intent position beats raw volume."""
    if impressions <= 0 and clicks <= 0:
        return 0.15
    # Striking distance bonus
    pos_score = 0.0
    if 4 <= position <= 15:
        pos_score = 0.55
    elif 1 <= position < 4:
        pos_score = 0.7
    elif position > 15:
        pos_score = 0.25
    imp_score = min(1.0, impressions / 50.0) * 0.35
    click_score = min(1.0, clicks / 5.0) * 0.35
    ctr = (clicks / impressions) if impressions else 0
    ctr_penalty = 0.15 if impressions >= 20 and ctr < 0.02 else 0.0
    return max(0.0, min(1.0, pos_score + imp_score + click_score + ctr_penalty))


def _base_opportunity(
    *,
    oid: str,
    topic: str,
    cluster: str,
    intent: str,
    persona: str,
    jtbd: str,
    service_slug: str | None,
    service_path: str | None,
    action: str,
    rationale: str,
    proposed_url: str | None = None,
    existing_url: str | None = None,
    suggested_cta: str | None = None,
    suggested_internal_links: list[str] | None = None,
    unique_data: bool = False,
    datalake_evidence: dict[str, Any] | None = None,
    gsc_evidence: dict[str, Any] | None = None,
    demand_strength: float = 0.2,
    data_moat: float = 0.2,
    topical: float = 0.5,
    freshness: float = 0.3,
    competitive: float = 0.4,
    penalties: list[str] | None = None,
    confidence: float = 0.6,
    source: str = "demand_graph",
) -> dict[str, Any]:
    service_fit = _service_fit_for_slug(service_slug)
    scored = compute_content_value_score(
        intent_stage=intent,
        service_fit=service_fit,
        data_moat=data_moat,
        demand_evidence=demand_strength,
        topical_authority=topical,
        freshness_trigger=freshness,
        competitive_opportunity=competitive,
        penalties=penalties,
    )
    opp: dict[str, Any] = {
        "id": oid,
        "topic": topic,
        "cluster": cluster,
        "intent": intent,
        "persona": persona,
        "jtbd": jtbd,
        "commercial_fit": round(service_fit, 3),
        "service_fit": service_slug,
        "service_path": service_path,
        "demand_signal": {
            "strength": round(demand_strength, 3),
            "source": "gsc" if gsc_evidence else "inferred",
        },
        "search_console_evidence": gsc_evidence or {},
        "datalake_evidence": datalake_evidence or {},
        "unique_data_available": unique_data,
        "freshness": {"score": freshness},
        "competition": {"score": competitive},
        "cannibalization": {"risk": "cannibalization" in (penalties or []), "urls": []},
        "proposed_url": proposed_url,
        "existing_url": existing_url,
        "action": action,
        "score": scored["score"],
        "score_breakdown": scored["breakdown"],
        "score_penalties": scored["penalties"],
        "rationale": rationale,
        "suggested_cta": suggested_cta,
        "suggested_internal_links": suggested_internal_links or [],
        "confidence": confidence,
        "source": source,
        "service_fit_score": service_fit,
        "data_moat_score": data_moat,
        "demand_strength": demand_strength,
        "topical_authority_score": topical,
        "freshness_score": freshness,
        "competitive_score": competitive,
        "penalties": list(penalties or []),
    }
    gate = gate_from_opportunity(opp)
    opp["indexability_gate"] = {
        "indexable": gate["indexable"],
        "decision": gate["decision"],
        "fails": gate["fails"],
        "warnings": gate["warnings"],
    }
    if gate["indexable"] and action in {"create", "improve", "keep"}:
        opp["publishability"] = "indexable_candidate"
    elif action == "noindex":
        opp["publishability"] = "noindex"
    elif not gate["indexable"]:
        opp["publishability"] = "blocked_by_gate"
    else:
        opp["publishability"] = "needs_human"
    return opp


def opportunities_from_demand_nodes(
    *,
    gsc_by_node: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Seed opportunities from the demand graph, enriched by GSC if present."""
    gsc_by_node = gsc_by_node or {}
    out: list[dict[str, Any]] = []
    for node in DEMAND_NODES:
        g = gsc_by_node.get(node["id"]) or {}
        impressions = float(g.get("impressions") or 0)
        clicks = float(g.get("clicks") or 0)
        position = float(g.get("position") or 0)
        demand = _gsc_demand_strength(impressions, clicks, position)
        existing = node.get("existing_url") or node.get("service_path")
        action = "improve" if existing and (impressions > 0 or clicks > 0) else (
            "keep" if existing else "create"
        )
        if existing and impressions >= 20 and clicks == 0:
            action = "improve"
        penalties: list[str] = []
        if node.get("requires_data_moat") and not g.get("has_data"):
            # still create as tofu candidate; data market opps will fill moat
            pass
        if node["intent"] == "tofu" and demand < 0.2:
            penalties.append("commodity_content")

        # Existing service/editorial URLs carry site provenance (not thin pSEO)
        editorial_provenance = {
            "dataset": "web-cfg-editorial",
            "as_of": "site",
            "record_count": 1,
            "methodology": "Página de serviço/editorial já publicada no site Confenge",
            "limitations": ["Não é agregação do datalake; autoridade editorial + serviço."],
            "sources": ["site-confenge"],
            "confidence": 0.8,
        } if existing else {}

        out.append(
            _base_opportunity(
                oid=f"opp-{node['id']}",
                topic=node["question"],
                cluster=node["cluster"],
                intent=node["intent"],
                persona=node["persona"],
                jtbd=node["jtbd"],
                service_slug=node.get("service_slug"),
                service_path=node.get("service_path"),
                action=action,
                rationale=(
                    f"Necessidade canônica do grafo de demanda ({node['id']}): "
                    f"{node['problem']}"
                ),
                proposed_url=existing,
                existing_url=existing,
                suggested_cta=node.get("cta"),
                suggested_internal_links=[
                    p
                    for p in [
                        node.get("service_path"),
                        node.get("tool_path"),
                        existing,
                    ]
                    if p
                ],
                unique_data=False,
                datalake_evidence=editorial_provenance,
                gsc_evidence={
                    "impressions": impressions,
                    "clicks": clicks,
                    "position": position,
                    "matched_queries": g.get("queries") or [],
                }
                if g
                else {},
                demand_strength=max(demand, 0.35 if node["intent"] == "bofu" else 0.2),
                data_moat=0.15,
                topical=0.75 if node["intent"] != "tofu" else 0.55,
                freshness=0.4,
                competitive=0.55 if impressions > 0 else 0.35,
                penalties=penalties,
                confidence=0.75 if g else 0.55,
                source="demand_graph",
            )
        )
    return out


def opportunities_from_markets(markets: list[dict[str, Any]], *, as_of: str) -> list[dict[str, Any]]:
    """Data-driven market/benchmark opportunities (content moat)."""
    out: list[dict[str, Any]] = []
    for m in markets:
        insight = insight_from_market(m, as_of=as_of)
        n = int(insight["record_count"] or 0)
        region = (m.get("region") or "") or ""
        segment = m.get("archetype_id") or m.get("segment") or ""
        slug = m.get("slug") or m.get("id") or "market"
        # Prefer existing inteligencia/radar paths when shape matches
        proposed = f"/inteligencia/mercados/{slug}/" if not str(slug).startswith("market-") else (
            f"/inteligencia/mercados/{str(slug).replace('market-', '')}/"
        )
        # Known radar pattern: archetype-uf
        if m.get("archetype_id") and region and len(str(region)) == 2:
            proposed = f"/radar/{m['archetype_id']}-{str(region).lower()}/"

        data_moat = min(1.0, 0.4 + n / 40.0)
        penalties: list[str] = []
        if n < 8:
            penalties.append("thin_content")
            penalties.append("missing_evidence")
        if n < 5:
            penalties.append("low_differentiation")

        action = "create" if n >= 8 else "do_not_create"
        if n < 8:
            action = "noindex"

        out.append(
            _base_opportunity(
                oid=f"opp-market-{slug}",
                topic=insight["headline"],
                cluster="inteligencia-mercado",
                intent="tofu",
                persona="diretor-construtora",
                jtbd="Comparar o próprio mercado com evidência agregada proprietária",
                service_slug="metodologia-inteligencia",
                service_path="/metodologia-inteligencia/",
                action=action if action != "do_not_create" else "noindex",
                rationale=(
                    "Benchmark proprietário a partir do datalake; information gain "
                    "que LLM genérico não reproduz sem os mesmos dados e corte."
                ),
                proposed_url=proposed,
                existing_url=None,
                suggested_cta="Ver metodologia e limites da inteligência de mercado",
                suggested_internal_links=[
                    "/metodologia-inteligencia/",
                    "/radar/",
                    "/inteligencia/",
                    "/auditoria-orcamento-licitacao/",
                ],
                unique_data=n >= 8,
                datalake_evidence={
                    "dataset": insight["dataset"],
                    "as_of": insight["data_as_of"],
                    "record_count": n,
                    "methodology": insight["methodology"],
                    "limitations": insight["limitations"],
                    "sources": insight["sources"],
                    "confidence": insight["confidence"],
                    "result": insight["result"],
                    "insight_id": insight["insight_id"],
                },
                demand_strength=0.35,
                data_moat=data_moat,
                topical=0.7,
                freshness=0.8,
                competitive=0.65,
                penalties=penalties,
                confidence=float(insight["confidence"]),
                source="datalake_market",
            )
        )
    return out


def opportunities_from_problem_service(
    items: list[dict[str, Any]], *, as_of: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ps in items:
        insight = insight_from_problem_service(ps, as_of=as_of)
        service = ps.get("confenge_service_slug") or ps.get("service")
        guides = list(ps.get("technical_guide_paths") or [])
        existing = guides[0] if guides else (f"/{service}/" if service else None)
        evidence = int(ps.get("evidence_count") or 0)
        out.append(
            _base_opportunity(
                oid=f"opp-ps-{ps.get('id') or ps.get('slug')}",
                topic=str(ps.get("problem_label") or ps.get("problem") or "problema-serviço"),
                cluster=str(ps.get("theme") or "gestao-contratual"),
                intent="mofu",
                persona="gerente-contratos",
                jtbd="Enquadrar o problema no serviço Confenge certo com evidência",
                service_slug=service,
                service_path=f"/{service}/" if service else None,
                action="improve" if existing else "create",
                rationale=str(ps.get("observed_pattern") or "")[:400],
                proposed_url=existing,
                existing_url=existing,
                suggested_cta=f"Ver serviço: {service}" if service else "Falar com a CONFENGE",
                suggested_internal_links=guides[:5] + ([f"/{service}/"] if service else []),
                unique_data=evidence >= 15,
                datalake_evidence={
                    "dataset": insight["dataset"],
                    "as_of": insight["data_as_of"],
                    "record_count": evidence,
                    "methodology": insight["methodology"],
                    "limitations": insight["limitations"],
                    "sources": insight["sources"],
                    "confidence": insight["confidence"],
                    "result": insight["result"],
                    "insight_id": insight["insight_id"],
                },
                demand_strength=0.45,
                data_moat=0.55 if evidence >= 20 else 0.35,
                topical=0.8,
                freshness=0.5,
                competitive=0.5,
                penalties=[] if evidence >= 15 else ["missing_evidence"],
                confidence=float(insight["confidence"]),
                source="datalake_problem_service",
            )
        )
    return out


def opportunities_from_radar(
    opps_payload: list[dict[str, Any]], *, as_of: str
) -> list[dict[str, Any]]:
    """Radar clusters with open items → freshness-triggered content refresh."""
    out: list[dict[str, Any]] = []
    for row in opps_payload:
        rid = str(row.get("id") or row.get("slug") or "radar")
        items = row.get("items") or []
        open_n = len(items) if isinstance(items, list) else int(row.get("open_count") or 0)
        hist = int(row.get("historical_count") or row.get("closed_recent_count") or 0)
        freshness = row.get("freshness") or {}
        age = float(freshness.get("age_hours") or 48)
        fresh_score = 0.9 if age <= 24 else 0.6 if age <= 72 else 0.25
        action = "improve" if open_n >= 3 else "noindex"
        penalties = []
        if open_n < 3:
            penalties.append("thin_content")
        out.append(
            _base_opportunity(
                oid=f"opp-radar-{rid}",
                topic=f"Radar: {rid} ({open_n} abertas)",
                cluster="radar-oportunidades",
                intent="tofu",
                persona="licitacoes",
                jtbd="Monitorar editais/contratos abertos no recorte com evidência fresca",
                service_slug="bid-room-licitacoes-obras",
                service_path="/bid-room-licitacoes-obras/",
                action=action,
                rationale=(
                    "Radar data-driven; só indexável com volume mínimo de itens abertos, "
                    "freshness e interpretação — não template por UF."
                ),
                proposed_url=f"/radar/{rid.replace('radar-', '')}/",
                existing_url=f"/radar/{rid.replace('radar-', '')}/",
                suggested_cta="Avaliar se a licitação cabe no perfil da construtora",
                suggested_internal_links=["/radar/", "/bid-room-licitacoes-obras/", "/diagnostico-pre-licitacao/"],
                unique_data=open_n >= 3,
                datalake_evidence={
                    "dataset": "pncp_open_opportunities",
                    "as_of": as_of,
                    "record_count": open_n,
                    "historical_count": hist,
                    "methodology": "Open-status filter on bids; never treat history as open",
                    "limitations": [
                        "Status pode mudar após o corte; sempre verificar fonte oficial."
                    ],
                    "sources": ["pncp"],
                    "confidence": 0.65 if open_n >= 3 else 0.3,
                    "freshness": freshness,
                },
                demand_strength=0.3,
                data_moat=0.5 if open_n >= 3 else 0.15,
                topical=0.5,
                freshness=fresh_score,
                competitive=0.45,
                penalties=penalties,
                confidence=0.65 if open_n >= 3 else 0.35,
                source="datalake_radar",
            )
        )
    return out


def build_opportunities(
    snapshot: dict[str, Any],
    *,
    gsc_queries: list[dict[str, Any]] | None = None,
    gsc_pages: list[dict[str, Any]] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Core pure entry: snapshot + optional GSC → ranked SEO_OPPORTUNITIES doc."""
    as_of = as_of or date.today().isoformat()
    markets = _as_list(snapshot.get("markets"), ("markets", "items"))
    problems = _as_list(snapshot.get("problem_service"), ("items", "problems"))
    radar = _as_list(snapshot.get("opportunities"), ("items", "opportunities"))

    gsc_by_node: dict[str, dict[str, Any]] = {}
    if gsc_queries:
        for m in match_queries_to_nodes(gsc_queries):
            bucket = gsc_by_node.setdefault(
                m["node_id"],
                {"impressions": 0.0, "clicks": 0.0, "position": 0.0, "queries": [], "pos_w": 0.0},
            )
            bucket["impressions"] += m["impressions"]
            bucket["clicks"] += m["clicks"]
            if m["position"] > 0:
                bucket["pos_w"] += m["position"] * max(m["impressions"], 1)
                bucket["queries"].append(m["query"])
        for nid, b in gsc_by_node.items():
            imp = b["impressions"] or 1
            b["position"] = b["pos_w"] / imp if b["pos_w"] else 0

    # Enrich GSC pages into demand (path → cluster heuristics)
    page_signals: list[dict[str, Any]] = []
    for p in gsc_pages or []:
        url = str(p.get("page") or p.get("Páginas principais") or "")
        page_signals.append(
            {
                "url": url,
                "clicks": float(p.get("clicks") or p.get("Cliques") or 0),
                "impressions": float(p.get("impressions") or p.get("Impressões") or 0),
                "position": float(p.get("position") or p.get("Posição") or 0),
            }
        )

    opps: list[dict[str, Any]] = []
    opps.extend(opportunities_from_demand_nodes(gsc_by_node=gsc_by_node))
    opps.extend(opportunities_from_markets(markets, as_of=as_of))
    opps.extend(opportunities_from_problem_service(problems, as_of=as_of))
    opps.extend(opportunities_from_radar(radar, as_of=as_of))

    # Attach page-level improve actions for high-impression low-CTR URLs
    for ps in page_signals:
        if ps["impressions"] >= 15 and ps["clicks"] <= 0 and ps["url"]:
            path = ps["url"].replace("https://confenge.com.br", "").replace("http://confenge.com.br", "")
            if not path.startswith("/"):
                path = "/" + path
            # Map path fragment → service for contextual CTA
            svc_slug, svc_path, cluster = _service_from_path(path)
            opps.append(
                _base_opportunity(
                    oid=f"opp-gsc-ctr-{abs(hash(path)) % 10_000_000}",
                    topic=f"CTR opportunity: {path}",
                    cluster=cluster or "gsc-feedback",
                    intent="mofu",
                    persona="orcamentista",
                    jtbd="Corrigir título/meta para capturar impressões existentes",
                    service_slug=svc_slug,
                    service_path=svc_path,
                    action="improve",
                    rationale=(
                        f"Muitas impressões ({ps['impressions']}) e CTR ~0 na posição "
                        f"{ps['position']:.1f} — reescrever title/meta e reforçar CTA."
                    ),
                    proposed_url=path,
                    existing_url=path,
                    suggested_cta=(
                        "Auditar orçamento e BDI do edital"
                        if "sinapi" in path or "bdi" in path or "orcamento" in path
                        else "Analisar meu caso com a CONFENGE"
                    ),
                    suggested_internal_links=[p for p in [path, svc_path] if p],
                    unique_data=False,
                    datalake_evidence={
                        "dataset": "web-cfg-editorial",
                        "as_of": "gsc",
                        "record_count": 1,
                        "methodology": "GSC page-level striking distance / CTR signal",
                        "limitations": ["Amostra GSC limitada no export disponível."],
                        "sources": ["google-search-console"],
                        "confidence": 0.75,
                    },
                    gsc_evidence=ps,
                    demand_strength=_gsc_demand_strength(ps["impressions"], ps["clicks"], ps["position"]),
                    data_moat=0.1,
                    topical=0.6,
                    freshness=0.7,
                    competitive=0.6,
                    penalties=[],
                    confidence=0.8,
                    source="gsc_page",
                )
            )

    # Dedupe by id, keep highest score
    by_id: dict[str, dict[str, Any]] = {}
    for o in opps:
        prev = by_id.get(o["id"])
        if not prev or o["score"] > prev["score"]:
            by_id[o["id"]] = o
    ranked = sorted(by_id.values(), key=lambda x: (-int(x["score"]), x["id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "north_star": "receita_esperada_atribuivel_ao_inbound_organico",
        "scoring": {
            "model": "content_value_score",
            "weights": {
                "commercial_intent": 25,
                "service_fit": 20,
                "data_moat": 20,
                "demand_evidence": 15,
                "topical_authority": 10,
                "freshness_trigger": 5,
                "competitive_opportunity": 5,
            },
        },
        "counts": {
            "total": len(ranked),
            "by_action": _count_by(ranked, "action"),
            "by_intent": _count_by(ranked, "intent"),
            "by_publishability": _count_by(ranked, "publishability"),
            "bofu": sum(1 for o in ranked if o["intent"] == "bofu"),
            "data_driven": sum(1 for o in ranked if o.get("unique_data_available")),
        },
        "demand_map_ref": "persona → problem → question → intent → service",
        "opportunities": ranked,
    }


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key) or "?")
        out[k] = out.get(k, 0) + 1
    return out


def _service_from_path(path: str) -> tuple[str | None, str | None, str | None]:
    p = path.lower()
    rules = [
        (("reequil", "reajuste", "repactua"), "reequilibrio-obras-publicas", "/reequilibrio-obras-publicas/", "reequilibrio"),
        (("aditivo", "acréscimo", "acrescimo", "supress"), "aditivos-obras-publicas", "/aditivos-obras-publicas/", "aditivos"),
        (("medicao", "medição", "glosa", "pagamento"), "medicoes-glosas-obras-publicas", "/medicoes-glosas-obras-publicas/", "medicoes-pagamentos"),
        (("atraso", "prorroga", "notificacao", "notificação"), "atrasos-prorrogacao-obras-publicas", "/atrasos-prorrogacao-obras-publicas/", "atrasos-prorrogacao"),
        (("sinapi", "sicro", "bdi", "orcamento", "orçamento", "desonerad"), "auditoria-orcamento-licitacao", "/auditoria-orcamento-licitacao/", "orcamento-bdi"),
        (("edital", "licita", "proposta"), "bid-room-licitacoes-obras", "/bid-room-licitacoes-obras/", "edital-proposta"),
    ]
    for keys, slug, spath, cluster in rules:
        if any(k in p for k in keys):
            return slug, spath, cluster
    return None, None, None


def run_engine(
    *,
    pseo_dir: Path | str,
    out_path: Path | str | None = None,
    gsc_queries: list[dict[str, Any]] | None = None,
    gsc_pages: list[dict[str, Any]] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """CLI-friendly: load snapshot, build, optionally write JSON."""
    snap = load_pseo_snapshot(pseo_dir)
    doc = build_opportunities(
        snap, gsc_queries=gsc_queries, gsc_pages=gsc_pages, as_of=as_of
    )
    doc["demand_map"] = demand_map()
    if out_path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        doc["_written"] = str(path)
    return doc
