BEGIN;
-- DESTRUCTIVE: this rollback drops columns containing backfilled and
-- application-written lineage metadata and CAS pointers. Take a full backup
-- of documents and document_versions before running it. The legacy tables are
-- intentionally preserved because migration 081 extends them in place.
DROP TABLE IF EXISTS process_document_links;
DROP INDEX IF EXISTS idx_document_versions_sha;
DROP INDEX IF EXISTS uq_document_versions_source_sha;
DROP INDEX IF EXISTS uq_document_versions_sha;
DROP INDEX IF EXISTS uq_document_versions_number;
ALTER TABLE IF EXISTS document_versions DROP CONSTRAINT IF EXISTS document_versions_document_id_fkey;
ALTER TABLE IF EXISTS document_versions DROP CONSTRAINT IF EXISTS ck_document_versions_metadata_complete;
ALTER TABLE IF EXISTS document_versions DROP COLUMN IF EXISTS created_at;
ALTER TABLE IF EXISTS document_versions DROP COLUMN IF EXISTS metadata_complete;
ALTER TABLE IF EXISTS document_versions DROP COLUMN IF EXISTS fetched_at;
ALTER TABLE IF EXISTS document_versions DROP COLUMN IF EXISTS source_fetch_id;
ALTER TABLE IF EXISTS document_versions DROP COLUMN IF EXISTS mime_type;
ALTER TABLE IF EXISTS document_versions DROP COLUMN IF EXISTS body_uri;
ALTER TABLE IF EXISTS document_versions DROP COLUMN IF EXISTS size_bytes;
ALTER TABLE IF EXISTS document_versions DROP COLUMN IF EXISTS source_version;
DROP TABLE IF EXISTS source_fetches;
DROP INDEX IF EXISTS idx_documents_entity_source;
DROP INDEX IF EXISTS uq_documents_source_canonical;
ALTER TABLE IF EXISTS documents DROP CONSTRAINT IF EXISTS ck_documents_metadata_complete;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS updated_at;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS created_at;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS metadata_complete;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS current_version;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS official_url;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS title;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS category;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS canonical_key;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS official_id;
ALTER TABLE IF EXISTS documents DROP COLUMN IF EXISTS entity_id;
DROP TABLE IF EXISTS procurement_processes;
COMMIT;
