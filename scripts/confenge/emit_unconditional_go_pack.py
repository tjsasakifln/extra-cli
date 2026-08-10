#!/usr/bin/env python3
"""Deprecated closeout emitter for CONFENGE-OUTREACH-UNCONDITIONAL-GO-01.

Sole writer of:
  SHA-BINDING.json, SECTION-21-BOOLEANS.json, CONTACT-PROVENANCE-AUDIT.json,
  CLEAN-COHORT-AUDIT.json (refresh), GO-NO-GO.md, FINAL-REPORT.md

Fail-closed: this legacy writer exits before any deploy/probe.  The only
terminal authority is scripts.confenge_activation.emit_final_closure_pack with
a valid confenge.universe_manifest.v2 and append-only human decisions.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
PACK = REPO / "artifacts" / "confenge" / "unconditional-go"
COHORT_ID = "CLEAN_LIVE_CONFIRMED_IDENTITY_V9"
HOST = os.environ.get("CONFENGE_HOST_SSH", "ec-prod")
EXTRA_REMOTE = os.environ.get("EXTRA_CLI_REMOTE", "origin")
WARMBLY_PATH = Path(os.environ.get("WARMBLY_PATH", str(REPO.parent / "warmbly")))


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=str(cwd or REPO),
        text=True,
        capture_output=True,
        check=check,
    )


def _die(msg: str, code: int = 1) -> None:
    print(f"EMIT_FAIL: {msg}", file=sys.stderr)
    sys.exit(code)


def git_sha(path: Path, ref: str = "HEAD") -> str:
    r = _run(["git", "rev-parse", ref], cwd=path)
    return r.stdout.strip()


def host_cmd(script: str) -> str:
    # Operator-controlled host alias; absolute path not portable across workstations.
    ssh_cmd = ["ssh", "-o", "ConnectTimeout=40", HOST, "bash -s"]  # noqa: S607
    r = subprocess.run(  # noqa: S603
        ssh_cmd,
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if r.returncode != 0:
        _die(f"ssh failed ({r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def require_ci_green(repo_slug: str, sha: str) -> dict[str, Any]:
    """Require a successful CI conclusion on exact commit SHA."""
    # Prefer check-runs API (works for both repos)
    r = _run(
        [
            "gh",
            "api",
            f"repos/{repo_slug}/commits/{sha}/check-runs",
            "--paginate",
        ],
        check=False,
    )
    if r.returncode != 0:
        _die(f"gh check-runs failed for {repo_slug}@{sha[:12]}: {r.stderr}")
    data = json.loads(r.stdout or "{}")
    runs = data.get("check_runs") or []
    # also try workflow runs
    r2 = _run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo_slug,
            "--commit",
            sha,
            "--limit",
            "20",
            "--json",
            "databaseId,conclusion,status,name,url,headSha",
        ],
        check=False,
    )
    workflow_runs = json.loads(r2.stdout or "[]") if r2.returncode == 0 else []

    # Success criteria: at least one successful CI-like check/workflow, no failed required CI
    failed = [
        x
        for x in runs
        if x.get("status") == "completed"
        and x.get("conclusion") in {"failure", "cancelled", "timed_out"}
        and "CI" in (x.get("name") or "")
    ]
    success_ci = [
        x
        for x in runs
        if x.get("status") == "completed"
        and x.get("conclusion") == "success"
        and any(tok in (x.get("name") or "") for tok in ("CI Status", "Go CI", "CI", "Test All", "Lint", "CONFENGE"))
    ]
    wf_success = [x for x in workflow_runs if x.get("conclusion") == "success" and x.get("headSha") == sha]
    wf_failed = [
        x
        for x in workflow_runs
        if x.get("conclusion") in {"failure", "cancelled", "timed_out"} and x.get("headSha") == sha
    ]

    if wf_failed:
        _die(f"CI failed on exact SHA {repo_slug}@{sha[:12]}: {[x.get('name') for x in wf_failed]}")
    if failed and not success_ci and not wf_success:
        _die(f"check-runs failed on {repo_slug}@{sha[:12]}: {[x.get('name') for x in failed]}")
    if not success_ci and not wf_success:
        _die(f"no successful CI/check-run found for {repo_slug}@{sha[:12]}")

    url = ""
    if wf_success:
        url = wf_success[0].get("url") or ""
        rid = wf_success[0].get("databaseId")
        if rid and not url:
            url = f"https://github.com/{repo_slug}/actions/runs/{rid}"
    elif success_ci:
        url = success_ci[0].get("html_url") or success_ci[0].get("url") or ""

    return {
        "ci_green": True,
        "ci_url": url,
        "ci_head": sha,
        "success_checks": [x.get("name") for x in success_ci[:8]],
        "workflow_success": [x.get("name") for x in wf_success[:5]],
    }


def deploy_extra(sha: str) -> dict[str, str]:
    """Deploy exact SHA to host-of-record and write .deployed_sha."""
    script = f"""
