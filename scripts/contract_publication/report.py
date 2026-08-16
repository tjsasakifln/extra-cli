"""Observability report for a ranking run."""

from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.contract_publication.models import Candidate
from scripts.contract_publication.schema import COMPONENT_NAMES, SCORE_FORMULA_VERSION, producer_sha


def _recommendation(candidates: list[Candidate], live_unavailable: bool) -> str:
    if live_unavailable:
        return "NEEDS_DATA"
    by_state = Counter(item.candidate_state for item in candidates)
    review = by_state.get("EDITORIAL_REVIEW", 0)
    hold = by_state.get("HOLD_FOR_DATA", 0)
    reject = by_state.get("REJECT", 0)
    if not candidates:
        return "NEEDS_DATA"
    if review == 0 and hold > reject:
        return "NEEDS_DATA"
    if review == 0 and reject >= hold:
        return "STOP" if reject == len(candidates) else "ADJUST"
    if review > 0 and hold > review:
        return "ADJUST"
    return "EXPAND"


def build_status_report(
    candidates: list[Candidate],
    *,
    as_of: str,
    snapshot_id: str | None,
    input_hash: str,
    policy_hash: str,
    catalog_mode: str,
    elapsed_ms: float,
    previous: dict[str, Any] | None = None,
    live_unavailable: bool = False,
    defects: list[str] | None = None,
) -> dict[str, Any]:
    by_state = {state: 0 for state in ("REJECT", "HOLD_FOR_DATA", "EDITORIAL_REVIEW")}
    for item in candidates:
        by_state[item.candidate_state] += 1
    scores = [
        item.publication_value_score.value for item in candidates if item.publication_value_score.value is not None
    ]
    reject_reasons: Counter[str] = Counter()
    hold_reasons: Counter[str] = Counter()
    for item in candidates:
        bucket = (
            reject_reasons
            if item.candidate_state == "REJECT"
            else hold_reasons
            if item.candidate_state == "HOLD_FOR_DATA"
            else None
        )
        if bucket is None:
            continue
        for code in item.reason_codes:
            bucket[code] += 1
    decomposition: dict[str, dict[str, Any]] = {}
    for name in COMPONENT_NAMES:
        values = []
        unknown = 0
        for item in candidates:
            component = next(part for part in item.components if part.name == name)
            if component.value is None:
                unknown += 1
            else:
                values.append(component.value)
        decomposition[name] = {
            "known": len(values),
            "unknown": unknown,
            "mean": round(sum(values) / len(values), 6) if values else None,
            "weight": candidates[0].publication_value_score.weights.get(name) if candidates else None,
        }
    stale = sum(1 for item in candidates if item.freshness_status == "STALE")
    fresh = sum(1 for item in candidates if item.freshness_status == "FRESH")
    unknown_fresh = sum(1 for item in candidates if item.freshness_status == "UNKNOWN")
    known_fields = sum(len(item.evidence_refs) for item in candidates)
    recommendation = _recommendation(candidates, live_unavailable)
    report = {
        "corpus": snapshot_id or catalog_mode,
        "snapshot_id": snapshot_id,
        "snapshot_hash": input_hash,
        "policy": SCORE_FORMULA_VERSION,
        "policy_hash": policy_hash,
        "producer_sha": producer_sha(),
        "as_of": as_of,
        "catalog_mode": catalog_mode,
        "status": "OFFICIAL_DATA_UNAVAILABLE" if live_unavailable else catalog_mode,
        "by_state": by_state,
        "score_distribution": {
            "known_count": len(scores),
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "mean": round(sum(scores) / len(scores), 6) if scores else None,
        },
        "score_decomposition": decomposition,
        "rejection_reasons": sorted(reject_reasons.items(), key=lambda pair: (-pair[1], pair[0])),
        "hold_reasons": sorted(hold_reasons.items(), key=lambda pair: (-pair[1], pair[0])),
        "freshness": {"fresh": fresh, "stale": stale, "unknown": unknown_fresh},
        "coverage": {
            "candidate_count": len(candidates),
            "evidence_ref_count": known_fields,
            "shortlist_ids": [
                item.analysis_candidate_id for item in candidates if item.candidate_state == "EDITORIAL_REVIEW"
            ][:10],
        },
        "defects": defects or [],
        "corrections": [],
        "cost_latency": {"elapsed_ms": round(elapsed_ms, 3), "candidates": len(candidates)},
        "diff_vs_previous": previous or {"note": "no_previous_run"},
        "recommendation": recommendation,
    }
    return report


def render_status_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Contract publication candidate status",
        "",
        f"- corpus: `{report.get('corpus')}`",
        f"- snapshot_hash: `{report.get('snapshot_hash')}`",
        f"- policy: `{report.get('policy')}` (`{report.get('policy_hash')}`)",
        f"- producer_sha: `{report.get('producer_sha')}`",
        f"- as_of: `{report.get('as_of')}`",
        f"- catalog_mode: `{report.get('catalog_mode')}`",
        f"- status: `{report.get('status')}`",
        f"- recommendation: `{report.get('recommendation')}`",
        "",
        "## States",
        "",
    ]
    for state, count in (report.get("by_state") or {}).items():
        lines.append(f"- {state}: {count}")
    dist = report.get("score_distribution") or {}
    lines.extend(
        [
            "",
            "## Score",
            "",
            f"- known: {dist.get('known_count')} min={dist.get('min')} max={dist.get('max')} mean={dist.get('mean')}",
            "",
            "## Decomposition",
            "",
        ]
    )
    for name, row in (report.get("score_decomposition") or {}).items():
        lines.append(
            f"- {name}: weight={row.get('weight')} known={row.get('known')} unknown={row.get('unknown')} mean={row.get('mean')}"
        )
    lines.extend(["", "## Rejection reasons", ""])
    for code, count in report.get("rejection_reasons") or []:
        lines.append(f"- {code}: {count}")
    if not report.get("rejection_reasons"):
        lines.append("- (none)")
    lines.extend(["", "## Hold reasons", ""])
    for code, count in report.get("hold_reasons") or []:
        lines.append(f"- {code}: {count}")
    if not report.get("hold_reasons"):
        lines.append("- (none)")
    fresh = report.get("freshness") or {}
    lines.extend(
        [
            "",
            "## Freshness / coverage",
            "",
            f"- fresh={fresh.get('fresh')} stale={fresh.get('stale')} unknown={fresh.get('unknown')}",
            f"- candidates={((report.get('coverage') or {}).get('candidate_count'))}",
            "",
            "## Cost",
            "",
            f"- elapsed_ms: {((report.get('cost_latency') or {}).get('elapsed_ms'))}",
            "",
            "## Diff vs previous",
            "",
            f"- {report.get('diff_vs_previous')}",
            "",
        ]
    )
    return "\n".join(lines)
