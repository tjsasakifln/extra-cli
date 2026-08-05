"""CLI entry: python3 -m scripts.commercial.reajuste_14133"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from scripts.commercial.reajuste_14133 import DEFAULT_AS_OF, DEFAULT_OUTPUT_ROOT, MODULE_VERSION
from scripts.commercial.reajuste_14133.desk_review import write_automated_triage
from scripts.commercial.reajuste_14133.export.excel_export import export_workbook
from scripts.commercial.reajuste_14133.export.reports import (
    assert_no_secrets,
    write_csv_json,
    write_data_quality,
    write_dossiers,
    write_executive_brief,
    write_methodology,
    write_v2_deliverables,
)
from scripts.commercial.reajuste_14133.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m scripts.commercial.reajuste_14133",
        description=(
            "Fila comercial CONFENGE: reajuste em sentido estrito (Lei 14.133/2021). "
            "Unidade comercial = fornecedor. Não cobre reequilíbrio, repactuação, "
            "atualização por atraso ou aditivo quantitativo."
        ),
    )
    p.add_argument("--as-of", default=DEFAULT_AS_OF, help="Data de referência (YYYY-MM-DD)")
    p.add_argument(
        "--scope",
        default="national",
        choices=("national", "sul_sc", "sc"),
        help="Escopo geográfico do pré-filtro SQL",
    )
    p.add_argument("--uf", default=None, help="Filtrar UF (ex.: SC)")
    p.add_argument("--municipio", default=None, help="Filtrar município (ILIKE)")
    p.add_argument("--supplier-cnpj", default=None, help="Filtrar CNPJ fornecedor")
    p.add_argument("--min-contract-value", type=float, default=1_000_000.0)
    p.add_argument("--min-potential-value", type=float, default=None)
    p.add_argument("--status", default=None, help="Filtrar status de elegibilidade")
    p.add_argument("--top", type=int, default=200)
    p.add_argument("--verify-documents", action="store_true")
    p.add_argument("--max-document-fetches", type=int, default=30)
    p.add_argument("--enrich-contacts", action="store_true")
    p.add_argument("--max-contact-lookups", type=int, default=40)
    p.add_argument("--output-dir", default=None, help="Default: output/commercial/reajuste_14133/<as-of>/")
    p.add_argument("--dsn", default=None, help="DSN read-only (env REAJUSTE_SOURCE_DSN / LOCAL_DATALAKE_DSN)")
    p.add_argument("--ssh", action="store_true", help="Forçar leitura via SSH ec-prod (read-only)")
    p.add_argument("--csv", default=None, help="Fonte CSV alternativa")
    p.add_argument(
        "--max-source-rows",
        type=int,
        default=None,
        help=(
            "DIAGNÓSTICO apenas: limita linhas lidas. Campanha real NÃO deve passar este flag. "
            "Default: None (varredura integral do pré-filtro)."
        ),
    )
    p.add_argument("--batch-size", type=int, default=2000)
    p.add_argument("--export-all", action="store_true", help="Gerar XLSX/CSV/JSON/docs/dossiers")
    p.add_argument("--dossier-count", type=int, default=30)
    p.add_argument("--strict", action="store_true", help="Exit != 0 se secrets nos artefatos ou falha de pipeline")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true", help="Imprimir resumo JSON em stdout")
    p.add_argument(
        "--manual-review",
        action="store_true",
        default=False,
        help=(
            "Gerar automated_object_triage.json (máquina). "
            "Default: False. NÃO confunde com revisão humana documental."
        ),
    )
    p.add_argument(
        "--resume-from",
        default=None,
        help="Diretório de run com .checkpoint/ para retomar após falha",
    )
    p.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Gravar checkpoint neste diretório (default: --output-dir quando exporta)",
    )
    p.add_argument(
        "--require-proxy-interregno",
        action="store_true",
        help="Filtro SQL legado por assinatura≥12m (não default; pode gerar falso negativo de data-base)",
    )
    return p


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def export_run(
    run: dict[str, Any],
    out_dir: Path,
    *,
    dossier_count: int,
    manual_review: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = write_csv_json(out_dir, run)
    paths["methodology"] = str(write_methodology(out_dir))
    paths["data_quality"] = str(write_data_quality(out_dir, run))
    v2_paths = write_v2_deliverables(out_dir, run)
    paths.update(v2_paths)
    review_for_brief: list[dict[str, Any]] | None = None
    # Only write automated triage when flag is explicitly True (never `or True`)
    if manual_review is True:
        triage_meta = write_automated_triage(out_dir, run.get("top_leads") or [])
        paths.update(triage_meta.get("paths") or {})
        run.setdefault("metrics", {}).update(
            {
                "automated_object_triage_count": triage_meta.get("automated_object_triage_count"),
                "manual_review_note": (
                    "automated_object_triage.json = MACHINE ONLY. "
                    "Human review is human_review_top30_suppliers.md/json — "
                    "hand-authored per campaign with documents/pages/clauses."
                ),
            }
        )
    # Prefer hand-authored human review for the brief when available
    for candidate in (
        out_dir / "human_review_top30_suppliers.json",
        out_dir / "human_desk_review_top30.json",
        out_dir / "manual_review.json",
    ):
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if payload.get("reviews") or payload.get("kind") == "human_desk_review":
                review_for_brief = payload.get("reviews")
                paths["human_review"] = str(candidate)
                run.setdefault("metrics", {})["human_review_count"] = payload.get("n")
                break
        except (OSError, json.JSONDecodeError):
            continue
    paths["executive_brief"] = str(write_executive_brief(out_dir, run, review_for_brief))
    paths["xlsx"] = str(export_workbook(out_dir, run))
    dpaths = write_dossiers(out_dir, run.get("top_leads") or [], n=dossier_count)
    paths["dossiers_count"] = str(len(dpaths))

    # checksums
    checksum_lines: list[str] = []
    for p in sorted(out_dir.rglob("*")):
        if p.is_file() and p.name != "checksums.sha256" and ".checkpoint" not in p.parts:
            try:
                checksum_lines.append(f"{_sha256_file(p)}  {p.relative_to(out_dir).as_posix()}")
            except OSError:
                continue
    csum_path = out_dir / "checksums.sha256"
    csum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    paths["checksums"] = str(csum_path)

    man = out_dir / "run_manifest.json"
    try:
        data = json.loads(man.read_text(encoding="utf-8")) if man.exists() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data.update(
        {
            "artifact_paths": paths,
            "metrics": run.get("metrics"),
            "funnel": run.get("funnel"),
            "distributions": run.get("distributions"),
            "terminal_status": run.get("terminal_status"),
            "resumed": run.get("resumed"),
            "checkpoint_dir": run.get("checkpoint_dir"),
            "git_sha": run.get("git_sha"),
            "module_version": run.get("module_version"),
            "params": run.get("params"),
        }
    )
    man.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    secrets = assert_no_secrets(out_dir)
    return {"paths": paths, "secret_hits": secrets}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.output_dir or f"{DEFAULT_OUTPUT_ROOT}/{args.as_of}")
    ckpt = args.checkpoint_dir or (str(out_dir) if args.export_all else None)
    try:
        run = run_pipeline(
            as_of=args.as_of,
            scope=args.scope,
            uf=args.uf,
            municipio=args.municipio,
            supplier_cnpj=args.supplier_cnpj,
            min_contract_value=args.min_contract_value,
            min_potential_value=args.min_potential_value,
            status_filter=args.status,
            top=args.top,
            verify_documents=args.verify_documents,
            max_document_fetches=args.max_document_fetches,
            enrich_contacts=args.enrich_contacts,
            max_contact_lookups=args.max_contact_lookups,
            dsn=args.dsn,
            prefer_ssh=args.ssh,
            csv_path=args.csv,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            max_source_rows=args.max_source_rows,
            resume_from=args.resume_from,
            checkpoint_dir=ckpt if not args.resume_from else None,
            require_proxy_interregno=args.require_proxy_interregno,
        )
    except Exception as exc:
        print(f"ERROR: pipeline failed: {exc}", file=sys.stderr)
        if args.strict:
            return 2
        return 1

    export_info: dict[str, Any] = {}
    if args.export_all and not args.dry_run:
        export_info = export_run(
            run,
            out_dir,
            dossier_count=args.dossier_count,
            manual_review=bool(args.manual_review),  # explicit; never `or True`
        )
        if export_info.get("secret_hits"):
            print(
                f"SECURITY: secret-like patterns in {export_info['secret_hits']}",
                file=sys.stderr,
            )
            if args.strict:
                return 3

    portfolios = run.get("supplier_portfolios") or []
    summary = {
        "module_version": MODULE_VERSION,
        "run_id": run.get("run_id"),
        "as_of": run.get("as_of"),
        "source_mode": run.get("source_mode"),
        "terminal_status": run.get("terminal_status"),
        "funnel": run.get("funnel"),
        "metrics": run.get("metrics"),
        "top_suppliers_preview": [
            {
                "ranking": p.get("ranking"),
                "outreach_status": p.get("outreach_status"),
                "score": p.get("score_fornecedor"),
                "uf": p.get("sede_uf"),
                "cnpj_masked": str(p.get("cnpj") or "")[:8] + "****",
                "qtd_contratos": p.get("qtd_contratos_candidatos"),
            }
            for p in portfolios[:10]
        ],
        "output_dir": str(out_dir) if args.export_all else None,
        "export": export_info.get("paths") if export_info else None,
        "dry_run": run.get("dry_run", False),
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"reajuste_14133 v{MODULE_VERSION} run={run.get('run_id')}")
        print(
            f"source={run.get('source_mode')} as_of={run.get('as_of')} "
            f"terminal={run.get('terminal_status')}"
        )
        funnel = run.get("funnel") or {}
        metrics = run.get("metrics") or {}
        print(
            "funnel: "
            f"raw={funnel.get('examined_raw')} universe={funnel.get('universe_eligible_count')} "
            f"construction={funnel.get('construction')} "
            f"suppliers={metrics.get('supplier_portfolios')} "
            f"READY={metrics.get('outreach_ready_suppliers')} "
            f"DOC_REQ={metrics.get('document_request_suppliers')} "
            f"REGIME_UNK={funnel.get('LEGAL_REGIME_UNKNOWN')}"
        )
        if args.export_all and not args.dry_run:
            print(f"artifacts → {out_dir}")
        for row in summary["top_suppliers_preview"]:
            print(
                f"  #{row['ranking']} {row['outreach_status']} score={row['score']} "
                f"{row['uf']} n_contracts={row['qtd_contratos']}"
            )

    if args.strict and not args.dry_run:
        if (run.get("funnel") or {}).get("examined_raw", 0) == 0:
            print("ERROR: strict mode — zero rows examined from source", file=sys.stderr)
            return 4
        for lead in run.get("leads") or []:
            if lead.get("classificacao") == "HOT_VERIFIED":
                gates = lead.get("hot_gates") or {}
                if not gates.get("documentos_acessiveis") or not gates.get("data_base_exata"):
                    print("ERROR: HOT_VERIFIED without documentary gates", file=sys.stderr)
                    return 5
            if lead.get("outreach_status") == "OUTREACH_READY":
                if lead.get("regime_legal") in {None, "UNKNOWN", "LEGAL_REGIME_UNKNOWN"}:
                    print("ERROR: OUTREACH_READY with unknown regime", file=sys.stderr)
                    return 6
                if not lead.get("regime_proven"):
                    print("ERROR: OUTREACH_READY without proven regime", file=sys.stderr)
                    return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
