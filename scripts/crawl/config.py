"""Configuration for PNCP Data Lake ingestion pipeline.

All values are tuned for Supabase free tier limits:
- Max DB connections: 20 (free tier)
- Storage: 500 MB
- Row limits: soft limit around 50k rows per table

Environment variables override defaults at runtime.
"""

import os

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

DATALAKE_ENABLED = os.getenv("DATALAKE_ENABLED", "true").lower() in ("true", "1")
DATALAKE_QUERY_ENABLED = os.getenv("DATALAKE_QUERY_ENABLED", "true").lower() in ("true", "1")

# ---------------------------------------------------------------------------
# Crawl schedule (UTC hours)
# ---------------------------------------------------------------------------

# Full crawl runs once daily at 5 UTC = 2am BRT
INGESTION_FULL_CRAWL_HOUR_UTC = int(os.getenv("INGESTION_FULL_CRAWL_HOUR_UTC", "5"))

# Incremental crawls at 11, 17, 23 UTC = 8am, 2pm, 8pm BRT
INGESTION_INCREMENTAL_HOURS = [int(h) for h in os.getenv("INGESTION_INCREMENTAL_HOURS", "11,17,23").split(",")]

# ---------------------------------------------------------------------------
# Date range
# ---------------------------------------------------------------------------

# How many days back to crawl on a full crawl
INGESTION_DATE_RANGE_DAYS = int(
    os.getenv("INGESTION_DATE_RANGE_DAYS", "7")
)  # DISK-IO-002: 10→7 days; incremental crawl covers last 3 days 3x/day

# How many days back to crawl on incremental (+ 1 day overlap applied at runtime)
INGESTION_INCREMENTAL_DAYS = int(os.getenv("INGESTION_INCREMENTAL_DAYS", "3"))

# ---------------------------------------------------------------------------
# Rate limiting & concurrency
# ---------------------------------------------------------------------------

# UFs per batch (matches PNCP_BATCH_SIZE from main config)
INGESTION_BATCH_SIZE_UFS = int(os.getenv("INGESTION_BATCH_SIZE_UFS", "5"))

# Seconds to sleep between UF batches (avoids PNCP rate limits)
INGESTION_BATCH_DELAY_S = float(os.getenv("INGESTION_BATCH_DELAY_S", "2.0"))

# Max pages fetched per (UF, modalidade) combination
INGESTION_MAX_PAGES = int(os.getenv("INGESTION_MAX_PAGES", "50"))

# Max simultaneous UF crawls (asyncio.Semaphore)
INGESTION_CONCURRENT_UFS = int(os.getenv("INGESTION_CONCURRENT_UFS", "5"))

# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

# Rows per Supabase RPC call — keep under Supabase 1 MB request limit
INGESTION_UPSERT_BATCH_SIZE = int(os.getenv("INGESTION_UPSERT_BATCH_SIZE", "500"))

# ---------------------------------------------------------------------------
# Scope filters
# ---------------------------------------------------------------------------

# Modalidades to crawl: 4=Concorrência, 5=Pregão Eletr., 6=Pregão Pres.,
# 7=Contratação Direta, 8=Inexigibilidade, 12=Credenciamento
INGESTION_MODALIDADES = [int(m) for m in os.getenv("INGESTION_MODALIDADES", "4,5,6,7,8,12").split(",")]

# UFs to crawl — all Brazilian states + DF
INGESTION_UFS = os.getenv(
    "INGESTION_UFS",
    "AC,AL,AM,AP,BA,CE,DF,ES,GO,MA,MG,MS,MT,PA,PB,PE,PI,PR,RJ,RN,RO,RR,RS,SC,SE,SP,TO",
).split(",")

# ---------------------------------------------------------------------------
# Retention / Purge
# ---------------------------------------------------------------------------

# STORY-OBS-001: retention bumped 30→400 days so SEO programmatic pages
# (observatorio, alertas, municipios, orgao) have ~13 months of history.
INGESTION_RETENTION_DAYS = int(os.getenv("INGESTION_RETENTION_DAYS", "400"))

# Days after data_encerramento before a closed bid is purged (default 30).
# Bids still open (data_encerramento in the future) are NEVER purged.
INGESTION_PURGE_GRACE_DAYS = int(
    os.getenv(
        "INGESTION_PURGE_GRACE_DAYS",
        str(INGESTION_RETENTION_DAYS),
    )
)

# ---------------------------------------------------------------------------
# Backfill (one-time historical crawl)
# ---------------------------------------------------------------------------

# Total days to backfill (API max = 365)
INGESTION_BACKFILL_DAYS = int(os.getenv("INGESTION_BACKFILL_DAYS", "365"))

