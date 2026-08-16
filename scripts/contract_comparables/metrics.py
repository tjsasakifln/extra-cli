"""Robust metrics over valor integral nominal. Emitted only after gates pass."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from statistics import median

from scripts.contract_comparables.constants import IQR_OUTLIER_K, ROBUST_DISTANCE_OUTLIER
from scripts.contract_comparables.models import MetricsBundle, Recorte, SelectedPeer


def _percentile(ordered: tuple[Decimal, ...], percent: float) -> Decimal:
    if not ordered:
        raise ValueError("percentile requires a non-empty sample")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (percent / 100.0)
    lower = int(position)
    upper = lower + 1
    if upper >= len(ordered):
        return ordered[-1]
    weight = Decimal(str(position - lower))
    return ordered[lower] * (Decimal("1") - weight) + ordered[upper] * weight


def _percentile_rank(values: tuple[Decimal, ...], focal: Decimal) -> float:
    size = len(values)
    below = sum(1 for value in values if value < focal)
    equal = sum(1 for value in values if value == focal)
    return (below + (0.5 * equal)) / size * 100.0


def compute_metrics(
    *,
    focal_value: Decimal,
    peers: tuple[SelectedPeer, ...],
    eligible_n: int,
    total_n: int,
) -> MetricsBundle:
    values = tuple(sorted(peer.recorte.contract.valor for peer in peers if peer.recorte.contract.valor is not None))
    if not values:
        raise ValueError("metrics require a usable sample")
    p25 = _percentile(values, 25)
    p50 = _percentile(values, 50)
    p75 = _percentile(values, 75)
    iqr = p75 - p25
    deviations = tuple(abs(value - p50) for value in values)
    mad = median(deviations)
    if not isinstance(mad, Decimal):
        mad = Decimal(str(mad))
    robust: float | None
    if mad == 0:
        robust = 0.0 if focal_value == p50 else None
    else:
        robust = float((focal_value - p50) / mad)
    lower_fence = p25 - (Decimal(str(IQR_OUTLIER_K)) * iqr)
    upper_fence = p75 + (Decimal(str(IQR_OUTLIER_K)) * iqr)
    iqr_outlier = focal_value < lower_fence or focal_value > upper_fence
    robust_outlier = robust is not None and abs(robust) > ROBUST_DISTANCE_OUTLIER
    usable_n = len(values)
    coverage = (usable_n / total_n) if total_n else 0.0
    missingness = ((eligible_n - usable_n) / eligible_n) if eligible_n else 1.0
    stratum: dict[str, int] = {}
    for peer in peers:
        key = peer.recorte.uf or "UNKNOWN"
        stratum[key] = stratum.get(key, 0) + 1
    return MetricsBundle(
        n=usable_n,
        median=p50,
        p25=p25,
        p75=p75,
        iqr=iqr,
        mad=mad,
        focal_percentile=_percentile_rank(values, focal_value),
        robust_distance=robust,
        minimum=values[0],
        maximum=values[-1],
        min_max_caution="min_max_are_sample_extremes_not_market_bounds",
        coverage=coverage,
        missingness=missingness,
        stratum=stratum,
        outlier_flag=bool(iqr_outlier or robust_outlier),
        outlier_method="iqr_1.5_and_mad_robust_distance",
    )


def usable_values(peers: Iterable[SelectedPeer]) -> tuple[Decimal, ...]:
    return tuple(peer.recorte.contract.valor for peer in peers if peer.recorte.contract.valor is not None)


def coverage_ratio(usable_n: int, total_n: int) -> float:
    if total_n <= 0:
        return 0.0
    return usable_n / total_n


def missingness_ratio(usable_n: int, eligible_n: int) -> float:
    if eligible_n <= 0:
        return 1.0
    return (eligible_n - usable_n) / eligible_n


def unknown_is_not_zero(recorte: Recorte) -> bool:
    if recorte.contract.valor_is_unknown:
        return recorte.contract.valor is None
    return True
