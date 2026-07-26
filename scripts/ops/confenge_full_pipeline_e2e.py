#!/usr/bin/env python3
"""FULL_PIPELINE_E2E_REPRODUCIBILITY — starts from raw snapshot contracts.

Two independent passes re-run:
  raw snapshot → discovery → prefilter → identity → universe → history →
  registry join → sector → signals → eligibility → offers → ranking → top20 →
  review queue

This is NOT the downstream gate (which may start from a frozen CNPJ list).
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

from scripts.commercial_leads.dbutil import connect  # noqa: E402
from scripts.commercial_leads.pipeline import (  # noqa: E402
    POPULATION_FULL,
    discover_candidate_suppliers,
    group_by_supplier,
    load_full_supplier_histories,
)
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

STAGE_HASH_KEYS = (
    "discovery_input_hash",
    "discovery_output_hash",
    "candidate_universe_hash",
    "identity_resolution_hash",
    "contract_history_hash",
    "registry_join_hash",
    "sector_decision_hash",
    "eligible_universe_hash",
    "signal_results_hash",
    "offer_scores_hash",
    "ranking_hash",
    "top20_order",
    "review_queue_hash",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _h(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def discovery_input_fingerprint(conn: Any) -> dict[str, Any]:
    """Fingerprint of raw snapshot input used for discovery (not a frozen CNPJ list)."""
    from scripts.commercial_leads.dbutil import fetch_all

    row = fetch_all(
        conn,
        """
        SELECT
          count(*)::bigint AS n_contracts,
          count(DISTINCT right(regexp_replace(coalesce(fornecedor_cnpj,''), '\\D', '', 'g'), 14))
            AS n_suppliers,
          min(data_publicacao)::text AS min_pub,
          max(data_publicacao)::text AS max_pub,
          md5(string_agg(contrato_id::text, ',' ORDER BY contrato_id)) AS contracts_md5
        FROM public.pncp_supplier_contracts
        WHERE length(regexp_replace(coalesce(fornecedor_cnpj,''), '\\D', '', 'g')) >= 14
        """,
    )
    r = row[0] if row else {}
    return {
        "source": "public.pncp_supplier_contracts",
        "n_contracts": int(r.get("n_contracts") or 0),
        "n_suppliers": int(r.get("n_suppliers") or 0),
        "min_pub": r.get("min_pub"),
        "max_pub": r.get("max_pub"),
        "contracts_md5": r.get("contracts_md5"),
    }


def one_full_pipeline_pass(
    conn: Any,
    profile: Any,
    *,
    as_of: date,
) -> dict[str, Any]:
    """Single end-to-end pass starting at raw snapshot discovery."""
    disc_input = discovery_input_fingerprint(conn)
    discovery_input_hash = _h(disc_input)

    evidence_by_cnpj, discovery_meta = discover_candidate_suppliers(
        conn, profile, population_mode=POPULATION_FULL
    )
    discovery_output = {
        "discovery_mode": discovery_meta.get("discovery_mode"),
        "candidate_supplier_count": discovery_meta.get("candidate_supplier_count"),
        "sql_prefilter_rows": discovery_meta.get("sql_prefilter_rows"),
        "relevance_pass_rows": discovery_meta.get("relevance_pass_rows"),
        "candidate_supplier_cnpjs": sorted(
            discovery_meta.get("candidate_supplier_cnpjs")
            or list(evidence_by_cnpj.keys())
        ),
    }
    discovery_output_hash = _h(discovery_output)

    # Identity normalization via group_by_supplier on discovery evidence
    discovery_flat: list[dict[str, Any]] = []
    for rows in evidence_by_cnpj.values():
        discovery_flat.extend(rows)
    disc_groups, exclusions, names_discovery = group_by_supplier(discovery_flat, profile)
    identity_blob = {
        "n_groups": len(disc_groups),
        "n_exclusions": len(exclusions) if isinstance(exclusions, (list, dict)) else 0,
        "cnpjs": sorted(disc_groups.keys()),
        "names_sample": sorted(
            (c, names_discovery.get(c) or "") for c in sorted(disc_groups.keys())[:50]
        ),
    }
    identity_resolution_hash = _h(identity_blob)

    candidate_cnpjs = sorted(
        set(disc_groups.keys()) | set(evidence_by_cnpj.keys())
    )
    candidate_universe_hash = _h(candidate_cnpjs)

    groups, hist = load_full_supplier_histories(
        conn, candidate_cnpjs, per_supplier_limit=None
    )
    if not hist.get("all_statuses_loaded"):
        return {
            "ok": False,
            "reason": "all_statuses_not_loaded",
            "discovery_input_hash": discovery_input_hash,
            "discovery_output_hash": discovery_output_hash,
        }

    hist_ids = [
        {
            "c": cnpj,
            "n": len(groups.get(cnpj) or []),
            "ids": sorted(
                str(r.get("contrato_id") or "") for r in (groups.get(cnpj) or [])
            )[:30],
        }
        for cnpj in candidate_cnpjs
    ]
    contract_history_hash = _h(hist_ids)

    try:
        reg = load_registry_map(conn, candidate_cnpjs)
    except Exception:
        reg = {}
    registry_join_hash = _h(
        sorted((c, bool(isinstance(reg, dict) and c in reg)) for c in candidate_cnpjs)
    )

    scored = []
    sector_decisions: list[dict[str, Any]] = []
    signal_blob: list[dict[str, Any]] = []
    offer_scores_blob: list[dict[str, Any]] = []
    names = dict(names_discovery)

    for cnpj in candidate_cnpjs:
        crow = groups.get(cnpj) or []
        if not crow:
            sector_decisions.append({"cnpj14": cnpj, "class": "OUT_OF_SCOPE"})
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

        active_rows = [r for r in crow if r.get("is_active") is True]
        contracts = rows_from_dicts(active_rows or crow)
        sigs = compute_signals_for_supplier(
            contracts, profile, as_of=as_of, official_acts=None
        )
        signal_blob.append(
            {
                "cnpj14": cnpj,
                "fired": sorted(s.signal_id for s in sigs if s.status == "FIRED"),
                "n": len(sigs),
            }
        )

        if klass not in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT"):
            continue
        total_value = sum(
            float(c.valor_total or 0) for c in contracts if c.valor_total is not None
        )
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
        "starts_from": "raw_snapshot_discovery",
        "gate_kind": "FULL_PIPELINE_E2E_REPRODUCIBILITY",
        "discovery_input": disc_input,
        "discovery_input_hash": discovery_input_hash,
        "discovery_output_hash": discovery_output_hash,
        "discovery_mode": discovery_meta.get("discovery_mode"),
        "candidate_universe_hash": candidate_universe_hash,
        "identity_resolution_hash": identity_resolution_hash,
        "contract_history_hash": contract_history_hash,
        "registry_join_hash": registry_join_hash,
        "sector_decision_hash": _h(sector_decisions),
        "eligible_universe_hash": _h([x.cnpj14 for x in scored]),
        "signal_results_hash": _h(signal_blob),
        "offer_scores_hash": _h(offer_scores_blob),
        "ranking_hash": _h(top20),
        "top20_order": top20_order,
        "review_queue_hash": _h(review_queue),
        "n_discovery_candidates": len(candidate_cnpjs),
        "n_eligible": len(scored),
        "n_review_queue": len(review_queue),
        "history_view": hist.get("history_view"),
        "all_statuses_loaded": hist.get("all_statuses_loaded"),
        "offer_mapping_top20": [x["offer"] for x in top20],
    }


def run_full_pipeline_e2e(*, dsn: str) -> dict[str, Any]:
    profile = load_profile(PROFILE)
    as_of = date.today()
    conn = connect(dsn)
    try:
        pass_a = one_full_pipeline_pass(conn, profile, as_of=as_of)
        pass_b = one_full_pipeline_pass(conn, profile, as_of=as_of)

        equal = {
            k: pass_a.get(k) == pass_b.get(k)
            for k in STAGE_HASH_KEYS
            if pass_a.get("ok") and pass_b.get("ok")
        }
        all_equal = (
            bool(pass_a.get("ok") and pass_b.get("ok"))
            and bool(equal)
            and all(equal.values())
        )
        # Must not start from frozen CNPJ list
        starts_ok = (
            pass_a.get("starts_from") == "raw_snapshot_discovery"
            and pass_b.get("starts_from") == "raw_snapshot_discovery"
        )
        ok = all_equal and starts_ok and int(pass_a.get("n_discovery_candidates") or 0) > 0
        status = "PASS" if ok else "BLOCKED_FULL_PIPELINE_E2E_NOT_PROVEN"
        report = {
            "ok": ok,
            "status": status,
            "gate_kind": "FULL_PIPELINE_E2E_REPRODUCIBILITY",
            "method": "live_double_full_pipeline_from_raw_snapshot_discovery",
            "starts_from_frozen_cnpj_list": False,
            "pass_a": pass_a,
            "pass_b": pass_b,
            "hash_equality": equal,
            "all_hashes_equal": all_equal,
            "top20_equal": pass_a.get("top20_order") == pass_b.get("top20_order"),
            "review_queue_equal": pass_a.get("review_queue_hash")
            == pass_b.get("review_queue_hash"),
            "same_frozen_raw_inputs_same_complete_outputs": all_equal,
            "executed_at": utc_now(),
            "note": (
                "Full-pipeline E2E re-executes discovery from pncp_supplier_contracts. "
                "Downstream reproducibility (frozen universe) is a separate gate."
            ),
        }
        out = ART / "full-pipeline-e2e-reproducibility-gate.json"
        out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        return report
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN", DEFAULT_DSN)
    )
    args = ap.parse_args(argv)
    rep = run_full_pipeline_e2e(dsn=args.dsn)
    print(
        json.dumps(
            {
                k: rep.get(k)
                for k in (
                    "ok",
                    "status",
                    "gate_kind",
                    "all_hashes_equal",
                    "top20_equal",
                    "starts_from_frozen_cnpj_list",
                )
            },
            indent=2,
        )
    )
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
