"""Approach copy fields: tone, CTA, questions — epistemic, no insider language."""

from __future__ import annotations

from typing import Any


def _company_label(bag: dict[str, Any]) -> str:
    return str(bag.get("razao_social") or bag.get("nome_fantasia") or "a empresa")


def _build_why_this_account(
    bag: dict[str, Any],
    company: str,
    confirmed: list[dict[str, Any]],
    service_id: str,
) -> str:
    """Specific WHY YOU from public contracts/facts — never hollow portfolio boilerplate."""
    contracts = bag.get("contracts") or []
    # Prefer a concrete object + agency from the first substantial contract.
    for c in contracts:
        if not isinstance(c, dict):
            continue
        obj = str(c.get("object") or c.get("objeto") or c.get("objeto_contrato") or "").strip()
        if len(obj) < 24:
            continue
        org = str(c.get("orgao") or c.get("agency") or c.get("orgao_nome") or "").strip()
        uf = str(c.get("uf") or "").strip()
        val = c.get("value_brl") or c.get("valor_total")
        bits = [f"{company} com execução pública observável"]
        if org:
            bits.append(f"junto a {org}")
        if uf:
            bits.append(f"({uf})")
        bits.append(f"— objeto: {obj[:160]}")
        if isinstance(val, (int, float)) and val > 0:
            bits.append(f"(R$ {val:,.0f})")
        return " ".join(bits)

    # Fall back to first confirmed fact if it is not a hollow portfolio count line.
    for item in confirmed:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        low = text.lower()
        if "portfólio público observado com" in low and "contrato(s) no input" in low:
            continue
        if "ufs observadas nos contratos" in low:
            continue
        return f"{company}: {text[:220]}"

    activity = str(bag.get("activity_class") or "").strip()
    if activity and activity not in {"OTHER", "UNKNOWN", ""}:
        return (
            f"{company} classificada como {activity} com material público insuficiente "
            f"para especialidade além de {service_id} — discovery honesto."
        )
    return (
        f"{company}: sem objeto contratual específico no input; "
        "não afirmar portfólio de engenharia sem evidência."
    )


