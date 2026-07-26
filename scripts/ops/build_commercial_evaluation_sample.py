#!/usr/bin/env python3
"""Build dual-review evaluation sample with >=200 REAL suppliers from last run.

Does NOT auto-fill human labels. Populates model fields + empty reviewer slots.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _row(item: dict[str, Any], stratum: str) -> dict[str, Any]:
    dq = item.get("data_quality") or {}
    sector = item.get("supplier_sector_evidence") or item.get("supplier_sector_fit") or {}
    if isinstance(sector, dict):
        model_cls = sector.get("classification") or item.get("supplier_sector_fit")
        cnae = sector.get("cnae_principal") or dq.get("cnae_principal")
        rel = sector.get("relevant_contract_count") or dq.get("relevant_contract_count")
        tot = sector.get("total_contract_count_full_history") or dq.get(
            "total_contract_count_full_history"
        )
        ratio = sector.get("relevant_contract_ratio_full_history") or dq.get(
            "relevant_contract_ratio_full_history"
        )
    else:
        model_cls = item.get("supplier_sector_fit")
        cnae = dq.get("cnae_principal") or item.get("cnae_principal")
        rel = item.get("relevant_contract_count") or dq.get("relevant_contract_count")
        tot = item.get("total_contract_count_full_history") or dq.get(
            "total_contract_count_full_history"
        )
        ratio = item.get("relevant_contract_ratio_full_history") or dq.get(
            "relevant_contract_ratio_full_history"
        )
    return {
        "stratum": stratum,
        "cnpj14": item.get("cnpj14"),
        "razao_social": item.get("razao_social"),
        "cnae_principal": cnae,
        "cnaes_secundarios": [],
        "situacao_cadastral": None,
        "relevant_contract_count": rel,
        "total_contract_count_full_history": tot,
        "relevant_contract_ratio_full_history": ratio,
        "model_classification": model_cls,
        "score_total": item.get("score_total"),
        "suggested_offer": item.get("suggested_offer"),
        "reviewer_a_classification": None,
        "reviewer_b_classification": None,
        "adjudicated_classification": None,
        "agreement": None,
        "reviewer_a_reason": None,
        "reviewer_b_reason": None,
        "evidence_checked": None,
        "revisor_a": None,
        "revisor_b": None,
        "data_revisao": None,
        "allowed_labels": [
            "CLEAR_FIT",
            "POSSIBLE_FIT",
            "OUT_OF_SCOPE",
            "INSUFFICIENT_EVIDENCE",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-dir",
        default="artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/run",
    )
    ap.add_argument(
        "--out",
        default="artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/commercial-review-evaluation-sample.json",
    )
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    run = json.loads((run_dir / "run-result.json").read_text(encoding="utf-8"))
    review = []
    rq = run_dir / "review-queue.json"
    if rq.is_file():
        review = json.loads(rq.read_text(encoding="utf-8"))
    leads = run.get("leads") or []

    published = [_row(L, "published_or_strong") for L in leads[:50]]
    possible = [
        _row(r, "possible")
        for r in review
        if r.get("supplier_sector_fit") == "POSSIBLE_ENGINEERING_FIT"
    ][:50]
    conflicting = [
        _row(r, "conflicting_or_unknown")
        for r in review
        if r.get("supplier_sector_fit") in ("CONFLICTING", "UNKNOWN")
    ][:50]
    oos = [
        _row(r, "out_of_scope")
        for r in review
        if r.get("supplier_sector_fit") == "OUT_OF_SCOPE"
    ][:50]

    # pad from remaining review if short
    def pad(target: list, need: int, stratum: str, pool: list) -> list:
        have = {x["cnpj14"] for x in target}
        for r in pool:
            if len(target) >= need:
                break
            c = r.get("cnpj14")
            if c and c not in have:
                target.append(_row(r, stratum))
                have.add(c)
        return target

    possible = pad(possible, 50, "possible", review)
    conflicting = pad(conflicting, 50, "conflicting_or_unknown", review)
    oos = pad(oos, 50, "out_of_scope", review)
    # published pad from strong in review
    strong_pool = [
        r
        for r in review
        if r.get("supplier_sector_fit")
        in ("STRONG_ENGINEERING_FIT", "CONFIRMED_ENGINEERING")
    ]
    published = pad(published, 50, "published_or_strong", strong_pool + review)

    items = published + possible + conflicting + oos
    # de-dupe by cnpj keep first
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for it in items:
        c = it.get("cnpj14")
        if not c or c in seen:
            continue
        seen.add(c)
        unique.append(it)

    sample = {
        "status": "PENDING_HUMAN",
        "min_n": 200,
        "n": len(unique),
        "dual_review_required": True,
        "reviewers": ["REVIEWER_A", "REVIEWER_B"],
        "run_id": run.get("run_id"),
        "strata_counts": {
            "published_or_strong": sum(1 for x in unique if x["stratum"] == "published_or_strong"),
            "possible": sum(1 for x in unique if x["stratum"] == "possible"),
            "conflicting_or_unknown": sum(
                1 for x in unique if x["stratum"] == "conflicting_or_unknown"
            ),
            "out_of_scope": sum(1 for x in unique if x["stratum"] == "out_of_scope"),
        },
        "items": unique,
        "note": (
            "Real suppliers from last full-history run. Human labels must be filled "
            "independently by two reviewers; no auto-fill of reviewer_classification."
        ),
        "ok_structural": len(unique) >= 200,
    }
    out = Path(args.out)
    out.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # xlsx
    try:
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "evaluation_sample"
        headers = list(unique[0].keys()) if unique else ["cnpj14"]
        ws.append(headers)
        for r in unique:
            ws.append(
                [
                    json.dumps(r[h], ensure_ascii=False)
                    if isinstance(r.get(h), (list, dict))
                    else r.get(h)
                    for h in headers
                ]
            )
        xlsx = out.with_suffix(".xlsx")
        wb.save(xlsx)
        print(f"xlsx: {xlsx}")
    except Exception as exc:  # noqa: BLE001
        print(f"xlsx skip: {exc}")

    print(
        json.dumps(
            {
                "n": sample["n"],
                "ok_structural": sample["ok_structural"],
                "strata_counts": sample["strata_counts"],
                "out": str(out),
            },
            indent=2,
        )
    )
    return 0 if sample["ok_structural"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
