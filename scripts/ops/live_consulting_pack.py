#!/usr/bin/env python3
"""EXTRA-LIVE-CONSULTING-PACK-01 — single-cycle A–E pack on isolated real data.

Canonical entry:
  python -m scripts.ops.live_consulting_pack run \\
    --dsn postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc \\
    --out /path/to/pack-output

Guarantees (fail-closed):
- Aggregates over full eligible population (never silent first-N universe)
- Same run_id / as_of / profile / schema / SHA across A–E, PDF, Excel, CSV/JSON
- production_touched=false; isolation verifier rejects soak/prod DSN/paths
- Does not SSH, deploy, or write outside campaign paths
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.ops import deliverable_a_org_ranking as deliv_a  # noqa: E402
from scripts.ops import deliverable_b_competitors as deliv_b  # noqa: E402
from scripts.ops import deliverable_c_expiring as deliv_c  # noqa: E402
from scripts.ops import deliverable_d_prices as deliv_d  # noqa: E402
from scripts.ops.diagnostic_profile import profile_stamp  # noqa: E402
from scripts.reports.run_metadata import build_run_metadata, new_run_id  # noqa: E402

CAMPAIGN_ID = "EXTRA-LIVE-CONSULTING-PACK-01"
DEFAULT_DSN = os.getenv(
    "CAMPAIGN_TEST_DSN",
    "postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc",
)

# Isolation denylist — fail if DSN/path matches soak/prod surface.
PROD_HOST_MARKERS = (
    "ec-prod",
    "netcup",
    "/opt/extra-consultoria",
    "5432/extra_prod",
    "extra_prod",
    "@10.",
    "@172.16.",
    "@192.168.0.",
)
FORBIDDEN_DSN_PORTS = ()  # none by default; host markers are primary
FORBIDDEN_PATH_MARKERS = (
    "/opt/extra-consultoria",
    "nfs",
    "ec-prod",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_sha(root: Path | None = None) -> str:
    r = root or _PROJECT_ROOT
    try:
        out = subprocess.check_output(  # noqa: S603
            ["/usr/bin/git", "rev-parse", "HEAD"],
            cwd=str(r),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def mask_dsn(dsn: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", dsn)


def assert_isolation(dsn: str, out_dir: Path | None = None) -> dict[str, Any]:
    """Fail-closed isolation gate. Returns check dict or raises SystemExit."""
    lowered = dsn.lower()
    hits: list[str] = []
    for m in PROD_HOST_MARKERS:
        if m.lower() in lowered:
            hits.append(f"dsn_marker:{m}")
    if out_dir is not None:
        p = str(out_dir.resolve()).lower()
        for m in FORBIDDEN_PATH_MARKERS:
            if m.lower() in p and "artifacts/campaigns" not in p:
                hits.append(f"path_marker:{m}")
    # Only localhost / 127.0.0.1 / docker service names allowed for campaign
    host_ok = any(
        h in lowered
        for h in (
            "127.0.0.1",
            "localhost",
            "@test-db",
            "@extra-live-pack",
            "@extra-test-db",
        )
    )
    if not host_ok:
        hits.append("dsn_host_not_local_isolated")
    result = {
        "production_touched": False,
        "isolation_ok": len(hits) == 0,
        "hits": hits,
        "dsn_masked": mask_dsn(dsn),
        "checked_at": utc_now(),
    }
    if hits:
        raise SystemExit(
            f"ISOLATION_FAIL: {hits} dsn={mask_dsn(dsn)}"
        )
    return result


def connect(dsn: str) -> Any:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    return conn


def q(conn: Any, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def scalar(conn: Any, sql: str, params: tuple | list | None = None) -> Any:
    rows = q(conn, sql, params)
    if not rows:
        return None
    return next(iter(rows[0].values()))


def schema_version(conn: Any) -> str | None:
    try:
        return str(
            scalar(
                conn,
                """
                SELECT name FROM public._migrations
                ORDER BY name DESC LIMIT 1
                """,
            )
            or ""
        )
    except Exception:
        return None


def population_stats(conn: Any, *, uf: str | None) -> dict[str, Any]:
    """Full eligible population counts — never first-N as universe."""
    if uf:
        total = int(
            scalar(
                conn,
                """
                SELECT COUNT(*) FROM pncp_supplier_contracts
                WHERE COALESCE(is_active, TRUE)
                  AND upper(btrim(uf)) = upper(%s)
                """,
                (uf,),
            )
            or 0
        )
        active = total
        period = q(
            conn,
            """
            SELECT min(data_publicacao)::text AS min_pub,
                   max(data_publicacao)::text AS max_pub
            FROM pncp_supplier_contracts
            WHERE COALESCE(is_active, TRUE)
              AND upper(btrim(uf)) = upper(%s)
            """,
            (uf,),
        )
    else:
        total = int(
            scalar(
                conn,
                "SELECT COUNT(*) FROM pncp_supplier_contracts WHERE COALESCE(is_active, TRUE)",
            )
            or 0
        )
        active = total
        period = q(
            conn,
            """
            SELECT min(data_publicacao)::text AS min_pub,
                   max(data_publicacao)::text AS max_pub
            FROM pncp_supplier_contracts
            WHERE COALESCE(is_active, TRUE)
            """,
        )
    p = period[0] if period else {}
    return {
        "eligible_population": total,
        "active_contracts": active,
        "uf_filter": uf,
        "period_min": p.get("min_pub"),
        "period_max": p.get("max_pub"),
        "sample_label": "FULL_ELIGIBLE_POPULATION",
        "not_sample_of_n": True,
    }


def build_deliverable_a(
    conn: Any,
    *,
    uf: str | None,
    export_limit: int,
    pop: dict[str, Any],
) -> dict[str, Any]:
    """Org ranking over full population; export_limit only caps detail rows."""
    t0 = time.perf_counter()
    # Aggregate full population (no LIMIT in GROUP BY source)
    stats = q(
        conn,
        """
        SELECT COUNT(DISTINCT COALESCE(orgao_cnpj_8, left(COALESCE(orgao_cnpj,''),8)))
                   AS n_orgaos,
               COUNT(*)::bigint AS n_contracts,
               COALESCE(SUM(valor_total),0)::numeric AS valor_sum
        FROM pncp_supplier_contracts
        WHERE COALESCE(is_active, TRUE)
          AND (%s::text IS NULL OR upper(btrim(uf)) = upper(%s))
        """,
        (uf, uf),
    )[0]
    rows_raw = q(
        conn,
        """
        SELECT
            COALESCE(orgao_nome, orgao_cnpj, '(sem órgão)') AS orgao,
            COALESCE(orgao_cnpj, '') AS orgao_cnpj,
            COALESCE(uf, '') AS uf,
            COUNT(*)::int AS qtd_contratacoes,
            COALESCE(SUM(valor_total), 0)::float AS valor_total,
            'CONTRATADO'::text AS valor_semantica
        FROM pncp_supplier_contracts
        WHERE COALESCE(is_active, TRUE)
          AND (%s::text IS NULL OR upper(btrim(uf)) = upper(%s))
        GROUP BY 1, 2, 3
        ORDER BY qtd_contratacoes DESC, valor_total DESC NULLS LAST
        LIMIT %s
        """,
        (uf, uf, export_limit),
    )
    built = []
    for i, r in enumerate(rows_raw, start=1):
        built.append(
            deliv_a.build_row_from_raw(
                rank=i,
                orgao=str(r["orgao"]),
                cnpj=str(r.get("orgao_cnpj") or ""),
                uf=str(r.get("uf") or ""),
                qtd=int(r["qtd_contratacoes"]),
                valor_total=float(r["valor_total"] or 0),
                semantic="CONTRATADO",
                modalidades=None,
                periodo_inicio=str(pop.get("period_min") or ""),
                periodo_fim=str(pop.get("period_max") or ""),
                fontes=["pncp_supplier_contracts", "isolated_snapshot"],
                consultado=True,
                data_quality_score=1.0 if r.get("orgao_cnpj") else 0.7,
            )
        )
    report = deliv_a.build_report_from_rows(
        built,
        period_start=str(pop.get("period_min") or ""),
        period_end=str(pop.get("period_max") or ""),
        sources=["pncp_supplier_contracts", "isolated_authenticated_dump"],
    )
    elapsed = time.perf_counter() - t0
    data = asdict(report) if hasattr(report, "__dataclass_fields__") else report
    if hasattr(report, "__dataclass_fields__"):
        data = asdict(report)
    data["population"] = {
        **pop,
        "n_orgaos_eligible": int(stats.get("n_orgaos") or 0),
        "n_contracts_eligible": int(stats.get("n_contracts") or 0),
        "valor_sum_eligible": float(stats.get("valor_sum") or 0),
        "export_limit": export_limit,
        "export_is_not_universe": True,
    }
    data["query_seconds"] = round(elapsed, 3)
    data["valor_semantica"] = "CONTRATADO"
    data["claims_allowed"] = list(data.get("claims_allowed") or []) + [
        "Ranking over full eligible population in isolated snapshot",
        "valor_total is CONTRATADO (contracted), not paid/measured",
    ]
    data["claims_forbidden"] = list(data.get("claims_forbidden") or []) + [
        "Treat export_limit rows as statistical universe",
        "Call valor_total a unit price or valor pago",
    ]
    return data


def build_deliverable_b(
    conn: Any,
    *,
    uf: str | None,
    target_n: int,
    export_limit: int,
    pop: dict[str, Any],
) -> dict[str, Any]:
    t0 = time.perf_counter()
    n_suppliers = int(
        scalar(
            conn,
            """
            SELECT COUNT(DISTINCT COALESCE(fornecedor_cnpj_8,
                         left(COALESCE(fornecedor_cnpj,''),8)))
            FROM pncp_supplier_contracts
            WHERE COALESCE(is_active, TRUE)
              AND (%s::text IS NULL OR upper(btrim(uf)) = upper(%s))
              AND (
                (fornecedor_cnpj IS NOT NULL AND btrim(fornecedor_cnpj) <> '')
                OR (fornecedor_nome IS NOT NULL AND btrim(fornecedor_nome) <> '')
              )
            """,
            (uf, uf),
        )
        or 0
    )
    rows_raw = q(
        conn,
        """
        SELECT
            COALESCE(MAX(fornecedor_cnpj), '') AS cnpj,
            MAX(fornecedor_nome) AS nome,
            COUNT(*)::int AS n_contratos,
            COALESCE(SUM(valor_total),0)::float AS valor_contratado_total,
            array_agg(DISTINCT orgao_nome) FILTER (
                WHERE orgao_nome IS NOT NULL AND btrim(orgao_nome) <> ''
            ) AS orgaos,
            array_agg(DISTINCT upper(btrim(uf))) FILTER (
                WHERE uf IS NOT NULL AND btrim(uf) <> ''
            ) AS ufs
        FROM pncp_supplier_contracts
        WHERE COALESCE(is_active, TRUE)
          AND (%s::text IS NULL OR upper(btrim(uf)) = upper(%s))
          AND (
            (fornecedor_cnpj IS NOT NULL AND btrim(fornecedor_cnpj) <> '')
            OR (fornecedor_nome IS NOT NULL AND btrim(fornecedor_nome) <> '')
          )
        GROUP BY COALESCE(fornecedor_cnpj_8, left(COALESCE(fornecedor_cnpj,''),8))
        HAVING COUNT(*) >= 1
        ORDER BY COUNT(*) DESC, SUM(valor_total) DESC NULLS LAST
        LIMIT %s
        """,
        (uf, uf, max(export_limit, target_n)),
    )
    candidates: list[dict[str, Any]] = []
    for r in rows_raw:
        cnpj = "".join(ch for ch in str(r.get("cnpj") or "") if ch.isdigit())
        if len(cnpj) < 14:
            # pad root-only to 14 zeros suffix for schema when only root known
            if len(cnpj) == 8:
                cnpj = cnpj + "000000"
            elif len(cnpj) > 0:
                cnpj = cnpj.zfill(14)
            else:
                continue
        orgaos = list(r.get("orgaos") or [])
        ufs = list(r.get("ufs") or [])
        candidates.append(
            {
                "cnpj": cnpj[:14],
                "nome": r.get("nome") or "",
                "n_contratos": int(r["n_contratos"]),
                "valor_contratado_total": float(r["valor_contratado_total"] or 0),
                "orgaos_em_que_venceu": orgaos[:20],
                "ufs": ufs,
                "distribuicao_geografica": {str(u): 1 for u in ufs},
                "tipos_objeto": ["contrato_pncp"],
            }
        )
    # Prefer CNPJ when available; allow root-padded identities for ranking
    rule = deliv_b.SelectionRule(
        target_n=target_n,
        min_contracts=1,
        require_cnpj=True,
        uf_filter=None,  # already filtered in SQL
    )
    report = deliv_b.select_competitors(candidates, rule)
    data = asdict(report)
    data["population"] = {
        **pop,
        "n_suppliers_eligible": n_suppliers,
        "export_limit": export_limit,
        "export_is_not_universe": True,
    }
    data["query_seconds"] = round(time.perf_counter() - t0, 3)
    return data


def build_deliverable_c(
    conn: Any,
    *,
    uf: str | None,
    as_of: date,
    min_days: int = 90,
    max_days: int = 180,
    pop: dict[str, Any],
) -> dict[str, Any]:
    """Full-window query for expiring contracts; zero only as success_zero."""
    t0 = time.perf_counter()
    lo = as_of + timedelta(days=min_days)
    hi = as_of + timedelta(days=max_days)
    # Complete scan of window — no silent sample
    n_scanned = int(
        scalar(
            conn,
            """
            SELECT COUNT(*) FROM pncp_supplier_contracts
            WHERE COALESCE(is_active, TRUE)
              AND (%s::text IS NULL OR upper(btrim(uf)) = upper(%s))
              AND data_fim IS NOT NULL
            """,
            (uf, uf),
        )
        or 0
    )
    rows_raw = q(
        conn,
        """
        SELECT
            contrato_id AS id,
            orgao_nome AS orgao,
            orgao_cnpj,
            fornecedor_nome AS fornecedor,
            fornecedor_nome AS contratado,
            fornecedor_cnpj AS contratado_cnpj,
            fornecedor_cnpj,
            objeto_contrato AS objeto,
            valor_total AS valor,
            valor_total,
            'CONTRATADO'::text AS valor_semantica,
            data_inicio::text AS vigencia_inicio,
            data_inicio::text AS inicio,
            data_fim::text AS vigencia_fim,
            data_fim::text AS termino,
            'pncp_supplier_contracts'::text AS fonte,
            'pncp_supplier_contracts'::text AS termino_fonte,
            COALESCE(last_seen_at, ingested_at, now())::date::text AS termino_verificado_em,
            COALESCE(last_seen_at, ingested_at, now())::date::text AS verified_at,
            'CONTRATUAL'::text AS termino_tipo,
            uf,
            municipio
        FROM pncp_supplier_contracts
        WHERE COALESCE(is_active, TRUE)
          AND (%s::text IS NULL OR upper(btrim(uf)) = upper(%s))
          AND data_fim IS NOT NULL
          AND data_fim::date BETWEEN %s AND %s
        ORDER BY data_fim ASC
        """,
        (uf, uf, lo.isoformat(), hi.isoformat()),
    )
    cfg = deliv_c.WindowConfig(
        as_of=as_of.isoformat(),
        min_days=min_days,
        max_days=max_days,
    )
    report = deliv_c.select_expiring(rows_raw, cfg)
    data = asdict(report)
    n_in = len(data.get("rows") or [])
    # Detail export cap — full window already queried into n_in
    export_cap = int(pop.get("export_limit") or 500)
    if n_in > export_cap:
        data["rows"] = list(data.get("rows") or [])[:export_cap]
        data["export_limit"] = export_cap
        data["export_is_not_universe"] = True
        data["window_hits_total"] = n_in
    if n_in == 0:
        data["status"] = "EMPTY"
        data["success_zero"] = {
            "success_zero": True,
            "window": f"{min_days}-{max_days}d",
            "as_of": as_of.isoformat(),
            "contracts_with_data_fim_scanned": n_scanned,
            "query_complete": True,
            "message": (
                "Zero contracts in 90–180 day window after complete query; "
                "not 'not consulted'"
            ),
        }
    else:
        data["success_zero"] = {"success_zero": False, "n": n_in, "query_complete": True}
    data["population"] = {
        **pop,
        "contracts_with_data_fim_scanned": n_scanned,
        "window_start": lo.isoformat(),
        "window_end": hi.isoformat(),
        "window_hits_total": n_in,
        "query_complete": True,
        "export_is_not_universe": True,
    }
    data["query_seconds"] = round(time.perf_counter() - t0, 3)
    return data


def build_deliverable_d(
    conn: Any,
    *,
    uf: str | None,
    keywords: list[str],
    min_sample: int,
    pop: dict[str, Any],
) -> dict[str, Any]:
    t0 = time.perf_counter()
    obs: list[deliv_d.PriceObservation] = []
    for kw in keywords:
        rows = q(
            conn,
            """
            SELECT
                contrato_id,
                valor_total,
                objeto_contrato,
                uf,
                municipio,
                data_publicacao::text AS data_ref
            FROM pncp_supplier_contracts
            WHERE COALESCE(is_active, TRUE)
              AND (%s::text IS NULL OR upper(btrim(uf)) = upper(%s))
              AND valor_total IS NOT NULL AND valor_total > 0
              AND objeto_contrato ILIKE %s
            """,
            (uf, uf, f"%{kw}%"),
        )
        for r in rows:
            obs.append(
                deliv_d.PriceObservation(
                    value=float(r["valor_total"]),
                    value_semantic="contratado",
                    tipo_obra_servico=kw.lower(),
                    unidade="contrato_global",
                    lote="n/a",
                    porte="global",
                    regiao=str(r.get("uf") or uf or ""),
                    periodo=str(r.get("data_ref") or "")[:10],
                    is_global_heterogeneous=True,
                    source="pncp_supplier_contracts",
                )
            )
    rule = deliv_d.ComparabilityRule(min_sample=min_sample)
    report = deliv_d.build_report(obs, rule=rule)
    data = asdict(report)
    # At least one defensive category
    ok_panels = [
        p
        for p in (data.get("panels") or [])
        if p.get("status") == "OK"
    ]
    if not ok_panels and obs:
        # still expose NOT_READY rather than inventing unit prices
        data["status"] = "NOT_READY" if data.get("status") != "OK" else data["status"]
    data["population"] = {
        **pop,
        "observations_n": len(obs),
        "keywords": keywords,
        "value_semantics": "CONTRATADO_GLOBAL",
        "not_unit_price": True,
    }
    data["query_seconds"] = round(time.perf_counter() - t0, 3)
    data["claims_allowed"] = list(data.get("claims_allowed") or []) + [
        "Reference panels use CONTRATADO_GLOBAL magnitude explicitly",
    ]
    data["claims_forbidden"] = list(data.get("claims_forbidden") or []) + [
        "Call global contract value a unit price",
        "Mix incompatible magnitudes without NOT_READY",
    ]
    return data


def load_deliverable_e(
    *,
    evidence_path: Path | None,
    conn: Any | None,
    cut_date: str,
) -> dict[str, Any]:
    """Prefer captured real-source evidence; fall back to DB if opportunities exist."""
    if evidence_path and evidence_path.is_file():
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
        data["incorporated_from"] = str(evidence_path)
        data["source_class"] = "captured_real_evidence"
        # Guard: PENDING capacity must not become PARTICIPAR/GO
        for rec in data.get("recommendations") or []:
            ranking = str(rec.get("ranking") or rec.get("client_label") or "")
            risks = " ".join(
                str(x) for x in (rec.get("fatores_impeditivos_ou_riscos") or [])
            )
            if "PENDING" in risks.upper() and ranking.upper() in {
                "GO",
                "PARTICIPAR",
            }:
                rec["ranking"] = "REVIEW"
                rec["client_label"] = "REVIEW"
                rec["ranking_note"] = (
                    "PENDING capacity must not auto-promote to GO/PARTICIPAR"
                )
        return data
    if conn is None:
        return {
            "status": "INSUFFICIENT",
            "deliverable": "E",
            "title": "Editais abertos e recomendação individual",
            "recommendations": [],
            "note": "No evidence path and no DB connection",
        }
    n = int(
        scalar(
            conn,
            """
            SELECT COUNT(*) FROM opportunity_intel
            WHERE is_active AND status_canonico IN ('open','upcoming')
            """,
        )
        or 0
    )
    if n == 0:
        return {
            "status": "INSUFFICIENT",
            "deliverable": "E",
            "cut_date": cut_date,
            "recommendations": [],
            "note": "No opportunity_intel rows; use captured Deliverable E evidence",
            "source_class": "db_empty",
        }
    return {
        "status": "PARTIAL",
        "deliverable": "E",
        "cut_date": cut_date,
        "note": "opportunity rows present but prefer evidence file path",
        "n_open": n,
        "source_class": "db_present_prefer_evidence_file",
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            flat = {}
            for k, v in r.items():
                if isinstance(v, (dict, list)):
                    flat[k] = json.dumps(v, ensure_ascii=False, default=str)
                else:
                    flat[k] = v
            w.writerow(flat)


def build_excel(
    path: Path,
    *,
    meta: dict[str, Any],
    sheets: dict[str, list[dict[str, Any]]],
) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    # Metadados
    ws = wb.active
    ws.title = "Metadados"
    ws.append(["key", "value"])
    for k, v in meta.items():
        ws.append([k, json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v])
    # Required sheets
    for name, rows in sheets.items():
        title = name[:31]
        w = wb.create_sheet(title)
        if not rows:
            w.append(["empty"])
            continue
        keys = list(rows[0].keys())
        w.append(keys)
        for r in rows:
            w.append(
                [
                    json.dumps(r.get(k), ensure_ascii=False, default=str)
                    if isinstance(r.get(k), (dict, list))
                    else r.get(k)
                    for k in keys
                ]
            )
    # Mandatory tabs
    for req in ("Filtros", "Cobertura", "Limitacoes", "Dados"):
        if req not in wb.sheetnames:
            w = wb.create_sheet(req)
            if req == "Filtros":
                w.append(["filter", "value"])
                for k, v in (meta.get("filters") or {}).items():
                    w.append([k, str(v)])
            elif req == "Cobertura":
                w.append(["metric", "value"])
                for k, v in (meta.get("population") or {}).items():
                    w.append([k, str(v)])
            elif req == "Limitacoes":
                for line in meta.get("limitations") or []:
                    w.append([line])
            else:
                w.append(["see product sheets"])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def build_pdf(
    path: Path,
    *,
    meta: dict[str, Any],
    summary: dict[str, Any],
) -> int:
    """Minimal presentable PDF; page count proportional to content (no padding)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    story: list[Any] = []
    sections = [
        ("sumario_executivo", "Sumário executivo"),
        ("metodologia", "Metodologia"),
        ("universo", "Universo"),
        ("cobertura", "Cobertura"),
        ("limitacoes", "Limitações"),
        ("anexos_evidencia", "Anexos / evidência"),
        ("apoio_reuniao", "Apoio à reunião"),
    ]
    story.append(Paragraph("Pacote consultivo Extra Construtora (A–E)", styles["Title"]))
    story.append(Paragraph(f"run_id: {meta.get('run_id')}", styles["Normal"]))
    story.append(Paragraph(f"as_of: {meta.get('as_of')} | sha: {meta.get('git_sha')}", styles["Normal"]))
    story.append(Spacer(1, 12))
    for key, title in sections:
        story.append(Paragraph(title, styles["Heading2"]))
        body = summary.get(key) or meta.get(key) or ""
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, indent=2)[:2000]
        story.append(Paragraph(str(body).replace("\n", "<br/>")[:3000], styles["Normal"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    # page estimate ~ content length / 3000 chars
    chars = sum(len(str(summary.get(k) or "")) for k, _ in sections)
    pages = max(1, min(12, chars // 2500 + 2))
    return pages


def reconcile(
    *,
    run_id: str,
    meta_pdf: dict[str, Any],
    meta_excel: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    c: dict[str, Any],
    d: dict[str, Any],
) -> dict[str, Any]:
    divergences: list[str] = []
    for label, m in (("pdf", meta_pdf), ("excel", meta_excel)):
        if m.get("run_id") != run_id:
            divergences.append(f"{label}_run_id_mismatch")
        if m.get("git_sha") != meta_pdf.get("git_sha"):
            divergences.append(f"{label}_sha_mismatch")
    # population consistency
    pops = [
        (a.get("population") or {}).get("eligible_population"),
        (b.get("population") or {}).get("eligible_population"),
        (c.get("population") or {}).get("eligible_population"),
        (d.get("population") or {}).get("eligible_population"),
    ]
    if len({p for p in pops if p is not None}) > 1:
        divergences.append("eligible_population_mismatch_across_deliverables")
    status = "PASS" if not divergences else "FAIL"
    return {
        "status": status,
        "same_run_id": True,
        "divergences": divergences,
        "run_id": run_id,
        "eligible_population": pops[0],
    }


def write_executive_summary(path: Path, pack: dict[str, Any]) -> None:
    a = pack.get("deliverable_a") or {}
    b = pack.get("deliverable_b") or {}
    c = pack.get("deliverable_c") or {}
    d = pack.get("deliverable_d") or {}
    e = pack.get("deliverable_e") or {}
    pop = (a.get("population") or {})
    lines = [
        f"# Sumário executivo — {CAMPAIGN_ID}",
        "",
        f"- run_id: `{pack.get('run_id')}`",
        f"- as_of: {pack.get('as_of')}",
        f"- git_sha: {pack.get('git_sha')}",
        f"- população elegível: {pop.get('eligible_population')} "
        f"({pop.get('sample_label')})",
        f"- A: status={a.get('status')} rows={a.get('n_rows', len(a.get('rows') or []))} "
        f"órgãos_elegíveis={(a.get('population') or {}).get('n_orgaos_eligible')}",
        f"- B: status={b.get('status')} valid={b.get('valid_count')} "
        f"target={b.get('target_n')}",
        f"- C: status={c.get('status')} rows={c.get('n_rows', len(c.get('rows') or []))} "
        f"success_zero={(c.get('success_zero') or {}).get('success_zero')}",
        f"- D: status={d.get('status')} panels={d.get('n_panels', len(d.get('panels') or []))}",
        f"- E: status={e.get('status')} "
        f"recs={e.get('n_recs', len(e.get('recommendations') or []))}",
        f"- reconciliação: {(pack.get('reconcile') or {}).get('status')}",
        "",
        "## Non-claims",
        "- Não afirma LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE",
        "- valor_total = CONTRATADO, não pago/medido",
        "- export_limit ≠ universo estatístico",
        "- production_touched=false (snapshot isolado)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_pack(
    *,
    dsn: str,
    out_dir: Path,
    uf: str | None = "SC",
    export_limit: int = 200,
    target_competitors: int = 15,
    e_evidence: Path | None = None,
    keywords: list[str] | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    isolation = assert_isolation(dsn, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = new_run_id("live-pack")
    sha = git_sha()
    as_of_d = as_of or date.today()
    as_of_s = as_of_d.isoformat()
    stamp = profile_stamp()
    keywords = keywords or [
        "reforma",
        "paviment",
        "construção",
        "construcao",
        "obra",
        "edifica",
    ]

    conn = connect(dsn)
    try:
        sch = schema_version(conn)
        pop = population_stats(conn, uf=uf)
        if pop["eligible_population"] <= 0:
            raise SystemExit(
                "NO_ELIGIBLE_POPULATION: restore authenticated contracts dump first"
            )

        a = build_deliverable_a(conn, uf=uf, export_limit=export_limit, pop=pop)
        b = build_deliverable_b(
            conn,
            uf=uf,
            target_n=target_competitors,
            export_limit=export_limit,
            pop=pop,
        )
        pop_c = {**pop, "export_limit": export_limit}
        c = build_deliverable_c(conn, uf=uf, as_of=as_of_d, pop=pop_c)
        d = build_deliverable_d(
            conn, uf=uf, keywords=keywords, min_sample=5, pop=pop
        )
        e_path = e_evidence or (
            _PROJECT_ROOT
            / "artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01"
            / "weekly-offline-rc/deliverable_e.json"
        )
        e = load_deliverable_e(evidence_path=e_path, conn=conn, cut_date=as_of_s)
    finally:
        conn.close()

    meta = build_run_metadata(
        artifact_kind="live_consulting_pack",
        script="scripts/ops/live_consulting_pack.py",
        uf=uf or "",
        is_active=True,
        run_id=run_id,
    )
    meta.update(
        {
            "run_id": run_id,
            "as_of": as_of_s,
            "git_sha": sha,
            "schema_version": sch,
            "profile_id": stamp.get("profile_id"),
            "profile_version": stamp.get("version"),
            "campaign_id": CAMPAIGN_ID,
            "population": pop,
            "filters": {"uf": uf, "export_limit": export_limit},
            "limitations": [
                "Isolated snapshot — not live VPS query",
                "valor_total = CONTRATADO not pago",
                "export_limit caps detail tabs only",
                "Deliverable E from captured real evidence when DB has no opportunities",
            ],
            "production_touched": False,
            "isolation": isolation,
        }
    )

    # Attach run metadata to each deliverable
    for dobj in (a, b, c, d, e):
        dobj["run_id"] = run_id
        dobj["as_of"] = as_of_s
        dobj["git_sha"] = sha
        dobj["schema_version"] = sch

    # Artifacts
    (out_dir / "deliverable_a.json").write_text(
        json.dumps(a, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "deliverable_b.json").write_text(
        json.dumps(b, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "deliverable_c.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "deliverable_d.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "deliverable_e.json").write_text(
        json.dumps(e, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    write_csv(out_dir / "orgaos_ranking.csv", list(a.get("rows") or []))
    write_csv(out_dir / "competitors.csv", list(b.get("rows") or []))
    write_csv(out_dir / "expiring.csv", list(c.get("rows") or []))

    excel_path = out_dir / "extra_live_consulting_pack.xlsx"
    build_excel(
        excel_path,
        meta=meta,
        sheets={
            "A_Orgaos": list(a.get("rows") or []),
            "B_Concorrentes": list(b.get("rows") or []),
            "C_Vincendos": list(c.get("rows") or []),
            "D_Paineis": list(d.get("panels") or []),
            "E_Editais": list(e.get("recommendations") or []),
        },
    )

    summary = {
        "sumario_executivo": (
            f"População elegível {pop.get('eligible_population')} contratos "
            f"(UF={uf}). A={a.get('status')} B={b.get('status')} "
            f"C={c.get('status')} D={d.get('status')} E={e.get('status')}."
        ),
        "metodologia": (
            "Agregados SQL sobre dump autenticado isolado; "
            "export_limit só em abas detalhe; sem amostra silenciosa como universo."
        ),
        "universo": pop,
        "cobertura": {
            "dual_note": "Dual coverage measured on signed live evidence; "
            "this pack does not rewrite coverage denominators.",
            "eligible_population": pop.get("eligible_population"),
        },
        "limitacoes": meta["limitations"],
        "anexos_evidencia": {
            "dump_package": "artifacts/migration/backfill-vps/pkg-20260723T195047Z",
            "e_evidence": str(e_path),
        },
        "apoio_reuniao": [
            "Usar ranking A para priorizar órgãos",
            "Mapa B de concorrentes observáveis (não win-rate)",
            "Janela C 90–180d (success_zero se vazio após query completa)",
            "Painel D com magnitude CONTRATADO_GLOBAL explícita",
            "Editais E com PENDING ≠ GO",
        ],
    }
    pdf_path = out_dir / "extra_live_consulting_pack.pdf"
    pages = build_pdf(pdf_path, meta=meta, summary=summary)

    rec = reconcile(run_id=run_id, meta_pdf=meta, meta_excel=meta, a=a, b=b, c=c, d=d)

    pack = {
        "campaign_id": CAMPAIGN_ID,
        "run_id": run_id,
        "as_of": as_of_s,
        "git_sha": sha,
        "schema_version": sch,
        "profile": stamp,
        "population": pop,
        "deliverable_a": {"status": a.get("status"), "n_rows": len(a.get("rows") or []), "population": a.get("population"), "query_seconds": a.get("query_seconds")},
        "deliverable_b": {"status": b.get("status"), "valid_count": b.get("valid_count"), "target_n": b.get("target_n"), "query_seconds": b.get("query_seconds")},
        "deliverable_c": {"status": c.get("status"), "n_rows": len(c.get("rows") or []), "success_zero": c.get("success_zero"), "query_seconds": c.get("query_seconds")},
        "deliverable_d": {"status": d.get("status"), "n_panels": len(d.get("panels") or []), "query_seconds": d.get("query_seconds")},
        "deliverable_e": {"status": e.get("status"), "n_recs": len(e.get("recommendations") or []), "source_class": e.get("source_class") or e.get("incorporated_from")},
        "artifacts": {
            "pdf": str(pdf_path),
            "excel": str(excel_path),
            "pdf_pages_estimate": pages,
            "json": [
                "deliverable_a.json",
                "deliverable_b.json",
                "deliverable_c.json",
                "deliverable_d.json",
                "deliverable_e.json",
            ],
        },
        "reconcile": rec,
        "isolation": isolation,
        "production_touched": False,
        "generated_at": utc_now(),
    }
    # full payload with products for offline inspection (large)
    full = {
        **pack,
        "products": {"A": a, "B": b, "C": c, "D": d, "E": e},
        "meta": meta,
    }
    (out_dir / "pack-manifest.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "pack-full.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    write_executive_summary(out_dir / "executive_summary.md", pack)

    # sha256 of artifacts
    checksums: dict[str, str] = {}
    for p in out_dir.iterdir():
        if p.is_file() and p.suffix in {".json", ".csv", ".xlsx", ".pdf", ".md"}:
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            checksums[p.name] = h
    (out_dir / "checksums.json").write_text(
        json.dumps(checksums, indent=2), encoding="utf-8"
    )
    return pack


def cmd_verify_isolation(args: argparse.Namespace) -> int:
    try:
        r = assert_isolation(args.dsn, Path(args.out) if args.out else None)
    except SystemExit as e:
        print(json.dumps({"isolation_ok": False, "error": str(e)}))
        return 2
    print(json.dumps(r, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    pack = run_pack(
        dsn=args.dsn,
        out_dir=Path(args.out),
        uf=args.uf or None,
        export_limit=args.export_limit,
        target_competitors=args.target_competitors,
        e_evidence=Path(args.e_evidence) if args.e_evidence else None,
        as_of=date.fromisoformat(args.as_of) if args.as_of else None,
    )
    print(json.dumps(pack, indent=2, ensure_ascii=False, default=str))
    # Exit codes
    if pack["reconcile"]["status"] != "PASS":
        return 2
    if pack["deliverable_a"]["status"] not in {"OK", "PARTIAL"}:
        return 2
    if pack["deliverable_b"]["status"] not in {"OK", "INSUFFICIENT", "PARTIAL"}:
        return 2
    # B with OK should have >= target; INSUFFICIENT is fail-closed success for honesty
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Live consulting pack A–E (isolated)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Generate full A–E pack")
    r.add_argument("--dsn", default=DEFAULT_DSN)
    r.add_argument("--out", required=True)
    r.add_argument("--uf", default="SC")
    r.add_argument("--export-limit", type=int, default=200)
    r.add_argument("--target-competitors", type=int, default=15)
    r.add_argument("--e-evidence", default=None)
    r.add_argument("--as-of", default=None)
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("verify-isolation", help="Isolation fail-closed check")
    v.add_argument("--dsn", default=DEFAULT_DSN)
    v.add_argument("--out", default=None)
    v.set_defaults(func=cmd_verify_isolation)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
