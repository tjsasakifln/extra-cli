# FINAL-REPORT — CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01

**Generated (UTC):** 2026-07-30T04:30:00Z  
**Closeout posture:** fail-closed / skeptic-reconciled

## Terminal status (§23) — single truth

| Field | Value |
|-------|--------|
| **status** | `BLOCKED` |
| **substatus** | `BLOCKED_PENDING_HUMAN_ACCEPTANCE` **and** residual technical debt (see below) |
| **scope_delivery** | `BLOCKED_SCOPE_UNDERDELIVERED` |
| **handoff_state** | `READY_FOR_TIAGO_REVIEW` (calibration package only) |
| **commercial_release_ready** | `false` |
| **PASS_ACTIVATION** | **NOT claimed** (removed; was contradictory closeout language) |

### Residual technical findings (skeptic 2026-07-30)

| Finding | Status after remediation PR |
|---------|------------------------------|
| Top10 gate accepted sector-only (no official RFB cadastro) | **Fixed in code** (`top10_gate.py` + pipeline). Retrospective on VPS Top20: **FAIL** (`official_registry_failures=10`) |
| Dossiers with CNAE/situação/registry=`NOT_AVAILABLE` while top10_ok=true | **Explained + fixed:** leads lacked registry surface; gate now requires official source + non-null cadastro |
| Holdout §8.2 (≥10 near-cut + ≥10 excluded) missing from package | **Added** `holdout-review.{json,csv,md}` under `review-package/` and `vps-live/package/` |
| FINAL-REPORT claimed PASS_ACTIVATION / coverage 1.0 as official | **This rewrite** — official ≈ 0.029 |
| acceptance-matrix stale (`vps_integrated_cycle=NOT_DONE`) | **Reconciled** after PR #178 |
| Campaign PR budget max 2 | **Exceeded** (#172 A, #174 B, #175 honesty, #178 VPS evidence, + this remediation). Documented; no further cosmetic PRs |

## Delivery chain (facts)

| Step | Result |
|------|--------|
| Pre-campaign PR #171 | Merged `e39a75f3` (not counted in campaign budget) |
| PR A capability #172 | Squash → `7243b87f` |
| PR B closeout #174 | → `70d904ef` |
| Honesty fix #175 (3rd campaign PR) | → `7ef1fc1d` official vs supplier coverage split |
| VPS evidence #178 (4th campaign PR) | → `75cf6df0` on main |
| PR #133 | Untouched draft |
| Soak non-interference | **PASS** (local post-merge + VPS dual cycle) |

## VPS live (OBJECTIVE §16) — executed

| Metric | Value |
|--------|--------|
| Deploy SHA | `7ef1fc1d` (no soak timer restart) |
| Evidence merge SHA | `75cf6df0` (#178) |
| Source | `pncp_datalake` RO (unix socket) |
| State | `confenge_commercial_activation` isolated |
| Contracts | **4 467 364** |
| Candidates | **22 882** |
| Leads | **20** |
| Run1 | `cl-20260730T023737Z-c6f5d5d2` |
| Run2 | `cl-20260730T024151Z-da169885` |
| Top20 idempotent | **true** |
| Top10 sector | all `CONFIRMED_ENGINEERING` |
| Top10 **official cadastro** (retrospective §8.1) | **FAIL** — 10/10 missing RFB resolution (dossiers: CNAE/situação/registry NOT_AVAILABLE) |
| official_registry_coverage | **0.0292** |
| supplier_registry_coverage | **1.0** (fallback-labeled) |
| Dossiers / kits | 20 / 5 under `vps-live/package/` |
| Holdout | near_cut≥10 + excluded≥10 under `vps-live/package/holdout-review.*` |
| Soak NI | **PASS** |
| Terminal reason (machine at run time) | `BLOCKED_INSUFFICIENT_HUMAN_LABELS` (pre-gate-fix code) |
| Terminal reason (post-gate-fix expectation) | `FAIL_TOP10_VALIDITY` until official RFB bulk lifts Top10 cadastro |

Evidence root: `artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/vps-live/`

## Registry honesty

- **Official (RFB-authority only):** ~0.029 (OpenCNPJ public cadastral markers).
- **Operational supplier row presence:** 1.0 via MinhaReceita/BrasilAPI **fallback** labels — **not** claimed as official.
- Redistributor fallback **must not** inflate `official_registry_coverage` to 1.0 (enforced since #175).

## What is still blocked (honest)

1. **Official RFB bulk** so Top10 can pass `evaluate_top10_gate` (cadastro oficial resolvido).  
2. **Tiago** human labels / acceptance (sole commercial ACCEPTED authority).  
3. **DOD §2.7** formal accepts: **0** via controller → `BLOCKED_SCOPE_UNDERDELIVERED`.  
4. **PR budget overage** already incurred; remediation continues only for skeptic-blocking defects.

## Non-claims

- `PASS` commercial release  
- `PASS_ACTIVATION`  
- `VPS_OPERATIONAL` / `LOCAL_READY` / `PROJECT_DONE`  
- `official_registry_coverage = 1.0`  
- precision@k without human labels  
- auto-send  
- 7-day soak completion  
- that pre-remediation `top10_gate.ok=true` satisfied §8.1

## How Tiago reviews (calibration, not release)

Package: `artifacts/.../vps-live/package/`

1. `TIAGO-REVIEW.md`  
2. `top20-dossiers/` + `top5-outreach-kits/` (manual copy only)  
3. `holdout-review.json` / `.csv` (near-cut + excluded; labels empty)  
4. `user-acceptance.template.json` → only Tiago may set `ACCEPTED`  
5. Expect commercial release to remain blocked until official Top10 cadastro **and** human accept

## Reproduce cycle

```bash
make confenge-commercial-cycle
```

Post-remediation code path fails Top10 closed when cadastro is not official RFB.

## DOD posture

- No bulk promotion.  
- `dod-delta.json`: accepted_count=0, status=`BLOCKED_SCOPE_UNDERDELIVERED`.  
- Human-gated CONFENGE_COMMERCIAL_READY checkboxes remain open.
