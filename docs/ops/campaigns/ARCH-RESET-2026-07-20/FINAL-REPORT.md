# FINAL-REPORT — ARCH-RESET-2026-07-20

**Campaign verdict:** `PARTIAL_WITH_BLOCKERS` (human merge queue)  
**Main baseline:** `d6d9e1984e348d64a669546613e192e4ebf610cd`

## Architecture decision

Keep **modular monolith**, local-first, PostgreSQL 16, CLI/Make.  
Single product weekly pipeline: **`make extra-weekly`**.  
OSS adopted only when proven; most external recommendations rejected or deferred.

## OSS scoreboard

| Component | Decision |
|-----------|----------|
| OCDS | ADOPT_AS_REFERENCE |
| Quality contract | ADOPT_PYTHON_SQL_NATIVE |
| dbt snapshots | REJECTED_SPIKE |
| Soda dual path | REJECT now |
| Splink | REJECTED_SPIKE_FOR_NOW |
| PyMuPDF | AGPL gate — not adopted |
| XlsxWriter / fpdf2 | REFERENCE_ONLY — keep openpyxl+ReportLab |
| rule-engine | REJECT now — reuse PR #52 |

## Campaign draft PRs (open)

| PR | Role |
|----|------|
| #54 | Baseline + disposition + ADR-023 |
| #55 | Characterization tests |
| #56 | Entrypoint classify + verify |
| #57 | OCDS spike |
| #58 | Quality spike |
| #59 | Live weekly proof + #52 eval |
| #60 | Spikes E/G/H/J |

## Existing product PRs

| PR | Disposition |
|----|-------------|
| #52 | MERGE_CANDIDATE (decision loop) |
| #53 | REBASE_AND_REDUCE (ledger) |
| #48–#51 | KEEP_DRAFT / SUPERSEDE (CTO stack) |

## Live proof summary

- Live cycle `weekly-20260720T123303Z-da1515c9a6` exit **0**, 1 opportunity, contracts degraded (429/503).  
- Human accept: PENDING_HUMAN.  
- No LOCAL_READY / 95% claims.

## Human merge order

1. #54 → #55 → #56  
2. #57 · #58 · #60 (parallel)  
3. #59  
4. #52 after suite honesty  
5. thin #53  
6. cleanup later  

## Residual blockers

- Draft PRs not merged to main  
- Full suite global debt  
- Coverage still not 95%  
- Contracts source health degraded  
- Docs on main still pre-campaign until merges
