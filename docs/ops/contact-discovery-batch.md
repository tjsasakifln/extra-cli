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
  --existing-contacts /var/lib/extra-consultoria/output/RUN_A/05_bridge_inputs/contacts.jsonl \
  --existing-contacts /var/lib/extra-consultoria/output/RUN_B/05_bridge_inputs/contacts.jsonl \
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

`--existing-contacts` is repeatable. Enqueue resolves each file to an absolute
path, records its SHA-256 and size in the immutable cohort/job contract, and
binds the hashes into `input_evidence_version`. The worker verifies the snapshot
before replaying existing account-linked routes as tier 0; a missing/changed
file is a factual `BLOCKED_WITH_REASON`, never a silent miss. Public discovery
is spent only when the reconciled evidence has no controlled-eligible route.

The next tier consults the locally activated, versioned Receita Federal
company-registry release by exact CNPJ. A corporate-domain e-mail from that row
is a company route, but never evidence of a person or department. Public
freemail remains stored and is eligible only when the active controlled-email
policy can also prove its public company association (for example, publication
on the resolved official site); the batch does not bypass the frozen policy. If
no official release is active, the attempt records
`OFFICIAL_REGISTRY_UNAVAILABLE`; a no-route result remains
`BLOCKED_WITH_REASON` while website/document/public-search tiers still run and
may independently produce `EMAIL_ROUTE_READY`.

The number recorded before implementation is a comparison baseline, not a
runtime cap. A canonical population enqueue binds `population_count`,
`population_hash`, `population_as_of`, target-fit mode, and target-fit/sector
classifier SHAs into cohort metadata. The final projection closes only when the
population count, durable job denominator, terminal projection count, and
unique terminal account count are equal. A population that grows between the
baseline and the run is processed in full; the older baseline is reconciled as
a separate before/after slice.

The contact-discovery denominator includes every current `TARGET_CONFIRMED`
account and records its sector class. It does not discard an account merely
because the sector dimension currently says `NON_CONSTRUCTION` or
`SECTOR_INSUFFICIENT_EVIDENCE`. That broader reachability ledger does not relax
the independent construction-membership gate used by the authoritative feed
and send-readiness policy.

The shipped systemd worker loads the canonical production environment from
`/opt/extra-consultoria/.env` (plus the optional crawler/collector overrides),
so its DSN and public-search endpoint match the manually verified CLI run.
