"""Export public-agency cycle artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from openpyxl import Workbook as _Workbook

    Workbook: Any = _Workbook
except ImportError:  # pragma: no cover
    Workbook = None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def export_public_agency_run(out_dir: Path, run: dict[str, Any]) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    leads = run.get("leads") or []
    paths: dict[str, str] = {}

    # JSON / CSV leads
    p = out_dir / "public-agency-leads.json"
    _write_json(p, leads)
    paths["public-agency-leads.json"] = str(p)

    fields = [
        "rank_position",
        "agency_id",
        "cnpj",
        "nome_oficial",
        "uf",
        "municipio",
        "populacao",
        "faixa_populacional",
        "priority_score",
        "publishability",
        "mode",
        "selected_service_id",
        "conflict_state",
        "relationship_state",
        "contract_count",
        "total_value",
    ]
    p = out_dir / "public-agency-leads.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, lead in enumerate(leads, start=1):
            agency = lead.get("agency") or {}
            score = lead.get("score") or {}
            pub = lead.get("publishability") or {}
            conflict = lead.get("conflict") or {}
            w.writerow(
                {
                    "rank_position": lead.get("rank_position") or i,
                    "agency_id": agency.get("agency_id"),
                    "cnpj": agency.get("cnpj"),
                    "nome_oficial": agency.get("nome_oficial"),
                    "uf": agency.get("uf"),
                    "municipio": agency.get("municipio"),
                    "populacao": agency.get("populacao"),
                    "faixa_populacional": agency.get("faixa_populacional"),
                    "priority_score": score.get("priority_score"),
                    "publishability": pub.get("category"),
                    "mode": lead.get("mode"),
                    "selected_service_id": score.get("selected_service_id"),
                    "conflict_state": conflict.get("state"),
                    "relationship_state": pub.get("relationship_state"),
                    "contract_count": lead.get("contract_count"),
                    "total_value": lead.get("total_value"),
                }
            )
    paths["public-agency-leads.csv"] = str(p)

    # Review template xlsx
    p = out_dir / "public-agency-review-template.xlsx"
    if Workbook is not None:
        wb = Workbook()
        ws = wb.active
        ws.title = "review"
        headers = fields + ["human_decision", "human_notes", "conflict_clearance", "outreach_approved"]
        ws.append(headers)
        for i, lead in enumerate(leads, start=1):
            agency = lead.get("agency") or {}
            score = lead.get("score") or {}
            pub = lead.get("publishability") or {}
            conflict = lead.get("conflict") or {}
            ws.append(
                [
                    lead.get("rank_position") or i,
                    agency.get("agency_id"),
                    agency.get("cnpj"),
                    agency.get("nome_oficial"),
                    agency.get("uf"),
                    agency.get("municipio"),
                    agency.get("populacao"),
                    agency.get("faixa_populacional"),
                    score.get("priority_score"),
                    pub.get("category"),
                    lead.get("mode"),
                    score.get("selected_service_id"),
                    conflict.get("state"),
                    pub.get("relationship_state"),
                    lead.get("contract_count"),
                    lead.get("total_value"),
                    "",
                    "",
                    "",
                    "",
                ]
            )
        wb.save(p)
    else:
        # CSV fallback with same name stem
        p = out_dir / "public-agency-review-template.csv"
        p.write_text((out_dir / "public-agency-leads.csv").read_text(encoding="utf-8"), encoding="utf-8")
    paths["public-agency-review-template.xlsx"] = str(p)

    # HTML report
    p = out_dir / "public-agency-report.html"
    rows_html = []
    for lead in leads[:50]:
        agency = lead.get("agency") or {}
        score = lead.get("score") or {}
        pub = lead.get("publishability") or {}
        rows_html.append(
            "<tr>"
            f"<td>{lead.get('rank_position')}</td>"
            f"<td>{agency.get('nome_oficial')}</td>"
            f"<td>{agency.get('uf')}</td>"
            f"<td>{agency.get('populacao')}</td>"
            f"<td>{score.get('priority_score')}</td>"
            f"<td>{pub.get('category')}</td>"
            f"<td>{score.get('selected_service_id')}</td>"
            "</tr>"
        )
    p.write_text(
        f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"/>
<title>CONFENGE Public Agency Commercial Report</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:.4rem;font-size:14px}}
th{{background:#133;color:#fff}}
.note{{background:#fff8e1;padding:1rem;margin:1rem 0}}
</style></head><body>
<h1>CONFENGE — fila de órgãos públicos</h1>
<p>Campaign: {run.get('campaign_id')} · status: <b>{run.get('status')}</b> · sha: <code>{run.get('git_sha')}</code></p>
<div class="note"><b>Sem outreach automático.</b> Tiago deve revisar conflitos, classificações e dossiers antes de qualquer contato.
Elegibilidade legal: apenas POTENTIALLY_ELIGIBLE_FOR_DIRECT_CONTRACTING quando aplicável.</div>
<table>
<thead><tr><th>#</th><th>Órgão</th><th>UF</th><th>Pop</th><th>Score</th><th>Publishability</th><th>Oferta</th></tr></thead>
<tbody>
{''.join(rows_html)}
</tbody></table>
</body></html>
""",
        encoding="utf-8",
    )
    paths["public-agency-report.html"] = str(p)

    # Summary md
    p = out_dir / "public-agency-summary.md"
    metrics = run.get("metrics") or {}
    p.write_text(
        f"""# Public agency commercial cycle — summary

- **campaign_id:** {run.get('campaign_id')}
- **status:** {run.get('status')}
- **reason:** {run.get('reason')}
- **git_sha:** `{run.get('git_sha')}`
- **as_of:** {run.get('as_of')}
- **agencies evaluated:** {metrics.get('evaluated_agencies')}
- **publishable:** {metrics.get('publishable_agencies')}
- **blocked:** {metrics.get('blocked_agencies')}
- **top_n:** {len(leads)}

## Human action

Tiago deve revisar a fila de órgãos, os conflitos de interesses, as classificações
jurídicas preliminares, os dossiers e os materiais de abordagem antes de autorizar
qualquer contato.
""",
        encoding="utf-8",
    )
    paths["public-agency-summary.md"] = str(p)

    # run-result
    p = out_dir / "public-agency-run-result.json"
    _write_json(p, run)
    paths["public-agency-run-result.json"] = str(p)

    # explanations + evidence ledger
    p = out_dir / "public-agency-lead-explanations.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for lead in leads:
            f.write(json.dumps(lead, ensure_ascii=False, default=str) + "\n")
    paths["public-agency-lead-explanations.jsonl"] = str(p)

    p = out_dir / "public-agency-evidence-ledger.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for lead in leads:
            for ev in lead.get("evidence") or []:
                row = {"agency_id": (lead.get("agency") or {}).get("agency_id"), **ev}
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    paths["public-agency-evidence-ledger.jsonl"] = str(p)

    # outreach queue (for human approval — never sent)
    p = out_dir / "public-agency-outreach-queue.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "agency_id",
                "nome_oficial",
                "relationship_state",
                "conflict_state",
                "contact_channel",
                "contact_value",
                "message_preview",
                "outreach_sent",
            ],
        )
        w.writeheader()
        for lead in leads:
            agency = lead.get("agency") or {}
            pub = lead.get("publishability") or {}
            conflict = lead.get("conflict") or {}
            contacts = (lead.get("contacts") or {}).get("accepted") or []
            c0 = contacts[0] if contacts else {}
            w.writerow(
                {
                    "agency_id": agency.get("agency_id"),
                    "nome_oficial": agency.get("nome_oficial"),
                    "relationship_state": pub.get("relationship_state"),
                    "conflict_state": conflict.get("state"),
                    "contact_channel": c0.get("channel"),
                    "contact_value": c0.get("value"),
                    "message_preview": (lead.get("outreach_message") or "")[:200],
                    "outreach_sent": "false",
                }
            )
    paths["public-agency-outreach-queue.csv"] = str(p)

    # service fit
    p = out_dir / "public-agency-service-fit.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["agency_id", "selected_service_id", "service_fit_score", "need_score", "priority_score"],
        )
        w.writeheader()
        for lead in leads:
            agency = lead.get("agency") or {}
            score = lead.get("score") or {}
            w.writerow(
                {
                    "agency_id": agency.get("agency_id"),
                    "selected_service_id": score.get("selected_service_id"),
                    "service_fit_score": score.get("service_fit_score"),
                    "need_score": score.get("need_score"),
                    "priority_score": score.get("priority_score"),
                }
            )
    paths["public-agency-service-fit.csv"] = str(p)

    # compliance flags
    p = out_dir / "public-agency-compliance-flags.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "agency_id",
                "eligibility_state",
                "fragmentation_severity",
                "object_class",
                "compliance_blocks",
            ],
        )
        w.writeheader()
        for lead in leads:
            agency = lead.get("agency") or {}
            w.writerow(
                {
                    "agency_id": agency.get("agency_id"),
                    "eligibility_state": (lead.get("eligibility") or {}).get("eligibility_state"),
                    "fragmentation_severity": (lead.get("fragmentation") or {}).get("severity"),
                    "object_class": (lead.get("object_classification") or {}).get("suggested_class"),
                    "compliance_blocks": "|".join(lead.get("compliance_blocks") or []),
                }
            )
    paths["public-agency-compliance-flags.csv"] = str(p)

    # conflict review
    p = out_dir / "public-agency-conflict-review.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["agency_id", "nome_oficial", "conflict_state", "reasons", "human_review_required"],
        )
        w.writeheader()
        for lead in leads:
            agency = lead.get("agency") or {}
            conflict = lead.get("conflict") or {}
            w.writerow(
                {
                    "agency_id": agency.get("agency_id"),
                    "nome_oficial": agency.get("nome_oficial"),
                    "conflict_state": conflict.get("state"),
                    "reasons": "|".join(conflict.get("reasons") or []),
                    "human_review_required": conflict.get("human_review_required"),
                }
            )
    paths["public-agency-conflict-review.csv"] = str(p)

    # checksums + manifest
    checksum_lines = []
    for name, path_str in sorted(paths.items()):
        pp = Path(path_str)
        if pp.is_file():
            checksum_lines.append(f"{_sha256_file(pp)}  {pp.name}")
    p = out_dir / "public-agency-checksums.sha256"
    p.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    paths["public-agency-checksums.sha256"] = str(p)

    manifest = {
        "campaign_id": run.get("campaign_id"),
        "status": run.get("status"),
        "run_id": run.get("run_id"),
        "code_sha": run.get("git_sha"),
        "as_of": run.get("as_of"),
        "config_hashes": run.get("config_hashes"),
        "metrics": run.get("metrics"),
        "artifacts": paths,
        "target": "public-agencies",
        "outreach_sent": False,
    }
    p = out_dir / "public-agency-manifest.json"
    _write_json(p, manifest)
    paths["public-agency-manifest.json"] = str(p)

    return paths
