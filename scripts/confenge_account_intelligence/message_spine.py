"""Single MessageSpine for CONFENGE outreach copy.

All consumer paths (dossier, draft body, Warmbly strategy, COPY_CONTEXT_READY)
must read messaging fields from this spine — never from confirmed[0] portfolio-count.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Meta evidence ids that may stay in internal lists but never seed the body.
META_EVIDENCE_PREFIXES: tuple[str, ...] = (
    "cf-portfolio-count",
    "cf-ufs",
    "cf-mature-no-reajuste",
    "si-portfolio",
    "wi-",
)

# Shared with send_readiness COPY_CONTEXT — MessageSpine.complete must match gate.
_HOLLOW_FACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"portf[oó]lio\s+p[uú]blico\s+observado\s+com\s+\d+\s+contrato", re.I),
    re.compile(r"portf[oó]lio\s+p[uú]blico\s+observado\s+com", re.I),
    re.compile(r"portf[oó]lio\s+p[uú]blico\s+observ[aá]vel", re.I),
    re.compile(r"portf[oó]lio\s+p[uú]blico\s+de\s+contratos", re.I),
    re.compile(r"sem\s+dor\s+contratual\s+concreta", re.I),
    re.compile(r"ufs\s+observadas\s+nos\s+contratos", re.I),
    re.compile(r"contrato\(s\)\s+no\s+input", re.I),
    re.compile(r"^sem\s+fato\s+p[uú]blico\s+confirmado", re.I),
    re.compile(r"sem\s+objeto\s+contratual\s+espec[ií]fico\s+no\s+input", re.I),
    re.compile(r"empresa\s+com\s+momento\s+comercial\s+p[uú]blico", re.I),
    re.compile(r"momento\s+comercial\s+indicado\s+pelo\s+extra-cli", re.I),
    re.compile(r"observamos\s+contratos\s+p[uú]blicos", re.I),
    re.compile(r"empresa\s+com\s+portf[oó]lio\s+p[uú]blico", re.I),
    re.compile(r"fato\s+contratual\s+p[uú]blico\s+utiliz[aá]vel", re.I),
    re.compile(r"sem\s+dor\s+especializada\s+dominante", re.I),
    re.compile(r"momento\s+comercial\s+p[uú]blico", re.I),
    re.compile(r"execu[cç][aã]o\s+p[uú]blica\s+observ[aá]vel", re.I),
    re.compile(r"empresa\s+com\s+execu[cç][aã]o\s+p[uú]blica", re.I),
    re.compile(r"target_fit|email_send_ready|copy_context_ready|service_fit_supported", re.I),
    re.compile(r"primary_service|micro_offer_code|why_this_account\s*=", re.I),
)


def is_hollow_fact(text: str | None) -> bool:
    """True when text is empty, meta-only, portfolio boilerplate, or generic why_now.

    MUST stay aligned with send_readiness._is_generic_why / evaluate_copy_context_ready
    so MessageSpine.complete cannot be True while COPY_CONTEXT_READY is False.
    """
    t = (text or "").strip()
    if not t:
        return True
    if len(t) < 24:
        return True
    low = t.lower()
    for pat in _HOLLOW_FACT_PATTERNS:
        if pat.search(low):
            return True
    # Pure count / UF lines without a contractual hook.
    if re.fullmatch(r".*\b\d+\s+contrato\(s\)\b.*", low) and "objeto" not in low and len(t) < 90:
        return True
    return False


def is_meta_evidence_id(eid: str | None) -> bool:
    s = str(eid or "")
    return any(s == p or s.startswith(p) for p in META_EVIDENCE_PREFIXES)


def _company_label(bag: dict[str, Any]) -> str:
    return str(bag.get("razao_social") or bag.get("nome_fantasia") or "a empresa")


def extract_contract_hook(bag: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (observed_fact, evidence_ids) from the strongest concrete contract object."""
    contracts = bag.get("contracts") or []
    evidence_ids: list[str] = []
    for i, c in enumerate(contracts):
        if not isinstance(c, dict):
            continue
        obj = str(c.get("object") or c.get("objeto") or c.get("objeto_contrato") or "").strip()
        if len(obj) < 24:
            continue
        org = str(c.get("orgao") or c.get("agency") or c.get("orgao_nome") or "").strip()
        uf = str(c.get("uf") or "").strip()
        val = c.get("value_brl") or c.get("valor_total")
        cid = str(c.get("id") or c.get("contrato_id") or f"contract-{i}")
        bits = [f"objeto: {obj[:180]}"]
        if org:
            bits.append(f"órgão: {org}")
        if uf:
            bits.append(f"UF {uf}")
        if isinstance(val, (int, float)) and val > 0:
            bits.append(f"R$ {val:,.0f}")
        fact = "; ".join(bits)
        evidence_ids.append(f"cf-contract-{cid}")
        return fact, evidence_ids
    return "", []


