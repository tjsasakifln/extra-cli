# Coverage scale M2 — N more entities with provenance

**Story:** `ROI-cand-coverage-scale-m2-more-entities`  
**Date:** 2026-07-17  
**Baseline M2:** 5 / 1093  
**After scale:** **81 / 1093 (7.41%)**  
**Delta:** +76 entities  
**Claims 95%?** **NO**

## AC

| AC | Result |
|----|--------|
| M2 numerator increases by N>0 | **MET** — 5 → 81 (+76) |
| No 95% claim | **MET** — 7.41% |
| commercial_signal separate | **MET** — still kind=commercial_signal |

## Method

`promote_from_crawl_artifacts(source=pncp, limit=200, sla_hours=24, persist=True)`  
Provenance from crawl evidence.json (run_id, raw_uri, raw_sha256, record ids, recon).

## Non-claims

- NOT 95% operational coverage
- NOT historical_contracts coverage claim
- NOT PRE_VPS / LOCAL_RESILIENCE READY
