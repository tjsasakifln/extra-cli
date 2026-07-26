#!/usr/bin/env python3
"""Evaluate hierarchical contract relevance on frozen holdout corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.contract_relevance import classify_contract_relevance  # noqa: E402


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    confusion: list[dict[str, Any]] = []
    by_cat: dict[str, dict[str, int]] = {}
    for r in rows:
        pred_pass = classify_contract_relevance(r["objeto"]).status == "PASS"
        gold = bool(r["relevant"])
        cat = str(r.get("category") or "unknown")
        by_cat.setdefault(cat, {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
        if pred_pass and gold:
            tp += 1
            by_cat[cat]["tp"] += 1
        elif pred_pass and not gold:
            fp += 1
            by_cat[cat]["fp"] += 1
            confusion.append({"id": r.get("id"), "type": "FP", "objeto": r["objeto"], "category": cat})
        elif not pred_pass and not gold:
            tn += 1
            by_cat[cat]["tn"] += 1
        else:
            fn += 1
            by_cat[cat]["fn"] += 1
            confusion.append({"id": r.get("id"), "type": "FN", "objeto": r["objeto"], "category": cat})
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return {
        "n": len(rows),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fpr, 4),
        "by_category": by_cat,
        "errors": confusion,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--holdout",
        default=str(_ROOT / "evals/commercial_leads/holdout-v1.jsonl"),
    )
    ap.add_argument(
        "--out",
        default=str(
            _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/contract-relevance-holdout.json"
        ),
    )
    ap.add_argument("--min-precision", type=float, default=0.95)
    ap.add_argument("--min-recall", type=float, default=0.90)
    ap.add_argument("--max-fpr", type=float, default=0.05)
    args = ap.parse_args(argv)

    rows = load_jsonl(Path(args.holdout))
    metrics = evaluate(rows)
    ok = (
        metrics["precision"] >= args.min_precision
        and metrics["recall"] >= args.min_recall
        and metrics["false_positive_rate"] <= args.max_fpr
    )
    report = {
        "holdout_path": args.holdout,
        "thresholds": {
            "precision": args.min_precision,
            "recall": args.min_recall,
            "false_positive_rate": args.max_fpr,
        },
        "metrics": metrics,
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": ok, **{k: metrics[k] for k in ("precision", "recall", "f1", "false_positive_rate", "n")}}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
