"""Build FUNNEL.md + JSON pack for full national commercial reservoir health.

Separates:
  PILOT_GO — high-quality small sample criteria
  NATIONAL_RESERVOIR_HEALTHY — full coverage + continuous enrichment + no artificial caps

Does not invent national counts. Callers pass live measurements.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.contact_coverage import (
    MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
)

DEFAULT_OUT = Path("artifacts/confenge/full-national-commercial-reservoir")


def _pct(part: int | float | None, whole: int | float | None) -> float | None:
    if part is None or whole is None or float(whole) == 0:
        return None
    return float(part) / float(whole) * 100.0


def _fmt_pct(p: float | None) -> str:
    if p is None:
        return "n/a"
    return f"{p:.1f}%"


def build_funnel_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Stage table with COUNT, % of previous, % of national, loss reasons."""
    national = int(metrics.get("national_universe") or 0)
    stages = [
        (
            "national supplier roots (pncp_supplier_contracts)",
            "national_universe",
            None,
        ),
        (
            "construction universe (independent sector dimension)",
            "construction_roots",
            "national_universe",
        ),
        ("target-fit eligible roots (supplier materialize set)", "target_fit_eligible", "national_universe"),
        ("target-fit dirty/enqueued", "target_fit_dirty_enqueued", "target_fit_eligible"),
        ("target-fit processed", "target_fit_processed", "target_fit_dirty_enqueued"),
        ("target-fit current materialized", "target_fit_materialized", "target_fit_eligible"),
        ("TARGET_CONFIRMED", "target_confirmed", "target_fit_materialized"),
        ("TARGET_PROBABLE_RESEARCH", "target_probable", "target_fit_materialized"),
        ("TARGET_OUT_OF_SCOPE", "target_out", "target_fit_materialized"),
        (
            "TARGET_INSUFFICIENT_EVIDENCE (retained for reconsideration)",
            "target_insufficient",
            "target_fit_materialized",
        ),
        ("activation WATCH", "activation_watch", "target_confirmed"),
        ("activation RESEARCH_REQUIRED", "activation_research", "target_confirmed"),
        ("activation ACTIONABLE_NOW", "activation_actionable", "target_confirmed"),
        ("activation SUPPRESSED", "activation_suppressed", "target_confirmed"),
        ("companies contact-discovery attempted", "contact_attempted", "target_confirmed"),
        ("companies contact-discovery never attempted", "contact_never_attempted", "target_confirmed"),
        ("companies with any email candidate", "email_candidate", "contact_attempted"),
        ("companies with real public email", "real_email", "contact_attempted"),
        ("COMPANY_OWNED", "company_owned", "real_email"),
        ("identity-safe", "identity_safe", "company_owned"),
        ("provenance-valid", "provenance_valid", "identity_safe"),
        ("service-fit valid", "service_fit", "identity_safe"),
        ("copy-context valid", "copy_context", "service_fit"),
        ("EMAIL_SEND_READY", "email_send_ready", "target_confirmed"),
        ("Warmbly imported", "warmbly_imported", "email_send_ready"),
        ("Warmbly currently eligible", "warmbly_eligible", "warmbly_imported"),
        ("Active hot-set", "active_hot_set", "email_send_ready"),
    ]
    loss = metrics.get("loss_reasons") or {}
    rows: list[dict[str, Any]] = []
    for label, key, prev_key in stages:
        count = metrics.get(key)
        count_i = int(count) if count is not None else None
        prev_c = int(metrics[prev_key]) if prev_key and metrics.get(prev_key) is not None else None
        rows.append(
            {
                "stage": label,
                "key": key,
                "count": count_i,
                "pct_of_previous": _pct(count_i, prev_c),
                "pct_of_national": _pct(count_i, national if national else None),
                "rejection_loss_reasons": loss.get(key) or loss.get(label) or {},
            }
        )
    return rows


