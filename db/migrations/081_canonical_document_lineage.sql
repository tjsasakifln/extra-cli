-- 081_canonical_document_lineage.sql
-- #272: immutable document metadata/version lineage; blobs remain outside PostgreSQL.
-- The text identifiers preserve compatibility with the pre-ledger seed tables.

BEGIN;

CREATE TABLE IF NOT EXISTS procurement_processes (
    id                BIGSERIAL PRIMARY KEY,
    entity_id         INTEGER NOT NULL REFERENCES sc_public_entities(id) ON DELETE RESTRICT,
    source            TEXT NOT NULL,
    official_id       TEXT NOT NULL,
    canonical_url     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_id, source, official_id)
);

CREATE TABLE IF NOT EXISTS documents (
    id                TEXT PRIMARY KEY,
    process_id        TEXT,
    sha256            TEXT,
    source            TEXT
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS entity_id INTEGER REFERENCES sc_public_entities(id) ON DELETE RESTRICT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS official_id TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS canonical_key TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS official_url TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS current_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata_complete BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE documents
SET canonical_key = COALESCE(canonical_key, id),
    official_id = COALESCE(official_id, id),
    category = COALESCE(category, 'legacy_unclassified')
WHERE canonical_key IS NULL OR official_id IS NULL OR category IS NULL;

DO $migration$
DECLARE
    duplicate_groups BIGINT;
BEGIN
    SELECT COUNT(*) INTO duplicate_groups
    FROM (
        SELECT 1
        FROM documents
        WHERE source IS NOT NULL AND canonical_key IS NOT NULL
        GROUP BY source, canonical_key
        HAVING COUNT(*) > 1
    ) duplicates;
    IF duplicate_groups > 0 THEN
        RAISE EXCEPTION
            'migration 081: % duplicate (source, canonical_key) groups in documents; deduplicate before applying',
            duplicate_groups;
    END IF;
END
$migration$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_source_canonical
    ON documents (source, canonical_key);

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'documents'::regclass
          AND conname = 'ck_documents_metadata_complete'
    ) THEN
        ALTER TABLE documents ADD CONSTRAINT ck_documents_metadata_complete CHECK (
            NOT metadata_complete OR (
                entity_id IS NOT NULL AND source IS NOT NULL AND canonical_key IS NOT NULL
                AND category IS NOT NULL AND official_url IS NOT NULL AND current_version >= 1
            )
        );
    END IF;
END
$migration$;

CREATE TABLE IF NOT EXISTS source_fetches (
    id                       BIGSERIAL PRIMARY KEY,
    source                   TEXT NOT NULL,
    sanitized_url            TEXT NOT NULL,
    document_run_id          TEXT REFERENCES process_document_runs(run_id) ON DELETE SET NULL,
    crawl_job_attempt_id     BIGINT REFERENCES crawl_job_attempts(id) ON DELETE SET NULL,
    status                   TEXT NOT NULL CHECK (status IN ('success', 'failed', 'blocked')),
    http_status              INTEGER CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    blob_confirmed           BOOLEAN NOT NULL DEFAULT FALSE,
    metadata_confirmed       BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at               TIMESTAMPTZ NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status <> 'success' OR (blob_confirmed AND metadata_confirmed))
);

CREATE TABLE IF NOT EXISTS document_versions (
    id                TEXT PRIMARY KEY,
    document_id       TEXT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    version           INTEGER NOT NULL,
    sha256            TEXT NOT NULL
);

ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS source_version TEXT;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS size_bytes BIGINT;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS body_uri TEXT;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS mime_type TEXT;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS source_fetch_id BIGINT REFERENCES source_fetches(id) ON DELETE RESTRICT;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS metadata_complete BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- CREATE TABLE IF NOT EXISTS does not retrofit constraints onto the legacy
-- document_versions table.  Keep legacy orphan rows readable while enforcing
-- canonical lineage for every new or updated row.
DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'document_versions'::regclass
          AND conname = 'document_versions_document_id_fkey'
    ) THEN
        ALTER TABLE document_versions
            ADD CONSTRAINT document_versions_document_id_fkey
            FOREIGN KEY (document_id) REFERENCES documents(id)
            ON DELETE RESTRICT NOT VALID;
    END IF;
END
$migration$;

UPDATE document_versions
SET source_version = COALESCE(source_version, 'legacy-v' || version::text)
WHERE source_version IS NULL;

DO $migration$
DECLARE
    duplicate_number_groups BIGINT;
    duplicate_sha_groups BIGINT;
BEGIN
    SELECT COUNT(*) INTO duplicate_number_groups
    FROM (
        SELECT 1 FROM document_versions
        GROUP BY document_id, version HAVING COUNT(*) > 1
    ) duplicates;
    SELECT COUNT(*) INTO duplicate_sha_groups
    FROM (
        SELECT 1 FROM document_versions
        GROUP BY document_id, sha256 HAVING COUNT(*) > 1
    ) duplicates;
    IF duplicate_number_groups > 0 OR duplicate_sha_groups > 0 THEN
        RAISE EXCEPTION
            'migration 081: duplicate document_versions groups (document_id, version)=%; (document_id, sha256)=%; deduplicate before applying',
            duplicate_number_groups, duplicate_sha_groups;
    END IF;
END
$migration$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_versions_number
    ON document_versions (document_id, version);
CREATE UNIQUE INDEX IF NOT EXISTS uq_document_versions_sha
    ON document_versions (document_id, sha256);
CREATE UNIQUE INDEX IF NOT EXISTS uq_document_versions_source_sha
    ON document_versions (document_id, source_version, sha256);

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'document_versions'::regclass
          AND conname = 'ck_document_versions_metadata_complete'
    ) THEN
        ALTER TABLE document_versions ADD CONSTRAINT ck_document_versions_metadata_complete CHECK (
            NOT metadata_complete OR (
                sha256 ~ '^[0-9a-f]{64}$' AND size_bytes > 0
                AND body_uri LIKE 'cas://%' AND source_fetch_id IS NOT NULL
                AND fetched_at IS NOT NULL
            )
        );
    END IF;
END
$migration$;

CREATE TABLE IF NOT EXISTS process_document_links (
    process_id          BIGINT NOT NULL REFERENCES procurement_processes(id) ON DELETE CASCADE,
    document_id         TEXT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    document_version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
    relationship        TEXT NOT NULL DEFAULT 'attachment',
    linked_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (process_id, document_version_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_entity_source
    ON documents (entity_id, source, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_versions_sha
    ON document_versions (sha256);
CREATE INDEX IF NOT EXISTS idx_process_document_links_document
    ON process_document_links (document_id, process_id);
CREATE INDEX IF NOT EXISTS idx_procurement_processes_official
    ON procurement_processes (source, official_id, entity_id);

COMMIT;
