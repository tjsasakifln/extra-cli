"""Tiago review package builder — one row per supplier, no outreach sent."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.commercial.reajuste_14133 import (
    DOCUMENT_REQUEST_CANDIDATE,
    OUTREACH_READY,
    TECHNICALLY_VERIFIED_PENDING_TIAGO,
    TERMINAL_BLOCKED_INSUFFICIENT,
)
from scripts.commercial.reajuste_14133.domain.outreach import exploratory_message

TIAGO_DECISIONS = ("ACCEPT", "REJECT", "DEFER")

QUEUE_COLUMNS = [
    "empresa",
    "cnpj",
    "contrato_principal",
    "demais_contratos",
    "objeto",
    "orgao",
    "valor_validado",
    "vigencia_inicio",
    "vigencia_fim",
    "regime",
    "clausula",
    "data_base",
    "data_base_state",
    "indice",
    "paginas_e_trechos",
    "historico_reajuste",
    "contato_email",
    "contato_telefone",
    "contato_site",
    "contato_fonte",
    "contato_data_consulta",
    "contato_verificavel",
    "riscos",
    "mensagem_exploratoria_sugerida",
    "decisao_sugerida",
    "tiago_decision",
    "outreach_status",
    "document_link_status",
    "score",
    "sede_uf",
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(  # noqa: S603
                ["git", "rev-parse", "HEAD"],  # noqa: S607
                stderr=subprocess.DEVNULL,
                text=True,
            )
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def supplier_row(portfolio: dict[str, Any], *, deepen: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one Tiago queue row from portfolio + optional deepen evidence."""
    best = dict(portfolio.get("melhor_oportunidade") or {})
    deepen = deepen or {}
    contratos = portfolio.get("contratos") or []
    demais = [
        c.get("contrato_id")
        for c in contratos
        if c.get("contrato_id") and c.get("contrato_id") != best.get("contrato_id")
    ]
    contatos = portfolio.get("contatos") or {}
    exact = deepen.get("exact_data_base") or best.get("exact_data_base") or {}
    primary = (exact.get("primary") if isinstance(exact, dict) else None) or {}
    idx_formula = deepen.get("index_formula") or best.get("index_formula") or {}
    pages = []
    if primary.get("page_or_cell"):
        pages.append(f"data-base p/cell={primary.get('page_or_cell')}: {primary.get('excerpt', '')[:120]}")
    if idx_formula.get("page"):
        pages.append(f"indice p={idx_formula.get('page')}: {idx_formula.get('indices')}")
    for e in deepen.get("evidences") or []:
        if isinstance(e, dict) and e.get("page"):
            pages.append(f"{e.get('field_found')} p={e.get('page')}: {(e.get('excerpt') or '')[:80]}")

    status = deepen.get("outreach_status") or portfolio.get("outreach_status")
    suggested = "DEFER"
    if status == TECHNICALLY_VERIFIED_PENDING_TIAGO:
        suggested = "ACCEPT"
    elif status == DOCUMENT_REQUEST_CANDIDATE:
        suggested = "DEFER"
    elif status == OUTREACH_READY:
        suggested = "ACCEPT"  # should not happen without Tiago; still empty for Tiago
    else:
        suggested = "REJECT" if deepen.get("false_positive") else "DEFER"

    return {
        "empresa": portfolio.get("razao_social") or deepen.get("razao_social"),
        "cnpj": portfolio.get("cnpj") or deepen.get("cnpj"),
        "contrato_principal": best.get("contrato_id") or deepen.get("contrato_id"),
        "demais_contratos": " | ".join(str(x) for x in demais[:12] if x),
        "objeto": best.get("objeto") or deepen.get("objeto"),
        "orgao": best.get("orgao_contratante") or deepen.get("orgao"),
        "valor_validado": best.get("valor_original") or best.get("valor_total") or deepen.get("valor"),
        "vigencia_inicio": best.get("data_inicio") or best.get("inicio_vigencia"),
        "vigencia_fim": best.get("data_fim") or best.get("fim_vigencia"),
        "regime": best.get("regime_legal") or deepen.get("regime"),
        "clausula": deepen.get("clausula_excerpt")
        or ("localizada" if deepen.get("clause_located") else best.get("clausula")),
        "data_base": primary.get("value") or best.get("data_base") or deepen.get("data_base"),
        "data_base_state": (exact.get("state") if isinstance(exact, dict) else None)
        or best.get("data_base_status"),
        "indice": (
            ", ".join(idx_formula.get("indices") or [])
            if isinstance(idx_formula, dict)
            else None
        )
        or best.get("indice")
        or deepen.get("indice"),
        "paginas_e_trechos": " || ".join(pages[:8]),
        "historico_reajuste": best.get("adjustment_history") or deepen.get("adjustment_history"),
        "contato_email": contatos.get("email_comercial") or deepen.get("email"),
        "contato_telefone": contatos.get("telefone_empresarial") or deepen.get("telefone"),
        "contato_site": contatos.get("site_oficial") or deepen.get("site"),
        "contato_fonte": contatos.get("fonte") or deepen.get("contato_fonte"),
        "contato_data_consulta": contatos.get("consulted_at") or deepen.get("contato_data_consulta"),
        "contato_verificavel": bool(
            portfolio.get("contato_verificavel")
            or contatos.get("email_comercial")
            or contatos.get("telefone_empresarial")
            or contatos.get("site_oficial")
            or deepen.get("contact_verifiable")
        ),
        "riscos": portfolio.get("riscos") or deepen.get("riscos"),
        "mensagem_exploratoria_sugerida": exploratory_message(),
        "decisao_sugerida": suggested,
        "tiago_decision": "",  # empty for Tiago: ACCEPT | REJECT | DEFER
        "outreach_status": status,
        "document_link_status": deepen.get("document_link_status")
        or best.get("document_link_status"),
        "score": portfolio.get("score_fornecedor") or best.get("score_total"),
        "sede_uf": portfolio.get("sede_uf") or deepen.get("uf"),
    }


