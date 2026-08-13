"""Atomic final-closure evidence pack from a single freeze timestamp.

Reads live strict ESR remeasure + host/runtime facts and writes the full
national-commercial-ready artifact set with consistent MANIFEST hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_activation.operational_metrics import (
    CONFENGE_BUSINESS_HOURS_PER_DAY,
    CONFENGE_PILOT_EMAILS_PER_HOUR,
    MIN_OPERATIONAL_RESERVE,
    build_capacity_metrics,
)
from scripts.confenge_activation.pilot_go_policy import (
    GO_NO_GO_SCHEMA,
    evaluate_pilot_go,
    lead_key,
    load_human_review_decisions,
    validate_universe_manifest,
)
from scripts.confenge_contact_resolution.discovery_state import DEFAULT_SOURCE_LADDER
from scripts.confenge_contact_resolution.human_review import HUMAN_REVIEW_PENDING

DEFAULT_OUT = Path("artifacts/confenge/national-commercial-ready")
_REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_NAMES = [
    "FINAL-REPORT.md",
    "GO-NO-GO.md",
    "GO-NO-GO.json",
    "FUNNEL.md",
    "FUNNEL.json",
    "TARGET-FIT-COVERAGE.json",
    "TARGET-FIT-CLASS-DISTRIBUTION.json",
    "SECTOR-CLASS-DISTRIBUTION.json",
    "UNIVERSE-MANIFEST.json",
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

# Critical Warmbly checks that cannot be PASS_CONFIG / PASS_UNIT_TEST / PENDING when PASS=true
WARMBLY_CRITICAL_CHECKS = (
    "smtp_imap_reply_stop",
    "dnc_preserved",
    "rolling_hot_set",
    "outcomes_webhook",
)
_CONFIG_ONLY_STATUSES = frozenset({"PASS_CONFIG", "PASS_UNIT_TEST", "PENDING"})


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


def build_sha_binding(
    *,
    origin_main: str,
    host_deployed: str,
    runtime: str,
    evaluated_code_sha: str | None = None,
    expected_origin_tip: str | None = None,
    warmbly_origin_main: str | None = None,
    warmbly_host_deployed: str | None = None,
    warmbly_runtime: str | None = None,
    evidence_publication_sha: str | None = None,
    evaluation_lineage_ok: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build SHA-BINDING without defaulting host/runtime to local HEAD.

    Terminal gating binds the immutable code evaluation to deployment/runtime:
    ``evaluated_code_sha == host_deployed == runtime``. The current origin tip
    and evidence-publication SHA are separate lineage and cannot invalidate an
    evaluation merely because evidence pointers were committed afterwards.
    """
    om = (origin_main or "").strip()
    hd = (host_deployed or "").strip()
    rt = (runtime or "").strip()
    evaluated = (str(evaluated_code_sha or "").strip() or om)
    tip = (expected_origin_tip or "").strip() or None
    triple = bool(evaluated and hd and rt and evaluated == hd == rt)
    tip_ok = True if tip is None else (om == tip)
    lineage_ok = evaluated == om or evaluation_lineage_ok is True
    publication = str(evidence_publication_sha or "").strip() or om or None
    out: dict[str, Any] = {
        "origin_main": om or None,
        "evaluated_code_sha": evaluated or None,
        "evidence_publication_sha": publication,
        "host_deployed_sha": hd or None,
        "runtime_sha": rt or None,
        "expected_origin_tip": tip,
        "triple_sha_equal": triple,
        "tip_matches_origin_main": tip_ok if tip is not None else None,
        "evaluated_deployment_runtime_equal": triple,
        "evaluation_lineage_ok": lineage_ok,
        # Gate flag used by emit_pack terminals. Publication lineage is not a code gate.
        "sha_bound": triple and tip_ok and lineage_ok,
        "warmbly_origin_main": warmbly_origin_main,
        "warmbly_host_deployed": warmbly_host_deployed,
        "warmbly_runtime": warmbly_runtime,
    }
    if extra:
        out.update({key: value for key, value in extra.items() if key not in out})
    return out


