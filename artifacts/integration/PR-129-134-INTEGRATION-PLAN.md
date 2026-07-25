# PR #129–#134 Integration Plan (CTO operational)

**Captured:** 2026-07-25T00:55:01Z  
**Main SHA:** `5d906f631f444dd803e92bb88b7c98972297f8d4`  
**Scope:** risk reduction and controlled integration — no new product features.  
**VPS/soak:** not touched in this workstream (`production_touched` must remain false).

## Merge order (mandatory)

1. **#131** — after slim, adversarial review, full CI green, **human ACCEPTED** by Tiago  
2. **#132** — rebase on new main, full suite green  
3. **#133** — rebase, full suite green, status `EXPERIMENTAL_TECHNICAL_PASS`  
4. **#134** — fix full-suite root cause, rebase, full suite green  

**Do not merge** #129 or #130 separately if absorbed by #131.  
**Do not merge** #121 as parallel architecture (migration 059 collision).

---

## Inventory by PR

### PR #121 — national contracts intelligence architecture
| Field | Value |
|-------|--------|
| Purpose | Draft architecture + migration 059 national intel layers |
| Branch | `campaign/national-contracts-intelligence-architecture-01` |
| Head | `a1c77a0d8aaef83c2f199c8df146da651d683b75` |
| Commits / files | 7 / 75 |
| Migrations | **059** `059_national_contracts_intelligence_layers.sql` — **collides** with main `059_coverage_evidence_canonical_entity_unique.sql` |
| Entrypoints | `scripts/national_intel/*` |
| CI | 8/8 SUCCESS |
| Overlaps | Concepts absorbed into #131 as migration **060** |
| Status recommended | **SUPERSEDED** by #131 |
| Action | After #131 merge: comment + close; extract only unique ideas if any via small PR |
| Merge condition | **Never as-is** (059 collision) |
| Close condition | #131 merged; ideas preserved or explicitly rejected |

### PR #129 — CANONICAL-ENTITY-LINKAGE-01
| Field | Value |
|-------|--------|
| Purpose | Canonical identity + auditable linkage |
| Branch | `campaign/canonical-entity-linkage-01` |
| Head | `bd6d404f77f715898cae6ca9824d315106f40d2c` |
| Commits / files | 5 / 43 |
| Migrations | **061** |
| Modules | `scripts/linkage/*` |
| CI | 8/8 SUCCESS |
| Contained by | **#131** (ancestor + zero missing paths) |
| Status recommended | **DO_NOT_MERGE** — absorbed |
| Action | Close without merge **after** #131 human accept + merge |
| Merge condition | N/A if FULLY_ABSORBED |
| Close condition | Absorption JSON `FULLY_ABSORBED` + #131 on main |

### PR #130 — EXTRA-LIVE-CONSULTING-PACK-01
| Field | Value |
|-------|--------|
| Purpose | Consulting pack A–E on isolated real dump (~4.44M contracts context) |
| Branch | `campaign/extra-live-consulting-pack-01` |
| Head | `6b5bc7678b5447e90b2e9df2de21d07de0fa42d2` |
| Commits / files | 30 / 95 |
| Migrations | **060** |
| Modules | `scripts/ops/live_consulting_pack.py`, national_intel, monthly monitor |
| CI | 8/8 SUCCESS |
| Contained by | **#131** |
| Status recommended | **DO_NOT_MERGE** — absorbed |
| Action | Close without merge after #131 accept+merge |
| Merge condition | N/A if FULLY_ABSORBED |
| Close condition | same as #129 |

### PR #131 — CLIENT-READY integrator (PRIMARY)
| Field | Value |
|-------|--------|
| Purpose | Integrated recurring consulting cycle A–E + linkage + dossiers |
| Branch | `campaign/client-ready-recurring-consulting-cycle-01` |
| Head (pre-slim tip) | `dd20c37d7b92cbe93774f1e7b4b0e53921f4b21c` |
| Commits / files (pre-slim) | 57 / 283 |
| Migrations | **060**, **061** (no 059 collision with main) |
| Contains | #129, #130 (ancestry proven) |
| CI | 8/8 SUCCESS |
| Human acceptance | **PENDING_HUMAN** (`user-acceptance.json`) — agents must not set ACCEPTED |
| Status recommended | Slim + review + gates → **READY_FOR_HUMAN_ACCEPTANCE** |
| Action | Remove heavy generated outputs; policy+gate; CTO review; keep freeze for Tiago |
| Merge condition | Full CI green + BLOCKER/HIGH fixed + Tiago ACCEPTED in user-acceptance.json |
| Close condition | Merged to main |

### PR #132 — Edital technical triage
| Field | Value |
|-------|--------|
| Purpose | Technical triage of editais with real public cases (Laguna/Imbituba) |
| Head | `8f636a504800b4cb4b4236cacff3b4f9ac6fc197` |
| Migrations | none |
| CI | 8/8 SUCCESS (current) |
| Status | Await #131 merge → rebase → re-prove full suite |
| Merge condition | Full suite green on post-#131 main |
| Blocking | await_131_merge |

### PR #133 — Bid submission readiness (experimental)
| Field | Value |
|-------|--------|
| Purpose | Document readiness/compliance pack |
| Head | `a5d0bf47677785cc203d8d8278ca52b3e7067aaa` |
| CI | 8/8 SUCCESS |
| Status | **EXPERIMENTAL** — fictional docs only; never READY_TO_SUBMIT from fiction |
| Merge condition | Full suite + privacy green + experimental label explicit |
| Blocking | await_131_merge; no real authorized client docs in git |

### PR #134 — Budget / BDI audit
| Field | Value |
|-------|--------|
| Purpose | Engineering budget, compositions, BDI audit |
| Head | `af2479056dbec40f35483fb0f7a7fe9e40637dca` |
| CI | **FAILURE** — `Test All (full suite)` |
| Root cause (evidence) | `ModuleNotFoundError: No module named 'hypothesis'` collecting `tests/budget_audit/test_adversarial_property.py` (run 30131433813) |
| Status | **BLOCKED_BY_CI** until hypothesis dep fixed + suite green |
| Merge condition | Full suite green; no legal/professional overclaim |

---

## Branch protection (current)

GitHub API: **main is NOT protected** (HTTP 404).  
Proposal only (no silent admin change): required PR, required status checks (lint, mypy, full suite, resilience, bandit, pip-audit, generated-artifacts-policy), dismiss stale reviews, no force-push, conversation resolution, CODEOWNERS for `db/migrations/**`, `.github/workflows/**`, `scripts/linkage/**`, `scripts/ops/live_consulting_pack.py`.

## Isolation rules

- Do not SSH to VPS, change timers, or touch soak.
- Campaign DSNs limited to localhost ports 5436/5438/5439.
- Fail-closed isolation checks in `scripts/linkage/isolation.py`.

## Machine-readable companion

See `artifacts/integration/PR-129-134-INTEGRATION-MATRIX.json`.
