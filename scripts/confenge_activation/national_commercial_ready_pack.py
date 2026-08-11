"""Legacy non-terminal artifact pack.

This module remains readable for historical reproducibility but cannot emit a
GO terminal. Use ``emit_final_closure_pack`` with universe-manifest v3.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_activation.operational_metrics import (
    PILOT_ACCEPTANCE_SAMPLE,
    build_capacity_metrics,
)
from scripts.confenge_contact_resolution.discovery_state import (
    CONTACT_EXHAUSTED,
    CONTACT_EXTERNAL_BLOCKER,
    CONTACT_FOUND_NOT_SENDABLE,
    CONTACT_READY,
    CONTACT_RETRY_PENDING,
)
from scripts.confenge_contact_resolution.human_review import HUMAN_REVIEW_PENDING

DEFAULT_OUT = Path("artifacts/confenge/national-commercial-ready")


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(  # noqa: S603 — fixed argv, no shell
                ["/usr/bin/git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload if payload.endswith("\n") else payload + "\n", encoding="utf-8")
    else:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )


def build_funnel_rows(
    *,
    national_universe: int,
    target_confirmed: int,
    target_probable: int,
    target_out: int,
    target_insufficient: int,
    contact_ready: int,
    contact_found_not_sendable: int,
    contact_exhausted: int,
    contact_retry: int,
    contact_external: int,
    contact_never: int,
    email_send_ready: int,
    warmbly_reservoir: int,
    active_hot_set: int,
) -> list[dict[str, Any]]:
    """Closed funnel rows — partitions must sum without silent double-count."""
    tf_sum = target_confirmed + target_probable + target_out + target_insufficient
    contact_sum = (
        contact_ready
        + contact_found_not_sendable
        + contact_exhausted
        + contact_retry
        + contact_external
        + contact_never
    )
    rows = [
        {
            "stage": "NATIONAL_COMMERCIAL_UNIVERSE",
            "count": national_universe,
            "pct_of_previous": None,
            "notes": "supplier CNPJ roots (canonical)",
        },
        {
            "stage": "TARGET_CONFIRMED",
            "count": target_confirmed,
            "pct_of_previous": _pct(target_confirmed, national_universe),
        },
        {
            "stage": "TARGET_PROBABLE_RESEARCH",
            "count": target_probable,
            "pct_of_previous": _pct(target_probable, national_universe),
            "notes": "requires positive ICP evidence",
        },
        {
            "stage": "TARGET_OUT_OF_SCOPE",
            "count": target_out,
            "pct_of_previous": _pct(target_out, national_universe),
        },
        {
            "stage": "TARGET_INSUFFICIENT_EVIDENCE",
            "count": target_insufficient,
            "pct_of_previous": _pct(target_insufficient, national_universe),
            "notes": "not PROBABLE — no positive ICP evidence",
        },
        {
            "stage": "target_fit_class_partition_sum",
            "count": tf_sum,
            "pct_of_previous": _pct(tf_sum, national_universe),
            "notes": "CONFIRMED+PROBABLE+OUT+INSUFFICIENT (should ≈ universe when fully classified)",
        },
        {"stage": CONTACT_READY, "count": contact_ready, "pct_of_previous": _pct(contact_ready, target_confirmed)},
        {
            "stage": CONTACT_FOUND_NOT_SENDABLE,
            "count": contact_found_not_sendable,
            "pct_of_previous": _pct(contact_found_not_sendable, target_confirmed),
        },
        {
            "stage": CONTACT_EXHAUSTED,
            "count": contact_exhausted,
            "pct_of_previous": _pct(contact_exhausted, target_confirmed),
        },
        {
            "stage": CONTACT_RETRY_PENDING,
            "count": contact_retry,
            "pct_of_previous": _pct(contact_retry, target_confirmed),
        },
        {
            "stage": CONTACT_EXTERNAL_BLOCKER,
            "count": contact_external,
            "pct_of_previous": _pct(contact_external, target_confirmed),
        },
        {
            "stage": "CONTACT_NEVER_ATTEMPTED",
            "count": contact_never,
            "pct_of_previous": _pct(contact_never, target_confirmed),
        },
        {
            "stage": "contact_terminal_partition_sum",
            "count": contact_sum,
            "pct_of_previous": _pct(contact_sum, target_confirmed),
            "notes": "must equal TARGET_CONFIRMED",
        },
        {
            "stage": "EMAIL_SEND_READY",
            "count": email_send_ready,
            "pct_of_previous": _pct(email_send_ready, target_confirmed),
        },
        {
            "stage": "WARMBLY_RESERVOIR",
            "count": warmbly_reservoir,
            "pct_of_previous": _pct(warmbly_reservoir, email_send_ready),
        },
        {
            "stage": "ACTIVE_HOT_SET",
            "count": active_hot_set,
            "pct_of_previous": _pct(active_hot_set, email_send_ready),
        },
    ]
    return rows


def _pct(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(float(num) / float(den), 6)


def render_funnel_md(rows: list[dict[str, Any]], *, capacity: dict[str, Any]) -> str:
    lines = [
        "# CONFENGE National Commercial Reservoir — FUNNEL",
        "",
        f"Generated: `{_utcnow()}`",
        "",
        "## Closed funnel",
        "",
        "| STAGE | COUNT | % OF PREVIOUS | NOTES |",
        "|-------|------:|--------------:|-------|",
    ]
    for r in rows:
        pct = r.get("pct_of_previous")
        pct_s = "n/a" if pct is None else f"{pct * 100:.2f}%"
        notes = r.get("notes") or "—"
        lines.append(f"| {r['stage']} | {r['count']} | {pct_s} | {notes} |")
    lines.extend(
        [
            "",
            "## Independent capacity metrics",
            "",
            "```json",
            json.dumps(capacity, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Principle",
            "",
            f"- `PILOT_ACCEPTANCE_SAMPLE={PILOT_ACCEPTANCE_SAMPLE}` is quality-only.",
            "- `NATIONAL_EMAIL_SEND_READY_RESERVOIR` is the commercial inventory.",
            "- `ACTIVE_HOT_SET` is a rolling throughput window, not a fixed cohort.",
            "",
        ]
    )
    return "\n".join(lines)


def build_go_no_go(
    *,
    capacity: dict[str, Any],
    coverage: dict[str, Any],
    contact_terminals_complete: bool,
    provenance_contamination: int,
    copy_audit_zeros: bool,
    sha_bound: bool,
    whatsapp_off: bool,
    human_review_pending: bool,
    human_review_accepted: bool,
) -> dict[str, Any]:
    gates = {
        "canonical_universe_reconciled": bool(coverage.get("FULLY_RECONCILED")),
        "coverage_ratio_le_1": (coverage.get("coverage_ratio") or 0) <= 1.0 + 1e-12,
        "unexplained_missing_eq_0": int(coverage.get("unexplained_missing") or 0) == 0,
        "orphan_materialized_eq_0": int(coverage.get("orphan_materialized_roots") or 0) == 0,
        "duplicate_roots_eq_0": int(coverage.get("duplicate_cnpj_root") or 0) == 0,
        "target_fit_fresh": bool(coverage.get("coverage_mode") in {"FULLY_RECONCILED", "PARTIAL"}),
        "contact_terminals_complete": contact_terminals_complete,
        "provenance_contamination_eq_0": provenance_contamination == 0,
        "copy_audit_all_zero": copy_audit_zeros,
        "email_send_ready_ge_min_reserve": bool(capacity.get("reserve_gate_ok")),
        "sha_binding_exact": sha_bound,
        "whatsapp_off": whatsapp_off,
    }
    healthy = all(gates.values())
    terminal = "SUPERSEDED_NON_TERMINAL"

    return {
        "schema": "confenge.go_no_go.v1",
        "as_of": _utcnow(),
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": healthy,
        "canonical_terminal_go": False,
        "terminal_state": terminal,
        "superseded_by": "scripts.confenge_activation.emit_final_closure_pack",
        "required_schema": "confenge.universe_manifest.v3",
        "gates": gates,
        "human_review_pending": human_review_pending,
        "human_review_accepted": human_review_accepted,
        "human_review_command": (
            "python -m scripts.confenge.human_review "
            "--sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json "
            "--reviewer tiago"
        ),
    }


def emit_pack(
    *,
    out_dir: Path = DEFAULT_OUT,
    national_universe: int,
    target_classes: dict[str, int],
    contact_terminals: dict[str, int],
    email_send_ready: int,
    warmbly_reservoir: int,
    active_hot_set: int,
    coverage: dict[str, Any],
    contact_coverage: dict[str, Any],
    source_yield: dict[str, Any],
    loss_reasons: dict[str, Any],
    service_distribution: dict[str, Any],
    copy_audit: dict[str, Any],
    warmbly_e2e: dict[str, Any],
    runtime_health: dict[str, Any],
    sha_binding: dict[str, Any],
    human_review_sample: list[dict[str, Any]],
    universe_reconciliation_md: str,
    final_report_md: str,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    capacity = build_capacity_metrics(
        email_send_ready_distinct_companies=email_send_ready,
        active_hot_set_size=active_hot_set,
    )

    tc = int(target_classes.get("TARGET_CONFIRMED") or 0)
    rows = build_funnel_rows(
        national_universe=national_universe,
        target_confirmed=tc,
        target_probable=int(target_classes.get("TARGET_PROBABLE_RESEARCH") or 0),
        target_out=int(target_classes.get("TARGET_OUT_OF_SCOPE") or 0),
        target_insufficient=int(target_classes.get("TARGET_INSUFFICIENT_EVIDENCE") or 0),
        contact_ready=int(contact_terminals.get(CONTACT_READY) or 0),
        contact_found_not_sendable=int(contact_terminals.get(CONTACT_FOUND_NOT_SENDABLE) or 0),
        contact_exhausted=int(contact_terminals.get(CONTACT_EXHAUSTED) or 0),
        contact_retry=int(contact_terminals.get(CONTACT_RETRY_PENDING) or 0),
        contact_external=int(contact_terminals.get(CONTACT_EXTERNAL_BLOCKER) or 0),
        contact_never=int(contact_terminals.get("CONTACT_NEVER_ATTEMPTED") or 0),
        email_send_ready=email_send_ready,
        warmbly_reservoir=warmbly_reservoir,
        active_hot_set=active_hot_set,
    )

    contact_complete = (
        int(contact_terminals.get("CONTACT_NEVER_ATTEMPTED") or 0) == 0
        and tc > 0
        and sum(int(v) for k, v in contact_terminals.items() if k != "CONTACT_NEVER_ATTEMPTED") >= tc
    )

    audit_zeros = all(
        int(copy_audit.get(k) or 0) == 0
        for k in (
            "FALSE_TARGET",
            "WRONG_COMPANY",
            "WRONG_CONTACT",
            "TAINTED_PROVENANCE",
            "MAILBOX_INAPPROPRIATE",
            "UNSUPPORTED_SERVICE",
            "HOLLOW_COPY",
            "UNSAFE_CLAIM",
            "INVENTED_PAIN",
            "WHY_NOW_UNSUPPORTED",
            "DUPLICATE_COPY",
        )
    )

    # Ensure sample starts pending
    sample = []
    for lead in human_review_sample:
        item = dict(lead)
        item.setdefault("review_status", HUMAN_REVIEW_PENDING)
        sample.append(item)

    go = build_go_no_go(
        capacity=capacity,
        coverage=coverage,
        contact_terminals_complete=contact_complete,
        provenance_contamination=int(copy_audit.get("TAINTED_PROVENANCE") or 0),
        copy_audit_zeros=audit_zeros,
        sha_bound=bool(sha_binding.get("triple_sha_equal")),
        whatsapp_off=bool(capacity.get("warmbly", {}).get("email_only")),
        human_review_pending=any(L.get("review_status") == HUMAN_REVIEW_PENDING for L in sample) or not sample,
        human_review_accepted=bool(sample) and all(L.get("review_status") == "HUMAN_REVIEW_APPROVED" for L in sample),
    )

    _write(out_dir / "FUNNEL.json", {"rows": rows, "capacity": capacity, "as_of": _utcnow()})
    _write(out_dir / "FUNNEL.md", render_funnel_md(rows, capacity=capacity))
    _write(out_dir / "TARGET-FIT-COVERAGE.json", coverage)
    _write(
        out_dir / "TARGET-FIT-CLASS-DISTRIBUTION.json",
        {"as_of": _utcnow(), "classes": target_classes, "national_universe": national_universe},
    )
    _write(out_dir / "CONTACT-COVERAGE.json", contact_coverage)
    _write(out_dir / "CONTACT-SOURCE-YIELD.json", source_yield)
    _write(out_dir / "CONTACT-LOSS-REASONS.json", loss_reasons)
    _write(
        out_dir / "EMAIL-SEND-READY-RESERVOIR.json",
        {
            "as_of": _utcnow(),
            "EMAIL_SEND_READY_DISTINCT_COMPANIES": email_send_ready,
            "capacity": capacity,
        },
    )
    _write(out_dir / "SERVICE-DISTRIBUTION.json", service_distribution)
    _write(out_dir / "COPY-AUDIT.json", copy_audit)
    _write(out_dir / "WARMBLY-E2E.json", warmbly_e2e)
    _write(out_dir / "RUNTIME-HEALTH.json", runtime_health)
    _write(out_dir / "SHA-BINDING.json", sha_binding)
    _write(
        out_dir / "HUMAN-REVIEW-SAMPLE.json",
        {
            "schema": "confenge.human_review_sample.v1",
            "as_of": _utcnow(),
            "status_default": HUMAN_REVIEW_PENDING,
            "count": len(sample),
            "leads": sample,
            "note": "Never auto-approve. Use python -m scripts.confenge.human_review",
        },
    )
    _write(out_dir / "UNIVERSE-RECONCILIATION.md", universe_reconciliation_md)
    _write(out_dir / "GO-NO-GO.json", go)
    _write(out_dir / "FINAL-REPORT.md", final_report_md)
    _write(
        out_dir / "GO-NO-GO.md",
        "\n".join(
            [
                "# GO / NO-GO",
                "",
                f"**Terminal state:** `{go['terminal_state']}`",
                "",
                f"**NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY:** `{go['NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY']}`",
                "",
                "## Gates",
                "",
                "```json",
                json.dumps(go["gates"], indent=2),
                "```",
                "",
                "## Human review command",
                "",
                "```bash",
                go["human_review_command"],
                "```",
                "",
            ]
        ),
    )

    manifest = {
        "schema": "confenge.national_commercial_ready_pack.v1",
        "as_of": _utcnow(),
        "git_sha": _git_sha(),
        "out_dir": str(out_dir),
        "terminal_state": go["terminal_state"],
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": go["NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY"],
    }
    _write(out_dir / "MANIFEST.json", manifest)
    return manifest
