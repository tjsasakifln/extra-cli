# Engineering data release candidate v2

CAMPAIGN_ID: `EXTRA-ENGINEERING-DATA-RELEASE-CANDIDATE-02`

Branch: `release/engineering-data-v2-20260905`

Base: `origin/main` `96f1bea8fa5f2a44d9563943f9875b350da3ccc4`

This is a branch/PR-only code candidate. It does not authorize merge, deploy,
production migration/backfill, refresh, feed, contact discovery, crawl or send.

## Minimal flow

`official structural facts -> persisted engineering class -> lifecycle -> supplier/org profiles -> SELECT-only commercial view`

The view exposes only `CONTRACT_SIGNED` and `CONTRACT_PUBLISHED` in its
`event_type` column. It contains no pre-signature result table, mapper, ingest
CLI, migration, join or output. #545, #559 and #568 remain excluded under the
fail-closed correction in #554.

## Included source patches

| source | issue | donor commit | stable patch-id | v2 migration |
|---|---:|---|---|---:|
| #555 | #546 | `ecd59e84443c` | `f50ccf8bc6c4` | 108 |
| #557 | #552 | `d76bf99acb18`, `1a0b99a64dae` | `585109ee7b31`, `7b28cd7309a2` | 109 |
| #558 | #544 | `2705cc64719c` | `705e88774246` | 110 |
| #560 | #548 | `446702d7d722`, `ce24b1abcf49` | `71101b2f394b`, `ed39d6319ee2` | 111 |
| #556 | #549 | `c8c590734a27` | `eee14c466086` | 112 |
| #561 | #547 | `2c94c5a82029` | `8b2ffa498be7` | 113 |
| #562 | #551 | `c16ea7301fb3` | `3f5dd1320048` | 114 |
| #563 | #550 | `78f8e172f45e` | `f974ce856213` | 115 |
| v2 | #553/#554 | local contemporary port | candidate | 116 + freshness code |

Shared structural fixes `09943f6abb38` (`9868fc1833f0`) and
`0afb347d2c66` (`db9891ba664d`) were applied once. No source branch stack was
cherry-picked wholesale.

## Architecture invariants

- `contract_engineering_class` is the sole classification authority; consumers
  do not duplicate engineering regex.
- Terminal lifecycle is visible and maps to `NOT_ACTIONABLE`.
- Supplier contact is cadastral data with source/timestamp provenance, never a
  decision-maker claim.
- `confenge_commercial_read_v1` is `NOLOGIN`, read-only and receives no
  credential in code.
- `--live` freshness forces durable production resolution and a stable evidence
  path; wrong cwd/release-tree evidence cannot silently replace it.
- PNCP live is not called by this candidate. All downstream reads target
  persisted Data Lake state.