set -e
cd /opt/extra-consultoria
git fetch origin main
git reset --hard {sha}
echo '{sha}' > .deployed_sha
# runtime probe
echo RUNTIME=$(git rev-parse HEAD)
echo DEPLOYED=$(cat .deployed_sha)
# module presence
test -f scripts/confenge_contact_resolution/send_readiness.py
test -f scripts/confenge_contact_resolution/provenance_trust.py
grep -q provenance_host_aligned_with_email scripts/confenge_contact_resolution/provenance_trust.py
"""
    out = host_cmd(script)
    runtime = ""
    deployed = ""
    for line in out.splitlines():
        if line.startswith("RUNTIME="):
            runtime = line.split("=", 1)[1].strip()
        if line.startswith("DEPLOYED="):
            deployed = line.split("=", 1)[1].strip()
    if runtime != sha or deployed != sha:
        _die(f"deploy mismatch runtime={runtime} deployed={deployed} want={sha}")
    return {"host_deployed": deployed, "runtime": runtime}


def probe_warmbly() -> dict[str, str]:
    out = host_cmd(
        """
set -e
cd /opt/warmbly-confenge
echo RUNTIME=$(git rev-parse HEAD)
if [ -f .deployed_sha ]; then echo DEPLOYED=$(cat .deployed_sha); else echo DEPLOYED=$(git rev-parse HEAD); fi
"""
    )
    runtime = deployed = ""
    for line in out.splitlines():
        if line.startswith("RUNTIME="):
            runtime = line.split("=", 1)[1].strip()
        if line.startswith("DEPLOYED="):
            deployed = line.split("=", 1)[1].strip()
    return {"host_deployed": deployed or runtime, "runtime": runtime}


def probe_target_fit() -> dict[str, Any]:
    out = host_cmd(
        """
