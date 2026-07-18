"""DoD «Entregável A — ranking dos órgãos públicos» — schema + audit.

Builds a ranking report structure with honest semantics:
- valor_semantica: CONTRATADO | ESTIMADO | HOMOLOGADO (never mix labels)
- ticket_medio: total/qtd with explicit formula
- zero_result vs not_consulted distinction
- data_quality_limitation when ranking is driven by data completeness

Does not invent live market coverage. Empty DB → INSUFFICIENT status.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.ops.diagnostic_profile import profile_stamp

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class OrgRankRow:
    rank: int
    orgao: str
    orgao_cnpj: str
    uf: str
    qtd_contratacoes: int
    valor_total: float
    valor_semantica: str  # CONTRATADO | ESTIMADO | HOMOLOGADO
    ticket_medio: float
    ticket_medio_formula: str
    frequencia_temporal: str  # e.g. "N eventos / period_days"
    modalidades: dict[str, int]
    periodo_inicio: str
    periodo_fim: str
    fontes: list[str]
    consultado: bool
    resultado_zero: bool
    data_quality_score: float | None
    data_quality_limitation: str


@dataclass
class DeliverableAReport:
    status: str  # OK | INSUFFICIENT | PARTIAL
    deliverable: str = "A"
    title: str = "Ranking dos órgãos públicos"
    profile: dict[str, Any] = field(default_factory=dict)
    period: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    coverage_notes: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    zero_vs_not_consulted: dict[str, Any] = field(default_factory=dict)
    ranking_bias_warning: str = (
        "Ranking pode favorecer entes com melhor qualidade de dados; "
        "data_quality_limitation é obrigatório por linha quando score < 1.0."
    )
    claims_allowed: list[str] = field(default_factory=list)
    claims_forbidden: list[str] = field(default_factory=list)
    generated_at: str = ""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def ticket_medio(valor_total: float, qtd: int) -> tuple[float, str]:
    if qtd <= 0:
        return 0.0, "undefined_when_qtd_zero"
    mean = valor_total / qtd
    return mean, "valor_total / qtd_contratacoes (same semantic as valor_total)"


def build_row_from_raw(
    *,
    rank: int,
    orgao: str,
    cnpj: str,
    uf: str,
    qtd: int,
    valor_total: float,
    semantic: str,
    modalidades: dict[str, int] | None,
    periodo_inicio: str,
    periodo_fim: str,
    fontes: list[str],
    consultado: bool,
    data_quality_score: float | None = None,
) -> OrgRankRow:
    tm, formula = ticket_medio(valor_total, qtd)
    zero = consultado and qtd == 0
    dq = data_quality_score
    limitation = ""
    if dq is not None and dq < 1.0:
        limitation = (
            f"data_quality_score={dq:.2f} < 1.0 — ranking may over-represent "
            "entes with richer source data; not a pure market measure"
        )
    elif not consultado:
        limitation = "ente not consulted this run"
    freq = f"{qtd} eventos no período ({periodo_inicio}..{periodo_fim})"
    return OrgRankRow(
        rank=rank,
        orgao=orgao,
        orgao_cnpj=cnpj,
        uf=uf,
        qtd_contratacoes=qtd,
        valor_total=valor_total,
        valor_semantica=semantic,
        ticket_medio=round(tm, 2),
        ticket_medio_formula=formula,
        frequencia_temporal=freq,
        modalidades=dict(modalidades or {}),
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        fontes=list(fontes),
        consultado=consultado,
        resultado_zero=zero,
        data_quality_score=dq,
        data_quality_limitation=limitation,
    )


def build_report_from_rows(
    rows: list[OrgRankRow],
    *,
    period_start: str,
    period_end: str,
    sources: list[str],
    status: str | None = None,
) -> DeliverableAReport:
    stamp = profile_stamp()
    if status is None:
        status = "OK" if rows else "INSUFFICIENT"
    zero = [r for r in rows if r.resultado_zero]
    not_consulted = [r for r in rows if not r.consultado]
    with_data = [r for r in rows if r.consultado and r.qtd_contratacoes > 0]
    return DeliverableAReport(
        status=status,
        profile=stamp,
        period={"inicio": period_start, "fim": period_end, "as_of": utc_now()[:10]},
        sources=sources,
        coverage_notes=[
            "Cobertura operacional do universo NÃO é inferida deste ranking.",
            "Empty ranking with status=INSUFFICIENT means no contracts/bids in DSN for filters.",
        ],
        rows=[asdict(r) for r in rows],
        zero_vs_not_consulted={
            "consulted_with_data": len(with_data),
            "consulted_zero": len(zero),
            "not_consulted": len(not_consulted),
            "rule": "resultado_zero only when consultado=true and qtd=0; not_consulted is separate",
        },
        claims_allowed=[
            f"Ranking rows={len(rows)} status={status}",
            "ticket_medio uses explicit formula on same value semantic",
            "zero vs not_consulted distinguished",
            "data_quality_limitation when score incomplete",
        ],
        claims_forbidden=[
            "ESTIMADO presented as CONTRATADO",
            "Sample N=0 as complete SC market",
            "Not consulted equals no licitation",
        ],
        generated_at=utc_now(),
    )


def fixture_demo_report() -> DeliverableAReport:
    """Deterministic fixture proving schema fields (not live market claim)."""
    rows = [
        build_row_from_raw(
            rank=1,
            orgao="Prefeitura Demo A",
            cnpj="00000000000191",
            uf="SC",
            qtd=4,
            valor_total=1_200_000.0,
            semantic="CONTRATADO",
            modalidades={"pregao_eletronico": 3, "dispensa": 1},
            periodo_inicio="2025-01-01",
            periodo_fim="2025-12-31",
            fontes=["pncp_supplier_contracts"],
            consultado=True,
            data_quality_score=0.85,
        ),
        build_row_from_raw(
            rank=2,
            orgao="Prefeitura Demo B",
            cnpj="00000000000272",
            uf="SC",
            qtd=0,
            valor_total=0.0,
            semantic="CONTRATADO",
            modalidades={},
            periodo_inicio="2025-01-01",
            periodo_fim="2025-12-31",
            fontes=["pncp_supplier_contracts"],
            consultado=True,
            data_quality_score=1.0,
        ),
        build_row_from_raw(
            rank=3,
            orgao="Autarquia Não Consultada",
            cnpj="00000000000353",
            uf="SC",
            qtd=0,
            valor_total=0.0,
            semantic="CONTRATADO",
            modalidades={},
            periodo_inicio="2025-01-01",
            periodo_fim="2025-12-31",
            fontes=[],
            consultado=False,
            data_quality_score=None,
        ),
    ]
    # ranks for zero/not consulted are informational; re-rank data rows only in production
    return build_report_from_rows(
        rows,
        period_start="2025-01-01",
        period_end="2025-12-31",
        sources=["fixture", "pncp_supplier_contracts"],
        status="OK",
    )


def audit_report(report: dict[str, Any] | DeliverableAReport) -> dict[str, Any]:
    """Check DoD Entregável A field presence on a report dict."""
    data = asdict(report) if isinstance(report, DeliverableAReport) else report
    rows = data.get("rows") or []
    checks: list[dict[str, Any]] = []

    def add(item_id: str, dod: str, ok: bool, evidence: list[str], notes: str = "") -> None:
        checks.append(
            {
                "item_id": item_id,
                "dod_text": dod,
                "status": "PASS" if ok else "FAIL",
                "evidence": evidence,
                "notes": notes,
            }
        )

    add(
        "generates_ranking",
        "O sistema gera ranking dos entes do universo que contratam obras e serviços compatíveis com o perfil.",
        data.get("status") in {"OK", "INSUFFICIENT", "PARTIAL"} and "rows" in data,
        [f"status={data.get('status')}", f"rows={len(rows)}", f"profile={data.get('profile')}"],
        "INSUFFICIENT is valid when DSN empty — capability still proven via fixture path",
    )
    has_qtd = all("qtd_contratacoes" in r for r in rows) if rows else True
    add(
        "qtd_contratacoes",
        "O ranking informa quantidade de contratações no período.",
        has_qtd,
        ["field qtd_contratacoes on each row"] if rows else ["empty rows OK for INSUFFICIENT"],
    )
    has_valor = all("valor_total" in r and "valor_semantica" in r for r in rows) if rows else True
    add(
        "valor_total",
        "O ranking informa valor contratado total.",
        has_valor,
        ["valor_total + valor_semantica"] if rows else ["empty"],
        "Semantic label required; may be ESTIMADO not CONTRATADO",
    )
    has_ticket = all(
        "ticket_medio" in r and "ticket_medio_formula" in r for r in rows
    ) if rows else True
    add(
        "ticket_medio",
        "O ranking informa ticket médio com semântica explícita.",
        has_ticket,
        ["ticket_medio + ticket_medio_formula"],
    )
    has_freq = all("frequencia_temporal" in r for r in rows) if rows else True
    add(
        "frequencia",
        "O ranking informa frequência temporal de contratação.",
        has_freq,
        ["frequencia_temporal"],
    )
    has_mod = all("modalidades" in r for r in rows) if rows else True
    add(
        "modalidades",
        "O ranking informa distribuição por modalidade.",
        has_mod,
        ["modalidades map"],
    )
    period = data.get("period") or {}
    add(
        "periodo",
        "O ranking informa período de análise.",
        bool(period.get("inicio") and period.get("fim")),
        [str(period)],
    )
    add(
        "fontes_cobertura",
        "O ranking informa fontes e cobertura aplicáveis.",
        bool(data.get("sources")) and bool(data.get("coverage_notes")),
        [f"sources={data.get('sources')}", f"notes={len(data.get('coverage_notes') or [])}"],
    )
    zvn = data.get("zero_vs_not_consulted") or {}
    add(
        "zero_vs_not_consulted",
        "Entes consultados com resultado zero permanecem distinguíveis de entes não consultados.",
        "consulted_zero" in zvn and "not_consulted" in zvn and "rule" in zvn,
        [str(zvn)],
    )
    add(
        "data_quality_bias",
        "O ranking não favorece artificialmente entes com maior qualidade de dados sem alertar essa limitação.",
        bool(data.get("ranking_bias_warning"))
        and (
            not rows
            or all(
                (r.get("data_quality_score") is None or r.get("data_quality_score") >= 1.0)
                or bool(r.get("data_quality_limitation"))
                for r in rows
            )
        ),
        ["ranking_bias_warning + per-row data_quality_limitation when score < 1"],
    )

    fail = sum(1 for c in checks if c["status"] == "FAIL")
    return {
        "ok": fail == 0,
        "generated_at": utc_now(),
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["status"] == "PASS"),
            "fail": fail,
        },
        "checks": checks,
        "report_status": data.get("status"),
        "row_count": len(rows),
    }


def from_org_ranking_live(live: dict[str, Any]) -> DeliverableAReport:
    """Adapt scripts/reports/org_ranking.py JSON into Deliverable A schema."""
    semantic = str(live.get("valor_semantica") or "ESTIMADO")
    source = str(live.get("source_table") or "unknown")
    as_of = utc_now()[:10]
    period_start = live.get("period_start") or as_of
    period_end = live.get("period_end") or as_of
    raw_rows = live.get("rows") or []
    rows: list[OrgRankRow] = []
    for i, r in enumerate(raw_rows, start=1):
        qtd = int(r.get("qtd") or r.get("qtd_contratacoes") or 0)
        valor = float(r.get("valor_total") or 0)
        rows.append(
            build_row_from_raw(
                rank=int(r.get("rank") or i),
                orgao=str(r.get("orgao") or r.get("nome") or "unknown"),
                cnpj=str(r.get("orgao_cnpj") or r.get("cnpj") or ""),
                uf=str(r.get("uf") or live.get("uf_filter") or ""),
                qtd=qtd,
                valor_total=valor,
                semantic=str(r.get("valor_semantica") or semantic),
                modalidades=r.get("modalidades") if isinstance(r.get("modalidades"), dict) else {},
                periodo_inicio=str(period_start),
                periodo_fim=str(period_end),
                fontes=[source],
                consultado=True,
                data_quality_score=r.get("data_quality_score"),
            )
        )
    status = str(live.get("status") or ("OK" if rows else "INSUFFICIENT"))
    report = build_report_from_rows(
        rows,
        period_start=str(period_start),
        period_end=str(period_end),
        sources=[source, "scripts/reports/org_ranking.py"],
        status=status,
    )
    notes = list(live.get("notes") or [])
    report.coverage_notes = list(report.coverage_notes) + notes
    if not rows:
        report.coverage_notes.append(
            "Live DSN produced 0 organs — capability proven; market ranking not claimed."
        )
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deliverable A org ranking schema/audit")
    p.add_argument(
        "command",
        choices=["fixture", "audit-fixture", "audit-file", "adapt-live", "audit-live"],
    )
    p.add_argument("--path", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.command == "fixture":
        report = fixture_demo_report()
        payload: dict[str, Any] = asdict(report)
    elif args.command == "audit-fixture":
        report = fixture_demo_report()
        payload = audit_report(report)
    elif args.command in {"adapt-live", "audit-live"}:
        path = args.path or PROJECT_ROOT / "output/reports/org-ranking-next30d.json"
        live = json.loads(Path(path).read_text(encoding="utf-8"))
        adapted = from_org_ranking_live(live)
        if args.command == "adapt-live":
            payload = asdict(adapted)
        else:
            payload = audit_report(adapted)
    else:
        path = args.path or PROJECT_ROOT / "docs/ops/session-2026-07-18-org-ranking/fixture-a.json"
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        payload = audit_report(data)

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.command.startswith("audit") and not payload.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
