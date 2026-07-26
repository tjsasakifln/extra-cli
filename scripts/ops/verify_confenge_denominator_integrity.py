#!/usr/bin/env python3
"""Prove sector concentration uses full supplier history, not prefilter-only.

Usage:
  make verify-confenge-denominator-integrity
  # unit path (no DB): always runs adversarial synthetic cases
  # DB path: set CONFENGE_COMMERCIAL_STATE_DSN + optional run artifacts
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.sector_fit import (  # noqa: E402
    CLASS_CONFIRMED,
    CLASS_STRONG,
    assert_denominator_invariant,
    classify_supplier_sector_fit,
)


def _c(obj: str, orgao: str = "o1", day: int = 0) -> dict[str, Any]:
    return {
        "objeto_contrato": obj,
        "orgao_cnpj": orgao,
        "data_publicacao": (date(2024, 1, 1) + timedelta(days=day)).isoformat(),
        "uf": "SC",
    }


def adversarial_cases() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    # Case 1: 1 pavement + 9 food → ratio 0.10, never STRONG
    contracts = [_c("pavimentação asfáltica de vias urbanas", "a", 0)]
    for i in range(9):
        contracts.append(_c("aquisição de refeições e alimentação escolar", f"f{i}", i + 1))
    d = classify_supplier_sector_fit(razao_social="MISTA ALIMENTOS LTDA", contracts=contracts)
    assert_denominator_invariant(d)
    ok = (
        d.total_contract_count_full_history == 10
        and d.relevant_contract_count == 1
        and abs(d.relevant_contract_ratio_full_history - 0.10) < 1e-9
        and d.classification not in (CLASS_STRONG, CLASS_CONFIRMED)
    )
    results.append(
        {
            "case": "1_pavement_9_food",
            "ok": ok,
            "ratio": d.relevant_contract_ratio_full_history,
            "classification": d.classification,
            "relevant": d.relevant_contract_count,
            "total": d.total_contract_count_full_history,
        }
    )

    # Case 2: 2 obra + 8 limpeza → never STRONG without CNAE
    contracts2 = [
        _c("execução de obra de engenharia civil", "a", 0),
        _c("construção de escola municipal em alvenaria", "b", 200),
    ]
    for i in range(8):
        contracts2.append(_c("serviço de limpeza e conservação predial", f"l{i}", i + 1))
    d2 = classify_supplier_sector_fit(razao_social="BETA SERVICOS GERAIS LTDA", contracts=contracts2)
    assert_denominator_invariant(d2)
    ok2 = (
        d2.relevant_contract_count == 2
        and d2.total_contract_count_full_history == 10
        and d2.classification not in (CLASS_STRONG, CLASS_CONFIRMED)
    )
    results.append(
        {
            "case": "2_obra_8_limpeza",
            "ok": ok2,
            "ratio": d2.relevant_contract_ratio_full_history,
            "classification": d2.classification,
        }
    )

    # Case 3: prefilter-only simulation — if only relevant loaded, ratio is contaminated
    # Gold architecture must NOT classify STRONG on that incomplete set without history_is_full
    only_relevant = [_c("pavimentação asfáltica de vias urbanas")]
    d_bad = classify_supplier_sector_fit(
        razao_social="CONTAMINATED LTDA",
        contracts=only_relevant,
        history_is_full=False,
    )
    ok3 = d_bad.classification not in (CLASS_STRONG, CLASS_CONFIRMED)
    results.append(
        {
            "case": "prefilter_only_incomplete_never_strong",
            "ok": ok3,
            "classification": d_bad.classification,
            "history_source": d_bad.history_source,
        }
    )

    # Case 4: full strong history still works
    strong_rows = [
        _c("execução de obras e serviços de engenharia para estradas", "org-a", 0),
        _c("pavimentação asfáltica de vias urbanas", "org-b", 200),
        _c("terraplenagem e drenagem urbana", "org-a", 400),
        _c("construção de escola municipal em alvenaria", "org-b", 500),
    ]
    d4 = classify_supplier_sector_fit(
        razao_social="CONSTRUTORA REAL LTDA",
        contracts=strong_rows,
        history_is_full=True,
    )
    ok4 = d4.classification in (CLASS_STRONG, CLASS_CONFIRMED) and d4.relevant_contract_ratio_full_history >= 0.7
    results.append(
        {
            "case": "legitimate_strong_full_history",
            "ok": ok4,
            "classification": d4.classification,
            "ratio": d4.relevant_contract_ratio_full_history,
        }
    )

    return results


def verify_db_sample(dsn: str, sample_n: int = 20) -> dict[str, Any]:
    """Stratified sample: reconcile loaded full history vs COUNT(*) on snapshot."""
    from scripts.commercial_leads.dbutil import connect
    from scripts.commercial_leads.pipeline import (
        discover_candidate_suppliers,
        load_full_supplier_histories,
    )
    from scripts.commercial_leads.profile import load_profile

    profile = load_profile(_ROOT / "config/commercial_profiles/confenge.yaml")
    conn = connect(dsn)
    try:
        evidence, disc_meta = discover_candidate_suppliers(
            conn, profile, max_contracts=50_000, population_mode="BOUNDED_SAMPLE"
        )
        cnpjs = sorted(evidence.keys())[: max(sample_n * 3, sample_n)]
        # stratify by discovery evidence size
        cnpjs = cnpjs[:sample_n]
        groups, hist_meta = load_full_supplier_histories(conn, cnpjs, per_supplier_limit=None)

        mismatches = []
        prefilter_only_inflation = []
        for cnpj in cnpjs:
            full = groups.get(cnpj, [])
            disc = evidence.get(cnpj, [])
            # classifier must receive full, not discovery-only
            from scripts.commercial_leads.sector_fit import classify_supplier_sector_fit

            d_full = classify_supplier_sector_fit(
                razao_social=full[0].get("fornecedor_nome") if full else cnpj,
                contracts=full,
                history_is_full=True,
            )
            d_pre = classify_supplier_sector_fit(
                razao_social=cnpj,
                contracts=disc,
                history_is_full=False,
            )
            if d_pre.relevant_contract_ratio_full_history > d_full.relevant_contract_ratio_full_history + 1e-9:
                if d_pre.classification in (CLASS_STRONG, CLASS_CONFIRMED) and d_full.classification not in (
                    CLASS_STRONG,
                    CLASS_CONFIRMED,
                ):
                    prefilter_only_inflation.append(
                        {
                            "cnpj14": cnpj,
                            "prefilter_ratio": d_pre.relevant_contract_ratio_full_history,
                            "full_ratio": d_full.relevant_contract_ratio_full_history,
                            "prefilter_class": d_pre.classification,
                            "full_class": d_full.classification,
                        }
                    )
            assert_denominator_invariant(d_full)

        return {
            "ok": hist_meta.get("history_complete", False)
            and hist_meta.get("snapshot_count_mismatch_n", 0) == 0
            and len(prefilter_only_inflation) == 0,
            "sample_n": len(cnpjs),
            "history_meta": hist_meta,
            "discovery_candidates": disc_meta.get("candidate_supplier_count"),
            "prefilter_inflation_caught": prefilter_only_inflation[:20],
            "mismatches": hist_meta.get("snapshot_count_mismatches") or mismatches,
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/denominator-integrity.json")
    p.add_argument("--dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN") or "")
    p.add_argument("--sample-n", type=int, default=20)
    args = p.parse_args(argv)

    report: dict[str, Any] = {
        "gate": "verify-confenge-denominator-integrity",
        "adversarial": adversarial_cases(),
    }
    adv_ok = all(c["ok"] for c in report["adversarial"])
    report["adversarial_ok"] = adv_ok

    if args.dsn:
        try:
            report["db_sample"] = verify_db_sample(args.dsn, sample_n=args.sample_n)
            report["db_ok"] = bool(report["db_sample"].get("ok"))
        except Exception as exc:  # noqa: BLE001
            report["db_sample"] = {"ok": False, "error": str(exc)}
            report["db_ok"] = False
    else:
        report["db_sample"] = {"ok": None, "skipped": True, "reason": "no DSN"}
        report["db_ok"] = None  # synthetic path sufficient for unit gate

    report["ok"] = bool(adv_ok) and (report["db_ok"] is not False if args.dsn else adv_ok)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "adversarial_ok": adv_ok, "db_ok": report.get("db_ok")}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
