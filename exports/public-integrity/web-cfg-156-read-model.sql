SELECT
  schema_version,
  query_id,
  aggregate_state,
  checked_at,
  as_of,
  expires_at,
  not_legal_conclusion,
  content_hash,
  producer_version
FROM public_read_integrity_v1.queries
WHERE query_id = $1
LIMIT 1