def _non_hollow_confirmed(confirmed: list[dict[str, Any]]) -> tuple[str, list[str]]:
    for item in confirmed:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        eid = str(item.get("id") or "")
        if is_meta_evidence_id(eid):
            continue
        if is_hollow_fact(text):
            continue
        return text[:240], [eid] if eid else []
    return "", []


def _compress_hook_insight(hook: str, *, max_len: int = 140) -> str:
    """Turn raw PNCP object dump into a short human insight fragment."""
    t = (hook or "").strip()
    # Drop "objeto:" prefix noise
    t = re.sub(r"(?i)^objeto:\s*", "", t)
    t = re.sub(r"(?i);\s*órg[aã]o:\s*", " junto a ", t)
    t = re.sub(r"(?i);\s*UF\s+", " (", t)
    if "R$" in t and "(" in t and not t.rstrip().endswith(")"):
        t = t.replace("; R$", "; valor R$")
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        t = t[: max_len - 1].rstrip() + "…"
    return t


def _why_now_text(why: dict[str, Any], hook: str, service_id: str) -> str:
    """Build temporal why_now that passes COPY_CONTEXT (never hollow meta templates)."""
    trigger = ""
    temporal = ""
    if isinstance(why, dict):
        trigger = str(why.get("trigger") or "").strip()
        for key in ("temporal_fact", "summary"):
            val = str(why.get(key) or "").strip()
            if not val or is_hollow_fact(val):
                continue
            temporal = val
            break
    # Prefer explicit temporal event when non-hollow.
    if temporal and not is_hollow_fact(temporal):
        # If temporal is still abstract, anchor to contract hook.
        if hook and not is_hollow_fact(hook) and "objeto" not in temporal.lower():
            insight = _compress_hook_insight(hook)
            return f"{temporal.rstrip('.')}: {insight}"
        return temporal
    if hook and not is_hollow_fact(hook):
        insight = _compress_hook_insight(hook)
        if trigger in {"aditivo", "additive", "CONTRACT_EXTENSION", "prorrogacao", "prorrogação"}:
            return f"Evento de prorrogação/aditivo recente ligado a: {insight}"
        if trigger in {"anualidade", "ANUALIDADE", "mature_no_reajuste"}:
            return f"Janela de aniversário/madurez contratual observável em: {insight}"
        if trigger in {"medicao", "medição", "glosa"}:
            return f"Sinal documental de medição/glosa associado a: {insight}"
        if trigger and trigger not in {"", "insufficient_facts", "portfolio_review"}:
            return f"Gatilho {trigger} ancorado no contrato público: {insight}"
        # portfolio_review without a dated event: WEAK temporal — do not invent "now".
        # Still provide a non-hollow line only when multi-signal portfolio exists in hook.
        if "órgão" in hook.lower() or "orgao" in hook.lower() or "UF" in hook:
            return (
                f"Carteira pública ativa com obrigação em execução — âncora: {insight}. "
                "Sem evento datado adicional no input (why_now_strength=MODERATE)."
            )
        # Single thin hook without temporal event → weak (caller may mark COPY false)
        return (
            f"Sem evento temporal específico no input; âncora contratual disponível: {insight} "
            "(why_now_strength=WEAK)."
        )
    if trigger == "insufficient_facts":
        return "Material público insuficiente para especialidade — discovery honesto."
    return f"Sem fato contratual concreto para {service_id}; não inventar dor."


