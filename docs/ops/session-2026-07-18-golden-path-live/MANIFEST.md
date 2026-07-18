# Golden path LIVE slice — DoD §12.1

Story ROI-cand-dyn-slice-b904c9d40e3a · cyc-2026-07-18T145609Z

## Fixes shipped
- `db/migrations/055_fix_upsert_pncp_raw_bids_ambiguous.sql` — upsert RPC fix
- resilience pipeline: no stage regress; promote skips already-past checkpoints
- golden_path: coverage + snapshot steps; FRESHNESS_SOURCES scope; GOLDEN_PATH_CRAWL_MODE/LIMIT
- schema applied: entity_aliases, engineering_opportunities, opportunity_intel, target_universe_*

## Live evidence
| Artifact | Result |
|----------|--------|
| pncp-live5.json | success fetched=6 inserted=6 |
| ledger-full.json | fontes OK, inserted=6, coverage, snapshot, excel, pdf (freshness fail contracts before scope) |
| ledger-final.json | exit 0 success_zero, freshness PASS (pncp scoped), coverage, snapshot, excel, pdf |

## Commands
```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
export GOLDEN_PATH_CRAWL_MODE=full GOLDEN_PATH_CRAWL_LIMIT=5
python3 -m scripts.golden_path --sources pncp --bootstrap --allow-zero \
  --ledger-output docs/ops/session-2026-07-18-golden-path-live/ledger-final.json
```
