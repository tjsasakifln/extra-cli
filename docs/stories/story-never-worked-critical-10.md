# Story: Never-worked critical issues (P2 fill after unused P0/P1)

**Status:** InProgress
**Branch:** `feat/never-worked-critical-10`
**Base:** `origin/main` at `d8bb521e`
**Capability slices:** quality/truth, complementary-source lake, municipal public portals

## Goal

Ship in-repo acceptance criteria for the ten highest-criticality **never-worked**
open issues after the 2026-08-15 filter. No unused P0/P1 survived (P1s #347
#350 #281 #285 #301 #305 and live/VALIDATE issues already have merged work).
The locked set is P2 fill:

1. #351 — PNCP live probe must use a legal `tamanhoPagina`
2. #349 — golden path must not label freshness `never` as `stale`
3. #33 — list schema-blocked suite modules and fix one view baseline gap
4. #265 — map Licitações-e public surface (or BLOCKED/NOT_APPLICABLE)
5. #250 — persist official ARP/IRP into the canonical lake path
6. #253 — inventory and collect Dados Abertos SC licitation resources
7. #266 — MIDES BigQuery query with explicit budget and missing-cred BLOCKED
8. #257 — Betha Atende public tenders adapter
9. #258 — IPM public portal adapter (canonical name, not IPAM mix-up)
10. #259 — Betha e-Gov adapter distinct from Atende

GitHub issue bodies are authoritative. PRs may reference an issue; they must
not auto-close when residual live/host ACs remain.

## Scope

### IN

- In-repo contracts, fixtures, CLI entry points and tests for the ten issues
- Registry + `crawl()`/`transform()` for newly registered sources
- Honest residual notes for live smoke / VPS / national recall

### OUT

- Already-worked P0 #372, DUI slices, waves 1–3, factory-spine republish
- New adapters still `state:blocked` on #346 VALIDATE (#252 #254 #255 #260 #261 #331–#335)
- Greenfield marketplaces #262 #263 #264 (lower 4th-key rank)
- `LOCAL_READY` / `VPS_OPERATIONAL` / 95% / `CI_GREEN` seals without exact HEAD checks
- Protocol/AIOX/hook edits

## Acceptance (implementable in-repo)

See each GitHub issue. Residual live criteria stay open on the issue.

## Risks

- Full-suite CI may fail for pre-existing main issues; do not weaken skips.
- Reviewability: split PRs by capability (≤60 files, ≤10k lines).
