"""Operator-friendly cards. One account per card. Immediately usable."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    FirstClassRouteKind,
    FirstClassRouteLabel,
)
from scripts.decision_unit_intelligence.repository import write_json


def build_card(account: AccountInvestigation) -> dict[str, Any]:
    people = {c.candidate_id: c for c in account.candidates}
    routes = {r.route_id: r for r in account.routes}
    rec = account.recommendation
    primary = people.get(rec.primary_target_id) if rec and rec.primary_target_id else None
    route = routes.get(rec.primary_route_id) if rec and rec.primary_route_id else None
    secondary = [people[i] for i in (rec.secondary_target_ids if rec else []) if i in people]
    alts = [routes[i] for i in (rec.alternative_route_ids if rec else []) if i in routes]
    action = ""
    do_not_claim = []
    relation = route.route_relation.value if route else None
    if route:
        action = route.next_action or ""
    if relation == "ROUTES_TO_NAMED_PERSON":
        do_not_claim.append("Não alegar contato direto: o canal apenas roteia até a pessoa nomeada.")
        if route and route.channel_type.value in {"COMPANY_SWITCHBOARD", "DIRECT_PHONE"}:
            do_not_claim.append("Não alegar que o telefone pertence à pessoa.")
    email_verification = route.extra.get("email_verification") if route else None
    verification_status = _operator_verification_status(email_verification)
    evidence = _lean_evidence(account, route)
    lean_route = {
        "kind": (route.first_class_kind.value if route else FirstClassRouteKind.MANUAL_RESEARCH.value),
        "label": (route.first_class_label.value if route else FirstClassRouteLabel.UNKNOWN.value),
        "channel": route.channel_value if route else None,
        "channel_type": route.channel_type.value if route else None,
        "reachability_class": route.reachability_class.value if route else None,
        "action_mode": rec.action_mode.value if rec else None,
        "relation": relation,
        "source": route.source_type if route else None,
        "observed_at": route.observed_at if route else None,
        "freshness": route.freshness.value if route else None,
        "epistemic_class": route.epistemic_class.value if route else None,
        "suitability": route.suitability.value if route else None,
        "suppression": route.suppression.value if route else None,
        "reason_codes": list(route.reason_codes) if route else [],
    }
    return {
        "who": primary.person_name if primary else None,
        "why_now": account.why_now,
        "offer": account.service_context,
        "decision_unit": {
            "person": primary.person_name if primary else None,
            "role": primary.decision_role_class.value if primary else None,
            "observed_roles": primary.observed_roles if primary else [],
        },
        "route": lean_route,
        "confidence": route.route_confidence.value if route else None,
        "evidence": evidence,
        "empresa": account.legal_name,
        "cnpj": account.cnpj,
        "oferta_recomendada": account.service_context,
        "primary_decision_unit_target": primary.person_name if primary else None,
        "role_evidence": {
            "observed_roles": primary.observed_roles if primary else [],
            "decision_role_class": primary.decision_role_class.value if primary else None,
            "role_confidence": primary.role_confidence.value if primary else None,
            "reason_codes": primary.reason_codes if primary else [],
            "evidence_ids": primary.evidence_ids if primary else [],
            "source_count": primary.source_count if primary else 0,
            "aspects": [a.to_dict() if hasattr(a, "to_dict") else a for a in (primary.aspects if primary else [])],
            "inferred_decision_relevance": primary.inferred_decision_relevance if primary else None,
        },
        "primary_route": route.channel_type.value if route else None,
        "route_class": route.reachability_class.value if route else account.extra.get("account_reachability_class"),
        "route_relation": relation,
        "route_reason_codes": list(route.reason_codes) if route else [],
        "channel_source_type": route.source_type if route else None,
        "channel_source_url": route.source_url if route else None,
        "channel_epistemic_class": route.epistemic_class.value if route else None,
        "channel_ownership": route.ownership.value if route else None,
        "route_freshness": route.freshness.value if route else None,
        "route_suppression": route.suppression.value if route else None,
        "route_confidence": route.route_confidence.value if route else None,
        "email_verification": email_verification,
        "email_verification_reports": account.extra.get("email_verification", []),
        "verification_status": verification_status,
        "email_discovery_class": (route.extra or {}).get("email_discovery_class") if route else None,
        "identity_explicitly_associated": (route.extra or {}).get("identity_explicitly_associated") if route else None,
        # Passive DNS/MX never makes a route send-ready or proves a mailbox/person.
        "email_send_ready": False,
        "domain_resolution": account.extra.get("domain_resolution"),
        "action_mode": rec.action_mode.value if rec else None,
        "channel": route.channel_value if route else None,
        "exact_next_action": action or (rec.next_action if rec else None),
        "secondary_target": secondary[0].person_name if secondary else None,
        "alternative_routes": [
            {
                "class": a.reachability_class.value,
                "channel_type": a.channel_type.value,
                "channel": a.channel_value,
                "action": a.action_mode.value,
                "epistemic_class": a.epistemic_class.value,
                "verification": a.extra.get("email_verification"),
            }
            for a in alts
        ],
        "confidence_dimensions": rec.dimensions if rec else {},
        "evidence_links": list(
            dict.fromkeys(
                [r.source_url for r in account.routes if r.source_url]
                + [e.source_url for e in account.evidence if e.source_url]
            )
        ),
        "field_evidence": [e.to_dict() for e in account.evidence],
        "warnings": account.warnings + (rec.warnings if rec else []),
        "do_not_claim": do_not_claim,
        "terminal": account.terminal.value,
    }


def _lean_evidence(account: AccountInvestigation, route: object) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if route is not None:
        items.append(
            {
                "source": getattr(route, "source_type", None),
                "url": getattr(route, "source_url", None),
                "observed_at": getattr(route, "observed_at", None),
                "channel": getattr(route, "channel_value", None),
            }
        )
    for ev in account.evidence:
        items.append(
            {
                "source": ev.source_type,
                "url": ev.source_url,
                "observed_at": ev.observed_at,
                "field": ev.field,
                "value": ev.value,
            }
        )
    seen: set[tuple[object, object, object]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = (item.get("source"), item.get("url"), item.get("value") or item.get("channel"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:8]


def _operator_verification_status(report: object) -> str:
    if not isinstance(report, dict):
        return "NOT_FOUND"
    classification = str(report.get("final_classification") or "").upper()
    if classification in {"GENERIC_MAILBOX", "GENERIC_ROLE_MAILBOX"}:
        return "INSTITUTIONAL_GENERIC"
    return "CANDIDATE_UNVERIFIED"


def render_markdown(cards: list[dict[str, Any]]) -> str:
    lines = [
        "# Decision-Unit Reachability — pack operacional",
        "",
        "Cada card é uma próxima ação humana. E-mail não é o produto.",
        "",
    ]
    for card in cards:
        lines.extend(
            [
                f"## {card.get('empresa') or card.get('cnpj')}",
                f"- Who: **{card.get('who') or '—'}**",
                f"- Why now: {card.get('why_now') or 'n/d'}",
                f"- Offer: `{card.get('offer') or card.get('oferta_recomendada')}`",
                f"- Decision unit: {card.get('decision_unit')}",
                f"- Route: `{((card.get('route') or {}).get('kind'))}` / `{((card.get('route') or {}).get('label'))}` `{((card.get('route') or {}).get('channel'))}`",
                f"- Confidence: `{card.get('confidence')}`",
                f"- Evidence: {card.get('evidence')}",
                f"- CNPJ: `{card.get('cnpj')}`",
                f"- Oferta: `{card.get('oferta_recomendada')}`",
                f"- Primary target: **{card.get('primary_decision_unit_target') or '—'}**",
                f"- Papel/evidência: {card.get('role_evidence')}",
                f"- Primary route: `{card.get('primary_route')}` / `{card.get('route_class')}`",
                f"- Relação canal↔pessoa: `{card.get('route_relation') or '—'}`",
                f"- Reason codes da rota: {card.get('route_reason_codes')}",
                f"- Provenance do canal: `{card.get('channel_source_type')}` / `{card.get('channel_epistemic_class')}` / `{card.get('channel_ownership')}`",
                f"- Domínio: {card.get('domain_resolution')}",
                f"- Verificação de e-mail: {card.get('email_verification')}",
                f"- Verificações de rotas alternativas: {card.get('email_verification_reports')}",
                f"- Action mode: `{card.get('action_mode')}`",
                f"- Canal: `{card.get('channel')}`",
                f"- **AÇÃO:** {card.get('exact_next_action')}",
                f"- Secondary: {card.get('secondary_target') or '—'}",
                f"- Alternativas: {card.get('alternative_routes')}",
                f"- Dimensões: {card.get('confidence_dimensions')}",
                f"- Evidence: {card.get('evidence_links')}",
                f"- Warnings: {card.get('warnings')}",
                f"- Terminal: `{card.get('terminal')}`",
            ]
        )
        for w in card.get("do_not_claim") or []:
            lines.append(f"- **NÃO ALEGAR:** {w}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_operator_pack(cards: list[dict[str, Any]], directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "cards.json"
    md_path = directory / "cards.md"
    write_json(json_path, {"n": len(cards), "cards": cards})
    md_path.write_text(render_markdown(cards), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}