# Chunk size in days — keeps results under 50-page cap for high-volume UFs
INGESTION_BACKFILL_CHUNK_DAYS = int(os.getenv("INGESTION_BACKFILL_CHUNK_DAYS", "7"))

# ---------------------------------------------------------------------------
# Estatais SC (Lei 13.303) — feature flags & timeouts
# ---------------------------------------------------------------------------

INGESTION_CELESC_ENABLED = os.getenv("INGESTION_CELESC_ENABLED", "true").lower() in ("true", "1")
INGESTION_CASAN_ENABLED = os.getenv("INGESTION_CASAN_ENABLED", "true").lower() in ("true", "1")
INGESTION_EPAGRI_ENABLED = os.getenv("INGESTION_EPAGRI_ENABLED", "true").lower() in ("true", "1")

CELESC_TIMEOUT = int(os.getenv("CELESC_TIMEOUT", "30"))
CASAN_TIMEOUT = int(os.getenv("CASAN_TIMEOUT", "30"))
EPAGRI_TIMEOUT = int(os.getenv("EPAGRI_TIMEOUT", "30"))

ESTATAIS_SC_CRAWL_HOURS = [int(h) for h in os.getenv("ESTATAIS_SC_CRAWL_HOURS", "11,23").split(",")]
ESTATAIS_SC_CRAWL_TIMEOUT = int(os.getenv("ESTATAIS_SC_CRAWL_TIMEOUT", "600"))  # 10 min safety

# ---------------------------------------------------------------------------
# ARP (Atas de Registro de Precos) — EXT-010
# ---------------------------------------------------------------------------

INGESTION_ARP_ENABLED = os.getenv("INGESTION_ARP_ENABLED", "true").lower() in ("true", "1")

# Incremental ARP crawl: 2x/day (11:00, 23:00 UTC = 8am, 8pm BRT)
INGESTION_ARP_HOURS = [int(h) for h in os.getenv("INGESTION_ARP_HOURS", "11,23").split(",")]

# Max pages per UF — ARP has lower volume than bids
INGESTION_ARP_MAX_PAGES = int(os.getenv("INGESTION_ARP_MAX_PAGES", "20"))

# How many days back for ARP crawl
INGESTION_ARP_DAYS = int(os.getenv("INGESTION_ARP_DAYS", "90"))

# ---------------------------------------------------------------------------
# PCA (Planos de Contratacoes Anuais) — EXT-010
# ---------------------------------------------------------------------------

INGESTION_PCA_ENABLED = os.getenv("INGESTION_PCA_ENABLED", "true").lower() in ("true", "1")

# Weekly PCA crawl: Monday 9:00 UTC = 6am BRT
INGESTION_PCA_HOUR_UTC = int(os.getenv("INGESTION_PCA_HOUR_UTC", "9"))

# Max pages per UF for PCA crawl
INGESTION_PCA_MAX_PAGES = int(os.getenv("INGESTION_PCA_MAX_PAGES", "50"))

# ---------------------------------------------------------------------------
# Retry policy for ARQ ingestion jobs (GAP-004, #1581)
# ---------------------------------------------------------------------------

# Crawl jobs: max 3 tries with exponential backoff
# Delays: 60s -> 300s -> 900s (1st retry -> 2nd retry -> DEAD after 3rd failure)
CRAWL_RETRY_MAX_TRIES = int(os.getenv("CRAWL_RETRY_MAX_TRIES", "3"))
CRAWL_RETRY_BACKOFF_BASE = int(os.getenv("CRAWL_RETRY_BACKOFF_BASE", "60"))
CRAWL_RETRY_BACKOFF_MULTIPLIER = int(os.getenv("CRAWL_RETRY_BACKOFF_MULTIPLIER", "5"))

# Purge and enricher jobs: best-effort, no retry
PURGE_RETRY_MAX_TRIES = int(os.getenv("PURGE_RETRY_MAX_TRIES", "1"))
ENRICHER_RETRY_MAX_TRIES = int(os.getenv("ENRICHER_RETRY_MAX_TRIES", "1"))

# ---------------------------------------------------------------------------
# EXT-012: Sistema S + Federais no Raio 200km — Feature flags
# ---------------------------------------------------------------------------

INGESTION_SEBRAE_SC_ENABLED = os.getenv("INGESTION_SEBRAE_SC_ENABLED", "true").lower() in ("true", "1")
INGESTION_SESI_SENAI_SC_ENABLED = os.getenv("INGESTION_SESI_SENAI_SC_ENABLED", "true").lower() in ("true", "1")
INGESTION_UFSC_ENABLED = os.getenv("INGESTION_UFSC_ENABLED", "true").lower() in ("true", "1")
INGESTION_IFSC_ENABLED = os.getenv("INGESTION_IFSC_ENABLED", "true").lower() in ("true", "1")

