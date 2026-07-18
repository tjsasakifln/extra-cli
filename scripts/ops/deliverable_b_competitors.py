"""DoD «Entregável B — mapeamento de 15 concorrentes observáveis».

Reproducible selection of up to N supplier winners with honest labels:
- never pad the list with noise when N valid < target
- deságio only with comparable estimado+homologado on same certame/lote/item
- active contracts require vigencia + status evidence
- operational capacity is HYPOTHESIS unless evidence exists
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
DEFAULT_TARGET_N = 15


@dataclass
class SelectionRule:
    """Configurable, reproducible ranking rule for competitor selection."""

    target_n: int = DEFAULT_TARGET_N
    min_contracts: int = 1
    sort_keys: tuple[str, ...] = ("n_contratos", "valor_contratado_total")
    require_cnpj: bool = True
    uf_filter: str | None = "SC"
    # deságio never auto-filled
    allow_desagio_without_pair: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_n": self.target_n,
            "min_contracts": self.min_contracts,
            "sort_keys": list(self.sort_keys),
            "require_cnpj": self.require_cnpj,
            "uf_filter": self.uf_filter,
            "allow_desagio_without_pair": self.allow_desagio_without_pair,
            "description": (
                f"Top {self.target_n} by {','.join(self.sort_keys)} "
                f"with min_contracts>={self.min_contracts}"
                + ("; require CNPJ" if self.require_cnpj else "")
            ),
        }


@dataclass
class CompetitorRow:
    rank: int
    cnpj: str
    nome: str
    identidade_canonica: str
    n_contratos: int
    valor_contratado_total: float
    valor_semantica: str  # CONTRATADO only for totals from contracts
    ticket_contratado_medio: float
    ticket_formula: str
    orgaos_em_que_venceu: list[str]
    distribuicao_geografica: dict[str, int]
    tipos_objeto: list[str]
    desagio: float | None
    desagio_status: str  # PRESENTED | NOT_APPLICABLE | INSUFFICIENT_PAIR
    desagio_evidence: str
    contratos_ativos: list[dict[str, Any]]
    capacidade_operacional: dict[str, Any]
    selection_score: float
    selection_justification: str


@dataclass
class DeliverableBReport:
    status: str  # OK | INSUFFICIENT | PARTIAL
    deliverable: str = "B"
    title: str = "Mapeamento de até 15 concorrentes observáveis"
    profile: dict[str, Any] = field(default_factory=dict)
    selection_rule: dict[str, Any] = field(default_factory=dict)
    target_n: int = DEFAULT_TARGET_N
    valid_count: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)
    insufficiency: dict[str, Any] = field(default_factory=dict)
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


def normalize_cnpj(raw: str | None) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits.zfill(14) if digits else ""


def ticket(total: float, n: int) -> tuple[float, str]:
    if n <= 0:
        return 0.0, "undefined_when_n_zero"
    return round(total / n, 2), "valor_contratado_total / n_contratos"


def desagio_from_pair(
    *,
    valor_estimado: float | None,
    valor_homologado: float | None,
    same_certame_lote_item: bool,
) -> tuple[float | None, str, str]:
    """Return (desagio_pct, status, evidence). Fail-closed without comparable pair."""
    if not same_certame_lote_item:
        return None, "INSUFFICIENT_PAIR", "estimado/homologado not linked to same certame/lote/item"
    if valor_estimado is None or valor_homologado is None:
        return None, "INSUFFICIENT_PAIR", "missing estimado or homologado"
    if valor_estimado <= 0:
        return None, "INSUFFICIENT_PAIR", "estimado must be > 0"
    pct = round((valor_estimado - valor_homologado) / valor_estimado * 100.0, 4)
    return pct, "PRESENTED", "pair on same certame/lote/item"


def active_contract_record(
    *,
    vigencia_inicio: str | None,
    vigencia_fim: str | None,
    status: str | None,
    status_as_of: str | None,
) -> dict[str, Any]:
    """Only label active when vigencia + status evidence exist."""
    ok = bool(vigencia_fim and status and status_as_of)
    return {
        "is_active_claim_allowed": ok and str(status).upper() in {"ATIVO", "VIGENTE", "ACTIVE"},
        "vigencia_inicio": vigencia_inicio,
        "vigencia_fim": vigencia_fim,
        "status": status,
        "status_as_of": status_as_of,
        "rule": "active requires vigencia_fim + status + status_as_of",
    }


def capacity_hypothesis(text: str | None = None) -> dict[str, Any]:
    return {
        "label": "HYPOTHESIS",
        "claim_as_fact_forbidden": True,
        "text": text or "Capacidade operacional não afirmada como fato sem evidência",
    }


def select_competitors(
    candidates: list[dict[str, Any]],
    rule: SelectionRule | None = None,
) -> DeliverableBReport:
    """Select up to target_n competitors without padding noise."""
    rule = rule or SelectionRule()
    stamp = profile_stamp()
    valid: list[dict[str, Any]] = []
    for c in candidates:
        cnpj = normalize_cnpj(c.get("cnpj") or c.get("ni_fornecedor"))
        n = int(c.get("n_contratos") or 0)
        if rule.require_cnpj and len(cnpj) != 14:
            continue
        if n < rule.min_contracts:
            continue
        if rule.uf_filter:
            ufs = c.get("ufs") or list((c.get("distribuicao_geografica") or {}).keys())
            if ufs and rule.uf_filter not in {str(u) for u in ufs}:
                continue
        valid.append({**c, "cnpj": cnpj, "n_contratos": n})

    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(item.get(k) or 0 for k in rule.sort_keys)

    ranked = sorted(valid, key=sort_key, reverse=True)
    selected = ranked[: rule.target_n]

    rows: list[CompetitorRow] = []
    for i, c in enumerate(selected, start=1):
        n = int(c["n_contratos"])
        total = float(c.get("valor_contratado_total") or c.get("valor_total") or 0)
        tm, formula = ticket(total, n)
        pair = c.get("desagio_pair") or {}
        desagio, dstatus, dev = desagio_from_pair(
            valor_estimado=pair.get("estimado"),
            valor_homologado=pair.get("homologado"),
            same_certame_lote_item=bool(pair.get("same_certame_lote_item")),
        )
        if rule.allow_desagio_without_pair is False and dstatus != "PRESENTED":
            desagio = None
        orgaos = list(c.get("orgaos_em_que_venceu") or c.get("orgaos") or [])
        geo = c.get("distribuicao_geografica") or {}
        if not geo and c.get("ufs"):
            geo = {str(u): 1 for u in c.get("ufs") or []}
        tipos = list(c.get("tipos_objeto") or c.get("object_types") or [])
        ativos_in = c.get("contratos_ativos") or []
        ativos = []
        for a in ativos_in:
            ativos.append(
                active_contract_record(
                    vigencia_inicio=a.get("vigencia_inicio"),
                    vigencia_fim=a.get("vigencia_fim"),
                    status=a.get("status"),
                    status_as_of=a.get("status_as_of"),
                )
            )
        score = float(n) * 1_000_000 + total
        rows.append(
            CompetitorRow(
                rank=i,
                cnpj=c["cnpj"],
                nome=str(c.get("nome") or c.get("nome_fornecedor") or ""),
                identidade_canonica=c["cnpj"],
                n_contratos=n,
                valor_contratado_total=round(total, 2),
                valor_semantica="CONTRATADO",
                ticket_contratado_medio=tm,
                ticket_formula=formula,
                orgaos_em_que_venceu=orgaos,
                distribuicao_geografica={str(k): int(v) for k, v in geo.items()},
                tipos_objeto=tipos,
                desagio=desagio,
                desagio_status=dstatus,
                desagio_evidence=dev,
                contratos_ativos=ativos,
                capacidade_operacional=capacity_hypothesis(c.get("capacidade_hipotese")),
                selection_score=score,
                selection_justification=(
                    f"rank by {rule.sort_keys}: n={n}, valor={total}; "
                    f"min_contracts>={rule.min_contracts}"
                ),
            )
        )

    valid_count = len(rows)
    if valid_count >= rule.target_n:
        status = "OK"
        insuff: dict[str, Any] = {
            "insufficient": False,
            "target_n": rule.target_n,
            "valid_count": valid_count,
            "message": f"{valid_count} defensáveis >= target {rule.target_n}",
        }
    else:
        status = "INSUFFICIENT"
        insuff = {
            "insufficient": True,
            "target_n": rule.target_n,
            "valid_count": valid_count,
            "message": (
                f"Apenas {valid_count} concorrentes defensáveis no recorte "
                f"(target {rule.target_n}); lista não completada com ruído"
            ),
            "presented_all_valid": True,
        }

    return DeliverableBReport(
        status=status,
        profile=stamp,
        selection_rule=rule.to_dict(),
        target_n=rule.target_n,
        valid_count=valid_count,
        rows=[asdict(r) for r in rows],
        insufficiency=insuff,
        claims_allowed=[
            f"Selected {valid_count} of target {rule.target_n} with rule {rule.to_dict()['description']}",
            "No padding when insufficient",
            "Deságio only with comparable pair",
            "Active claim only with vigencia+status evidence",
            "Capacity labeled HYPOTHESIS without evidence",
        ],
        claims_forbidden=[
            "Pad list to 15 with noise",
            "Deságio without same certame/lote/item pair",
            "Call contract active without vigencia+status",
            "State competitor capacity as fact without evidence",
            "ESTIMADO labeled as CONTRATADO total",
        ],
        generated_at=utc_now(),
    )


def fixture_candidates(n: int = 18) -> list[dict[str, Any]]:
    """Deterministic synthetic winners for schema proof (not live market)."""
    out: list[dict[str, Any]] = []
    for i in range(1, n + 1):
        cnpj = f"{i:08d}0001{i % 10}{ (i * 3) % 10 }"
        # pad to 14
        cnpj = (cnpj + "00")[:14]
        out.append(
            {
                "cnpj": cnpj,
                "nome": f"Fornecedor Demo {i}",
                "n_contratos": max(1, 20 - i),
                "valor_contratado_total": float(5_000_000 - i * 100_000),
                "orgaos_em_que_venceu": [f"Orgao {i}", f"Orgao {i+1}"],
                "distribuicao_geografica": {"SC": max(1, 5 - i % 4), "PR": i % 3},
                "tipos_objeto": ["reforma_predial", "manutencao_predial"][: 1 + (i % 2)],
                "desagio_pair": (
                    {
                        "estimado": 100_000.0,
                        "homologado": 90_000.0,
                        "same_certame_lote_item": True,
                    }
                    if i == 1
                    else {}
                ),
                "contratos_ativos": [
                    {
                        "vigencia_inicio": "2025-01-01",
                        "vigencia_fim": "2026-12-31",
                        "status": "ATIVO",
                        "status_as_of": "2026-07-18",
                    }
                ]
                if i <= 3
                else [{"vigencia_fim": None, "status": None, "status_as_of": None}],
            }
        )
    return out


def fixture_report(target_n: int = DEFAULT_TARGET_N) -> DeliverableBReport:
    return select_competitors(fixture_candidates(18), SelectionRule(target_n=target_n))


def audit_report(report: dict[str, Any] | DeliverableBReport) -> dict[str, Any]:
    data = asdict(report) if isinstance(report, DeliverableBReport) else report
    rows = data.get("rows") or []
    rule = data.get("selection_rule") or {}
    target = int(data.get("target_n") or rule.get("target_n") or DEFAULT_TARGET_N)
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

    insuff = data.get("insufficiency") or {}
    can_select = data.get("status") in {"OK", "INSUFFICIENT", "PARTIAL"} and "rows" in data
    add(
        "select_15_when_enough",
        "O sistema consegue selecionar e justificar pelo menos 15 fornecedores vencedores relevantes, quando existirem dados suficientes no recorte.",
        can_select
        and (
            (data.get("status") == "OK" and len(rows) >= target)
            or (data.get("status") == "INSUFFICIENT" and insuff.get("insufficient") is True)
        ),
        [f"status={data.get('status')}", f"rows={len(rows)}", f"target={target}"],
        "INSUFFICIENT allowed when valid_count < target",
    )
    add(
        "reproducible_rule",
        "A seleção dos 15 possui regra reproduzível e configurável.",
        bool(rule.get("description") and rule.get("sort_keys") is not None),
        [str(rule)],
    )
    has_cnpj = all((r.get("cnpj") or r.get("identidade_canonica")) for r in rows) if rows else True
    add(
        "cnpj_identity",
        "Cada fornecedor possui CNPJ ou identidade canônica.",
        has_cnpj,
        ["cnpj/identidade_canonica"],
    )
    has_n = all("n_contratos" in r for r in rows) if rows else True
    add("n_contratos", "Cada fornecedor possui quantidade de contratos identificados.", has_n, ["n_contratos"])
    has_valor = all(
        "valor_contratado_total" in r and r.get("valor_semantica") == "CONTRATADO" for r in rows
    ) if rows else True
    add(
        "valor_total",
        "Cada fornecedor possui valor contratado total.",
        has_valor,
        ["valor_contratado_total + valor_semantica=CONTRATADO"],
    )
    has_ticket = all(
        "ticket_contratado_medio" in r and "ticket_formula" in r for r in rows
    ) if rows else True
    add(
        "ticket_medio",
        "Cada fornecedor possui ticket contratado médio.",
        has_ticket,
        ["ticket_contratado_medio + ticket_formula"],
    )
    has_org = all("orgaos_em_que_venceu" in r for r in rows) if rows else True
    add("orgaos", "Cada fornecedor possui órgãos em que venceu.", has_org, ["orgaos_em_que_venceu"])
    has_geo = all("distribuicao_geografica" in r for r in rows) if rows else True
    add("geo", "Cada fornecedor possui distribuição geográfica.", has_geo, ["distribuicao_geografica"])
    has_tipos = all("tipos_objeto" in r for r in rows) if rows else True
    add("tipos", "Cada fornecedor possui tipos de objeto em que venceu.", has_tipos, ["tipos_objeto"])

    desagio_ok = True
    for r in rows:
        if r.get("desagio") is not None and r.get("desagio_status") != "PRESENTED":
            desagio_ok = False
        if r.get("desagio_status") == "PRESENTED" and not r.get("desagio_evidence"):
            desagio_ok = False
    add(
        "desagio_pair",
        "Deságio só é apresentado quando valor estimado e valor homologado comparáveis estiverem ligados ao mesmo certame, lote ou item.",
        desagio_ok,
        ["desagio_status PRESENTED only with evidence"],
    )

    active_ok = True
    for r in rows:
        for a in r.get("contratos_ativos") or []:
            if a.get("is_active_claim_allowed") and not (
                a.get("vigencia_fim") and a.get("status") and a.get("status_as_of")
            ):
                active_ok = False
    add(
        "active_requires_vigencia",
        "Contrato só é chamado de ativo quando houver vigência e status atual suficientes para sustentar a afirmação.",
        active_ok,
        ["is_active_claim_allowed requires vigencia_fim+status+status_as_of"],
    )

    cap_ok = all(
        (r.get("capacidade_operacional") or {}).get("label") == "HYPOTHESIS"
        and (r.get("capacidade_operacional") or {}).get("claim_as_fact_forbidden") is True
        for r in rows
    ) if rows else True
    add(
        "capacity_hypothesis",
        "Capacidade operacional disponível de concorrente nunca é afirmada como fato sem evidência; inferências são rotuladas como hipótese.",
        cap_ok,
        ["capacidade_operacional.label=HYPOTHESIS"],
    )

    no_pad_ok = (
        (data.get("status") == "OK" and len(rows) >= target)
        or (
            data.get("status") == "INSUFFICIENT"
            and insuff.get("insufficient") is True
            and len(rows) < target
            and insuff.get("presented_all_valid") is True
        )
    )
    add(
        "no_noise_padding",
        "Quando não houver 15 concorrentes defensáveis, o relatório declara a insuficiência e apresenta todos os casos válidos, sem completar a lista com ruído.",
        no_pad_ok,
        [str(insuff)],
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
        "valid_count": data.get("valid_count"),
        "target_n": target,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deliverable B competitors mapping")
    p.add_argument("command", choices=["fixture", "audit-fixture", "insufficient-demo", "audit-file"])
    p.add_argument("--target-n", type=int, default=DEFAULT_TARGET_N)
    p.add_argument("--path", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.command == "fixture":
        report = fixture_report(args.target_n)
        payload: dict[str, Any] = asdict(report)
    elif args.command == "insufficient-demo":
        # only 3 valid candidates
        report = select_competitors(fixture_candidates(3), SelectionRule(target_n=args.target_n))
        payload = asdict(report)
    elif args.command == "audit-fixture":
        report = fixture_report(args.target_n)
        payload = audit_report(report)
    else:
        path = args.path or PROJECT_ROOT / "docs/ops/session-2026-07-18-deliverable-b/fixture-b.json"
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