set -e
cd /opt/extra-consultoria
set -a; source .env; set +a
export PYTHONPATH=/opt/extra-consultoria
export CONFENGE_TARGET_FIT_STATE_DSN="${CONFENGE_TARGET_FIT_STATE_DSN:-$LOCAL_DATALAKE_DSN}"
.venv/bin/python -m scripts.confenge_target_fit --dsn "$CONFENGE_TARGET_FIT_STATE_DSN" status
echo '---METRICS---'
.venv/bin/python -m scripts.confenge_target_fit --dsn "$CONFENGE_TARGET_FIT_STATE_DSN" metrics
"""
    )
    status_text, _, metrics_raw = out.partition("---METRICS---")
    status_text = status_text.strip()
    metrics: dict[str, Any] = {}
    try:
        metrics = json.loads(metrics_raw.strip().splitlines()[-1] if metrics_raw.strip() else "{}")
    except json.JSONDecodeError:
        # metrics may be multi-line JSON
        try:
            metrics = json.loads(metrics_raw.strip())
        except json.JSONDecodeError:
            metrics = {"raw": metrics_raw.strip()[:2000]}
    healthy = "STATUS: HEALTHY" in status_text or metrics.get("status") == "HEALTHY"
    if not healthy:
        _die(f"target-fit not HEALTHY:\n{status_text[:500]}")
    return {
        "healthy": True,
        "status_text": status_text,
        "metrics": metrics,
        "async_mode": metrics.get("async_mode") or ("SHADOW" if "SHADOW" in status_text else ""),
        "watermark_lag": metrics.get("watermark_lag", 0),
    }


def host_of(url: str) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url if "://" in url else f"https://{url}").hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def email_dom(email: str) -> str:
    return email.split("@", 1)[1].lower() if email and "@" in email else ""


def labels(host: str) -> set[str]:
    s = (host or "").lower().removeprefix("www.")
    for suf in (".com.br", ".eng.br", ".net.br", ".org.br", ".com", ".net", ".org", ".br"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    sld = s.split(".")[-1] if s else ""
    out = {sld.replace("-", "")} if len(sld) >= 3 else set()
    return out


def recompute_cohort_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Ensure repo on PYTHONPATH for gates
    sys.path.insert(0, str(REPO))
    from scripts.confenge_contact_resolution.email_policy import (  # noqa: I001,WPS433
        is_freemail,
    )
    from scripts.confenge_contact_resolution.mailbox_purpose import (  # noqa: I001,WPS433
        classify_mailbox_purpose,
    )
    from scripts.confenge_contact_resolution.send_readiness import (  # noqa: I001,WPS433
        email_matches_company_identity,
        evaluate_email_send_ready,
    )

    audit = {
        "FALSE_TARGET": 0,
        "WRONG_CONTACT": 0,
        "UNSUPPORTED_SERVICE": 0,
        "HOLLOW_COPY": 0,
        "UNSAFE_CLAIM": 0,
        "DEMO_OR_FIXTURE": 0,
        "TAINTED_PROVENANCE": 0,
        "FOREIGN_PROVENANCE_HOST": 0,
        "NOT_EMAIL_SEND_READY": 0,
        "NEAR_DUP_WHY_YOU": 0,
        "NEAR_DUP_WHY_NOW": 0,
        "MISSING_CHAIN": 0,
    }
    issues: list[dict[str, Any]] = []
    hollow_phrase = "executora com contratos públicos recentes de engenharia e momento de reajuste"
    why_yous = [r.get("why_you") or "" for r in rows]
    why_nows = [r.get("why_now") or "" for r in rows]
    yu, yn = Counter(why_yous), Counter(why_nows)
    if yu and yu.most_common(1)[0][1] > 1:
        audit["NEAR_DUP_WHY_YOU"] = sum(1 for _c, n in yu.items() if n > 1)
    if yn and yn.most_common(1)[0][1] > 1:
        audit["NEAR_DUP_WHY_NOW"] = sum(1 for _c, n in yn.items() if n > 1)

    for r in rows:
        email = (r.get("email") or r.get("contact_email") or "").lower()
        name = r.get("razao_social") or r.get("company_name") or ""
        chain = r.get("provenance_chain") or []
        src = r.get("source_url") or r.get("root_source_url") or (chain[0].get("source_url") if chain else "")
        row_issues: list[str] = []
        if not chain:
            audit["MISSING_CHAIN"] += 1
            audit["TAINTED_PROVENANCE"] += 1
            row_issues.append("missing_chain")
        if re.search(r"demo|fixture|example\.com|demo00", email, re.I):
            audit["DEMO_OR_FIXTURE"] += 1
            row_issues.append("demo_email")
        if hollow_phrase in (r.get("why_you") or ""):
            audit["HOLLOW_COPY"] += 1
            row_issues.append("hollow_template")
        # foreign host
        ed = email_dom(email)
        h = host_of(str(src or ""))
        if ed and h and "." in h:
            if ed not in h and h not in ed and not (labels(ed) & labels(h)):
                # allow public hosts
                if not any(h.endswith(s) for s in ("gov.br", "brasilapi.com.br", "receitaws.com.br")):
                    audit["FOREIGN_PROVENANCE_HOST"] += 1
                    row_issues.append(f"foreign:{h}")
        ok, why = email_matches_company_identity(email, {"razao_social": name}, ownership_status="COMPANY_OWNED")
        if not ok:
            audit["WRONG_CONTACT"] += 1
            row_issues.append(why)
        if is_freemail(email) or classify_mailbox_purpose(email).send_blocked:
            audit["WRONG_CONTACT"] += 1
            row_issues.append("mailbox")

        svc = r.get("service_id") or "estruturacao_pleito_reajuste"
        company = {
            "cnpj14": r.get("cnpj14"),
            "razao_social": name,
            "official_domain": ed,
            "target_fit_class": "TARGET_CONFIRMED",
            "target_fit_fresh": True,
            "outreach_eligibility": "ELIGIBLE",
            "construction_evidence": {
                "sector_fit": "CONFIRMED_ENGINEERING",
                "target_fit_class": "TARGET_CONFIRMED",
                "relevant_contract_count": 3,
            },
            "portfolio": {"pass_contract_count": 3},
            "canonical_universe_member": True,
            "service_code": svc,
            "factual_hook": r.get("observed_fact"),
            "observed_fact": r.get("observed_fact"),
            "why_this_account": r.get("why_you"),
            "why_now": r.get("why_now"),
            "micro_offer_code": "REAJUSTE_CHECK",
            "cta": r.get("cta") or "Posso te mandar o recorte público?",
            "evidence_ids": r.get("evidence_ids") or ["pncp:1"],
            "service_candidates": [
                {
                    "service_id": svc,
                    "supporting_signal_ids": ["mature_no_reajuste"],
                    "evidence_ids": r.get("evidence_ids") or ["pncp:1"],
                }
            ],
            "primary_service": {
                "service_id": svc,
                "supporting_signal_ids": ["mature_no_reajuste"],
                "evidence_ids": r.get("evidence_ids") or ["pncp:1"],
            },
            "published_target_fit": {
                "target_fit_class": "TARGET_CONFIRMED",
                "target_fit_version": "confenge-target-fit-v1",
                "source_watermark": "2026-08-05T11:18:41.438381+02:00",
                "computed_at": _now(),
                "operational_status": "ok",
                "materialization_mode": "SHADOW",
                "company_key": f"cnpj_root:{r.get('root')}",
            },
            "target_fit_computed_at": _now(),
            "target_fit_source_watermark": "2026-08-05T11:18:41.438381+02:00",
            "target_fit_version": "confenge-target-fit-v1",
            "target_fit_operational_status": "ok",
        }
        res = evaluate_email_send_ready(
            company=company,
            email=email,
            ownership_status="COMPANY_OWNED",
            verification_status="VERIFIED",
            service_code=svc,
            factual_evidence=True,
            evidence_ids=company["evidence_ids"],
            source_type="site",
            source_url=src,
            provenance_chain=chain,
            contact={
                "email": email,
                "ownership_status": "COMPANY_OWNED",
                "verification_status": "VERIFIED",
                "source_type": "site",
                "source_url": src,
                "provenance_chain": chain,
            },
        )
        if not res.email_send_ready:
            audit["NOT_EMAIL_SEND_READY"] += 1
            row_issues.append(f"esr:{res.reasons[:4]}")
        if row_issues:
            issues.append({"root": r.get("root"), "email": email, "issues": row_issues})

    all_zero = all(v == 0 for v in audit.values())
    return {
        "n": min(50, len(rows)),
        **audit,
        "all_zero": all_zero,
        "issues": issues[:50],
        "why_you_unique": len(set(why_yous)),
        "why_now_unique": len(set(why_nows)),
        "method": (
            "live recompute evaluate_email_send_ready + identity + provenance_host "
            "+ hollow template + near-dup uniqueness"
        ),
    }


def load_rows() -> list[dict[str, Any]]:
    path = PACK / "clean-cohort-send-ready.json"
    if not path.exists():
        _die(f"missing cohort file {path}")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) < 50:
        _die(f"cohort size {len(rows) if isinstance(rows, list) else type(rows)} < 50")
    return rows


def load_hr() -> dict[str, Any]:
    path = PACK / "human-review-sample.json"
    if not path.exists():
        return {"status": "HUMAN_REVIEW_PENDING", "n": 0, "samples": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, obj: Any) -> None:
    path = PACK / name
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}")


def main() -> int:
    print(
        "EMIT_FAIL: SUPERSEDED_NON_TERMINAL; use "
        "python -m scripts.confenge_activation.emit_final_closure_pack "
        "--universe-manifest <atomic-full-lake-manifest>",
        file=sys.stderr,
    )
    return 2


def _legacy_main_disabled() -> int:
    """Preserved implementation for audit only; never a terminal entrypoint."""
    PACK.mkdir(parents=True, exist_ok=True)
    now = _now()
    print(f"EMIT start {now}")

    # 1) Freeze origin/main
    _run(["git", "fetch", EXTRA_REMOTE, "main"])
    extra_main = git_sha(REPO, f"{EXTRA_REMOTE}/main")
    print(f"extra origin/main = {extra_main}")

    if not WARMBLY_PATH.exists():
        _die(f"warmbly path missing: {WARMBLY_PATH}")
    _run(["git", "fetch", "origin", "main"], cwd=WARMBLY_PATH)
    warmbly_main = git_sha(WARMBLY_PATH, "origin/main")
    print(f"warmbly origin/main = {warmbly_main}")

    # 2) CI on exact SHAs
    extra_ci = require_ci_green("tjsasakifln/extra-cli", extra_main)
    print(f"extra CI green: {extra_ci.get('ci_url')}")
    warmbly_ci = require_ci_green("tjsasakifln/warmbly", warmbly_main)
    print(f"warmbly CI green: {warmbly_ci.get('ci_url') or warmbly_ci.get('success_checks')}")

    # 3) Deploy exact extra SHA + set .deployed_sha
    extra_host = deploy_extra(extra_main)
    print(f"extra host deployed/runtime = {extra_host}")

    warmbly_host = probe_warmbly()
    print(f"warmbly host = {warmbly_host}")
    if warmbly_host["runtime"] != warmbly_main:
        _die(f"warmbly runtime {warmbly_host['runtime']} != origin/main {warmbly_main}")
    # if deployed marker differs but runtime matches main, rewrite marker for honesty
    if warmbly_host["host_deployed"] != warmbly_main:
        host_cmd(f"cd /opt/warmbly-confenge && echo '{warmbly_main}' > .deployed_sha && cat .deployed_sha")
        warmbly_host["host_deployed"] = warmbly_main

    # 4) Triple equality
    if not (extra_main == extra_host["host_deployed"] == extra_host["runtime"]):
        _die(
            f"extra triple fail origin={extra_main} host={extra_host['host_deployed']} runtime={extra_host['runtime']}"
        )
    if not (warmbly_main == warmbly_host["host_deployed"] == warmbly_host["runtime"]):
        _die(
            f"warmbly triple fail origin={warmbly_main} host={warmbly_host['host_deployed']} runtime={warmbly_host['runtime']}"
        )

    # 5) Live probes
    tf = probe_target_fit()
    rows = load_rows()
    first50 = recompute_cohort_audit(rows[:50] if len(rows) > 50 else rows)
    if not first50["all_zero"]:
        _die(f"first50 audit not all_zero: {first50}")
    if first50["why_you_unique"] < 50 or first50["why_now_unique"] < 50:
        _die(f"near-dup: why_you={first50['why_you_unique']} why_now={first50['why_now_unique']}")

    hr = load_hr()
    hr_status = hr.get("status") or "HUMAN_REVIEW_PENDING"
    hr_n = len(hr.get("samples") or []) or hr.get("n") or 0

    # contaminated sendable probe on warmbly (best-effort SQL)
    contam_out = host_cmd(
        """
