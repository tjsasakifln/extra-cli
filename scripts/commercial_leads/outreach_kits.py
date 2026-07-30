"""Manual outreach kits for Top-5 — human send only, no automation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_FORBIDDEN = re.compile(
    r"propens[aã]o|probabilidade de compra|inten[cç][aã]o de compra|"
    r"lead quente|dor comprovada|sei que voc[eê]s (precisam|querem)|"
    r"garantimos (convers[aã]o|fechamento)",
    re.I,
)

_OFFER_LABELS = {
    "diagnostico_b2g": "Diagnóstico B2G",
    "monitoramento": "Monitoramento de oportunidades PNCP",
    "analise_edital": "Análise técnica de edital",
    "apoio_proposta": "Apoio em licitações e propostas",
    "acompanhamento_admin": "Acompanhamento contratual / gestão documental",
    "auditoria_orcamento": "Auditoria de orçamento, composições e BDI",
    "inteligencia_mercado": "Inteligência de mercado PNCP",
}


def _contact_public(lead: dict[str, Any]) -> dict[str, Any]:
    reg = lead.get("registry") or {}
    phone = reg.get("telefone") or lead.get("telefone") or "NOT_AVAILABLE"
    email = reg.get("email") or lead.get("email") or "NOT_AVAILABLE"
    site = reg.get("site") or lead.get("site") or "NOT_AVAILABLE"
    return {
        "telefone": phone if phone else "NOT_AVAILABLE",
        "email": email if email else "NOT_AVAILABLE",
        "site": site if site else "NOT_AVAILABLE",
        "source": reg.get("source") or lead.get("registry_source") or "NOT_AVAILABLE",
        "source_date": reg.get("source_date") or lead.get("registry_source_date") or "NOT_AVAILABLE",
        "note": "Apenas contatos empresariais públicos oficiais; ausência = NOT_AVAILABLE (não inventar).",
    }


def _primary_signal(lead: dict[str, Any]) -> str:
    fired = lead.get("signals_fired") or []
    if not fired:
        return "padrão de contratos públicos observados no histórico carregado"
    s0 = fired[0]
    if isinstance(s0, dict):
        return str(s0.get("signal_id") or s0.get("hypothesis") or "sinal_observado")
    return str(s0)


def build_outreach_kit(lead: dict[str, Any], *, run_id: str | None = None) -> dict[str, Any]:
    name = lead.get("razao_social") or "empresa"
    cnpj = lead.get("cnpj14")
    offer_id = lead.get("suggested_offer") or "diagnostico_b2g"
    offer_label = _OFFER_LABELS.get(str(offer_id), str(offer_id))
    signal = _primary_signal(lead)
    uf = lead.get("uf") or (lead.get("registry") or {}).get("uf") or ""
    contact = _contact_public(lead)

    summary_lines = [
        f"{name} (CNPJ {cnpj}) aparece na fila prioritária CONFENGE com score {lead.get('score_total')}.",
        f"Enquadramento setorial observado: {lead.get('supplier_sector_fit')} / {lead.get('activity_class')}.",
        f"Contratos públicos observados no histórico carregado: {lead.get('contract_count')}; "
        f"valor agregado (soma histórica): {lead.get('total_value')}.",
        f"Sinal/padrão principal que justifica a abordagem: {signal}.",
        f"Oferta sugerida (hipótese de aderência, não demanda confirmada): {offer_label}.",
        "Todo o conteúdo é para envio manual por Tiago; nenhuma mensagem é disparada pelo sistema.",
    ]

    kit = {
        "schema_version": "outreach-kit-v1",
        "cnpj14": cnpj,
        "razao_social": name,
        "rank_position": lead.get("rank_position"),
        "run_id": run_id,
        "summary_5_to_10_lines": summary_lines,
        "trigger_event_or_pattern": signal,
        "suggested_offer": {"id": offer_id, "label": offer_label},
        "value_arguments": [
            f"Leitura objetiva do histórico público pode ajudar a estruturar a operação B2G "
            f"em torno de padrões como «{signal}».",
            f"A oferta «{offer_label}» é uma hipótese de aderência CONFENGE a partir de evidências "
            "publicadas — a validação depende da conversa com a empresa.",
        ],
        "discovery_question": (
            "Hoje, como vocês acompanham novas oportunidades públicas e a carga de "
            "documentação/contratos em andamento?"
        ),
        "interpretation_risks": [
            "Contratos públicos não provam intenção de contratar consultoria.",
            "Um contrato de engenharia isolado não prova que toda a empresa é do setor.",
            "Dados cadastrais podem estar defasados em relação à operação real.",
            "Sinais de crescimento ou concentração são observáveis, não diagnósticos internos.",
        ],
        "public_business_contact": contact,
        "whatsapp_short": (
            f"Olá, sou Tiago da CONFENGE. Vi no PNCP o histórico público de {name}"
            f"{f' ({uf})' if uf else ''} e alguns padrões recentes de contratos. "
            f"Posso te mandar um resumo objetivo (sem compromisso) sobre como costumamos "
            f"apoiar empresas com perfil semelhante em {offer_label.lower()}?"
        ),
        "email_initial": {
            "subject": f"CONFENGE — leitura objetiva do histórico público de {name}",
            "body": (
                f"Prezados,\n\n"
                f"Sou Tiago Sasaki, da CONFENGE. A partir de dados públicos de contratos "
                f"(PNCP), observamos o histórico de {name} e padrões como «{signal}».\n\n"
                f"Isso não significa que haja uma demanda confirmada — apenas uma hipótese de "
                f"adererência para uma conversa breve sobre {offer_label.lower()}.\n\n"
                f"Se fizer sentido, posso enviar um one-pager com o que observamos e perguntas "
                f"de discovery. Caso prefira não prosseguir, responda «não» e encerramos.\n\n"
                f"Atenciosamente,\nTiago Sasaki\nCONFENGE\n"
            ),
        },
        "call_script": [
            "1. Apresentação: Tiago / CONFENGE — consultoria B2G; piloto Extra Construtora separado.",
            f"2. Contexto: histórico público de {name}; padrão {signal}.",
            "3. Pergunta de discovery (acima).",
            "4. Oferta como hipótese, não como diagnóstico fechado.",
            "5. CTA: autorização para one-pager ou reunião de 20 min.",
            "6. Se recusa: registrar DO_NOT_CONTACT ou LOST com motivo.",
        ],
        "follow_up_suggestion": (
            "Se não houver resposta em 5–7 dias úteis: um follow-up curto relembrando o "
            "one-pager e oferecendo encerrar o contato."
        ),
        "cta": "Autoriza envio de one-pager factual (5–8 linhas) com o que observamos no PNCP?",
        "manual_send_only": True,
        "automation_forbidden": True,
    }
    blob = json.dumps(kit, ensure_ascii=False, default=str)
    kit["language_scan_forbidden_hit"] = bool(_FORBIDDEN.search(blob))
    return kit


def kit_to_markdown(kit: dict[str, Any]) -> str:
    contact = kit.get("public_business_contact") or {}
    email = kit.get("email_initial") or {}
    lines = [
        f"# Kit de abordagem — {kit.get('razao_social')}",
        "",
        f"- CNPJ: `{kit.get('cnpj14')}` | Rank: {kit.get('rank_position')}",
        f"- Oferta sugerida: **{(kit.get('suggested_offer') or {}).get('label')}**",
        "- Envio: **manual only** (sem automação)",
        "",
        "## Resumo",
    ]
    for line in kit.get("summary_5_to_10_lines") or []:
        lines.append(f"- {line}")
    lines += [
        "",
        f"## Evento/padrão: {kit.get('trigger_event_or_pattern')}",
        "",
        "## Argumentos de valor",
    ]
    for a in kit.get("value_arguments") or []:
        lines.append(f"- {a}")
    lines += [
        "",
        f"## Pergunta de discovery\n\n{kit.get('discovery_question')}",
        "",
        "## Riscos de interpretação",
    ]
    for r in kit.get("interpretation_risks") or []:
        lines.append(f"- {r}")
    lines += [
        "",
        "## Contato empresarial público",
        f"- telefone: {contact.get('telefone')}",
        f"- e-mail: {contact.get('email')}",
        f"- site: {contact.get('site')}",
        f"- fonte: {contact.get('source')} @ {contact.get('source_date')}",
        "",
        "## WhatsApp (copiar/colar)",
        "",
        kit.get("whatsapp_short") or "",
        "",
        "## E-mail",
        f"**Assunto:** {email.get('subject')}",
        "",
        email.get("body") or "",
        "",
        "## Roteiro de ligação",
    ]
    for step in kit.get("call_script") or []:
        lines.append(f"- {step}")
    lines += [
        "",
        f"## Follow-up\n\n{kit.get('follow_up_suggestion')}",
        "",
        f"## CTA\n\n{kit.get('cta')}",
        "",
    ]
    return "\n".join(lines)


def export_outreach_kits(
    out_dir: Path,
    leads: list[dict[str, Any]],
    *,
    run_id: str | None = None,
    limit: int = 5,
) -> dict[str, str]:
    root = Path(out_dir) / "top5-outreach-kits"
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    index: list[dict[str, Any]] = []
    for lead in leads[:limit]:
        cnpj = str(lead.get("cnpj14") or "unknown")
        kit = build_outreach_kit(lead, run_id=run_id)
        jp = root / f"{cnpj}.json"
        mp = root / f"{cnpj}.md"
        jp.write_text(json.dumps(kit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        mp.write_text(kit_to_markdown(kit), encoding="utf-8")
        paths[f"kit:{cnpj}:json"] = str(jp)
        paths[f"kit:{cnpj}:md"] = str(mp)
        index.append({"cnpj14": cnpj, "rank": lead.get("rank_position"), "json": str(jp), "md": str(mp)})
    idx = root / "index.json"
    idx.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["kits_index"] = str(idx)
    return paths