def _why_this_account(company: str, hook: str, confirmed: list[dict[str, Any]], service_id: str) -> str:
    """Explain why THIS company warrants the approach (not a PNCP dump)."""
    if hook and not is_hollow_fact(hook):
        insight = _compress_hook_insight(hook, max_len=160)
        # Multi-organ / multi-UF signals → portfolio complexity (real why_you)
        multi = False
        low = hook.lower()
        if "órgão" in low or "orgao" in low:
            multi = True
        return (
            f"{company} aparece com obrigação pública em curso ({insight}). "
            + (
                "Quando a execução cruza órgão/UF e valor material, costuma valer "
                "olhar o contrato com disciplina de monitoramento antes de escalar dor."
                if multi
                else "O objeto e o valor material tornam útil uma leitura objetiva do contrato "
                "antes de assumir que a equipe interna já fechou o tema."
            )
        )
    text, _ = _non_hollow_confirmed(confirmed)
    if text and not is_hollow_fact(text):
        return f"{company}: {text[:220]}"
    return (
        f"{company}: sem objeto contratual específico no input; "
        f"não afirmar portfólio de engenharia sem evidência ({service_id})."
    )


@dataclass(frozen=True)
class MessageSpine:
    observed_fact: str
    why_this_account: str
    why_now: str
    fact_evidence_ids: list[str] = field(default_factory=list)
    micro_offer_code: str = ""
    service_id: str = ""
    body_seed_fact: str = ""
    complete: bool = False
    incomplete_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Canonical micro-offer codes (not approach_mode labels).
MICRO_BY_SERVICE: dict[str, str] = {
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


def build_message_spine(
    bag: dict[str, Any],
    *,
    why: dict[str, Any],
    selection: dict[str, Any],
    layers: dict[str, list[dict[str, Any]]] | None = None,
) -> MessageSpine:
    """Build the sealed messaging spine from bag + router selection.

    Portfolio-count / UFs-only / mature meta may remain in epistemic layers but
    never populate observed_fact or body_seed_fact.
    """
    primary = selection.get("primary_service") or {}
    service_id = str(primary.get("service_id") or primary.get("service_code") or "")
    micro = MICRO_BY_SERVICE.get(service_id, "DIAGNOSTIC_CHECKLIST")
    company = _company_label(bag)
    confirmed = list((layers or {}).get("confirmed_facts") or [])

    hook, hook_ids = extract_contract_hook(bag)
    if not hook:
        conf_text, conf_ids = _non_hollow_confirmed(confirmed)
        hook, hook_ids = conf_text, conf_ids

    why_you = _why_this_account(company, hook, confirmed, service_id)
    why_now = _why_now_text(why if isinstance(why, dict) else {}, hook, service_id)

    incomplete: list[str] = []
    if is_hollow_fact(hook):
        incomplete.append("observed_fact_hollow_or_missing")
    if is_hollow_fact(why_you):
        incomplete.append("why_this_account_hollow")
    if is_hollow_fact(why_now):
        incomplete.append("why_now_hollow")
    if not service_id:
        incomplete.append("service_id_missing")
    if not micro:
        incomplete.append("micro_offer_missing")
    if not hook_ids:
        incomplete.append("fact_evidence_ids_missing")

    observed = "" if is_hollow_fact(hook) else hook
    body_seed = observed  # identical — no second path

    return MessageSpine(
        observed_fact=observed,
        why_this_account=why_you if not is_hollow_fact(why_you) else "",
        why_now=why_now if not is_hollow_fact(why_now) else "",
        fact_evidence_ids=list(hook_ids),
        micro_offer_code=micro,
        service_id=service_id,
        body_seed_fact=body_seed,
        complete=len(incomplete) == 0 and bool(observed),
        incomplete_reasons=incomplete,
    )
