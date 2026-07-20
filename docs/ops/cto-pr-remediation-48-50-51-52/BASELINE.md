# BASELINE — CTO PR remediation 48/50/51/52

**Captured (UTC):** 2026-07-20T01:46:47Z

## HEADs

| Ref | SHA |
|-----|-----|
| origin/main | `d6d9e1984e348d64a669546613e192e4ebf610cd` |
| PR #48 head | `423743fcebb8b3b9141b51b939c5ecdcc6708d35` |
| PR #50 head | `28c2cfb720f3b42f8bb8b8d5df423b918bf1919c` |
| PR #51 head | `f707e7b7d42d50e224b9511e033c63bf30905868` |
| PR #52 head | `dd2d501496e30409c8d672a9925e04e94c70c40b` |

## DoD checkbox count (main-ish / current #48 tree)

- Pattern: 308 checked / 1047 unchecked / 1355 total (~22.7%) — measured earlier on goal branch; re-verify before seal claims.

## Preflight

- grok version: **0.2.106 (stable)** — supports headless subagents, `--sandbox strict`, `--permission-mode dontAsk`, `--no-auto-update`
- grok inspect: discovers AGENTS.md + AIOX rules/hooks
- extra-dod-roi: status/scan/audit/rank-next operational
- Ranking[0] at cycle-1: `cand-dyn-slice:cb906bb58392`
- Full suite CI: **SKIPPED** on PRs (workflow_dispatch only) — not claimed green

## Overlap

| Area | PRs |
|------|-----|
| scripts/cto/** | #48, #50, #51 (chain) |
| decision loop | #52 only (main base) |
| canary-proof.md | #50/#51 historical |

## Test baseline notes

- #48 CTO suite: **146 passed** after security remediation
- #52 decision loop: **41 passed**
- Full suite: not green globally (preexisting debt)
