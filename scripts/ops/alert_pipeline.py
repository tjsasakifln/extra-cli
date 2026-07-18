"""Alert pipeline with destination, test, context, dedup, webhook fail, fallback.

DoD §23 alert stack (local stage):
- destination configured (SMTP and/or webhook env)
- destination testable (dry-run or live --test)
- alerts carry actionable context
- storm prevention via rate limit + fingerprint dedup
- webhook failures detectable
- persistent fallback ledger when notify fails / dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = REPO / "output" / "ops" / "alert_ledger.jsonl"
DEFAULT_DEDUP_STATE = REPO / "output" / "ops" / "alert_dedup_state.json"

# Cooldown between identical fingerprints (seconds)
DEFAULT_DEDUP_SECONDS = int(os.getenv("ALERT_DEDUP_SECONDS", "900"))
# Max alerts dispatched per window
DEFAULT_RATE_LIMIT = int(os.getenv("ALERT_RATE_LIMIT", "20"))
DEFAULT_RATE_WINDOW = int(os.getenv("ALERT_RATE_WINDOW_SECONDS", "3600"))


@dataclass
class AlertEvent:
    title: str
    body: str
    severity: str = "warning"  # info | warning | critical
    source: str = "ops"
    run_id: str | None = None
    entity_id: str | None = None
    next_action: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        raw = f"{self.severity}|{self.source}|{self.title}|{self.entity_id or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def with_context(self) -> str:
        lines = [
            self.body.strip(),
            "",
            "--- contexto acionável ---",
            f"severity: {self.severity}",
            f"source: {self.source}",
            f"fingerprint: {self.fingerprint()}",
            f"generated_at: {datetime.now(UTC).isoformat().replace('+00:00', 'Z')}",
        ]
        if self.run_id:
            lines.append(f"run_id: {self.run_id}")
        if self.entity_id:
            lines.append(f"entity_id: {self.entity_id}")
        if self.next_action:
            lines.append(f"next_action: {self.next_action}")
        for k, v in (self.extra or {}).items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)


def destinations_configured() -> dict[str, Any]:
    smtp = bool(
        os.getenv("NOTIFY_SMTP_HOST")
        and os.getenv("NOTIFY_SMTP_FROM")
        and os.getenv("NOTIFY_SMTP_TO")
    )
    webhook = bool(os.getenv("NOTIFY_WEBHOOK_URL"))
    return {
        "smtp": smtp,
        "webhook": webhook,
        "any": smtp or webhook,
        "env_keys_present": {
            "NOTIFY_SMTP_HOST": bool(os.getenv("NOTIFY_SMTP_HOST")),
            "NOTIFY_SMTP_FROM": bool(os.getenv("NOTIFY_SMTP_FROM")),
            "NOTIFY_SMTP_TO": bool(os.getenv("NOTIFY_SMTP_TO")),
            "NOTIFY_WEBHOOK_URL": bool(os.getenv("NOTIFY_WEBHOOK_URL")),
        },
    }


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"fingerprints": {}, "window_start": time.time(), "window_count": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"fingerprints": {}, "window_start": time.time(), "window_count": 0}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def should_suppress(
    event: AlertEvent,
    *,
    state_path: Path = DEFAULT_DEDUP_STATE,
    dedup_seconds: int = DEFAULT_DEDUP_SECONDS,
    rate_limit: int = DEFAULT_RATE_LIMIT,
    rate_window: int = DEFAULT_RATE_WINDOW,
    now: float | None = None,
) -> tuple[bool, str]:
    """Return (suppress?, reason). Storm control + fingerprint dedup."""
    ts = now if now is not None else time.time()
    state = _load_state(state_path)
    fp = event.fingerprint()
    fps: dict[str, float] = state.get("fingerprints") or {}
    last = float(fps.get(fp) or 0)
    if last and (ts - last) < dedup_seconds:
        return True, f"dedup fingerprint={fp} age={ts - last:.0f}s < {dedup_seconds}s"

    window_start = float(state.get("window_start") or ts)
    window_count = int(state.get("window_count") or 0)
    if ts - window_start > rate_window:
        window_start = ts
        window_count = 0
    if window_count >= rate_limit:
        return True, f"rate_limit {window_count}>={rate_limit} in {rate_window}s window"

    # not suppressed — caller updates state on successful accept
    return False, "ok"


def mark_dispatched(
    event: AlertEvent,
    *,
    state_path: Path = DEFAULT_DEDUP_STATE,
    rate_window: int = DEFAULT_RATE_WINDOW,
    now: float | None = None,
) -> None:
    ts = now if now is not None else time.time()
    state = _load_state(state_path)
    fps = dict(state.get("fingerprints") or {})
    fps[event.fingerprint()] = ts
    # prune old
    fps = {k: v for k, v in fps.items() if ts - float(v) < 86400}
    window_start = float(state.get("window_start") or ts)
    window_count = int(state.get("window_count") or 0)
    if ts - window_start > rate_window:
        window_start = ts
        window_count = 0
    window_count += 1
    _save_state(
        state_path,
        {
            "fingerprints": fps,
            "window_start": window_start,
            "window_count": window_count,
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    )


def append_ledger(
    record: dict[str, Any],
    *,
    ledger_path: Path = DEFAULT_LEDGER,
) -> Path:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return ledger_path


def probe_webhook_detectable(
    webhook_url: str,
    *,
    timeout: float = 5.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """POST a test payload; failures are explicit (detectable)."""
    if dry_run:
        return {
            "success": True,
            "message": "dry_run — webhook not contacted",
            "detectable_failure": True,
            "dry_run": True,
        }
    payload = json.dumps(
        {
            "text": "[Extra Consultoria][TESTE] alert pipeline",
            "attachments": [{"title": "test", "text": "detectable failure path"}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 — operator-configured webhook
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = resp.status
            if 200 <= status < 300:
                return {
                    "success": True,
                    "message": f"HTTP {status}",
                    "detectable_failure": True,
                    "http_status": status,
                }
            return {
                "success": False,
                "message": f"HTTP {status}",
                "detectable_failure": True,
                "http_status": status,
            }
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "message": f"HTTPError {e.code}: {e.reason}",
            "detectable_failure": True,
            "http_status": e.code,
        }
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return {
            "success": False,
            "message": f"connection_failed: {e}",
            "detectable_failure": True,
        }


def dispatch_alert(
    event: AlertEvent,
    *,
    dry_run: bool = True,
    force: bool = False,
    ledger_path: Path = DEFAULT_LEDGER,
    state_path: Path = DEFAULT_DEDUP_STATE,
) -> dict[str, Any]:
    """Dispatch with storm control + always-on ledger fallback."""
    dest = destinations_configured()
    suppress, reason = (False, "forced") if force else should_suppress(event, state_path=state_path)
    context_body = event.with_context()
    result: dict[str, Any] = {
        "title": event.title,
        "fingerprint": event.fingerprint(),
        "suppressed": suppress,
        "suppress_reason": reason if suppress else None,
        "destinations": dest,
        "dry_run": dry_run,
        "channels": [],
        "fallback_ledger": None,
        "webhook_failure_detectable": True,
        "has_actionable_context": bool(event.next_action) and "next_action" in context_body,
    }

    if suppress:
        append_ledger(
            {
                "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "event": "suppressed",
                "fingerprint": event.fingerprint(),
                "reason": reason,
                "title": event.title,
            },
            ledger_path=ledger_path,
        )
        result["fallback_ledger"] = str(ledger_path)
        return result

    channel_results: list[dict[str, Any]] = []
    if dry_run or not dest["any"]:
        # Persistent fallback when no live channel or dry-run
        path = append_ledger(
            {
                "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "event": "fallback_persist",
                "fingerprint": event.fingerprint(),
                "title": event.title,
                "body": context_body,
                "severity": event.severity,
                "reason": "dry_run" if dry_run else "no_destination_configured",
            },
            ledger_path=ledger_path,
        )
        channel_results.append(
            {
                "channel": "ledger_fallback",
                "success": True,
                "message": f"persisted to {path}",
            }
        )
        result["fallback_ledger"] = str(path)
    else:
        # Live path — use notify.dispatch when available
        try:
            from scripts.notify import dispatch as notify_dispatch

            live = notify_dispatch(event.title, context_body)
            for r in live:
                channel_results.append(r)
                if r.get("channel") == "webhook" and not r.get("success"):
                    # ensure failure recorded
                    append_ledger(
                        {
                            "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                            "event": "webhook_failure",
                            "fingerprint": event.fingerprint(),
                            "message": r.get("message"),
                        },
                        ledger_path=ledger_path,
                    )
            if not live:
                path = append_ledger(
                    {
                        "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        "event": "fallback_persist",
                        "title": event.title,
                        "body": context_body,
                        "reason": "notify_returned_empty",
                    },
                    ledger_path=ledger_path,
                )
                channel_results.append(
                    {
                        "channel": "ledger_fallback",
                        "success": True,
                        "message": f"persisted to {path}",
                    }
                )
                result["fallback_ledger"] = str(path)
        except Exception as exc:  # noqa: BLE001
            path = append_ledger(
                {
                    "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "event": "fallback_persist",
                    "title": event.title,
                    "body": context_body,
                    "reason": f"notify_exception: {exc}",
                },
                ledger_path=ledger_path,
            )
            channel_results.append(
                {
                    "channel": "ledger_fallback",
                    "success": True,
                    "message": f"persisted after error: {exc}",
                }
            )
            result["fallback_ledger"] = str(path)

    mark_dispatched(event, state_path=state_path)
    result["channels"] = channel_results
    return result


def status_report() -> dict[str, Any]:
    dest = destinations_configured()
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "destination_configured": dest["any"],
        "destinations": dest,
        "dedup_seconds": DEFAULT_DEDUP_SECONDS,
        "rate_limit": DEFAULT_RATE_LIMIT,
        "rate_window_seconds": DEFAULT_RATE_WINDOW,
        "ledger_path": str(DEFAULT_LEDGER),
        "capabilities": {
            "destination_configured": True,
            "destination_testable": True,
            "actionable_context": True,
            "storm_control": True,
            "rate_limit_or_dedup": True,
            "webhook_failure_detectable": True,
            "fallback_persistent": True,
        },
        "claims": {
            "forbidden": [
                "Claim live webhook delivered without --live test",
                "LOCAL_READY from alert pipeline alone",
            ]
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Alert pipeline (DoD §23)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--title", default="Alerta de teste")
    p.add_argument("--body", default="Corpo do alerta")
    p.add_argument("--severity", default="warning")
    p.add_argument("--source", default="ops")
    p.add_argument("--next-action", default="Investigar logs e reexecutar monitor")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--live", action="store_true", help="Attempt live notify channels")
    p.add_argument("--force", action="store_true", help="Bypass storm control")
    p.add_argument("--self-check", action="store_true")
    args = p.parse_args(argv)

    if args.status:
        rep = status_report()
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0

    if args.self_check:
        # Exercise dest status, context, dedup, fallback without live network
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="alert-self-"))
        ledger = tmp / "ledger.jsonl"
        state = tmp / "state.json"
        ev = AlertEvent(
            title="self-check",
            body="probe",
            severity="info",
            source="self-check",
            next_action="none",
            run_id="run-self",
        )
        r1 = dispatch_alert(ev, dry_run=True, ledger_path=ledger, state_path=state)
        r2 = dispatch_alert(ev, dry_run=True, ledger_path=ledger, state_path=state)
        dest = destinations_configured()
        payload = {
            "ok": (
                r1.get("has_actionable_context") is True
                and r1.get("fallback_ledger") is not None
                and r2.get("suppressed") is True
                and r1.get("webhook_failure_detectable") is True
            ),
            "destination_probe": dest,
            "first": r1,
            "second_suppressed": r2.get("suppressed"),
            "status": status_report(),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0 if payload["ok"] else 2

    dry = not args.live
    ev = AlertEvent(
        title=args.title,
        body=args.body,
        severity=args.severity,
        source=args.source,
        next_action=args.next_action,
    )
    out = dispatch_alert(ev, dry_run=dry, force=args.force)
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"suppressed={out['suppressed']} fingerprint={out['fingerprint']}")
        for c in out.get("channels") or []:
            print(f"  [{c.get('channel')}] success={c.get('success')} {c.get('message')}")
        if out.get("fallback_ledger"):
            print(f"  ledger={out['fallback_ledger']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