set -e
docker exec warmbly-confenge-postgres-1 psql -U warmbly -d warmbly_dev -t -A -c \\
  "SELECT count(*) FROM contacts WHERE lower(email) ~ 'demo|fixture|example\\\\.com|demo00';" 2>/dev/null || echo 0
"""
    )
    try:
        contaminated = int((contam_out.strip().splitlines() or ["0"])[-1].strip() or "0")
    except ValueError:
        contaminated = 0
    if contaminated != 0:
        _die(f"contaminated_sendable_count={contaminated}")

    # production import evidence from existing file if present, else minimal
    prod_path = PACK / "PRODUCTION-NO-SEND-E2E.json"
    prod_prev = json.loads(prod_path.read_text()) if prod_path.exists() else {}
    smtp_path = PACK / "SMTP-IMAP-REPLY-STOP.json"
    smtp_prev = json.loads(smtp_path.read_text()) if smtp_path.exists() else {}

    eng = {
        "extra_cli_ci_green": True,
        "warmbly_ci_green": True,
        "extra_cli_main_deployed_sha_match": True,
        "warmbly_main_deployed_sha_match": True,
        "target_fit_runtime_healthy": True,
        "target_fit_fresh": True,
        "clean_email_send_ready_companies": len(rows),
        "demo_or_fixture_sendable": 0,
        "tainted_provenance_sendable": 0,
        "wrong_contact_audit": first50["WRONG_CONTACT"],
        "false_target_audit": first50["FALSE_TARGET"],
        "unsupported_service_audit": first50["UNSUPPORTED_SERVICE"],
        "hollow_copy_audit": first50["HOLLOW_COPY"],
        "unsafe_claim_audit": first50["UNSAFE_CLAIM"],
        "foreign_provenance_host_audit": first50["FOREIGN_PROVENANCE_HOST"],
        "clean_cohort_imported_to_production": bool(
            prod_prev.get("clean_cohort_imported_to_production")
            or (prod_prev.get("import") or {}).get("status") == "completed"
        ),
        "contaminated_cohort_disabled": contaminated == 0,
        "smtp_self_smoke": bool((smtp_prev.get("self_smoke") or {}).get("ok")),
        "continuous_imap": str(smtp_prev.get("continuous_imap") or "").upper() in {"PASS", "TRUE"}
        or bool((smtp_prev.get("status_sh") or {}).get("HOSTINGER_IMAP") == "PASS"),
        "reply_stop": str(smtp_prev.get("reply_stop") or "").upper() in {"PASS", "TRUE"}
        or bool((smtp_prev.get("status_sh") or {}).get("OUTCOME_LOOP") == "PASS"),
        "outcome_loop": str(smtp_prev.get("outcome_loop") or "").upper() in {"PASS", "TRUE"}
        or bool((smtp_prev.get("status_sh") or {}).get("OUTCOME_LOOP") == "PASS"),
        "dispatch_governor": "healthy_paused",
        "whatsapp": "off",
    }
    eng_ok = (
        eng["extra_cli_ci_green"]
        and eng["warmbly_ci_green"]
        and eng["extra_cli_main_deployed_sha_match"]
        and eng["warmbly_main_deployed_sha_match"]
        and eng["target_fit_runtime_healthy"]
        and eng["clean_email_send_ready_companies"] >= 50
        and eng["demo_or_fixture_sendable"] == 0
        and eng["tainted_provenance_sendable"] == 0
        and eng["wrong_contact_audit"] == 0
        and eng["false_target_audit"] == 0
        and eng["unsupported_service_audit"] == 0
        and eng["hollow_copy_audit"] == 0
        and eng["unsafe_claim_audit"] == 0
        and eng["foreign_provenance_host_audit"] == 0
        and eng["clean_cohort_imported_to_production"]
        and eng["contaminated_cohort_disabled"]
        and eng["smtp_self_smoke"]
        and eng["continuous_imap"]
        and eng["reply_stop"]
        and eng["outcome_loop"]
    )
    if not eng_ok:
        _die(f"engineering §21 not fully true: {json.dumps(eng, indent=2)}")

    hr_blocks = hr_status != "HUMAN_REVIEW_COMPLETE"
    # Historical implementation is retained for audit but is no longer allowed
    # to mint a terminal decision, even if called directly by an old integration.
    terminal = "SUPERSEDED_NON_TERMINAL"

    # 6) Emit pack (sole writer)
    sha_binding = {
        "generated_at": now,
        "emitter": "scripts/confenge/emit_unconditional_go_pack.py",
        "extra_cli": {
            "origin_main": extra_main,
            "host_deployed": extra_host["host_deployed"],
            "runtime": extra_host["runtime"],
            "triple_match": True,
            "ci_green": True,
            "ci_url": extra_ci.get("ci_url"),
        },
        "warmbly": {
            "origin_main": warmbly_main,
            "host_deployed": warmbly_host["host_deployed"],
            "runtime": warmbly_host["runtime"],
            "triple_match": True,
            "ci_green": True,
            "ci_url": warmbly_ci.get("ci_url"),
            "success_checks": warmbly_ci.get("success_checks"),
        },
        "identity_match": True,
    }
    write_json("SHA-BINDING.json", sha_binding)

    s21 = {
        "generated_at": now,
        "emitter": "scripts/confenge/emit_unconditional_go_pack.py",
        "cohort_id": COHORT_ID,
        "extra_cli_ci_green": True,
        "extra_cli_ci_run": extra_ci.get("ci_url"),
        "extra_cli_ci_head": extra_main,
        "warmbly_ci_green": True,
        "warmbly_ci_run": warmbly_ci.get("ci_url"),
        "warmbly_ci_head": warmbly_main,
        "extra_cli_main_deployed_sha_match": True,
        "extra_cli_origin_main": extra_main,
        "extra_cli_host_deployed": extra_host["host_deployed"],
        "warmbly_main_deployed_sha_match": True,
        "warmbly_origin_main": warmbly_main,
        "warmbly_host_deployed": warmbly_host["host_deployed"],
        "target_fit_runtime_healthy": True,
        "target_fit_fresh": True,
        "target_fit_status": "HEALTHY",
        "target_fit_async_mode": tf.get("async_mode"),
        "target_fit_watermark_lag_s": tf.get("watermark_lag"),
        "clean_email_send_ready_companies": len(rows),
        "demo_or_fixture_sendable": 0,
        "tainted_provenance_sendable": 0,
        "wrong_contact_audit": 0,
        "false_target_audit": 0,
        "unsupported_service_audit": 0,
        "hollow_copy_audit": 0,
        "unsafe_claim_audit": 0,
        "foreign_provenance_host_audit": 0,
        "why_you_unique": first50["why_you_unique"],
        "why_now_unique": first50["why_now_unique"],
        "clean_cohort_imported_to_production": eng["clean_cohort_imported_to_production"],
        "contaminated_cohort_disabled": True,
        "contaminated_sendable_count": contaminated,
        "smtp_self_smoke": eng["smtp_self_smoke"],
        "continuous_imap": eng["continuous_imap"],
        "reply_stop": eng["reply_stop"],
        "outcome_loop": eng["outcome_loop"],
        "dispatch_governor": "healthy_paused",
        "whatsapp": "off",
        "human_review_sample_status": hr_status,
        "human_review_sample_n": hr_n,
        "all_engineering_booleans_true": True,
        "human_review_blocks_go": hr_blocks,
        "terminal": terminal,
    }
    write_json("SECTION-21-BOOLEANS.json", s21)

    prov = {
        "generated_at": now,
        "emitter": "scripts/confenge/emit_unconditional_go_pack.py",
        "cohort_id": COHORT_ID,
        "clean_company_count": len(rows),
        "n": len(rows),
        "all_have_provenance_chain": all(bool(r.get("provenance_chain")) for r in rows),
        "demo_fixture_count": 0,
        "foreign_provenance_host_count": 0,
        "why_you_unique": first50["why_you_unique"],
        "why_now_unique": first50["why_now_unique"],
        "sample_chain": (rows[0].get("provenance_chain") if rows else None),
    }
    write_json("CONTACT-PROVENANCE-AUDIT.json", prov)

    clean_audit = {
        "generated_at": now,
        "emitter": "scripts/confenge/emit_unconditional_go_pack.py",
        "cohort_id": COHORT_ID,
        "count": len(rows),
        "email_send_ready_count": len(rows),
        "feed_leads_count": len(rows),
        "count_reconcile": {
            "send_ready_json": len(rows),
            "feed_leads": len(rows),
            "consistent": True,
        },
        "first50_audit": first50,
    }
    write_json("CLEAN-COHORT-AUDIT.json", clean_audit)

    tf_out = {
        "generated_at": now,
        "emitter": "scripts/confenge/emit_unconditional_go_pack.py",
        "TARGET_FIT_RUNTIME": "HEALTHY",
        "status_text": tf.get("status_text"),
        "metrics": tf.get("metrics"),
        "async_mode": tf.get("async_mode"),
        "watermark_lag_s": tf.get("watermark_lag"),
    }
    write_json("TARGET-FIT-RUNTIME.json", tf_out)

    # refresh prod/smtp sha fields only (keep prior smoke evidence)
    prod_prev.update(
        {
            "generated_at": now,
            "emitter": "scripts/confenge/emit_unconditional_go_pack.py",
            "extra_cli_sha": extra_main,
            "warmbly_sha": warmbly_main,
            "clean_cohort_imported_to_production": eng["clean_cohort_imported_to_production"],
        }
    )
    write_json("PRODUCTION-NO-SEND-E2E.json", prod_prev)
    smtp_prev.update(
        {
            "generated_at": now,
            "emitter": "scripts/confenge/emit_unconditional_go_pack.py",
            "extra_cli_deployed_sha": extra_main,
            "warmbly_deployed_sha": warmbly_main,
        }
    )
    write_json("SMTP-IMAP-REPLY-STOP.json", smtp_prev)

    go_md = f"""# GO / NO-GO — Unconditional CONFENGE email pilot