def write_tiago_review_package(
    out_dir: Path,
    *,
    portfolios: list[dict[str, Any]],
    deepen_results: list[dict[str, Any]] | None = None,
    false_positives: list[dict[str, Any]] | None = None,
    link_conflicts: list[dict[str, Any]] | None = None,
    terminal_status: str = TERMINAL_BLOCKED_INSUFFICIENT,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Write output/commercial/reajuste_14133/tiago-review/ package."""
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = out_dir / "evidence_pack"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    deepen_by_cnpj = {
        str(d.get("cnpj") or ""): d for d in (deepen_results or []) if d.get("cnpj")
    }
    rows = [
        supplier_row(p, deepen=deepen_by_cnpj.get(str(p.get("cnpj") or "")))
        for p in portfolios
    ]
    # de-dupe by cnpj
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in rows:
        c = str(r.get("cnpj") or "")
        if not c or c in seen:
            continue
        seen.add(c)
        deduped.append(r)
    rows = deduped

    tech = [r for r in rows if r.get("outreach_status") == TECHNICALLY_VERIFIED_PENDING_TIAGO]
    # Also include deepen-only tech rows not in portfolios
    for d in deepen_results or []:
        if d.get("outreach_status") == TECHNICALLY_VERIFIED_PENDING_TIAGO:
            c = str(d.get("cnpj") or "")
            if c and c not in seen:
                rows.append(supplier_row({"cnpj": c, "razao_social": d.get("razao_social")}, deepen=d))
                seen.add(c)
                tech.append(rows[-1])

    doc_req = [r for r in rows if r.get("outreach_status") == DOCUMENT_REQUEST_CANDIDATE]
    outreach_ready = [r for r in rows if r.get("outreach_status") == OUTREACH_READY]
    assert len(outreach_ready) == 0 or all(  # noqa: S101
        not r.get("tiago_decision") for r in outreach_ready
    ), "OUTREACH_READY must not be forged with Tiago decision"

    # CSVs
    def _write_csv(path: Path, data: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
        if not data:
            path.write_text("", encoding="utf-8")
            # still write header when fieldnames known
            if fieldnames:
                with path.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    w.writeheader()
            return
        fields = fieldnames or list(data[0].keys())
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for row in data:
                w.writerow({k: row.get(k) for k in fields})

    queue_json_path = out_dir / "tiago_review_queue.json"
    queue_payload = {
        "kind": "tiago_review_queue",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "git_sha": _git_head(),
        "terminal_status": terminal_status,
        "n": len(rows),
        "technically_verified_pending_tiago": len(tech),
        "document_request_remaining": len(doc_req),
        "outreach_ready": len(outreach_ready),
        "human_review_done_forged": False,
        "tiago_decision_options": list(TIAGO_DECISIONS),
        "rows": rows,
        "notes": notes or [],
    }
    queue_json_path.write_text(
        json.dumps(queue_payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    _write_csv(out_dir / "technically_verified_pending_tiago.csv", tech, QUEUE_COLUMNS)
    _write_csv(out_dir / "document_request_remaining.csv", doc_req, QUEUE_COLUMNS)
    _write_csv(
        out_dir / "false_positives_removed.csv",
        false_positives or [],
        fieldnames=[
            "empresa",
            "cnpj",
            "reason",
            "objeto",
            "document_link_status",
            "sector_flags",
        ],
    )
    _write_csv(
        out_dir / "document_link_conflicts.csv",
        link_conflicts or [],
        fieldnames=[
            "empresa",
            "cnpj",
            "contrato_id",
            "document",
            "status",
            "reasons",
            "excerpt",
        ],
    )

    # XLSX if openpyxl available
    xlsx_path = out_dir / "tiago_review_queue.xlsx"
    try:
        from openpyxl import Workbook  # type: ignore[import-untyped]

        wb = Workbook()
        ws = wb.active
        ws.title = "tiago_queue"
        ws.append(QUEUE_COLUMNS)
        for r in rows:
            ws.append([r.get(c) for c in QUEUE_COLUMNS])
        ws2 = wb.create_sheet("technically_verified")
        ws2.append(QUEUE_COLUMNS)
        for r in tech:
            ws2.append([r.get(c) for c in QUEUE_COLUMNS])
        wb.save(xlsx_path)
    except Exception:
        # minimal CSV fallback copy named xlsx is wrong — write CSV sibling note
        _write_csv(out_dir / "tiago_review_queue.csv", rows, QUEUE_COLUMNS)
        xlsx_path.write_text(
            "openpyxl unavailable — see tiago_review_queue.csv / .json\n",
            encoding="utf-8",
        )

    # Evidence pack: per tech supplier summary
    for r in tech[:30]:
        cnpj = str(r.get("cnpj") or "unknown")
        (evidence_dir / f"{cnpj}.json").write_text(
            json.dumps(r, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    if deepen_results:
        (evidence_dir / "deepen_results.json").write_text(
            json.dumps(deepen_results, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

    head = _git_head()
    report = out_dir / "FINAL-REPORT.md"
    report.write_text(
        "\n".join(
            [
                "# FINAL-REPORT — Tiago review package (reajuste 14.133)",
                "",
                f"- **git_sha (HEAD):** `{head}`",
                f"- **generated_at:** {queue_payload['generated_at']}",
                f"- **terminal_status:** `{terminal_status}`",
                f"- **TECHNICALLY_VERIFIED_PENDING_TIAGO:** {len(tech)}",
                f"- **DOCUMENT_REQUEST_CANDIDATE remaining:** {len(doc_req)}",
                f"- **OUTREACH_READY:** {len(outreach_ready)} (must stay 0 without Tiago)",
                f"- **false_positives_removed:** {len(false_positives or [])}",
                f"- **document_link_conflicts:** {len(link_conflicts or [])}",
                f"- **suppliers in queue (deduped):** {len(rows)}",
                "",
                "## Rules",
                "",
                "- `tiago_decision` is empty until Tiago sets ACCEPT / REJECT / DEFER.",
                "- `human_review_done` is never forged true by this package.",
                "- No contact was sent in this round.",
                "- `ai_assisted_evidence_review` ≠ human review.",
                "",
                "## Notes",
                "",
                *[f"- {n}" for n in (notes or ["(none)"])],
                "",
                "## Top 15 for Tiago",
                "",
            ]
            + [
                (
                    f"{i}. **{r.get('empresa')}** (`{r.get('cnpj')}`) — "
                    f"status={r.get('outreach_status')} | "
                    f"data-base={r.get('data_base')} ({r.get('data_base_state')}) | "
                    f"indice={r.get('indice')} | link={r.get('document_link_status')}"
                )
                for i, r in enumerate(
                    sorted(rows, key=lambda x: float(x.get("score") or 0), reverse=True)[:15],
                    1,
                )
            ]
            + ["", "## Limitations", ""]
            + [f"- {n}" for n in (notes or []) if "limit" in n.lower() or "esgot" in n.lower() or "PNCP" in n]
            + (["- See deepen evidence_pack for per-supplier documentary exhaustion."] if not tech else []),
        )
        + "\n",
        encoding="utf-8",
    )

    # checksums + head binding
    checksum_lines: list[str] = []
    for p in sorted(out_dir.rglob("*")):
        if p.is_file() and p.name != "checksums.sha256":
            try:
                checksum_lines.append(f"{_sha256_file(p)}  {p.relative_to(out_dir).as_posix()}")
            except OSError:
                continue
    csum = out_dir / "checksums.sha256"
    csum.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    (out_dir / "HEAD.txt").write_text(head + "\n", encoding="utf-8")

    return {
        "path": str(out_dir),
        "git_sha": head,
        "n_queue": len(rows),
        "technically_verified_pending_tiago": len(tech),
        "document_request_remaining": len(doc_req),
        "outreach_ready": len(outreach_ready),
        "terminal_status": terminal_status,
        "checksums": str(csum),
    }
