# CONFENGE-EXTRA-LIVE-INBOUND-TRUTH-02 — evidence

## Frente A — incremental drift

Shipped predicate: `scripts.contracts_truth.classify_population_drift` + `PaginationReconcile.finish` + `evaluate_window_completion` + limited tail pass in `scripts.crawl.run_contracts_90d_pilot`.

Policy (explicit, not a 44515/44517 special case):

- `growth_budget_abs = 8`
- `growth_budget_ratio = 0.01`
- `max_passes = 2`
- `max_seconds = 90`
- `max_page_growth = 1`

Observed host incremental (`pncp-contracts.service` 2026-08-17 06:03–06:29 -03):

| Field | Value |
|---|---|
| window | `20260810_20260817` |
| pages | 90 |
| transformed | 44517 |
| inserted | 261 |
| skipped | 44256 |
| elapsed | 1576.6s |
| old-code decision | `failed` / `source_population_drift:totalRegistros 44515 -> 44517` |
| new classifier on the same totals | `needs_retry` (`monotonic_growth_unproven`, `new_ids_not_seen`, `allows_tail_pass=true`) |
| after a proven tail pass | `converged` |

Controlled live dry-run of the **new** runner (`CONTRACTS_MAX_PAGES=2 --days 1 --dry-run`):

| Field | Value |
|---|---|
| window | `20260816_20260817` |
| first/last `totalRegistros` | 6911 / 6911 |
| drift status | `ok` / `population_stable` |
| window complete | no (`Hit CONTRACTS_MAX_PAGES=2 before total_pages=14`) |
| inserts | 0 (dry-run) |
| incremental status | `failed` (incomplete by cap — not `INCREMENTAL_HEALTHY`) |

Tests: `tests/test_population_drift_convergence.py` plus durability/pilot predicates. 81 passed.

## Frente B / C — official-live analysis export

Live SELECT (VPS, read-only, `uf='SC'`, AEC tokens, editorial tokens first, **not** ordered by `valor_total`): 40 rows, 32 editorial-token hits. Semantic columns still absent.

Command:

```text
python3 -m scripts.public_read_consumers refresh \
  --consumer web-cfg/contract-analysis \
  --out exports/public-read-live/contract-analysis/1.0
```

Two refreshes on the same official snapshot:

| Run | `payload.content_hash` |
|---|---|
| 1 (`generated_at` 18:20Z) | `63614768fc8c3d7e0ecb8da454a9832d8fbc58c0c4bc30dc9fe395a0a1e87595` |
| 2 (`generated_at` 18:21Z) | `63614768fc8c3d7e0ecb8da454a9832d8fbc58c0c4bc30dc9fe395a0a1e87595` |

Manifest (hash excludes `generated_at`): `7437a1cf6abb2c6db156290c98f6eaf3f1d5bf301d585c351e007f7d0156552c`

Export directory: `exports/public-read-live/contract-analysis/1.0/{payload,manifest,lineage,status,snapshot}.json`

| Field | Value |
|---|---|
| `official_live` | true |
| `producer_status` | `OFFICIAL_LIVE` |
| `schema` | `public-read-contract-analysis/1.0` |
| geography / `claim_scope` | SC |
| `claim_authorization` | null |
| `no_index_authorization` | true |
| coverage | 40 HOLD / 0 READY / 0 REJECT / 0 EDITORIAL_REVIEW |
| #415 | `NOT_COMPARABLE` (`live_columns_unavailable`) |
| INDEX / PUBLISHABLE_* | not emitted |

This is an honest `HOLD_FOR_DATA` official-live feed: live rows exist, documents/semantic columns do not. No text was invented. No OCR.

## Classes

| Result | Class |
|---|---|
| Drift classifier + tests | `CODE_PROVEN` |
| Dry-run incremental vs live PNCP | `LIVE_PROVEN` (window incomplete by cap) |
| Host incremental unit 2026-08-17 | `LIVE_PROVEN` failed — **not** `INCREMENTAL_HEALTHY` |
| Official SC SELECT | `LIVE_PROVEN` |
| Consumer export | `OFFICIAL_LIVE` + `HOLD_FOR_DATA` |
| Comparability | `NOT_COMPARABLE` |
| #302 national | unchanged, still open |
| X-Ray / INDEX / nacional_completo | `NO_GO` |
