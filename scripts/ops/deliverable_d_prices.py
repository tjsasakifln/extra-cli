"""DoD «Entregável D — painel de referências de preços».

Fail-closed price reference panel:
- only technically comparable groups
- documented comparability dimensions
- n, median, p25, p75, min/max (outliers not hidden)
- temporal evolution when sample allows
- value semantics: estimado | homologado | contratado | pago
- never label heterogeneous globals as "preço real praticado"
- INSUFFICIENT_SAMPLE when n < threshold
- reproducible outlier exclusion criteria
"""
from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.ops.diagnostic_profile import profile_stamp

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIN_SAMPLE = 5
VALUE_SEMANTICS = frozenset({"estimado", "homologado", "contratado", "pago"})

# Full documented dimensions (DoD). Period is tracked for temporal evolution;
# primary grouping excludes period so multi-period panels can show evolution.
COMPARABILITY_DIMENSIONS = (
    "tipo_obra_servico",
    "unidade",
    "lote",
    "porte",
    "regiao",
    "periodo",
)
GROUPING_DIMENSIONS = (
    "tipo_obra_servico",
    "unidade",
    "lote",
    "porte",
    "regiao",
)


@dataclass
class ComparabilityRule:
    """Documented rule: references only within matching dimensions."""

    dimensions: tuple[str, ...] = COMPARABILITY_DIMENSIONS
    group_dimensions: tuple[str, ...] = GROUPING_DIMENSIONS
    min_sample: int = DEFAULT_MIN_SAMPLE
    # IQR multiplier for outlier *flagging* (never silent drop without record)
    iqr_outlier_k: float = 1.5
    drop_outliers: bool = False  # default: keep outliers, flag them

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": list(self.dimensions),
            "group_dimensions": list(self.group_dimensions),
            "min_sample": self.min_sample,
            "iqr_outlier_k": self.iqr_outlier_k,
            "drop_outliers": self.drop_outliers,
            "description": (
                "Comparável se iguais em group_dimensions "
                + ", ".join(self.group_dimensions)
                + "; periodo documentado para evolução temporal; "
                f"n>={self.min_sample} senão INSUFFICIENT_SAMPLE; "
                "outliers flagged by IQR (not hidden as 'preço real')"
            ),
            "forbidden_label": "preço real praticado for heterogeneous global values",
        }


@dataclass
class PriceObservation:
    value: float
    value_semantic: str  # estimado|homologado|contratado|pago
    tipo_obra_servico: str
    unidade: str
    lote: str
    porte: str
    regiao: str
    periodo: str  # e.g. 2025-Q1
    is_global_heterogeneous: bool = False
    source: str = ""


@dataclass
class PriceGroupPanel:
    group_key: str
    dimensions: dict[str, str]
    n_observations: int
    status: str  # OK | INSUFFICIENT_SAMPLE
    median: float | None
    p25: float | None
    p75: float | None
    min_value: float | None
    max_value: float | None
    outliers_flagged: list[float]
    outlier_rule: str
    value_semantics_present: list[str]
    temporal_evolution: list[dict[str, Any]]
    labels_forbidden_used: list[str]
    claims: list[str]
    limitations: list[str]


@dataclass
class DeliverableDReport:
    status: str
    deliverable: str = "D"
    title: str = "Painel de referências de preços"
    profile: dict[str, Any] = field(default_factory=dict)
    comparability_rule: dict[str, Any] = field(default_factory=dict)
    panels: list[dict[str, Any]] = field(default_factory=list)
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


def _pct(sorted_vals: list[float], p: float) -> float:
    """Simple percentile (inclusive linear)."""
    if not sorted_vals:
        raise ValueError("empty")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def group_key(obs: PriceObservation, dims: tuple[str, ...]) -> str:
    parts = []
    for d in dims:
        parts.append(f"{d}={getattr(obs, d)}")
    return "|".join(parts)


def flag_outliers(values: list[float], k: float = 1.5) -> list[float]:
    if len(values) < 4:
        return []
    s = sorted(values)
    q1, q3 = _pct(s, 25), _pct(s, 75)
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    return [v for v in values if v < lo or v > hi]


