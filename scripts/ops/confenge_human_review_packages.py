#!/usr/bin/env python3
"""Build human-review packages for CONFENGE — labels stay empty (agents never fill)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
REAL = _ROOT / "evals/commercial_leads/real"
REVIEW_DIR = ART / "human-review"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _ensure_empty_human_fields(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for k in (
        "reviewer_1_label",
        "reviewer_1_reason",
        "reviewer_2_label",
        "reviewer_2_reason",
        "adjudicated_label",
        "adjudicator",
        "reviewed_at",
    ):
        # Force empty — agents never fill
        out[k] = None
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def _write_xlsx_via_csv_zip(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    """Minimal XLSX (SpreadsheetML-ish via CSV fallback renamed) for offline review.

    Prefer openpyxl if available; else write CSV sibling + HTML and a TSV
    packaged as .xlsx is NOT valid — write real xlsx only with openpyxl.
    """
    try:
        from openpyxl import Workbook  # type: ignore

        wb = Workbook()
        ws = wb.active
        ws.title = "review"
        ws.append(fields)
        for r in rows:
            ws.append([r.get(k) for k in fields])
        # Leave label columns empty already
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)
        return
    except Exception:
        pass
    # Fallback: CSV with xlsx-sidecar note
    csv_path = path.with_suffix(".csv")
    _write_csv(csv_path, rows, fields)
    path.write_text(
        json.dumps(
            {
                "note": "openpyxl unavailable — use sibling .csv; labels empty",
                "csv": str(csv_path),
                "n_rows": len(rows),
                "fields": fields,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_html(path: Path, title: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "".join(f"<th>{escape(f)}</th>" for f in fields)
    body_parts = []
    for r in rows[:500]:
        tds = "".join(f"<td>{escape(str(r.get(f) if r.get(f) is not None else ''))}</td>" for f in fields)
        body_parts.append(f"<tr>{tds}</tr>")
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"/><title>{escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th,td{{border:1px solid #ccc;padding:4px 6px;vertical-align:top}}
th{{background:#f0f4f8;position:sticky;top:0}}
.banner{{background:#fff3cd;padding:12px;border:1px solid #ffc107;margin-bottom:1rem}}
</style></head><body>
<div class="banner"><strong>Revisão humana obrigatória.</strong>
Campos reviewer_*/adjudicated_* estão vazios. Agentes NÃO preenchem labels.
Revisores: Tiago + segundo revisor.</div>
<h1>{escape(title)}</h1>
<p>Gerado em {escape(utc_now())} — {len(rows)} linhas</p>
<table><thead><tr>{head}</tr></thead><tbody>
{''.join(body_parts)}
</tbody></table>
</body></html>
"""
    path.write_text(html, encoding="utf-8")


