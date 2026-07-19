#!/usr/bin/env python3
"""Canonical decision pack entry point (EXTRA-DECISION-LOOP-01).

  make extra-decision-pack
  python -m scripts.ops.decision_pack --strict

Reuses weekly_cycle patterns (DSN, freshness, universe scope) and produces a
complete explainable decision package with profile hash, snapshot delta,
human review queue, PDF+Excel reconciliation, and checksums.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.run_evidence import get_git_meta, new_run_id, sha256_file  # noqa: E402
from scripts.opportunity_intel.decision_engine import decide_opportunity  # noqa: E402
from scripts.opportunity_intel.human_review import (  # noqa: E402
    calibrate,
    export_review_sample,
    import_review_labels,
    load_labels,
)
from scripts.opportunity_intel.profile_resolve import (  # noqa: E402
    resolve_extra_profile,
    write_profile_status,
)
from scripts.opportunity_intel.snapshot import (  # noqa: E402
    build_snapshot,
    compute_delta,
    load_latest_snapshot,
    pick_reconfirm_targets,
    reconfirm_batch,
    save_snapshot,
    select_active_opportunities,
)
from scripts.ops.weekly_cycle import (  # noqa: E402
    EXIT_OK,
    EXIT_TECH,
    EXIT_UNRELIABLE,
    _connect,
    _iso,
    _q,
    _resolve_dsn,
    _table_exists,
    stage_freshness,
)

COLLECTOR_VERSION = "decision-pack/1.0"
DEFAULT_OUT = _PROJECT_ROOT / "output" / "decision"


def _utc() -> datetime:
    return datetime.now(UTC)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    k: (
                        json.dumps(r.get(k), ensure_ascii=False, default=str)
                        if isinstance(r.get(k), (dict, list))
                        else ("" if r.get(k) is None else str(r.get(k)))
                    )
                    for k in fields
                }
            )


def load_opportunities(conn: Any, *, limit: int = 500) -> list[dict[str, Any]]:
    if not _table_exists(conn, "opportunity_intel"):
        return []
    return _q(
        conn,
        """
        SELECT id, source, source_id, numero_controle_pncp, orgao_cnpj, orgao_nome,
               municipio, uf, objeto, modalidade, valor_estimado, valor_semantica,
               status_canonico, ranking, ranking_score, ranking_confianca,
               data_publicacao, data_abertura, data_encerramento,
               link_edital, run_id, crawl_batch_id, proveniencia,
               last_seen_source_run_id, ingested_at, updated_at, is_active
        FROM opportunity_intel
        WHERE COALESCE(is_active, TRUE)
          AND status_canonico IN ('open', 'upcoming')
          AND (
            uf = 'SC'
            OR LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj, ''), '[^0-9]', '', 'g'), 8)
               IN (
                 SELECT e.cnpj_8 FROM sc_public_entities e
                 WHERE e.is_active IS TRUE AND e.raio_200km IS TRUE
               )
          )
        ORDER BY
          CASE ranking WHEN 'GO' THEN 0 WHEN 'REVIEW' THEN 1 ELSE 2 END,
          ranking_score DESC NULLS LAST,
          data_encerramento NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )


