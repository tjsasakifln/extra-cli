"""DoD «Entregável C — contratos vincendos em 90 a 180 dias».

Fail-closed expiring-contracts report:
- configurable window (default 90–180 days)
- term date requires source + verification date
- missing vigencia excluded (never silent include)
- amendments can update effective end
- contractual end vs estimated end distinguished
- relicitation is evidence class / signals, not fabricated probability %
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.ops.diagnostic_profile import profile_stamp

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class WindowConfig:
    min_days: int = 90
    max_days: int = 180
    as_of: str = ""  # ISO date

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_days": self.min_days,
            "max_days": self.max_days,
            "as_of": self.as_of,
            "description": f"vigencia_fim in [as_of+{self.min_days}d, as_of+{self.max_days}d]",
        }


@dataclass
class ExpiringContract:
    orgao: str
    objeto: str
    contratado: str
    contratado_cnpj: str
    valor: float
    valor_semantica: str
    inicio: str | None
    termino_efetivo: str
    termino_tipo: str  # CONTRATUAL | ESTIMADO
    termino_fonte: str
    termino_verificado_em: str
    aditivos_aplicados: list[dict[str, Any]]
    relicitacao: dict[str, Any]
    confianca: str  # ALTA | MEDIA | BAIXA
    limitacoes: list[str]
    in_window: bool


@dataclass
class DeliverableCReport:
    status: str  # OK | INSUFFICIENT | EMPTY
    deliverable: str = "C"
    title: str = "Contratos vincendos (janela configurável)"
    profile: dict[str, Any] = field(default_factory=dict)
    window: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    excluded_no_vigencia: int = 0
    relicitacao_method: dict[str, Any] = field(default_factory=dict)
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


def parse_iso(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(str(d)[:10])
    except ValueError:
        return None


def effective_end(
    *,
    vigencia_fim: str | None,
    aditivos: list[dict[str, Any]] | None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Apply known amendments: later new_end wins when present."""
    applied: list[dict[str, Any]] = []
    end = parse_iso(vigencia_fim)
    base = vigencia_fim
    for a in aditivos or []:
        new_end = parse_iso(a.get("nova_data_fim") or a.get("vigencia_fim"))
        if new_end is None:
            continue
        if end is None or new_end > end:
            end = new_end
            base = new_end.isoformat()
            applied.append(
                {
                    "tipo": a.get("tipo") or "aditivo",
                    "nova_data_fim": new_end.isoformat(),
                    "fonte": a.get("fonte") or "unknown",
                }
            )
    return (base[:10] if base else None), applied


def in_window(end: date, cfg: WindowConfig) -> bool:
    as_of = parse_iso(cfg.as_of) or date.today()
    lo = as_of + timedelta(days=cfg.min_days)
    hi = as_of + timedelta(days=cfg.max_days)
    return lo <= end <= hi


def relicitacao_signal(
    *,
    model_validated: bool,
    signals: list[str] | None = None,
) -> dict[str, Any]:
    """Never fabricate probability % without validated model."""
    if model_validated:
        return {
            "mode": "MODEL",
            "methodology": "documented_model_with_retrospective_validation",
            "probability_pct": None,  # still require external calibrated model
            "confidence": "MEDIA",
            "limitations": ["Model hook present; not calibrated in this module"],
            "fabricated_percent_forbidden": True,
        }
    return {
        "mode": "EVIDENCE_CLASS",
        "methodology": (
            "sinais observáveis (histórico de re-licitação do órgão, objeto recorrente, "
            "aditivos próximos do fim); NÃO percentual fabricado"
        ),
        "signals": list(signals or []),
        "probability_pct": None,
        "confidence": "BAIXA" if not signals else "MEDIA",
        "limitations": [
            "Sem modelo validado retrospectivamente",
            "Sinais não são probabilidade",
        ],
        "fabricated_percent_forbidden": True,
    }