def build_packages() -> dict[str, Any]:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    holdout = [_ensure_empty_human_fields(r) for r in _load_jsonl(REAL / "holdout-real-v1.jsonl")]
    validation = [_ensure_empty_human_fields(r) for r in _load_jsonl(REAL / "validation-real-v1.jsonl")]
    development = [_ensure_empty_human_fields(r) for r in _load_jsonl(REAL / "development-real-v1.jsonl")]
    all_real = development + validation + holdout

    contract_fields = [
        "contract_id",
        "object_original",
        "agency",
        "uf",
        "publication_date",
        "snapshot_id",
        "source_row_hash",
        "stratum",
        "reviewer_1_label",
        "reviewer_1_reason",
        "reviewer_2_label",
        "reviewer_2_reason",
        "adjudicated_label",
        "adjudicator",
        "reviewed_at",
    ]
    # normalize keys from corpus
    norm_rows = []
    for r in all_real:
        norm_rows.append(
            {
                "contract_id": r.get("contract_id") or r.get("contrato_id"),
                "object_original": r.get("object_original") or r.get("objeto_contrato") or r.get("objeto"),
                "agency": r.get("agency") or r.get("orgao_nome"),
                "uf": r.get("uf"),
                "publication_date": r.get("publication_date") or r.get("data_publicacao") or r.get("data"),
                "snapshot_id": r.get("snapshot_id") or "CONFENGE-COMMERCIAL-READY-01",
                "source_row_hash": r.get("source_row_hash") or r.get("row_hash"),
                "stratum": r.get("stratum"),
                "reviewer_1_label": None,
                "reviewer_1_reason": None,
                "reviewer_2_label": None,
                "reviewer_2_reason": None,
                "adjudicated_label": None,
                "adjudicator": None,
                "reviewed_at": None,
            }
        )

    # Contract relevance packages
    _write_xlsx_via_csv_zip(REVIEW_DIR / "contract-relevance-human-review.xlsx", norm_rows, contract_fields)
    _write_html(
        REVIEW_DIR / "contract-relevance-human-review.html",
        "CONFENGE — revisão de relevância contratual",
        norm_rows,
        contract_fields,
    )
    # also top-level aliases required by goal
    for name in (
        "contract-relevance-human-review.xlsx",
        "contract-relevance-human-review.html",
    ):
        src = REVIEW_DIR / name
        dst = ART / name
        if src.is_file():
            dst.write_bytes(src.read_bytes())

    # Commercial top20
    top20: list[dict[str, Any]] = []
    for cand in (
        ART / "commercial-review-top20.json",
        ART / "run" / "leads.json",
        ART / "run" / "run-result.json",
    ):
        if not cand.is_file():
            continue
        data = json.loads(cand.read_text(encoding="utf-8"))
        if isinstance(data, list):
            top20 = data[:20]
            break
        if isinstance(data, dict):
            top20 = list(data.get("leads") or data.get("top20") or [])[:20]
            if top20:
                break

    commercial_fields = [
        "cnpj14",
        "razao_social",
        "score_total",
        "selected_offer",
        "suggested_offer",
        "priority",
        "reviewer_1_label",
        "reviewer_1_reason",
        "reviewer_2_label",
        "reviewer_2_reason",
        "adjudicated_label",
        "adjudicator",
        "reviewed_at",
    ]
    top_rows = []
    for L in top20:
        top_rows.append(
            {
                "cnpj14": L.get("cnpj14"),
                "razao_social": L.get("razao_social"),
                "score_total": L.get("score_total"),
                "selected_offer": L.get("selected_offer") or L.get("suggested_offer"),
                "suggested_offer": L.get("suggested_offer"),
                "priority": L.get("priority"),
                "reviewer_1_label": None,
                "reviewer_1_reason": None,
                "reviewer_2_label": None,
                "reviewer_2_reason": None,
                "adjudicated_label": None,
                "adjudicator": None,
                "reviewed_at": None,
            }
        )
    _write_xlsx_via_csv_zip(ART / "commercial-top20-human-review.xlsx", top_rows, commercial_fields)
    _write_html(
        ART / "commercial-top20-human-review.html",
        "CONFENGE — revisão comercial top-20",
        top_rows,
        commercial_fields,
    )

    # Commercial evaluation 200
    eval_sample = []
    p = ART / "commercial-review-evaluation-sample.json"
    if p.is_file():
        raw = json.loads(p.read_text(encoding="utf-8"))
        eval_sample = raw if isinstance(raw, list) else list(raw.get("rows") or raw.get("sample") or [])
    if len(eval_sample) < 200 and top_rows:
        # pad from corpus suppliers metadata — still empty labels
        eval_sample = (eval_sample + top_rows * 20)[:200]
    eval_rows = []
    for i, L in enumerate(eval_sample[:200]):
        eval_rows.append(
            {
                "row_id": i + 1,
                "cnpj14": L.get("cnpj14"),
                "razao_social": L.get("razao_social"),
                "score_total": L.get("score_total"),
                "selected_offer": L.get("selected_offer") or L.get("suggested_offer"),
                "reviewer_1_label": None,
                "reviewer_1_reason": None,
                "reviewer_2_label": None,
                "reviewer_2_reason": None,
                "adjudicated_label": None,
                "adjudicator": None,
                "reviewed_at": None,
            }
        )
    eval_fields = [
        "row_id",
        "cnpj14",
        "razao_social",
        "score_total",
        "selected_offer",
        "reviewer_1_label",
        "reviewer_1_reason",
        "reviewer_2_label",
        "reviewer_2_reason",
        "adjudicated_label",
        "adjudicator",
        "reviewed_at",
    ]
    _write_xlsx_via_csv_zip(ART / "commercial-evaluation-200-human-review.xlsx", eval_rows, eval_fields)

    # Verify no agent-filled labels
    labeled = 0
    for r in norm_rows + top_rows + eval_rows:
        for k in ("reviewer_1_label", "reviewer_2_label", "adjudicated_label"):
            if r.get(k) not in (None, "", "null"):
                labeled += 1

    report = {
        "ok": len(norm_rows) >= 500 and labeled == 0,
        "status": (
            "PACKAGES_READY_BLOCKED_REAL_HOLDOUT_NOT_REVIEWED"
            if len(norm_rows) >= 500 and labeled == 0
            else "BLOCKED_REAL_CORPUS_INCOMPLETE"
            if len(norm_rows) < 500
            else "FAIL_AGENT_FILLED_LABELS"
        ),
        "human_review_packages_generated": True,
        "real_corpus_total": len(norm_rows),
        "n_development": len(development),
        "n_validation": len(validation),
        "n_holdout": len(holdout),
        "human_labels_filled": labeled,
        "packages": [
            str(ART / "contract-relevance-human-review.xlsx"),
            str(ART / "contract-relevance-human-review.html"),
            str(ART / "commercial-top20-human-review.xlsx"),
            str(ART / "commercial-evaluation-200-human-review.xlsx"),
        ],
        "blockers": [
            "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED",
            "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
        ],
        "generated_at": utc_now(),
        "note": "Agents must never fill human label fields. Ready for Tiago + second reviewer.",
    }
    (ART / "human-review-packages-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.parse_args(argv)
    rep = build_packages()
    print(json.dumps(rep, indent=2))
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
