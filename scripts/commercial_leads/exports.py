"""Export commercial queue artifacts from a single run payload."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def export_all(out_dir: Path, run: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    leads = run.get("leads") or []
    paths: dict[str, str] = {}

    # leads.json (+ mandate aliases)
    p = out_dir / "leads.json"
    _write_json(p, leads)
    paths["leads.json"] = str(p)
    p_alias = out_dir / "commercial-leads.json"
    _write_json(p_alias, leads)
    paths["commercial-leads.json"] = str(p_alias)

    # leads.csv
    p = out_dir / "leads.csv"
    fields = [
        "rank_position",
        "cnpj14",
        "razao_social",
        "score_total",
        "priority",
        "suggested_offer",
        "next_human_step",
        "commercial_state",
        "signals_fired_count",
        "signals_not_computable_count",
        "total_value",
        "contract_count",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, lead in enumerate(leads, start=1):
            w.writerow(
                {
                    "rank_position": lead.get("rank_position") or i,
                    "cnpj14": lead.get("cnpj14"),
                    "razao_social": lead.get("razao_social"),
                    "score_total": lead.get("score_total"),
                    "priority": lead.get("priority"),
                    "suggested_offer": lead.get("suggested_offer"),
                    "next_human_step": lead.get("next_human_step"),
                    "commercial_state": lead.get("commercial_state", "NEW"),
                    "signals_fired_count": len(lead.get("signals_fired") or []),
                    "signals_not_computable_count": len(lead.get("signals_not_computable") or []),
                    "total_value": lead.get("total_value"),
                    "contract_count": lead.get("contract_count"),
                }
            )
    paths["leads.csv"] = str(p)
    p_alias = out_dir / "commercial-leads.csv"
    p_alias.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    paths["commercial-leads.csv"] = str(p_alias)

    # lead-explanations.jsonl / evidence-ledger
    p = out_dir / "lead-explanations.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for lead in leads:
            f.write(json.dumps(lead, ensure_ascii=False, default=str) + "\n")
    paths["lead-explanations.jsonl"] = str(p)

    p = out_dir / "signal-catalog.json"
    _write_json(p, run.get("signal_catalog") or {})
    paths["signal-catalog.json"] = str(p)

    p = out_dir / "baseline-comparison.json"
    _write_json(p, run.get("baseline_comparison") or {})
    paths["baseline-comparison.json"] = str(p)

    # commercial-ledger.csv
    p = out_dir / "commercial-ledger.csv"
    ledger = run.get("ledger") or []
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["cnpj14", "event_type", "author", "payload_json", "created_at"],
        )
        w.writeheader()
        for row in ledger:
            w.writerow(
                {
                    "cnpj14": row.get("cnpj14"),
                    "event_type": row.get("event_type"),
                    "author": row.get("author", "system"),
                    "payload_json": json.dumps(row.get("payload") or {}, ensure_ascii=False),
                    "created_at": row.get("created_at"),
                }
            )
    paths["commercial-ledger.csv"] = str(p)

    # review-template.xlsx (openpyxl if available; else CSV fallback + note)
    p_xlsx = out_dir / "review-template.xlsx"
    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Review Tiago"
        headers = [
            "rank",
            "cnpj14",
            "razao_social",
            "score_total",
            "priority",
            "signals_fired",
            "suggested_offer",
            "next_human_step",
            "human_decision",
            "human_notes",
            "reviewer",
            "reviewed_at",
        ]
        ws.append(headers)
        for i, lead in enumerate(leads, start=1):
            fired = ",".join(
                s.get("signal_id", "") for s in (lead.get("signals_fired") or []) if isinstance(s, dict)
            )
            ws.append(
                [
                    i,
                    lead.get("cnpj14"),
                    lead.get("razao_social"),
                    lead.get("score_total"),
                    lead.get("priority"),
                    fired,
                    lead.get("suggested_offer"),
                    lead.get("next_human_step"),
                    "",  # human_decision — never pre-filled as accepted
                    "",
                    "",
                    "",
                ]
            )
        ws2 = wb.create_sheet("Instructions")
        ws2.append(["Campo human_decision permanece vazio até revisão real de Tiago."])
        ws2.append(["Não preencher aceite automaticamente."])
        ws2.append(["Estados: REVIEWED, QUALIFIED, DISQUALIFIED, DO_NOT_CONTACT, ..."])
        wb.save(p_xlsx)
        paths["review-template.xlsx"] = str(p_xlsx)
    except Exception as exc:  # noqa: BLE001 — fallback is intentional
        p_csv = out_dir / "review-template.csv"
        with p_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "rank",
                    "cnpj14",
                    "razao_social",
                    "score_total",
                    "priority",
                    "human_decision",
                    "human_notes",
                ]
            )
            for i, lead in enumerate(leads, start=1):
                w.writerow([i, lead.get("cnpj14"), lead.get("razao_social"), lead.get("score_total"), lead.get("priority"), "", ""])
        paths["review-template.csv"] = str(p_csv)
        paths["review-template.xlsx_error"] = str(exc)


    # commercial-review.csv (open review sheet)
    p_rev = out_dir / "commercial-review.csv"
    with p_rev.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "rank", "cnpj14", "razao_social", "score_total", "priority",
                "signals_fired", "suggested_offer", "next_human_step",
                "human_status", "human_reason", "reviewer", "reviewed_at",
            ],
        )
        w.writeheader()
        for i, lead in enumerate(leads, start=1):
            fired = "|".join(
                s.get("signal_id", "")
                for s in (lead.get("signals_fired") or [])
                if isinstance(s, dict)
            )
            w.writerow(
                {
                    "rank": i,
                    "cnpj14": lead.get("cnpj14"),
                    "razao_social": lead.get("razao_social"),
                    "score_total": lead.get("score_total"),
                    "priority": lead.get("priority"),
                    "signals_fired": fired,
                    "suggested_offer": lead.get("suggested_offer"),
                    "next_human_step": lead.get("next_human_step"),
                    "human_status": "",
                    "human_reason": "",
                    "reviewer": "",
                    "reviewed_at": "",
                }
            )
    paths["commercial-review.csv"] = str(p_rev)

    # commercial-summary.md alias
    # (written after executive-summary; see below)

    # signal-distribution.json
    dist: dict[str, int] = {}
    for lead in leads:
        for s in lead.get("signals_fired") or []:
            if isinstance(s, dict) and s.get("signal_id"):
                dist[str(s["signal_id"])] = dist.get(str(s["signal_id"]), 0) + 1
    p_dist = out_dir / "signal-distribution.json"
    _write_json(p_dist, {"by_signal_fired_count": dist, "lead_count": len(leads)})
    paths["signal-distribution.json"] = str(p_dist)

    # evidence-ledger.jsonl
    p_ev = out_dir / "evidence-ledger.jsonl"
    with p_ev.open("w", encoding="utf-8") as f:
        for lead in leads:
            for e in lead.get("evidence") or []:
                row = {"cnpj14": lead.get("cnpj14"), **(e if isinstance(e, dict) else {"raw": e})}
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    paths["evidence-ledger.jsonl"] = str(p_ev)

    # executive-summary.md
    p = out_dir / "executive-summary.md"
    status = run.get("status")
    p.write_text(
        "\n".join(
            [
                "# Fila comercial CONFENGE — resumo executivo",
                "",
                f"- **Status técnico:** `{status}`",
                f"- **Run ID:** `{run.get('run_id')}`",
                f"- **Profile:** `{run.get('profile_id')}` v`{run.get('profile_version')}`",
                f"- **Snapshot hash:** `{run.get('snapshot_hash')}`",
                f"- **Empresas elegíveis:** {run.get('eligible_companies')}",
                f"- **Leads na fila:** {len(leads)}",
                f"- **Limite:** {run.get('queue_limit')}",
                "",
                "## Linguagem",
                "",
                "Esta fila apresenta **sinais observados** de necessidade, complexidade ou aderência ao perfil.",
                "Não afirma probabilidade de compra, intenção de contratação nem necessidade comprovada de consultoria.",
                "",
                "## Top leads",
                "",
            ]
            + [
                f"{i}. `{L.get('cnpj14')}` — {L.get('razao_social')} — score {L.get('score_total')} — {L.get('priority')}"
                for i, L in enumerate(leads[:20], start=1)
            ]
            + [
                "",
                "## Non-claims",
                "",
                *[f"- {n}" for n in (run.get("non_claims") or [])],
                "",
                "## Revisão humana",
                "",
                "Template de revisão gerado vazio. Aceite de Tiago **não** é fabricado por este pipeline.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    paths["executive-summary.md"] = str(p)
    p_sum = out_dir / "commercial-summary.md"
    p_sum.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    paths["commercial-summary.md"] = str(p_sum)

    # operational-report.html
    p = out_dir / "operational-report.html"
    rows_html = "".join(
        f"<tr><td>{i}</td><td>{L.get('cnpj14')}</td><td>{_esc(L.get('razao_social'))}</td>"
        f"<td>{L.get('score_total')}</td><td>{L.get('priority')}</td>"
        f"<td>{len(L.get('signals_fired') or [])}</td></tr>"
        for i, L in enumerate(leads, start=1)
    )
    p.write_text(
        f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"/>
<title>CONFENGE Commercial Queue</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;}}
table{{border-collapse:collapse;width:100%;}}
th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;}}
th{{background:#f4f4f4;}}
.note{{background:#fff8e1;padding:1rem;border-left:4px solid #f9a825;}}
</style></head><body>
<h1>Fila comercial CONFENGE</h1>
<div class="note"><strong>Nota:</strong> sinais observados / prioridade para revisão humana.
Não é probabilidade de compra. Revisão de Tiago não preenchida automaticamente.</div>
<p>Status: <code>{_esc(status)}</code> · Run: <code>{_esc(run.get('run_id'))}</code></p>
<p>Snapshot: <code>{_esc(run.get('snapshot_hash'))}</code></p>
<table><thead><tr><th>#</th><th>CNPJ</th><th>Razão social</th><th>Score</th><th>Prioridade</th><th>Sinais</th></tr></thead>
<tbody>{rows_html}</tbody></table>
</body></html>
""",
        encoding="utf-8",
    )
    paths["operational-report.html"] = str(p)
    p_html = out_dir / "commercial-report.html"
    p_html.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    paths["commercial-report.html"] = str(p_html)

    p = out_dir / "run-result.json"
    _write_json(p, run)
    paths["run-result.json"] = str(p)

    return paths