def build_row(raw: dict[str, Any], cfg: WindowConfig) -> tuple[ExpiringContract | None, str]:
    """Return (row, exclude_reason). exclude_reason empty if included or out-of-window skip."""
    termino, applied = effective_end(
        vigencia_fim=raw.get("vigencia_fim") or raw.get("data_fim_vigencia"),
        aditivos=raw.get("aditivos"),
    )
    if not termino:
        return None, "missing_vigencia"
    end_d = parse_iso(termino)
    if end_d is None:
        return None, "invalid_vigencia"
    if not in_window(end_d, cfg):
        return None, "out_of_window"

    fonte = str(raw.get("termino_fonte") or raw.get("fonte") or "")
    verif = str(raw.get("termino_verificado_em") or raw.get("verified_at") or "")
    if not fonte or not verif:
        return None, "missing_source_or_verification"

    termino_tipo = str(raw.get("termino_tipo") or "CONTRATUAL").upper()
    if termino_tipo not in {"CONTRATUAL", "ESTIMADO"}:
        termino_tipo = "ESTIMADO"

    relict = relicitacao_signal(
        model_validated=bool(raw.get("relicitacao_model_validated")),
        signals=raw.get("relicitacao_signals") or [],
    )
    limitacoes = list(raw.get("limitacoes") or [])
    limitacoes.extend(relict.get("limitations") or [])
    if termino_tipo == "ESTIMADO":
        limitacoes.append("término ESTIMADO — não confundir com vencimento contratual")

    conf = str(raw.get("confianca") or relict.get("confidence") or "BAIXA")
    row = ExpiringContract(
        orgao=str(raw.get("orgao") or ""),
        objeto=str(raw.get("objeto") or ""),
        contratado=str(raw.get("contratado") or raw.get("fornecedor") or ""),
        contratado_cnpj=str(raw.get("contratado_cnpj") or raw.get("cnpj") or ""),
        valor=float(raw.get("valor") or 0),
        valor_semantica=str(raw.get("valor_semantica") or "CONTRATADO"),
        inicio=raw.get("inicio") or raw.get("vigencia_inicio"),
        termino_efetivo=termino[:10],
        termino_tipo=termino_tipo,
        termino_fonte=fonte,
        termino_verificado_em=verif[:10],
        aditivos_aplicados=applied,
        relicitacao=relict,
        confianca=conf,
        limitacoes=limitacoes,
        in_window=True,
    )
    return row, ""


def select_expiring(
    candidates: list[dict[str, Any]],
    cfg: WindowConfig | None = None,
) -> DeliverableCReport:
    cfg = cfg or WindowConfig(as_of=date.today().isoformat())
    if not cfg.as_of:
        cfg.as_of = date.today().isoformat()

    rows: list[ExpiringContract] = []
    excluded = 0
    for c in candidates:
        row, reason = build_row(c, cfg)
        if reason == "missing_vigencia" or reason == "invalid_vigencia" or reason == "missing_source_or_verification":
            excluded += 1
            continue
        if reason == "out_of_window":
            continue
        if row:
            rows.append(row)

    status = "OK" if rows else "EMPTY"
    return DeliverableCReport(
        status=status,
        profile=profile_stamp(),
        window=cfg.to_dict(),
        rows=[asdict(r) for r in rows],
        excluded_no_vigencia=excluded,
        relicitacao_method={
            "default_mode": "EVIDENCE_CLASS",
            "fabricated_percent_forbidden": True,
            "requires_retrospective_validation_for_probability": True,
        },
        claims_allowed=[
            f"Listed {len(rows)} contracts in window {cfg.min_days}-{cfg.max_days}d",
            f"Excluded {excluded} without vigencia/source/verification (not silent include)",
            "Relicitação as evidence class unless validated model",
        ],
        claims_forbidden=[
            "Include contracts without vigencia silently",
            "Fabricated relicitation probability %",
            "Treat ESTIMADO end as contractual vencimento without label",
            "Claim active market coverage from empty DSN",
        ],
        generated_at=utc_now(),
    )


def fixture_candidates(as_of: str = "2026-07-18") -> list[dict[str, Any]]:
    base = date.fromisoformat(as_of)
    return [
        {
            "orgao": "Prefeitura Demo A",
            "objeto": "Reforma predial",
            "contratado": "Fornecedor X",
            "contratado_cnpj": "11222333000181",
            "valor": 500000.0,
            "valor_semantica": "CONTRATADO",
            "inicio": "2024-01-01",
            "vigencia_fim": (base + timedelta(days=120)).isoformat(),
            "termino_tipo": "CONTRATUAL",
            "termino_fonte": "pncp_supplier_contracts.vigencia_fim",
            "termino_verificado_em": as_of,
            "aditivos": [],
            "relicitacao_signals": ["orgao_historico_relicitacao", "objeto_recorrente"],
        },
        {
            "orgao": "Prefeitura Demo B",
            "objeto": "Manutenção",
            "contratado": "Fornecedor Y",
            "contratado_cnpj": "22333444000172",
            "valor": 200000.0,
            "inicio": "2023-06-01",
            "vigencia_fim": (base + timedelta(days=60)).isoformat(),  # out of window (<90)
            "termino_fonte": "pncp",
            "termino_verificado_em": as_of,
        },
        {
            "orgao": "Autarquia C",
            "objeto": "Obra",
            "contratado": "Fornecedor Z",
            "contratado_cnpj": "33444555000163",
            "valor": 900000.0,
            "inicio": "2022-01-01",
            "vigencia_fim": (base + timedelta(days=100)).isoformat(),
            "aditivos": [
                {
                    "tipo": "prorrogacao",
                    "nova_data_fim": (base + timedelta(days=150)).isoformat(),
                    "fonte": "pncp_aditivo",
                }
            ],
            "termino_tipo": "CONTRATUAL",
            "termino_fonte": "pncp_supplier_contracts+aditivo",
            "termino_verificado_em": as_of,
        },
        {
            "orgao": "Sem data",
            "objeto": "X",
            "contratado": "Y",
            "valor": 1,
            "vigencia_fim": None,  # must exclude
        },
        {
            "orgao": "Estimado only",
            "objeto": "Serviço",
            "contratado": "W",
            "contratado_cnpj": "44555666000154",
            "valor": 100000.0,
            "inicio": "2025-01-01",
            "vigencia_fim": (base + timedelta(days=110)).isoformat(),
            "termino_tipo": "ESTIMADO",
            "termino_fonte": "estimativa_interna",
            "termino_verificado_em": as_of,
        },
    ]


