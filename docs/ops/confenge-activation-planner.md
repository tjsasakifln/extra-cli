# CONFENGE commercial activation planner

## Purpose

Maximize expected commercial revenue per hour of human intervention.

The national B2G construction universe (~tens of thousands of companies) is a
**monitored reservoir**, not a backlog. Only accounts with an objective reason
to act **now** enter the expensive path and Warmbly working set.

```text
DATALAKE → universe → activation scan (cheap)
  → hot set (capacity-aware)
  → account intelligence + contacts (expensive)
  → confenge.outreach.v1 → Warmbly
```

## Activation states (planning only — not CRM)

| State | Meaning |
|-------|---------|
| `WATCH` | In reservoir; no current commercial reason for expensive work |
| `RESEARCH_REQUIRED` | Signal warrants deeper research before outreach |
| `ACTIONABLE_NOW` | Sustained reason to enrich and potentially work in Warmbly |
| `SUPPRESSED` | Dominant human block (e.g. DNC) |

These do **not** replace `commercial_state` / Decision & Outcome Memory.

## Policy

Versioned config:

`config/commercial/confenge_activation_policy.yaml`

- Trigger catalog with observational language only
- Score weights (sum 100) for **ordering**, never purchase probability
- Capacity: `sends_per_hour × send_window_hours × planning_horizon_days × research_buffer`
- `max_hot_set` is a safety cap, not the commercial strategy

## Commands

### Plan only (cheap)

```bash
python -m scripts.confenge_activation plan \
  --universe path/to/confenge-universe-v1.jsonl \
  --out output/activation_cycle \
  --as-of 2026-08-08 \
  --prior output/activation_cycle/activation-projections.jsonl
```

### Full pipeline (production path)

```bash
python -m scripts.confenge_outreach_pipeline run \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --out output/confenge_outreach \
  --as-of 2026-08-08 \
  --use-activation-planner
```

Smoke / diverse sample (not a commercial shortlist strategy):

```bash
python -m scripts.confenge_outreach_pipeline run \
  --csv tests/fixtures/confenge_universe/contracts_sample.csv \
  --out /tmp/confenge_smoke \
  --force-sample-mode \
  --limit-downstream 20 \
  --skip-contacts
```

### Recurring production cycle

Production uses the canonical pipeline plus its existing atomic publisher. It does not copy a second flat feed or treat a repeated hash as success:

```bash
python -m scripts.ops.confenge_feed_cycle \
  --output-root /var/lib/extra-consultoria/output \
  --durable-contacts /var/lib/extra-consultoria/output/contact-discovery/current/contacts.jsonl \
  --publish-dir /opt/confenge-plane/feed-www \
  --max-age-hours 24
```

Install and enable `extra-confenge-feed-cycle.timer` (12-hour cadence, at 01:20 and 13:20 local time) and `extra-confenge-feed-monitor.timer` (hourly validation). The feed schedule deliberately starts after the PNCP 00:00/12:00 source windows have time to close; an in-flight source window remains a fail-closed publication blocker. Configure the non-secret paths from `deploy/systemd/confenge-feed.env.example`. The service account needs write access to `/var/lib/extra-consultoria` and the publication root. Warmbly reads the manifest from the HTTP document root that mounts the atomic `current` release; the `current` symlink changes only after the full manifest, every chunk hash, full target-fit coverage, PNCP freshness and both feed timestamps pass validation.

The durable state is `/var/lib/extra-consultoria/confenge-feed/publication-state.json`. It preserves the last successful publication while recording the latest generation and monitor result, duration, snapshot, watermark, lead/contact totals, deltas, route classes and provenance sources. Alerts append to `/var/lib/extra-consultoria/alerts/confenge-feed.jsonl` and trigger the normal systemd `OnFailure` path.

`SAME_SNAPSHOT_NOT_FRESHNESS` exits non-zero and alerts. A green timer that produced no new snapshot is not freshness. A stale, partial or corrupt build is refused and the last valid `current` release remains served.

### Manual atomic publish

After a successful cycle:

```bash
python -m scripts.confenge_activation publish \
  --build-dir output/confenge_outreach/06_warmbly_feed \
  --publish-dir /var/lib/confenge/feeds
```

Warmbly should read `.../current/manifest.json` only after atomic promote.

Validate the public release independently:

```bash
python -m scripts.confenge_activation check-publication \
  --publish-dir /opt/confenge-plane/feed-www \
  --max-age-hours 24
```

## Manifest summary fields

Pipeline reports real cycle numbers (never hard-coded):

- `reservoir_count`
- `activation_counts` (WATCH / RESEARCH_REQUIRED / ACTIONABLE_NOW / SUPPRESSED)
- `hot_set_count`
- `expensive_enrichment_count`
- `feed_count`
- `policy_version`
- `source_watermark`
- `full_scale_universe`

## Deactivations

When an account leaves `ACTIONABLE_NOW`, the feed manifest includes:

```json
"deactivations": [
  {
    "cnpj14": "...",
    "from_state": "ACTIONABLE_NOW",
    "to_state": "WATCH",
    "reason_codes": [],
    "evaluated_at": "...",
    "source_hash": "..."
  }
]
```

Warmbly applies these without clearing DNC / human state.

## Persistence

- JSONL projections under cycle `02_activation/`
- Optional Postgres: migration `070_confenge_activation_projection.sql`
- Projection is recomputable; Decision Memory remains the human ledger

## Invariants

- Never LLM-scan 48k accounts per cycle
- Never treat `limit_downstream` as production commercial strategy
- Never claim legal rights from anniversary windows
- Mega-contract value alone does not dominate score
- Same input + same policy version → same scores/hashes
