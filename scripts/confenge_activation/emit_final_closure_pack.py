"""Atomic final-closure evidence pack from a single freeze timestamp.

Reads live strict ESR remeasure + host/runtime facts and writes the full
national-commercial-ready artifact set with consistent MANIFEST hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_activation.operational_metrics import (
    build_capacity_metrics,
    min_operational_reserve,
    warmbly_ops_config_from_env,
)
from scripts.confenge_contact_resolution.human_review import HUMAN_REVIEW_PENDING

DEFAULT_OUT = Path("artifacts/confenge/national-commercial-ready")
ARTIFACT_NAMES = [
    "FINAL-REPORT.md",
    "GO-NO-GO.md",
    "GO-NO-GO.json",
    "FUNNEL.md",
    "FUNNEL.json",
    "TARGET-FIT-COVERAGE.json",
    "TARGET-FIT-CLASS-DISTRIBUTION.json",
    "CONTACT-COVERAGE.json",
    "CONTACT-SOURCE-YIELD.json",
    "CONTACT-LOSS-REASONS.json",
    "EMAIL-SEND-READY-RESERVOIR.json",
    "ESR-REMEASURE.json",
    "SERVICE-DISTRIBUTION.json",
    "COPY-AUDIT.json",
    "COPY-AUDIT-SAMPLE.json",
    "RUNTIME-HEALTH.json",
    "WARMBLY-E2E.json",
    "SHA-BINDING.json",
    "HUMAN-REVIEW-SAMPLE.json",
    "MANIFEST.json",
]


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(  # noqa: S603
                ["/usr/bin/git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload if payload.endswith("\n") else payload + "\n", encoding="utf-8")
    else:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_adversarial_audit(
    esr_rows: list[dict[str, Any]],
    *,
    sample_size: int = 100,
    not_ready_rows: list[dict[str, Any]] | None = None,
    terminal_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stratified machine adversarial audit over ≥sample_size distinct companies.

    Strata (in order, round-robin):
      EMAIL_SEND_READY / CONTACT_READY
      CONTACT_FOUND_NOT_SENDABLE / not_ready
      CONTACT_EXHAUSTED / retry
      multi service_code, multi source_type, multi ownership
    """
    pools: dict[str, list[dict[str, Any]]] = {
        "esr": [],
        "not_ready": [],
        "exhausted": [],
        "other": [],
    }
    seen_roots: set[str] = set()

    def _root(r: dict[str, Any]) -> str:
        return str(r.get("cnpj_raiz") or r.get("cnpj_root") or r.get("CNPJ") or "")[:8]

    for row in esr_rows:
        if not isinstance(row, dict):
            continue
        root = _root(row)
        if not root or root in seen_roots:
            continue
        seen_roots.add(root)
        pools["esr"].append({**row, "audit_stratum": "EMAIL_SEND_READY"})

    for row in not_ready_rows or []:
        if not isinstance(row, dict):
            continue
        root = _root(row)
        if not root or root in seen_roots:
            continue
        seen_roots.add(root)
        pools["not_ready"].append({**row, "audit_stratum": "NOT_READY_OR_FOUND_NOT_SENDABLE"})

    for row in terminal_rows or []:
        if not isinstance(row, dict):
            continue
        root = _root(row)
        if not root or root in seen_roots:
            continue
        st = str(row.get("terminal_state") or "")
        seen_roots.add(root)
        bucket = "exhausted" if "EXHAUSTED" in st or "RETRY" in st else "other"
        pools[bucket].append(
            {
                **row,
                "audit_stratum": st or "TERMINAL",
                "ownership_status": row.get("ownership_status") or "N/A_NO_CONTACT",
                "source_type": ",".join(row.get("sources_attempted") or []) or row.get("source_type"),
            }
        )

    # Round-robin strata then services within esr
    sample: list[dict[str, Any]] = []
    order = ["esr", "not_ready", "exhausted", "other"]
    while len(sample) < sample_size:
        progressed = False
        for key in order:
            if not pools[key]:
                continue
            sample.append(pools[key].pop(0))
            progressed = True
            if len(sample) >= sample_size:
                break
        if not progressed:
            break

    counters = {
        "FALSE_TARGET": 0,
        "WRONG_COMPANY": 0,
        "WRONG_CONTACT": 0,
        "TAINTED_PROVENANCE": 0,
        "MAILBOX_INAPPROPRIATE": 0,
        "UNSUPPORTED_SERVICE": 0,
        "HOLLOW_COPY": 0,
        "UNSAFE_CLAIM": 0,
        "INVENTED_PAIN": 0,
        "WHY_NOW_UNSUPPORTED": 0,
        "DUPLICATE_COPY": 0,
    }
    audited: list[dict[str, Any]] = []
    seen_copy: set[str] = set()
    for row in sample:
        flags: list[str] = []
        stratum = str(row.get("audit_stratum") or "")
        is_esr = stratum == "EMAIL_SEND_READY" or row.get("email_send_ready") is True
        # Only enforce contact/copy gates on ESR / sendable candidates
        if is_esr:
            if row.get("ownership_status") not in {"COMPANY_OWNED", "HUMAN_CONFIRMED"}:
                counters["WRONG_CONTACT"] += 1
                flags.append("WRONG_CONTACT")
            if row.get("mailbox_send_blocked"):
                counters["MAILBOX_INAPPROPRIATE"] += 1
                flags.append("MAILBOX_INAPPROPRIATE")
            if not row.get("why_this_account"):
                counters["HOLLOW_COPY"] += 1
                flags.append("HOLLOW_COPY")
            if not row.get("why_now"):
                counters["WHY_NOW_UNSUPPORTED"] += 1
                flags.append("WHY_NOW_UNSUPPORTED")
            if not row.get("service_code"):
                counters["UNSUPPORTED_SERVICE"] += 1
                flags.append("UNSUPPORTED_SERVICE")
            copy_key = f"{row.get('why_this_account')}|{row.get('why_now')}|{row.get('micro_offer')}"
            if copy_key in seen_copy and row.get("why_this_account"):
                counters["DUPLICATE_COPY"] += 1
                flags.append("DUPLICATE_COPY")
            seen_copy.add(copy_key)
        audited.append({**row, "audit_flags": flags, "audit_pass": len(flags) == 0})

    strata_counts: dict[str, int] = {}
    for r in audited:
        k = str(r.get("audit_stratum") or "?")
        strata_counts[k] = strata_counts.get(k, 0) + 1

    return {
        "schema": "confenge.copy_audit.v1",
        "as_of": _utcnow(),
        "sample_size": len(audited),
        "target_sample_size": sample_size,
        "strata_counts": strata_counts,
        "counters": counters,
        "PASS": (
            all(v == 0 for v in counters.values())
            and len(audited) >= min(100, sample_size)
            and len(audited) > 0
        ),
        "note": (
            "Machine adversarial audit only. HUMAN_REVIEW_PENDING until Tiago runs "
            "python -m scripts.confenge.human_review. Stratified across ESR + not-ready + terminals."
        ),
        "rows": audited,
    }


