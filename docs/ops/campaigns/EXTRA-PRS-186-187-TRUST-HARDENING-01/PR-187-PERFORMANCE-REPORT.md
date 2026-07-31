# PR #187 Performance Report

## Extraction path
- Server-side named cursors (`pseo_contracts`, `pseo_bids`)
- `fetchmany` chunks (default 5000)
- Isolation: REPEATABLE READ, read-only
- `statement_timeout=600000`, `connect_timeout=15`, `application_name=extra-pseo-export`
- Structural proof: `cur.fetchall()` removed from large-table path in `pipeline.py`

## Fixture export (local)
- 40 contracts + 200 bids fixture
- Wall time: ~4–5s including classification + write + validation (pytest suite 44 tests in 4.5s)

## 250k synthetic
- Not executed against live Postgres in this session (no productive DSN mutation; fixture path used).
- Structural readiness: chunked cursor API + counts metadata (`fetch_mode`, `chunk_size`).

## Non-claims
- Not claiming proven million-row production scale without measured run on representative volume.
