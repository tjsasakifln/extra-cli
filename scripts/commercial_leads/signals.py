"""Deterministic commercial signal computation.

Absence of data → NOT_COMPUTABLE (never silent zero / silent penalty).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Any

from scripts.commercial_leads.profile import CommercialProfile

SIGNAL_STATUS_FIRED = "FIRED"
SIGNAL_STATUS_NOT = "NOT_FIRED"
SIGNAL_STATUS_NC = "NOT_COMPUTABLE"


def _fold(text: str | None) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.upper()).strip()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if type(value) is date:
        return value
    # datetime is subclass of date
    if hasattr(value, "date") and callable(value.date) and not isinstance(value, date):
        try:
            return value.date()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001
            return None
    if isinstance(value, date):
        # datetime instance
        try:
            return value.date()  # type: ignore[attr-defined, no-any-return]
        except Exception:  # noqa: BLE001
            return date(value.year, value.month, value.day)
    s = str(value)[:10]
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def object_category(objeto: str | None, keywords_by_segment: list[list[str]]) -> str | None:
    blob = _fold(objeto)
    if not blob:
        return None
    for kws in keywords_by_segment:
        for kw in kws:
            if _fold(kw) and _fold(kw) in blob:
                return _fold(kw)
    # coarse buckets
    for token in ("OBRA", "SERVICO", "SERVICO", "FORNECIMENTO", "PROJETO", "MANUTENCAO"):
        if token in blob:
            return token
    return "OTHER"


@dataclass
class SignalResult:
    signal_id: str
    status: str
    strength: float
    weight: float
    contribution: float
    hypothesis: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    offer: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "status": self.status,
            "strength": self.strength,
            "weight": self.weight,
            "contribution": self.contribution,
            "hypothesis": self.hypothesis,
            "evidence": self.evidence,
            "limitations": self.limitations,
            "offer": self.offer,
            "reason": self.reason,
        }


@dataclass
class ContractRow:
    contrato_id: str | None
    orgao_cnpj: str | None
    orgao_nome: str | None
    fornecedor_cnpj: str | None
    fornecedor_nome: str | None
    objeto_contrato: str | None
    valor_total: float | None
    data_inicio: date | None
    data_fim: date | None
    data_publicacao: date | None
    uf: str | None
    source: str | None
    source_id: str | None


def rows_from_dicts(rows: list[dict[str, Any]]) -> list[ContractRow]:
    out: list[ContractRow] = []
    for r in rows:
        out.append(
            ContractRow(
                contrato_id=r.get("contrato_id"),
                orgao_cnpj=r.get("orgao_cnpj"),
                orgao_nome=r.get("orgao_nome"),
                fornecedor_cnpj=r.get("fornecedor_cnpj"),
                fornecedor_nome=r.get("fornecedor_nome"),
                objeto_contrato=r.get("objeto_contrato"),
                valor_total=_num(r.get("valor_total")),
                data_inicio=_parse_date(r.get("data_inicio")),
                data_fim=_parse_date(r.get("data_fim")),
                data_publicacao=_parse_date(r.get("data_publicacao")),
                uf=(str(r["uf"]).strip().upper() if r.get("uf") else None),
                source=r.get("source"),
                source_id=r.get("source_id"),
            )
        )
    return out


def _evidence_contract(c: ContractRow, **extra: Any) -> dict[str, Any]:
    valor_sem = "valor_total_contracted" if c.valor_total is not None else "valor_absent"
    url = None
    if c.contrato_id and str(c.contrato_id).startswith("http"):
        url = c.contrato_id
    elif c.source_id and str(c.source_id).startswith("http"):
        url = str(c.source_id)
    return {
        "contrato_id": c.contrato_id,
        "orgao_cnpj": c.orgao_cnpj,
        "orgao_nome": c.orgao_nome,
        "objeto": (c.objeto_contrato or "")[:300],
        "valor_total": c.valor_total,
        "valor_semantics": valor_sem,
        "data_publicacao": c.data_publicacao.isoformat() if c.data_publicacao else None,
        "data_fim": c.data_fim.isoformat() if c.data_fim else None,
        "uf": c.uf,
        "source": c.source or "pncp",
        "source_id": c.source_id,
        "official_url_or_id": url or c.contrato_id,
        **extra,
    }


def _hyp(catalog: dict[str, Any], signal_id: str, default: str) -> str:
    for s in catalog.get("signals") or []:
        if isinstance(s, dict) and s.get("id") == signal_id:
            return str(s.get("hypothesis") or default)
    return default


def _offer(profile: CommercialProfile, signal_id: str) -> str | None:
    return (profile.data.get("offers_by_signal") or {}).get(signal_id)


def _weight(profile: CommercialProfile, signal_id: str) -> float:
    return float(profile.weights.get(signal_id, 1.0))


def _mk(
    profile: CommercialProfile,
    signal_id: str,
    status: str,
    strength: float = 0.0,
    evidence: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    reason: str | None = None,
    default_hyp: str = "",
) -> SignalResult:
    w = _weight(profile, signal_id)
    contrib = w * strength if status == SIGNAL_STATUS_FIRED else 0.0
    return SignalResult(
        signal_id=signal_id,
        status=status,
        strength=strength,
        weight=w,
        contribution=contrib,
        hypothesis=_hyp(profile.catalog, signal_id, default_hyp),
        evidence=evidence or [],
        limitations=limitations or [],
        offer=_offer(profile, signal_id),
        reason=reason,
    )


def compute_signals_for_supplier(
    contracts: list[ContractRow],
    profile: CommercialProfile,
    *,
    as_of: date,
    official_acts: list[dict[str, Any]] | None = None,
) -> list[SignalResult]:
    th = profile.thresholds
    recent_days = int(th.get("recent_window_days", 180))
    prior_days = int(th.get("prior_window_days", 365))
    recent_start = as_of - timedelta(days=recent_days)
    prior_start = recent_start - timedelta(days=prior_days)

    dated = [c for c in contracts if c.data_publicacao is not None]
    recent = [c for c in dated if recent_start <= c.data_publicacao <= as_of]  # type: ignore[operator]
    prior = [c for c in dated if prior_start <= c.data_publicacao < recent_start]  # type: ignore[operator]

    seg_kws = [
        list(s.get("object_keywords") or [])
        for s in (profile.data.get("segments") or [])
        if isinstance(s, dict)
    ]
    material = float((profile.data.get("ticket") or {}).get("material_ticket_brl", 500_000))
    results: list[SignalResult] = []

    # 1 first_public_contract
    if not dated:
        results.append(
            _mk(
                profile,
                "first_public_contract",
                SIGNAL_STATUS_NC,
                reason="missing_data_publicacao",
                default_hyp="primeiro contrato público recente",
            )
        )
    else:
        first = min(dated, key=lambda c: c.data_publicacao)  # type: ignore[arg-type, return-value]
        within = int(th.get("first_public_within_days", 365))
        if first.data_publicacao is None:
            results.append(
                _mk(
                    profile,
                    "first_public_contract",
                    SIGNAL_STATUS_NC,
                    reason="missing_first_pub_date",
                    default_hyp="primeiro contrato público recente",
                )
            )
            # continue remaining signals without early return
            first_pub_ok = False
        else:
            first_pub_ok = True
        if first_pub_ok and first.data_publicacao is not None:
            days = (as_of - first.data_publicacao).days
            if days <= within and len(dated) <= 2:
                results.append(
                    _mk(
                        profile,
                        "first_public_contract",
                        SIGNAL_STATUS_FIRED,
                        strength=1.0,
                        evidence=[_evidence_contract(first, days_since_first=days)],
                        default_hyp="primeiro contrato público recente",
                    )
                )
            else:
                results.append(
                    _mk(
                        profile,
                        "first_public_contract",
                        SIGNAL_STATUS_NOT,
                        reason="not_first_or_outside_window",
                        default_hyp="primeiro contrato público recente",
                    )
                )

    # 2 ticket_above_history
    hist_vals = [c.valor_total for c in prior if c.valor_total is not None]
    recent_vals = [(c, c.valor_total) for c in recent if c.valor_total is not None]
    if len(hist_vals) < 3 or not recent_vals:
        results.append(
            _mk(
                profile,
                "ticket_above_history",
                SIGNAL_STATUS_NC,
                reason="insufficient_history_or_recent_value",
                limitations=["requires >=3 historical contracts with valor_total"],
                default_hyp="ticket acima do histórico",
            )
        )
    else:
        med = median(hist_vals)
        ratio_th = float(th.get("ticket_vs_median_ratio", 3.0))
        best = max(recent_vals, key=lambda x: x[1] or 0)
        if med > 0 and best[1] is not None and best[1] >= med * ratio_th and best[1] >= material:
            results.append(
                _mk(
                    profile,
                    "ticket_above_history",
                    SIGNAL_STATUS_FIRED,
                    strength=min(3.0, (best[1] / med) / ratio_th),
                    evidence=[
                        _evidence_contract(
                            best[0],
                            own_median=med,
                            ratio=best[1] / med,
                        )
                    ],
                    default_hyp="ticket acima do histórico",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "ticket_above_history",
                    SIGNAL_STATUS_NOT,
                    reason="ratio_below_threshold",
                    default_hyp="ticket acima do histórico",
                )
            )

    # 3 quantity_growth
    growth_th = float(th.get("growth_ratio", 2.0))
    if not prior:
        results.append(
            _mk(
                profile,
                "quantity_growth",
                SIGNAL_STATUS_NC,
                reason="empty_prior_window",
                default_hyp="crescimento de quantidade",
            )
        )
    elif len(recent) >= max(2, growth_th) and len(recent) >= growth_th * max(len(prior), 1) / max(
        growth_th / growth_th, 1
    ):
        # fire if recent >= growth_ratio * prior
        if len(recent) >= growth_th * len(prior) and len(recent) >= 2:
            results.append(
                _mk(
                    profile,
                    "quantity_growth",
                    SIGNAL_STATUS_FIRED,
                    strength=min(3.0, len(recent) / max(len(prior), 1) / growth_th),
                    evidence=[
                        {
                            "recent_count": len(recent),
                            "prior_count": len(prior),
                            "ratio": len(recent) / max(len(prior), 1),
                            "contracts": [_evidence_contract(c) for c in recent[:3]],
                        }
                    ],
                    default_hyp="crescimento de quantidade",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "quantity_growth",
                    SIGNAL_STATUS_NOT,
                    reason="growth_below_threshold",
                    default_hyp="crescimento de quantidade",
                )
            )
    else:
        results.append(
            _mk(
                profile,
                "quantity_growth",
                SIGNAL_STATUS_NOT,
                reason="growth_below_threshold",
                default_hyp="crescimento de quantidade",
            )
        )

    # 4 value_growth
    sum_r = sum(c.valor_total for c in recent if c.valor_total is not None)
    sum_p = sum(c.valor_total for c in prior if c.valor_total is not None)
    if not prior or (sum_p == 0 and any(c.valor_total is None for c in prior + recent)):
        # if no prior values at all
        if sum_p == 0 and not any(c.valor_total is not None for c in prior):
            results.append(
                _mk(
                    profile,
                    "value_growth",
                    SIGNAL_STATUS_NC,
                    reason="missing_prior_values",
                    default_hyp="crescimento de valor",
                )
            )
        elif sum_p > 0 and sum_r >= growth_th * sum_p and sum_r >= material:
            results.append(
                _mk(
                    profile,
                    "value_growth",
                    SIGNAL_STATUS_FIRED,
                    strength=min(3.0, (sum_r / sum_p) / growth_th),
                    evidence=[
                        {
                            "recent_value_sum": sum_r,
                            "prior_value_sum": sum_p,
                            "ratio": sum_r / sum_p,
                            "valor_semantics": "sum_valor_total_contracted",
                            "contracts": [_evidence_contract(c) for c in recent[:3]],
                        }
                    ],
                    default_hyp="crescimento de valor",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "value_growth",
                    SIGNAL_STATUS_NOT,
                    reason="value_growth_below_threshold",
                    default_hyp="crescimento de valor",
                )
            )
    elif sum_p > 0 and sum_r >= growth_th * sum_p and sum_r >= material:
        results.append(
            _mk(
                profile,
                "value_growth",
                SIGNAL_STATUS_FIRED,
                strength=min(3.0, (sum_r / sum_p) / growth_th),
                evidence=[
                    {
                        "recent_value_sum": sum_r,
                        "prior_value_sum": sum_p,
                        "ratio": sum_r / sum_p,
                        "valor_semantics": "sum_valor_total_contracted",
                        "contracts": [_evidence_contract(c) for c in recent[:3]],
                    }
                ],
                default_hyp="crescimento de valor",
            )
        )
    else:
        results.append(
            _mk(
                profile,
                "value_growth",
                SIGNAL_STATUS_NOT,
                reason="value_growth_below_threshold",
                default_hyp="crescimento de valor",
            )
        )

    def _agency_key(c: ContractRow) -> str | None:
        if c.orgao_cnpj and digits_clean(c.orgao_cnpj):
            return digits_clean(c.orgao_cnpj)[:14]
        if c.orgao_nome:
            return "NAME:" + _fold(c.orgao_nome)[:80]
        return None

    # 5 new_agency
    prior_ag = {k for c in prior if (k := _agency_key(c))}
    recent_ag = {k for c in recent if (k := _agency_key(c))}
    if not any(_agency_key(c) for c in dated):
        results.append(
            _mk(
                profile,
                "new_agency",
                SIGNAL_STATUS_NC,
                reason="agency_identifiers_missing",
                default_hyp="entrada em novo órgão",
            )
        )
    else:
        new_ag = recent_ag - prior_ag
        if new_ag and prior_ag:
            sample = [c for c in recent if _agency_key(c) in new_ag][:3]
            results.append(
                _mk(
                    profile,
                    "new_agency",
                    SIGNAL_STATUS_FIRED,
                    strength=min(2.0, float(len(new_ag))),
                    evidence=[_evidence_contract(c) for c in sample],
                    default_hyp="entrada em novo órgão",
                )
            )
        elif not prior_ag and recent_ag:
            results.append(
                _mk(
                    profile,
                    "new_agency",
                    SIGNAL_STATUS_NC,
                    reason="no_prior_agency_baseline",
                    default_hyp="entrada em novo órgão",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "new_agency",
                    SIGNAL_STATUS_NOT,
                    reason="no_new_agency",
                    default_hyp="entrada em novo órgão",
                )
            )

    # 6 new_region
    prior_uf = {c.uf for c in prior if c.uf}
    recent_uf = {c.uf for c in recent if c.uf}
    if not any(c.uf for c in dated):
        results.append(
            _mk(
                profile,
                "new_region",
                SIGNAL_STATUS_NC,
                reason="uf_missing",
                default_hyp="entrada em nova região",
            )
        )
    else:
        new_uf = recent_uf - prior_uf
        if new_uf and prior_uf:
            sample = [c for c in recent if c.uf in new_uf][:3]
            results.append(
                _mk(
                    profile,
                    "new_region",
                    SIGNAL_STATUS_FIRED,
                    strength=float(len(new_uf)),
                    evidence=[_evidence_contract(c) for c in sample],
                    default_hyp="entrada em nova região",
                )
            )
        elif not prior_uf:
            results.append(
                _mk(
                    profile,
                    "new_region",
                    SIGNAL_STATUS_NC,
                    reason="no_prior_uf_baseline",
                    default_hyp="entrada em nova região",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "new_region",
                    SIGNAL_STATUS_NOT,
                    reason="no_new_uf",
                    default_hyp="entrada em nova região",
                )
            )

    # 7 new_object_category
    def cats(rows: list[ContractRow]) -> set[str]:
        out: set[str] = set()
        for c in rows:
            cat = object_category(c.objeto_contrato, seg_kws)
            if cat:
                out.add(cat)
        return out

    if not any(c.objeto_contrato for c in dated):
        results.append(
            _mk(
                profile,
                "new_object_category",
                SIGNAL_STATUS_NC,
                reason="objeto_missing",
                default_hyp="nova categoria de objeto",
            )
        )
    else:
        pc, rc = cats(prior), cats(recent)
        new_c = rc - pc
        if new_c and pc:
            sample = [c for c in recent if object_category(c.objeto_contrato, seg_kws) in new_c][:3]
            results.append(
                _mk(
                    profile,
                    "new_object_category",
                    SIGNAL_STATUS_FIRED,
                    strength=float(len(new_c)),
                    evidence=[_evidence_contract(c) for c in sample],
                    default_hyp="nova categoria de objeto",
                )
            )
        elif not pc:
            results.append(
                _mk(
                    profile,
                    "new_object_category",
                    SIGNAL_STATUS_NC,
                    reason="no_prior_category_baseline",
                    default_hyp="nova categoria de objeto",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "new_object_category",
                    SIGNAL_STATUS_NOT,
                    reason="no_new_category",
                    default_hyp="nova categoria de objeto",
                )
            )

    # 8 concurrent_portfolio
    conc_min = int(th.get("concurrent_min", 3))
    active = []
    missing_dates = 0
    for c in contracts:
        if c.data_fim is None and c.data_inicio is None:
            missing_dates += 1
            continue
        if c.data_fim is not None and c.data_fim >= as_of:
            active.append(c)
        elif c.data_fim is None and c.data_inicio is not None and c.data_inicio <= as_of:
            # open-ended: treat as active if started
            active.append(c)
    if missing_dates == len(contracts) and contracts:
        results.append(
            _mk(
                profile,
                "concurrent_portfolio",
                SIGNAL_STATUS_NC,
                reason="missing_start_end_dates",
                default_hyp="carteira simultânea",
            )
        )
    elif len(active) >= conc_min:
        results.append(
            _mk(
                profile,
                "concurrent_portfolio",
                SIGNAL_STATUS_FIRED,
                strength=min(3.0, len(active) / conc_min),
                evidence=[_evidence_contract(c) for c in active[:5]],
                default_hyp="carteira simultânea",
            )
        )
    else:
        results.append(
            _mk(
                profile,
                "concurrent_portfolio",
                SIGNAL_STATUS_NOT,
                reason="below_concurrent_min",
                default_hyp="carteira simultânea",
            )
        )

    # 9 agency_concentration
    share_th = float(th.get("agency_concentration_share", 0.70))
    by_ag: dict[str, float] = {}
    total_v = 0.0
    for c in dated:
        if c.valor_total is None:
            continue
        k = _agency_key(c)
        if not k:
            continue
        by_ag[k] = by_ag.get(k, 0.0) + c.valor_total
        total_v += c.valor_total
    if total_v <= 0 or not by_ag:
        results.append(
            _mk(
                profile,
                "agency_concentration",
                SIGNAL_STATUS_NC,
                reason="missing_orgao_or_valor",
                default_hyp="concentração em órgão",
            )
        )
    else:
        top_k, top_v = max(by_ag.items(), key=lambda x: x[1])
        share = top_v / total_v
        if share >= share_th:
            sample = [c for c in dated if _agency_key(c) == top_k][:3]
            results.append(
                _mk(
                    profile,
                    "agency_concentration",
                    SIGNAL_STATUS_FIRED,
                    strength=share,
                    evidence=[_evidence_contract(c, agency_share=share) for c in sample],
                    default_hyp="concentração em órgão",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "agency_concentration",
                    SIGNAL_STATUS_NOT,
                    reason="share_below_threshold",
                    default_hyp="concentração em órgão",
                )
            )

    # 10 contract_concentration
    cshare_th = float(th.get("contract_concentration_share", 0.50))
    by_ct: dict[str, float] = {}
    total_c = 0.0
    for c in dated:
        if c.valor_total is None:
            continue
        k = c.contrato_id or f"anon:{id(c)}"
        by_ct[k] = by_ct.get(k, 0.0) + c.valor_total
        total_c += c.valor_total
    if total_c <= 0:
        results.append(
            _mk(
                profile,
                "contract_concentration",
                SIGNAL_STATUS_NC,
                reason="missing_valor_total",
                default_hyp="concentração em contrato",
            )
        )
    else:
        top_id, top_cv = max(by_ct.items(), key=lambda x: x[1])
        share = top_cv / total_c
        if share >= cshare_th:
            sample = [c for c in dated if (c.contrato_id or f"anon:{id(c)}") == top_id][:2]
            results.append(
                _mk(
                    profile,
                    "contract_concentration",
                    SIGNAL_STATUS_FIRED,
                    strength=share,
                    evidence=[_evidence_contract(c, contract_share=share) for c in sample],
                    default_hyp="concentração em contrato",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "contract_concentration",
                    SIGNAL_STATUS_NOT,
                    reason="share_below_threshold",
                    default_hyp="concentração em contrato",
                )
            )

    # 11 near_expiry
    expiry_days = int(th.get("near_expiry_days", 120))
    horizon = as_of + timedelta(days=expiry_days)
    expiring = [c for c in contracts if c.data_fim and as_of <= c.data_fim <= horizon]
    if not any(c.data_fim for c in contracts):
        results.append(
            _mk(
                profile,
                "near_expiry",
                SIGNAL_STATUS_NC,
                reason="data_fim_missing",
                default_hyp="contratos próximos do término",
            )
        )
    elif expiring:
        results.append(
            _mk(
                profile,
                "near_expiry",
                SIGNAL_STATUS_FIRED,
                strength=min(2.0, len(expiring) / 2),
                evidence=[_evidence_contract(c) for c in expiring[:5]],
                default_hyp="contratos próximos do término",
            )
        )
    else:
        results.append(
            _mk(
                profile,
                "near_expiry",
                SIGNAL_STATUS_NOT,
                reason="no_near_expiry",
                default_hyp="contratos próximos do término",
            )
        )

    # 12 addendum_recurrence / 13 adverse_event from official acts
    acts = official_acts or []
    if not acts:
        results.append(
            _mk(
                profile,
                "addendum_recurrence",
                SIGNAL_STATUS_NC,
                reason="no_official_acts_data",
                limitations=["official_acts table empty or not linked for supplier"],
                default_hyp="recorrência de aditivos",
            )
        )
        results.append(
            _mk(
                profile,
                "adverse_event",
                SIGNAL_STATUS_NC,
                reason="no_official_acts_data",
                limitations=["official_acts table empty or not linked for supplier"],
                default_hyp="evento adverso oficial",
            )
        )
    else:
        add_types = {"aditivo", "apostilamento", "prorrogacao", "prorrogação", "extension", "addendum"}
        adv_types = {"suspensao", "suspensão", "rescisao", "rescisão", "sancao", "sanção", "penalty"}
        add_acts = [
            a
            for a in acts
            if any(t in _fold(str(a.get("act_type") or a.get("tipo") or "")) for t in (_fold(x) for x in add_types))
        ]
        adv_acts = [
            a
            for a in acts
            if any(t in _fold(str(a.get("act_type") or a.get("tipo") or "")) for t in (_fold(x) for x in adv_types))
        ]
        if len(add_acts) >= 2:
            results.append(
                _mk(
                    profile,
                    "addendum_recurrence",
                    SIGNAL_STATUS_FIRED,
                    strength=min(2.0, len(add_acts) / 2),
                    evidence=[{"act": a, "note": "official publication only"} for a in add_acts[:5]],
                    default_hyp="recorrência de aditivos",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "addendum_recurrence",
                    SIGNAL_STATUS_NOT,
                    reason="below_addendum_threshold",
                    default_hyp="recorrência de aditivos",
                )
            )
        # adverse: require URL
        adv_with_url = [a for a in adv_acts if a.get("url") or a.get("official_url") or a.get("source_url")]
        if adv_with_url:
            results.append(
                _mk(
                    profile,
                    "adverse_event",
                    SIGNAL_STATUS_FIRED,
                    strength=1.0,
                    evidence=[
                        {
                            "act": a,
                            "language": "evento adverso publicado oficialmente; não constitui acusação",
                        }
                        for a in adv_with_url[:3]
                    ],
                    default_hyp="evento adverso oficial",
                )
            )
        elif adv_acts:
            results.append(
                _mk(
                    profile,
                    "adverse_event",
                    SIGNAL_STATUS_NC,
                    reason="adverse_act_without_official_url",
                    default_hyp="evento adverso oficial",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "adverse_event",
                    SIGNAL_STATUS_NOT,
                    reason="no_adverse_acts",
                    default_hyp="evento adverso oficial",
                )
            )

    # 14 diversity_increase
    div_min = int(th.get("diversity_new_organs_min", 2))
    if not any(_agency_key(c) for c in dated):
        results.append(
            _mk(
                profile,
                "diversity_increase",
                SIGNAL_STATUS_NC,
                reason="agency_identifiers_missing",
                default_hyp="aumento de diversidade",
            )
        )
    else:
        delta = len(recent_ag) - len(prior_ag)
        if prior and delta >= div_min:
            results.append(
                _mk(
                    profile,
                    "diversity_increase",
                    SIGNAL_STATUS_FIRED,
                    strength=min(2.0, delta / div_min),
                    evidence=[
                        {
                            "recent_organs": len(recent_ag),
                            "prior_organs": len(prior_ag),
                            "delta": delta,
                        }
                    ],
                    default_hyp="aumento de diversidade",
                )
            )
        elif not prior:
            results.append(
                _mk(
                    profile,
                    "diversity_increase",
                    SIGNAL_STATUS_NC,
                    reason="no_prior_baseline",
                    default_hyp="aumento de diversidade",
                )
            )
        else:
            results.append(
                _mk(
                    profile,
                    "diversity_increase",
                    SIGNAL_STATUS_NOT,
                    reason="diversity_delta_below_threshold",
                    default_hyp="aumento de diversidade",
                )
            )

    # 15 win_recurrence
    win_min = int(th.get("win_recurrence_min", 3))
    window_all = [c for c in dated if c.data_publicacao and prior_start <= c.data_publicacao <= as_of]
    if not dated:
        results.append(
            _mk(
                profile,
                "win_recurrence",
                SIGNAL_STATUS_NC,
                reason="dates_missing",
                default_hyp="recorrência de vitórias",
            )
        )
    elif len(window_all) >= win_min:
        results.append(
            _mk(
                profile,
                "win_recurrence",
                SIGNAL_STATUS_FIRED,
                strength=min(2.0, len(window_all) / win_min),
                evidence=[_evidence_contract(c) for c in window_all[:5]],
                default_hyp="recorrência de vitórias",
            )
        )
    else:
        results.append(
            _mk(
                profile,
                "win_recurrence",
                SIGNAL_STATUS_NOT,
                reason="below_win_min",
                default_hyp="recorrência de vitórias",
            )
        )

    return results


def digits_clean(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _dampen_group(results: list[SignalResult], group_ids: set[str]) -> list[SignalResult]:
    fired = [r for r in results if r.signal_id in group_ids and r.status == SIGNAL_STATUS_FIRED]
    if len(fired) < 2:
        return results
    keep = sorted(fired, key=lambda r: r.contribution, reverse=True)[0].signal_id
    out: list[SignalResult] = []
    for r in results:
        if r.signal_id in group_ids and r.status == SIGNAL_STATUS_FIRED and r.signal_id != keep:
            out.append(
                SignalResult(
                    signal_id=r.signal_id,
                    status=r.status,
                    strength=r.strength,
                    weight=r.weight,
                    contribution=r.contribution * 0.5,
                    hypothesis=r.hypothesis,
                    evidence=r.evidence,
                    limitations=list(r.limitations) + [f"correlation_dampening_applied_vs_{keep}"],
                    offer=r.offer,
                    reason=r.reason,
                )
            )
        else:
            out.append(r)
    return out


def decorrelate_contributions(results: list[SignalResult]) -> list[SignalResult]:
    """Limit inflation from correlated signal groups (growth; concentration)."""
    out = _dampen_group(results, {"quantity_growth", "value_growth", "diversity_increase"})
    out = _dampen_group(out, {"agency_concentration", "contract_concentration"})
    return out
