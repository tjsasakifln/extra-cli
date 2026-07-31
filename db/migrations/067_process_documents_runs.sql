-- ============================================================================
-- Migration 067: Process documents run ledger (metadata only — raw blobs outside PG/Git)
-- ============================================================================
-- Purpose: Persist fail-closed DocumentRunResult summaries and document
-- inventory for capability procurement_process_documents.
-- Blobs remain content-addressed on disk (ADR-020).
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.process_document_runs (
    run_id                  TEXT PRIMARY KEY,
    canonical_entity_id     TEXT NOT NULL,
    source_id               TEXT NOT NULL,
    portal_family           TEXT NOT NULL,
    status                  TEXT NOT NULL,
    capabilities_requested  TEXT[] NOT NULL DEFAULT '{}',
    capabilities_proven     TEXT[] NOT NULL DEFAULT '{}',
    started_at              TIMESTAMPTZ NOT NULL,
    finished_at             TIMESTAMPTZ NOT NULL,
    query_parameters        JSONB NOT NULL DEFAULT '{}'::jsonb,
    pages_attempted         INTEGER NOT NULL DEFAULT 0,
    pages_completed         INTEGER NOT NULL DEFAULT 0,
    records_seen            INTEGER NOT NULL DEFAULT 0,
    processes_seen          INTEGER NOT NULL DEFAULT 0,
    documents_discovered    INTEGER NOT NULL DEFAULT 0,
    documents_downloaded    INTEGER NOT NULL DEFAULT 0,
    documents_unchanged     INTEGER NOT NULL DEFAULT 0,
    documents_failed        INTEGER NOT NULL DEFAULT 0,
    errors                  JSONB NOT NULL DEFAULT '[]'::jsonb,
    blockers                JSONB NOT NULL DEFAULT '[]'::jsonb,
    retry_count             INTEGER NOT NULL DEFAULT 0,
    latency_ms              DOUBLE PRECISION,
    raw_manifest_uri        TEXT,
    checkpoint_uri          TEXT,
    evidence_uri            TEXT,
    success_zero_justification TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_process_document_runs_entity
    ON public.process_document_runs (canonical_entity_id, finished_at DESC);

CREATE INDEX IF NOT EXISTS idx_process_document_runs_status
    ON public.process_document_runs (status);

CREATE TABLE IF NOT EXISTS public.process_documents (
    internal_id             TEXT PRIMARY KEY,
    sha256                  TEXT NOT NULL,
    size_bytes              BIGINT NOT NULL,
    download_url            TEXT NOT NULL,
    source_id               TEXT NOT NULL,
    canonical_entity_id     TEXT NOT NULL,
    portal_family           TEXT NOT NULL,
    document_category       TEXT NOT NULL DEFAULT 'unknown_category',
    official_id             TEXT,
    original_title          TEXT,
    original_filename       TEXT,
    administrative_process_id TEXT,
    procurement_id          TEXT,
    notice_id               TEXT,
    contract_id             TEXT,
    related_bidder          TEXT,
    source_page_url         TEXT,
    published_at            TEXT,
    fetched_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    declared_mime           TEXT,
    detected_mime           TEXT,
    extension               TEXT,
    version                 INTEGER NOT NULL DEFAULT 1,
    run_id                  TEXT REFERENCES public.process_document_runs(run_id) ON DELETE SET NULL,
    raw_uri                 TEXT,
    public_access_status    TEXT NOT NULL DEFAULT 'public',
    sanitization_status     TEXT NOT NULL DEFAULT 'raw',
    error                   TEXT,
    blocker                 TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_process_documents_entity
    ON public.process_documents (canonical_entity_id);

CREATE INDEX IF NOT EXISTS idx_process_documents_procurement
    ON public.process_documents (procurement_id);

CREATE INDEX IF NOT EXISTS idx_process_documents_sha256
    ON public.process_documents (sha256);

COMMIT;
