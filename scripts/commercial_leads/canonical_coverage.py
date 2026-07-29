"""Single source of truth for commercial registry coverage metrics.

All exports (result.json, queue-summary, cycle-manifest, nested metrics)
MUST derive coverage from ``build_canonical_coverage`` / the structure it
returns. Divergence is a hard gate failure.
"""

from __future__ import annotations

from typing import Any

from scripts.commercial_leads.supplier_registry import coverage_report


def build_canonical_coverage(
    registry: dict[str, Any],
    *,
    all_candidates: list[str],
    top100: list[str],
    top20: list[str],
    eligible_candidates: list[str] | None = None,
    resolution_status: dict[str, str] | None = None,
    terminal_status: str | None = None,
    declared_blockers: list[str] | None = None,
) -> dict[str, Any]:
    """Build the only coverage object allowed in commercial artifacts."""
    base = coverage_report(
        registry,  # type: ignore[arg-type]
        all_candidates=all_candidates,
        top100=top100,
        top20=top20,
        resolution_status=resolution_status,
    )
    eligible = eligible_candidates if eligible_candidates is not None else all_candidates
    eligible_cov = coverage_report(
        registry,  # type: ignore[arg-type]
        all_candidates=eligible,
        top100=top100,
        top20=top20,
        resolution_status=resolution_status,
    )
    canon = {
        "schema_version": "canonical-coverage-v1",
        "registry_coverage_all_candidates": base["registry_coverage_all_candidates"],
        "registry_coverage_eligible_candidates": eligible_cov[
            "registry_coverage_all_candidates"
        ],
        "registry_coverage_top100": base["registry_coverage_top100"],
        "registry_coverage_top20": base["registry_coverage_top20"],
        "cnae_primary_coverage": base.get("cnae_primary_coverage"),
        "cnae_secondary_coverage": base.get("cnae_secondary_coverage"),
        "registry_freshness": base.get("registry_freshness"),
        "top20_coverage_100pct": base.get("top20_coverage_100pct"),
        "registry_universe_resolved": base.get("registry_universe_resolved"),
        "registry_resolved_or_definitively_not_found": base.get(
            "registry_resolved_or_definitively_not_found"
        ),
        "registry_resolution_status_counts": base.get(
            "registry_resolution_status_counts"
        ),
        "missing_candidates_n": base.get("missing_candidates_n"),
        "missing_candidates_sample": base.get("missing_candidates_sample"),
        "block_reason": base.get("block_reason"),
        "selection_bias_risk": base.get("selection_bias_risk"),
        "rule_version": base.get("rule_version"),
        "generated_at": base.get("generated_at"),
        "terminal_status": terminal_status,
        "declared_blockers": list(declared_blockers or []),
        # Flat aliases for top-level result fields (same numbers only)
        "official_registry_coverage": (base.get("registry_coverage_all_candidates") or {}).get(
            "coverage"
        ),
        "cnae_coverage": base.get("cnae_primary_coverage"),
    }
    return canon


def _slice_cov(blob: dict[str, Any] | None, key: str) -> float | None:
    if not isinstance(blob, dict):
        return None
    node = blob.get(key)
    if isinstance(node, dict) and "coverage" in node:
        v = node.get("coverage")
        return float(v) if v is not None else None
    if key in ("cnae_coverage", "cnae_primary_coverage", "official_registry_coverage"):
        v = blob.get(key)
        if v is None and key == "cnae_coverage":
            v = blob.get("cnae_primary_coverage")
        return float(v) if v is not None else None
    return None