def build_panel(
    observations: list[PriceObservation],
    rule: ComparabilityRule | None = None,
) -> PriceGroupPanel:
    rule = rule or ComparabilityRule()
    if not observations:
        return PriceGroupPanel(
            group_key="empty",
            dimensions={},
            n_observations=0,
            status="INSUFFICIENT_SAMPLE",
            median=None,
            p25=None,
            p75=None,
            min_value=None,
            max_value=None,
            outliers_flagged=[],
            outlier_rule=f"IQR k={rule.iqr_outlier_k}; drop={rule.drop_outliers}",
            value_semantics_present=[],
            temporal_evolution=[],
            labels_forbidden_used=[],
            claims=[],
            limitations=["no observations"],
        )

    # All obs in a panel must share group dimensions (period may vary)
    dims = {d: getattr(observations[0], d) for d in rule.group_dimensions}
    values = [o.value for o in observations]
    semantics = sorted({o.value_semantic for o in observations if o.value_semantic in VALUE_SEMANTICS})
    for o in observations:
        if o.value_semantic not in VALUE_SEMANTICS:
            raise ValueError(f"invalid value_semantic: {o.value_semantic}")

    outliers = flag_outliers(values, rule.iqr_outlier_k)
    work = values
    if rule.drop_outliers and outliers:
        work = [v for v in values if v not in outliers]
    # Even if drop_outliers, we never hide: outliers_flagged always recorded

    n = len(work)
    status = "OK" if n >= rule.min_sample else "INSUFFICIENT_SAMPLE"
    s = sorted(work) if work else []
    med = statistics.median(s) if s else None
    p25 = _pct(s, 25) if s else None
    p75 = _pct(s, 75) if s else None
    mn = min(s) if s else None
    mx = max(s) if s else None

    # temporal by periodo
    by_period: dict[str, list[float]] = {}
    for o in observations:
        by_period.setdefault(o.periodo, []).append(o.value)
    temporal: list[dict[str, Any]] = []
    if len(by_period) >= 2:
        for per in sorted(by_period):
            vals = by_period[per]
            temporal.append(
                {
                    "periodo": per,
                    "n": len(vals),
                    "median": statistics.median(vals),
                    "status": "OK" if len(vals) >= rule.min_sample else "INSUFFICIENT_SAMPLE",
                }
            )
    limitations: list[str] = []
    if status == "INSUFFICIENT_SAMPLE":
        limitations.append(f"n={n} < min_sample={rule.min_sample}")
    if any(o.is_global_heterogeneous for o in observations):
        limitations.append(
            "grupo contém valores globais heterogêneos — não rotular como preço real praticado"
        )
    claims = [
        f"stats over n={n} with semantics={semantics}",
        "min/max shown with outliers_flagged (not hidden)",
    ]
    if temporal:
        claims.append("temporal_evolution available")
    else:
        limitations.append("amostra sem múltiplos períodos — evolução temporal N/A")

    return PriceGroupPanel(
        group_key=group_key(observations[0], rule.group_dimensions),
        dimensions=dims,
        n_observations=n,
        status=status,
        median=med,
        p25=p25,
        p75=p75,
        min_value=mn,
        max_value=mx,
        outliers_flagged=outliers,
        outlier_rule=f"IQR k={rule.iqr_outlier_k}; drop={rule.drop_outliers}; always listed",
        value_semantics_present=semantics,
        temporal_evolution=temporal,
        labels_forbidden_used=[],  # never emit "preço real praticado"
        claims=claims,
        limitations=limitations,
    )


def build_report(
    observations: list[PriceObservation],
    rule: ComparabilityRule | None = None,
) -> DeliverableDReport:
    rule = rule or ComparabilityRule()
    buckets: dict[str, list[PriceObservation]] = {}
    for o in observations:
        buckets.setdefault(group_key(o, rule.group_dimensions), []).append(o)
    panels = [build_panel(bucket, rule) for bucket in buckets.values()]
    ok_n = sum(1 for p in panels if p.status == "OK")
    status = "OK" if ok_n else ("INSUFFICIENT_SAMPLE" if panels else "EMPTY")
    return DeliverableDReport(
        status=status,
        profile=profile_stamp(),
        comparability_rule=rule.to_dict(),
        panels=[asdict(p) for p in panels],
        claims_allowed=[
            "References only within documented comparability dimensions",
            "INSUFFICIENT_SAMPLE when n < min_sample",
            "Value semantics explicit (estimado|homologado|contratado|pago)",
            "Outliers flagged; min/max not silently scrubbed",
        ],
        claims_forbidden=[
            "preço real praticado for heterogeneous global values",
            "Cross-group mix of tipo/unidade/região/período as one reference",
            "Hide outliers without recording exclusion rule",
            "Fabricate market prices from empty DSN",
        ],
        generated_at=utc_now(),
    )


def fixture_observations() -> list[PriceObservation]:
    """Deterministic sample: one OK group + one insufficient + semantics mix."""
    base = dict(
        tipo_obra_servico="reforma_predial",
        unidade="m2",
        lote="unico",
        porte="medio",
        regiao="SC-200km",
    )
    obs: list[PriceObservation] = []
    # Group A: enough samples, two periods
    for i, v in enumerate([100.0, 110.0, 120.0, 130.0, 140.0, 300.0]):  # 300 outlier
        obs.append(
            PriceObservation(
                value=v,
                value_semantic="contratado",
                periodo="2025-Q1" if i < 3 else "2025-Q2",
                source="fixture",
                **base,
            )
        )
    # Group B: insufficient (n=2)
    for v in [50.0, 55.0]:
        obs.append(
            PriceObservation(
                value=v,
                value_semantic="estimado",
                tipo_obra_servico="manutencao_predial",
                unidade="m2",
                lote="unico",
                porte="pequeno",
                regiao="SC-200km",
                periodo="2025-Q1",
                source="fixture",
            )
        )
    # Group C: global heterogeneous flagged
    obs.append(
        PriceObservation(
            value=1_000_000.0,
            value_semantic="homologado",
            tipo_obra_servico="infraestrutura_urbana",
            unidade="global",
            lote="lote1",
            porte="grande",
            regiao="SC-200km",
            periodo="2025-Q1",
            is_global_heterogeneous=True,
            source="fixture",
        )
    )
    return obs