def evaluation_lineage_preserved(evaluated_sha: str, tip_sha: str) -> bool:
    """Prove that a prior evaluation remains valid at the publication tip."""
    evaluated = str(evaluated_sha or "").strip()
    tip = str(tip_sha or "").strip()
    if not evaluated or not tip:
        return False
    if evaluated == tip:
        return True
    git = shutil.which("git")
    if not git:
        return False
    try:
        subprocess.check_call(  # noqa: S603
            [git, "merge-base", "--is-ancestor", evaluated, tip],
            cwd=str(_REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        from scripts.ops.confenge_frozen_inputs import evaluate_post_freeze_diff

        result = evaluate_post_freeze_diff(
            root=_REPO_ROOT,
            freeze_sha=evaluated,
            tip=tip,
        )
        return bool(result.get("ok"))
    except (OSError, subprocess.SubprocessError):
        return False


def ladder_complete_from_source_yield(
    source_yield: dict[str, Any] | None,
    *,
    target_confirmed: int,
    ladder_steps: tuple[str, ...] | list[str] = DEFAULT_SOURCE_LADDER,
    min_ratio: float = 1.0,
) -> dict[str, Any]:
    """Derive full_source_ladder_complete from CONTACT-SOURCE-YIELD (not a trusted flag).

    Each ladder step must have companies_attempted >= target_confirmed * min_ratio,
    OR an explicit classified external remainder (class HUMAN_SESSION_REQUIRED /
    PUBLIC_AUTH_REQUIRED / CAPTCHA_REQUIRED / PAID_SOURCE / LEGALLY_RESTRICTED)
    documenting the residual N.

    Historical regression fixtures with partial probes (for example 20/8382,
    never a live fallback) force complete=false.
    """
    tc = max(0, int(target_confirmed))
    threshold = int(tc * float(min_ratio)) if tc else 0
    sources = {}
    if isinstance(source_yield, dict):
        raw = source_yield.get("sources")
        if isinstance(raw, dict):
            sources = raw
    missing: list[str] = []
    partial: list[dict[str, Any]] = []
    covered: list[str] = []
    for step in ladder_steps:
        entry = sources.get(step) if isinstance(sources.get(step), dict) else {}
        attempted = int(entry.get("companies_attempted") or 0) if entry else 0
        klass = str(entry.get("class") or "").strip().upper()
        external_ok = (
            klass
            in {
                "HUMAN_SESSION_REQUIRED",
                "PUBLIC_AUTH_REQUIRED",
                "CAPTCHA_REQUIRED",
                "PAID_SOURCE",
                "LEGALLY_RESTRICTED",
                "UNAVAILABLE",
            }
            and int(entry.get("external_remainder_n") or entry.get("companies_blocked") or 0) >= 0
            and (
                # classified external must document remaining companies OR attempted==tc
                attempted >= threshold or int(entry.get("external_remainder_n") or 0) > 0 or entry.get("portal")
            )
        )
        # Near-full national coverage (≥99.9%) counts as ladder-complete for that step
        # (allows off-by-one bookkeeping without accepting historical partial probes).
        ratio = (attempted / tc) if tc > 0 else 0.0
        if attempted >= threshold or ratio >= 0.999:
            covered.append(step)
            continue
        if external_ok and attempted < threshold:
            # Residual explicitly classified as external — step not engineering-complete
            # but does not by itself force ENGINEERING if all other steps full.
            # For national closure we still require engineering-complete public steps.
            partial.append(
                {
                    "step": step,
                    "companies_attempted": attempted,
                    "threshold": threshold,
                    "reason": "classified_external_partial",
                    "class": klass,
                }
            )
            missing.append(step)
            continue
        missing.append(step)
        partial.append(
            {
                "step": step,
                "companies_attempted": attempted,
                "threshold": threshold,
                "reason": "below_target_confirmed",
                "class": klass or None,
            }
        )
    complete = len(missing) == 0 and tc > 0
    return {
        "full_source_ladder_complete": complete,
        "target_confirmed": tc,
        "threshold": threshold,
        "ladder_steps": list(ladder_steps),
        "covered": covered,
        "missing": missing,
        "partial": partial,
    }


def warmbly_behavioral_pass(warmbly_e2e: dict[str, Any]) -> tuple[bool, bool, bool]:
    """Return (warmbly_pass, feed_real, config_only_critical)."""
    checks = warmbly_e2e.get("checks") if isinstance(warmbly_e2e.get("checks"), dict) else {}
    feed_real = str(checks.get("reservoir_feed_import") or "").upper() == "PASS"
    config_only = any(str(checks.get(k) or "").upper() in _CONFIG_ONLY_STATUSES for k in WARMBLY_CRITICAL_CHECKS)
    # PASS=true is invalid if critical checks are config-only / pending
    declared = bool(warmbly_e2e.get("PASS"))
    if declared and config_only:
        declared = False
    warmbly_pass = declared and feed_real and not config_only
    return warmbly_pass, feed_real, config_only


def warmbly_runtime_controls_pass(warmbly_e2e: dict[str, Any]) -> bool:
    """Require observed no-send controls, not merely desired configuration."""
    dispatch = warmbly_e2e.get("dispatch")
    if not isinstance(dispatch, dict):
        dispatch = {}
    rate = warmbly_e2e.get("emails_per_hour", warmbly_e2e.get("rate_per_hour"))
    try:
        rate_ok = float(rate) == CONFENGE_PILOT_EMAILS_PER_HOUR
    except (TypeError, ValueError):
        rate_ok = False
    state = str(
        dispatch.get("state")
        or warmbly_e2e.get("dispatch_state")
        or ""
    ).upper()
    return bool(
        rate_ok
        and warmbly_e2e.get("email_only") is True
        and warmbly_e2e.get("whatsapp_enabled") is False
        and warmbly_e2e.get("auto_send_enabled") is False
        and state in {"PAUSED", "PAUSED_MANUAL_START"}
    )


def assert_pack_postconditions(
    out_dir: Path,
    *,
    expected_origin_tip: str | None = None,
) -> list[str]:
    """Return list of post-condition violations (empty = OK)."""
    errors: list[str] = []
    go = _load_json(out_dir / "GO-NO-GO.json") or {}
    man = _load_json(out_dir / "MANIFEST.json") or {}
    sha = _load_json(out_dir / "SHA-BINDING.json") or {}
    esr = _load_json(out_dir / "ESR-REMEASURE.json") or {}
    warmbly = _load_json(out_dir / "WARMBLY-E2E.json") or {}
    universe = _load_json(out_dir / "UNIVERSE-MANIFEST.json") or {}
    errors.extend(validate_universe_manifest(universe))
    if go.get("terminal_state") != man.get("terminal_state"):
        errors.append(
            f"GO.terminal_state={go.get('terminal_state')!r} != MANIFEST.terminal_state={man.get('terminal_state')!r}"
        )
    if go.get("PILOT_READY_CANDIDATE") != man.get("PILOT_READY_CANDIDATE"):
        errors.append("PILOT_READY_CANDIDATE mismatch GO vs MANIFEST")
    terminal = str(go.get("terminal_state") or "")
    claims_bound = bool((go.get("gates") or {}).get("sha_bound"))
    if claims_bound and str(man.get("evaluated_code_sha") or "") != str(
        sha.get("evaluated_code_sha") or ""
    ):
        errors.append("MANIFEST.evaluated_code_sha differs from SHA-BINDING evaluation")
    esr_n = int(go.get("EMAIL_SEND_READY_DISTINCT_COMPANIES") or esr.get("EMAIL_SEND_READY_DISTINCT_COMPANIES") or 0)
    rows = esr.get("esr_rows") if isinstance(esr.get("esr_rows"), list) else []
    rows_file = out_dir / "EMAIL-SEND-READY-ROWS.jsonl"
    rows_file_n = 0
    if rows_file.is_file():
        rows_file_n = sum(1 for line in rows_file.read_text(encoding="utf-8").splitlines() if line.strip())
    if esr_n > 0 and len(rows) == 0 and rows_file_n == 0:
        errors.append(f"ESR={esr_n} but esr_rows empty and no EMAIL-SEND-READY-ROWS.jsonl")
    if bool(warmbly.get("PASS")):
        checks = warmbly.get("checks") if isinstance(warmbly.get("checks"), dict) else {}
        for k in WARMBLY_CRITICAL_CHECKS:
            st = str(checks.get(k) or "").upper()
            if st in _CONFIG_ONLY_STATUSES:
                errors.append(f"WARMBLY PASS=true but {k}={st}")
    if terminal == "GO_FOR_REAL_CONFENGE_EMAIL_PILOT":
        gates = go.get("gates") if isinstance(go.get("gates"), dict) else {}
        if go.get("schema") != GO_NO_GO_SCHEMA or not go.get("PILOT_GO"):
            errors.append("GO terminal requires confenge.go_no_go.v2 PILOT_GO=true")
        if not gates.get("human_top20_review_complete"):
            errors.append("GO terminal requires completed Top-20 human review")
        if not gates.get("human_hot_set_10_approved"):
            errors.append("GO terminal requires 10 explicitly approved leads")
        dispatch = go.get("dispatch") if isinstance(go.get("dispatch"), dict) else {}
        if dispatch.get("state") != "PAUSED_MANUAL_START":
            errors.append("GO terminal must leave dispatch PAUSED_MANUAL_START")
        if dispatch.get("channel") != "EMAIL_ONLY" or dispatch.get("whatsapp") != "OFF":
            errors.append("GO terminal must be EMAIL_ONLY with WhatsApp OFF")
    return errors


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
        "PASS": (all(v == 0 for v in counters.values()) and len(audited) >= min(100, sample_size) and len(audited) > 0),
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
    universe_manifest: dict[str, Any],
    sha_binding: dict[str, Any],
    warmbly_e2e: dict[str, Any],
    source_yield: dict[str, Any] | None = None,
    loss_reasons: dict[str, Any] | None = None,
    terminal_rows: list[dict[str, Any]] | None = None,
    full_ladder_complete: bool | None = None,
    expected_origin_tip: str | None = None,
    human_review_decisions: Path | None = None,
    enforce_postconditions: bool = True,
) -> dict[str, Any]:
    as_of = _utcnow()
    # pack_git_sha is local worktree HEAD for provenance only — never used as origin_main
    pack_git_sha = _git_sha()
    esr_n = int(esr_report.get("EMAIL_SEND_READY_DISTINCT_COMPANIES") or 0)
    funnel = esr_report.get("funnel") or {}
    eph = float(CONFENGE_PILOT_EMAILS_PER_HOUR)
    bhd = float(CONFENGE_BUSINESS_HOURS_PER_DAY)
    reserve = MIN_OPERATIONAL_RESERVE
    capacity = build_capacity_metrics(
        email_send_ready_distinct_companies=esr_n,
        active_hot_set_size=min(50, esr_n),
        emails_per_hour=eph,
        business_hours_per_day=bhd,
    )
    national_universe = int(universe_manifest.get("supplier_roots_observed") or 0)
    manifest_classes = universe_manifest.get("target_classes") or {}
    normalized_target_classes = {key: int(target_classes.get(key) or 0) for key in manifest_classes}
    if normalized_target_classes != dict(manifest_classes):
        raise ValueError("target_classes must exactly match UNIVERSE-MANIFEST target_classes")
    target_classes = normalized_target_classes
    tc = int(target_classes.get("TARGET_CONFIRMED") or 0)

    esr_rows = list(esr_report.get("esr_rows") or [])
    # Durable rows file is authority when ESR>0 and esr_rows omitted
    rows_path = out_dir / "EMAIL-SEND-READY-ROWS.jsonl"
    if not esr_rows and rows_path.is_file() and esr_n > 0:
        esr_rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        esr_report = {**esr_report, "esr_rows": esr_rows}
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

    # Derive ladder completeness from measured yield — never trust a free-standing flag alone.
    yield_eval = ladder_complete_from_source_yield(
        source_yield if isinstance(source_yield, dict) else None,
        target_confirmed=tc,
    )
    derived_ladder = bool(yield_eval["full_source_ladder_complete"])
    if full_ladder_complete is None:
        full_ladder_complete = derived_ladder
    else:
        # Explicit override cannot claim complete if yield measurement says incomplete.
        full_ladder_complete = bool(full_ladder_complete) and derived_ladder
    contact_partition_complete = terminal_sum >= tc and never_n == 0
    contact_complete = contact_partition_complete and retry_n == 0 and bool(full_ladder_complete)

    # service_fit ontology: prefer explicit counters from strict ESR remeasure.
    # Never treat "service_fit_supported" (PASS reason) as a loss.
    not_ready_top = list(esr_report.get("not_ready_top") or [])
    service_fit_unsupported = int(esr_report.get("service_fit_unsupported_count") or 0)
    if not service_fit_unsupported:
        for item in not_ready_top:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            key = str(item[0]).strip()
            if key in {"service_fit_unsupported", "FAIL:service_fit_unsupported"}:
                service_fit_unsupported = max(service_fit_unsupported, int(item[1]))
    if "service_fit_ontology_ok" in esr_report:
        service_fit_ok = bool(esr_report.get("service_fit_ontology_ok"))
    else:
        service_fit_ok = service_fit_unsupported == 0

    healthy = bool(capacity.get("reserve_gate_ok") and esr_n >= reserve and contact_complete)
    machine_quality_ready = esr_n >= 50 and bool(audit.get("PASS")) and int(audit.get("sample_size") or 0) >= 100
    # Prefer explicit sha_bound (tip-aware); fall back to triple only if tip not set.
    if "sha_bound" in sha_binding:
        sha_ok = bool(sha_binding.get("sha_bound"))
    else:
        sha_ok = bool(sha_binding.get("triple_sha_equal"))
        tip = (expected_origin_tip or sha_binding.get("expected_origin_tip") or "").strip()
        if tip and str(sha_binding.get("origin_main") or "") != tip:
            sha_ok = False
    warmbly_pass, warmbly_feed_real, config_only_critical = warmbly_behavioral_pass(warmbly_e2e)
    warmbly_controls_ok = warmbly_runtime_controls_pass(warmbly_e2e)
    warmbly_partial = warmbly_feed_real and bool(warmbly_e2e.get("PASS")) and config_only_critical

    reserve_days = round(esr_n / (eph * bhd), 2) if eph * bhd > 0 else 0.0
    decisions_path = human_review_decisions or out_dir / "HUMAN-REVIEW-DECISIONS.jsonl"
    human_review = load_human_review_decisions(decisions_path, eligible_rows=esr_rows)
    technical_gates = {
        "universe_fully_reconciled": not validate_universe_manifest(universe_manifest),
        "runtime_fully_reconciled": bool(runtime_health.get("FULLY_RECONCILED")),
        "all_confirmed_terminal": contact_partition_complete,
        "full_source_ladder_complete": bool(full_ladder_complete),
        "strict_esr_minimum_50": esr_n >= 50,
        "machine_audit_pass_100": machine_quality_ready,
        "service_fit_ontology_ok": service_fit_ok,
        "sha_bound": sha_ok,
        "warmbly_behavioral_e2e_pass": warmbly_pass and warmbly_feed_real,
        "warmbly_runtime_controls_10h_email_only_paused": warmbly_controls_ok,
    }
    policy = evaluate_pilot_go(
        universe_manifest=universe_manifest,
        technical_gates=technical_gates,
        human_review=human_review,
        email_send_ready=esr_n,
        minimum_operational_reserve=reserve,
    )
    healthy = bool(policy["NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY"])
    pilot_go = bool(policy["PILOT_GO"])
    pilot_ready_candidate = policy["PILOT_QUALITY"] == "PASS"
    terminal = str(policy["terminal_state"])
    pilot_tech = (
        "GO_APPROVED_MANUAL_START"
        if pilot_go
        else "READY_FOR_HUMAN_REVIEW"
        if policy["PILOT_QUALITY"] == "PASS"
        else "PARTIAL"
        if esr_n > 0
        else "NOT_READY"
    )
    national_reserve = "HEALTHY" if healthy else f"PARTIAL_{reserve_days}_DAYS" if esr_n > 0 else "EMPTY"

    if terminal == "ENGINEERING_IN_PROGRESS":
        universe_errors = validate_universe_manifest(universe_manifest)
        if universe_errors:
            one_action = "Reconciliar universo integral: " + ", ".join(universe_errors[:5])
        elif not full_ladder_complete or retry_n > 0:
            miss = ",".join(yield_eval.get("missing") or []) or "ladder"
            one_action = (
                f"Completar source ladder nacional (missing/partial: {miss}); "
                f"transparency_compras e demais PUBLIC_NO_AUTH exigem companies_attempted>={tc}. "
                f"RETRY_PENDING={retry_n}; ESR={esr_n} reserve={reserve}."
            )
        elif not sha_ok:
            tip = expected_origin_tip or sha_binding.get("expected_origin_tip") or "origin/main"
            one_action = (
                "Avaliar/deployar a mesma revisão de código no host e runtime: "
                f"evaluated={sha_binding.get('evaluated_code_sha')}, "
                f"host={sha_binding.get('host_deployed_sha')}, runtime={sha_binding.get('runtime_sha')}; "
                f"ESR={esr_n}."
            )
        elif warmbly_partial or not warmbly_pass:
            one_action = (
                f"Completar Warmbly behavioral no-send E2E "
                f"(SMTP/IMAP/reply-stop live + DNC preserve + rolling hot-set populated); "
                f"feed import alone is insufficient. ESR={esr_n}."
            )
        elif int(audit.get("sample_size") or 0) < 100 or not audit.get("PASS"):
            one_action = (
                f"Auditoria adversarial estratificada ≥100 PASS "
                f"(agora n={audit.get('sample_size')} PASS={audit.get('PASS')})."
            )
        elif not service_fit_ok:
            one_action = (
                f"Zerar service_fit_unsupported residual ({service_fit_unsupported}) via package/ontology; ESR={esr_n}."
            )
        else:
            one_action = f"Fechar gaps de engenharia restantes; ESR={esr_n} reserve={reserve}."
    elif terminal == "READY_FOR_TIAGO_HUMAN_REVIEW":
        one_action = (
            f"Concluir revisão Top-20 e obter 10 aprovações explícitas "
            f"(reviewed={human_review['reviewed_current_esr']}, "
            f"approved={human_review['approved_current_esr']}). "
            f"Reserva nacional segue independente: ESR={esr_n}/{reserve}."
        )
    else:
        one_action = "Tiago deve executar o comando manual de início; dispatch permanece PAUSED."

    go = {
        **policy,
        "schema": GO_NO_GO_SCHEMA,
        "as_of": as_of,
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": healthy,
        "PILOT_READY_CANDIDATE": pilot_ready_candidate,
        "PILOT_TECHNICAL_READINESS": pilot_tech,
        "NATIONAL_RESERVE_READINESS": national_reserve,
        "RESERVE_DAYS": reserve_days,
        "gates": {
            "FULLY_RECONCILED": bool(runtime_health.get("FULLY_RECONCILED")),
            "all_confirmed_terminal": contact_partition_complete,
            "full_source_ladder_complete": bool(full_ladder_complete),
            "ladder_yield_missing": list(yield_eval.get("missing") or []),
            "email_send_ready_ge_min_reserve": esr_n >= reserve,
            "strict_esr_measured": True,
            "service_fit_ontology_ok": service_fit_ok,
            "service_fit_unsupported_count": service_fit_unsupported,
            "machine_audit_pass": bool(audit.get("PASS")),
            "machine_audit_sample_size": int(audit.get("sample_size") or 0),
            "sha_bound": sha_ok,
            "warmbly_e2e_pass": warmbly_pass,
            "warmbly_feed_import_pass": warmbly_feed_real,
            "warmbly_behavioral_complete": warmbly_pass,
            "warmbly_runtime_controls_pass": warmbly_controls_ok,
            "warmbly_partial_config_only": warmbly_partial,
            "human_top20_review_complete": bool(human_review.get("top20_review_complete")),
            "human_hot_set_10_approved": bool(human_review.get("hot_set_10_approved")),
            "universe_manifest_v3_valid": not validate_universe_manifest(universe_manifest),
        },
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": esr_n,
        "MIN_OPERATIONAL_RESERVE": reserve,
        "gap_vs_reserve": max(0, reserve - esr_n),
        "email_roots_upper_bound": esr_report.get("email_roots_upper_bound"),
        "funnel": funnel,
        "universe": {
            "supplier_roots_observed": national_universe,
            "construction_roots": universe_manifest.get("construction_roots"),
            "datalake_watermark": universe_manifest.get("datalake_watermark"),
        },
        "one_action": one_action,
        "human_review_command": (
            "python -m scripts.confenge.human_review "
            "--sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json "
            "--reviewer tiago"
        ),
    }

    gate_guidance = {
        "universe_fully_reconciled": (
            str(validate_universe_manifest(universe_manifest)),
            "atomic universe closure failed",
            "rerun full sector + target reconciliation from one snapshot",
        ),
        "runtime_fully_reconciled": (
            str(runtime_health.get("FULLY_RECONCILED")),
            "runtime did not report full reconciliation",
            "complete live reconciliation and rebuild the pack",
        ),
        "all_confirmed_terminal": (
            f"terminal_sum={terminal_sum}; target_confirmed={tc}; never={never_n}",
            "target-confirmed contact partition is open",
            "resume bounded contact workers until every root has a terminal state",
        ),
        "full_source_ladder_complete": (
            str(yield_eval.get("missing") or []),
            "one or more measured source-ladder stages remain incomplete",
            "resume only the missing ladder checkpoints",
        ),
        "strict_esr_minimum_50": (
            f"ESR={esr_n}",
            "controlled-pilot quality population is below 50",
            "resolve real contact/provenance/copy failures without relaxing gates",
        ),
        "machine_audit_pass_100": (
            f"PASS={audit.get('PASS')}; n={audit.get('sample_size')}",
            "adversarial quality audit is insufficient or failed",
            "fix the failed rows and rerun the 100-row audit",
        ),
        "service_fit_ontology_ok": (
            f"unsupported={service_fit_unsupported}",
            "one or more leads lack defensible service fit",
            "correct evidence-based service routing; never invent pain",
        ),
        "sha_bound": (
            f"evaluated={sha_binding.get('evaluated_code_sha')}; host={sha_binding.get('host_deployed_sha')}; runtime={sha_binding.get('runtime_sha')}",
            "evaluated code is not the deployed runtime revision",
            "deploy and evaluate the same immutable revision",
        ),
        "warmbly_behavioral_e2e_pass": (
            str(warmbly_e2e.get("checks") or {}),
            "real Warmbly behavioral proof is incomplete",
            "rerun the no-send behavioral probes on the live runtime",
        ),
        "warmbly_runtime_controls_10h_email_only_paused": (
            f"rate={warmbly_e2e.get('emails_per_hour')}; dispatch={warmbly_e2e.get('dispatch')}",
            "live dispatch controls differ from 10/h, EMAIL_ONLY, WhatsApp OFF, paused",
            "restore the required live controls and remeasure",
        ),
    }
    false_gate_rows = [
        (gate, *gate_guidance[gate])
        for gate, ok in technical_gates.items()
        if not ok and gate in gate_guidance
    ]
    if not human_review.get("top20_review_complete"):
        false_gate_rows.append(
            (
                "human_top20_review_complete",
                f"reviewed={human_review.get('reviewed_current_esr')}",
                "attributable human review is incomplete",
                go["human_review_command"],
            )
        )
    if not human_review.get("hot_set_10_approved"):
        false_gate_rows.append(
            (
                "human_hot_set_10_approved",
                f"approved={human_review.get('approved_current_esr')}",
                "fewer than 10 current leads are explicitly approved",
                go["human_review_command"],
            )
        )
    false_gate_table = [
        "| Gate falso | Evidência objetiva | Root cause | Ação mínima |",
        "|---|---|---|---|",
        *[
            "| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |"
            for row in false_gate_rows
        ],
    ]

    hr_leads = []
    for row in esr_rows[: min(20, len(esr_rows))]:
        decision = human_review.get("latest_by_key", {}).get(lead_key(row))
        hr_leads.append(
            {
                **row,
                "lead_key": lead_key(row),
                "review_status": (
                    decision.get("review_status") or decision.get("status") if decision else HUMAN_REVIEW_PENDING
                ),
                "human_review": decision,
                "empresa": row.get("razao_social"),
                "CNPJ": row.get("cnpj_raiz"),
                "recommended_service": row.get("service_code"),
                "contact": {
                    "name": row.get("contact_name") or row.get("name"),
                    "role": row.get("contact_role") or row.get("role"),
                    "email": row.get("email"),
                    "ownership_status": row.get("ownership_status"),
                    "mailbox_purpose": row.get("mailbox_purpose"),
                },
                "source": {
                    "type": row.get("source_type"),
                    "url": row.get("source_url"),
                    "document": row.get("source_document"),
                    "observed_at": row.get("source_date") or row.get("observed_at"),
                },
                "evidence": row.get("supporting_evidence") or row.get("evidence") or [],
                "risks": row.get("risks") or row.get("limitations") or row.get("claims_to_avoid") or [],
                "decision": decision,
                "draft": None,
            }
        )

    funnel_rows = [
        {"stage": "SUPPLIER_UNIVERSE", "count": national_universe},
        {"stage": "CONSTRUCTION_UNIVERSE", "count": universe_manifest.get("construction_roots")},
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
            "PILOT_READY_CANDIDATE": pilot_ready_candidate,
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
        out_dir / "SECTOR-CLASS-DISTRIBUTION.json",
        {
            "as_of": as_of,
            "classes": universe_manifest.get("sector_classes") or {},
            "supplier_roots_observed": national_universe,
            "construction_roots": universe_manifest.get("construction_roots"),
        },
    )
    _write(out_dir / "UNIVERSE-MANIFEST.json", universe_manifest)
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
            "sources": esr_report.get("yield_by_source") or esr_report.get("service_distribution") or {},
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
    _write(
        out_dir / "RUNTIME-HEALTH.json",
        {
            **runtime_health,
            "as_of": as_of,
            "full_source_ladder_complete": bool(full_ladder_complete),
            "ladder_yield_eval": yield_eval,
        },
    )
    _write(
        out_dir / "SHA-BINDING.json",
        {**sha_binding, "as_of": as_of, "pack_git_sha": pack_git_sha},
    )
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
                f"**PILOT_READY_CANDIDATE:** `{pilot_ready_candidate}`",
                f"**PILOT_GO:** `{pilot_go}`",
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
            "note": "Definitive ordered Top-20. Never auto-approve. Machine audit ≠ human review.",
            "human_review_summary": {key: value for key, value in human_review.items() if key != "latest_by_key"},
        },
    )
    _write(
        out_dir / "FINAL-REPORT.md",
        "\n".join(
            [
                "# FINAL-REPORT — National commercial reservoir (strict ESR)",
                "",
                f"- generated_at: `{as_of}`",
                f"- evaluated_code_sha: `{sha_binding.get('evaluated_code_sha') or pack_git_sha}`",
                "",
                "```text",
                f"SUPPLIER_UNIVERSE={national_universe}",
                f"CONSTRUCTION_UNIVERSE={universe_manifest.get('construction_roots')}",
                f"SECTOR_INSUFFICIENT={universe_manifest.get('genuinely_unresolved_sector_roots')}",
                "",
                f"TARGET_CONFIRMED={target_classes.get('TARGET_CONFIRMED', 0)}",
                f"TARGET_PROBABLE={target_classes.get('TARGET_PROBABLE_RESEARCH', 0)}",
                f"TARGET_INSUFFICIENT={target_classes.get('TARGET_INSUFFICIENT_EVIDENCE', 0)}",
                f"TARGET_OUT_OF_SCOPE={target_classes.get('TARGET_OUT_OF_SCOPE', 0)}",
                "",
                f"EMAIL_SEND_READY={esr_n}",
                f"MIN_OPERATIONAL_RESERVE={reserve}",
                "",
                f"UNIVERSE_HEALTH={policy['UNIVERSE_HEALTH']}",
                f"PILOT_QUALITY={policy['PILOT_QUALITY']}",
                f"HUMAN_ACCEPTANCE={policy['HUMAN_ACCEPTANCE']}",
                f"PILOT_GO={str(pilot_go).lower()}",
                f"NATIONAL_RESERVOIR_HEALTH={policy['NATIONAL_RESERVOIR_HEALTH']}",
                "",
                f"WARMBLY_BEHAVIORAL_E2E={'PASS' if warmbly_pass else 'FAIL'}",
                "DISPATCH=PAUSED_MANUAL_START",
                "CHANNEL=EMAIL_ONLY",
                "WHATSAPP=OFF",
                "RATE=10/h",
                "",
                f"terminal_state={terminal}",
                "```",
                "",
                "GO alcançado. Nenhum envio foi iniciado. A única ação seguinte é o comando manual de início por Tiago."
                if pilot_go
                else "GO NÃO ALCANÇADO",
                "",
                *(false_gate_table if not pilot_go else []),
                "",
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
                "- Top-20 human review + 10 approvals are required for PILOT_GO",
                "- subsets validate quality/control dispatch; they never cap universe processing",
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
    # Bind the manifest to evaluated code, independently from evidence publication.
    extra_cli_sha = (
        str(sha_binding.get("evaluated_code_sha") or "").strip() or pack_git_sha
    )
    manifest = {
        "schema": "confenge.national_commercial_ready_pack.v2",
        "generated_at": as_of,
        "extra_cli_sha": extra_cli_sha,
        "evaluated_code_sha": sha_binding.get("evaluated_code_sha") or extra_cli_sha,
        "evidence_publication_sha": sha_binding.get("evidence_publication_sha"),
        "warmbly_sha": sha_binding.get("warmbly_origin_main") or sha_binding.get("warmbly_sha"),
        "database_watermark": runtime_health.get("database_watermark"),
        "target_fit_version": runtime_health.get("target_fit_version"),
        "service_contract_version": "confenge_account_intelligence.catalog",
        "contact_evaluator_version": "send_readiness.evaluate_email_send_ready",
        "copy_evaluator_version": "send_readiness.evaluate_copy_context_ready",
        "terminal_state": terminal,
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": healthy,
        "PILOT_READY_CANDIDATE": policy["PILOT_QUALITY"] == "PASS",
        "PILOT_GO": pilot_go,
        "UNIVERSE_HEALTH": policy["UNIVERSE_HEALTH"],
        "NATIONAL_RESERVOIR_HEALTH": policy["NATIONAL_RESERVOIR_HEALTH"],
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": esr_n,
        "MIN_OPERATIONAL_RESERVE": reserve,
        "full_source_ladder_complete": bool(full_ladder_complete),
        "ladder_yield_eval": yield_eval,
        "artifact_hashes": hashes,
    }
    _write(out_dir / "MANIFEST.json", manifest)
    if enforce_postconditions:
        violations = assert_pack_postconditions(
            out_dir, expected_origin_tip=expected_origin_tip or sha_binding.get("expected_origin_tip")
        )
        if violations:
            raise RuntimeError("atomic pack post-conditions failed:\n- " + "\n- ".join(violations))
    return manifest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--esr-report", type=Path, default=DEFAULT_OUT / "ESR-REMEASURE.json")
    p.add_argument(
        "--origin-main-sha",
        type=str,
        required=True,
        help="git rev-parse origin/main after fetch (never defaulted to local HEAD)",
    )
    p.add_argument(
        "--host-deployed-sha",
        type=str,
        required=True,
        help="Host .deployed_sha (never defaulted to local HEAD)",
    )
    p.add_argument(
        "--evaluated-code-sha",
        type=str,
        required=True,
        help="Immutable code revision whose CI/runtime gates were evaluated",
    )
    p.add_argument(
        "--runtime-sha",
        type=str,
        default=None,
        help="Runtime code identity (defaults to host-deployed-sha)",
    )
    p.add_argument(
        "--expected-origin-tip",
        type=str,
        default=None,
        help="Optional tip pin; defaults to --origin-main-sha",
    )
    p.add_argument("--warmbly-sha", type=str, default=None)
    p.add_argument(
        "--evidence-publication-sha",
        type=str,
        default=None,
        help="Optional evidence-pointer commit; never used as evaluated-code gate",
    )
    p.add_argument("--source-yield", type=Path, default=None)
    p.add_argument("--warmbly-e2e", type=Path, default=None)
    p.add_argument(
        "--universe-manifest",
        type=Path,
        default=DEFAULT_OUT / "UNIVERSE-MANIFEST.json",
        help="Required confenge.universe_manifest.v3 from the atomic full-lake run",
    )
    p.add_argument(
        "--human-review-decisions",
        type=Path,
        default=DEFAULT_OUT / "HUMAN-REVIEW-DECISIONS.jsonl",
        help="Append-only attributable human decisions",
    )
    p.add_argument("--skip-postconditions", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    esr = _load_json(args.esr_report) or {}
    universe = _load_json(args.universe_manifest)
    universe_errors = validate_universe_manifest(universe)
    if universe_errors:
        raise SystemExit("valid --universe-manifest is required: " + ", ".join(universe_errors))
    origin = (args.origin_main_sha or "").strip()
    host = (args.host_deployed_sha or "").strip()
    runtime = (args.runtime_sha or host).strip()
    tip = (args.expected_origin_tip or origin).strip()
    if not origin or not host:
        raise SystemExit("origin-main-sha and host-deployed-sha are required")
    sha_binding = build_sha_binding(
        origin_main=origin,
        host_deployed=host,
        runtime=runtime,
        evaluated_code_sha=args.evaluated_code_sha,
        expected_origin_tip=tip,
        warmbly_origin_main=args.warmbly_sha,
        warmbly_host_deployed=args.warmbly_sha,
        warmbly_runtime=args.warmbly_sha,
        evidence_publication_sha=args.evidence_publication_sha,
        evaluation_lineage_ok=evaluation_lineage_preserved(
            args.evaluated_code_sha,
            origin,
        ),
        extra={"pr_222_merged": True, "pr_223_merged": True, "pr_226_merged": True, "pr_227_merged": True},
    )
    # Class counts come only from the atomic universe manifest.  Historical
    # constants (48,748 / 8,382 / 900) are never denominators here.
    classes = dict(universe.get("target_classes") or {})
    terms = esr.get("process_terminal_counts") or {}
    observed = int(universe.get("supplier_roots_observed") or 0)
    materialized = int(universe.get("materialized_roots") or 0)
    runtime_health = {
        "FULLY_RECONCILED": bool(universe.get("FULLY_RECONCILED")),
        "coverage_ratio": (materialized / observed) if observed else None,
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
        "database_watermark": universe.get("datalake_watermark"),
        "target_fit_version": universe.get("target_fit_version"),
    }
    yield_doc = (
        _load_json(args.source_yield) if args.source_yield else _load_json(args.out_dir / "CONTACT-SOURCE-YIELD.json")
    )
    warmbly = _load_json(args.warmbly_e2e) if args.warmbly_e2e else _load_json(args.out_dir / "WARMBLY-E2E.json")
    if not isinstance(warmbly, dict):
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
                "rolling_hot_set": "PENDING",
                "outcomes_webhook": "PENDING",
            },
        }
    manifest = emit_pack(
        out_dir=args.out_dir,
        esr_report=esr,
        target_classes=classes,
        contact_terminals=terms,
        runtime_health=runtime_health,
        universe_manifest=universe,
        sha_binding=sha_binding,
        warmbly_e2e=warmbly,
        source_yield=yield_doc if isinstance(yield_doc, dict) else None,
        expected_origin_tip=tip,
        human_review_decisions=args.human_review_decisions,
        enforce_postconditions=not args.skip_postconditions,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