def build_approach_fields(
    bag: dict[str, Any],
    *,
    structure: dict[str, Any],
    why: dict[str, Any],
    selection: dict[str, Any],
    layers: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    primary = selection["primary_service"]
    sid = primary["service_id"]
    mode = primary.get("approach_mode") or ""
    sc = structure.get("structure_class") or "unknown"
    company = _company_label(bag)

    # fact_to_mention: prefer confirmed fact text
    confirmed = layers.get("confirmed_facts") or []
    if confirmed:
        fact_to_mention = confirmed[0]["text"]
    else:
        fact_to_mention = (
            "Não há fato público confirmado suficiente no input; "
            "a conversa deve partir de discovery sem afirmar portfólio inexistente."
        )

    # Per-service question / CTA / objection
    templates: dict[str, dict[str, str]] = {
        "estruturacao_pleito_reajuste": {
            "q": (
                "Como a equipe tem acompanhado a aplicação de reajuste/índices "
                "nos contratos maduros — há memória de cálculo recente?"
            ),
            "cta": (
                "Posso enviar um roteiro objetivo de checagem de reajuste "
                "(cláusula → índice → memória) para um contrato-piloto."
            ),
            "obj": "Já temos jurídico/orçamento interno cuidando de reajuste.",
        },
        "reequilibrio_economico_financeiro": {
            "q": "Houve evento extraordinário ou descompasso de custos que vocês já documentaram parcialmente?",
            "cta": "Ofereço uma leitura técnica independente do material de reequilíbrio já reunido.",
            "obj": "Estamos aguardando parecer interno antes de qualquer apoio externo.",
        },
        "aditivos_extracontratuais": {
            "q": ("Os aditivos recentes estão com memorial quantitativo/qualitativo alinhado ao edital original?"),
            "cta": "Posso revisar a cadeia aditivo → planilha → memória em um caso recente.",
            "obj": "Aditivos já estão formalizados com a fiscalização.",
        },
        "medicoes_glosas_memoria": {
            "q": "Qual o ponto mais recorrente de glosa ou divergência na memória de cálculo?",
            "cta": "Proponho uma revisão pontual da última medição contestada, com checklist de evidências.",
            "obj": "A fiscalização já fechou o ciclo de medição.",
        },
        "auditoria_orcamento_bdi": {
            "q": (
                "Há interesse em uma segunda opinião independente sobre planilha/BDI "
                "de um pacote específico (sem substituir a equipe interna)?"
            ),
            "cta": "Envio escopo de auditoria focal (composições + BDI) para um contrato-alvo.",
            "obj": "Já temos orçamentistas e não precisamos de reforço geral.",
        },
        "gestao_monitoramento_contratual": {
            "q": "Quais prazos e obrigações contratuais mais consomem a equipe neste trimestre?",
            "cta": "Posso montar um painel mínimo de monitoramento para o portfólio prioritário.",
            "obj": "Já usamos sistema próprio de gestão contratual.",
        },
        "apoio_licitacoes_propostas": {
            "q": "Há edital/proposta em janela nas próximas semanas que mereça reforço técnico de pico?",
            "cta": "Disponibilizo apoio de pico em análise de edital/proposta sob NDA.",
            "obj": "A área de licitações está coberta neste ciclo.",
        },
        "inteligencia_pncp_mercado": {
            "q": "Quais UFs/órgãos vocês querem priorizar na leitura de mercado público?",
            "cta": "Posso entregar um briefing PNCP focado no recorte que importar para vocês.",
            "obj": "Já acompanhamos o PNCP internamente.",
        },
        "diagnostico_contratual_b2g": {
            "q": (
                "Quais contratos ou frentes B2G mais preocupam a liderança técnica "
                "neste momento (mesmo que a gente ainda não tenha o dossiê completo)?"
            ),
            "cta": "Sugiro um diagnóstico contratual B2G curto para mapear riscos e priorizar encaixes.",
            "obj": "Ainda não temos clareza se faz sentido conversar agora.",
        },
        "reforco_temporario_backoffice": {
            "q": "Onde a carga contratual mais aperta o time (medições, aditivos, reajuste, propostas)?",
            "cta": "Posso dimensionar um reforço temporário de backoffice técnico/contratual por sprint.",
            "obj": "Preferimos não externalizar rotinas operacionais.",
        },
    }
    t = templates.get(sid) or templates["diagnostico_contratual_b2g"]

    # Canonical micro-offer codes (not approach_mode labels).
    micro_by_service: dict[str, str] = {
        "estruturacao_pleito_reajuste": "REAJUSTE_CHECK",
        "reequilibrio_economico_financeiro": "CLAIM_READINESS_CHECK",
        "aditivos_extracontratuais": "ADITIVO_RISK_CHECK",
        "medicoes_glosas_memoria": "MEDICAO_CHECK",
        "auditoria_orcamento_bdi": "DOCUMENT_CHECKLIST",
        "gestao_monitoramento_contratual": "PUBLIC_DATA_SNAPSHOT",
        "apoio_licitacoes_propostas": "PROCUREMENT_RISK_SNAPSHOT",
        "inteligencia_pncp_mercado": "MARKET_BRIEF",
        "diagnostico_contratual_b2g": "DIAGNOSTIC_CHECKLIST",
        "reforco_temporario_backoffice": "BACKOFFICE_SCOPE_CHECK",
    }
    micro_offer_code = micro_by_service.get(sid, "DIAGNOSTIC_CHECKLIST")

    # why_this_account: must cite a concrete public hook, never a hollow portfolio template.
    why_this_account = _build_why_this_account(bag, company, confirmed, sid)

    # Tone / density
    if sc == "robust" or "independente" in mode or "auditoria" in mode or "segunda_opiniao" in mode:
        tone = "consultivo_abm"
        density = "alta"
        framing = (
            "Segunda opinião / revisão independente / apoio de pico — "
            "respeitando estrutura existente; nunca 'vocês não têm estrutura'."
        )
    elif sc == "lean" and sid == "reforco_temporario_backoffice":
        tone = "operacional_parceiro"
        density = "moderada"
        framing = (
            "Reforço operacional temporário sustentado por evidências de carga/regionalidade — sem afirmar organograma."
        )
    elif sid == "diagnostico_contratual_b2g":
        tone = "consultivo_discovery"
        density = "baixa"
        framing = "Discovery honesto: não inventar dor; convidar a validar hipóteses com a empresa."
    else:
        tone = "tecnico_moderado"
        density = "moderada"
        framing = "Abordagem técnica ancorada em fato público mencionado e pergunta aberta."

    claims_to_avoid = [
        "Afirmar estrutura interna (organograma, headcount, área jurídica) sem fonte pública.",
        "Tratar ausência de dado como prova de ausência de reajuste, aditivo ou equipe.",
        "Linguagem insider ('sei que o gerente X…', 'vocês não têm claims…').",
        "Prometer resultado de pleito, vitória em licitação ou reequilíbrio garantido.",
        "Qualificar/desqualificar a empresa como lead; o produto é ângulo de abordagem.",
        "Usar score genérico como se fosse evidência contratual.",
    ]
    if sc == "robust":
        claims_to_avoid.append("Oferecer outsourcing pleno ou dizer que a conta 'não tem estrutura'.")

    research_gaps: list[str] = []
    if not (bag.get("contracts") or []):
        research_gaps.append("Sem contratos públicos no input — buscar PNCP/contratos por CNPJ.")
    if not bag.get("cnae_principal"):
        research_gaps.append("CNAE principal ausente.")
    if structure.get("structure_class") == "unknown":
        research_gaps.append("Sinais de estrutura interna insuficientes — não inferir lean por omissão.")
    if any(
        c.get("age_days") and c["age_days"] >= 365 and not c.get("reajuste_evidence")
        for c in (bag.get("contracts") or [])
    ):
        research_gaps.append("Validar cláusulas de reajuste e eventuais termos aditivos não presentes no input.")
    if not (bag.get("evidence") or []):
        research_gaps.append("Sem evidências com URL/documento — anexar fontes quando disponíveis.")

    # Dominant state note baked into limitations later
    return {
        "fact_to_mention": fact_to_mention,
        "question_to_ask": t["q"],
        "cta": t["cta"]
        .replace("Posso", f"Para {company}, posso")
        .replace("Para a empresa, posso", f"Para {company}, posso")
        if False
        else t["cta"],
        "objection_expected": t["obj"],
        "claims_to_avoid": claims_to_avoid,
        "message_tone": {
            "tone": tone,
            "technical_density": density,
            "framing": framing,
        },
        "research_gaps": research_gaps,
        "why_this_account": why_this_account,
        "micro_offer_code": micro_offer_code,
    }
