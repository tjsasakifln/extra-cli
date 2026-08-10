"""Single MessageSpine for CONFENGE outreach copy.

All consumer paths (dossier, draft body, Warmbly strategy, COPY_CONTEXT_READY)
must read messaging fields from this spine — never from confirmed[0] portfolio-count.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
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
    re.compile(r"sem\s+dor\s+concreta\s+dominante", re.I),
    re.compile(r"sem\s+dor\s+contratual\s+concreta", re.I),
    re.compile(r"sem\s+dor\s+concreta", re.I),
    re.compile(r"momento\s+comercial\s+p[uú]blico", re.I),
    re.compile(r"execu[cç][aã]o\s+p[uú]blica\s+observ[aá]vel", re.I),
    re.compile(r"empresa\s+com\s+execu[cç][aã]o\s+p[uú]blica", re.I),
    re.compile(r"portf[oó]lio\s+multi-contrato\s+ativo", re.I),
    re.compile(r"why_now_strength\s*=\s*(?:moderate|weak)", re.I),
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


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    s = str(val).strip()[:10]
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _extract_temporal_event(bag: dict[str, Any], why: dict[str, Any]) -> tuple[str, str]:
    """Return (why_now_text, strength) strength in {STRONG, MODERATE, WEAK}.

    STRENGTH rules (objective §6):
    - STRONG: dated aditivo/prorrogação/publicação/aniversário/medição with timestamp
    - WEAK: no dated temporal event (even if contract hook exists) → COPY not ready
    """
    today = date.today()
    trigger = str((why or {}).get("trigger") or "").strip()
    # Explicit non-hollow temporal_fact with a date token
    for key in ("temporal_fact", "summary"):
        val = str((why or {}).get(key) or "").strip()
        if not val or is_hollow_fact(val):
            continue
        if re.search(r"20\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/20\d{2}|20\d{2}", val):
            if trigger in {"portfolio_review", "insufficient_facts", ""}:
                # Still accept if text itself has a dated event language
                if any(
                    k in val.lower()
                    for k in (
                        "publicad",
                        "aditivo",
                        "prorroga",
                        "anivers",
                        "medi",
                        "glosa",
                        "licita",
                        "contrata",
                        "inici",
                        "término",
                        "termino",
                        "venciment",
                    )
                ):
                    return val, "STRONG"
            else:
                return val, "STRONG"

    contracts = bag.get("contracts") or []
    dated: list[tuple[date, str, dict[str, Any]]] = []
    for c in contracts:
        if not isinstance(c, dict):
            continue
        for date_field, label in (
            ("publication_date", "publicação"),
            ("data_publicacao", "publicação"),
            ("start_date", "início de execução"),
            ("data_inicio", "início de execução"),
            ("end_date", "término previsto"),
            ("data_fim", "término previsto"),
        ):
            d = _parse_date(c.get(date_field))
            if d:
                dated.append((d, label, c))

    if not dated and trigger in {
        "aditivo",
        "additive",
        "CONTRACT_EXTENSION",
        "prorrogacao",
        "prorrogação",
        "anualidade",
        "ANUALIDADE",
        "mature_no_reajuste",
        "medicao",
        "medição",
        "glosa",
    }:
        # Trigger names alone without dates are still WEAK (no inventing "now")
        return (
            f"Gatilho {trigger} sem timestamp verificável no input "
            "(why_now_strength=WEAK).",
            "WEAK",
        )

    if dated:
        # Prefer most recent publication/start within ~540 days
        dated.sort(key=lambda x: x[0], reverse=True)
        for d, label, c in dated:
            age = (today - d).days
            if age < 0:
                age = 0
            if age > 540 and label != "término previsto":
                continue
            obj = str(c.get("object") or c.get("objeto") or "")[:100]
            org = str(c.get("orgao") or c.get("agency") or "")[:80]
            bits = [f"{label} em {d.isoformat()}"]
            if org:
                bits.append(f"órgão {org}")
            if obj:
                bits.append(f"objeto: {obj}")
            # Near end_date → anniversary/termination window
            if label == "término previsto":
                days_left = (d - today).days
                if -30 <= days_left <= 180:
                    return (
                        "Contrato com "
                        + "; ".join(bits)
                        + f" (horizonte ~{days_left} dias) — janela temporal verificável.",
                        "STRONG",
                    )
                continue
            if age <= 180:
                # Diversify phrasing (blind-template must not collapse all to one scaffold)
                h = (age + len(bits[0]) + len(obj)) % 3
                recent = (
                    "Evento contratual público recente: " + "; ".join(bits) + ".",
                    "Publicação/marco recente no PNCP: " + "; ".join(bits) + ".",
                    "Há um marco datado e recente na carteira pública: "
                    + "; ".join(bits)
                    + ".",
                )
                return recent[h], "STRONG"
            if age <= 400:
                h = (age + len(bits[0])) % 3
                mid = (
                    "Marco contratual datado no portfólio: " + "; ".join(bits) + ".",
                    "Ainda no horizonte operacional: " + "; ".join(bits) + ".",
                    "Registro público com data verificável: " + "; ".join(bits) + ".",
                )
                return mid[h], "MODERATE"

    # No dated event → WEAK (do not invent "now")
    return (
        "Sem evento temporal datado no input (why_now_strength=WEAK); "
        "manter em pesquisa/reservatório até haver aditivo, publicação, "
        "aniversário ou outro marco verificável.",
        "WEAK",
    )


def _why_now_text(why: dict[str, Any], hook: str, service_id: str, bag: dict[str, Any] | None = None) -> tuple[str, str]:
    """Return (why_now, strength). strength WEAK ⇒ spine incomplete / COPY false."""
    bag = bag or {}
    text, strength = _extract_temporal_event(bag, why if isinstance(why, dict) else {})
    if strength != "WEAK" and text and not is_hollow_fact(text):
        return text, strength
    # Force WEAK path — never MODERATE invented from undated portfolio
    return text if text else (
        f"Sem fato temporal concreto para {service_id} (why_now_strength=WEAK)."
    ), "WEAK"


def _object_theme(hook: str) -> str:
    low = (hook or "").lower()
    themes = [
        (("paviment", "cbuq", "asfalt"), "pavimentação/vias"),
        (("saneamento", "esgoto", "rede de água", "abastecimento"), "saneamento"),
        (("obra de arte", "ponte", "viaduto"), "obra de arte especial"),
        (("edifica", "predial", "reforma"), "edificação/reforma"),
        (("drenagem", "macrodren"), "drenagem"),
        (("terraplen", "movimento de terra"), "terraplenagem"),
        (("licita", "edital", "proposta"), "frente de licitação"),
        (("medição", "medicao", "glosa"), "ciclo de medição"),
        (("aditivo", "prorroga"), "aditivo/prorrogação"),
        (("bdi", "planilha", "orçamento"), "planilha/BDI"),
    ]
    for keys, label in themes:
        if any(k in low for k in keys):
            return label
    return "execução contratual pública"


def _why_this_account(
    company: str,
    hook: str,
    confirmed: list[dict[str, Any]],
    service_id: str,
    bag: dict[str, Any] | None = None,
) -> str:
    """Explain why THIS company warrants the approach (not a fixed PNCP dump scaffold)."""
    bag = bag or {}
    contracts = [c for c in (bag.get("contracts") or []) if isinstance(c, dict)]
    orgaos = {
        str(c.get("orgao") or c.get("agency") or "").strip()
        for c in contracts
        if str(c.get("orgao") or c.get("agency") or "").strip()
    }
    ufs = {str(c.get("uf") or "").strip().upper() for c in contracts if str(c.get("uf") or "").strip()}
    n = len(contracts)
    theme = _object_theme(hook)

    if hook and not is_hollow_fact(hook):
        insight = _compress_hook_insight(hook, max_len=120)
        # Hash company so same shape does not always pick the same skeleton (blind-template).
        h = sum(ord(c) for c in (company or "")) % 3
        # Diversify structure by portfolio shape + company hash
        if n >= 3 and len(orgaos) >= 2 and len(ufs) >= 2:
            variants = (
                (
                    f"{company} concentra {n} frentes públicas recentes em {len(ufs)} UFs "
                    f"e {len(orgaos)} órgãos, com ênfase em {theme}. "
                    f"Âncora: {insight}."
                ),
                (
                    f"Olhando o recorte público de {company}, {theme} aparece espalhado em "
                    f"{len(ufs)} UFs / {len(orgaos)} órgãos (≈{n} frentes). "
                    f"Ponto de partida: {insight}."
                ),
                (
                    f"O que chama atenção em {company} não é um edital isolado: são "
                    f"{n} frentes recentes em geografia e órgãos distintos ({theme}). "
                    f"Fato utilizável: {insight}."
                ),
            )
            return variants[h]
        if n >= 3 and len(orgaos) >= 2:
            variants = (
                (
                    f"A carteira pública de {company} distribui {theme} entre "
                    f"{len(orgaos)} órgãos distintos — o custo de priorizar o contrato "
                    f"errado sobe quando medições e marcos não compartilham a mesma fiscalização. "
                    f"Fato-base: {insight}."
                ),
                (
                    f"Em {company}, {theme} passa por {len(orgaos)} fiscalizações diferentes "
                    f"ao mesmo tempo. Isso muda a ordem de conversa: primeiro qual contrato "
                    f"pesa mais, depois o detalhe. Âncora: {insight}."
                ),
                (
                    f"{company} opera {theme} sob múltiplos órgãos ({len(orgaos)}). "
                    f"Sem assumir dor interna: o ângulo é só a coordenação pública observável. "
                    f"Marco: {insight}."
                ),
            )
            return variants[h]
        if n >= 3:
            variants = (
                (
                    f"{company} mantém múltiplos contratos públicos em paralelo "
                    f"(n≈{n}) no tema {theme}. Isso muda o tipo de conversa: "
                    f"não é um edital isolado, é ritmo de carteira. Âncora: {insight}."
                ),
                (
                    f"Há ritmo de carteira em {company}: cerca de {n} contratos públicos "
                    f"no tema {theme}, não um evento único. Âncora: {insight}."
                ),
                (
                    f"Para {company}, o encaixe parte do volume paralelo (~{n}) em {theme}. "
                    f"Fato: {insight}."
                ),
            )
            return variants[h]
        if len(ufs) >= 2:
            uf_s = ", ".join(sorted(ufs)[:4])
            variants = (
                (
                    f"{company} aparece com {theme} em mais de uma UF "
                    f"({uf_s}). Âncora pública: {insight}."
                ),
                (
                    f"Há presença multi-UF de {theme} em {company} ({uf_s}). "
                    f"Ponto concreto: {insight}."
                ),
                (
                    f"{company} — {theme} cruzando UFs ({uf_s}). "
                    f"Fato: {insight}."
                ),
            )
            return variants[h]
        # Single-contract but specific object
        variants = (
            (
                f"No caso de {company}, o encaixe parte de um fato concreto de {theme}: "
                f"{insight}. Sem generalizar portfólio além do que está no input."
            ),
            (
                f"Para {company}, o gancho é específico em {theme}: {insight}. "
                f"Não extrapolamos para a carteira inteira sem mais evidência."
            ),
            (
                f"{company} — foco no fato de {theme} disponível no input: {insight}."
            ),
        )
        return variants[h]
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

    why_you = _why_this_account(company, hook, confirmed, service_id, bag=bag)
    why_now, why_now_strength = _why_now_text(
        why if isinstance(why, dict) else {}, hook, service_id, bag=bag
    )

    incomplete: list[str] = []
    if is_hollow_fact(hook):
        incomplete.append("observed_fact_hollow_or_missing")
    if is_hollow_fact(why_you):
        incomplete.append("why_this_account_hollow")
    if is_hollow_fact(why_now) or why_now_strength == "WEAK":
        # §6: no dated temporal event ⇒ not COPY_CONTEXT_READY / spine incomplete
        incomplete.append("why_now_weak_or_hollow")
    if not service_id:
        incomplete.append("service_id_missing")
    if not micro:
        incomplete.append("micro_offer_missing")
    if not hook_ids:
        incomplete.append("fact_evidence_ids_missing")

    observed = "" if is_hollow_fact(hook) else hook
    body_seed = observed  # identical — no second path
    # Never surface WEAK why_now as a sendable field
    why_now_out = "" if why_now_strength == "WEAK" or is_hollow_fact(why_now) else why_now

    return MessageSpine(
        observed_fact=observed,
        why_this_account=why_you if not is_hollow_fact(why_you) else "",
        why_now=why_now_out,
        fact_evidence_ids=list(hook_ids),
        micro_offer_code=micro,
        service_id=service_id,
        body_seed_fact=body_seed,
        complete=len(incomplete) == 0 and bool(observed) and why_now_strength != "WEAK",
        incomplete_reasons=incomplete,
    )
