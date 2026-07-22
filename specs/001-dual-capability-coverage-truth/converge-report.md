# Speckit converge — dual-capability-coverage-truth

**Date:** 2026-07-22  
**Base main:** ac81c51 (+ this remediation)

## Codebase vs tasks

| Task | Status | Evidence |
|------|--------|----------|
| T001–T019 engine/spec | Done | dual engine + tests + checklist |
| T020 PR/CI | Done | PR #108 CI green + merge edd7618 |
| T021–T031 fail-closed/matrix/hashes | Done | dual_capability_coverage v1.1+ |
| T032 independent review | Done | v1.1 H1 + v1.2 skeptic + v1.3 re-stamp |
| T033 merge | Done | #108 |
| T034 main reproof | Done | main dual CLI after merges |
| T035 acceptance pack/controller | Done | dod_controller accept + pack 4efe05fc94 |
| T036 DOD ACCEPTED | Done | PR #109 |
| T040–T044 skeptic remediation | Done | #110/#111 + this PR |

## Remaining unbuilt work

Only **operational** (not measurement-engine implementable):

1. Resolve ambiguous CNPJ roots (identity_unresolved → 0)
2. Backfill coverage_evidence for dual 95% gates
3. Optional: activate applicability config beyond draft

## Converge verdict

**CONVERGED** for measurement dual fail-closed + normative "calcula cobertura".  
**NOT** claiming dual 95% operational gates.