def extract_coverage_views(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull coverage numbers from a run/result-like payload for reconciliation."""
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    nested = metrics.get("registry_coverage") if isinstance(metrics.get("registry_coverage"), dict) else {}
    top = payload.get("registry_coverage") if isinstance(payload.get("registry_coverage"), dict) else {}
    # Prefer explicit canonical block
    canon = payload.get("canonical_coverage") or metrics.get("canonical_coverage") or nested or top
    if not isinstance(canon, dict):
        canon = {}
    return {
        "global": _slice_cov(canon, "registry_coverage_all_candidates")
        if "registry_coverage_all_candidates" in canon
        else (
            payload.get("official_registry_coverage")
            if payload.get("official_registry_coverage") is not None
            else metrics.get("cnae_coverage")
        ),
        "eligible": _slice_cov(canon, "registry_coverage_eligible_candidates"),
        "top100": _slice_cov(canon, "registry_coverage_top100"),
        "top20": _slice_cov(canon, "registry_coverage_top20"),
        "cnae": canon.get("cnae_primary_coverage")
        if canon.get("cnae_primary_coverage") is not None
        else metrics.get("cnae_coverage"),
        # Registry coverage block only — never conflate with human/terminal reason.
        "block_reason": canon.get("block_reason"),
        "terminal_status": canon.get("terminal_status") or payload.get("status"),
        "terminal_reason": payload.get("reason") or payload.get("terminal_reason"),
        "source": "canonical_coverage" if payload.get("canonical_coverage") or metrics.get("canonical_coverage") else "legacy",
    }


def reconcile_coverage_artifacts(
    artifacts: dict[str, dict[str, Any]],
    *,
    abs_tol: float = 1e-9,
) -> dict[str, Any]:
    """Fail closed if any artifact disagrees on coverage or terminal status.

    ``artifacts`` maps name → parsed JSON object (result, queue-summary, cycle-manifest, …).
    """
    views = {name: extract_coverage_views(body) for name, body in artifacts.items()}
    keys = ("global", "eligible", "top100", "top20", "cnae", "block_reason", "terminal_status")
    divergences: list[dict[str, Any]] = []

    names = list(views.keys())
    if len(names) < 2:
        return {
            "ok": True,
            "views": views,
            "divergences": [],
            "note": "fewer_than_two_artifacts",
        }

    ref_name = names[0]
    ref = views[ref_name]
    for name in names[1:]:
        other = views[name]
        for k in keys:
            a, b = ref.get(k), other.get(k)
            if a is None and b is None:
                continue
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if abs(float(a) - float(b)) > abs_tol:
                    divergences.append(
                        {
                            "field": k,
                            "left": ref_name,
                            "right": name,
                            "left_value": a,
                            "right_value": b,
                        }
                    )
            elif a != b:
                # Allow missing eligible on legacy artifacts only if both non-canonical
                if k == "eligible" and (a is None or b is None):
                    if views[ref_name].get("source") == "legacy" or views[name].get("source") == "legacy":
                        continue
                divergences.append(
                    {
                        "field": k,
                        "left": ref_name,
                        "right": name,
                        "left_value": a,
                        "right_value": b,
                    }
                )

    # Internal consistency: nested vs top-level inside each artifact
    for name, body in artifacts.items():
        metrics = body.get("metrics") if isinstance(body.get("metrics"), dict) else {}
        nested = metrics.get("registry_coverage") if isinstance(metrics.get("registry_coverage"), dict) else None
        top_cov = body.get("official_registry_coverage")
        if nested is not None and top_cov is not None:
            nested_g = _slice_cov(nested, "registry_coverage_all_candidates")
            if nested_g is not None and abs(float(nested_g) - float(top_cov)) > abs_tol:
                divergences.append(
                    {
                        "field": "official_registry_coverage_vs_nested",
                        "left": f"{name}.official_registry_coverage",
                        "right": f"{name}.metrics.registry_coverage",
                        "left_value": top_cov,
                        "right_value": nested_g,
                    }
                )
        # Stale blocker: block_reason null but terminal claims registry unavailable
        reason = str(body.get("reason") or body.get("terminal_reason") or "")
        br = None
        if nested:
            br = nested.get("block_reason")
        if (
            reason == "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
            and nested
            and nested.get("registry_universe_resolved") is True
            and (nested.get("registry_coverage_all_candidates") or {}).get("coverage") == 1.0
            and br is None
        ):
            divergences.append(
                {
                    "field": "stale_registry_blocker",
                    "left": name,
                    "right": "nested_registry",
                    "left_value": reason,
                    "right_value": "universe_resolved_coverage_1.0",
                }
            )

    return {
        "ok": len(divergences) == 0,
        "views": views,
        "divergences": divergences,
        "gate": "PASS" if not divergences else "FAIL_COVERAGE_DIVERGENCE",
    }


def assert_no_coverage_divergence(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    report = reconcile_coverage_artifacts(artifacts)
    if not report["ok"]:
        raise AssertionError(
            "coverage divergence: "
            + "; ".join(
                f"{d['field']}:{d['left_value']}!={d['right_value']}" for d in report["divergences"][:8]
            )
        )
    return report