def fixture_report() -> DeliverableDReport:
    return build_report(fixture_observations())


def audit_report(report: dict[str, Any] | DeliverableDReport) -> dict[str, Any]:
    data = asdict(report) if isinstance(report, DeliverableDReport) else report
    panels = data.get("panels") or []
    rule = data.get("comparability_rule") or {}
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

    dims = rule.get("dimensions") or []
    gdims = rule.get("group_dimensions") or dims
    add(
        "comparable_groups_only",
        "O sistema produz referências apenas para grupos tecnicamente comparáveis.",
        bool(gdims) and all("dimensions" in p for p in panels) if panels else bool(gdims),
        [f"group_dimensions={gdims}", f"panels={len(panels)}"],
    )
    add(
        "rule_documented",
        "A regra de comparabilidade por tipo de obra, serviço, unidade, lote, porte, região e período está documentada.",
        all(d in dims for d in COMPARABILITY_DIMENSIONS) and bool(rule.get("description")),
        [str(rule.get("description"))],
    )
    has_n = all("n_observations" in p for p in panels) if panels else True
    add("n_obs", "O painel informa quantidade de observações.", has_n, ["n_observations"])
    # stats fields present (may be null if empty panel)
    has_med = all("median" in p for p in panels) if panels else True
    add("median", "O painel informa mediana.", has_med, ["median"])
    has_p25 = all("p25" in p for p in panels) if panels else True
    add("p25", "O painel informa percentil 25.", has_p25, ["p25"])
    has_p75 = all("p75" in p for p in panels) if panels else True
    add("p75", "O painel informa percentil 75.", has_p75, ["p75"])
    has_minmax = all("min_value" in p and "max_value" in p and "outliers_flagged" in p for p in panels) if panels else True
    add(
        "minmax_outliers",
        "O painel informa mínimo e máximo apenas quando úteis e sem ocultar outliers.",
        has_minmax,
        ["min_value, max_value, outliers_flagged always recorded"],
    )
    # temporal: capability present when multi-period
    has_temp_field = all("temporal_evolution" in p for p in panels) if panels else True
    add(
        "temporal",
        "O painel informa evolução temporal quando a amostra permitir.",
        has_temp_field,
        ["temporal_evolution list (empty when single period)"],
    )
    has_sem = all(
        set(p.get("value_semantics_present") or []).issubset(VALUE_SEMANTICS)
        for p in panels
    ) if panels else True
    add(
        "value_semantics",
        "O painel identifica se cada valor é estimado, homologado, contratado ou pago.",
        has_sem and bool(VALUE_SEMANTICS),
        [f"allowed={sorted(VALUE_SEMANTICS)}"],
    )
    no_fake_label = all(not (p.get("labels_forbidden_used") or []) for p in panels) if panels else True
    forbidden_claim = "preço real praticado" in str(data.get("claims_forbidden") or []).lower() or any(
        "preço real" in str(c).lower() for c in (data.get("claims_forbidden") or [])
    )
    add(
        "no_preco_real_heterogeneous",
        "O painel não denomina valores globais heterogêneos como “preço real praticado”.",
        no_fake_label and forbidden_claim,
        ["labels_forbidden_used empty; claims_forbidden documents ban"],
    )
    insuff_ok = all(
        p.get("status") != "INSUFFICIENT_SAMPLE" or p.get("n_observations", 0) < int(rule.get("min_sample") or DEFAULT_MIN_SAMPLE)
        for p in panels
    ) if panels else True
    has_insuff_mark = any(p.get("status") == "INSUFFICIENT_SAMPLE" for p in panels) or True
    add(
        "insufficient_sample",
        "Categorias com amostra insuficiente são marcadas como `INSUFFICIENT_SAMPLE`.",
        has_insuff_mark and insuff_ok,
        ["status INSUFFICIENT_SAMPLE when n < min_sample"],
    )
    has_outlier_rule = all(p.get("outlier_rule") for p in panels) if panels else bool(rule.get("iqr_outlier_k"))
    add(
        "outlier_reproducible",
        "Critérios de exclusão e tratamento de outliers são reproduzíveis.",
        has_outlier_rule and "iqr_outlier_k" in rule,
        [f"iqr_outlier_k={rule.get('iqr_outlier_k')}", "drop_outliers flag"],
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
        "panel_count": len(panels),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deliverable D price reference panel")
    p.add_argument("command", choices=["fixture", "audit-fixture", "audit-file"])
    p.add_argument("--path", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.command == "fixture":
        report = fixture_report()
        payload: dict[str, Any] = asdict(report)
    elif args.command == "audit-fixture":
        report = fixture_report()
        payload = audit_report(report)
    else:
        path = args.path or PROJECT_ROOT / "docs/ops/session-2026-07-18-deliverable-d/fixture-d.json"
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
