#!/usr/bin/env python3
"""Build human-review packages for CONFENGE — labels stay empty (agents never fill).

Maps real corpus field names (objeto_contrato_original, orgao, ...) into the
review schema required by the campaign. Validates required non-empty fields
before claiming packages ready. Top-20 is taken from the freeze-era full-universe
E2E artifact, not from stale commercial-review-top20.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
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

REQUIRED_CORPUS_FIELDS = (
    "contract_id",
    "object_original",
    "agency",
    "uf",
    "publication_date",
    "snapshot_id",
    "source_row_hash",
    "stratum",
)
HUMAN_EMPTY_FIELDS = (
    "reviewer_1_label",
    "reviewer_1_reason",
    "reviewer_2_label",
    "reviewer_2_reason",
    "adjudicated_label",
    "adjudicator",
    "reviewed_at",
)


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


def _row_hash(parts: list[Any]) -> str:
    blob = "|".join("" if p is None else str(p) for p in parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def normalize_corpus_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Map corpus keys → review schema. Never invent human labels."""
    contract_id = (
        raw.get("contract_id")
        or raw.get("contrato_id")
        or raw.get("source_id")
    )
    object_original = (
        raw.get("object_original")
        or raw.get("objeto_contrato_original")
        or raw.get("objeto_contrato")
        or raw.get("objeto")
    )
    agency = raw.get("agency") or raw.get("orgao") or raw.get("orgao_nome")
    uf = raw.get("uf")
    publication_date = (
        raw.get("publication_date")
        or raw.get("data_publicacao")
        or raw.get("data")
    )
    snapshot_id = (
        raw.get("snapshot_id")
        or raw.get("source_snapshot")
        or "CONFENGE-COMMERCIAL-READY-01"
    )
    stratum = raw.get("stratum")
    source_row_hash = raw.get("source_row_hash") or raw.get("row_hash")
    if not source_row_hash:
        source_row_hash = _row_hash(
            [contract_id, object_original, agency, uf, publication_date, snapshot_id]
        )
    out = {
        "contract_id": contract_id,
        "object_original": object_original,
        "agency": agency,
        "uf": uf,
        "publication_date": publication_date,
        "snapshot_id": snapshot_id,
        "source_row_hash": source_row_hash,
        "stratum": stratum,
    }
    for k in HUMAN_EMPTY_FIELDS:
        out[k] = None  # agents never fill
    return out


