#!/usr/bin/env python3
"""Fail-closed soak tracker for operational contracts / open tenders SLA.

Records observations under campaign artifacts. Does **not** invent green days.
All calendar keys use UTC: ``datetime.now(UTC).date()``.

``health_ok=true`` only when every applicable requirement is true, including:

* contracts timer enabled + active
* contracts service success + run_id
* contracts freshness <=168h (ingestion/artifact — never document date)
* contracts coverage >=95%
* open_tenders timer family enabled + active
* open_tenders freshness <=24h
* open_tenders coverage >=95%
* zero failed critical units
* automatic_execution proven (systemd invocation), not CLI default

Missing measurement is a gap day — never silent success.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]

CONTRACTS_SLA_HOURS = 168
OPEN_TENDERS_SLA_HOURS = 24
COVERAGE_MIN = 0.95
DEFAULT_CAMPAIGN = "EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01"
DUAL_SUMMARY_CANDIDATES = (
    "output/coverage/dual-campaign-orrc-01/dual-capability-coverage-summary.json",
    "output/coverage/dual-latest/dual-capability-coverage-summary.json",
    "output/coverage/dual-capability-coverage-summary.json",
)


def _is_vps_host() -> bool:
    try:
        if Path("/root/.extra-pg-credentials").is_file():
            return True
    except OSError:
        pass
    try:
        if Path("/opt/extra-consultoria").is_dir() and Path(
            "/var/lib/extra-consultoria"
        ).is_dir():
            host = os.uname().nodename if hasattr(os, "uname") else ""
            return host.startswith("v") or host.startswith("v220")
    except OSError:
        pass
    return False


def _run_local(cmd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(  # noqa: S603
            ["/bin/bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


def _ssh(cmd: str) -> tuple[int, str]:
    if _is_vps_host():
        return _run_local(cmd)
    try:
        r = subprocess.run(  # noqa: S603
            [
                "/usr/bin/ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "ec-prod",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


def _detect_automatic_execution(*, force_automatic: bool = False) -> bool:
    """True only when invoked by systemd timer/service or explicit --automatic.

    NO_MANUAL_RUN_AS_AUTOMATION: bare CLI defaults to False.
    """
    if force_automatic:
        return True
    if os.environ.get("SOAK_AUTOMATIC", "").strip() in {"1", "true", "yes"}:
        return True
    # systemd sets INVOCATION_ID for service units
    if os.environ.get("INVOCATION_ID"):
        return True
    if os.environ.get("JOURNAL_STREAM"):
        return True
    return False


def _load_dual_coverage(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or _ROOT
    for rel in DUAL_SUMMARY_CANDIDATES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        caps = data.get("capabilities") or {}
        out: dict[str, Any] = {
            "dual_summary_path": str(path),
            "dual_gate_status": data.get("dual_gate_status"),
            "pipeline_success": data.get("pipeline_success"),
            "scope_complete": data.get("scope_complete"),
        }
        for cap in ("open_tenders", "historical_contracts"):
            c = caps.get(cap) or {}
            if not isinstance(c, dict):
                continue
            pct = c.get("coverage_pct")
            try:
                pct_f = float(pct) if pct is not None else None
            except (TypeError, ValueError):
                pct_f = None
            # dual reports coverage_pct as 0-100 scale
            if pct_f is not None and pct_f > 1.0:
                pct_f = pct_f / 100.0
            out[f"{cap}_coverage"] = pct_f
            out[f"{cap}_covered"] = c.get("covered_numerator")
            out[f"{cap}_denom"] = c.get("applicable_denominator") or c.get(
                "universe_count"
            )
            out[f"{cap}_gate"] = c.get("gate_status")
        return out
    return {}


def _measure_runtime() -> tuple[int, str]:
    """Collect runtime signals. Freshness must NOT use document publication dates."""
    return _ssh(
        "set +e; "
        "failed=$(systemctl --failed --plain --no-legend 2>/dev/null | wc -l); "
        "echo failed_units=$failed; "
        "echo failed_critical=$(systemctl --failed --plain --no-legend 2>/dev/null | "
        "grep -E 'pncp-contracts|extra-weekly|extra-health|extra-contracts-soak|"
        "extra-crawl-pncp|extra-crawl-ciga' | wc -l); "
        "echo health_timer=$(systemctl is-active extra-health-check.timer 2>/dev/null || true); "
        "echo contracts_timer=$(systemctl is-active pncp-contracts.timer 2>/dev/null || true); "
        "echo contracts_timer_enabled=$(systemctl is-enabled pncp-contracts.timer 2>/dev/null || true); "
        "echo contracts_last_trigger=$(systemctl show pncp-contracts.timer -p LastTriggerUSec --value 2>/dev/null || true); "
        "echo contracts_next_trigger=$(systemctl show pncp-contracts.timer -p NextElapseUSecRealtime --value 2>/dev/null || true); "
        "echo last_contracts_result=$(systemctl show pncp-contracts.service -p Result --value 2>/dev/null || true); "
        "echo last_contracts_exec=$(systemctl show pncp-contracts.service -p ExecMainStatus --value 2>/dev/null || true); "
        "echo editais_pncp_timer=$(systemctl is-active extra-crawl-pncp.timer 2>/dev/null || true); "
        "echo editais_pncp_timer_enabled=$(systemctl is-enabled extra-crawl-pncp.timer 2>/dev/null || true); "
        "echo editais_ciga_timer=$(systemctl is-active extra-crawl-ciga-ckan.timer 2>/dev/null || true); "
        "echo editais_ciga_timer_enabled=$(systemctl is-enabled extra-crawl-ciga-ckan.timer 2>/dev/null || true); "
        "echo last_editais_pncp_result=$(systemctl show extra-crawl-pncp.service -p Result --value 2>/dev/null || true); "
        "echo host=$(hostname 2>/dev/null || true); "
        "echo deployed_sha=$(cat /opt/extra-consultoria/.deployed_sha 2>/dev/null || "
        "git -C /opt/extra-consultoria rev-parse HEAD 2>/dev/null || true); "
        "if [ -f /root/.extra-pg-credentials ]; then . /root/.extra-pg-credentials; fi; "
        "if [ -f /opt/extra-consultoria/.env ]; then set -a; . /opt/extra-consultoria/.env; set +a; fi; "
        "if [ -n \"${LOCAL_DATALAKE_DSN:-}${DATABASE_URL:-}\" ]; then "
        "export LOCAL_DATALAKE_DSN=\"${LOCAL_DATALAKE_DSN:-$DATABASE_URL}\"; "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'contracts_count='||count(*) FROM pncp_supplier_contracts;\" 2>/dev/null; "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'contracts_ingest_age_hours='||COALESCE("
        "round(EXTRACT(EPOCH FROM (now() - max(completed_at)))/3600.0, 2), 99999) "
        "FROM ingestion_runs WHERE source IN ('contracts','pncp_contracts') "
        "AND status IN ('completed','success') "
        "AND completed_at IS NOT NULL;\" 2>/dev/null; "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'contracts_run_id='||COALESCE("
        "(SELECT meta->>'run_id' FROM ingestion_runs "
        "WHERE source IN ('contracts','pncp_contracts') "
        "AND status IN ('completed','success') "
        "ORDER BY completed_at DESC NULLS LAST LIMIT 1), '');\" 2>/dev/null; "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'editais_obs_age_hours='||COALESCE("
        "round(EXTRACT(EPOCH FROM (now() - max(completed_at)))/3600.0, 2), 99999) "
        "FROM coverage_evidence WHERE capability='open_tenders' "
        "AND completed_at IS NOT NULL;\" 2>/dev/null; "
        "fi; "
        # dual summary mtime as open_tenders freshness fallback (observation time)
        "for f in "
        "/opt/extra-consultoria/output/coverage/dual-campaign-orrc-01/dual-capability-coverage-summary.json "
        "/opt/extra-consultoria/output/coverage/dual-capability-coverage-summary.json; do "
        "if [ -f \"$f\" ]; then "
        "echo dual_summary_age_hours=$(python3 -c \"import os,time;print(round((time.time()-os.path.getmtime('$f'))/3600,2))\" 2>/dev/null); "
        "break; fi; done; "
        "if [ -f /opt/extra-consultoria/output/contracts/incremental-latest.json ]; then "
        "echo contracts_artifact_age_hours=$(python3 -c "
        "\"import os,time; p='/opt/extra-consultoria/output/contracts/incremental-latest.json'; "
        "print(round((time.time()-os.path.getmtime(p))/3600,2))\" 2>/dev/null); "
        "echo contracts_artifact_run_id=$(python3 -c "
        "\"import json; d=json.load(open('/opt/extra-consultoria/output/contracts/incremental-latest.json')); "
        "print(d.get('run_id') or '')\" 2>/dev/null); "
        "fi; "
        "for f in "
        "/opt/extra-consultoria/output/coverage/dual-campaign-orrc-01/dual-capability-coverage-summary.json "
        "/opt/extra-consultoria/output/coverage/dual-latest/dual-capability-coverage-summary.json "
        "/opt/extra-consultoria/output/coverage/dual-capability-coverage-summary.json; do "
        "if [ -f \"$f\" ]; then "
        "echo dual_summary_path=$f; "
        "python3 -c \"import json;d=json.load(open('$f'));"
        "c=d.get('capabilities') or {};"
        "ot=(c.get('open_tenders') or {});hc=(c.get('historical_contracts') or {});"
        "print('open_tenders_coverage_pct='+str(ot.get('coverage_pct')));"
        "print('historical_contracts_coverage_pct='+str(hc.get('coverage_pct')));"
        "print('dual_gate_status='+str(d.get('dual_gate_status')));"
        "\" 2>/dev/null; "
        "break; fi; done"
    )


def _parse_kv(out: str) -> dict[str, str]:
    kv: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.partition("=")
            kv[k.strip()] = v.strip()
    return kv


def _pct_to_fraction(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f > 1.0:
        return f / 100.0
    return f


def _compute_health_ok(obs: dict[str, Any]) -> tuple[bool, list[str]]:
    """Fail-closed health. Every failure reason is listed."""
    reasons: list[str] = []
    if obs.get("failed_critical_units") not in (0, "0"):
        reasons.append("failed_critical_units")

    # --- contracts automation ---
    if obs.get("contracts_timer") not in {"active"}:
        reasons.append("contracts_timer_not_active")
    if obs.get("contracts_timer_enabled") not in {"enabled", "static"}:
        reasons.append("contracts_timer_not_enabled")
    if obs.get("last_contracts_result") != "success":
        reasons.append("last_contracts_result_not_success")
    exec_st = obs.get("last_contracts_exec")
    if exec_st not in (None, "", "0", 0, "75", 75):
        try:
            if int(exec_st) not in (0, 75):
                reasons.append(f"last_contracts_exec={exec_st}")
        except (TypeError, ValueError):
            reasons.append(f"last_contracts_exec_unparseable={exec_st}")
    if not obs.get("run_id"):
        reasons.append("missing_run_id")

    fresh = obs.get("contracts_freshness_hours")
    if fresh is None:
        reasons.append("missing_contracts_freshness")
    else:
        try:
            if float(fresh) > CONTRACTS_SLA_HOURS:
                reasons.append(f"contracts_stale_h={fresh}")
        except (TypeError, ValueError):
            reasons.append("contracts_freshness_unparseable")

    cc = obs.get("contracts_coverage")
    if cc is None:
        reasons.append("missing_contracts_coverage")
    else:
        try:
            if float(cc) < COVERAGE_MIN:
                reasons.append(f"contracts_coverage_below_95={cc}")
        except (TypeError, ValueError):
            reasons.append("contracts_coverage_unparseable")

    # --- open tenders automation ---
    if obs.get("editais_pncp_timer") not in {"active"}:
        reasons.append("editais_pncp_timer_not_active")
    if obs.get("editais_pncp_timer_enabled") not in {"enabled", "static"}:
        reasons.append("editais_pncp_timer_not_enabled")
    # CIGA is weekly; require enabled (active between fires is still "active" for timers)
    if obs.get("editais_ciga_timer_enabled") not in {"enabled", "static"}:
        reasons.append("editais_ciga_timer_not_enabled")
    if obs.get("editais_ciga_timer") not in {"active"}:
        reasons.append("editais_ciga_timer_not_active")

    ot_fresh = obs.get("open_tenders_freshness_hours")
    if ot_fresh is None:
        reasons.append("missing_open_tenders_freshness")
    else:
        try:
            if float(ot_fresh) > OPEN_TENDERS_SLA_HOURS:
                reasons.append(f"open_tenders_stale_h={ot_fresh}")
        except (TypeError, ValueError):
            reasons.append("open_tenders_freshness_unparseable")

    otc = obs.get("open_tenders_coverage")
    if otc is None:
        reasons.append("missing_open_tenders_coverage")
    else:
        try:
            if float(otc) < COVERAGE_MIN:
                reasons.append(f"open_tenders_coverage_below_95={otc}")
        except (TypeError, ValueError):
            reasons.append("open_tenders_coverage_unparseable")

    # Manual / unproven automation is never soak green
    if obs.get("automatic_execution") is not True:
        reasons.append("manual_execution_not_automation")

    return (len(reasons) == 0), reasons


def observe(
    *,
    dsn: str | None,
    campaign: str,
    automatic: bool | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    root = project_root or _ROOT
    art = root / "artifacts" / "campaigns" / campaign
    art.mkdir(parents=True, exist_ok=True)
    day_utc = datetime.now(UTC).date().isoformat()
    observation_id = f"obs-{day_utc}-{uuid.uuid4().hex[:10]}"

    auto = (
        automatic
        if automatic is not None
        else _detect_automatic_execution()
    )

    obs: dict[str, Any] = {
        "day_utc": day_utc,
        "day": day_utc,
        "observation_id": observation_id,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "host": None,
        "deployed_sha": None,
        "schema_version": None,
        "policy_version": None,
        "universe_version": None,
        "timer_enabled": None,
        "timer_active": None,
        "last_trigger": None,
        "next_trigger": None,
        "service_result": None,
        "exec_main_status": None,
        "invocation_id": os.environ.get("INVOCATION_ID"),
        "run_id": None,
        "automatic_execution": bool(auto),
        "contracts_freshness_hours": None,
        "open_tenders_freshness_hours": None,
        "contracts_coverage": None,
        "open_tenders_coverage": None,
        "failed_critical_units": None,
        "failed_units": None,
        "source_health": None,
        "checksum_status": None,
        "health_ok": False,
        "health_fail_reasons": [],
        "notes": [],
        "dsn_configured": bool(dsn),
        "measure_mode": "local_vps" if _is_vps_host() else "ssh_ec_prod",
        "freshness_basis": "ingestion_runs.completed_at|artifact_mtime|coverage_evidence — NOT data_publicacao",
    }

    dual_local = _load_dual_coverage(root)
    if dual_local:
        if dual_local.get("open_tenders_coverage") is not None:
            obs["open_tenders_coverage"] = dual_local["open_tenders_coverage"]
        if dual_local.get("historical_contracts_coverage") is not None:
            obs["contracts_coverage"] = dual_local["historical_contracts_coverage"]
        obs["dual_gate_status"] = dual_local.get("dual_gate_status")
        obs["notes"].append(f"dual_summary={dual_local.get('dual_summary_path')}")

    rc, out = _measure_runtime()
    if rc != 0 and not out.strip():
        obs["notes"].append(f"measure_failed_rc={rc}")
        obs["health_ok"] = False
        obs["health_fail_reasons"] = ["measure_failed"]
    else:
        kv = _parse_kv(out)
        if rc != 0:
            obs["notes"].append(f"measure_rc={rc}")
        try:
            obs["failed_units"] = int(kv.get("failed_units") or "0")
        except ValueError:
            obs["failed_units"] = None
        try:
            obs["failed_critical_units"] = int(kv.get("failed_critical") or "0")
        except ValueError:
            obs["failed_critical_units"] = None
        obs["host"] = kv.get("host")
        obs["deployed_sha"] = kv.get("deployed_sha") or None
        obs["timer_active"] = kv.get("contracts_timer")
        obs["contracts_timer"] = kv.get("contracts_timer")
        obs["timer_enabled"] = kv.get("contracts_timer_enabled")
        obs["contracts_timer_enabled"] = kv.get("contracts_timer_enabled")
        obs["health_timer"] = kv.get("health_timer")
        obs["last_trigger"] = kv.get("contracts_last_trigger")
        obs["next_trigger"] = kv.get("contracts_next_trigger")
        obs["service_result"] = kv.get("last_contracts_result")
        obs["last_contracts_result"] = kv.get("last_contracts_result")
        obs["exec_main_status"] = kv.get("last_contracts_exec")
        obs["last_contracts_exec"] = kv.get("last_contracts_exec")
        obs["editais_pncp_timer"] = kv.get("editais_pncp_timer")
        obs["editais_pncp_timer_enabled"] = kv.get("editais_pncp_timer_enabled")
        obs["editais_ciga_timer"] = kv.get("editais_ciga_timer")
        obs["editais_ciga_timer_enabled"] = kv.get("editais_ciga_timer_enabled")
        obs["last_editais_pncp_result"] = kv.get("last_editais_pncp_result")

        if kv.get("contracts_count"):
            try:
                obs["contracts_count"] = int(kv["contracts_count"])
            except ValueError:
                pass

        age = kv.get("contracts_ingest_age_hours") or kv.get("contracts_artifact_age_hours")
        if age not in (None, ""):
            try:
                obs["contracts_freshness_hours"] = float(age)
                obs["freshness_source"] = (
                    "ingestion_runs"
                    if kv.get("contracts_ingest_age_hours")
                    else "artifact_mtime"
                )
            except ValueError:
                obs["notes"].append(f"age_unparseable:{age}")

        ot_age = kv.get("editais_obs_age_hours") or kv.get("dual_summary_age_hours")
        if ot_age not in (None, ""):
            try:
                obs["open_tenders_freshness_hours"] = float(ot_age)
                if not kv.get("editais_obs_age_hours"):
                    obs["notes"].append("open_tenders_freshness_from_dual_summary_mtime")
            except ValueError:
                obs["notes"].append(f"editais_age_unparseable:{ot_age}")

        run_id = kv.get("contracts_run_id") or kv.get("contracts_artifact_run_id") or ""
        obs["run_id"] = run_id or None
        obs["incremental_exit"] = (
            0 if kv.get("last_contracts_result") == "success" else None
        )

        # Prefer dual summary from host if local missing
        if obs.get("open_tenders_coverage") is None:
            obs["open_tenders_coverage"] = _pct_to_fraction(
                kv.get("open_tenders_coverage_pct")
            )
        if obs.get("contracts_coverage") is None:
            obs["contracts_coverage"] = _pct_to_fraction(
                kv.get("historical_contracts_coverage_pct")
            )
        if kv.get("dual_gate_status"):
            obs["dual_gate_status"] = kv.get("dual_gate_status")
        if kv.get("dual_summary_path"):
            obs["notes"].append(f"dual_summary_host={kv.get('dual_summary_path')}")

    ok, reasons = _compute_health_ok(obs)
    obs["health_ok"] = ok
    obs["health_fail_reasons"] = reasons

    day_path = art / "soak" / f"{day_utc}.json"
    day_path.parent.mkdir(parents=True, exist_ok=True)
    observations_for_day: list[dict[str, Any]] = []
    if day_path.is_file():
        try:
            prev = json.loads(day_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict) and prev.get("observations"):
                observations_for_day = list(prev["observations"])
            elif isinstance(prev, dict) and prev.get("observation_id"):
                observations_for_day = [prev]
        except (OSError, json.JSONDecodeError):
            obs["notes"].append("prior_day_file_unreadable")
    observations_for_day.append(obs)
    day_doc = {
        "day_utc": day_utc,
        "observations": observations_for_day,
        "rollup": _day_rollup(observations_for_day),
    }
    day_path.write_text(json.dumps(day_doc, indent=2) + "\n", encoding="utf-8")

    host_dir = Path("/var/lib/extra-consultoria/backfill/soak")
    try:
        host_dir.mkdir(parents=True, exist_ok=True)
        (host_dir / f"{day_utc}.json").write_text(
            json.dumps(day_doc, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        if not _is_vps_host():
            payload = json.dumps(day_doc, indent=2)
            _ssh(
                "mkdir -p /var/lib/extra-consultoria/backfill/soak && "
                f"cat > /var/lib/extra-consultoria/backfill/soak/{day_utc}.json <<'EOF'\n"
                + payload
                + "\nEOF\n"
            )

    return _write_campaign_rollup(art, campaign)


def _day_rollup(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        return {"health_ok": False, "reason": "no_observations"}
    latest = observations[-1]
    any_ok = any(bool(o.get("health_ok")) for o in observations)
    return {
        "health_ok": any_ok,
        "observation_count": len(observations),
        "latest_observation_id": latest.get("observation_id"),
        "latest_run_id": latest.get("run_id"),
        "latest_contracts_freshness_hours": latest.get("contracts_freshness_hours"),
        "latest_open_tenders_freshness_hours": latest.get("open_tenders_freshness_hours"),
        "latest_contracts_coverage": latest.get("contracts_coverage"),
        "latest_open_tenders_coverage": latest.get("open_tenders_coverage"),
        "all_fail_reasons": sorted(
            {r for o in observations for r in (o.get("health_fail_reasons") or [])}
        ),
    }


def _ensure_soak_epoch(art: Path, *, deployed_sha: str | None) -> dict[str, Any]:
    epoch_path = art / "soak_epoch.json"
    if epoch_path.is_file():
        try:
            return json.loads(epoch_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    epoch = {
        "soak_epoch_started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "calendar": "UTC",
        "required_consecutive_days": 7,
        "initial_deployed_sha": deployed_sha,
        "campaign": DEFAULT_CAMPAIGN,
        "rules": {
            "no_retroactive_fill": True,
            "no_pre_fix_days": True,
            "coverage_min": COVERAGE_MIN,
            "contracts_sla_hours": CONTRACTS_SLA_HOURS,
            "open_tenders_sla_hours": OPEN_TENDERS_SLA_HOURS,
        },
    }
    epoch_path.write_text(json.dumps(epoch, indent=2) + "\n", encoding="utf-8")
    return epoch


def _write_campaign_rollup(art: Path, campaign: str) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    days_payload: list[dict[str, Any]] = []
    day_keys: set[str] = set()
    latest_sha = None
    for i in range(7):
        d = (today - timedelta(days=i)).isoformat()
        p = art / "soak" / f"{d}.json"
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        day_keys.add(d)
        if isinstance(doc, dict) and "rollup" in doc:
            obs_list = doc.get("observations") or []
            if obs_list:
                latest_sha = obs_list[-1].get("deployed_sha") or latest_sha
            days_payload.append(
                {
                    "day_utc": d,
                    "health_ok": bool((doc.get("rollup") or {}).get("health_ok")),
                    "rollup": doc.get("rollup"),
                    "observation_count": len(doc.get("observations") or []),
                }
            )
        elif isinstance(doc, dict):
            days_payload.append(
                {
                    "day_utc": d,
                    "health_ok": bool(doc.get("health_ok")),
                    "legacy": True,
                    "observation_count": 1,
                }
            )

    epoch = _ensure_soak_epoch(art, deployed_sha=latest_sha)
    expected_days = {(today - timedelta(days=i)).isoformat() for i in range(7)}
    present = day_keys

    def _rollup_fresh_ok(x: dict[str, Any]) -> bool:
        r = x.get("rollup") or {}
        cf = r.get("latest_contracts_freshness_hours")
        of = r.get("latest_open_tenders_freshness_hours")
        try:
            if cf is None or float(cf) > CONTRACTS_SLA_HOURS:
                return False
            if of is None or float(of) > OPEN_TENDERS_SLA_HOURS:
                return False
        except (TypeError, ValueError):
            return False
        return True

    def _rollup_cov_ok(x: dict[str, Any]) -> bool:
        r = x.get("rollup") or {}
        try:
            cc = r.get("latest_contracts_coverage")
            oc = r.get("latest_open_tenders_coverage")
            if cc is None or float(cc) < COVERAGE_MIN:
                return False
            if oc is None or float(oc) < COVERAGE_MIN:
                return False
        except (TypeError, ValueError):
            return False
        return True

    freshness_ok = all(_rollup_fresh_ok(x) for x in days_payload) if days_payload else False
    coverage_ok = all(_rollup_cov_ok(x) for x in days_payload) if days_payload else False
    health_all = all(x.get("health_ok") for x in days_payload) if days_payload else False
    complete = (
        expected_days.issubset(present)
        and len(days_payload) >= 7
        and health_all
        and freshness_ok
        and coverage_ok
    )
    first_eligible = (
        datetime.fromisoformat(
            epoch["soak_epoch_started_at"].replace("Z", "+00:00")
        ).date()
        + timedelta(days=6)
    ).isoformat()
    rollup = {
        "campaign": campaign,
        "required_consecutive_days": 7,
        "calendar": "UTC",
        "soak_epoch_started_at": epoch.get("soak_epoch_started_at"),
        "first_eligible_completion_date_utc": first_eligible,
        "observations_last_7d": days_payload,
        "expected_days": sorted(expected_days),
        "present_days": sorted(present),
        "complete": complete,
        "complete_reason": (
            "ok"
            if complete
            else "missing_days_or_health_or_freshness_or_coverage"
        ),
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "rules": {
            "no_retroactive_fill": True,
            "no_document_date_freshness": True,
            "no_manual_as_automation": True,
            "health_requires_contracts_and_editais_coverage_ge_95": True,
            "health_requires_contracts_success_and_run_id": True,
            "coverage_min": COVERAGE_MIN,
            "contracts_sla_hours": CONTRACTS_SLA_HOURS,
            "open_tenders_sla_hours": OPEN_TENDERS_SLA_HOURS,
        },
    }
    (art / "soak.json").write_text(json.dumps(rollup, indent=2) + "\n", encoding="utf-8")
    return rollup


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    p.add_argument("--dsn", default=os.environ.get("LOCAL_DATALAKE_DSN"))
    p.add_argument(
        "--manual",
        action="store_true",
        help="Force automatic_execution=false (CLI/manual path)",
    )
    p.add_argument(
        "--automatic",
        action="store_true",
        help="Assert this observation is automated (systemd/SOAK_AUTOMATIC)",
    )
    args = p.parse_args(argv)
    if args.manual and args.automatic:
        print(
            json.dumps({"error": "cannot pass both --manual and --automatic"}),
        )
        return 2
    automatic: bool | None
    if args.manual:
        automatic = False
    elif args.automatic:
        automatic = True
    else:
        automatic = None  # detect
    rollup = observe(dsn=args.dsn, campaign=args.campaign, automatic=automatic)
    print(json.dumps(rollup, indent=2))
    return 0 if rollup.get("complete") else 2


if __name__ == "__main__":
    raise SystemExit(main())