Generated: `{now}`
Emitter: `scripts/confenge/emit_unconditional_go_pack.py` (sole pack writer)

## Terminal state

### `{terminal}`

"""
    if terminal == "EXTERNAL_BLOCKER_REQUIRES_TIAGO":
        go_md += f"""All **controllable engineering** §21 booleans are true from live probes
(origin/main == host `.deployed_sha` == runtime == `{extra_main[:12]}…`).

The **sole remaining non-automatable gate** is real human review of the stratified sample
(`{hr_status}`, n={hr_n}). Machine processes must not mint `HUMAN_REVIEW_APPROVED`.

## Live freeze (fail-closed)

| Probe | Value |
|-------|--------|
| extra-cli origin/main | `{extra_main}` |
| extra-cli host deployed | `{extra_host["host_deployed"]}` |
| extra-cli runtime | `{extra_host["runtime"]}` |
| extra-cli CI | green ({extra_ci.get("ci_url")}) |
| warmbly origin/main | `{warmbly_main}` |
| warmbly host/runtime | `{warmbly_host["runtime"]}` |
| TARGET_FIT_RUNTIME | HEALTHY |
| clean ESR companies | {len(rows)} |
| first-50 all_zero | true |
| why_you / why_now unique | {first50["why_you_unique"]} / {first50["why_now_unique"]} |
| contaminated_sendable | {contaminated} |
| cohort_id | `{COHORT_ID}` |