def build_artifact_pack(metrics: dict[str, Any]) -> dict[str, Any]:
    """All campaign JSON documents + funnel markdown body."""
    rows = build_funnel_rows(metrics)
    coverage = metrics.get("target_fit_coverage") or {}
    contact = metrics.get("contact_coverage") or {}
    service = metrics.get("service_distribution") or {}
    reservoir = metrics.get("reservoir_health") or {}
    loss = metrics.get("loss_reasons") or {}

    esr = int(metrics.get("email_send_ready") or 0)
    pilot_go = bool(metrics.get("pilot_go"))
    # Pilot quality flags — caller must set after adversarial audit
    pilot = {
        "PILOT_GO": pilot_go,
        "MINIMUM_PILOT_ACCEPTANCE_SAMPLE": MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
        "email_send_ready": esr,
        "pilot_sample_met": esr >= MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
        "zero_false_target": metrics.get("zero_false_target"),
        "zero_wrong_contact": metrics.get("zero_wrong_contact"),
        "zero_tainted_provenance": metrics.get("zero_tainted_provenance"),
        "zero_unsupported_service": metrics.get("zero_unsupported_service"),
        "zero_hollow_copy": metrics.get("zero_hollow_copy"),
        "zero_unsafe_claim": metrics.get("zero_unsafe_claim"),
        "note": (
            "PILOT_GO is independent of NATIONAL_RESERVOIR_HEALTHY. "
            "Do not treat ESR≥50 as pipeline capacity or business objective."
        ),
    }
    national_healthy = {
        "NATIONAL_RESERVOIR_HEALTHY": bool(metrics.get("national_reservoir_healthy")),
        "FULL_NATIONAL_READY": bool(
            (coverage.get("FULL_NATIONAL_READY") if isinstance(coverage, dict) else False)
            or metrics.get("FULL_NATIONAL_READY")
        ),
        "coverage_mode": (coverage.get("coverage_mode") if isinstance(coverage, dict) else None)
        or reservoir.get("coverage_mode"),
        "requirements": [
            "full target-fit coverage >= 99.5% or fully explained gaps",
            "continuous enrichment over reservoir (no artificial truncation)",
            "observable backlog / dirty queue",
            "no EMAIL_SEND_READY hard cap",
            "service multi-service not monoculture without causal diagnosis",
        ],
    }

    funnel_md = render_funnel_md(
        metrics=metrics,
        rows=rows,
        pilot=pilot,
        national_healthy=national_healthy,
    )

    return {
        "FUNNEL.md": funnel_md,
        "LOSS-REASONS.json": loss,
        "SERVICE-DISTRIBUTION.json": service,
        "TARGET-FIT-COVERAGE.json": coverage,
        "UNIVERSE-MANIFEST.json": metrics.get("universe_manifest") or {},
        "CONTACT-COVERAGE.json": contact,
        "RESERVOIR-HEALTH.json": {
            **reservoir,
            "pilot": pilot,
            "national": national_healthy,
            "as_of": datetime.now(UTC).isoformat(),
            "warmbly_capacity_per_hour": metrics.get("warmbly_capacity_per_hour", 10),
            "warmbly_channel": metrics.get("warmbly_channel", "EMAIL_ONLY"),
            "whatsapp": metrics.get("whatsapp", "OFF"),
        },
        "funnel_rows": rows,
    }


def render_funnel_md(
    *,
    metrics: dict[str, Any],
    rows: list[dict[str, Any]],
    pilot: dict[str, Any],
    national_healthy: dict[str, Any],
) -> str:
    lines = [
        "# CONFENGE Full National Commercial Reservoir — FUNNEL",
        "",
        f"Generated: `{datetime.now(UTC).isoformat()}`",
        "",
        "## Principle",
        "",
        "The datalake is a national asset. The commercial pipeline treats it as a",
        "**continuously explored reservoir**, not a Top-50 spreadsheet.",
        "Send capacity controls **velocity**, not **visibility**.",
        "",
        "## Closed funnel",
        "",
        "| STAGE | COUNT | % OF PREVIOUS | % OF NATIONAL | LOSS / NOTES |",
        "|-------|------:|--------------:|--------------:|--------------|",
    ]
    for r in rows:
        loss = r.get("rejection_loss_reasons") or {}
        loss_s = ", ".join(f"{k}={v}" for k, v in sorted(loss.items())[:6]) if loss else "—"
        count = r["count"] if r["count"] is not None else "—"
        lines.append(
            f"| {r['stage']} | {count} | {_fmt_pct(r['pct_of_previous'])} | "
            f"{_fmt_pct(r['pct_of_national'])} | {loss_s} |"
        )

    lines += [
        "",
        "## Headline capacity (honest)",
        "",
        f"- National universe: **{metrics.get('national_universe', '—')}**",
        f"- TARGET_CONFIRMED: **{metrics.get('target_confirmed', '—')}**",
        f"- Contact attempted: **{metrics.get('contact_attempted', '—')}**",
        f"- Company-owned / identity-safe: **{metrics.get('identity_safe', '—')}**",
        f"- EMAIL_SEND_READY reservoir: **{metrics.get('email_send_ready', '—')}**",
        f"- Active hot-set: **{metrics.get('active_hot_set', '—')}**",
        f"- Warmbly capacity: **{metrics.get('warmbly_capacity_per_hour', 10)}/h EMAIL_ONLY** "
        f"(WhatsApp {metrics.get('whatsapp', 'OFF')})",
        "",
        "## PILOT_GO vs NATIONAL_RESERVOIR_HEALTHY",
        "",
        "```json",
        json.dumps({"pilot": pilot, "national": national_healthy}, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Root cause of historical ~1.038 materialization",
        "",
        str(
            metrics.get("truncation_root_cause")
            or (
                "Pre-#215 keyset pagination early-exit after filtered first page "
                "(~500 roots); SHADOW authority on empty current; no continuous "
                "worker drain after reconcile; mass construction requeue only "
                "expanded to ~1.038 before full national enqueue."
            )
        ),
        "",
        "## DO NOT",
        "",
        "- Optimize for ESR ≥ 50 as capacity",
        "- Stop target-fit / enrichment / materialization at Top-N",
        "- Claim FULL_NATIONAL_READY without full reconcile evidence",
        "- Treat worker HEALTHY + 2% populated as national readiness",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_artifact_pack(metrics: dict[str, Any], out_dir: Path | str = DEFAULT_OUT) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pack = build_artifact_pack(metrics)
    (out / "FUNNEL.md").write_text(pack["FUNNEL.md"], encoding="utf-8")
    for name in (
        "LOSS-REASONS.json",
        "SERVICE-DISTRIBUTION.json",
        "TARGET-FIT-COVERAGE.json",
        "UNIVERSE-MANIFEST.json",
        "CONTACT-COVERAGE.json",
        "RESERVOIR-HEALTH.json",
    ):
        (out / name).write_text(
            json.dumps(pack[name], indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    (out / "funnel-rows.json").write_text(
        json.dumps(pack["funnel_rows"], indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return out
