"""Import explicit human documentary review records.

Only this path may set human_review_completed=True.
Automated desk/AI packages must never call complete_human_review.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

REQUIRED_HINT_FIELDS = (
    "reviewer",
    "decision",
)


def load_human_review_file(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load JSON or CSV human review file keyed by contrato_id or cnpj.

    Expected fields (JSON list/object or CSV columns):
      reviewer, reviewed_at, documents_read, pages, clauses,
      data_base_confirmed, index_confirmed, prior_adjustment,
      balance_or_measurements, decision, notes, confidence,
      contrato_id and/or cnpj
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"human-review-file not found: {p}")

    records: list[dict[str, Any]] = []
    if p.suffix.lower() == ".json":
        payload = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            records = [r for r in payload if isinstance(r, dict)]
        elif isinstance(payload, dict):
            if "reviews" in payload and isinstance(payload["reviews"], list):
                records = [r for r in payload["reviews"] if isinstance(r, dict)]
            elif "records" in payload and isinstance(payload["records"], list):
                records = [r for r in payload["records"] if isinstance(r, dict)]
            else:
                records = [payload]
    elif p.suffix.lower() == ".csv":
        with p.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            records = list(reader)
    else:
        raise ValueError(f"Unsupported human-review-file format: {p.suffix}")

    out: dict[str, dict[str, Any]] = {}
    for raw in records:
        rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        if not rec.get("reviewer"):
            continue
        # Normalize decision
        decision = str(rec.get("decision") or "").strip().upper()
        rec["decision"] = decision
        rec["human_review_completed"] = decision in {
            "ACCEPT",
            "CONFIRMED",
            "APPROVED",
            "COMPLETE",
        }
        # Never allow automated sources to pose as human
        source = str(rec.get("source") or rec.get("kind") or "").lower()
        if "ai" in source or "automated" in source or "machine" in source:
            rec["human_review_completed"] = False
            rec["decision"] = "REJECT_AUTOMATED_SOURCE"
        cid = str(rec.get("contrato_id") or rec.get("contract_id") or "").strip()
        cnpj = "".join(ch for ch in str(rec.get("cnpj") or "") if ch.isdigit())[:14]
        if cid:
            out[cid] = rec
        if len(cnpj) == 14:
            # CNPJ key only if no more specific contract key already preferred
            out.setdefault(cnpj, rec)
    return out


def human_review_done_for(
    records: dict[str, dict[str, Any]],
    *,
    contrato_id: str | None = None,
    cnpj: str | None = None,
) -> bool:
    """True only when an imported human review explicitly completed."""
    rec = None
    if contrato_id and contrato_id in records:
        rec = records[contrato_id]
    elif cnpj:
        c = "".join(ch for ch in cnpj if ch.isdigit())[:14]
        rec = records.get(c)
    if not rec:
        return False
    if rec.get("human_review_completed"):
        return True
    return (
        rec.get("decision") in {"ACCEPT", "CONFIRMED", "APPROVED", "COMPLETE"}
        and bool(rec.get("reviewer"))
    )