# EXT-012 schedules (UTC)
# SEBRAE SC API leve — 2x/day
SEBRAE_SC_CRAWL_HOURS = [int(h) for h in os.getenv("SEBRAE_SC_CRAWL_HOURS", "8,20").split(",")]
SEBRAE_SC_CRAWL_TIMEOUT = int(os.getenv("SEBRAE_SC_CRAWL_TIMEOUT", "300"))

# SESI/SENAI SC — 1x/day
SESI_SENAI_SC_CRAWL_HOUR = int(os.getenv("SESI_SENAI_SC_CRAWL_HOUR_UTC", "12"))
SESI_SENAI_SC_CRAWL_TIMEOUT = int(os.getenv("SESI_SENAI_SC_CRAWL_TIMEOUT", "600"))

# UFSC — 1x/day
UFSC_CRAWL_HOUR = int(os.getenv("UFSC_CRAWL_HOUR_UTC", "13"))
UFSC_CRAWL_TIMEOUT = int(os.getenv("UFSC_CRAWL_TIMEOUT", "600"))

# IFSC — 1x/day
IFSC_CRAWL_HOUR = int(os.getenv("IFSC_CRAWL_HOUR_UTC", "14"))
IFSC_CRAWL_TIMEOUT = int(os.getenv("IFSC_CRAWL_TIMEOUT", "600"))

# ---------------------------------------------------------------------------
# EXT-008: Portal de Compras SC + e-lic — Feature flags & concurrency
# ---------------------------------------------------------------------------

INGESTION_SC_COMPRAS_ENABLED = os.getenv("INGESTION_SC_COMPRAS_ENABLED", "true").lower() in ("true", "1")
INGESTION_SC_COMPRAS_CONCURRENT_REQUESTS = int(os.getenv("INGESTION_SC_COMPRAS_CONCURRENT_REQUESTS", "3"))

# Max pages per crawl run
INGESTION_SC_COMPRAS_MAX_PAGES = int(os.getenv("INGESTION_SC_COMPRAS_MAX_PAGES", "100"))

# Full crawl: last 30 days
INGESTION_SC_COMPRAS_FULL_DAYS = int(os.getenv("INGESTION_SC_COMPRAS_FULL_DAYS", "30"))

# Incremental crawl: last 24h (+1h overlap applied at runtime)
INGESTION_SC_COMPRAS_INCREMENTAL_DAYS = int(os.getenv("INGESTION_SC_COMPRAS_INCREMENTAL_DAYS", "1"))

# ARQ timeouts
INGESTION_SC_COMPRAS_FULL_TIMEOUT = int(os.getenv("INGESTION_SC_COMPRAS_FULL_TIMEOUT", "7200"))
INGESTION_SC_COMPRAS_INCREMENTAL_TIMEOUT = int(os.getenv("INGESTION_SC_COMPRAS_INCREMENTAL_TIMEOUT", "1800"))

# Schedule (UTC) — incremental at 11:00, 17:00, 23:00 UTC = 8am, 2pm, 8pm BRT
INGESTION_SC_COMPRAS_FULL_HOUR_UTC = int(os.getenv("INGESTION_SC_COMPRAS_FULL_HOUR_UTC", "5"))
INGESTION_SC_COMPRAS_INCREMENTAL_HOURS = [
    int(h) for h in os.getenv("INGESTION_SC_COMPRAS_INCREMENTAL_HOURS", "11,17,23").split(",")
]

# ---------------------------------------------------------------------------
# EXT-009: DOM-SC API — Contratos de Todos os 295 Municipios de SC
# ---------------------------------------------------------------------------

INGESTION_DOM_SC_ENABLED = os.getenv("INGESTION_DOM_SC_ENABLED", "true").lower() in ("true", "1")

# DOM-SC API authentication
DOM_SC_CPF = os.getenv("DOM_SC_CPF", "")
DOM_SC_CNPJ = os.getenv("DOM_SC_CNPJ", "")
DOM_SC_API_KEY = os.getenv("DOM_SC_API_KEY", "")

# Schedule: daily at 9:00 UTC = 6:00 BRT
INGESTION_DOM_SC_HOUR_UTC = int(os.getenv("INGESTION_DOM_SC_HOUR_UTC", "9"))

# ARQ timeout: 1h safety (expected < 15 min for ~5k contracts/mes)
INGESTION_DOM_SC_TIMEOUT = int(os.getenv("INGESTION_DOM_SC_TIMEOUT", "3600"))

# Delay between municipio groups to avoid rate limiting
INGESTION_DOM_SC_DELAY_S = float(os.getenv("INGESTION_DOM_SC_DELAY_S", "1.0"))
