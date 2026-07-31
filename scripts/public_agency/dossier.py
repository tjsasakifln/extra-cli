"""Per-agency commercial dossier generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def render_dossier_markdown(lead: dict[str, Any]) -> str:
    agency = lead.get("agency") or {}
    score = lead.get("score") or {}
    signals = lead.get("signals") or []
    classification = lead.get("object_classification") or {}
    eligibility = lead.get("eligibility") or {}
    fragmentation = lead.get("fragmentation") or {}
    conflict = lead.get("conflict") or {}
    service = lead.get("selected_service") or {}
    contacts = lead.get("contacts") or {}
    mode = lead.get("mode") or "PROACTIVE_INSTITUTIONAL_PROSPECT"
    pub = lead.get("publishability") or {}

    fired = [s for s in signals if s.get("status") == "FIRED"]
    facts = []
    if agency.get("cnpj"):
        facts.append(f"CNPJ: {agency.get('cnpj')}")
    if agency.get("nome_oficial"):
        facts.append(f"Nome: {agency.get('nome_oficial')}")
    if agency.get("uf"):
        facts.append(f"UF: {agency.get('uf')}")
    if agency.get("populacao") is not None:
        facts.append(f"População (IBGE): {agency.get('populacao')}")

    inferences = [
        f"Modo: {mode}",
        f"Oferta sugerida: {service.get('service_id') or score.get('selected_service_id')}",
        f"Score: {score.get('priority_score')}",
    ]
    hypotheses = [
        "Sinais de possível necessidade técnica"
        if mode == "PROACTIVE_INSTITUTIONAL_PROSPECT"
        else "Oportunidade reativa com evidência contratual/publicação",
    ]
    unavailable = []
    if not (contacts.get("accepted") or []):
        unavailable.append("Contato institucional específico não capturado — pesquisa adicional")
    if eligibility.get("annual_sum_state") == "DIRECT_CONTRACTING_SUM_UNKNOWN":
        unavailable.append("Somatório anual da mesma natureza desconhecido")

    lines = [
        f"# Dossier — {agency.get('nome_oficial') or agency.get('agency_id')}",
        "",
        "**entity_type:** PUBLIC_AGENCY_PROSPECT  ",
        f"**agency_id:** `{agency.get('agency_id')}`  ",
        f"**publishability:** {pub.get('category')}  ",
        f"**relationship_state:** {pub.get('relationship_state')}  ",
        "**campaign:** CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01",
        "",
        "## 1. Identificação oficial",
    ]
    lines.extend([f"- {x}" for x in facts] if facts else ["- (incompleta)"])
    lines += [
        "",
        "## 2. População e contexto",
        f"- Município: {agency.get('municipio') or 'n/d'}",
        f"- Faixa populacional: {agency.get('faixa_populacional') or 'UNKNOWN'}",
        f"- Esfera: {agency.get('esfera') or 'n/d'}",
        "- Nota: população é variável contextual, não prova isolada de baixa capacidade técnica.",
        "",
        "## 3. Histórico de contratações de engenharia",
        f"- Contratos observados (evidência): {lead.get('contract_count', 0)}",
        f"- Valor total observado: {lead.get('total_value')}",
        f"- Última publicação: {lead.get('last_publication') or 'n/d'}",
        "",
        "## 4. Sinais detectados",
    ]
    for s in fired:
        lines.append(f"- **{s.get('signal_id')}** (conf={s.get('confidence')}): {s.get('definition', '')}")
    if not fired:
        lines.append("- Nenhum sinal FIRED.")

    lines += [
        "",
        "## 5. Evidências",
        f"- Ledger refs: {len(lead.get('evidence') or [])}",
        "",
        "## 6. Limitações",
    ]
    lines.extend([f"- {x}" for x in (lead.get("limitations") or ["n/d"])])
    lines += [
        "",
        "## 7. Problema provável",
        f"- {lead.get('probable_problem') or 'Sinais de possível necessidade técnica de apoio em obras/serviços de engenharia.'}",
        "",
        "## 8. Serviço CONFENGE mais aderente",
        f"- {service.get('nome') or service.get('service_id') or score.get('selected_service_id')}",
        "",
        "## 9. Entregáveis sugeridos",
    ]
    ents = list(service.get("entregaveis") or [])[:12]
    lines.extend([f"- {e}" for e in ents] if ents else ["- (ver catálogo)"])
    lines += [
        "",
        "## 10. Classificação preliminar do objeto",
        f"- Classe: {classification.get('suggested_class')}",
        f"- Confiança: {classification.get('confidence')}",
        f"- Validação humana: {classification.get('human_validation_required')}",
        f"- Justificativa: {classification.get('justification')}",
        "",
        "## 11. Limite legal potencialmente aplicável",
        f"- Estado: **{eligibility.get('eligibility_state')}**",
        f"- Threshold: {eligibility.get('threshold_id')} ({eligibility.get('threshold_amount')})",
        f"- Disclaimer: {eligibility.get('disclaimer')}",
        "",
        "## 12. Somatório anual conhecido",
        f"- {fragmentation.get('annual_sum_state') or eligibility.get('annual_sum_state')}",
        f"- Valor conhecido: {fragmentation.get('annual_sum_same_nature')}",
        "",
        "## 13. Alerta de fracionamento",
        f"- Suspeito: {fragmentation.get('fragmentation_suspected')}",
        f"- Severidade: {fragmentation.get('severity')}",
        f"- Indicadores: {', '.join(fragmentation.get('indicators') or []) or 'nenhum'}",
        "",
        "## 14. Validação jurídica pelo órgão",
        "- Obrigatória. O sistema não autoriza contratação direta.",
        "",
        "## 15. Faixa de preço (por escopo)",
        f"- {service.get('faixa_preco_por_escopo') or 'ver catálogo / proposta por escopo'}",
        "- Preço NÃO é ancorado no teto legal.",
        "",
        "## 16. Documentos e qualificações exigíveis",
        "- Conforme edital/procedimento do órgão; kit de habilitação CONFENGE em estado auditável.",
        "",
        "## 17. Conflito de interesses",
        f"- Estado: **{conflict.get('state')}**",
        f"- Notas: {conflict.get('notes')}",
        f"- cannot_assert_no_conflict: {conflict.get('cannot_assert_no_conflict')}",
        "",
        "## 18. Contato institucional",
    ]
    accepted = list(contacts.get("accepted") or [])
    if accepted:
        lines.extend([f"- {c.get('channel')}: {c.get('value')}" for c in accepted])
    else:
        lines.append("- Pesquisa adicional de canal institucional necessária")
    lines += [
        "",
        "## 19. Abordagem recomendada",
        f"- {lead.get('recommended_approach') or 'Apresentar capacidade técnica e redução de risco documental/executivo; não vender dispensa.'}",
        "",
        "## 20. Mensagem inicial (minuta)",
        "```",
        lead.get("outreach_message")
        or (
            f"Prezados(as),\n\nA CONFENGE presta apoio técnico especializado a órgãos públicos "
            f"em planejamento de contratações de obras/serviços de engenharia, orçamentação e "
            f"apoio técnico à fiscalização (sem substituir o fiscal público).\n\n"
            f"Identificamos sinais públicos de possível necessidade técnica em {agency.get('nome_oficial')}. "
            f"Gostaríamos de apresentar nosso catálogo e entender se há demanda de suporte.\n\n"
            f"Atenciosamente,\nCONFENGE"
        ),
        "```",
        "",
        "## 21. Roteiro de reunião",
        "1. Contexto do órgão e obras em andamento/planejadas",
        "2. Gargalos de fase preparatória / fiscalização",
        "3. Oferta aderente e entregáveis",
        "4. Escopo, prazo, preço por esforço",
        "5. Limites legais e papéis (art. 117)",
        "6. Próximos passos e documentos",
        "",
        "## 22. Próximos passos",
        f"- {lead.get('next_human_step') or 'Revisão humana de conflito, classificação e autorização de outreach.'}",
        "",
        "## 23. Human-review checklist",
        "- [ ] Identidade oficial conferida",
        "- [ ] Sinais e evidências revisados",
        "- [ ] Classificação do objeto validada se ambígua",
        "- [ ] Conflito de interesses declarado/clearance",
        "- [ ] Contato institucional confirmado em fonte pública",
        "- [ ] Mensagem revisada (sem promessa de dispensa)",
        "- [ ] Aprovação explícita de Tiago antes de qualquer contato",
        "",
        "---",
        "",
        "## Separação epistemológica",
        "",
        "### Fatos comprovados",
    ]
    lines.extend([f"- {x}" for x in facts])
    lines += ["", "### Inferências"]
    lines.extend([f"- {x}" for x in inferences])
    lines += ["", "### Hipóteses"]
    lines.extend([f"- {x}" for x in hypotheses])
    lines += ["", "### Informações indisponíveis"]
    lines.extend([f"- {x}" for x in unavailable] if unavailable else ["- (nenhuma listada)"])
    lines += [
        "",
        "### Recomendações comerciais",
        f"- Categoria: {pub.get('category')}",
        f"- Ação: {lead.get('next_human_step')}",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_dossier(out_dir: Path, lead: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    agency = lead.get("agency") or {}
    aid = agency.get("agency_id") or lead.get("agency_id") or "unknown"
    path = out_dir / f"dossier-{aid}.md"
    path.write_text(render_dossier_markdown(lead), encoding="utf-8")
    return path