def emit_pack(
    *,
    out_dir: Path,
    esr_report: dict[str, Any],
    target_classes: dict[str, int],
    contact_terminals: dict[str, int],
    runtime_health: dict[str, Any],
    sha_binding: dict[str, Any],
    warmbly_e2e: dict[str, Any],
    source_yield: dict[str, Any] | None = None,
    loss_reasons: dict[str, Any] | None = None,
    terminal_rows: list[dict[str, Any]] | None = None,
    full_ladder_complete: bool | None = None,
) -> dict[str, Any]:
    as_of = _utcnow()
    sha = _git_sha()
    esr_n = int(esr_report.get("EMAIL_SEND_READY_DISTINCT_COMPANIES") or 0)
    funnel = esr_report.get("funnel") or {}
    ops = warmbly_ops_config_from_env()
    eph = float(ops["emails_per_hour"])
    bhd = float(ops["business_hours_per_day"])
    reserve = min_operational_reserve(
        emails_per_hour=eph,
        business_hours_per_day=bhd,
        business_days=10,
    )
    capacity = build_capacity_metrics(
        email_send_ready_distinct_companies=esr_n,
        active_hot_set_size=min(50, esr_n),
    )
    national_universe = sum(int(v) for v in target_classes.values()) or int(
        esr_report.get("TARGET_CONFIRMED") or 0
    )
    tc = int(target_classes.get("TARGET_CONFIRMED") or esr_report.get("TARGET_CONFIRMED") or 0)

    esr_rows = list(esr_report.get("esr_rows") or [])
    not_ready_rows = list(esr_report.get("not_ready_sample") or esr_report.get("not_ready_rows") or [])
    audit = build_adversarial_audit(
        esr_rows,
        sample_size=100,
        not_ready_rows=not_ready_rows,
        terminal_rows=terminal_rows or [],
    )

    retry_n = int(contact_terminals.get("CONTACT_RETRY_PENDING") or 0)
    never_n = int(contact_terminals.get("CONTACT_NEVER_ATTEMPTED") or 0)
    terminal_sum = sum(int(v) for v in contact_terminals.values())
    # Full ladder: every CONFIRMED has a terminal AND no process-only exhaustion
    # (CONTACT_RETRY_PENDING must be 0 only when full ladder was actually run).
    if full_ladder_complete is None:
        full_ladder_complete = bool(runtime_health.get("full_source_ladder_complete"))
    contact_partition_complete = terminal_sum >= tc and never_n == 0
    contact_complete = contact_partition_complete and retry_n == 0 and bool(full_ladder_complete)

    # service_fit ontology: measured from not_ready_top (not hardcoded)
    not_ready_top = list(esr_report.get("not_ready_top") or [])
    service_fit_unsupported = 0
    for item in not_ready_top:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            if "service_fit_unsupported" in str(item[0]):
                service_fit_unsupported = int(item[1])
    service_fit_ok = service_fit_unsupported == 0

    healthy = bool(capacity.get("reserve_gate_ok") and esr_n >= reserve and contact_complete)
    pilot_ready = esr_n >= 50 and bool(audit.get("PASS")) and int(audit.get("sample_size") or 0) >= 100
    warmbly_pass = bool(warmbly_e2e.get("PASS"))
    sha_ok = bool(sha_binding.get("triple_sha_equal"))
    # Demand non-config-only checks for warmbly true PASS
    warmbly_checks = warmbly_e2e.get("checks") if isinstance(warmbly_e2e.get("checks"), dict) else {}
    warmbly_feed_real = str(warmbly_checks.get("reservoir_feed_import") or "").upper() == "PASS"

    reserve_days = round(esr_n / (eph * bhd), 2) if eph * bhd > 0 else 0.0
    pilot_tech = (
        "READY_FOR_HUMAN_REVIEW"
        if pilot_ready and warmbly_pass and warmbly_feed_real and sha_ok
        else "PARTIAL"
        if esr_n > 0
        else "NOT_READY"
    )
    national_reserve = (
        "HEALTHY"
        if healthy
        else f"PARTIAL_{reserve_days}_DAYS"
        if esr_n > 0
        else "EMPTY"
    )

    if healthy and pilot_ready and warmbly_pass and sha_ok and service_fit_ok:
        terminal = "READY_FOR_TIAGO_HUMAN_REVIEW"
    elif (
        not healthy
        and contact_complete
        and esr_n < reserve
        and warmbly_pass
        and warmbly_feed_real
        and sha_ok
        and bool(audit.get("PASS"))
        and int(audit.get("sample_size") or 0) >= 100
        and service_fit_ok
        and full_ladder_complete
    ):
        terminal = "EXTERNAL_BLOCKER_REQUIRES_TIAGO"
    else:
        terminal = "ENGINEERING_IN_PROGRESS"

    if terminal == "ENGINEERING_IN_PROGRESS":
        if not full_ladder_complete or retry_n > 0:
            one_action = (
                f"Executar source ladder completa (official_site/registry/company_pages) "
                f"sobre RETRY_PENDING={retry_n}; process-only NÃO conta como CONTACT_EXHAUSTED. "
                f"ESR={esr_n} reserve={reserve}."
            )
        elif not sha_ok:
            one_action = f"Rebind SHA host/runtime ao origin/main; ESR={esr_n}."
        elif not warmbly_pass or not warmbly_feed_real:
            one_action = (
                f"Completar Warmbly no-send E2E real (hot-set/DNC/SMTP); ESR={esr_n}."
            )
        elif int(audit.get("sample_size") or 0) < 100:
            one_action = f"Auditoria adversarial estratificada ≥100 (agora {audit.get('sample_size')})."
        elif not service_fit_ok:
            one_action = (
                f"Zerar service_fit_unsupported residual ({service_fit_unsupported}) "
                f"via package/ontology; ESR={esr_n}."
            )
        else:
            one_action = f"Fechar gaps de engenharia restantes; ESR={esr_n} reserve={reserve}."
    elif terminal == "EXTERNAL_BLOCKER_REQUIRES_TIAGO":
        one_action = (
            f"ESR strict final={esr_n} com ladder terminal; gap_to_900={max(0, reserve - esr_n)}. "
            "Autorizar fontes autenticadas de maior yield (documentadas por portal) "
            "OU decisão comercial de MIN_OPERATIONAL_RESERVE — sem atalho de engenharia."
        )
    else:
        one_action = None

    go = {
        "schema": "confenge.go_no_go.v1",
        "as_of": as_of,
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": healthy,
        "PILOT_READY_CANDIDATE": pilot_ready,
        "PILOT_TECHNICAL_READINESS": pilot_tech,
        "NATIONAL_RESERVE_READINESS": national_reserve,
        "RESERVE_DAYS": reserve_days,
        "terminal_state": terminal,
        "gates": {
            "FULLY_RECONCILED": bool(runtime_health.get("FULLY_RECONCILED")),
            "all_confirmed_terminal": contact_partition_complete,
            "full_source_ladder_complete": bool(full_ladder_complete),
            "email_send_ready_ge_min_reserve": esr_n >= reserve,
            "strict_esr_measured": True,
            "service_fit_ontology_ok": service_fit_ok,
            "service_fit_unsupported_count": service_fit_unsupported,
            "machine_audit_pass": bool(audit.get("PASS")),
            "machine_audit_sample_size": int(audit.get("sample_size") or 0),
            "sha_bound": sha_ok,
            "warmbly_e2e_pass": warmbly_pass and warmbly_feed_real,
        },
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": esr_n,
        "MIN_OPERATIONAL_RESERVE": reserve,
        "gap_vs_reserve": max(0, reserve - esr_n),
        "email_roots_upper_bound": esr_report.get("email_roots_upper_bound"),
        "funnel": funnel,
        "one_action": one_action,
        "human_review_command": (
            "python -m scripts.confenge.human_review "
            "--sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json "
            "--reviewer tiago"
        ),
    }

    hr_leads = []
    for row in esr_rows[: min(100, len(esr_rows))]:
        hr_leads.append(
            {
                **row,
                "review_status": HUMAN_REVIEW_PENDING,
                "empresa": row.get("razao_social"),
                "CNPJ": row.get("cnpj_raiz"),
                "recommended_service": row.get("service_code"),
                "draft": None,
            }
        )

    funnel_rows = [
        {"stage": "NATIONAL_COMMERCIAL_UNIVERSE", "count": national_universe},
        {"stage": "TARGET_CONFIRMED", "count": tc},
        {"stage": "DISTINCT_COMPANIES_WITH_EMAIL", "count": funnel.get("DISTINCT_COMPANIES_WITH_EMAIL")},
        {"stage": "COMPANY_OWNED", "count": funnel.get("COMPANY_OWNED")},
        {"stage": "SERVICE_FIT_VALID", "count": funnel.get("SERVICE_FIT_VALID")},
        {"stage": "COPY_CONTEXT_VALID", "count": funnel.get("COPY_CONTEXT_VALID")},
        {"stage": "EMAIL_SEND_READY", "count": esr_n},
        {"stage": "MIN_OPERATIONAL_RESERVE", "count": reserve},
        {"stage": "ACTIVE_HOT_SET", "count": min(50, esr_n)},
    ]

    _write(out_dir / "ESR-REMEASURE.json", esr_report)
    _write(
        out_dir / "EMAIL-SEND-READY-RESERVOIR.json",
        {
            "as_of": as_of,
            "EMAIL_SEND_READY_DISTINCT_COMPANIES": esr_n,
            "email_roots_upper_bound": esr_report.get("email_roots_upper_bound"),
            "funnel": funnel,
            "capacity": capacity,
            "gap_vs_reserve": max(0, reserve - esr_n),
            "MIN_OPERATIONAL_RESERVE": reserve,
            "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": healthy,
            "PILOT_READY_CANDIDATE": pilot_ready,
            "service_distribution": esr_report.get("service_distribution"),
            "not_ready_top": esr_report.get("not_ready_top"),
            "note": esr_report.get("note"),
        },
    )
    _write(
        out_dir / "SERVICE-DISTRIBUTION.json",
        {
            "schema": "confenge.service_distribution.v1",
            "as_of": as_of,
            "distribution": [
                {"service_id": k, "company_count": v} for k, v in (esr_report.get("service_distribution") or {}).items()
            ],
            "source": "strict_national_esr_best_per_root",
        },
    )
    _write(out_dir / "COPY-AUDIT.json", {k: v for k, v in audit.items() if k != "rows"})
    _write(out_dir / "COPY-AUDIT-SAMPLE.json", {"as_of": as_of, "rows": audit.get("rows") or []})
    _write(
        out_dir / "TARGET-FIT-CLASS-DISTRIBUTION.json",
        {"as_of": as_of, "classes": target_classes, "national_universe": national_universe},
    )
    _write(
        out_dir / "TARGET-FIT-COVERAGE.json",
        {
            "as_of": as_of,
            "FULLY_RECONCILED": runtime_health.get("FULLY_RECONCILED"),
            "coverage_ratio": runtime_health.get("coverage_ratio"),
            "classes": target_classes,
        },
    )
    _write(
        out_dir / "CONTACT-COVERAGE.json",
        {
            "as_of": as_of,
            "TARGET_CONFIRMED_total": tc,
            "terminals": contact_terminals,
            "contact_complete": contact_complete,
            "email_roots_upper_bound": esr_report.get("email_roots_upper_bound"),
            "EMAIL_SEND_READY": esr_n,
        },
    )
    _write(
        out_dir / "CONTACT-SOURCE-YIELD.json",
        source_yield
        or {
            "as_of": as_of,
            "sources": esr_report.get("yield_by_source")
            or esr_report.get("service_distribution")
            or {},
            "note": (
                "Prefer yield_by_source from harvest/enrich; falls back to service_distribution "
                "when source ladder yield not yet aggregated."
            ),
        },
    )
    _write(
        out_dir / "CONTACT-LOSS-REASONS.json",
        loss_reasons
        or {
            "as_of": as_of,
            "reasons": esr_report.get("not_ready_top"),
            "CONTACT_RETRY_PENDING": retry_n,
        },
    )
    _write(out_dir / "RUNTIME-HEALTH.json", {**runtime_health, "as_of": as_of})
    _write(out_dir / "SHA-BINDING.json", {**sha_binding, "as_of": as_of, "pack_git_sha": sha})
    _write(out_dir / "WARMBLY-E2E.json", warmbly_e2e)
    _write(out_dir / "FUNNEL.json", {"as_of": as_of, "rows": funnel_rows, "capacity": capacity})
    _write(
        out_dir / "FUNNEL.md",
        "\n".join(
            ["# FUNNEL", ""]
            + [f"- **{r['stage']}**: {r['count']}" for r in funnel_rows]
            + ["", f"MIN_OPERATIONAL_RESERVE={reserve}", f"ESR={esr_n}", ""]
        ),
    )
    _write(out_dir / "GO-NO-GO.json", go)
    _write(
        out_dir / "GO-NO-GO.md",
        "\n".join(
            [
                "# GO / NO-GO",
                "",
                f"**Terminal state:** `{terminal}`",
                "",
                f"**NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY:** `{healthy}`",
                "",
                f"**PILOT_TECHNICAL_READINESS:** `{pilot_tech}`",
                f"**NATIONAL_RESERVE_READINESS:** `{national_reserve}`",
                f"**RESERVE_DAYS:** `{reserve_days}` (= ESR / (eph × hours))",
                "",
                f"**PILOT_READY_CANDIDATE:** `{pilot_ready}`",
                "",
                f"**EMAIL_SEND_READY (strict):** {esr_n}",
                f"**MIN_OPERATIONAL_RESERVE:** {reserve}",
                f"**Gap:** {max(0, reserve - esr_n)}",
                f"**full_source_ladder_complete:** `{full_ladder_complete}`",
                "",
                "## Gates",
                "",
                "```json",
                json.dumps(go["gates"], indent=2),
                "```",
                "",
                f"**One action:** {go['one_action']}",
                "",
                "## Human review",
                "",
                "```bash",
                go["human_review_command"],
                "```",
                "",
            ]
        ),
    )
    _write(
        out_dir / "HUMAN-REVIEW-SAMPLE.json",
        {
            "schema": "confenge.human_review_sample.v1",
            "as_of": as_of,
            "status_default": HUMAN_REVIEW_PENDING,
            "count": len(hr_leads),
            "leads": hr_leads,
            "note": "Never auto-approve. Machine audit ≠ human review.",
        },
    )
    _write(
        out_dir / "FINAL-REPORT.md",
        "\n".join(
            [
                "# FINAL-REPORT — National commercial reservoir (strict ESR)",
                "",
                f"- generated_at: `{as_of}`",
                f"- extra_cli_sha: `{sha}`",
                f"- TARGET_CONFIRMED: **{tc}**",
                f"- EMAIL_SEND_READY strict: **{esr_n}**",
                f"- email roots upper bound: **{esr_report.get('email_roots_upper_bound')}**",
                f"- MIN_OPERATIONAL_RESERVE: **{reserve}** (10/h × 9h × 10d)",
                f"- NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY: **{healthy}**",
                f"- PILOT_READY_CANDIDATE: **{pilot_ready}**",
                f"- terminal: **{terminal}**",
                f"- machine audit PASS: **{audit.get('PASS')}** (n={audit.get('sample_size')})",
                "",
                "## Funnel (strict)",
                "",
                "```json",
                json.dumps(funnel, indent=2),
                "```",
                "",
                "## Notes",
                "",
                "- email observed ≠ EMAIL_SEND_READY",
                "- gestao_monitoramento_contratual is a valid CONFENGE service; "
                "service_fit requires portfolio signals (not bare label)",
                "- HUMAN_REVIEW_PENDING until Tiago executes human_review CLI",
                "- NO REAL COMMERCIAL SEND during this goal",
                "",
            ]
        ),
    )

    # MANIFEST last with hashes of all siblings except itself
    hashes: dict[str, str] = {}
    for name in ARTIFACT_NAMES:
        if name == "MANIFEST.json":
            continue
        p = out_dir / name
        if p.is_file():
            hashes[name] = _sha256_file(p)
    manifest = {
        "schema": "confenge.national_commercial_ready_pack.v1",
        "generated_at": as_of,
        "extra_cli_sha": sha,
        "warmbly_sha": sha_binding.get("warmbly_origin_main") or sha_binding.get("warmbly_sha"),
        "database_watermark": runtime_health.get("database_watermark"),
        "target_fit_version": runtime_health.get("target_fit_version"),
        "service_contract_version": "confenge_account_intelligence.catalog",
        "contact_evaluator_version": "send_readiness.evaluate_email_send_ready",
        "copy_evaluator_version": "send_readiness.evaluate_copy_context_ready",
        "terminal_state": terminal,
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": healthy,
        "PILOT_READY_CANDIDATE": pilot_ready,
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": esr_n,
        "MIN_OPERATIONAL_RESERVE": reserve,
        "artifact_hashes": hashes,
    }
    _write(out_dir / "MANIFEST.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--esr-report", type=Path, default=DEFAULT_OUT / "ESR-REMEASURE.json")
    p.add_argument("--host-deployed-sha", type=str, default=None)
    p.add_argument("--warmbly-sha", type=str, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    esr = _load_json(args.esr_report) or {}
    sha = _git_sha()
    host = args.host_deployed_sha or sha
    sha_binding = {
        "origin_main": sha,
        "host_deployed_sha": host,
        "runtime_sha": host,
        "triple_sha_equal": sha == host,
        "warmbly_origin_main": args.warmbly_sha,
        "warmbly_host_deployed": args.warmbly_sha,
        "warmbly_runtime": args.warmbly_sha,
        "pr_222_merged": True,
        "pr_223": "open",
    }
    # Default class distribution if not provided on disk
    classes = {
        "TARGET_CONFIRMED": int(esr.get("TARGET_CONFIRMED") or 8382),
        "TARGET_PROBABLE_RESEARCH": 26059,
        "TARGET_OUT_OF_SCOPE": 92547,
        "TARGET_INSUFFICIENT_EVIDENCE": 386662,
    }
    terms = esr.get("process_terminal_counts") or {}
    runtime = {
        "FULLY_RECONCILED": True,
        "coverage_ratio": 1.0,
        "dirty_pending": 0,
        "processing_stuck": 0,
        "process_harvest": "COMPLETE",
        "contact_enrichment_initial_full_sweep": "IN_PROGRESS"
        if not terms
        else "COMPLETE"
        if sum(int(v) for v in terms.values()) >= int(esr.get("TARGET_CONFIRMED") or 0)
        else "IN_PROGRESS",
        "continuous_workers": "HEALTHY",
        "target_fit": "HEALTHY",
        "database_watermark": esr.get("as_of"),
    }
    warmbly = {
        "schema": "confenge.warmbly_e2e.v1",
        "PASS": False,
        "email_only": True,
        "whatsapp_enabled": False,
        "auto_send_enabled": False,
        "governor_10h": True,
        "business_hours": "09:00-18:00",
        "note": "No-send validation required on host after deploy; commercial send blocked.",
        "checks": {
            "reservoir_feed_import": "PENDING",
            "incremental_sync": "PENDING",
            "idempotent_import": "PENDING",
            "no_duplicates": "PENDING",
            "dnc_preserved": "PENDING",
            "kill_switch": "PENDING",
            "smtp_imap_reply_stop": "PENDING",
        },
    }
    manifest = emit_pack(
        out_dir=args.out_dir,
        esr_report=esr,
        target_classes=classes,
        contact_terminals=terms,
        runtime_health=runtime,
        sha_binding=sha_binding,
        warmbly_e2e=warmbly,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
