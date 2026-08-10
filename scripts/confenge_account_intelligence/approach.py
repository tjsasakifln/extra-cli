"""Approach copy fields: tone, CTA, questions — epistemic, no insider language.

Messaging facts come ONLY from MessageSpine (never confirmed[0] portfolio-count).
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_account_intelligence.message_spine import (
    build_message_spine,
)


def _company_label(bag: dict[str, Any]) -> str:
    return str(bag.get("razao_social") or bag.get("nome_fantasia") or "a empresa")


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

    spine = build_message_spine(bag, why=why, selection=selection, layers=layers)
    fact_to_mention = spine.observed_fact or (
        "Não há fato contratual concreto no input; "
        "a conversa deve partir de discovery sem afirmar portfólio inexistente."
    )
    why_this_account = spine.why_this_account or (
        f"{company}: sem objeto contratual específico no input; "
        "não afirmar portfólio de engenharia sem evidência."
    )
    micro_offer_code = spine.micro_offer_code

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
            "cta": (
                "Se fizer sentido, monto um recorte enxuto só dos contratos com marcos "
                "nos próximos 90 dias — sem dashboard genérico."
            ),
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
    t = dict(templates.get(sid) or templates["diagnostico_contratual_b2g"])

    # Diversify CTA wording by company hash so same service does not mass-reuse one line.
    cta_variants = {
        "gestao_monitoramento_contratual": [
            "Se fizer sentido, monto um recorte enxuto só dos contratos com marcos nos próximos 90 dias.",
            "Posso devolver uma lista priorizada dos 3 contratos públicos com maior carga de obrigação no horizonte curto.",
            "Ofereço um check de 20 minutos sobre qual contrato da carteira pública mereceria atenção primeiro.",
        ],
        "estruturacao_pleito_reajuste": [
            "Posso enviar um roteiro objetivo de checagem de reajuste (cláusula → índice → memória) para um contrato-piloto.",
            "Se útil, faço a leitura de uma cláusula de reajuste pública e devolvo os pontos a confirmar com a equipe.",
        ],
        "aditivos_extracontratuais": [
            "Posso revisar a cadeia aditivo → planilha → memória em um caso recente.",
            "Se quiser, olho o memorial de um aditivo público e aponto só as lacunas documentais.",
        ],
        "medicoes_glosas_memoria": [
            "Proponho uma revisão pontual da última medição contestada, com checklist de evidências.",
            "Posso devolver um checklist curto do que costuma sustentar (ou derrubar) uma memória de medição.",
        ],
        "auditoria_orcamento_bdi": [
            "Envio escopo de auditoria focal (composições + BDI) para um contrato-alvo.",
            "Se fizer sentido, faço uma segunda opinião só sobre um pacote de planilha/BDI — sem substituir a equipe.",
        ],
        "apoio_licitacoes_propostas": [
            "Disponibilizo apoio de pico em análise de edital/proposta sob NDA.",
            "Posso ajudar a varrer um edital em janela e devolver riscos técnicos de proposta em formato curto.",
        ],
        "diagnostico_contratual_b2g": [
            "Sugiro um diagnóstico contratual B2G curto para mapear riscos e priorizar encaixes.",
            "Se preferir, começamos por uma conversa de 15 minutos só para validar se há encaixe real.",
        ],
        "reforco_temporario_backoffice": [
            "Posso dimensionar um reforço temporário de backoffice técnico/contratual por sprint.",
            "Se a carga apertar, monto um escopo de sprint de apoio (medições/aditivos/propostas) com entregáveis claros.",
        ],
        "inteligencia_pncp_mercado": [
            "Posso entregar um briefing PNCP focado no recorte que importar para vocês.",
            "Se útil, recorto o PNCP por UF/órgão e devolvo um mapa de oportunidades públicas.",
        ],
        "reequilibrio_economico_financeiro": [
            "Ofereço uma leitura técnica independente do material de reequilíbrio já reunido.",
            "Posso ajudar a organizar o nexo causal documental antes de qualquer narrativa de crédito.",
        ],
    }
    variants = cta_variants.get(sid) or [t["cta"]]
    h = sum(ord(ch) for ch in company) if company else 0
    t["cta"] = variants[h % len(variants)]

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
        "observed_fact": spine.observed_fact,
        "body_seed_fact": spine.body_seed_fact,
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
        "why_now_copy": spine.why_now,
        "micro_offer_code": micro_offer_code,
        "message_spine": spine.as_dict(),
        "message_spine_complete": spine.complete,
        "fact_evidence_ids": list(spine.fact_evidence_ids),
    }
