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


def _why_now_text(why: dict[str, Any], hook: str, service_id: str) -> str:
    """Build why_now that passes COPY_CONTEXT (never generic portfolio_review template)."""
    trigger = ""
    if isinstance(why, dict):
        trigger = str(why.get("trigger") or "").strip()
        for key in ("temporal_fact", "summary"):
            val = str(why.get(key) or "").strip()
            if not val or is_hollow_fact(val):
                continue
            # Even non-hollow must not be pure meta without contract hook when we have one.
            if hook and not is_hollow_fact(hook) and "objeto" not in val.lower():
                # Prefer anchoring to concrete hook over abstract summary.
                break
            return val
    if hook and not is_hollow_fact(hook):
        if trigger and trigger not in {"", "insufficient_facts", "portfolio_review"}:
            return f"Momento {trigger} ancorado no fato público: {hook[:160]}"
        # portfolio_review / empty trigger: still require concrete hook, not hollow template
        return f"Fato contratual público utilizável agora: {hook[:160]}"
    if trigger == "insufficient_facts":
        return "Material público insuficiente para especialidade — discovery honesto."
    return f"Sem fato contratual concreto para {service_id}; não inventar dor."


def _why_this_account(company: str, hook: str, confirmed: list[dict[str, Any]], service_id: str) -> str:
    if hook and not is_hollow_fact(hook):
        return f"{company} com execução pública observável — {hook}"
    text, _ = _non_hollow_confirmed(confirmed)
    if text:
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
