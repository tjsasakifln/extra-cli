"""Unit tests for monitoring/alerting system — Story TD-5.5.

Tests for:
    - notify.py: notification dispatch (email, webhook)
    - collect-metrics.py: metrics collection from DB and log files
    - check-alerts.py: periodic alert checks
    - health-dashboard.py: CLI dashboard
"""

from __future__ import annotations

import importlib.util
import json
import os
import smtplib
import sys
import urllib.error
from pathlib import Path
from types import ModuleType
from unittest.mock import ANY, MagicMock, Mock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Module loader for hyphenated filenames
# ---------------------------------------------------------------------------
# Scripts like collect-metrics.py, check-alerts.py, health-dashboard.py cannot
# be imported via ``from scripts.X import Y`` because Python identifiers
# cannot contain hyphens. We preload them via importlib and register them
# in sys.modules under their underscored aliases so that both ``from scripts.X``
# and ``patch("scripts.X.Y")`` work transparently.

_MODULE_CACHE: dict[str, ModuleType] = {}


def _load_hyphenated_module(name: str) -> ModuleType:
    """Load a script module with a hyphenated filename into sys.modules.

    Registers the module as ``scripts.{name}`` (hyphen replaced by underscore)
    so standard import / patch syntax works afterwards.
    """
    if name in _MODULE_CACHE:
        return _MODULE_CACHE[name]

    underscored = name.replace("-", "_")
    file_path = _PROJECT_ROOT / "scripts" / f"{name}.py"
    if not file_path.exists():
        raise ImportError(f"Script not found: {file_path}")

    spec = importlib.util.spec_from_file_location(
        f"scripts.{underscored}", str(file_path),
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for: {name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[f"scripts.{underscored}"] = module
    spec.loader.exec_module(module)
    _MODULE_CACHE[name] = module
    return module


# Preload hyphenated modules so they are available for import and patch()
_load_hyphenated_module("collect-metrics")
_load_hyphenated_module("check-alerts")
_load_hyphenated_module("health-dashboard")


# notify.py has no hyphen and can be imported normally
import scripts.notify as notify_mod  # noqa: E402


# ===========================================================================
# notify.py tests
# ===========================================================================


class TestNotifyEmail:
    """Tests for notify.send_email()."""

    def test_send_email_success(self):
        """SMTP server responds — email sent successfully."""
        with (
            patch("scripts.notify.smtplib.SMTP") as mock_smtp,
            patch("scripts.notify.SMTP_HOST", "smtp.test.com"),
            patch("scripts.notify.SMTP_PORT", 587),
            patch("scripts.notify.SMTP_USER", "user"),
            patch("scripts.notify.SMTP_PASSWORD", "pass"),
            patch("scripts.notify.SMTP_FROM", "from@test.com"),
            patch("scripts.notify.SMTP_TO", "to@test.com"),
            patch("scripts.notify.SMTP_USE_TLS", True),
        ):
            instance = mock_smtp.return_value.__enter__.return_value
            result = notify_mod.send_email("Subject", "Body text")

            assert result["success"] is True
            instance.starttls.assert_called_once()
            instance.login.assert_called_once_with("user", "pass")
            instance.sendmail.assert_called_once()

    def test_send_email_auth_failure(self):
        """SMTP authentication fails — error reported."""
        with (
            patch("scripts.notify.smtplib.SMTP") as mock_smtp,
            patch("scripts.notify.SMTP_HOST", "smtp.test.com"),
            patch("scripts.notify.SMTP_PORT", 587),
            patch("scripts.notify.SMTP_USER", "user"),
            patch("scripts.notify.SMTP_PASSWORD", "wrong"),
            patch("scripts.notify.SMTP_FROM", "from@test.com"),
            patch("scripts.notify.SMTP_TO", "to@test.com"),
            patch("scripts.notify.SMTP_USE_TLS", True),
        ):
            instance = mock_smtp.return_value.__enter__.return_value
            instance.login.side_effect = smtplib.SMTPAuthenticationError(
                535, b"Authentication failed"
            )
            result = notify_mod.send_email("Subject", "Body")

            assert result["success"] is False
            assert "authentication" in result["message"].lower()

    def test_send_email_no_config(self):
        """Missing SMTP config raises RuntimeError."""
        with (
            patch("scripts.notify.SMTP_HOST", ""),
            patch("scripts.notify.SMTP_FROM", ""),
            patch("scripts.notify.SMTP_TO", ""),
        ):
            with pytest.raises(RuntimeError, match="SMTP not configured"):
                notify_mod.send_email("Subject", "Body")

    def test_send_email_no_tls(self):
        """TLS disabled — should not call starttls."""
        with (
            patch("scripts.notify.smtplib.SMTP") as mock_smtp,
            patch("scripts.notify.SMTP_HOST", "smtp.test.com"),
            patch("scripts.notify.SMTP_PORT", 587),
            patch("scripts.notify.SMTP_USER", ""),
            patch("scripts.notify.SMTP_PASSWORD", ""),
            patch("scripts.notify.SMTP_FROM", "from@test.com"),
            patch("scripts.notify.SMTP_TO", "to@test.com"),
            patch("scripts.notify.SMTP_USE_TLS", False),
        ):
            instance = mock_smtp.return_value.__enter__.return_value
            result = notify_mod.send_email("Subject", "Body")

            assert result["success"] is True
            instance.starttls.assert_not_called()
            instance.login.assert_not_called()


class TestNotifyWebhook:
    """Tests for notify.send_webhook()."""

    def test_webhook_success(self):
        """Webhook responds 200."""
        with (
            patch("scripts.notify.urllib.request.urlopen") as mock_request,
            patch("scripts.notify.WEBHOOK_URL", "https://hooks.test.com/abc"),
        ):
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b"ok"
            mock_request.return_value.__enter__.return_value = mock_response

            result = notify_mod.send_webhook("Alert", "Something failed")

            assert result["success"] is True
            args, _ = mock_request.call_args
            assert args[0].method == "POST"
            body = json.loads(args[0].data)
            assert "Alert" in body["text"]

    def test_webhook_http_error(self):
        """Webhook returns 500."""
        with (
            patch("scripts.notify.urllib.request.urlopen") as mock_request,
            patch("scripts.notify.WEBHOOK_URL", "https://hooks.test.com/abc"),
        ):
            mock_request.side_effect = urllib.error.HTTPError(
                url="https://hooks.test.com/abc",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=None,
            )
            result = notify_mod.send_webhook("Alert", "Body")

            assert result["success"] is False
            assert "500" in result["message"]

    def test_webhook_no_config(self):
        """Missing webhook URL raises RuntimeError."""
        with patch("scripts.notify.WEBHOOK_URL", ""):
            with pytest.raises(RuntimeError, match="Webhook not configured"):
                notify_mod.send_webhook("Alert", "Body")

    def test_webhook_url_override(self):
        """Custom webhook URL passed as argument."""
        with patch("scripts.notify.urllib.request.urlopen") as mock_request:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b"ok"
            mock_request.return_value.__enter__.return_value = mock_response

            result = notify_mod.send_webhook(
                "Alert", "Body", webhook_url="https://custom.test.com/wh",
            )
            assert result["success"] is True
            assert "custom.test.com" in mock_request.call_args[0][0].full_url


class TestNotifyDispatch:
    """Tests for notify.dispatch()."""

    def test_dispatch_all_channels(self):
        """Dispatch sends to both email and webhook when both configured."""
        with (
            patch("scripts.notify.send_email",
                  return_value={"success": True, "message": "OK"}),
            patch("scripts.notify.send_webhook",
                  return_value={"success": True, "message": "OK"}),
            patch("scripts.notify.SMTP_HOST", "smtp.test.com"),
            patch("scripts.notify.SMTP_FROM", "from@test.com"),
            patch("scripts.notify.SMTP_TO", "to@test.com"),
            patch("scripts.notify.WEBHOOK_URL", "https://hooks.test.com"),
        ):
            results = notify_mod.dispatch("Alert", "Body")

            assert len(results) == 2
            assert all(r["success"] for r in results)

    def test_dispatch_no_channels(self):
        """No channels configured — returns empty list, logs warning."""
        with (
            patch("scripts.notify.SMTP_HOST", ""),
            patch("scripts.notify.SMTP_FROM", ""),
            patch("scripts.notify.SMTP_TO", ""),
            patch("scripts.notify.WEBHOOK_URL", ""),
        ):
            results = notify_mod.dispatch("Alert", "Body")
            assert results == []

    def test_dispatch_channel_failure_continues(self):
        """One channel fails, the other still executes."""
        with (
            patch("scripts.notify.send_email",
                  return_value={"success": False, "message": "Fail"}),
            patch("scripts.notify.send_webhook",
                  return_value={"success": True, "message": "OK"}),
            patch("scripts.notify.SMTP_HOST", "smtp.test.com"),
            patch("scripts.notify.SMTP_FROM", "from@test.com"),
            patch("scripts.notify.SMTP_TO", "to@test.com"),
            patch("scripts.notify.WEBHOOK_URL", "https://hooks.test.com"),
        ):
            results = notify_mod.dispatch("Alert", "Body")

            assert len(results) == 2
            assert results[0]["success"] is False
            assert results[1]["success"] is True

    def test_dispatch_specific_channel(self):
        """Dispatch only to specified channel."""
        with (
            patch("scripts.notify.send_email",
                  return_value={"success": True, "message": "OK"}),
            patch("scripts.notify.send_webhook",
                  return_value={"success": True, "message": "OK"}),
        ):
            results = notify_mod.dispatch("Alert", "Body", channels=["email"])

            assert len(results) == 1
            assert results[0]["channel"] == "email"


# ===========================================================================
# collect-metrics.py tests
# ===========================================================================


@pytest.fixture(scope="module")
def cm_mod():
    """Fixture providing the collect-metrics module."""
    import scripts.collect_metrics as m  # noqa: F811
    return m


class TestCollectMetrics:
    """Tests for collect-metrics module functions."""

    def test_collect_crawl_metrics(self):
        """Parses ingestion_runs query results correctly."""
        import scripts.collect_metrics as m

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = [
            ("pncp", 10, 9, 1, 500, 450, 400,
             _dt("2026-07-11T12:00:00"), _dt("2026-07-11T12:00:00")),
            ("dom_sc", 5, 5, 0, 200, 190, 180,
             _dt("2026-07-11T10:00:00"), _dt("2026-07-11T10:00:00")),
        ]

        result = m.collect_crawl_metrics(mock_conn, days=7)

        assert result["total_runs"] == 15
        assert result["total_successful"] == 14
        assert result["total_failed"] == 1
        assert result["overall_success_rate"] == pytest.approx(93.3, rel=0.1)
        assert len(result["sources"]) == 2
        assert result["sources"][0]["source"] == "pncp"
        assert result["sources"][0]["success_rate"] == 90.0

    def test_collect_crawl_metrics_empty(self):
        """Empty query results — safe defaults."""
        import scripts.collect_metrics as m

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        result = m.collect_crawl_metrics(mock_conn, days=7)

        assert result["sources"] == []
        assert result["total_runs"] == 0
        assert result["overall_success_rate"] == 0.0

    def test_collect_coverage_metrics(self):
        """Parses entity coverage query correctly."""
        import scripts.collect_metrics as m

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (100, 85)
        mock_cur.fetchall.return_value = [
            ("pncp", 80),
            ("dom_sc", 60),
        ]

        result = m.collect_coverage_metrics(mock_conn)

        assert result["total_entities"] == 100
        assert result["covered_entities"] == 85
        assert result["uncovered_entities"] == 15
        assert result["coverage_pct"] == 85.0
        assert result["by_source"]["pncp"] == 80

    def test_collect_backup_metrics_log_found(self):
        """Parses backup log for structured JSON entry."""
        import scripts.collect_metrics as m

        log = (
            '[2026-07-11 06:00:00] [INFO] LOG_JSON: '
            '{"event":"backup","timestamp":"2026-07-11T06:00:00+00:00",'
            '"file":"dump.gz","size_bytes":1048576,"duration_sec":120,"status":"success"}\n'
        )
        with (
            patch("scripts.collect_metrics.Path.exists", return_value=True),
            patch("scripts.collect_metrics.Path.read_text", return_value=log),
        ):
            result = m.collect_backup_metrics()

            assert result["last_backup"] == "2026-07-11T06:00:00+00:00"
            assert result["last_backup_status"] == "success"
            assert result["last_backup_size"] == 1048576
            assert result["log_available"] is True

    def test_collect_backup_metrics_log_missing(self):
        """Backup log file not found."""
        import scripts.collect_metrics as m

        with patch("scripts.collect_metrics.Path.exists", return_value=False):
            result = m.collect_backup_metrics()

            assert result["last_backup"] is None
            assert result["last_backup_status"] == "unknown"
            assert result["log_available"] is False

    def test_collect_backup_metrics_log_empty(self):
        """Backup log exists but is empty."""
        import scripts.collect_metrics as m

        with (
            patch("scripts.collect_metrics.Path.exists", return_value=True),
            patch("scripts.collect_metrics.Path.read_text", return_value=""),
        ):
            result = m.collect_backup_metrics()

            assert result["last_backup"] is None
            assert result["log_available"] is True

    def test_check_consecutive_failures(self):
        """Detects sources with N+ consecutive failures."""
        import scripts.collect_metrics as m

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = [
            ("pncp", 4, _dt("2026-07-10T10:00:00"), _dt("2026-07-11T08:00:00")),
        ]

        result = m.check_consecutive_failures(mock_conn, threshold=3)

        assert len(result) == 1
        assert result[0]["source"] == "pncp"
        assert result[0]["consecutive_failures"] == 4

    def test_check_consecutive_failures_none(self):
        """No sources with consecutive failures — empty list."""
        import scripts.collect_metrics as m

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        result = m.check_consecutive_failures(mock_conn, threshold=3)

        assert result == []


# ===========================================================================
# check-alerts.py tests
# ===========================================================================


class TestCheckAlerts:
    """Tests for check-alerts module functions."""

    def test_alert_registry(self):
        """AlertRegistry accumulates alerts correctly."""
        import scripts.check_alerts as m

        reg = m.AlertRegistry()

        assert reg.alerts == []
        assert reg.max_severity == 0

        reg.add(2, "disk", "Disk critical", "90% used")
        assert len(reg.alerts) == 1
        assert reg.max_severity == 2
        assert reg.has_critical() is True

        reg.add(1, "backup", "Backup stale", "28h ago")
        assert len(reg.alerts) == 2
        assert reg.has_warnings() is True

        data = reg.to_dict()
        assert data["total_alerts"] == 2
        assert data["max_severity"] == 2

    def test_check_disk_warning(self):
        """Disk at warn threshold triggers warning alert."""
        import scripts.check_alerts as m

        with (
            patch("scripts.check_alerts.shutil.disk_usage") as mock_du,
            patch("scripts.check_alerts.ALERT_DISK_WARN_PCT", 80),
            patch("scripts.check_alerts.ALERT_DISK_CRIT_PCT", 90),
        ):
            mock_du.return_value.used = 85 * 1024**3
            mock_du.return_value.total = 100 * 1024**3
            mock_du.return_value.free = 15 * 1024**3

            reg = m.AlertRegistry()
            m.check_disk(reg)

            assert len(reg.alerts) == 1
            assert reg.alerts[0]["severity"] == 1
            assert reg.alerts[0]["category"] == "disk"

    def test_check_disk_critical(self):
        """Disk at critical threshold triggers critical alert."""
        import scripts.check_alerts as m

        with (
            patch("scripts.check_alerts.shutil.disk_usage") as mock_du,
            patch("scripts.check_alerts.ALERT_DISK_WARN_PCT", 80),
            patch("scripts.check_alerts.ALERT_DISK_CRIT_PCT", 90),
        ):
            mock_du.return_value.used = 95 * 1024**3
            mock_du.return_value.total = 100 * 1024**3
            mock_du.return_value.free = 5 * 1024**3

            reg = m.AlertRegistry()
            m.check_disk(reg)

            assert len(reg.alerts) == 1
            assert reg.alerts[0]["severity"] == 2
            assert reg.alerts[0]["category"] == "disk"

    def test_check_disk_ok(self):
        """Normal disk usage — no alerts."""
        import scripts.check_alerts as m

        with (
            patch("scripts.check_alerts.shutil.disk_usage") as mock_du,
            patch("scripts.check_alerts.ALERT_DISK_WARN_PCT", 80),
            patch("scripts.check_alerts.ALERT_DISK_CRIT_PCT", 90),
        ):
            mock_du.return_value.used = 40 * 1024**3
            mock_du.return_value.total = 100 * 1024**3
            mock_du.return_value.free = 60 * 1024**3

            reg = m.AlertRegistry()
            m.check_disk(reg)

            assert len(reg.alerts) == 0

    def test_check_db_online_success(self):
        """psql returns OK — no alert."""
        import scripts.check_alerts as m

        with patch("scripts.check_alerts.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "1\n"
            mock_run.return_value = mock_result

            reg = m.AlertRegistry()
            m.check_db_online(reg)

            assert len(reg.alerts) == 0

    def test_check_db_online_failure(self):
        """psql fails — critical alert."""
        import scripts.check_alerts as m

        with patch("scripts.check_alerts.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "connection refused"
            mock_run.return_value = mock_result

            reg = m.AlertRegistry()
            m.check_db_online(reg)

            assert len(reg.alerts) == 1
            assert reg.alerts[0]["severity"] == 2
            assert reg.alerts[0]["category"] == "db"

    def test_check_storage_box_mounted(self):
        """Storage Box mounted — no alert."""
        import scripts.check_alerts as m

        with (
            patch("scripts.check_alerts.os.path.ismount", return_value=True),
            patch("scripts.check_alerts.os.listdir",
                  return_value=["backup_1.dump"]),
        ):
            reg = m.AlertRegistry()
            m.check_storage_box(reg)

            assert len(reg.alerts) == 0

    def test_check_storage_box_not_mounted(self):
        """Storage Box not mounted — critical alert."""
        import scripts.check_alerts as m

        with patch("scripts.check_alerts.os.path.ismount", return_value=False):
            reg = m.AlertRegistry()
            m.check_storage_box(reg)

            assert len(reg.alerts) == 1
            assert reg.alerts[0]["severity"] == 2
            assert reg.alerts[0]["category"] == "storage"

    def test_check_backup_recent(self):
        """Backup ran recently — no alert."""
        import scripts.check_alerts as m

        with (
            patch("scripts.check_alerts.Path.exists", return_value=True),
            patch("scripts.check_alerts.Path.read_text") as mock_read,
            patch("scripts.check_alerts.ALERT_BACKUP_MAX_HOURS", 28),
        ):
            mock_read.return_value = (
                '[2026-07-11 06:00:00] [INFO] LOG_JSON: '
                '{"event":"backup","timestamp":"2026-07-11T06:00:00+00:00",'
                '"status":"success","size_bytes":1048576}\n'
            )

            reg = m.AlertRegistry()
            m.check_backup(reg)

            assert len(reg.alerts) == 0

    def test_check_backup_failed(self):
        """Last backup failed — critical alert."""
        import scripts.check_alerts as m

        with (
            patch("scripts.check_alerts.Path.exists", return_value=True),
            patch("scripts.check_alerts.Path.read_text") as mock_read,
        ):
            mock_read.return_value = (
                '[2026-07-11 06:00:00] [INFO] LOG_JSON: '
                '{"event":"backup","timestamp":"2026-07-11T06:00:00+00:00",'
                '"status":"failed","size_bytes":0}\n'
            )

            reg = m.AlertRegistry()
            m.check_backup(reg)

            assert len(reg.alerts) == 1
            assert reg.alerts[0]["severity"] == 2
            assert reg.alerts[0]["category"] == "backup"

    def test_check_api_keys_missing(self):
        """Missing required API key — warning alert."""
        import scripts.check_alerts as m

        with patch("scripts.check_alerts.os.getenv", return_value=""):
            reg = m.AlertRegistry()
            m.check_api_keys(reg)

            assert len(reg.alerts) >= 2

    def test_check_api_keys_present(self):
        """All API keys present — no warnings."""
        import scripts.check_alerts as m

        def _mock_getenv(key, default=None):
            env = {"OPENAI_API_KEY": "sk-test123", "DOM_SC_API_KEY": "dom-key-456"}
            return env.get(key, default) if default else env.get(key, "")

        with patch("scripts.check_alerts.os.getenv", side_effect=_mock_getenv):
            reg = m.AlertRegistry()
            m.check_api_keys(reg)

            # Only PORTAL_TRANSPARENCIA_API_KEY info alert
            assert len(reg.alerts) == 1
            assert reg.alerts[0]["severity"] == 0


# ===========================================================================
# health-dashboard.py tests
# ===========================================================================


class TestHealthDashboard:
    """Tests for health-dashboard module functions."""

    def test_status_icon_known(self):
        """Known statuses map to correct icons."""
        import scripts.health_dashboard as m

        assert m._status_icon("pass") == "PASS"
        assert m._status_icon("fail") == "FAIL"
        assert m._status_icon("warn") == "WARN"
        assert m._status_icon("healthy") == "OK"

    def test_status_icon_unknown(self):
        """Unknown status returns question mark."""
        import scripts.health_dashboard as m

        assert m._status_icon("nonexistent") == "?"

    def test_collect_system_health_checks(self):
        """System health collector runs all checks."""
        import scripts.health_dashboard as m

        with (
            patch("scripts.health_dashboard.subprocess.run") as mock_run,
            patch("scripts.health_dashboard.shutil.disk_usage") as mock_du,
            patch("scripts.health_dashboard.os.path.ismount", return_value=True),
        ):
            mock_db = MagicMock()
            mock_db.returncode = 0
            mock_db.stdout = "1\n"

            mock_du.return_value.used = 45 * 1024**3
            mock_du.return_value.total = 100 * 1024**3
            mock_du.return_value.free = 55 * 1024**3

            mock_run.return_value = mock_db

            result = m.collect_system_health()

            assert result["status"] == "healthy"
            assert result["checks"]["db"]["status"] == "pass"
            assert result["checks"]["disk"]["status"] == "pass"
            assert result["checks"]["storage_box"]["status"] == "pass"

    def test_collect_crawl_stats_db_error(self):
        """DB error during crawl stats collection returns error field."""
        import scripts.health_dashboard as m

        with patch("scripts.health_dashboard.get_db_conn",
                   side_effect=Exception("DB down")):
            result = m.collect_crawl_stats()

            assert result["error"] is not None
            assert "DB down" in result["error"]

    def test_collect_alert_summary_subprocess(self):
        """Alert summary runs check-alerts.py as subprocess and parses JSON."""
        import scripts.health_dashboard as m

        mock_json = json.dumps({
            "event": "alert_check",
            "total_alerts": 1,
            "alerts": [
                {"severity": 2, "category": "disk",
                 "title": "Disk critical", "message": "90% used"},
            ],
        })

        with (
            patch("scripts.health_dashboard.subprocess.run") as mock_run,
            patch("scripts.health_dashboard.os.path.isfile", return_value=True),
        ):
            mock_result = MagicMock()
            mock_result.returncode = 2
            mock_result.stdout = mock_json
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = m.collect_alert_summary()

            assert result["total"] == 1
            assert result["critical"] == 1
            assert result["alerts"][0]["category"] == "disk"

    def test_collect_alert_summary_not_found(self):
        """check-alerts.py not found — returns error gracefully."""
        import scripts.health_dashboard as m

        with patch("scripts.health_dashboard.os.path.isfile", return_value=False):
            result = m.collect_alert_summary()

            assert result["total"] == 0
            assert "not found" in result["error"]

    def test_collect_backup_status(self):
        """Backup status parses log correctly."""
        import scripts.health_dashboard as m

        with (
            patch("scripts.health_dashboard.Path.exists", return_value=True),
            patch("scripts.health_dashboard.Path.read_text",
                  return_value=(
                      '[2026-07-11 06:00:00] [INFO] LOG_JSON: '
                      '{"event":"backup","timestamp":"2026-07-11T06:00:00+00:00",'
                      '"status":"success","size_bytes":2097152}\n'
                  )),
        ):
            result = m.collect_backup_status()

            assert result["last_backup"] == "2026-07-11T06:00:00+00:00"
            assert result["status"] == "success"
            assert result["size_mb"] == 2.0
            assert result["hours_ago"] is not None


# ===========================================================================
# Helper
# ===========================================================================


class _dt:
    """Minimal mock for datetime-like objects returned by psycopg2."""

    def __init__(self, iso_str: str) -> None:
        self._iso = iso_str

    def isoformat(self) -> str:
        return self._iso