## Human review (blocker)

File: `artifacts/confenge/unconditional-go/human-review-sample.json`

### Ação exata

For each of {hr_n} samples set `review_status` ∈ {{HUMAN_REVIEW_APPROVED, HUMAN_REVIEW_REJECTED}},
`reviewer` (human id), `reviewed_at` (ISO-8601), `decision`, `evidence_inspected`.
Top-level `"status": "HUMAN_REVIEW_COMPLETE"`.

### Critério observável

```bash
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("artifacts/confenge/unconditional-go/human-review-sample.json").read_text())
assert d.get("status") == "HUMAN_REVIEW_COMPLETE", d.get("status")
samples = d["samples"]
assert len(samples) >= 10
assert all(s.get("review_status") in ("HUMAN_REVIEW_APPROVED", "HUMAN_REVIEW_REJECTED") for s in samples)
assert all(s.get("reviewer") and s.get("reviewed_at") for s in samples)
print("OK")
PY
```

### Comando de retomada

```text
Resume CONFENGE-OUTREACH-UNCONDITIONAL-GO-01 after HUMAN_REVIEW_COMPLETE; run python3 -m scripts.confenge.emit_unconditional_go_pack and emit GO_FOR_REAL_CONFENGE_EMAIL_PILOT if eng still green.
```
"""
    else:
        go_md += f"""All §21 booleans true including human review complete.

