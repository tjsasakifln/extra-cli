"""Consultative investigation dossier (JSON + HTML) from linkage run."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_dossier(
    investigation: dict[str, Any],
    *,
    metrics: dict[str, Any] | None = None,
    universe: dict[str, Any] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    inv = investigation or {}
    opp = inv.get("opportunity") or {}
    return {
        "title": "Dossiê de investigação — linkage canônico",
        "campaign_id": "CANONICAL-ENTITY-LINKAGE-01",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": inv.get("run_id"),
        "opportunity_id": inv.get("opportunity_id"),
        "universe": universe
        or {
            "note": "Isolated snapshot + open opportunities in linkage RC DB",
        },
        "cut": {
            "opportunity": {
                "id": opp.get("id"),
                "orgao_cnpj": opp.get("orgao_cnpj"),
                "orgao_nome": opp.get("orgao_nome"),
                "objeto": opp.get("objeto"),
                "uf": opp.get("uf"),
                "numero_controle_pncp": opp.get("numero_controle_pncp"),
            }
        },
        "sources": [
            "opportunity_intel",
            "pncp_supplier_contracts",
            "canonical_organs",
            "canonical_suppliers",
            "opportunity_organ_links",
            "opportunity_contract_links",
            "observed_supplier_relations",
        ],
        "lineage": {
            "organs": inv.get("organs") or [],
            "contracts": inv.get("contracts") or [],
            "observed_suppliers": inv.get("observed_suppliers") or [],
        },
        "quality": metrics or {},
        "status": inv.get("status"),
        "claims": [c for c in (inv.get("claims") or []) if c],
        "non_claims": inv.get("non_claims")
        or [
            "not_observed_participant_of_open_tender",
            "similarity_is_not_participation",
        ],
        "limitations": limitations
        or [
            "Links to historical contracts mean shared organ (and optional object tokens), not that the supplier bid on the open tender.",
            "Heuristic name-only merges are never auto-accepted.",
            "Coverage dual metrics are independent of this identity graph (ADR-030).",
        ],
    }


def write_dossier(
    dossier: dict[str, Any],
    out_dir: str | Path,
    *,
    stem: str = "operational-report",
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{stem}.json"
    html_path = out / f"{stem}.html"
    csv_path = out / f"{stem}-suppliers.csv"

    json_path.write_text(json.dumps(dossier, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # CSV of observed suppliers
    lines = ["supplier_canonical_key,relation_kind,classification,score,contract_id,claim_level"]
    for s in dossier.get("lineage", {}).get("observed_suppliers") or []:
        lines.append(
            ",".join(
                [
                    str(s.get("supplier_canonical_key") or ""),
                    str(s.get("relation_kind") or ""),
                    str(s.get("classification") or ""),
                    str(s.get("score") or ""),
                    str(s.get("contract_id") or ""),
                    str(s.get("claim_level") or ""),
                ]
            )
        )
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    html_path.write_text(_render_html(dossier), encoding="utf-8")
    return {
        "json": str(json_path),
        "html": str(html_path),
        "csv": str(csv_path),
    }


def _render_html(d: dict[str, Any]) -> str:
    def esc(x: Any) -> str:
        return html.escape(str(x if x is not None else ""))

    opp = (d.get("cut") or {}).get("opportunity") or {}
    organs = d.get("lineage", {}).get("organs") or []
    contracts = d.get("lineage", {}).get("contracts") or []
    suppliers = d.get("lineage", {}).get("observed_suppliers") or []

    rows_c = "".join(
        f"<tr><td>{esc(c.get('contract_id'))}</td><td>{esc(c.get('classification'))}</td>"
        f"<td>{esc(c.get('score'))}</td><td>{esc(c.get('claim_level'))}</td>"
        f"<td>{esc(','.join(c.get('reason_codes') or []))}</td></tr>"
        for c in contracts[:50]
    )
    rows_s = "".join(
        f"<tr><td>{esc(s.get('supplier_canonical_key'))}</td><td>{esc(s.get('relation_kind'))}</td>"
        f"<td>{esc(s.get('classification'))}</td><td>{esc(s.get('score'))}</td>"
        f"<td>{esc(s.get('contract_id'))}</td></tr>"
        for s in suppliers[:50]
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<title>{esc(d.get("title"))}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #122; }}
h1,h2 {{ color: #0b3d5c; }}
.badge {{ display:inline-block; padding:0.15rem 0.5rem; border-radius:4px; background:#e8f1f8; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th,td {{ border: 1px solid #ccd; padding: 0.4rem 0.6rem; text-align: left; font-size: 0.9rem; }}
th {{ background: #f0f4f8; }}
.nonclaim {{ color: #844; }}
.meta {{ color: #456; font-size: 0.9rem; }}
</style>
</head>
<body>
<h1>{esc(d.get("title"))}</h1>
<p class="meta">Campaign <span class="badge">{esc(d.get("campaign_id"))}</span>
 · run_id <code>{esc(d.get("run_id"))}</code>
 · status <strong>{esc(d.get("status"))}</strong>
 · {esc(d.get("generated_at"))}</p>

<h2>Oportunidade</h2>
<ul>
<li>ID: {esc(opp.get("id"))}</li>
<li>Órgão: {esc(opp.get("orgao_nome"))} ({esc(opp.get("orgao_cnpj"))})</li>
<li>PNCP: {esc(opp.get("numero_controle_pncp"))}</li>
<li>UF: {esc(opp.get("uf"))}</li>
<li>Objeto: {esc(opp.get("objeto"))}</li>
</ul>

<h2>Órgãos resolvidos ({len(organs)})</h2>
<pre>{esc(json.dumps(organs, ensure_ascii=False, indent=2, default=str)[:4000])}</pre>

<h2>Contratos históricos relacionados ({len(contracts)})</h2>
<table>
<thead><tr><th>contrato_id</th><th>class</th><th>score</th><th>claim</th><th>reasons</th></tr></thead>
<tbody>{rows_c or "<tr><td colspan=5>Nenhum</td></tr>"}</tbody>
</table>

<h2>Fornecedores observados (vencedores históricos) ({len(suppliers)})</h2>
<table>
<thead><tr><th>supplier</th><th>relation</th><th>class</th><th>score</th><th>contract</th></tr></thead>
<tbody>{rows_s or "<tr><td colspan=5>Nenhum</td></tr>"}</tbody>
</table>

<h2>Claims</h2>
<ul>{"".join(f"<li>{esc(c)}</li>" for c in (d.get("claims") or []) or ["—"])}</ul>

<h2 class="nonclaim">Non-claims</h2>
<ul class="nonclaim">{"".join(f"<li>{esc(c)}</li>" for c in (d.get("non_claims") or []))}</ul>

<h2>Limitações</h2>
<ul>{"".join(f"<li>{esc(c)}</li>" for c in (d.get("limitations") or []))}</ul>

<h2>Qualidade (métricas do run)</h2>
<pre>{esc(json.dumps(d.get("quality") or {}, ensure_ascii=False, indent=2, default=str)[:5000])}</pre>
</body>
</html>
"""
