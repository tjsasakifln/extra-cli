# PREFLIGHT — CONFENGE-EXTRA-PRODUCER-CONVERGENCE-02

Fetched 2026-08-20. Work proceeds only on worktree
`.worktrees/producer-convergence-02` branch
`integration/confenge-extra-producer-convergence-02`. Dirty checkout
`feat/public-integrity-producer-436` was not used.

## Observed SHAs

| Ref | SHA | Note |
|---|---|---|
| Cut claimed `origin/main` | `b132582cf31629b328e8483175ad6e08bf4e6f89` | #435 squash merge |
| Current `origin/main` | `cfe14234a08f39a4a288e57f184cb23e758667c2` | #437 squash merge after the cut |
| #437 merge | `cfe14234` | MERGED; 097 occupied |
| #435 | `b132582c` | MERGED; comparables authority |
| #438 HEAD | `origin/campaign/confenge-extra-bofu-evidence-packs-02` | OPEN draft, CI green, 0 review threads |
| #439 HEAD | `origin/feat/public-integrity-producer-436` | OPEN draft, CI green, 0 review threads |
| #413 | OPEN | Untouched |
| Host `.deployed_sha` | `bbc4b6b7db295909d773f5a0e1f3314085a2f26c` | Behind current main; #437 not deployed |

Post-cut unique main commit: only #437. 097 is occupied
(`db/migrations/097_national_coverage.sql` + rollback). This campaign adds
additive `098_national_coverage_consumer_select_only.sql` and does not edit 097.

## Dirty checkout (ignored)

Untracked local copies under the primary checkout (`.campaign/`, `.venv/`,
`artifacts/`, `docs/ops/campaigns/CONFENGE-EXTRA-FIRST-QCO-HANDOFF-01/`,
`output/`, `tests/fixtures/dui/`). Not mixed into this worktree.

## Host `/opt/extra-consultoria`

- alias: `ec-prod` → `root@159.195.18.88:2222`
- hostname: `v2202607385716487230`
- host key: `SHA256:XKxs4y1Wa2MwQzn8YZ8YXOw3haG3B8AH/kmEiYngD0s`
- service user: `extra-consultoria`
- lock `/var/lock/confenge-production-deploy`: absent at preflight
- disk: 127G/503G (27%); memory: 6400/15996 MB
- porcelain lines at preflight: 8 (recorded; deploy will capture a backup first)

## CI

#437 required checks SUCCESS on merge. #438/#439 CI + reviewability SUCCESS
on their source heads. Main push CI for #437 SUCCESS.
