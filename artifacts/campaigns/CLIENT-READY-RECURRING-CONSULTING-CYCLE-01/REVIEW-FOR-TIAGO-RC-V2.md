# Review for Tiago — Commercial RC v2

**Classification:** `READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW`  
**Status:** `PENDING_HUMAN` (never auto-ACCEPTED)  
**Artifact:** `client-ready-frozen-rc-v2`  
**run_id:** `live-pack-20260725-030451-7af94c4f`  
**product_rc_sha:** `c17864f681776e7d12df1bd99edb7f4c8f89f4c4`

## What changed vs RC v1 (CHANGES_REQUESTED)

RC v1 remains historically **CHANGES_REQUESTED** (`rc-v1-CHANGES_REQUESTED.json`). It is not overwritten.

| Issue RC v1 | Fix RC v2 |
|-------------|-----------|
| E with sheets, computers, lab exams, fleet | Sector filter → `SUCCESS_ZERO_ENGINEERING_OPPORTUNITIES` (0 non-engineering) |
| C with castration, courses, fuel, karate | C only engineering; 13k+ non-eng excluded |
| A ranked by general purchase volume | A ranked by engineering contracts only |
| D absurd global medians | All panels `INSUFFICIENT_COMPARABLE_DATA` for global heterogeneous values |
| PDF technical dump | Executive PDF (CONFENGE/Extra, 6 pages, PT business language) |
| XLSX raw dump | Dashboard + 8 executive sheets, CNPJ as text, R$ |
| Hash drift / self-hash identity | Reconciled checksums; identity sidecar, no self-hash |

## How to review

1. Open `client-ready-frozen-rc-v2/executive-report.pdf`
2. Open `client-ready-frozen-rc-v2/consulting-pack.xlsx` (Dashboard first)
3. Spot-check A/B/C JSON under pack-v2 if desired
4. Decide: **ACCEPTED** | **REJECTED** | **CHANGES_REQUESTED**

## Non-claims (still honest)

- Capacities (CAT, capital, guarantees) remain **PENDING** — no invented GO
- Zero open engineering editais in frozen evidence is an honest outcome
- No VPS/prod/soak touched; no merge performed by agent