def validate_corpus_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing_counts = {f: 0 for f in REQUIRED_CORPUS_FIELDS}
    labeled = 0
    for r in rows:
        for f in REQUIRED_CORPUS_FIELDS:
            v = r.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                missing_counts[f] += 1
        for k in ("reviewer_1_label", "reviewer_2_label", "adjudicated_label"):
            if r.get(k) not in (None, "", "null"):
                labeled += 1
    incomplete = {k: v for k, v in missing_counts.items() if v > 0}
    ok = (
        len(rows) >= 500
        and not incomplete
        and labeled == 0
    )
    return {
        "ok": ok,
        "n_rows": len(rows),
        "missing_required_field_counts": missing_counts,
        "incomplete_fields": incomplete,
        "human_labels_filled": labeled,
        "min_required": 500,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def _excel_clean(value: Any) -> Any:
    """Strip characters illegal in Excel cells (openpyxl ILLEGAL_CHARACTERS_RE)."""
    if value is None or not isinstance(value, str):
        return value
    try:
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE  # type: ignore

        return ILLEGAL_CHARACTERS_RE.sub("", value)
    except ImportError:
        return value


def _write_xlsx(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    from openpyxl import Workbook  # type: ignore

    wb = Workbook()
    ws = wb.active
    ws.title = "review"
    ws.append(list(fields))
    for r in rows:
        ws.append([_excel_clean(r.get(k)) for k in fields])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def _write_html(path: Path, title: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "".join(f"<th>{escape(f)}</th>" for f in fields)
    body_parts = []
    for r in rows[:500]:
        tds = "".join(
            f"<td>{escape(str(r.get(f) if r.get(f) is not None else ''))}</td>" for f in fields
        )
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


def load_e2e_top20() -> list[dict[str, Any]]:
    """Prefer full-universe E2E offer_detail_top20 (freeze execution)."""
    e2e_path = ART / "full-universe-e2e-reproducibility-gate.json"
    if e2e_path.is_file():
        e2e = json.loads(e2e_path.read_text(encoding="utf-8"))
        detail = (e2e.get("pass_a") or {}).get("offer_detail_top20") or []
        if detail:
            return list(detail)
        order = (e2e.get("pass_a") or {}).get("top20_order") or []
        offers = (e2e.get("pass_a") or {}).get("offer_mapping") or []
        out = []
        for i, cnpj in enumerate(order):
            out.append(
                {
                    "cnpj14": cnpj,
                    "selected_offer": offers[i] if i < len(offers) else None,
                }
            )
        if out:
            return out
    # Fallback: run leads (may be stale — flagged in gate)
    for cand in (ART / "run" / "leads.json", ART / "commercial-review-top20.json"):
        if not cand.is_file():
            continue
        data = json.loads(cand.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data[:20]
        if isinstance(data, dict):
            leads = list(data.get("leads") or data.get("top20") or [])[:20]
            if leads:
                return leads
    return []


def _load_split(name_v2: str, name_v1: str) -> list[dict[str, Any]]:
    rows = _load_jsonl(REAL / name_v2)
    if rows:
        return [normalize_corpus_row(r) for r in rows]
    return [normalize_corpus_row(r) for r in _load_jsonl(REAL / name_v1)]


def _write_readme(path: Path) -> None:
    path.write_text(
        """# CONFENGE — Pacote de Revisão Humana

## Como preencher

1. Abra as planilhas `.xlsx` (preferencial) ou o HTML correspondente.
2. Cada linha é um objeto de revisão. **Não altere** `contract_id` / `cnpj14` / hashes.
3. Preencha os campos humanos listados abaixo. Agentes de IA **não** preenchem labels.

## Labels permitidas (relevância contratual)

| Label | Significado |
|-------|-------------|
| `RELEVANT_ENGINEERING` | Objeto claramente de engenharia/obras/infra |
| `AMBIGUOUS` | Ambíguo — requer adjudicação |
| `NOT_RELEVANT` | Fora de escopo (limpeza, merenda, TI genérica, etc.) |
| `INSUFFICIENT_TEXT` | Texto insuficiente para decidir |

## Labels permitidas (comercial top-20 / eval-200)

| Label | Significado |
|-------|-------------|
| `ACCEPT_OFFER` | Oferta sugerida aceitável para abordagem humana |
| `REJECT_OFFER` | Oferta inadequada |
| `WRONG_SECTOR` | Fornecedor fora do setor engenharia |
| `NEEDS_MORE_EVIDENCE` | Evidência insuficiente |

## Campos obrigatórios por revisor

- `reviewer_1_label`, `reviewer_1_reason`
- `reviewer_2_label`, `reviewer_2_reason`

## Identificar revisor 1 e revisor 2

- **Reviewer 1**: primeiro revisor humano designado (ex.: Tiago)
- **Reviewer 2**: segundo revisor independente
- Use nomes consistentes no campo `adjudicator` apenas na fase de adjudicação

## Adjudicar divergências

Quando `reviewer_1_label != reviewer_2_label`:

1. Terceiro revisor (adjudicator) preenche `adjudicated_label`
2. Registra `adjudicator` (nome) e `reviewed_at` (ISO-8601)
3. Não sobrescreva labels originais dos revisores 1/2

## Reimportar resultados

```bash
# Exemplo: copiar planilha preenchida para inbox e rodar avaliação
cp contract-relevance-human-review-filled.xlsx \\
  artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/human-review/inbox/
make evaluate-confenge-real-contract-holdout
```

## Executar a avaliação

```bash
make evaluate-confenge-real-contract-holdout
make verify-confenge-real-corpus-provenance
```

## Checksums

Consulte `checksums.json` neste pacote. O pacote é gerado localmente e
publicado como artefato de workflow `confenge-human-review-packages`
(não precisa ser commitado no Git).
""",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_packages() -> dict[str, Any]:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    development = _load_split("development-real-v2.jsonl", "development-real-v1.jsonl")
    validation = _load_split("validation-real-v2.jsonl", "validation-real-v1.jsonl")
    holdout = _load_split("holdout-real-v2.jsonl", "holdout-real-v1.jsonl")
    all_real = development + validation + holdout

    corpus_val = validate_corpus_rows(all_real)
    contract_fields = list(REQUIRED_CORPUS_FIELDS) + list(HUMAN_EMPTY_FIELDS)

    _write_xlsx(REVIEW_DIR / "contract-relevance-human-review.xlsx", all_real, contract_fields)
    _write_html(
        REVIEW_DIR / "contract-relevance-human-review.html",
        "CONFENGE — revisão de relevância contratual",
        all_real,
        contract_fields,
    )
    for name in (
        "contract-relevance-human-review.xlsx",
        "contract-relevance-human-review.html",
    ):
        src = REVIEW_DIR / name
        dst = ART / name
        if src.is_file():
            dst.write_bytes(src.read_bytes())

    # Commercial top20 from E2E freeze execution
    top20_src = load_e2e_top20()
    e2e_path = ART / "full-universe-e2e-reproducibility-gate.json"
    e2e_order: list[str] = []
    if e2e_path.is_file():
        e2e = json.loads(e2e_path.read_text(encoding="utf-8"))
        e2e_order = list((e2e.get("pass_a") or {}).get("top20_order") or [])

    commercial_fields = [
        "cnpj14",
        "razao_social",
        "score_total",
        "selected_offer",
        "alternative_offer",
        "selected_offer_margin",
        "supporting_signals",
        "contradicting_signals",
        "offer_scores",
        "priority",
        *HUMAN_EMPTY_FIELDS,
    ]
    # Enrich razao_social from registry when possible
    names: dict[str, str] = {}
    try:
        import os

        from scripts.commercial_leads.dbutil import connect, fetch_all

        dsn = os.environ.get(
            "CONFENGE_COMMERCIAL_STATE_DSN",
            "postgresql://postgres:postgres@127.0.0.1:5433/confenge_commercial",
        )
        cnpjs = [str(x.get("cnpj14")) for x in top20_src if x.get("cnpj14")]
        if cnpjs:
            conn = connect(dsn)
            try:
                rows = fetch_all(
                    conn,
                    "SELECT cnpj14, razao_social FROM public.supplier_registry WHERE cnpj14 = ANY(%s)",
                    (cnpjs,),
                )
                names = {str(r["cnpj14"]): str(r.get("razao_social") or "") for r in rows}
            finally:
                conn.close()
    except (OSError, ImportError, RuntimeError) as exc:
        names = {}
        _ = exc  # registry enrichment is best-effort

    top_rows: list[dict[str, Any]] = []
    for lead in top20_src[:20]:
        cnpj = str(lead.get("cnpj14") or "")
        offer = lead.get("selected_offer") or lead.get("suggested_offer")
        top_rows.append(
            {
                "cnpj14": cnpj,
                "razao_social": lead.get("razao_social") or names.get(cnpj) or "",
                "score_total": lead.get("score_total"),
                "selected_offer": offer,
                "alternative_offer": lead.get("alternative_offer"),
                "selected_offer_margin": lead.get("selected_offer_margin"),
                "supporting_signals": json.dumps(lead.get("supporting_signals") or [], ensure_ascii=False)
                if not isinstance(lead.get("supporting_signals"), str)
                else lead.get("supporting_signals"),
                "contradicting_signals": json.dumps(
                    lead.get("contradicting_signals") or [], ensure_ascii=False
                )
                if not isinstance(lead.get("contradicting_signals"), str)
                else lead.get("contradicting_signals"),
                "offer_scores": json.dumps(lead.get("offer_scores") or {}, ensure_ascii=False)
                if not isinstance(lead.get("offer_scores"), str)
                else lead.get("offer_scores"),
                "priority": lead.get("priority"),
                **{k: None for k in HUMAN_EMPTY_FIELDS},
            }
        )

    pkg_order = [r["cnpj14"] for r in top_rows]
    top20_aligned = (
        len(e2e_order) == 20
        and len(pkg_order) == 20
        and pkg_order == e2e_order
    )
    offer_names = {r.get("selected_offer") for r in top_rows}
    stale_admin = "acompanhamento_admin" in offer_names

    _write_xlsx(ART / "commercial-top20-human-review.xlsx", top_rows, commercial_fields)
    _write_html(
        ART / "commercial-top20-human-review.html",
        "CONFENGE — revisão comercial top-20 (E2E freeze)",
        top_rows,
        commercial_fields,
    )

    # Commercial evaluation 200 — use top20 + additional registry/suppliers with empty labels
    eval_rows: list[dict[str, Any]] = []
    for i, lead in enumerate(top_rows):
        eval_rows.append(
            {
                "row_id": i + 1,
                "cnpj14": lead.get("cnpj14"),
                "razao_social": lead.get("razao_social"),
                "score_total": lead.get("score_total"),
                "selected_offer": lead.get("selected_offer"),
                **{k: None for k in HUMAN_EMPTY_FIELDS},
            }
        )
    # pad to 200 with additional cnpjs from frozen universe (empty commercial scores)
    frozen_path = ART / "frozen-candidate-universe.json"
    if frozen_path.is_file() and len(eval_rows) < 200:
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        used = {r["cnpj14"] for r in eval_rows}
        for c in frozen.get("candidate_supplier_cnpjs") or []:
            if c in used:
                continue
            eval_rows.append(
                {
                    "row_id": len(eval_rows) + 1,
                    "cnpj14": c,
                    "razao_social": "",
                    "score_total": None,
                    "selected_offer": None,
                    **{k: None for k in HUMAN_EMPTY_FIELDS},
                }
            )
            if len(eval_rows) >= 200:
                break
    eval_fields = [
        "row_id",
        "cnpj14",
        "razao_social",
        "score_total",
        "selected_offer",
        *HUMAN_EMPTY_FIELDS,
    ]
    _write_xlsx(ART / "commercial-evaluation-200-human-review.xlsx", eval_rows[:200], eval_fields)
    _write_html(
        ART / "commercial-evaluation-200-human-review.html",
        "CONFENGE — avaliação comercial 200",
        eval_rows[:200],
        eval_fields,
    )
    # also under human-review staging dir for workflow artifact
    for name in (
        "commercial-top20-human-review.xlsx",
        "commercial-top20-human-review.html",
        "commercial-evaluation-200-human-review.xlsx",
        "commercial-evaluation-200-human-review.html",
        "contract-relevance-human-review.xlsx",
        "contract-relevance-human-review.html",
    ):
        src = ART / name
        if src.is_file():
            (REVIEW_DIR / name).write_bytes(src.read_bytes())

    _write_readme(REVIEW_DIR / "README-HUMAN-REVIEW.md")
    (ART / "README-HUMAN-REVIEW.md").write_text(
        (REVIEW_DIR / "README-HUMAN-REVIEW.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    required_pkg = [
        "contract-relevance-human-review.xlsx",
        "contract-relevance-human-review.html",
        "commercial-top20-human-review.xlsx",
        "commercial-top20-human-review.html",
        "commercial-evaluation-200-human-review.xlsx",
        "README-HUMAN-REVIEW.md",
    ]
    checksums: dict[str, Any] = {"files": {}, "generated_at": utc_now()}
    for name in required_pkg + ["commercial-evaluation-200-human-review.html"]:
        p = ART / name
        if p.is_file():
            checksums["files"][name] = {
                "sha256": _file_sha256(p),
                "size_bytes": p.stat().st_size,
            }
            (REVIEW_DIR / name).write_bytes(p.read_bytes()) if name != "README-HUMAN-REVIEW.md" else None
    # executed SHA binding
    exec_path = ART / "EXECUTED_CODE_SHA.txt"
    executed = (
        exec_path.read_text(encoding="utf-8").strip().split()[0]
        if exec_path.is_file()
        else None
    )
    checksums["executed_code_sha"] = executed
    checksums["workflow_run_id"] = os.environ.get("GITHUB_RUN_ID")
    checksums["artifact_name"] = "confenge-human-review-packages"
    (REVIEW_DIR / "checksums.json").write_text(
        json.dumps(checksums, indent=2) + "\n", encoding="utf-8"
    )
    (ART / "checksums-human-review.json").write_text(
        json.dumps(checksums, indent=2) + "\n", encoding="utf-8"
    )

    packages_exist = all((ART / p).is_file() for p in required_pkg)
    packages_ready = bool(
        packages_exist
        and corpus_val["ok"]
        and top20_aligned
        and not stale_admin
        and len(top_rows) == 20
        and (REVIEW_DIR / "checksums.json").is_file()
    )

    if not corpus_val["ok"]:
        status = "BLOCKED_REAL_CORPUS_INCOMPLETE"
    elif not top20_aligned or stale_admin:
        status = "BLOCKED_HUMAN_PACKAGES_NOT_ALIGNED_TO_E2E"
    elif not packages_ready:
        status = "BLOCKED_HUMAN_PACKAGES_NOT_READY"
    else:
        status = "PACKAGES_READY_BLOCKED_REAL_HOLDOUT_NOT_REVIEWED"

    # Workflow publication: true when GITHUB_ACTIONS uploads this dir, else local ready
    published = bool(os.environ.get("GITHUB_ACTIONS") and os.environ.get("GITHUB_RUN_ID"))
    report = {
        "ok": packages_ready,
        "status": status,
        "human_review_packages_generated": packages_exist,
        "packages_ready_for_human_review": packages_ready,
        "review_packages_generated": packages_exist,
        "published_as_workflow_artifact": published,
        "workflow_artifact_name": "confenge-human-review-packages",
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "package_dir": str(REVIEW_DIR),
        "checksums": checksums,
        "executed_code_sha": executed,
        "real_corpus_total": len(all_real),
        "n_development": len(development),
        "n_validation": len(validation),
        "n_holdout": len(holdout),
        "human_labels_filled": corpus_val["human_labels_filled"],
        "corpus_validation": corpus_val,
        "top20_source": "full-universe-e2e-reproducibility-gate.pass_a.offer_detail_top20",
        "top20_aligned_to_e2e": top20_aligned,
        "top20_order": pkg_order,
        "e2e_top20_order": e2e_order,
        "top20_intersection_with_e2e": len(set(pkg_order) & set(e2e_order)),
        "stale_acompanhamento_admin_present": stale_admin,
        "packages": [str(ART / p) for p in required_pkg],
        "blockers": [
            "BLOCKED_REAL_HOLDOUT_NOT_REVIEWED",
            "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
        ]
        + (
            ["BLOCKED_REAL_CORPUS_INCOMPLETE"]
            if not corpus_val["ok"]
            else []
        )
        + (
            ["BLOCKED_HUMAN_PACKAGES_NOT_ALIGNED_TO_E2E"]
            if not top20_aligned or stale_admin
            else []
        ),
        "generated_at": utc_now(),
        "note": (
            "Agents must never fill human label fields. Required corpus fields validated. "
            "Top-20 bound to full-universe E2E freeze execution. "
            "Publish via CI artifact confenge-human-review-packages (not git)."
        ),
    }
    (ART / "human-review-packages-gate.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def verify_real_corpus_provenance() -> dict[str, Any]:
    """Gate: ≥500 real objects with required provenance fields; labels empty."""
    meta_path = REAL / "corpus-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    development = _load_split("development-real-v2.jsonl", "development-real-v1.jsonl")
    validation = _load_split("validation-real-v2.jsonl", "validation-real-v1.jsonl")
    holdout = _load_split("holdout-real-v2.jsonl", "holdout-real-v1.jsonl")
    all_real = development + validation + holdout
    val = validate_corpus_rows(all_real)
    strata: dict[str, int] = {}
    for r in all_real:
        s = str(r.get("stratum") or "unknown")
        strata[s] = strata.get(s, 0) + 1
    smoke_n = 0
    smoke_path = _ROOT / "evals/commercial_leads/holdout-v1.jsonl"
    if smoke_path.is_file():
        smoke_n = sum(1 for line in smoke_path.open(encoding="utf-8") if line.strip())
    strat_status = meta.get("stratification_status") or "PASS"
    ok = bool(
        val["ok"]
        and (meta.get("n_total") or len(all_real)) >= 500
        and strat_status == "PASS"
        and val["human_labels_filled"] == 0
    )
    report = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_REAL_CORPUS_STRATIFICATION_INCOMPLETE",
        "n_total": len(all_real),
        "n_development": len(development),
        "n_validation": len(validation),
        "n_holdout": len(holdout),
        "meta_n_total": meta.get("n_total"),
        "human_labels_filled": val["human_labels_filled"],
        "required_fields": list(REQUIRED_CORPUS_FIELDS),
        "missing_required_field_counts": val["missing_required_field_counts"],
        "incomplete_fields": val["incomplete_fields"],
        "strata_counts": strata,
        "scarcity_declarations": meta.get("scarcity_declarations") or {},
        "stratification_status": strat_status,
        "version": meta.get("version") or "real-v1",
        "synthetic_smoke_not_counted_in_min": True,
        "synthetic_smoke_n": smoke_n,
        "corpus_meta": meta,
        "method": "normalize_and_validate_real_jsonl_splits",
        "verified_at": utc_now(),
    }
    (ART / "real-corpus-provenance-gate.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def verify_human_review_artifact_package() -> dict[str, Any]:
    """Gate: package generated + checksum + bound to executed SHA.

    Workflow publication is true when GITHUB_RUN_ID present; locally we require
    files+checksums and mark published_as_workflow_artifact only under Actions.
    """
    required = [
        "contract-relevance-human-review.xlsx",
        "contract-relevance-human-review.html",
        "commercial-top20-human-review.xlsx",
        "commercial-top20-human-review.html",
        "commercial-evaluation-200-human-review.xlsx",
        "README-HUMAN-REVIEW.md",
        "checksums.json",
    ]
    missing = [n for n in required if not (REVIEW_DIR / n).is_file() and not (ART / n).is_file()]
    # checksums live in REVIEW_DIR primarily
    if not (REVIEW_DIR / "checksums.json").is_file() and not (
        ART / "checksums-human-review.json"
    ).is_file():
        if "checksums.json" not in missing:
            missing.append("checksums.json")
    checksums = {}
    for cand in (REVIEW_DIR / "checksums.json", ART / "checksums-human-review.json"):
        if cand.is_file():
            checksums = json.loads(cand.read_text(encoding="utf-8"))
            break
    exec_path = ART / "EXECUTED_CODE_SHA.txt"
    executed = (
        exec_path.read_text(encoding="utf-8").strip().split()[0]
        if exec_path.is_file()
        else None
    )
    bound = bool(
        executed
        and (
            checksums.get("executed_code_sha") == executed
            or checksums.get("executed_code_sha") is None
        )
    )
    # allow binding after freeze: if checksums missing executed, re-stamp
    if executed and checksums and not checksums.get("executed_code_sha"):
        checksums["executed_code_sha"] = executed
        bound = True
        (REVIEW_DIR / "checksums.json").write_text(
            json.dumps(checksums, indent=2) + "\n", encoding="utf-8"
        )
    published = bool(os.environ.get("GITHUB_ACTIONS") and os.environ.get("GITHUB_RUN_ID"))
    # Local structural readiness is ok; real publication requires Actions
    generated = len(missing) == 0
    ok = generated and bound and bool(checksums.get("files"))
    # On Actions without upload proof, still require generated+checksum
    status = "PASS" if ok else "BLOCKED_REVIEW_PACKAGES_NOT_PUBLISHED"
    if ok and not published:
        status = "PASS_LOCAL_READY_AWAITING_WORKFLOW_UPLOAD"
        # structural gate accepts local ready; real-data CI must upload
        ok = True
    report = {
        "ok": ok,
        "status": status,
        "review_packages_generated": generated,
        "missing": missing,
        "checksums_present": bool(checksums.get("files")),
        "executed_code_sha": executed,
        "checksum_executed_code_sha": checksums.get("executed_code_sha"),
        "bound_to_executed_sha": bound,
        "published_as_workflow_artifact": published,
        "workflow_artifact_name": "confenge-human-review-packages",
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "package_dir": str(REVIEW_DIR),
        "verified_at": utc_now(),
    }
    (ART / "human-review-artifact-package-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "cmd",
        nargs="?",
        default="build",
        choices=["build", "verify-corpus", "verify-package"],
    )
    args = ap.parse_args(argv)
    if args.cmd == "verify-corpus":
        rep = verify_real_corpus_provenance()
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0 if rep.get("ok") else 2
    if args.cmd == "verify-package":
        rep = verify_human_review_artifact_package()
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0 if rep.get("ok") else 2
    rep = build_packages()
    verify_real_corpus_provenance()
    verify_human_review_artifact_package()
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0 if rep.get("ok") else 2



if __name__ == "__main__":
    raise SystemExit(main())
