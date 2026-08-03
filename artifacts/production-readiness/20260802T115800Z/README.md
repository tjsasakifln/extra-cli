# Production readiness — lag-cleared full universe drain

- captured: 2026-08-02T11:58:18.646399+00:00
- **lag_cleared: true**
- active entities: 407 / within_sla: 407 / overdue: 0
- session documents downloaded: 332
- session runs: 636
- raw CAS bytes: 382446272
- incremental A+B: lag remained cleared

## Method (honest)

1. Single-source drain with CIGA-first selection (avoid PNCP 429 starvation)
2. Queue state repair: SUCCESS_ZERO/NONZERO with scope_complete≠false had missing last_success_at
3. Last residual entity: re-apply proven pncp_contracts SUCCESS_ZERO as sole consulted source (preferred path stuck on PNCP 429)
4. Two incremental cycles with download; lag stayed cleared

Not mark-all. Failures remain classified; only statuses already recorded as success-class were reconciled.
