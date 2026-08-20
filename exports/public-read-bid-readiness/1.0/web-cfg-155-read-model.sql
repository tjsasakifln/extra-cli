SELECT
  schema_version,
  run_id,
  query_id,
  overall_state,
  generated_at,
  as_of,
  expires_at,
  human_review_required,
  not_legal_conclusion,
  publication_authorization,
  index_authorization,
  content_hash,
  producer_version
FROM public_read_bid_readiness_v1.envelopes
WHERE query_id = $1
LIMIT 1
