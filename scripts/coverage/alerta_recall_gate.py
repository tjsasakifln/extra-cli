"""Recall gate of extra-cli against an AlertaLicitação benchmark window.

Measures Recall(extra-cli | AlertaLicitação) on equivalent windows. Extra-only
items are audited as gain beyond the aggregator and are never added to the
conditional-recall denominator. AlertaLicitação is not treated as absolute truth.

This module is the fail-closed core of issue #35. It does not remove the XLS
flow and does not use adapter counts or PNCP-only coverage as a recall proxy.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

SCHEMA_VERSION = 1
MatchBucket = Literal["both", "alerta_only", "extra_only"]
RetirementDecision = Literal["continue", "reduce", "retire"]
LAYER_BRUTO = "bruto"
LAYER_ADERENTE = "aderente"
LAYER_MATERIAL = "material"
BUCKET_BOTH: MatchBucket = "both"
BUCKET_ALERTA_ONLY: MatchBucket = "alerta_only"
BUCKET_EXTRA_ONLY: MatchBucket = "extra_only"
RETIRE_CONTINUE: RetirementDecision = "continue"
RETIRE_REDUCE: RetirementDecision = "reduce"
RETIRE_RETIRE: RetirementDecision = "retire"

REQUIRED_STRATA = (
    "ente",
    "plataforma",
    "tipo_fonte",
    "modalidade",
    "municipio",
    "esfera",
    "natureza_objeto",
    "publicacao_original",
)

DEFAULT_SLO = {
    "bruto_min": 0.80,
    "aderente_min": 0.90,
    "material_min": 0.95,
    "retire_material_min": 0.97,
    "retire_windows": 4,
    "reduce_material_min": 0.93,
}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson score interval. Returns (low, high) in [0, 1], or (None, None)."""
    if trials <= 0:
        return None, None
    if successes < 0 or successes > trials:
        raise ValueError("successes must be between 0 and trials")
    phat = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    centre = (phat + z2 / (2.0 * trials)) / denom
    margin = (z * math.sqrt((phat * (1.0 - phat) + z2 / (4.0 * trials)) / trials)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


@dataclass(frozen=True)
class OpportunityRef:
    identity: str
    source_platform: str
    ente_id: str | None = None
    modalidade: str | None = None
    municipio: str | None = None
    esfera: str | None = None
    natureza_objeto: str | None = None
    publicacao_original: str | None = None
    tipo_fonte: str | None = None
    published_at: str | None = None
    discovered_at: str | None = None
    aderente: bool = True
    material: bool = True
    strata: tuple[str, ...] = ()


@dataclass(frozen=True)
class WindowManifest:
    filters: dict[str, Any]
    cutoff: str
    universe_hash: str
    strata: tuple[str, ...]
    sample_size: int
    slo: dict[str, float]
    window_start: str
    window_end: str
    period_id: str
    hashes: dict[str, str]


@dataclass(frozen=True)
class LayerMetric:
    name: str
    numerator: int
    denominator: int
    rate: float | None
    misses: tuple[str, ...]
    ci_low: float | None
    ci_high: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissAdjudication:
    identity: str
    cause: str
    next_action: str
    reconciles_with: str = "#346"


@dataclass(frozen=True)
class RecallReport:
    manifest: WindowManifest
    buckets: dict[str, tuple[str, ...]]
    layers: dict[str, LayerMetric]
    extra_only_audit: tuple[str, ...]
    misses: tuple[MissAdjudication, ...]
    retirement: RetirementDecision
    retirement_reason: str
    generated_at: str = field(default_factory=_utc_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": self.generated_at,
            "manifest": asdict(self.manifest),
            "buckets": {k: list(v) for k, v in self.buckets.items()},
            "layers": {k: v.as_dict() for k, v in self.layers.items()},
            "extra_only_audit": list(self.extra_only_audit),
            "misses": [asdict(m) for m in self.misses],
            "retirement": self.retirement,
            "retirement_reason": self.retirement_reason,
        }


def match_key(item: OpportunityRef) -> str:
    return item.identity.strip()


def classify_match(
    alerta: OpportunityRef,
    extra: OpportunityRef | None,
) -> MatchBucket:
    if extra is None:
        return BUCKET_ALERTA_ONLY
    if match_key(alerta) != match_key(extra):
        raise ValueError("classify_match requires the same identity")
    return BUCKET_BOTH


def build_window_manifest(
    *,
    alerta_items: list[OpportunityRef],
    extra_items: list[OpportunityRef],
    window_start: str,
    window_end: str,
    cutoff: str,
    filters: dict[str, Any],
    period_id: str,
    slo: dict[str, float] | None = None,
) -> WindowManifest:
    if not window_start or not window_end:
        raise ValueError("window_start and window_end are required")
    if window_end < window_start:
        raise ValueError("window_end precedes window_start")
    resolved_slo = dict(DEFAULT_SLO)
    if slo:
        resolved_slo.update(slo)
    universe = {
        "alerta": sorted(match_key(i) for i in alerta_items),
        "extra": sorted(match_key(i) for i in extra_items),
    }
    return WindowManifest(
        filters=dict(filters),
        cutoff=cutoff,
        universe_hash=sha256_payload(universe),
        strata=REQUIRED_STRATA,
        sample_size=len(alerta_items),
        slo=resolved_slo,
        window_start=window_start,
        window_end=window_end,
        period_id=period_id,
        hashes={
            "alerta": sha256_payload([asdict(i) for i in alerta_items]),
            "extra": sha256_payload([asdict(i) for i in extra_items]),
            "filters": sha256_payload(filters),
        },
    )


def _index(items: list[OpportunityRef]) -> dict[str, OpportunityRef]:
    out: dict[str, OpportunityRef] = {}
    for item in items:
        key = match_key(item)
        if not key:
            raise ValueError("opportunity identity is required")
        if key in out:
            raise ValueError(f"duplicate identity in sample: {key}")
        out[key] = item
    return out


def _layer_metric(name: str, captured: list[str], denom_ids: list[str]) -> LayerMetric:
    denom = len(denom_ids)
    num = len(captured)
    rate = (num / denom) if denom else None
    misses = tuple(sorted(set(denom_ids) - set(captured)))
    low, high = wilson_interval(num, denom) if denom else (None, None)
    return LayerMetric(
        name=name,
        numerator=num,
        denominator=denom,
        rate=rate,
        misses=misses,
        ci_low=low,
        ci_high=high,
    )


def adjudicate_miss(item: OpportunityRef, *, latency_hours: float | None) -> MissAdjudication:
    """Assign a cause and next action. Freshness miss is not a definitive miss."""
    if latency_hours is not None and latency_hours > 24:
        return MissAdjudication(
            identity=item.identity,
            cause="freshness_lag",
            next_action="reconsultar a fonte na janela de freshness antes de contar miss definitivo",
        )
    if item.tipo_fonte in {"html", "pdf", "js"}:
        return MissAdjudication(
            identity=item.identity,
            cause="source_surface_gap",
            next_action="ativar ou corrigir o adapter da superfície que publicou o item",
        )
    return MissAdjudication(
        identity=item.identity,
        cause="match_or_coverage_gap",
        next_action="reconciliar com #346 e atribuir o gap ao ente/fonte",
    )


def evaluate_retirement(
    material: LayerMetric,
    *,
    consecutive_windows_meeting: int,
    slo: dict[str, float],
) -> tuple[RetirementDecision, str]:
    """Formalize continue / reduce / retire. Never retires on a single window."""
    rate = material.rate
    if rate is None:
        return RETIRE_CONTINUE, "denominador material vazio — sem evidência para retirar o XLS"
    retire_min = float(slo.get("retire_material_min", DEFAULT_SLO["retire_material_min"]))
    reduce_min = float(slo.get("reduce_material_min", DEFAULT_SLO["reduce_material_min"]))
    windows_needed = int(slo.get("retire_windows", DEFAULT_SLO["retire_windows"]))
    if rate >= retire_min and consecutive_windows_meeting >= windows_needed:
        return (
            RETIRE_RETIRE,
            f"material {rate:.3f} >= {retire_min} em {consecutive_windows_meeting} janelas",
        )
    if rate >= reduce_min:
        return RETIRE_REDUCE, f"material {rate:.3f} permite reduzir o XLS, não retirar"
    return RETIRE_CONTINUE, f"material {rate:.3f} abaixo do limiar de redução {reduce_min}"


def evaluate_recall(
    *,
    alerta_items: list[OpportunityRef],
    extra_items: list[OpportunityRef],
    window_start: str,
    window_end: str,
    cutoff: str,
    filters: dict[str, Any],
    period_id: str,
    slo: dict[str, float] | None = None,
    consecutive_windows_meeting: int = 0,
    latency_hours_by_id: dict[str, float] | None = None,
) -> RecallReport:
    """Compute bruto / aderente / material recall and a retirement decision."""
    if any(k in json.dumps(filters).lower() for k in ("count(*)", "db_row_count", "adapter_count")):
        raise ValueError("filters must not use operational counts as a recall proxy")

    alerta = _index(alerta_items)
    extra = _index(extra_items)
    both = sorted(set(alerta) & set(extra))
    alerta_only = sorted(set(alerta) - set(extra))
    extra_only = sorted(set(extra) - set(alerta))

    def _ids(predicate: Callable[[OpportunityRef], bool]) -> list[str]:
        return [k for k, item in alerta.items() if predicate(item)]

    bruto_denom = list(alerta)
    aderente_denom = _ids(lambda i: i.aderente)
    material_denom = _ids(lambda i: i.aderente and i.material)

    bruto_cap = [k for k in bruto_denom if k in extra]
    aderente_cap = [k for k in aderente_denom if k in extra]
    material_cap = [k for k in material_denom if k in extra]

    layers = {
        LAYER_BRUTO: _layer_metric(LAYER_BRUTO, bruto_cap, bruto_denom),
        LAYER_ADERENTE: _layer_metric(LAYER_ADERENTE, aderente_cap, aderente_denom),
        LAYER_MATERIAL: _layer_metric(LAYER_MATERIAL, material_cap, material_denom),
    }

    latency = latency_hours_by_id or {}
    misses = tuple(adjudicate_miss(alerta[mid], latency_hours=latency.get(mid)) for mid in alerta_only)

    manifest = build_window_manifest(
        alerta_items=alerta_items,
        extra_items=extra_items,
        window_start=window_start,
        window_end=window_end,
        cutoff=cutoff,
        filters=filters,
        period_id=period_id,
        slo=slo,
    )
    decision, reason = evaluate_retirement(
        layers[LAYER_MATERIAL],
        consecutive_windows_meeting=consecutive_windows_meeting,
        slo=manifest.slo,
    )
    return RecallReport(
        manifest=manifest,
        buckets={
            BUCKET_BOTH: tuple(both),
            BUCKET_ALERTA_ONLY: tuple(alerta_only),
            BUCKET_EXTRA_ONLY: tuple(extra_only),
        },
        layers=layers,
        extra_only_audit=tuple(extra_only),
        misses=misses,
        retirement=decision,
        retirement_reason=reason,
    )


def gate_exit(report: RecallReport) -> int:
    """0 = SLO met; 2 = fail-closed. Extra-only never inflates the pass condition."""
    slo = report.manifest.slo
    for name, key in (
        (LAYER_BRUTO, "bruto_min"),
        (LAYER_ADERENTE, "aderente_min"),
        (LAYER_MATERIAL, "material_min"),
    ):
        metric = report.layers[name]
        if metric.rate is None or metric.rate < float(slo[key]):
            return 2
    return 0