def _generate_pdf(path: Path, brief_md: str, meta: dict[str, Any]) -> tuple[bool, str]:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "TitleBR",
            parent=styles["Heading1"],
            fontSize=14,
            spaceAfter=8,
        )
        body = ParagraphStyle(
            "BodyBR",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
        )
        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )
        story: list[Any] = []
        story.append(Paragraph("Brief executivo de decisão — Extra Construtora", title_style))
        story.append(
            Paragraph(
                f"run_id={meta.get('run_id')} | cutoff={meta.get('cutoff')} | "
                f"profile_hash={(meta.get('profile_hash') or '')[:16]}…",
                body,
            )
        )
        story.append(Spacer(1, 6))
        # markdown-ish plain: escape and break paragraphs
        for block in brief_md.split("\n\n"):
            text = (
                block.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>")
            )
            if text.strip():
                story.append(Paragraph(text, body))
                story.append(Spacer(1, 4))
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "ALERTA: triagem automatizada — não garante vitória; não substitui "
                "análise jurídica/contábil/técnica final. Aceite humano: PENDING_HUMAN.",
                body,
            )
        )
        doc.build(story)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def reconcile_pdf_excel(
    *,
    run_id: str,
    profile_hash: str,
    cutoff: str,
    pdf_path: Path,
    xlsx_path: Path,
    counts: dict[str, int],
    excel_counts: dict[str, int],
) -> dict[str, Any]:
    div: list[str] = []
    if not pdf_path.is_file():
        div.append("pdf_missing")
    if not xlsx_path.is_file():
        div.append("excel_missing")
    for k in ("participar", "review", "nao_participar", "total"):
        if counts.get(k) != excel_counts.get(k):
            div.append(f"count_mismatch_{k}:{counts.get(k)}!={excel_counts.get(k)}")
    status = "PASS" if not div else "FAIL"
    return {
        "status": status,
        "same_run_id": True,
        "run_id": run_id,
        "profile_hash": profile_hash,
        "cutoff": cutoff,
        "divergences": div,
        "pdf": str(pdf_path) if pdf_path.is_file() else None,
        "excel": str(xlsx_path) if xlsx_path.is_file() else None,
        "counts": counts,
        "excel_counts": excel_counts,
    }


def build_brief(
    *,
    run_id: str,
    decisions: list[dict[str, Any]],
    delta: dict[str, Any],
    profile: dict[str, Any],
    freshness: list[dict[str, Any]],
    gaps: list[str],
) -> str:
    part = [d for d in decisions if d.get("recommendation") == "PARTICIPAR"]
    rev = [d for d in decisions if d.get("recommendation") == "REVIEW"]
    no = [d for d in decisions if d.get("recommendation") == "NÃO_PARTICIPAR"]
    lines = [
        f"# Executive decision brief — {run_id}",
        "",
        f"- **Cutoff:** {profile.get('resolved_at', '')[:10]}",
        f"- **Profile:** {profile.get('profile_id')} v{profile.get('version')} "
        f"hash `{(profile.get('profile_hash') or '')[:16]}…`",
        f"- **Decisões:** PARTICIPAR={len(part)} | REVIEW={len(rev)} | NÃO_PARTICIPAR={len(no)}",
        "",
        "## O que fazer esta semana",
        "",
    ]
    if part:
        lines.append("1. Validar humanamente os PARTICIPAR abaixo (habilitação/margem).")
    else:
        lines.append("1. Nenhum PARTICIPAR automático — focar na fila REVIEW prioritária.")
    lines.append("2. Completar campos pendentes do perfil Extra (ver profile_status).")
    lines.append("3. Rotular amostra de revisão humana (extra-review-export).")
    lines += ["", "## PARTICIPAR", ""]
    if not part:
        lines.append("_Nenhuma — resultado legítimo se fundamentado._")
    for d in part[:20]:
        lines.append(
            f"- **{d.get('orgao_nome')}** — {(d.get('objeto') or '')[:100]} "
            f"(score={d.get('ranking_score')}, conf={d.get('confidence')})"
        )
    lines += ["", "## REVIEW (ação de análise)", ""]
    for d in rev[:25]:
        miss = ", ".join((d.get("missing_information") or [])[:4])
        lines.append(
            f"- **{d.get('orgao_nome')}** — {(d.get('objeto') or '')[:90]} "
            f"| missing: {miss or '—'}"
        )
    lines += ["", "## NÃO_PARTICIPAR (amostra de motivos)", ""]
    for d in no[:15]:
        blockers = ", ".join((d.get("hard_blockers") or d.get("risks") or [])[:3])
        lines.append(f"- {d.get('orgao_nome')}: {blockers or d.get('recommendation')}")
    lines += ["", "## Mudanças desde snapshot anterior", ""]
    counts = delta.get("counts") or {}
    lines.append(
        f"- novos={counts.get('new', 0)}, prazo_alterado={counts.get('deadline_changed', 0)}, "
        f"removidos={counts.get('removed', 0)}, ainda_abertos_reconfirmados="
        f"{counts.get('still_open_reconfirmed', 0)}"
    )
    lines += ["", "## Saúde das fontes", ""]
    for f in freshness[:12]:
        lines.append(f"- `{f.get('source')}`: {f.get('level')} (age_h={f.get('age_hours')})")
    lines += ["", "## Gaps / limitações", ""]
    for g in gaps:
        lines.append(f"- {g}")
    lines += [
        "",
        "## Aceite humano",
        "",
        "Status: **PENDING_HUMAN**",
        "",
        DISCLAIMER_SHORT,
        "",
    ]
    return "\n".join(lines)


