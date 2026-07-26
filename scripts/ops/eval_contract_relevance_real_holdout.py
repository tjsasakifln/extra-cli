#!/usr/bin/env python3
"""Evaluate real-contract holdout (never smoke set for performance claims).

Smoke adversarial set remains in evals/commercial_leads/holdout-v1.jsonl as
SMOKE_ADVERSARIAL_SET only.

Real corpus lives under evals/commercial_leads/real/:
  development-real-v1.jsonl
  validation-real-v1.jsonl
  holdout-real-v1.jsonl

Human labels (reviewer_1/2, adjudicated) must never be filled by agents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads import SMOKE_ADVERSARIAL_SET  # noqa: E402
from scripts.commercial_leads.contract_relevance import classify_contract_relevance  # noqa: E402

REAL_DIR = _ROOT / "evals/commercial_leads/real"
SMOKE_PATH = _ROOT / "evals/commercial_leads/holdout-v1.jsonl"
ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"


def _file_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_smoke_only() -> dict[str, Any]:
    """Smoke set metrics — explicitly not a real performance claim."""
    n = 0
    correct = 0
    if SMOKE_PATH.is_file():
        for line in SMOKE_PATH.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            pred = classify_contract_relevance(row.get("objeto") or row.get("text") or "").status
            exp = (row.get("expected") or row.get("label") or "").upper()
            # map smoke labels
            if exp in {"RELEVANT", "PASS", "TRUE", "1"}:
                exp_s = "PASS"
            elif exp in {"REVIEW"}:
                exp_s = "REVIEW"
            else:
                exp_s = "FAIL"
            if pred == exp_s:
                correct += 1
    return {
        "set_type": SMOKE_ADVERSARIAL_SET,
        "n": n,
        "accuracy_smoke_only": round(correct / n, 4) if n else None,
        "claim_allowed": False,
        "note": "Smoke adversarial set only — never publish as real precision/recall.",
    }


def evaluate_real_holdout(holdout_path: Path) -> dict[str, Any]:
    if not holdout_path.is_file():
        return {
            "ok": False,
            "status": "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED",
            "reason": "holdout_file_missing",
            "path": str(holdout_path),
            "set_type": "holdout-real-v1",
        }

    rows: list[dict[str, Any]] = []
    for line in holdout_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

    labeled = [
        r
        for r in rows
        if r.get("adjudicated_label")
        and r.get("reviewer_1_label")
        and r.get("reviewer_2_label")
    ]
    if len(labeled) < 500:
        return {
            "ok": False,
            "status": "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED",
            "reason": "insufficient_dual_human_labels",
            "n_rows": len(rows),
            "n_labeled": len(labeled),
            "min_required": 500,
            "corpus_sha256": _file_sha(holdout_path),
            "set_type": "holdout-real-v1",
            "thresholds": {"precision": 0.95, "recall": 0.90, "fpr": 0.05},
            "note": "Agents must not fill human label fields.",
        }

    # Metrics against adjudicated labels
    tp = fp = tn = fn = 0
    for r in labeled:
        gold = str(r["adjudicated_label"]).upper()
        if gold in {"RELEVANT", "PASS"}:
            gold_pos = True
        elif gold in {"NOT_RELEVANT", "FAIL", "IRRELEVANT"}:
            gold_pos = False
        else:
            continue  # REVIEW excluded from P/R binary
        pred = classify_contract_relevance(
            r.get("objeto_contrato_original") or r.get("objeto") or ""
        ).status
        pred_pos = pred == "PASS"
        if pred_pos and gold_pos:
            tp += 1
        elif pred_pos and not gold_pos:
            fp += 1
        elif not pred_pos and not gold_pos:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    fpr = fp / (fp + tn) if (fp + tn) else None
    ok = (
        precision is not None
        and recall is not None
        and fpr is not None
        and precision >= 0.95
        and recall >= 0.90
        and fpr <= 0.05
    )
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "set_type": "holdout-real-v1",
        "n_labeled": len(labeled),
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "false_positive_rate": round(fpr, 4) if fpr is not None else None,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "corpus_sha256": _file_sha(holdout_path),
        "thresholds": {"precision": 0.95, "recall": 0.90, "fpr": 0.05},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--holdout",
        type=Path,
        default=REAL_DIR / "holdout-real-v1.jsonl",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ART / "contract-relevance-real-holdout.json",
    )
    args = ap.parse_args(argv)
    smoke = evaluate_smoke_only()
    real = evaluate_real_holdout(args.holdout)
    report = {
        "smoke_adversarial_set": smoke,
        "real_holdout": real,
        "ok": bool(real.get("ok")),
        "status": real.get("status"),
        "claim_policy": (
            "Never publish 100% precision from SMOKE_ADVERSARIAL_SET. "
            "Real holdout dual-human labels required."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    # Exit 2 = BLOCKED (not green success), 1 = FAIL, 0 = PASS
    if real.get("status") == "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED":
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
