"""Human review loop: stratified export, idempotent import, calibration.

Labels are NEVER auto-filled. Without enough human labels, calibrate returns
PENDING_HUMAN without inventing metrics.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_DIR = PROJECT_ROOT / "data" / "human_reviews"

MIN_LABELS_FOR_METRICS = 10

REVIEW_FIELDS = (
    "opportunity_id",
    "source_id",
    "orgao_nome",
    "objeto",
    "valor_estimado",
    "modalidade",
    "status_canonico",
    "system_recommendation",
    "system_internal_ranking",
    "system_confidence",
    "stratum",
    "human_decision",
    "human_reason",
    "hard_block_confirmed",
    "missing_information",
    "would_present_to_client",
    "reviewed_at",
    "reviewer",
)


@dataclass
class CalibrateResult:
    status: str  # PENDING_HUMAN | OK
    n_labels: int
    min_required: int
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stratum(row: dict[str, Any]) -> str:
    rec = str(row.get("recommendation") or row.get("system_recommendation") or "")
    conf = str(row.get("confidence") or row.get("system_confidence") or "")
    missing = row.get("missing_information") or []
    if rec == "PARTICIPAR":
        return "best_candidate"
    if rec == "NÃO_PARTICIPAR" or rec == "NAO_PARTICIPAR":
        return "discard"
    if missing:
        return "incomplete_data"
    if conf == "LOW":
        return "borderline"
    return "borderline"


def stratified_sample(
    decisions: list[dict[str, Any]],
    *,
    target: int = 40,
    min_per_stratum: int = 3,
) -> list[dict[str, Any]]:
    """Stratified sample 30–50 (or all if fewer)."""
    if not decisions:
        return []
    target = max(1, min(50, max(30, target) if len(decisions) >= 30 else len(decisions)))
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in decisions:
        row = dict(d)
        row["stratum"] = _stratum(d)
        buckets[row["stratum"]].append(row)

    selected: list[dict[str, Any]] = []
    # ensure diversity
    for _str, items in buckets.items():
        take = min(min_per_stratum, len(items))
        selected.extend(items[:take])
    # fill remaining by round-robin
    if len(selected) < target:
        rest = []
        selected_ids = {s.get("opportunity_id") or s.get("id") for s in selected}
        for items in buckets.values():
            for it in items:
                oid = it.get("opportunity_id") or it.get("id")
                if oid not in selected_ids:
                    rest.append(it)
        need = target - len(selected)
        selected.extend(rest[:need])
    # if still short, take all
    if len(decisions) <= target:
        # all valid with strata
        all_rows = []
        for d in decisions:
            row = dict(d)
            row["stratum"] = _stratum(d)
            all_rows.append(row)
        return all_rows
    return selected[:target]


def export_review_sample(
    decisions: list[dict[str, Any]],
    out_path: Path,
    *,
    target: int = 40,
) -> dict[str, Any]:
    """Export CSV for human labeling — human_* columns left empty."""
    sample = stratified_sample(decisions, target=target)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows_out: list[dict[str, Any]] = []
    for d in sample:
        oid = d.get("opportunity_id") or d.get("id")
        rows_out.append(
            {
                "opportunity_id": oid,
                "source_id": d.get("source_id"),
                "orgao_nome": d.get("orgao_nome"),
                "objeto": (str(d.get("objeto") or ""))[:200],
                "valor_estimado": d.get("valor_estimado"),
                "modalidade": d.get("modalidade"),
                "status_canonico": d.get("status_canonico"),
                "system_recommendation": d.get("recommendation") or d.get("system_recommendation"),
                "system_internal_ranking": d.get("internal_ranking") or d.get("system_internal_ranking"),
                "system_confidence": d.get("confidence") or d.get("system_confidence"),
                "stratum": d.get("stratum") or _stratum(d),
                # human fields intentionally blank — never auto-filled
                "human_decision": "",
                "human_reason": "",
                "hard_block_confirmed": "",
                "missing_information": "",
                "would_present_to_client": "",
                "reviewed_at": "",
                "reviewer": "",
            }
        )
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(REVIEW_FIELDS))
        w.writeheader()
        for r in rows_out:
            w.writerow({k: r.get(k, "") for k in REVIEW_FIELDS})

    insufficient = len(sample) < 30
    meta = {
        "schema": "extra-review-export/1.0",
        "exported_at": _utc_now(),
        "n_sample": len(sample),
        "n_universe": len(decisions),
        "target": target,
        "insufficient_sample": insufficient,
        "note": (
            "Amostra insuficiente — use todos os válidos e declare insuficiência."
            if insufficient
            else "Amostra estratificada pronta para rotulagem humana."
        ),
        "path": str(out_path),
        "strata": dict(Counter(r["stratum"] for r in rows_out)),
    }
    meta_path = out_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def import_review_labels(
    csv_path: Path,
    store_dir: Path | None = None,
) -> dict[str, Any]:
    """Idempotent import: upsert by opportunity_id; preserve history of changes."""
    store = store_dir or DEFAULT_REVIEW_DIR
    store.mkdir(parents=True, exist_ok=True)
    labels_path = store / "labels.json"
    history_path = store / "history.jsonl"

    existing: dict[str, Any] = {"labels": {}}
    if labels_path.is_file():
        loaded: Any = json.loads(labels_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded
    raw_labels_any = existing.get("labels")
    raw_labels: dict[str, Any] = raw_labels_any if isinstance(raw_labels_any, dict) else {}
    labels: dict[str, dict[str, Any]] = {
        str(k): v for k, v in raw_labels.items() if isinstance(v, dict)
    }

    rows = _read_csv(csv_path)
    imported = 0
    skipped_empty = 0
    updates = 0
    for row in rows:
        oid = str(row.get("opportunity_id") or "").strip()
        human = str(row.get("human_decision") or "").strip()
        if not oid or not human:
            skipped_empty += 1
            continue
        # never invent — only accept explicit human fields
        payload = {
            "opportunity_id": oid,
            "human_decision": human,
            "human_reason": (row.get("human_reason") or "").strip(),
            "hard_block_confirmed": (row.get("hard_block_confirmed") or "").strip(),
            "missing_information": (row.get("missing_information") or "").strip(),
            "would_present_to_client": (row.get("would_present_to_client") or "").strip(),
            "reviewed_at": (row.get("reviewed_at") or "").strip() or _utc_now(),
            "reviewer": (row.get("reviewer") or "").strip() or "tiago",
            "system_recommendation": (row.get("system_recommendation") or "").strip(),
            "stratum": (row.get("stratum") or "").strip(),
            "imported_at": _utc_now(),
        }
        prev = labels.get(oid)
        if prev and prev.get("human_decision") == payload["human_decision"] and prev.get(
            "human_reason"
        ) == payload["human_reason"]:
            # idempotent no-op
            imported += 1
            continue
        if prev:
            updates += 1
            with history_path.open("a", encoding="utf-8") as hf:
                hf.write(
                    json.dumps(
                        {"at": _utc_now(), "opportunity_id": oid, "before": prev, "after": payload},
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
        labels[oid] = payload
        imported += 1

    store_doc = {
        "schema": "extra-human-labels/1.0",
        "updated_at": _utc_now(),
        "labels": labels,
        "n_labels": len(labels),
    }
    labels_path.write_text(
        json.dumps(store_doc, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "ok",
        "imported_rows": imported,
        "updates": updates,
        "skipped_empty_human": skipped_empty,
        "n_labels_total": len(labels),
        "labels_path": str(labels_path),
    }


def load_labels(store_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    store = store_dir or DEFAULT_REVIEW_DIR
    path = store / "labels.json"
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return dict(doc.get("labels") or {})


def _normalize_rec(val: str) -> str:
    v = (val or "").strip().upper().replace(" ", "_")
    if v in {"NAO_PARTICIPAR", "NAO-PARTICIPAR", "NO_GO", "NÃO-PARTICIPAR"}:
        return "NÃO_PARTICIPAR"
    if v in {"GO", "PARTICIPAR"}:
        return "PARTICIPAR"
    if v in {"REVIEW", "REVISAR"}:
        return "REVIEW"
    return v


def calibrate(
    labels: dict[str, dict[str, Any]] | None = None,
    store_dir: Path | None = None,
    *,
    min_labels: int = MIN_LABELS_FOR_METRICS,
) -> CalibrateResult:
    """Compute honest metrics only with enough human labels."""
    lab = labels if labels is not None else load_labels(store_dir)
    n = len(lab)
    if n < min_labels:
        return CalibrateResult(
            status="PENDING_HUMAN",
            n_labels=n,
            min_required=min_labels,
            metrics={},
            notes=[
                f"Apenas {n} labels humanos; mínimo {min_labels} para métricas.",
                "Nenhuma precisão/recall inventada.",
            ],
        )

    classes = ["PARTICIPAR", "REVIEW", "NÃO_PARTICIPAR"]
    matrix: dict[str, dict[str, int]] = {c: {d: 0 for d in classes} for c in classes}
    y_true: list[str] = []
    y_pred: list[str] = []
    for _oid, row in lab.items():
        t = _normalize_rec(str(row.get("human_decision") or ""))
        p = _normalize_rec(str(row.get("system_recommendation") or ""))
        if t not in classes or p not in classes:
            continue
        matrix[t][p] += 1
        y_true.append(t)
        y_pred.append(p)

    def prf(cls: str) -> dict[str, float]:
        tp = matrix[cls][cls]
        fp = sum(matrix[o][cls] for o in classes if o != cls)
        fn = sum(matrix[cls][o] for o in classes if o != cls)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        return {"precision": round(prec, 4), "recall": round(rec, 4), "support": tp + fn}

    per_class = {c: prf(c) for c in classes}
    agree = sum(1 for a, b in zip(y_true, y_pred, strict=False) if a == b)
    n_eval = len(y_true) or 1
    agreement = agree / n_eval

    # actionable false negatives: human PARTICIPAR, system NÃO_PARTICIPAR
    fn_actionable = matrix["PARTICIPAR"]["NÃO_PARTICIPAR"]
    by_stratum: dict[str, dict[str, Any]] = {}
    stratum_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in lab.values():
        st = str(row.get("stratum") or "unknown")
        stratum_groups[st].append(
            (
                _normalize_rec(str(row.get("human_decision") or "")),
                _normalize_rec(str(row.get("system_recommendation") or "")),
            )
        )
    for st, pairs in stratum_groups.items():
        ok = sum(1 for a, b in pairs if a == b and a)
        by_stratum[st] = {
            "n": len(pairs),
            "agreement": round(ok / len(pairs), 4) if pairs else 0.0,
        }

    # Wilson-ish rough CI for agreement (honest interval when n small)
    z = 1.96
    phat = agreement
    denom = 1 + z**2 / n_eval
    center = (phat + z**2 / (2 * n_eval)) / denom
    margin = (z * math.sqrt((phat * (1 - phat) + z**2 / (4 * n_eval)) / n_eval)) / denom
    ci = [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]

    metrics = {
        "confusion_matrix": matrix,
        "per_class": per_class,
        "participar_precision": per_class["PARTICIPAR"]["precision"],
        "actionable_false_negative_rate": round(
            fn_actionable / max(1, per_class["PARTICIPAR"]["support"]),
            4,
        ),
        "actionable_false_negatives": fn_actionable,
        "agreement_system_vs_human": round(agreement, 4),
        "agreement_ci95": ci,
        "by_stratum": by_stratum,
        "n_evaluated": len(y_true),
    }
    return CalibrateResult(
        status="OK",
        n_labels=n,
        min_required=min_labels,
        metrics=metrics,
        notes=["Métricas calculadas apenas sobre labels humanos persistidos."],
    )