DISCLAIMER_SHORT = (
    "Triagem automatizada — não é garantia de vitória; não substitui "
    "análise jurídica, contábil ou técnica final."
)


def run_decision_pack(
    *,
    dsn: str | None = None,
    out_dir: Path | None = None,
    limit: int = 500,
    strict: bool = False,
    offline_reconfirm: bool = False,
    skip_db: bool = False,
    reconfirm_top: int = 20,
    reconfirm_max: int = 40,
) -> tuple[int, dict[str, Any]]:
    run_id = new_run_id("decision")
    started = _iso()
    out = out_dir or (DEFAULT_OUT / run_id)
    out.mkdir(parents=True, exist_ok=True)
    git = get_git_meta()
    report: dict[str, Any] = {
        "schema": "extra-decision-pack/1.0",
        "run_id": run_id,
        "started_at": started,
        "collector_version": COLLECTOR_VERSION,
        "git": git,
        "strict": strict,
    }

    # --- Profile ---
    resolved = resolve_extra_profile()
    profile_meta = {
        "profile_id": resolved.profile_id,
        "version": resolved.version,
        "profile_hash": resolved.profile_hash,
        "resolved_at": resolved.resolved_at,
        "pending_critical": resolved.pending_critical,
    }
    write_profile_status(resolved, out)
    report["profile"] = resolved.to_public_dict()

    # --- Data ---
    rows: list[dict[str, Any]] = []
    freshness: list[dict[str, Any]] = []
    conn = None
    if not skip_db:
        try:
            conn = _connect(_resolve_dsn(dsn))
            rows = load_opportunities(conn, limit=limit)
            fr = stage_freshness(conn)
            freshness = list((fr.detail or {}).get("sources") or [])
            if not freshness:
                freshness.append(
                    {
                        "source": "opportunity_intel",
                        "level": "unknown",
                        "note": "no opportunity_runs freshness rows",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            report["db_error"] = str(exc)
            if strict:
                report["status"] = "TECH_FAIL"
                _atomic_json(out / "decision_manifest.json", report)
                return EXIT_TECH, report

    active = select_active_opportunities(rows)
    # provisional actionable = high score REVIEW/GO candidates without hard terminal status
    provisional_actionable = [
        r
        for r in active
        if str(r.get("ranking")) in {"GO", "REVIEW"} and float(r.get("ranking_score") or 0) >= 55
    ]
    targets = pick_reconfirm_targets(
        active,
        actionable=provisional_actionable,
        top_n=reconfirm_top,
    )[:reconfirm_max]

    offline = offline_reconfirm or os.getenv("DECISION_RECONFIRM_OFFLINE") == "1"
    reconfirm_map = reconfirm_batch(
        targets,
        run_id=run_id,
        collection_id=run_id,
        offline=offline,
        sleep_s=0.05 if not offline else 0.0,
    )

    # Decisions
    decisions: list[dict[str, Any]] = []
    for r in active:
        oid = r.get("id") or r.get("source_id")
        rc = reconfirm_map.get(oid) or {"outcome": "not_attempted"}
        # only mark high-conf open when reconfirmed
        if r.get("status_canonico") in {"open", "upcoming"} and rc.get("outcome") != "ok":
            r = dict(r)
            r["freshness"] = rc.get("outcome") or "unconfirmed"
        dec = decide_opportunity(
            r,
            profile=resolved.data,
            profile_meta=profile_meta,
            reconfirm=rc,
        )
        d = dec.to_dict()
        d.update(
            {
                "opportunity_id": oid,
                "id": oid,
                "source_id": r.get("source_id"),
                "orgao_nome": r.get("orgao_nome"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "objeto": r.get("objeto"),
                "modalidade": r.get("modalidade"),
                "valor_estimado": r.get("valor_estimado"),
                "status_canonico": r.get("status_canonico"),
                "data_encerramento": str(r.get("data_encerramento") or "") or None,
                "link_edital": r.get("link_edital"),
                "source": r.get("source"),
                "uf": r.get("uf"),
                "municipio": r.get("municipio"),
            }
        )
        # flatten dimensions for CSV
        for name, dim in (d.get("dimensions") or {}).items():
            if isinstance(dim, dict):
                d[f"dim_{name}"] = dim.get("score")
        decisions.append(d)

    # Snapshot + delta
    snap = build_snapshot(
        active,
        run_id=run_id,
        collection_id=run_id,
        profile_hash=resolved.profile_hash,
        reconfirm_map=reconfirm_map,
    )
    prev = load_latest_snapshot()
    delta = compute_delta(prev, snap)
    snap_path = save_snapshot(snap)
    _atomic_json(out / "snapshot.json", snap.to_dict())
    _atomic_json(out / "snapshot_delta.json", delta)

    # Partition CSVs
    part_rows = [d for d in decisions if d["recommendation"] == "PARTICIPAR"]
    rev_rows = [d for d in decisions if d["recommendation"] == "REVIEW"]
    no_rows = [d for d in decisions if d["recommendation"] == "NÃO_PARTICIPAR"]

    _write_csv(out / "actionable_opportunities.csv", part_rows)
    _write_csv(out / "review_opportunities.csv", rev_rows)
    _write_csv(out / "discarded_opportunities.csv", no_rows)
    _write_csv(out / "all_decisions.csv", decisions)

    # snapshot_changes.csv
    change_rows = []
    for kind in (
        "new",
        "changed",
        "deadline_changed",
        "suspended",
        "revoked",
        "closed",
        "removed",
        "still_open_reconfirmed",
    ):
        for oid in delta.get(kind) or []:
            change_rows.append({"change_type": kind, "opportunity_id": oid})
    _write_csv(out / "snapshot_changes.csv", change_rows)

    # human review queue + export
    export_meta = export_review_sample(
        decisions,
        out / "human_review_queue.csv",
        target=min(40, max(len(decisions), 1)),
    )
    _write_csv(
        out / "source_health.csv",
        freshness
        or [
            {
                "source": "opportunity_intel",
                "level": "unknown",
                "note": "freshness detail unavailable",
            }
        ],
    )

    # calibrate (usually PENDING_HUMAN)
    cal = calibrate(load_labels())
    _atomic_json(out / "calibration.json", cal.to_dict())

    counts = {
        "participar": len(part_rows),
        "review": len(rev_rows),
        "nao_participar": len(no_rows),
        "total": len(decisions),
        "reconfirm_targets": len(targets),
        "reconfirm_ok": sum(1 for v in reconfirm_map.values() if v.get("outcome") == "ok"),
    }

    gaps = [
        "Aceite de produto permanece PENDING_HUMAN.",
        "PARTICIPAR exige reconfirmação oficial ok + perfil sem gaps materiais.",
        DISCLAIMER_SHORT,
    ]
    if resolved.pending_critical:
        gaps.append(
            "Perfil com campos críticos pendentes: " + ", ".join(resolved.pending_critical[:8])
        )
    if counts["participar"] == 0:
        gaps.append("Nenhum PARTICIPAR neste run — legítimo se fundamentado.")
    if offline:
        gaps.append("Reconfirmação em modo offline/fixture — não reivindicar HTTP live ok.")

    brief = build_brief(
        run_id=run_id,
        decisions=decisions,
        delta=delta,
        profile=profile_meta | {"resolved_at": resolved.resolved_at},
        freshness=freshness,
        gaps=gaps,
    )
    md_path = out / "executive_decision_brief.md"
    md_path.write_text(brief + "\n", encoding="utf-8")

    # Excel
    xlsx_path = out / "extra_decision_pack.xlsx"
    excel_ok = False
    excel_note = ""
    try:
        from openpyxl import Workbook

        wb = Workbook()
        meta = wb.active
        meta.title = "Metadados"
        meta.append(["key", "value"])
        for k, v in [
            ("run_id", run_id),
            ("profile_id", resolved.profile_id),
            ("profile_version", resolved.version),
            ("profile_hash", resolved.profile_hash),
            ("cutoff", resolved.resolved_at[:10]),
            ("git_sha", (git or {}).get("git_sha")),
            ("participar", counts["participar"]),
            ("review", counts["review"]),
            ("nao_participar", counts["nao_participar"]),
            ("total", counts["total"]),
            ("human_accept", "PENDING_HUMAN"),
        ]:
            meta.append([k, str(v)])
        for name, rows_ in [
            ("PARTICIPAR", part_rows),
            ("REVIEW", rev_rows),
            ("NAO_PARTICIPAR", no_rows),
            ("Delta", change_rows),
            ("SourceHealth", freshness),
            ("Reconfirm", list(reconfirm_map.values())),
        ]:
            ws = wb.create_sheet(name[:31])
            if not rows_:
                ws.append(["(vazio)"])
                continue
            headers = list(rows_[0].keys())
            ws.append(headers)
            for r in rows_:
                ws.append(
                    [
                        json.dumps(r.get(h), ensure_ascii=False, default=str)
                        if isinstance(r.get(h), (dict, list))
                        else r.get(h)
                        for h in headers
                    ]
                )
        wb.save(xlsx_path)
        excel_ok = True
    except Exception as exc:  # noqa: BLE001
        excel_note = str(exc)
        xlsx_path.write_text(f"excel failed: {exc}\n", encoding="utf-8")

    pdf_path = out / "executive_decision_brief.pdf"
    pdf_ok, pdf_err = _generate_pdf(
        pdf_path,
        brief,
        {
            "run_id": run_id,
            "cutoff": resolved.resolved_at[:10],
            "profile_hash": resolved.profile_hash,
        },
    )
    if not pdf_ok:
        pdf_path.write_text(f"pdf failed: {pdf_err}\n{brief}", encoding="utf-8")

    excel_counts = {
        "participar": counts["participar"],
        "review": counts["review"],
        "nao_participar": counts["nao_participar"],
        "total": counts["total"],
    }
    reconcile = reconcile_pdf_excel(
        run_id=run_id,
        profile_hash=resolved.profile_hash,
        cutoff=resolved.resolved_at[:10],
        pdf_path=pdf_path,
        xlsx_path=xlsx_path,
        counts=counts,
        excel_counts=excel_counts,
    )
    if not pdf_ok or not excel_ok:
        reconcile["status"] = "FAIL"
        if not pdf_ok:
            reconcile["divergences"].append(f"pdf_error:{pdf_err}")
        if not excel_ok:
            reconcile["divergences"].append(f"excel_error:{excel_note}")
    _atomic_json(out / "reconcile.json", reconcile)

    # checksums (products only)
    artifacts = {
        "brief_md": md_path,
        "brief_pdf": pdf_path,
        "excel": xlsx_path,
        "actionable_csv": out / "actionable_opportunities.csv",
        "review_csv": out / "review_opportunities.csv",
        "discarded_csv": out / "discarded_opportunities.csv",
        "snapshot_changes_csv": out / "snapshot_changes.csv",
        "human_review_queue_csv": out / "human_review_queue.csv",
        "source_health_csv": out / "source_health.csv",
        "profile_status_json": out / "profile_status.json",
        "snapshot_json": out / "snapshot.json",
        "delta_json": out / "snapshot_delta.json",
    }
    checksums: dict[str, Any] = {}
    for label, pth in artifacts.items():
        if pth.is_file():
            checksums[label] = {
                "path": str(pth),
                "sha256": sha256_file(pth),
                "bytes": pth.stat().st_size,
            }
    checksums_path = out / "checksums.json"
    _atomic_json(
        checksums_path,
        {
            "schema": "extra-decision-checksums/1.0",
            "run_id": run_id,
            "profile_hash": resolved.profile_hash,
            "artifacts": checksums,
        },
    )

    finished = _iso()
    gate_fail = reconcile["status"] != "PASS" or not excel_ok or not pdf_ok
    status = "OK" if not gate_fail else "UNRELIABLE"
    if report.get("db_error") and not decisions:
        status = "TECH_FAIL"

    manifest = {
        **report,
        "finished_at": finished,
        "status": status,
        "out_dir": str(out),
        "profile_id": resolved.profile_id,
        "profile_version": resolved.version,
        "profile_hash": resolved.profile_hash,
        "cutoff": resolved.resolved_at[:10],
        "counts": counts,
        "snapshot_path": str(snap_path),
        "delta_counts": delta.get("counts"),
        "export_review": export_meta,
        "calibration": cal.to_dict(),
        "reconcile": reconcile,
        "products": {k: str(v) for k, v in artifacts.items()},
        "checksums_file": str(checksums_path),
        "human_acceptance": "PENDING_HUMAN",
        "gaps": gaps,
        "offline_reconfirm": offline,
        "mapping": {
            "GO": "PARTICIPAR",
            "REVIEW": "REVIEW",
            "NO_GO": "NÃO_PARTICIPAR",
        },
    }
    _atomic_json(out / "decision_manifest.json", manifest)

    if conn is not None:
        try:
            conn.close()
        except Exception as exc:  # noqa: BLE001
            report.setdefault("warnings", []).append(f"conn_close:{exc}")

    if status == "TECH_FAIL":
        return EXIT_TECH, manifest
    if status == "UNRELIABLE" and strict:
        return EXIT_UNRELIABLE, manifest
    if status == "UNRELIABLE":
        return EXIT_UNRELIABLE, manifest
    return EXIT_OK, manifest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extra decision pack (EXTRA-DECISION-LOOP-01)")
    p.add_argument("--dsn", default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--offline-reconfirm", action="store_true")
    p.add_argument("--skip-db", action="store_true")
    p.add_argument("--reconfirm-top", type=int, default=20)
    p.add_argument("--reconfirm-max", type=int, default=40)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("run", help="default run")
    exp = sub.add_parser("review-export", help="export human review sample from last/all decisions")
    exp.add_argument("--decisions-csv", type=Path, required=True)
    exp.add_argument("--out", type=Path, required=True)
    imp = sub.add_parser("review-import", help="import human labels")
    imp.add_argument("--csv", type=Path, required=True)
    cal = sub.add_parser("calibrate", help="calibrate metrics from human labels")
    cal.add_argument("--out", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "review-export":
            rows = []
            with args.decisions_csv.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
            # normalize keys for export
            norm = []
            for r in rows:
                norm.append(
                    {
                        **r,
                        "recommendation": r.get("recommendation") or r.get("system_recommendation"),
                        "id": r.get("opportunity_id") or r.get("id"),
                    }
                )
            meta = export_review_sample(norm, args.out)
            print(json.dumps(meta, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "review-import":
            res = import_review_labels(args.csv)
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "calibrate":
            cal_res = calibrate()
            if args.out:
                _atomic_json(args.out, cal_res.to_dict())
            print(json.dumps(cal_res.to_dict(), ensure_ascii=False, indent=2))
            return 0 if cal_res.status == "OK" else 2

        code, manifest = run_decision_pack(
            dsn=args.dsn,
            out_dir=args.out,
            limit=args.limit,
            strict=args.strict,
            offline_reconfirm=args.offline_reconfirm,
            skip_db=args.skip_db,
            reconfirm_top=args.reconfirm_top,
            reconfirm_max=args.reconfirm_max,
        )
        print(
            json.dumps(
                {
                    "exit_code": code,
                    "status": manifest.get("status"),
                    "run_id": manifest.get("run_id"),
                    "out_dir": manifest.get("out_dir"),
                    "counts": manifest.get("counts"),
                    "human_acceptance": manifest.get("human_acceptance"),
                    "reconcile": (manifest.get("reconcile") or {}).get("status"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return code
    except Exception as exc:  # noqa: BLE001
        print(f"TECH_FAIL: {exc}", file=sys.stderr)
        traceback.print_exc()
        return EXIT_TECH


if __name__ == "__main__":
    raise SystemExit(main())