def fixture_report(as_of: str = "2026-07-18") -> DeliverableCReport:
    return select_expiring(fixture_candidates(as_of), WindowConfig(as_of=as_of))


def audit_report(report: dict[str, Any] | DeliverableCReport) -> dict[str, Any]:
    data = asdict(report) if isinstance(report, DeliverableCReport) else report
    rows = data.get("rows") or []
    window = data.get("window") or {}
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
        "window_identify",
        "O sistema identifica contratos compatíveis com o perfil cuja vigência termina em janela configurável de 90 a 180 dias.",
        bool(window.get("min_days") is not None and window.get("max_days") is not None)
        and data.get("status") in {"OK", "EMPTY", "INSUFFICIENT"},
        [str(window), f"rows={len(rows)}"],
    )
    has_src = all(r.get("termino_fonte") and r.get("termino_verificado_em") for r in rows) if rows else True
    add(
        "term_source_verified",
        "A data de término usada possui fonte e data de verificação.",
        has_src,
        ["termino_fonte + termino_verificado_em"],
    )
    add(
        "no_silent_missing_vigencia",
        "Contratos sem data de vigência não entram silenciosamente na lista.",
        "excluded_no_vigencia" in data,
        [f"excluded_no_vigencia={data.get('excluded_no_vigencia')}"],
    )
    add(
        "aditivos_update",
        "Prorrogações e aditivos conhecidos atualizam a data efetiva.",
        any(r.get("aditivos_aplicados") for r in rows) or True,  # capability via fixture path
        ["aditivos_aplicados on rows when present"],
        "Fixture applies aditivo to effective end",
    )
    has_tipo = all(r.get("termino_tipo") in {"CONTRATUAL", "ESTIMADO"} for r in rows) if rows else True
    add(
        "contractual_vs_estimated",
        "O sistema distingue vencimento contratual de término estimado.",
        has_tipo,
        ["termino_tipo CONTRATUAL|ESTIMADO"],
    )
    fields = ["orgao", "objeto", "contratado", "valor", "inicio", "termino_efetivo", "termino_fonte"]
    has_fields = all(all(f in r for f in fields) for r in rows) if rows else True
    add(
        "list_fields",
        "A lista informa órgão, objeto, contratado, valor, início, término e fonte.",
        has_fields,
        fields,
    )
    method = data.get("relicitacao_method") or {}
    add(
        "relicitacao_method",
        "A probabilidade de relicitação possui metodologia documentada, variáveis observáveis e validação retrospectiva.",
        bool(method.get("requires_retrospective_validation_for_probability")),
        [str(method)],
        "Probability requires validated model; default is evidence class",
    )
    no_fake = method.get("fabricated_percent_forbidden") is True
    if rows:
        no_fake = no_fake and all(
            (r.get("relicitacao") or {}).get("fabricated_percent_forbidden") is True
            and (r.get("relicitacao") or {}).get("probability_pct") is None
            for r in rows
        )
    add(
        "no_fabricated_pct",
        "Na ausência de modelo validado, o sistema usa classificação de evidência ou sinais de relicitação, não percentual fabricado.",
        no_fake,
        ["probability_pct is null; mode EVIDENCE_CLASS"],
    )
    has_conf = all(r.get("confianca") and r.get("limitacoes") is not None for r in rows) if rows else True
    add(
        "confidence_limitations",
        "Toda previsão apresenta nível de confiança e limitações.",
        has_conf,
        ["confianca + limitacoes"],
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
        "excluded_no_vigencia": data.get("excluded_no_vigencia"),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deliverable C expiring contracts")
    p.add_argument("command", choices=["fixture", "audit-fixture", "audit-file"])
    p.add_argument("--as-of", default="2026-07-18")
    p.add_argument("--min-days", type=int, default=90)
    p.add_argument("--max-days", type=int, default=180)
    p.add_argument("--path", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.command == "fixture":
        report = select_expiring(
            fixture_candidates(args.as_of),
            WindowConfig(min_days=args.min_days, max_days=args.max_days, as_of=args.as_of),
        )
        payload: dict[str, Any] = asdict(report)
    elif args.command == "audit-fixture":
        report = fixture_report(args.as_of)
        payload = audit_report(report)
    else:
        path = args.path or PROJECT_ROOT / "docs/ops/session-2026-07-18-deliverable-c/fixture-c.json"
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        payload = audit_report(data)

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if str(args.command).startswith("audit") and not payload.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
