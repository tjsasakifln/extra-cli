# CONFENGE-EXTRA-LIVE-INBOUND-TRUTH-02 — baseline

Measured from isolated worktree `feat/live-inbound-truth-02` on `origin/main` `4bbb825c5052558fec495c9528e5fa5a6a2e8416`.

The user checkout `feat/extra-023-full-suite-gate` @ `7d7cba80` was not reset, cleaned, or stashed.

## Git

| Field | Value |
|---|---|
| origin/main | `4bbb825c5052558fec495c9528e5fa5a6a2e8416` |
| Worktree | `.worktrees/live-inbound-truth-02` |
| Branch | `feat/live-inbound-truth-02` |
| PR #413 files | untouched (empty diff vs origin/main) |

## Facts already accepted (not rediscovered)

| Fact | Class |
|---|---|
| National 3y backfill | `BACKFILL_COMPLETO` (37/37 windows) |
| Lake `COUNT(*)` | 4 573 257 (`LIVE_PROVEN` 2026-08-17) |
| Incremental 2026-08-17 | inserted 261 then **failed** `source_population_drift` 44515→44517 |
| Incremental healthy? | **no** — not `INCREMENTAL_HEALTHY` |
| Market Answer SC | already produced from official lake (closeout) |
| `public_read_v1` | relation absent on host |
| #415 semantic columns | `unidade`, `quantidade`, `regime`, `modalidade`, `valor_semantic` **absent** |
| #302 persist tables | absent; national gate unchanged |

## Credentials (presence only)

| Item | State |
|---|---|
| Netcup SSH identity | PRESENTE |
| `LOCAL_DATALAKE_DSN` on VPS | PRESENTE |
| Laptop env DSN | AUSENTE |
| Tunnel used | SSH remote SELECT; no DSN copied to laptop |
