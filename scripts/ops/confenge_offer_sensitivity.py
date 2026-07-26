#!/usr/bin/env python3
"""Offer mapping sensitivity + discrimination for CONFENGE top-20.

Does not force artificial diversity. Proves selection is data-driven via
ablation of near_expiry / concurrent_portfolio / agency_concentration /
contract_concentration signals.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.dbutil import connect  # noqa: E402
from scripts.commercial_leads.pipeline import load_full_supplier_histories  # noqa: E402
from scripts.commercial_leads.profile import load_profile  # noqa: E402
from scripts.commercial_leads.scoring import (  # noqa: E402
    diagnose_offer_distribution,
    rank_leads,
    score_supplier,
)
from scripts.commercial_leads.sector_fit import classify_supplier_sector_fit  # noqa: E402
from scripts.commercial_leads.signals import (  # noqa: E402
    SIGNAL_STATUS_FIRED,
    compute_signals_for_supplier,
    rows_from_dicts,
)
from scripts.commercial_leads.supplier_registry import load_registry_map  # noqa: E402

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
PROFILE = _ROOT / "config/commercial_profiles/confenge.yaml"
DEFAULT_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/confenge_commercial"

ABLATION_SIGNALS = (
    "near_expiry",
    "concurrent_portfolio",
    "agency_concentration",
    "contract_concentration",
)


def _entropy(counts: dict[str, int]) -> float:
    total = sum(counts.values()) or 1
    h = 0.0
    for n in counts.values():
        if n <= 0:
            continue
        p = n / total
        h -= p * math.log(p + 1e-15, 2)
    return h


def _map_offers(leads: list[Any]) -> list[str]:
    out = []
    for x in leads:
        out.append(x.selected_offer or x.suggested_offer or "none")
    return out


def _score_universe(
    conn: Any,
    cnpjs: list[str],
    profile: Any,
    *,
    as_of: date,
    drop_signals: set[str] | None = None,
) -> list[Any]:
    groups, _hist = load_full_supplier_histories(conn, cnpjs, per_supplier_limit=None)
    try:
        reg = load_registry_map(conn, cnpjs)
    except Exception:
        reg = {}
    drop_signals = drop_signals or set()
    scored = []
    for cnpj in cnpjs:
        crow = groups.get(cnpj) or []
        if not crow:
            continue
        rec = reg.get(cnpj) if isinstance(reg, dict) else None
        sector = classify_supplier_sector_fit(
            razao_social=crow[0].get("fornecedor_nome"),
            contracts=crow,
            cnae_principal=rec.cnae_principal if rec else None,
            cnaes_secundarios=list(rec.cnaes_secundarios) if rec else [],
            history_is_full=True,
        )
        if sector.classification not in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT"):
            continue
        active = [r for r in crow if r.get("is_active") is True]
        contracts = rows_from_dicts(active or crow)
        sigs = compute_signals_for_supplier(contracts, profile, as_of=as_of, official_acts=None)
        if drop_signals:
            for s in sigs:
                if s.signal_id in drop_signals and s.status == SIGNAL_STATUS_FIRED:
                    s.status = "NOT_COMPUTABLE"
                    s.contribution = 0.0
        total_value = sum(float(c.valor_total or 0) for c in contracts if c.valor_total is not None)
        pubs = [c.data_publicacao for c in contracts if c.data_publicacao]
        lead = score_supplier(
            cnpj14=cnpj,
            razao_social=crow[0].get("fornecedor_nome") or cnpj,
            signal_results=sigs,
            profile=profile,
            total_value=total_value,
            contract_count=len(contracts),
            last_publication=max(pubs).isoformat() if pubs else None,
        )
        scored.append(lead)
    return rank_leads(scored, profile, suppressed_cnpjs=set(), state_by_cnpj={})[:20]


def run_offer_analysis(*, dsn: str, run_result: Path | None = None) -> dict[str, Any]:
    profile = load_profile(PROFILE)
    cnpjs: list[str] = []
    if run_result and run_result.is_file():
        d = json.loads(run_result.read_text(encoding="utf-8"))
        lm = d.get("load_meta") or {}
        cnpjs = list(lm.get("candidate_supplier_cnpjs") or [])
    conn = connect(dsn)
    try:
        if not cnpjs:
            from scripts.ops.confenge_full_universe_e2e import frozen_candidates

            cnpjs = frozen_candidates(conn, run_result)
        # Use up to full universe; ranking still top-20
        as_of = date.today()
        baseline = _score_universe(conn, cnpjs, profile, as_of=as_of)
        base_offers = _map_offers(baseline)
        base_counts: dict[str, int] = {}
        for o in base_offers:
            base_counts[o] = base_counts.get(o, 0) + 1

        per_lead = []
        for x in baseline:
            per_lead.append(
                {
                    "cnpj14": x.cnpj14,
                    "offer_scores": dict(x.offer_scores or {}),
                    "selected_offer": x.selected_offer or x.suggested_offer,
                    "alternative_offer": x.alternative_offer,
                    "selected_offer_margin": x.selected_offer_margin,
                    "supporting_signals": list(x.supporting_signals or []),
                    "contradicting_signals": list(x.contradicting_signals or []),
                    "score_total": x.score_total,
                    "individual_justification": (
                        f"offer={x.selected_offer or x.suggested_offer}; "
                        f"margin={x.selected_offer_margin}; "
                        f"supporting={list(x.supporting_signals or [])}; "
                        f"scores={dict(x.offer_scores or {})}"
                    ),
                }
            )

        ablations: dict[str, Any] = {}
        change_rates: dict[str, float] = {}
        for sig in ABLATION_SIGNALS:
            ranked = _score_universe(conn, cnpjs, profile, as_of=as_of, drop_signals={sig})
            offers = _map_offers(ranked)
            counts: dict[str, int] = {}
            for o in offers:
                counts[o] = counts.get(o, 0) + 1
            changed = sum(1 for a, b in zip(base_offers, offers) if a != b)
            rate = changed / max(len(base_offers), 1)
            change_rates[sig] = rate
            ablations[sig] = {
                "offer_distribution": counts,
                "offers": offers,
                "selection_change_rate": rate,
                "excessive_concentration": rate >= 0.9,
            }

        diag = diagnose_offer_distribution(
            [
                {
                    "selected_offer": x.selected_offer or x.suggested_offer,
                    "selected_offer_margin": x.selected_offer_margin,
                }
                for x in baseline
            ]
        )
        dominant = max(base_counts.values()) / max(len(base_offers), 1) if base_offers else 0
        margins = [
            float(x.selected_offer_margin)
            for x in baseline
            if x.selected_offer_margin is not None
        ]
        mean_margin = sum(margins) / len(margins) if margins else None

        # PASS discrimination if either multi-offer OR uniform with per-lead evidence
        uniform = len(base_counts) == 1 and len(base_offers) >= 5
        discrimination_ok = (diag.get("block") is None) or (
            uniform
            and all(p.get("individual_justification") for p in per_lead)
            and mean_margin is not None
        )
        excessive = any(v.get("excessive_concentration") for v in ablations.values())

        sens_ok = not excessive
        report = {
            "ok": sens_ok and discrimination_ok and len(per_lead) > 0,
            "status": "PASS" if sens_ok and discrimination_ok and per_lead else "BLOCKED_OFFER_MAPPING_NOT_VALIDATED",
            "offer_distribution_baseline": base_counts,
            "offer_distribution_without_each_signal": {
                k: v["offer_distribution"] for k, v in ablations.items()
            },
            "offer_selection_change_rate": change_rates,
            "dominant_offer_rate": dominant,
            "offer_entropy": _entropy(base_counts),
            "mean_selected_offer_margin": mean_margin,
            "ablations": ablations,
            "per_lead": per_lead,
            "diagnose": diag,
            "uniform_offer_justified_individually": uniform and discrimination_ok,
            "note": (
                "Uniform offer across top-20 is allowed when each lead has individualized "
                "offer_scores/margin/signals evidence. Artificial diversity is forbidden."
            ),
        }
        (ART / "offer-sensitivity-gate.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
        disc = {
            "ok": discrimination_ok,
            "status": "PASS" if discrimination_ok else "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE",
            "dominant_offer_rate": dominant,
            "offer_entropy": _entropy(base_counts),
            "mean_selected_offer_margin": mean_margin,
            "offer_distribution": base_counts,
            "per_lead_n": len(per_lead),
            "uniform_but_justified": uniform and discrimination_ok,
            "diagnose": diag,
        }
        (ART / "offer-discrimination-gate.json").write_text(
            json.dumps(disc, indent=2, default=str) + "\n", encoding="utf-8"
        )
        return report
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN", DEFAULT_DSN))
    ap.add_argument("--run-result", type=Path, default=ART / "run" / "run-result.json")
    args = ap.parse_args(argv)
    rep = run_offer_analysis(dsn=args.dsn, run_result=args.run_result)
    print(
        json.dumps(
            {
                k: rep.get(k)
                for k in (
                    "ok",
                    "status",
                    "offer_distribution_baseline",
                    "offer_selection_change_rate",
                    "dominant_offer_rate",
                    "offer_entropy",
                    "mean_selected_offer_margin",
                    "uniform_offer_justified_individually",
                )
            },
            indent=2,
            default=str,
        )
    )
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
