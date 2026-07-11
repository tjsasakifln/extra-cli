#!/usr/bin/env python3
"""Notification dispatcher — SMTP email and webhook (Slack/Discord).

Extra Consultoria — Story TD-5.5
Envia notificacoes para canais configurados em variaveis de ambiente.

Usage:
    python scripts/notify.py --subject "Alerta" --body "Falha no crawler X"

    python scripts/notify.py --subject "Teste" --body "Notificacao de teste" --test

    python scripts/notify.py --webhook-url "https://hooks.slack.com/..." \\
        --subject "Alerta" --body "Storage Box offline"

Exit codes:
    0 — Notification sent successfully
    1 — Configuration error (missing SMTP/webhook settings)
    2 — Send failure (network, auth, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.logging_config import get_logger, set_correlation_id

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

# SMTP
SMTP_HOST = os.getenv("NOTIFY_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("NOTIFY_SMTP_PORT", "587"))
SMTP_USER = os.getenv("NOTIFY_SMTP_USER", "")
SMTP_PASSWORD = os.getenv("NOTIFY_SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("NOTIFY_SMTP_FROM", "")
SMTP_TO = os.getenv("NOTIFY_SMTP_TO", "")
SMTP_USE_TLS = os.getenv("NOTIFY_SMTP_USE_TLS", "true").lower() == "true"

# Webhook
WEBHOOK_URL = os.getenv("NOTIFY_WEBHOOK_URL", "")

# Project info
PROJECT_NAME = "Extra Consultoria"
PROJECT_ENV = os.getenv("APP_ENV", "dev")


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------


def send_email(subject: str, body: str) -> dict[str, Any]:
    """Send notification via SMTP email.

    Returns:
        Dict with keys ``success`` (bool) and ``message`` (str).

    Raises:
        RuntimeError: If SMTP is not configured.
    """
    if not SMTP_HOST or not SMTP_FROM or not SMTP_TO:
        raise RuntimeError("SMTP not configured: set NOTIFY_SMTP_HOST, NOTIFY_SMTP_FROM, NOTIFY_SMTP_TO")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[{PROJECT_NAME}] {subject}"
    msg["From"] = SMTP_FROM
    msg["To"] = SMTP_TO

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            if SMTP_USE_TLS:
                server.starttls(context=context)
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [SMTP_TO], msg.as_string())

        logger.info(
            "Email sent to %s: %s",
            SMTP_TO,
            subject,
            extra={"extra_data": {"action": "notify_email", "to": SMTP_TO, "subject": subject}},
        )
        return {"success": True, "message": f"Email sent to {SMTP_TO}"}

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed for %s", SMTP_USER)
        return {"success": False, "message": "SMTP authentication failed"}
    except (smtplib.SMTPException, OSError) as e:
        logger.error("SMTP send failed: %s", e)
        return {"success": False, "message": str(e)}


def send_webhook(
    subject: str,
    body: str,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Send notification via webhook (Slack/Discord compatible).

    Args:
        subject: Alert title (used as Slack fallback text).
        body: Alert body text.
        webhook_url: Override URL (defaults to ``NOTIFY_WEBHOOK_URL``).

    Returns:
        Dict with keys ``success`` (bool) and ``message`` (str).

    Raises:
        RuntimeError: If webhook URL is not configured.
    """
    url = webhook_url or WEBHOOK_URL
    if not url:
        raise RuntimeError("Webhook not configured: set NOTIFY_WEBHOOK_URL")

    # Slack-compatible message format (also works with Discord)
    payload: dict[str, Any] = {
        "text": f"[{PROJECT_NAME}] {subject}",
        "attachments": [
            {
                "fallback": subject,
                "color": "danger",
                "title": subject,
                "text": body,
                "footer": f"{PROJECT_NAME} | {PROJECT_ENV}",
                "ts": int(__import__("time").time()),
            },
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body_resp = resp.read().decode("utf-8").strip()

        if 200 <= status < 300:
            logger.info(
                "Webhook sent: %s (status=%d)",
                subject,
                status,
                extra={
                    "extra_data": {
                        "action": "notify_webhook",
                        "subject": subject,
                        "status": status,
                    },
                },
            )
            return {"success": True, "message": f"Webhook sent (HTTP {status})"}
        else:
            logger.error("Webhook returned HTTP %d: %s", status, body_resp)
            return {"success": False, "message": f"HTTP {status}: {body_resp}"}

    except urllib.error.HTTPError as e:
        logger.error("Webhook HTTP error: %d %s", e.code, e.reason)
        return {"success": False, "message": f"HTTP {e.code}: {e.reason}"}
    except (urllib.error.URLError, OSError) as e:
        logger.error("Webhook connection failed: %s", e)
        return {"success": False, "message": str(e)}


def dispatch(
    subject: str,
    body: str,
    channels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Dispatch notification to all configured channels.

    Args:
        subject: Alert subject/title.
        body: Alert body text.
        channels: Which channels to use (``email``, ``webhook``).
                  Defaults to all configured channels.

    Returns:
        List of result dicts per channel.
    """
    if channels is None:
        channels = []
        if SMTP_HOST and SMTP_FROM and SMTP_TO:
            channels.append("email")
        if WEBHOOK_URL:
            channels.append("webhook")

    if not channels:
        logger.warning("No notification channels configured. Set NOTIFY_SMTP_* or NOTIFY_WEBHOOK_URL.")
        return []

    results: list[dict[str, Any]] = []
    for channel in channels:
        try:
            if channel == "email":
                result = send_email(subject, body)
            elif channel == "webhook":
                result = send_webhook(subject, body)
            else:
                result = {"success": False, "message": f"Unknown channel: {channel}"}
        except RuntimeError as e:
            result = {"success": False, "message": str(e)}
        except Exception as e:
            logger.exception("Notification via %s failed", channel)
            result = {"success": False, "message": str(e)}

        result["channel"] = channel
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extra Consultoria — Notification Dispatcher",
    )
    p.add_argument("--subject", default="Alerta do sistema", help="Notification subject")
    p.add_argument("--body", default="", help="Notification body text")
    p.add_argument(
        "--channel",
        choices=["email", "webhook", "all"],
        default="all",
        help="Notification channel (default: all configured)",
    )
    p.add_argument("--webhook-url", help="Override webhook URL for this call")
    p.add_argument("--test", action="store_true", help="Send a test notification to verify configuration")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    set_correlation_id()

    if args.test:
        logger.info("Sending test notification...")
        subject = "[TESTE] Notificacao de Teste — Extra Consultoria"
        _now_ts = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        body = (
            "Esta e uma notificacao de teste do sistema de monitoramento.\n\n"
            f"Host: {os.uname().nodename}\n"
            f"Ambiente: {PROJECT_ENV}\n"
            f"Timestamp: {_now_ts}\n"
            f"Channel: {args.channel}\n\n"
            "Se voce recebeu esta mensagem, o sistema de notificacao esta configurado corretamente."
        )
    else:
        subject = args.subject
        body = args.body or f"Alerta do sistema {PROJECT_NAME}"

    channels = None if args.channel == "all" else [args.channel]
    if args.webhook_url:
        os.environ["NOTIFY_WEBHOOK_URL"] = args.webhook_url

    results = dispatch(subject, body, channels)

    if not results:
        logger.warning("No notifications sent — check configuration")
        print("No notification channels configured.", file=sys.stderr)
        print("Set NOTIFY_SMTP_HOST / NOTIFY_SMTP_FROM / NOTIFY_SMTP_TO for email,")
        print("or NOTIFY_WEBHOOK_URL for Slack/Discord webhook.")
        return 1

    for r in results:
        status = "OK" if r["success"] else "FAIL"
        print(f"  [{status}] {r['channel']}: {r['message']}")

    all_ok = all(r["success"] for r in results)
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
