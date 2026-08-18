# Official-live authority handoff 01

Sanitized campaign report. No secrets, no raw documents, no production write.

## Baseline revalidated

- `origin/main` at start: `54b9b509eddf982a7fa7dae2f6ced713c2c3e34f`
- Landed: `scripts/official_contract_semantics/**` (#428) and `scripts/historical_contract_authority/**` (#430)
- Open PR #413 left untouched
- Issues: #414 closed; #400 closed; #415 remains open (peer-group DoD is larger than this slice)
- `LOCAL_DATALAKE_DSN` / `DATABASE_URL` absent in this environment
- Consumer: web-cfg #83 / PR #118

## What shipped

Additive 1.1 clocks: `event_effective_at`, `source_published_at`, `retrieved_at`, `verified_at`, `source_as_of`.
Operational freshness uses only `verified_at`/`retrieved_at`. An old contractual event re-verified now is not `stale_evidence` and is not rewritten as recent.

`analysis_mode`: `DOCUMENT_CHAIN` | `TIMELINE` | `COMPARATIVE`.
`NOT_APPLICABLE` is allowed only without comparative language and with a document-backed singular insight.
Comparative language reactivates the peer gate. Generic value+term is not a singular insight.

Live window is current and configurable (default last 30 days). PNCP 429 retries and is not cached.

Entry:

```bash
python3 -m scripts.historical_contract_authority --mode official-live \
  --limit 12 --start-date 2026-07-18 --end-date 2026-08-17 \
  --as-of 2026-08-17T12:00:00Z --output <handoff-dir>
```

## Live result

Status: **BLOCKED** (not READY).

- Sources tried: `pncp_consulta_api` (DSN unavailable, recorded as unavailability)
- Window: 2026-07-18 .. 2026-08-17, UF SC, limit 12
- Documents considered: 1; obtained: 2 (listing + page)
- Partial dossier: `242dc2e35e5523e01f64a57cb3058b35` `DATA_HOLD`
- Contract observed: PNCP `08184785000101-2-000459/2026` (GLP / registro de preços, Joinville)
- Reason codes: `HOLD_FOR_DATA`, `missing_singular_insight`
- `publication_authorization=false`, `index_authorization=false`, `production_write=false`, `backfill=false`
- Two canaries: same `BLOCKED` status, same dossier content hash `8054ea40c0b84ca40f51021793f29ff4ae42b48851a8a7e7625177eb72b2ba13`

Rendezvous (atomic, outside git):

`$HOME/.local/share/confenge/handoffs/contract-analysis/official-live-01/`

Contains `BLOCKED.json`, `manifest.json`, `dossiers/<id>.json` (DATA_HOLD), `SHA256SUMS.txt`, `replay.txt`, `README.md`. No `READY.json`.

## Tests

- Focused: 94 passed (`tests/official_contract_semantics/`, `tests/historical_contract_authority/`)
- Broader slice: 135 passed, 1 skipped
- Adversarial: old event + current verify is not stale; old event is not recent; comparative language reactivates peers; missing locator blocks READY; 1.0 still loads; hashes exclude verification clocks

## Residual

The bounded official window verified one SC contract. It has official identity, value and term, but no documentary singularity (aditivo, reajuste, reequilíbrio, prazo material, BDI, medição/glosa). That is not HANDOFF_READY.

Smallest next verifiable step: rerun the same official-live entry on a window that actually contains those documentary families, or with DSN already present. Do not fabricate READY.
