# Contact discovery — durable batch

Additive job bus around shipped `run_account`. Does not change
`web_discovery.py` planner/crawler/heuristics.

Job type: `CONFENGE_CONTACT_DISCOVERY`

## Operator commands

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"

python3 -m scripts.decision_unit_intelligence batch enqueue \
  --cohort COHORT_ID --cnpjs 11222333000181,44555666000177 \
  --search-backend off --service reajuste_14133

# Full TARGET_CONFIRMED population from the mode-aware canonical store.
# This mode rejects --limit and refuses a disabled public-search backend.
python3 -m scripts.decision_unit_intelligence batch enqueue \
  --cohort "target-confirmed-$(date -u +%Y%m%dT%H%M%SZ)" \
  --population target-confirmed \
  --search-backend searxng \
  --searxng-url "$CONFENGE_SEARXNG_URL" \
  --service reajuste_14133

python3 -m scripts.decision_unit_intelligence batch worker --loop --max-jobs 100
python3 -m scripts.decision_unit_intelligence batch progress --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch inspect --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch failures --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch retry --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch resume --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch cancel --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch publish --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch export-contacts \
  --cohort COHORT_ID \
  --out output/contact-discovery/contacts.jsonl \
  --report output/contact-discovery/contact-projection-report.json
python3 -m scripts.decision_unit_intelligence batch kill-switch --enable --reason pause --actor ops
```

Outputs live under `output/contact-discovery/` (gitignored).
A snapshot is approved only when the denominator closes, every account is
terminal or a nominal blocker, hashes reconcile, and there are no duplicates.

429 / timeout / budget / source-block keep their reason codes. They never
become “sem contato encontrado”.

Each v2 job output also carries one enrichment terminal:

- `EMAIL_ROUTE_READY`: at least one controlled-eligible public route exists and
  exactly one is ranked `preferred_initial`;
- `NO_PUBLIC_EMAIL_FOUND`: the configured public waterfall completed without an
  eligible route;
- `BLOCKED_WITH_REASON`: search was disabled, a provider/source failed, policy
  blocked the run, or another factual blocker prevented a complete negative.

`export-contacts` verifies job/account IDs and output hashes before writing a
derived bridge JSONL. By default it refuses an incomplete denominator.
`--allow-partial` is only for observable incremental feed refreshes and never
counts as full-population evidence.
