#!/usr/bin/env python3
"""Full-universe end-to-end reproducibility for CONFENGE.

Runs the commercial pipeline stages TWICE over the frozen full candidate
universe (n == frozen_candidate_count). Subset runs must be labeled
SAMPLED_E2E_TEST and never claim full-population PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.dbutil import connect, fetch_all  # noqa: E402
from scripts.commercial_leads.pipeline import load_full_supplier_histories  # noqa: E402
from scripts.commercial_leads.profile import load_profile  # noqa: E402
from scripts.commercial_leads.scoring import rank_leads, score_supplier  # noqa: E402
from scripts.commercial_leads.sector_fit import classify_supplier_sector_fit  # noqa: E402
from scripts.commercial_leads.signals import (  # noqa: E402
    compute_signals_for_supplier,
    rows_from_dicts,
)
from scripts.commercial_leads.supplier_registry import load_registry_map  # noqa: E402

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
PROFILE = _ROOT / "config/commercial_profiles/confenge.yaml"
DEFAULT_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/confenge_commercial"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _h(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def frozen_candidates(conn: Any, run_result: Path | None) -> list[str]:
    if run_result and run_result.is_file():
        d = json.loads(run_result.read_text(encoding="utf-8"))
        lm = d.get("load_meta") or {}
        cnpjs = [str(c) for c in (lm.get("candidate_supplier_cnpjs") or []) if c]
        if cnpjs:
            return sorted(set(cnpjs))
        leads = d.get("leads") or []
        if leads:
            return sorted({str(L["cnpj14"]) for L in leads if L.get("cnpj14")})
    rows = fetch_all(
        conn,
        """
        SELECT DISTINCT right(regexp_replace(fornecedor_cnpj, '\\D', '', 'g'), 14) AS c
        FROM public.pncp_supplier_contracts
        WHERE length(regexp_replace(coalesce(fornecedor_cnpj,''), '\\D', '', 'g')) >= 14
        ORDER BY 1
        """,
    )
    return [r["c"] for r in rows]


def one_pass(
    conn: Any,
    cnpjs: list[str],
    profile: Any,
    *,
    as_of: date,
    names: dict[str, str],
) -> dict[str, Any]:
    groups, hist = load_full_supplier_histories(conn, cnpjs, per_supplier_limit=None)
    try:
        reg = load_registry_map(conn, cnpjs)
    except Exception:
        reg = {}

    if not hist.get("all_statuses_loaded"):
        return {"ok": False, "reason": "all_statuses_not_loaded", "hist": hist}

    scored = []
    sector_decisions: list[dict[str, Any]] = []
    sector_dist: dict[str, int] = {}
    signal_blob: list[dict[str, Any]] = []
    offer_scores_blob: list[dict[str, Any]] = []
    active_counts: dict[str, int] = {}
    hist_ids: list[dict[str, Any]] = []

    for cnpj in cnpjs:
        crow = groups.get(cnpj) or []
        active_counts[cnpj] = sum(1 for r in crow if r.get("is_active") is True)
        hist_ids.append(
            {
                "c": cnpj,
                "n": len(crow),
                "ids": sorted(str(r.get("contrato_id") or "") for r in crow)[:30],
            }
        )
        if not crow:
            sector_decisions.append({"cnpj14": cnpj, "class": "OUT_OF_SCOPE"})
            sector_dist["OUT_OF_SCOPE"] = sector_dist.get("OUT_OF_SCOPE", 0) + 1
            continue
        rec = reg.get(cnpj) if isinstance(reg, dict) else None
        sector = classify_supplier_sector_fit(
            razao_social=names.get(cnpj) or crow[0].get("fornecedor_nome"),
            contracts=crow,
            cnae_principal=rec.cnae_principal if rec else None,
            cnaes_secundarios=list(rec.cnaes_secundarios) if rec else [],
            history_is_full=True,
        )
        klass = sector.classification
        sector_decisions.append({"cnpj14": cnpj, "class": klass})
        sector_dist[klass] = sector_dist.get(klass, 0) + 1

        # Commercial signals use ACTIVE portfolio when available
        active_rows = [r for r in crow if r.get("is_active") is True]
        contracts = rows_from_dicts(active_rows or crow)
        sigs = compute_signals_for_supplier(contracts, profile, as_of=as_of, official_acts=None)
        signal_blob.append(
            {
                "cnpj14": cnpj,
                "fired": sorted(s.signal_id for s in sigs if s.status == "FIRED"),
                "n": len(sigs),
            }
        )

        if klass not in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT"):
            continue
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
        lead._sector = klass  # type: ignore[attr-defined]
        scored.append(lead)
        offer_scores_blob.append(
            {
                "cnpj14": cnpj,
                "selected_offer": lead.selected_offer or lead.suggested_offer,
                "offer_scores": dict(lead.offer_scores or {}),
                "margin": lead.selected_offer_margin,
                "score_total": round(float(lead.score_total), 6),
            }
        )

    ranked = rank_leads(scored, profile, suppressed_cnpjs=set(), state_by_cnpj={})
    top20 = [
        {
            "cnpj14": x.cnpj14,
            "score_total": round(x.score_total, 6),
            "sector": getattr(x, "_sector", None),
            "offer": x.selected_offer or x.suggested_offer,
        }
        for x in ranked[:20]
    ]
    top20_order = [x["cnpj14"] for x in top20]
    review_queue = sorted(
        d["cnpj14"]
        for d in sector_decisions
        if d["class"] not in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT")
    )

    return {
        "ok": True,
        "n_universe": len(cnpjs),
        "candidate_universe_hash": _h(sorted(cnpjs)),
        "contract_history_hash": _h(hist_ids),
        "full_history_hash": _h(
            {
                "n_groups": len(groups),
                "n_contracts": sum(len(v) for v in groups.values()),
                "mode": hist.get("history_expansion_mode"),
                "view": hist.get("history_view"),
            }
        ),
        "active_portfolio_hash": _h(active_counts),
        "registry_snapshot_hash": _h(sorted((reg or {}).keys()) if isinstance(reg, dict) else []),
        "registry_join_hash": _h(
            sorted((c, bool(isinstance(reg, dict) and c in reg)) for c in cnpjs)
        ),
        "sector_decision_hash": _h(sector_decisions),
        "eligible_universe_hash": _h([x.cnpj14 for x in scored]),
        "signal_results_hash": _h(signal_blob),
        "offer_scores_hash": _h(offer_scores_blob),
        "ranking_hash": _h(top20),
        "top20_order": top20_order,
        "review_queue_hash": _h(review_queue),
        "history_view": hist.get("history_view"),
        "all_statuses_loaded": hist.get("all_statuses_loaded"),
        "n_eligible": len(scored),
        "sector_classification_distribution": sector_dist,
        "offer_mapping": [x["offer"] for x in top20],
        "offer_detail_top20": [
            {
                "cnpj14": x.cnpj14,
                "selected_offer": x.selected_offer or x.suggested_offer,
                "alternative_offer": x.alternative_offer,
                "selected_offer_margin": x.selected_offer_margin,
                "offer_scores": dict(x.offer_scores or {}),
                "supporting_signals": list(x.supporting_signals or []),
                "contradicting_signals": list(x.contradicting_signals or []),
            }
            for x in ranked[:20]
        ],
    }


def run_full_universe_e2e(
    *,
    dsn: str,
    run_result: Path | None = None,
    sample_limit: int = 0,
) -> dict[str, Any]:
    profile = load_profile(PROFILE)
    names: dict[str, str] = {}
    if run_result and run_result.is_file():
        d = json.loads(run_result.read_text(encoding="utf-8"))
        names = {
            str(L.get("cnpj14")): str(L.get("razao_social") or "")
            for L in (d.get("leads") or [])
            if L.get("cnpj14")
        }
        as_of_raw = d.get("as_of")
    else:
        as_of_raw = None
    as_of = date.fromisoformat(str(as_of_raw)[:10]) if as_of_raw else date.today()

    conn = connect(dsn)
    try:
        cnpjs = frozen_candidates(conn, run_result)
        frozen_n = len(cnpjs)
        sampled = False
        if sample_limit and sample_limit > 0 and sample_limit < frozen_n:
            cnpjs = cnpjs[:sample_limit]
            sampled = True

        pass_a = one_pass(conn, cnpjs, profile, as_of=as_of, names=names)
        pass_b = one_pass(conn, cnpjs, profile, as_of=as_of, names=names)

        hash_keys = [
            "candidate_universe_hash",
            "contract_history_hash",
            "active_portfolio_hash",
            "registry_snapshot_hash",
            "registry_join_hash",
            "sector_decision_hash",
            "eligible_universe_hash",
            "signal_results_hash",
            "offer_scores_hash",
            "ranking_hash",
            "top20_order",
            "review_queue_hash",
        ]
        equal = {k: pass_a.get(k) == pass_b.get(k) for k in hash_keys}
        all_equal = all(equal.values()) and bool(pass_a.get("ok") and pass_b.get("ok"))
        n_match = pass_a.get("n_universe") == frozen_n and not sampled

        if sampled:
            status = "SAMPLED_E2E_TEST"
            ok = False
        elif all_equal and n_match:
            status = "PASS"
            ok = True
        else:
            status = "BLOCKED_FULL_UNIVERSE_E2E_NOT_PROVEN"
            ok = False

        report = {
            "ok": ok,
            "status": status,
            "method": "live_double_full_pipeline_frozen_universe_all_status_history",
            "frozen_candidate_count": frozen_n,
            "n_universe": pass_a.get("n_universe"),
            "n_universe_equals_frozen": n_match,
            "sampled": sampled,
            "pass_a": pass_a,
            "pass_b": pass_b,
            "hash_equality": equal,
            "all_hashes_equal": all_equal,
            "top20_equal": pass_a.get("top20_order") == pass_b.get("top20_order"),
            "review_queue_equal": pass_a.get("review_queue_hash")
            == pass_b.get("review_queue_hash"),
            "same_inputs_same_complete_outputs": all_equal,
            "executed_at": utc_now(),
            "note": (
                "Full-universe PASS requires n_universe == frozen_candidate_count and "
                "identical stage hashes across two independent passes. "
                "Sampled runs are SAMPLED_E2E_TEST only."
            ),
        }
        out = ART / "full-universe-e2e-reproducibility-gate.json"
        out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        if not sampled:
            (ART / "end-to-end-reproducibility-gate.json").write_text(
                json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
            )
        return report
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN", DEFAULT_DSN))
    ap.add_argument("--run-result", type=Path, default=ART / "run" / "run-result.json")
    ap.add_argument("--sample-limit", type=int, default=0)
    args = ap.parse_args(argv)
    rep = run_full_universe_e2e(
        dsn=args.dsn, run_result=args.run_result, sample_limit=args.sample_limit
    )
    print(
        json.dumps(
            {
                k: rep.get(k)
                for k in (
                    "ok",
                    "status",
                    "frozen_candidate_count",
                    "n_universe",
                    "n_universe_equals_frozen",
                    "all_hashes_equal",
                    "top20_equal",
                    "sampled",
                )
            },
            indent=2,
        )
    )
    if rep.get("status") == "SAMPLED_E2E_TEST":
        return 2
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