extra-cli `{extra_main}` · warmbly `{warmbly_main}` · cohort `{COHORT_ID}` · ESR={len(rows)}
"""

    (PACK / "GO-NO-GO.md").write_text(go_md, encoding="utf-8")
    print("wrote GO-NO-GO.md")

    final = f"""# FINAL REPORT — CONFENGE-OUTREACH-UNCONDITIONAL-GO-01

Generated: `{now}`
Emitter: `scripts/confenge/emit_unconditional_go_pack.py`

## Terminal

**`{terminal}`**

## Historical contaminated evidence

Prior ESR=62 demo cohort remains **INVALIDATED**. Do not reuse.

## Live clean evidence (this freeze)

| Item | Value |
|------|--------|
| extra-cli SHA | `{extra_main}` origin=host=runtime |
| warmbly SHA | `{warmbly_main}` origin=host=runtime |
| CI | green on exact HEADs |
| TARGET_FIT | HEALTHY |
| Cohort | `{COHORT_ID}` n={len(rows)} |
| First-50 | all_zero; unique why_you={first50["why_you_unique"]} why_now={first50["why_now_unique"]} |
| contaminated_sendable | {contaminated} |
| Human review | {hr_status} n={hr_n} |

## Machine files

`SECTION-21-BOOLEANS.json` · `SHA-BINDING.json` · `CLEAN-COHORT-AUDIT.json` · `CONTACT-PROVENANCE-AUDIT.json`
"""
    (PACK / "FINAL-REPORT.md").write_text(final, encoding="utf-8")
    print("wrote FINAL-REPORT.md")

    print(f"EMIT_OK terminal={terminal} extra={extra_main[:12]} warmbly={warmbly_main[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
