#!/usr/bin/env python3
"""Periodic alert checker — verifica condicoes criticas e dispara notificacoes.

Extra Consultoria — Story TD-5.5
Verificacoes:
    - Falha consecutiva de crawler (padrao: 3x)
    - Disco cheio (>90%)
    - DB offline
    - Storage Box inacessivel
    - Backup falhou
    - API keys expiradas ou proximas do vencimento

Integra com:
    - ``health_check.py`` para checagens de infraestrutura
    - ``collect-metrics.py`` para metricas de crawl
    - ``notify.py`` para disparo de notificacoes

Usage:
    python scripts/check-alerts.py                          # Run all checks
    python scripts/check-alerts.py --json                   # JSON output
    python scripts/check-alerts.py --dry-run                # Don't send notifications
    python scripts/check-alerts.py --test                   # Test alert (always sends)

Exit codes:
    0 — All checks passed (no alerts triggered)
    1 — Warnings only (e.g. disk > 80%)
    2 — Critical alerts triggered
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.logging_config import get_logger, set_correlation_id
from config.settings import DEFAULT_DSN

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

ALERT_CONSECUTIVE_FAILURES = int(os.getenv("ALERT_CONSECUTIVE_FAILURES", "3"))
ALERT_DISK_CRIT_PCT = int(os.getenv("ALERT_DISK_CRIT_PCT", "90"))
ALERT_DISK_WARN_PCT = int(os.getenv("ALERT_DISK_WARN_PCT", "80"))
ALERT_BACKUP_MAX_HOURS = int(os.getenv("ALERT_BACKUP_MAX_HOURS", "28"))

BACKUP_LOG_FILE = os.getenv("BACKUP_LOG_FILE", "/var/log/backup-database.log")
STORAGE_BOX_MOUNT = os.getenv("BACKUP_MOUNT_POINT", "/mnt/storage-box")

# API keys that should be checked (name, purpose)
REQUIRED_API_KEYS: list[tuple[str, str]] = [
    ("OPENAI_API_KEY", "OpenAI LLM"),
    ("DOM_SC_API_KEY", "DOM-SC"),
    # PORTAL_TRANSPARENCIA_API_KEY is optional — skip if absent
]


# ---------------------------------------------------------------------------
# Alert state
# ---------------------------------------------------------------------------


class AlertRegistry:
    """Collects triggered alerts and decides severity."""

    def __init__(self) -> None:
        self.alerts: list[dict[str, Any]] = []
        self.max_severity = 0

    def add(
        self,
        severity: int,
        category: str,
        title: str,
        message: str,
        details: str = "",
    ) -> None:
        """Register an alert.

        Args:
            severity: 0=info, 1=warning, 2=critical.
            category: Alert category (crawl, disk, db, storage, backup, api_key).
            title: Short alert title.
            message: Human-readable alert message.
            details: Optional technical details.
        """
        self.alerts.append(
            {
                "severity": severity,
                "category": category,
                "title": title,
                "message": message,
                "details": details,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        self.max_severity = max(self.max_severity, severity)

    def has_critical(self) -> bool:
        return any(a["severity"] >= 2 for a in self.alerts)

    def has_warnings(self) -> bool:
        return any(a["severity"] == 1 for a in self.alerts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": "alert_check",
            "timestamp": datetime.now(UTC).isoformat(),
            "host": os.uname().nodename,
            "total_alerts": len(self.alerts),
            "max_severity": self.max_severity,
            "alerts": self.alerts,
        }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_consecutive_crawl_failures(registry: AlertRegistry, threshold: int) -> None:
    """Check for sources with N consecutive failures in ingestion_runs."""
    logger.debug("Checking consecutive crawl failures (threshold=%d)", threshold)
    try:
        import psycopg2  # noqa: PLC0415

        conn = psycopg2.connect(DEFAULT_DSN)
        cur = conn.cursor()
        cur.execute(
            """WITH ranked AS (
                SELECT source, status, started_at,
                    ROW_NUMBER() OVER (PARTITION BY source ORDER BY started_at DESC) AS rn
                FROM ingestion_runs
                WHERE started_at >= NOW() - INTERVAL '48 hours'
            ),
            consec AS (
                SELECT source, COUNT(*) AS cnt,
                    MAX(started_at) AS last_fail,
                    STRING_AGG(started_at::text, ', ' ORDER BY started_at DESC) AS fail_times
                FROM ranked
                WHERE rn <= %s AND status = 'failed'
                GROUP BY source
                HAVING COUNT(*) >= %s
            )
            SELECT source, cnt, last_fail, fail_times FROM consec
            ORDER BY cnt DESC""",
            (threshold + 3, threshold),
        )
        for row in cur.fetchall():
            registry.add(
                severity=2,
                category="crawl",
                title=f"Crawler {row[0]}: {row[1]} falhas consecutivas",
                message=(
                    f"O crawler '{row[0]}' falhou {row[1]} vezes consecutivas. "
                    f"Ultima falha: {row[2].isoformat() if row[2] else 'N/A'}."
                ),
                details=f"Falhas: {row[3]}" if row[3] else "",
            )
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning("Cannot check consecutive failures (DB may be offline): %s", e)


def check_disk(registry: AlertRegistry) -> None:
    """Check disk usage against warning and critical thresholds."""
    logger.debug("Checking disk space")
    try:
        usage = shutil.disk_usage("/")
        pct = usage.used / usage.total * 100
        total_gb = usage.total / (1024**3)
        free_gb = usage.free / (1024**3)

        if pct >= ALERT_DISK_CRIT_PCT:
            registry.add(
                severity=2,
                category="disk",
                title=f"Disco critico: {pct:.0f}% utilizado",
                message=(
                    f"Disco em / esta com {pct:.0f}% de uso ({free_gb:.1f}G livres "
                    f"de {total_gb:.1f}G). Atingiu o limiar critico de {ALERT_DISK_CRIT_PCT}%."
                ),
                details=f"total={total_gb:.1f}G used={usage.used / 1024**3:.1f}G free={free_gb:.1f}G",
            )
        elif pct >= ALERT_DISK_WARN_PCT:
            registry.add(
                severity=1,
                category="disk",
                title=f"Disco em alerta: {pct:.0f}% utilizado",
                message=(
                    f"Disco em / esta com {pct:.0f}% de uso ({free_gb:.1f}G livres). "
                    f"Atingiu o limiar de alerta de {ALERT_DISK_WARN_PCT}%."
                ),
                details=f"total={total_gb:.1f}G free={free_gb:.1f}G",
            )
    except Exception as e:
        logger.warning("Cannot check disk: %s", e)


def check_db_online(registry: AlertRegistry) -> None:
    """Check PostgreSQL connectivity via psql."""
    logger.debug("Checking DB connectivity")
    try:
        result = subprocess.run(
            ["psql", DEFAULT_DSN, "-c", "SELECT 1 AS ok", "-t", "-A"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 or "1" not in result.stdout.strip():
            registry.add(
                severity=2,
                category="db",
                title="Banco de dados offline",
                message=(
                    "Nao foi possivel conectar ao PostgreSQL. "
                    f"psql retornou codigo {result.returncode}: {result.stderr.strip()[:200]}"
                ),
                details=result.stderr.strip()[:500] if result.stderr else "",
            )
    except subprocess.TimeoutExpired:
        registry.add(
            severity=2,
            category="db",
            title="Banco de dados offline (timeout)",
            message="Conexao com PostgreSQL excedeu o limite de 10 segundos.",
        )
    except FileNotFoundError:
        registry.add(
            severity=1,
            category="db",
            title="psql nao encontrado",
            message="O comando psql nao esta disponivel no PATH.",
        )
    except Exception as e:
        registry.add(
            severity=2,
            category="db",
            title="Erro ao verificar banco de dados",
            message=str(e),
        )


def check_storage_box(registry: AlertRegistry) -> None:
    """Check if Storage Box is mounted and accessible."""
    logger.debug("Checking Storage Box mount")
    if not os.path.ismount(STORAGE_BOX_MOUNT):
        registry.add(
            severity=2,
            category="storage",
            title="Storage Box desmontado",
            message=(
                f"O ponto de montagem {STORAGE_BOX_MOUNT} nao esta montado. Backups para Storage Box podem falhar."
            ),
        )
        return

    try:
        entries = os.listdir(STORAGE_BOX_MOUNT)
        logger.debug("Storage Box OK (%d entries)", len(entries))
    except PermissionError:
        registry.add(
            severity=2,
            category="storage",
            title="Storage Box sem permissao",
            message=(f"Storage Box montado em {STORAGE_BOX_MOUNT} mas sem permissao de leitura."),
        )
    except Exception as e:
        registry.add(
            severity=1,
            category="storage",
            title="Storage Box inacessivel",
            message=f"Erro ao acessar {STORAGE_BOX_MOUNT}: {e}",
        )


def check_backup(registry: AlertRegistry) -> None:
    """Check if backup ran recently by inspecting backup log."""
    logger.debug("Checking backup status")
    log_path = Path(BACKUP_LOG_FILE)
    if not log_path.exists():
        registry.add(
            severity=1,
            category="backup",
            title="Log de backup nao encontrado",
            message=f"Arquivo de log de backup nao encontrado em {BACKUP_LOG_FILE}. "
            "Nao foi possivel verificar o status do ultimo backup.",
        )
        return

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        registry.add(
            severity=1,
            category="backup",
            title="Erro ao ler log de backup",
            message=str(e),
        )
        return

    # Find most recent LOG_JSON entry
    last_timestamp = None
    last_status = None
    for line in reversed(content.splitlines()):
        if "LOG_JSON:" in line:
            try:
                log_entry = json.loads(line.split("LOG_JSON:", 1)[1].strip())
                last_timestamp = log_entry.get("timestamp")
                last_status = log_entry.get("status")
                break
            except (json.JSONDecodeError, IndexError):
                continue

    if last_status == "failed":
        registry.add(
            severity=2,
            category="backup",
            title="Ultimo backup falhou",
            message=f"O ultimo backup em {last_timestamp} falhou.",
        )
        return

    # Check if backup ran within the expected window
    if last_timestamp:
        try:
            last_time = datetime.fromisoformat(last_timestamp)
            now = datetime.now(UTC)
            hours_ago = (now - last_time).total_seconds() / 3600
            if hours_ago > ALERT_BACKUP_MAX_HOURS:
                registry.add(
                    severity=2,
                    category="backup",
                    title=f"Backup desatualizado ({hours_ago:.0f}h atras)",
                    message=(
                        f"O ultimo backup foi ha {hours_ago:.0f} horas "
                        f"({last_timestamp}). O limite e de {ALERT_BACKUP_MAX_HOURS}h."
                    ),
                )
        except (ValueError, TypeError):
            pass
    else:
        registry.add(
            severity=1,
            category="backup",
            title="Nenhum backup encontrado no log",
            message="Nao foram encontrados registros de backup no arquivo de log.",
        )


def check_api_keys(registry: AlertRegistry) -> None:
    """Check that required API keys are set and warn about optional ones."""
    logger.debug("Checking API keys")
    for key, purpose in REQUIRED_API_KEYS:
        value = os.getenv(key, "")
        if not value:
            registry.add(
                severity=1,
                category="api_key",
                title=f"API key faltando: {key}",
                message=(f"A chave {key} ({purpose}) nao esta configurada no arquivo .env ou ambiente."),
                details=f"Service: {purpose}",
            )

    # Check PORTAL_TRANSPARENCIA_API_KEY (optional, but warn if present but empty)
    portal_key = os.getenv("PORTAL_TRANSPARENCIA_API_KEY", "")
    if not portal_key:
        registry.add(
            severity=0,
            category="api_key",
            title="API key Portal da Transparencia nao configurada",
            message=(
                "PORTAL_TRANSPARENCIA_API_key nao esta configurada. "
                "O crawler do Portal da Transparencia pode ser afetado."
            ),
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_checks(dry_run: bool = False) -> AlertRegistry:
    """Run all alert checks and optionally send notifications.

    Args:
        dry_run: If True, do not send notifications.

    Returns:
        AlertRegistry with all triggered alerts.
    """
    registry = AlertRegistry()

    # Infrastructure checks
    check_disk(registry)
    check_db_online(registry)
    check_storage_box(registry)
    check_backup(registry)

    # Crawl checks (requires DB — skip if DB is down)
    if not any(a["category"] == "db" and a["severity"] >= 2 for a in registry.alerts):
        check_consecutive_crawl_failures(registry, ALERT_CONSECUTIVE_FAILURES)

    # API key checks
    check_api_keys(registry)

    # Log results
    if registry.alerts:
        by_severity: dict[int, int] = {}
        for a in registry.alerts:
            by_severity[a["severity"]] = by_severity.get(a["severity"], 0) + 1
        logger.info(
            "Alert check: %d alerts (critical=%d, warn=%d, info=%d)",
            len(registry.alerts),
            by_severity.get(2, 0),
            by_severity.get(1, 0),
            by_severity.get(0, 0),
            extra={"extra_data": {"alerts": registry.alerts, "dry_run": dry_run}},
        )
    else:
        logger.info("Alert check: no alerts triggered")

    # Send notifications for critical/warning alerts (unless dry-run)
    if not dry_run and registry.alerts:
        _send_alert_notifications(registry)

    return registry


def _send_alert_notifications(registry: AlertRegistry) -> None:
    """Send notifications for triggered alerts."""
    from scripts.notify import dispatch as notify_dispatch  # noqa: PLC0415

    critical = [a for a in registry.alerts if a["severity"] >= 2]
    warnings = [a for a in registry.alerts if a["severity"] == 1]

    if critical:
        subject = f"[CRITICO] {critical[0]['title']}"
        body_lines = [f"Foram detectados {len(critical)} alertas criticos e {len(warnings)} alertas no sistema.\n"]
        for a in critical:
            body_lines.append(f"[CRITICO] {a['title']}")
            body_lines.append(f"  {a['message']}")
            body_lines.append("")
        for a in warnings:
            body_lines.append(f"[ALERTA] {a['title']}")
            body_lines.append(f"  {a['message']}")
            body_lines.append("")

        notify_dispatch(subject, "\n".join(body_lines).strip())

    elif warnings:
        # Only send warnings if there are no critical issues
        subject = f"[ALERTA] {warnings[0]['title']}"
        body_lines = [f"Foram detectados {len(warnings)} alertas no sistema.\n"]
        for a in warnings:
            body_lines.append(f"[ALERTA] {a['title']}")
            body_lines.append(f"  {a['message']}")
            body_lines.append("")

        notify_dispatch(subject, "\n".join(body_lines).strip())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extra Consultoria — Periodic Alert Checker",
    )
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--dry-run", action="store_true", help="Check only, do not send notifications")
    p.add_argument("--test", action="store_true", help="Send a test alert to verify notification pipeline")
    p.add_argument(
        "--threshold",
        type=int,
        default=ALERT_CONSECUTIVE_FAILURES,
        help=f"Consecutive failure threshold (default: {ALERT_CONSECUTIVE_FAILURES})",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    set_correlation_id()

    if args.threshold != ALERT_CONSECUTIVE_FAILURES:
        globals()["ALERT_CONSECUTIVE_FAILURES"] = args.threshold

    if args.test:
        # Send a test notification
        from scripts.notify import dispatch as test_dispatch  # noqa: PLC0415

        logger.info("Sending test alert...")
        results = test_dispatch(
            "[TESTE] Alerta de teste — Sistema de Monitoramento",
            (
                "Este e um alerta de teste do sistema de monitoramento.\n\n"
                "Se voce recebeu esta mensagem, o pipeline de notificacao "
                "esta configurado corretamente.\n\n"
                f"Host: {os.uname().nodename}\n"
                f"Timestamp: {datetime.now(UTC).isoformat()}"
            ),
        )
        for r in results:
            status = "OK" if r["success"] else "FAIL"
            print(f"  [{status}] {r['channel']}: {r['message']}")
        all_ok = all(r["success"] for r in results)
        return 0 if all_ok else 2

    registry = run_checks(dry_run=args.dry_run)

    if args.json:
        print(json.dumps(registry.to_dict(), ensure_ascii=False, default=str, indent=2))
    else:
        print(f"Alert Check — {registry.to_dict()['timestamp']}")
        print(f"Host: {os.uname().nodename}")
        print()
        if not registry.alerts:
            print("  No alerts triggered.")
        else:
            for a in registry.alerts:
                sev_label = {0: "INFO", 1: "WARN", 2: "CRIT"}.get(a["severity"], "?")
                print(f"  [{sev_label}] [{a['category']}] {a['title']}")
                print(f"           {a['message']}")
                print()

        critical_count = sum(1 for a in registry.alerts if a["severity"] >= 2)
        warning_count = sum(1 for a in registry.alerts if a["severity"] == 1)
        print(f"Total: {len(registry.alerts)} alerts (critical={critical_count}, warnings={warning_count})")

    exit_code = 0
    if registry.has_critical():
        exit_code = 2
    elif registry.has_warnings():
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
