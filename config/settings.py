"""Centralized settings from environment variables.

All configuration for the Extra Consultoria platform lives here.
No hardcoded credentials, paths, or URLs in application code.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
INTEL_DIR = DATA_DIR / "intel"
REPORTS_DIR = DATA_DIR / "reports"
PDF_DIR = OUTPUT_DIR / "pdfs"
EXCEL_DIR = OUTPUT_DIR / "excels"
LOG_DIR = OUTPUT_DIR / "logs"

# Ensure output dirs exist
for _d in (INTEL_DIR, REPORTS_DIR, PDF_DIR, EXCEL_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
LOCAL_DATALAKE_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
)
# DEFAULT_DSN alias for backward compatibility with monitor.py and orchestrator.py
DEFAULT_DSN = LOCAL_DATALAKE_DSN
DATALAKE_BACKEND = os.getenv("DATALAKE_BACKEND", "local")
DATALAKE_QUERY_ENABLED = os.getenv("DATALAKE_QUERY_ENABLED", "true").lower() == "true"

# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
OPENAI_TIMEOUT_S = int(os.getenv("OPENAI_TIMEOUT_S", "10"))
OPENAI_MAX_CONCURRENT = int(os.getenv("OPENAI_MAX_CONCURRENT", "5"))

# ---------------------------------------------------------------------------
# PNCP API
# ---------------------------------------------------------------------------
PNCP_BASE = os.getenv("PNCP_BASE", "https://pncp.gov.br/api/consulta/v3")
PNCP_FILES_BASE = os.getenv("PNCP_FILES_BASE", "https://pncp.gov.br/api/pncp/v1")
PNCP_MAX_PAGES = int(os.getenv("PNCP_MAX_PAGES", "50"))
PNCP_PAGE_SIZE = int(os.getenv("PNCP_PAGE_SIZE", "50"))
PNCP_READ_TIMEOUT = int(os.getenv("PNCP_READ_TIMEOUT", "15"))
PNCP_MAX_RETRIES = int(os.getenv("PNCP_MAX_RETRIES", "1"))

# ---------------------------------------------------------------------------
# DOM-SC (Diário Oficial dos Municípios de SC)
# ---------------------------------------------------------------------------
DOM_SC_API_KEY = os.getenv("DOM_SC_API_KEY", "")
DOM_SC_BASE = os.getenv("DOM_SC_BASE", "https://www.diariomunicipal.sc.gov.br")

# ---------------------------------------------------------------------------
# PCP v2 (Portal de Compras Públicas)
# ---------------------------------------------------------------------------
PCP_BASE = os.getenv(
    "PCP_BASE",
    "https://compras.api.portaldecompraspublicas.com.br/v2",
)

# ---------------------------------------------------------------------------
# ComprasGov v3
# ---------------------------------------------------------------------------
COMPRAS_GOV_BASE = os.getenv(
    "COMPRAS_GOV_BASE",
    "https://dadosabertos.compras.gov.br",
)

# ---------------------------------------------------------------------------
# Ingestion Settings
# ---------------------------------------------------------------------------
INGESTION_UFS = os.getenv("INGESTION_UFS", "SC").split(",")
INGESTION_MODALIDADES = [int(m) for m in os.getenv("INGESTION_MODALIDADES", "1,2,3,4,5,6,7").split(",")]
INGESTION_DATE_RANGE_DAYS = int(os.getenv("INGESTION_DATE_RANGE_DAYS", "30"))
INGESTION_INCREMENTAL_DAYS = int(os.getenv("INGESTION_INCREMENTAL_DAYS", "3"))
INGESTION_PURGE_GRACE_DAYS = int(os.getenv("INGESTION_PURGE_GRACE_DAYS", "400"))
INGESTION_BATCH_DELAY_S = float(os.getenv("INGESTION_BATCH_DELAY_S", "1.0"))
INGESTION_CONCURRENT_UFS = int(os.getenv("INGESTION_CONCURRENT_UFS", "3"))
INGESTION_BATCH_SIZE_UFS = int(os.getenv("INGESTION_BATCH_SIZE_UFS", "5"))
INGESTION_MAX_PAGES = int(os.getenv("INGESTION_MAX_PAGES", "50"))

# Full crawl schedule
INGESTION_FULL_CRAWL_HOUR_UTC = int(os.getenv("INGESTION_FULL_CRAWL_HOUR_UTC", "5"))
INGESTION_INCREMENTAL_HOURS = [int(h) for h in os.getenv("INGESTION_INCREMENTAL_HOURS", "11,17,23").split(",")]

# ---------------------------------------------------------------------------
# Sector Config
# ---------------------------------------------------------------------------
SECTORS_CONFIG_PATH = CONFIG_DIR / "sectors_config.yaml"
SECTORS_DATA_PATH = CONFIG_DIR / "sectors_data.yaml"

# ---------------------------------------------------------------------------
# Coverage SLA
# ---------------------------------------------------------------------------
COVERAGE_TARGET_PCT = float(os.getenv("COVERAGE_TARGET_PCT", "100.0"))
COVERAGE_WINDOW_DAYS = int(os.getenv("COVERAGE_WINDOW_DAYS", "90"))

# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------
ENTITY_ENRICHMENT_TTL_DAYS = int(os.getenv("ENTITY_ENRICHMENT_TTL_DAYS", "30"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
INTEL_LOG_LEVEL = os.getenv("INTEL_LOG_LEVEL", "INFO")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # "json" or "text"
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))

# ---------------------------------------------------------------------------
# Monitoring & Alerts (TD-5.5)
# ---------------------------------------------------------------------------

# Alert thresholds
ALERT_CONSECUTIVE_FAILURES = int(os.getenv("ALERT_CONSECUTIVE_FAILURES", "3"))
ALERT_DISK_WARN_PCT = int(os.getenv("ALERT_DISK_WARN_PCT", "80"))
ALERT_DISK_CRIT_PCT = int(os.getenv("ALERT_DISK_CRIT_PCT", "90"))
ALERT_BACKUP_MAX_HOURS = int(os.getenv("ALERT_BACKUP_MAX_HOURS", "28"))

# Metrics collection interval
COLLECT_METRICS_INTERVAL_MINUTES = int(os.getenv("COLLECT_METRICS_INTERVAL_MINUTES", "60"))

# ---------------------------------------------------------------------------
# Notifications (TD-5.5)
# ---------------------------------------------------------------------------

# SMTP email notification
NOTIFY_SMTP_HOST = os.getenv("NOTIFY_SMTP_HOST", "")
NOTIFY_SMTP_PORT = int(os.getenv("NOTIFY_SMTP_PORT", "587"))
NOTIFY_SMTP_USER = os.getenv("NOTIFY_SMTP_USER", "")
NOTIFY_SMTP_PASSWORD = os.getenv("NOTIFY_SMTP_PASSWORD", "")
NOTIFY_SMTP_FROM = os.getenv("NOTIFY_SMTP_FROM", "")
NOTIFY_SMTP_TO = os.getenv("NOTIFY_SMTP_TO", "")
NOTIFY_SMTP_USE_TLS = os.getenv("NOTIFY_SMTP_USE_TLS", "true").lower() == "true"

# Webhook notification (Slack / Discord)
NOTIFY_WEBHOOK_URL = os.getenv("NOTIFY_WEBHOOK_URL", "")
