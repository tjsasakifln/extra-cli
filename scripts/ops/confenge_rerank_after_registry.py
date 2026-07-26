#!/usr/bin/env python3
"""Re-rank frozen candidate universe AFTER full registry enrichment.

Sequence (mandatory):
  frozen candidates → load all-status history → registry join → sector →
  signals → eligibility → rank → top20

Does not re-discover candidates; uses frozen CNPJ list from last run-result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.dbutil import connect  # noqa: E402
from scripts.commercial_leads.pipeline import (  # noqa: E402
    compute_supplier_history_metrics,
    load_full_supplier_histories,
    split_history_views,
)
from scripts.commercial_leads.profile import load_profile  # noqa: E402
from scripts.commercial_leads.scoring import (  # noqa: E402
    diagnose_offer_distribution,
    rank_leads,
    score_supplier,
)
from scripts.commercial_leads.sector_fit import (  # noqa: E402
    PUBLISHABLE,
    classify_supplier_sector_fit,
    sector_fit_histogram,
)
from scripts.commercial_leads.signals import (  # noqa: E402
    compute_signals_for_supplier,
    rows_from_dicts,
)
from scripts.commercial_leads.supplier_registry import (  # noqa: E402
    coverage_report,
    load_registry_map,
)

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN"))
    ap.add_argument(
        "--run-result",
        type=Path,
        default=ART / "run" / "run-result.json",
    )
    ap.add_argument("--out", type=Path, default=ART / "rerank-after-registry.json")
    ap.add_argument("--limit-universe", type=int, default=0, help="0 = all frozen candidates")
    args = ap.parse_args(argv)
    if not args.dsn:
        print(json.dumps({"ok": False, "reason": "DSN required"}))
        return 2

    run = json.loads(args.run_result.read_text(encoding="utf-8"))
    lm = run.get("load_meta") or {}
    universe = list(lm.get("candidate_supplier_cnpjs") or [])
    if args.limit_universe and args.limit_universe > 0:
        universe = universe[: args.limit_universe]
    if len(universe) < 20:
        print(json.dumps({"ok": False, "reason": "universe_too_small", "n": len(universe)}))
        return 1

    # Resolution statuses from ingest
    res_path = ART / "registry-resolution-status.json"
    resolution_status = {}
    if res_path.is_file():
        resolution_status = (json.loads(res_path.read_text()).get("statuses") or {})

    profile = load_profile(_ROOT / "config/commercial_profiles/confenge.yaml")
    as_of = date.fromisoformat(str(run.get("as_of") or date.today().isoformat()))
    names = {str(L.get("cnpj14")): L.get("razao_social") for L in (run.get("leads") or [])}

    conn = connect(args.dsn)
    try:
        groups, hist = load_full_supplier_histories(conn, universe, per_supplier_limit=None)
        reg_map = load_registry_map(conn, universe)
    finally:
        conn.close()

    if not hist.get("all_statuses_loaded"):
        print(json.dumps({"ok": False, "reason": "history_not_all_status", "hist": hist}, default=str))
        return 1

    reg_cov = coverage_report(
        reg_map,
        all_candidates=universe,
        top100=universe[:100],
        top20=[],  # filled after ranking
        resolution_status=resolution_status,
    )
    if reg_cov.get("selection_bias_risk") or (reg_cov.get("registry_coverage_all_candidates") or {}).get(
        "coverage"
    ) != 1.0:
        # allow definitive resolution path
        if (reg_cov.get("registry_resolved_or_definitively_not_found") or 0) < 1.0:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "reason": "BLOCKED_REGISTRY_SELECTION_BIAS",
                        "registry_coverage": reg_cov,
                    },
                    indent=2,
                    default=str,
                )
            )
            return 2

    sector_decisions = []
    scored = []
    extras: dict[str, dict[str, Any]] = {}
    for cnpj in universe:
        crow = groups.get(cnpj) or []
        if not crow:
            continue
        reg = reg_map.get(cnpj)
        hist_m = compute_supplier_history_metrics(crow)
        _all, active = split_history_views(crow)
        sector = classify_supplier_sector_fit(
            razao_social=names.get(cnpj) or crow[0].get("fornecedor_nome"),
            contracts=crow,
            cnae_principal=reg.cnae_principal if reg else None,
            cnaes_secundarios=list(reg.cnaes_secundarios) if reg else [],
            history_is_full=True,
        )
        sector_decisions.append(sector)
        if sector.classification not in PUBLISHABLE:
            continue
        signal_rows = rows_from_dicts(active) if active else rows_from_dicts(crow)
        sigs = compute_signals_for_supplier(signal_rows, profile, as_of=as_of, official_acts=None)
        contracts = rows_from_dicts(crow)
        total_value = sum(float(c.valor_total or 0) for c in contracts if c.valor_total is not None)
        pubs = [c.data_publicacao for c in contracts if c.data_publicacao]
        lead = score_supplier(
            cnpj14=cnpj,
            razao_social=names.get(cnpj) or crow[0].get("fornecedor_nome") or cnpj,
            signal_results=sigs,
            profile=profile,
            total_value=total_value,
            contract_count=len(contracts),
            last_publication=max(pubs).isoformat() if pubs else None,
        )
        scored.append(lead)
        extras[cnpj] = {
            "supplier_sector_fit": sector.classification,
            "supplier_sector_confidence": sector.confidence,
            "activity_class": sector.activity_class,
            "cnae_principal": reg.cnae_principal if reg else None,
            "history_metrics": hist_m,
            "data_quality": {
                "history_view": "ALL_SNAPSHOT_SUPPLIER_HISTORY",
                **hist_m,
            },
        }

    ranked = rank_leads(scored, profile, suppressed_cnpjs=set(), state_by_cnpj={})
    leads: list[dict[str, Any]] = []
    for i, lead in enumerate(ranked, start=1):
        d = lead.as_dict()
        d["rank_position"] = i
        d.update(extras.get(lead.cnpj14, {}))
        leads.append(d)

    top20 = [L["cnpj14"] for L in leads[:20]]
    reg_cov = coverage_report(
        reg_map,
        all_candidates=universe,
        top100=[m.cnpj14 for m in scored[:100]] if scored else universe[:100],
        top20=top20,
        resolution_status=resolution_status,
    )
    offer_diag = diagnose_offer_distribution(leads[:20] if leads else leads)
    sector_dist = sector_fit_histogram(sector_decisions)

    ranking_hash = hashlib.sha256(
        json.dumps(
            [(L["cnpj14"], L["score_total"], L.get("supplier_sector_fit"), L.get("selected_offer")) for L in leads[:20]],
            sort_keys=True,
        ).encode()
    ).hexdigest()

    # Compare to previous published top20
    prev = [str(L.get("cnpj14")) for L in (run.get("leads") or [])[:20]]
    # CNPJs in top20 now that were not in previous top20
    introduced = [c for c in top20 if c not in set(prev)]

    report = {
        "ok": (
            reg_cov.get("selection_bias_risk") is False
            and (reg_cov.get("registry_coverage_all_candidates") or {}).get("coverage") == 1.0
            and hist.get("all_statuses_loaded") is True
        ),
        "method": "rerank_after_full_universe_registry_enrichment",
        "sequence": [
            "frozen_candidate_universe",
            "all_status_history",
            "registry_join_100pct",
            "sector_classification",
            "signals",
            "eligibility",
            "ranking",
            "top20",
        ],
        "candidate_universe_n": len(universe),
        "candidate_universe_hash": hashlib.sha256(json.dumps(sorted(universe)).encode()).hexdigest(),
        "history_view": hist.get("history_view"),
        "all_statuses_loaded": hist.get("all_statuses_loaded"),
        "registry_coverage": reg_cov,
        "sector_fit_distribution": sector_dist,
        "eligible_n": len(scored),
        "ranked_n": len(leads),
        "top20": leads[:20],
        "top20_order": top20,
        "previous_top20_order": prev,
        "introduced_in_top20_after_full_registry": introduced,
        "ranking_hash": ranking_hash,
        "offer_mapping_diagnostic": offer_diag,
        "selection_bias_risk": reg_cov.get("selection_bias_risk"),
        "block_reason": reg_cov.get("block_reason"),
        "note": (
            "Ranking executed only after full candidate universe registry enrichment. "
            "Amplifying coverage from ~2% to 100% can introduce firms previously invisible."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({k: report[k] for k in report if k != "top20"}, indent=2, default=str))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
