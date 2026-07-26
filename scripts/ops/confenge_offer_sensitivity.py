#!/usr/bin/env python3
"""Offer mapping sensitivity + discrimination for CONFENGE top-20.

PASS requires cumulative quantitative criteria. Presence of free-text
``individual_justification`` NEVER overrides diagnose.block / degeneracy flags.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
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
    MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE,
    MIN_SELECTED_OFFER_MARGIN,
    OFFER_SCORE_KEYS,
    _SIGNAL_OFFER_WEIGHTS,
    diagnose_offer_distribution,
    rank_leads,
    score_supplier,
)  # noqa: I001
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


def _score_universe(
    conn: Any,
    cnpjs: list[str],
    profile: Any,
    *,
    as_of: date,
    drop_signals: set[str] | None = None,
    rank_limit: int | None = None,
    require_engineering: bool = True,
) -> list[Any]:
    """Score candidates; optionally rank-limit for top-N publication lists.

    For ablation sensitivity on a fixed lead set, pass rank_limit=None and
    require_engineering=False only when the CNPJ list is already the fixed set
    (callers still apply sector filter for baseline discovery).
    """
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
        if require_engineering and sector.classification not in (
            "CONFIRMED_ENGINEERING",
            "STRONG_ENGINEERING_FIT",
        ):
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
    ranked = rank_leads(scored, profile, suppressed_cnpjs=set(), state_by_cnpj={})
    if rank_limit is not None:
        return ranked[:rank_limit]
    return ranked


def _lead_dict(x: Any) -> dict[str, Any]:
    return {
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


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return round(num / (dx * dy), 4)


def evaluate_offer_pass(
    *,
    baseline: list[Any],
    diag: dict[str, Any],
    change_rates: dict[str, float],
    max_change_rate: float = MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE,
    min_margin: float = MIN_SELECTED_OFFER_MARGIN,
) -> dict[str, Any]:
    """Pure PASS decision — no text justification override.

    Cumulative rules (all required for PASS):
    - multi positive offer score buckets on every lead
    - alternative_offer populated for all leads
    - selected_offer_margin >= min_margin for all leads
    - selected_offer not hardcoded constant without scores
    - offer scores vary materially across leads
    - supporting signals vary materially across leads
    - diagnose.block is null
    - catalog_degenerate is false
    - robust_quantitative_justification is true
    - no single-signal ablation change rate > max_change_rate
    """
    reasons: list[str] = []
    n = len(baseline)
    if n == 0:
        return {
            "ok": False,
            "status": "BLOCKED_OFFER_MAPPING_NOT_VALIDATED",
            "reasons": ["empty_top20"],
            "diagnose_block": diag.get("block"),
        }

    multi_buckets_all = True
    alt_all = True
    margin_all = True
    hardcoded = False
    for x in baseline:
        scores = dict(x.offer_scores or {})
        pos = sum(1 for v in scores.values() if float(v or 0) > 0)
        if pos < 2:
            multi_buckets_all = False
        if not (x.alternative_offer or "").strip():
            alt_all = False
        m = x.selected_offer_margin
        if m is None or float(m) < min_margin:
            margin_all = False
        # Hardcoded: selected offer with zero score mass
        sel = x.selected_offer or x.suggested_offer
        if sel and pos == 0:
            hardcoded = True

    if not multi_buckets_all:
        reasons.append("not_all_leads_have_multiple_positive_offer_score_buckets")
    if not alt_all:
        reasons.append("alternative_offer_missing_for_some_leads")
    if not margin_all:
        reasons.append(f"selected_offer_margin_below_minimum_{min_margin}")
    if hardcoded:
        reasons.append("selected_offer_hardcoded_without_scores")

    # Material variation of offer scores across leads (entropy of selected offers
    # OR variance of at least one score key)
    offer_dist = Counter((x.selected_offer or x.suggested_offer or "none") for x in baseline)
    score_varies = len(offer_dist) >= 2
    if not score_varies:
        # allow same winner if per-bucket score vectors still differ materially
        vectors = []
        for x in baseline:
            scores = dict(x.offer_scores or {})
            vectors.append(tuple(round(float(scores.get(k) or 0), 3) for k in OFFER_SCORE_KEYS))
        score_varies = len(set(vectors)) >= max(2, n // 5)
    if not score_varies:
        reasons.append("offer_scores_do_not_vary_materially_across_leads")

    support_sets = [tuple(sorted(x.supporting_signals or [])) for x in baseline]
    # Material variation: at least 2 distinct support patterns, and the most common
    # pattern must not cover the entire population (no single universal signature).
    n_distinct_support = len(set(support_sets))
    if support_sets:
        top_support_share = max(support_sets.count(s) for s in set(support_sets)) / n
    else:
        top_support_share = 1.0
    signals_vary = n_distinct_support >= 2 and top_support_share < 0.95
    if not signals_vary:
        reasons.append("supporting_signals_do_not_vary_materially_across_leads")

    block = diag.get("block")
    if block:
        reasons.append(str(block))
    explanation = diag.get("explanation") or {}
    catalog_degenerate = bool(explanation.get("catalog_degenerate"))
    if catalog_degenerate:
        reasons.append("catalog_degenerate")
    robust = bool(diag.get("robust_quantitative_justification"))
    if not robust:
        reasons.append("robust_quantitative_justification_false")

    excessive: list[str] = []
    for sig, rate in change_rates.items():
        if rate > max_change_rate:
            excessive.append(sig)
    if excessive:
        reasons.append("BLOCKED_OFFER_MAPPING_EXCESSIVELY_SENSITIVE")

    # Text justification must NEVER clear diagnose/degeneracy/robust failures
    ok = not reasons
    if ok:
        status = "PASS"
    elif "BLOCKED_OFFER_MAPPING_EXCESSIVELY_SENSITIVE" in reasons:
        status = "BLOCKED_OFFER_MAPPING_EXCESSIVELY_SENSITIVE"
    elif block:
        status = str(block)
    elif catalog_degenerate or not robust:
        status = "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE"
    else:
        status = "BLOCKED_OFFER_MAPPING_NOT_VALIDATED"

    return {
        "ok": ok,
        "status": status,
        "reasons": reasons,
        "diagnose_block": block,
        "catalog_degenerate": catalog_degenerate,
        "robust_quantitative_justification": robust,
        "multi_buckets_all": multi_buckets_all,
        "alternative_offer_all": alt_all,
        "margin_all_above_min": margin_all,
        "hardcoded_selection": hardcoded,
        "offer_scores_vary": score_varies,
        "supporting_signals_vary": signals_vary,
        "excessive_sensitivity_signals": excessive,
        "max_single_signal_change_rate_threshold": max_change_rate,
        "min_selected_offer_margin": min_margin,
        # Explicit: text justification does not override
        "individual_justification_override_forbidden": True,
    }


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
        as_of = date.today()
        ranked_all = _score_universe(conn, cnpjs, profile, as_of=as_of, rank_limit=None)
        baseline = ranked_all[:20]
        base_by_cnpj = {x.cnpj14: (x.selected_offer or x.suggested_offer) for x in baseline}
        base_offers = [base_by_cnpj[c] for c in base_by_cnpj]
        base_counts: dict[str, int] = dict(Counter(base_offers))
        baseline_cnpjs = list(base_by_cnpj.keys())

        per_lead = [_lead_dict(x) for x in baseline]

        ablations: dict[str, Any] = {}
        change_rates: dict[str, float] = {}
        for sig in ABLATION_SIGNALS:
            # Ablate offers for the SAME baseline CNPJs only (not re-ranked top-20)
            ablated = _score_universe(
                conn,
                baseline_cnpjs,
                profile,
                as_of=as_of,
                drop_signals={sig},
                rank_limit=None,
                require_engineering=False,
            )
            by_cnpj = {
                x.cnpj14: (x.selected_offer or x.suggested_offer) for x in ablated
            }
            present = set(by_cnpj.keys())
            changed = 0
            offers_for_baseline: list[str] = []
            for cnpj, base_off in base_by_cnpj.items():
                if cnpj not in present:
                    changed += 1
                    offers_for_baseline.append("DROPPED")
                    continue
                new_off = by_cnpj[cnpj]
                offers_for_baseline.append(
                    str(new_off) if new_off is not None else "none"
                )
                if (new_off or "none") != (base_off or "none"):
                    changed += 1
            rate = changed / max(len(base_by_cnpj), 1)
            change_rates[sig] = rate
            counts = dict(Counter(o for o in offers_for_baseline if o != "DROPPED"))
            ablations[sig] = {
                "offer_distribution": counts,
                "offers_for_baseline_cnpjs": offers_for_baseline,
                "selection_change_rate": rate,
                "comparison_mode": "same_baseline_cnpjs",
                "excessive": rate > MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE,
            }

        # Full lead dicts for diagnose (must include offer_scores / alternatives)
        diag = diagnose_offer_distribution(baseline)
        dominant = max(base_counts.values()) / max(len(base_offers), 1) if base_offers else 0
        margins = [
            float(x.selected_offer_margin)
            for x in baseline
            if x.selected_offer_margin is not None
        ]
        mean_margin = sum(margins) / len(margins) if margins else None

        decision = evaluate_offer_pass(
            baseline=baseline, diag=diag, change_rates=change_rates
        )

        # Matrices / distributions required by integrity goal
        signal_to_offer_weight_matrix = {
            sig: dict(weights) for sig, weights in _SIGNAL_OFFER_WEIGHTS.items()
        }
        offer_score_distribution: dict[str, list[float]] = {k: [] for k in OFFER_SCORE_KEYS}
        for x in baseline:
            scores = dict(x.offer_scores or {})
            for k in OFFER_SCORE_KEYS:
                offer_score_distribution[k].append(round(float(scores.get(k) or 0), 4))

        # Signal correlation via support co-occurrence among top-20
        all_sigs = sorted(
            {
                s
                for x in baseline
                for s in (x.supporting_signals or [])
                if isinstance(s, str) and not s.startswith("mapping:")
            }
        )
        signal_correlation_matrix: dict[str, dict[str, float | None]] = {}
        for a in all_sigs:
            signal_correlation_matrix[a] = {}
            xa = [
                1.0 if a in (x.supporting_signals or []) else 0.0 for x in baseline
            ]
            for b in all_sigs:
                xb = [
                    1.0 if b in (x.supporting_signals or []) else 0.0 for x in baseline
                ]
                signal_correlation_matrix[a][b] = _pearson(xa, xb)

        offer_margin_distribution = [round(m, 4) for m in margins]
        per_signal_ablation_results = {
            k: {
                "selection_change_rate": v["selection_change_rate"],
                "offer_distribution": v["offer_distribution"],
                "excessive": v["excessive"],
            }
            for k, v in ablations.items()
        }

        sens_ok = decision["ok"]
        report = {
            "ok": sens_ok,
            "status": decision["status"] if sens_ok else decision["status"],
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
            "pass_decision": decision,
            "signal_to_offer_weight_matrix": signal_to_offer_weight_matrix,
            "offer_score_distribution": offer_score_distribution,
            "signal_correlation_matrix": signal_correlation_matrix,
            "offer_margin_distribution": offer_margin_distribution,
            "per_signal_ablation_results": per_signal_ablation_results,
            "uniform_offer_justified_individually": False,  # no text override path
            "note": (
                "PASS requires cumulative quantitative criteria. "
                "individual_justification text never overrides diagnose.block / "
                "catalog_degenerate / robust_quantitative_justification. "
                "Ablation compared on same baseline CNPJs (not re-ranked zip)."
            ),
        }
        (ART / "offer-sensitivity-gate.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
        disc_ok = (
            decision["ok"]
            or decision["status"]
            not in (
                "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE",
                "BLOCKED_OFFER_MAPPING_NOT_VALIDATED",
            )
        ) and decision["diagnose_block"] is None and not decision["catalog_degenerate"]
        # Discrimination gate: same decision (no separate text loophole)
        disc = {
            "ok": decision["ok"],
            "status": (
                "PASS"
                if decision["ok"]
                else (
                    decision["status"]
                    if decision["status"] != "BLOCKED_OFFER_MAPPING_EXCESSIVELY_SENSITIVE"
                    else "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE"
                    if decision["diagnose_block"]
                    else decision["status"]
                )
            ),
            "dominant_offer_rate": dominant,
            "offer_entropy": _entropy(base_counts),
            "mean_selected_offer_margin": mean_margin,
            "offer_distribution": base_counts,
            "per_lead_n": len(per_lead),
            "uniform_but_justified": False,
            "diagnose": diag,
            "pass_decision": decision,
            "catalog_degenerate": decision["catalog_degenerate"],
            "robust_quantitative_justification": decision[
                "robust_quantitative_justification"
            ],
        }
        # If only sensitivity fails, discrimination can still PASS when diagnose clean
        if (
            not decision["ok"]
            and decision["status"] == "BLOCKED_OFFER_MAPPING_EXCESSIVELY_SENSITIVE"
            and decision["diagnose_block"] is None
            and not decision["catalog_degenerate"]
            and decision["robust_quantitative_justification"]
            and decision["multi_buckets_all"]
            and decision["alternative_offer_all"]
        ):
            disc["ok"] = True
            disc["status"] = "PASS"
            disc["note"] = "discrimination PASS; sensitivity separately BLOCKED"
        (ART / "offer-discrimination-gate.json").write_text(
            json.dumps(disc, indent=2, default=str) + "\n", encoding="utf-8"
        )
        # Overall: both must pass for commercial integrity
        report["discrimination_status"] = disc["status"]
        report["ok"] = decision["ok"] and disc["ok"]
        if report["ok"]:
            report["status"] = "PASS"
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
                    "dominant_offer_rate",
                    "offer_selection_change_rate",
                    "mean_selected_offer_margin",
                    "discrimination_status",
                )
            },
            indent=2,
            default=str,
        )
    )
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
