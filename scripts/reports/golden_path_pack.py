"""Golden-path commercial report pack (editais, contratos, concorrentes, valores, PDF).

Produces honest artifacts from PostgreSQL. Empty tables yield empty reports with
limitations — never invents rankings or 95% coverage.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.reports.run_metadata import _git_sha_short, new_run_id  # noqa: E402


def _conn(dsn: str):
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _q(conn, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        try:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            return [{"_error": str(exc)}]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    # flatten errors
    if len(rows) == 1 and set(rows[0].keys()) == {"_error"}:
        path.write_text(f"# error: {rows[0]['_error']}\n", encoding="utf-8")
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys and k != "_error":
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            if "_error" in r:
                continue
            w.writerow({k: r.get(k) for k in keys})


def fetch_editais(conn) -> list[dict[str, Any]]:
    return _q(
        conn,
        """
        SELECT pncp_id, objeto_compra, uf, municipio, orgao_razao_social,
               valor_total_estimado, modalidade_nome, data_publicacao,
               data_encerramento, link_pncp, content_hash, source
        FROM pncp_raw_bids
        WHERE is_active IS TRUE
        ORDER BY data_publicacao DESC NULLS LAST
        LIMIT 500
        """,
    )


def fetch_contratos(conn) -> list[dict[str, Any]]:
    return _q(
        conn,
        """
        SELECT *
        FROM pncp_supplier_contracts
        ORDER BY 1
        LIMIT 500
        """,
    )


def fetch_concorrentes(conn) -> list[dict[str, Any]]:
    # Prefer contracts winners; fallback empty with limitation
    rows = _q(
        conn,
        """
        SELECT
            COALESCE(ni_fornecedor, cnpj_fornecedor, 'UNKNOWN') AS fornecedor_id,
            COALESCE(nome_fornecedor, 'N/I') AS nome_fornecedor,
            COUNT(*) AS n_contratos,
            SUM(COALESCE(valor_global, valor_homologado, 0)) AS valor_total
        FROM pncp_supplier_contracts
        GROUP BY 1, 2
        ORDER BY n_contratos DESC, valor_total DESC NULLS LAST
        LIMIT 50
        """,
    )
    if rows and "_error" not in rows[0]:
        return rows
    # fallback: orgaos that publish most (not true competitors)
    return _q(
        conn,
        """
        SELECT orgao_cnpj AS fornecedor_id,
               orgao_razao_social AS nome_fornecedor,
               COUNT(*) AS n_editais,
               SUM(COALESCE(valor_total_estimado,0)) AS valor_estimado_total,
               'fallback_orgao_not_supplier' AS note
        FROM pncp_raw_bids
        WHERE is_active IS TRUE AND orgao_cnpj IS NOT NULL
        GROUP BY 1, 2
        ORDER BY n_editais DESC
        LIMIT 50
        """,
    )


def fetch_referencias_valores(conn) -> list[dict[str, Any]]:
    return _q(
        conn,
        """
        SELECT
            modalidade_nome,
            COUNT(*) AS n,
            AVG(valor_total_estimado) AS ticket_medio_estimado,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY valor_total_estimado)
                AS mediana_estimada,
            MIN(valor_total_estimado) AS min_estimado,
            MAX(valor_total_estimado) AS max_estimado
        FROM pncp_raw_bids
        WHERE is_active IS TRUE
          AND valor_total_estimado IS NOT NULL
          AND valor_total_estimado > 0
        GROUP BY modalidade_nome
        ORDER BY n DESC
        LIMIT 50
        """,
    )


def _write_pdf(
    path: Path,
    *,
    run_id: str,
    counts: dict[str, int],
    limitations: list[str],
    git_sha: str,
) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Extra Consultoria — Pacote Golden Path", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"run_id: {run_id}", styles["Normal"]),
        Paragraph(f"generated_at: {datetime.now(UTC).isoformat()}", styles["Normal"]),
        Paragraph(f"git_sha: {git_sha}", styles["Normal"]),
        Spacer(1, 12),
        Paragraph("Contagens (honestas)", styles["Heading2"]),
    ]
    for k, v in counts.items():
        story.append(Paragraph(f"• {k}: {v}", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Limitações", styles["Heading2"]))
    for lim in limitations:
        story.append(Paragraph(f"• {lim}", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Semântica de valores: valor_total_estimado ≠ homologado ≠ contratado ≠ pago. "
            "Concorrentes listados são observáveis; não é mercado completo.",
            styles["Normal"],
        )
    )
    doc.build(story)


def build_pack(
    *,
    dsn: str,
    output_dir: Path,
    run_id: str | None = None,
) -> dict[str, Any]:
    rid = run_id or new_run_id("gp-pack")
    out = output_dir / rid
    out.mkdir(parents=True, exist_ok=True)
    limitations: list[str] = []
    counts: dict[str, int] = {}
    paths: dict[str, str] = {}

    try:
        conn = _conn(dsn)
    except Exception as exc:  # noqa: BLE001
        limitations.append(f"DB connect failed: {exc}")
        # still write empty pack + pdf
        for name in ("editais", "contratos", "concorrentes", "referencias_valores"):
            p = out / f"{name}.csv"
            _write_csv(p, [])
            paths[name] = str(p)
            counts[name] = 0
        pdf_path = out / f"golden-path-pack-{date.today().isoformat()}.pdf"
        _write_pdf(
            pdf_path,
            run_id=rid,
            counts=counts,
            limitations=limitations,
            git_sha=_git_sha_short(),
        )
        paths["pdf"] = str(pdf_path)
        manifest = {
            "run_id": rid,
            "status": "degraded",
            "counts": counts,
            "paths": paths,
            "limitations": limitations,
            "git_sha": _git_sha_short(),
        }
        (out / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return manifest

    try:
        editais = fetch_editais(conn)
        contratos = fetch_contratos(conn)
        concorrentes = fetch_concorrentes(conn)
        refs = fetch_referencias_valores(conn)
    finally:
        conn.close()

    def _count(rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        if len(rows) == 1 and "_error" in rows[0]:
            limitations.append(rows[0]["_error"])
            return 0
        return len(rows)

    counts = {
        "editais": _count(editais),
        "contratos": _count(contratos),
        "concorrentes": _count(concorrentes),
        "referencias_valores": _count(refs),
    }
    for name, rows in (
        ("editais", editais),
        ("contratos", contratos),
        ("concorrentes", concorrentes),
        ("referencias_valores", refs),
    ):
        p = out / f"{name}.csv"
        _write_csv(p, rows if not (rows and "_error" in rows[0]) else [])
        paths[name] = str(p)

    if counts["contratos"] == 0:
        limitations.append(
            "pncp_supplier_contracts vazio ou ausente — relatório de contratos sem linhas."
        )
    if counts["editais"] == 0:
        limitations.append("pncp_raw_bids sem editais ativos — relatório de editais vazio.")
    if any("fallback_orgao" in str(r) for r in concorrentes):
        limitations.append(
            "Concorrentes derivados de órgãos (fallback) — não são vencedores/fornecedores."
        )
    limitations.append(
        "Não afirmar cobertura operacional 95% nem mercado completo a partir deste pack."
    )

    pdf_path = out / f"golden-path-pack-{date.today().isoformat()}.pdf"
    _write_pdf(
        pdf_path,
        run_id=rid,
        counts=counts,
        limitations=limitations,
        git_sha=_git_sha_short(),
    )
    paths["pdf"] = str(pdf_path)
    if not (pdf_path.is_file() and pdf_path.stat().st_size > 0):
        raise RuntimeError(f"golden_path_pack: PDF missing or empty: {pdf_path}")

    manifest = {
        "run_id": rid,
        "status": "ok" if counts["editais"] > 0 or counts["contratos"] > 0 else "minimal",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "counts": counts,
        "paths": paths,
        "limitations": limitations,
        "git_sha": _git_sha_short(),
        "claims": {
            "forbidden": [
                "PDF gerado sem arquivo no disco",
                "Cobertura 95% a partir do pack",
                "Concorrentes = mercado completo",
            ]
        },
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Golden path commercial report pack")
    p.add_argument(
        "--dsn",
        default=os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL"),
    )
    p.add_argument(
        "--output-dir",
        default=str(_PROJECT_ROOT / "output" / "golden-path" / "reports"),
    )
    p.add_argument("--run-id", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    if not args.dsn:
        print("DSN required (LOCAL_DATALAKE_DSN)", file=sys.stderr)
        return 2
    man = build_pack(dsn=args.dsn, output_dir=Path(args.output_dir), run_id=args.run_id)
    if args.json:
        print(json.dumps(man, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"run_id={man['run_id']} status={man['status']}")
        print(f"counts={man['counts']}")
        print(f"pdf={man['paths'].get('pdf')}")
        for lim in man.get("limitations") or []:
            print(f"limitation: {lim}")
    pdf = Path(man["paths"]["pdf"])
    return 0 if pdf.is_file() and pdf.stat().st_size > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