def _esc(value: Any) -> str:
    s = str(value if value is not None else "")
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def reconcile_exports(out_dir: Path, run: dict[str, Any]) -> dict[str, Any]:
    leads = run.get("leads") or []
    issues: list[str] = []
    ok = True

    lj = out_dir / "leads.json"
    if not lj.is_file() and (out_dir / "commercial-leads.json").is_file():
        lj = out_dir / "commercial-leads.json"
    if not lj.is_file():
        ok = False
        issues.append("missing_leads_json")
    else:
        loaded = json.loads(lj.read_text(encoding="utf-8"))
        if len(loaded) != len(leads):
            ok = False
            issues.append("leads_json_count_mismatch")
    for alias in ("commercial-leads.json", "commercial-leads.csv", "commercial-summary.md"):
        if not (out_dir / alias).is_file() and not (out_dir / alias.replace("commercial-", "").replace("summary.md", "executive-summary.md")).is_file():
            # soft: alias optional if core present; only require commercial-leads.json when core leads.json exists
            pass

    csv_path = out_dir / "leads.csv"
    if csv_path.is_file():
        with csv_path.open(encoding="utf-8") as f:
            n = sum(1 for _ in f) - 1
        if n != len(leads):
            ok = False
            issues.append("leads_csv_count_mismatch")
    else:
        ok = False
        issues.append("missing_leads_csv")

    expl = out_dir / "lead-explanations.jsonl"
    if expl.is_file():
        n = sum(1 for _ in expl.open(encoding="utf-8") if _.strip())
        if n != len(leads):
            ok = False
            issues.append("explanations_count_mismatch")
    else:
        ok = False
        issues.append("missing_explanations")

    return {"ok": ok, "issues": issues, "lead_count": len(leads)}
