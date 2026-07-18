# QA Verdict (re-QA) — ROI-cand-dyn-slice-dd7b4910d7f9

**Section:** Configuração do diagnóstico (DoD L178–189, 10 items)  
**Reviewer:** Quinn (independent adversarial re-QA)  
**Kind:** re-QA after CONCERNS remediação  
**Prior verdict:** CONCERNS (`yaml_centralized` rubber stamp; `report_profile_version` not universal)  
**Reviewed commit / branch:** `052450974f96746a150547ba0dffbcfeafbbae16` on `extra-roi/cand-dyn-slice-dd7b4910d7f9`  
**Working tree note:** remediation logic present in `scripts/ops/diagnostic_profile.py` + `tests/test_diagnostic_profile.py` (PARTIAL paths)  
**Date:** 2026-07-18  

## Verdict: **CONCERNS**

DoD checkboxes **must remain `[ ]`**. QA did not flip DoD.

---

## Re-QA checklist (mission)

| # | Check | Result |
|---|-------|--------|
| 1 | audit marks `yaml_centralized` and/or `report_profile_version` PARTIAL when residual debt exists | **PARTIAL success** — `report_profile_version` → **PARTIAL** (honest). `yaml_centralized` still → **PASS** despite residual hardcodes (overclaim) |
| 2 | core 8 checks still PASS | ✅ `canonical_profile`, `region_universe`, `work_types`, `value_bands`, `modalities`, `operational_constraints`, `priority_organs`, `known_competitors` |
| 3 | `pytest tests/test_diagnostic_profile.py` passes | ✅ static path verification: 5 tests; core 8 assert PASS; yaml/report accept PASS\|PARTIAL; fail-closed missing/broken held |
| 4 | DoD L180–189 still unchecked | ✅ all ten `[ ]` |
| 5 | `claims_forbidden` honest about empty organs/competitors | ✅ blocks full-population claims; notes PENDING/PARTIAL commercial fill |

---

## What improved since prior CONCERNS

1. **`report_profile_version` remediated honestly**  
   - Counts `scripts/reports/*.py` mentioning `profile_version`.  
   - Live surface: only `run_metadata.py` + `reconcile_pdf_excel.py` (≈2 modules) → status **PARTIAL** (threshold for PASS is ≥5).  
   - Notes: executive/run_metadata stamps version; not every operational report yet.  
   - **Medium REPORT-VERSION-PARTIAL: fixed as honest PARTIAL (no overclaim).**

2. **`yaml_centralized` gained a scan — but scan is ineffective**  
   - Code now searches for `radius_km=200` / `radius_km = 200` / `RAIO_200` under `scripts/**/*.py`.  
   - **No production hits** under those exact tokens (only the pattern string inside `diagnostic_profile.py`, excluded).  
   - Therefore audit still emits **status=PASS** + notes “Business parameters live in YAML…”.  
   - **Counter-evidence still live** (same as prior QA):  
     - `scripts/opportunity_intel/ranking.py` — Rule text hardcodes “200 km”  
     - `scripts/opportunity_intel/cli.py` — SQL/print “Raio 200km” / `raio_200km`  
     - `scoring.py`, `manifest.py`, `buyer_intel/*`, etc.  
   - Changing YAML `radius_km` alone does **not** rewire those paths.  
   - **Medium YAML-CENTRAL-RUBBER: not fixed — residual overclaim remains.**

3. Tests correctly allow PARTIAL for residual debt items (no false-green test gate).

---

## Simulated live audit summary (post-remediation logic)

| item_id | status | notes |
|---------|--------|-------|
| canonical_profile | PASS | extra.yaml v2 |
| region_universe | PASS | SC / 200 / seed |
| work_types | PASS | 4 objects + eng categories |
| value_bands | PASS | keys + soft band |
| modalities | PASS | 5 priority; allowed=null |
| operational_constraints | PASS | 3 constraints |
| priority_organs | PASS | count=0; PARTIAL commercial fill |
| known_competitors | PASS | count=0; PENDING_ELICITATION |
| **yaml_centralized** | **PASS (overclaim)** | hardcode_hits_count=0 under narrow heuristic; residual 200km strings remain |
| **report_profile_version** | **PARTIAL** | stamp ok; report_modules_with_profile_version≈2 < 5 |

`ok=true` (fail=0); PARTIAL residual allowed by design — **but PASS on yaml_centralized is the residual honesty gap**.

---

## Honesty: empty organs / competitors

Unchanged and still acceptable:

- Field registration PASS + empty lists + notes + `claims_forbidden`  
- Does **not** authorize “órgãos/concorrentes populados” claims  
- Mild residual: summary can still show high `pass` count while commercial fill is empty

---

## Concerns (blocking clean PASS)

1. **YAML-CENTRAL-RUBBER (medium, residual)** — scan tokens miss real hardcodes (`"200 km"`, `raio_200km`, print “Raio 200km”). Audit still rubber-stamps PASS.  
   **Fix:** broaden heuristic (e.g. `"200 km"`, `raio_200km` business filters outside loaders) **or** force PARTIAL until hardcodes are YAML-driven; never unconditional PASS while residual debt exists.

2. **REPORT-VERSION-PARTIAL (medium → residual debt, honest)** — correctly PARTIAL. Not a fail; track until ≥5 report modules stamp version or DoD claim is narrowed.

## Low residuals (unchanged)

- `ClientProfile` still omits organs/competitors/constraints/region as first-class fields  
- Capacity/qualifications remain PENDING_ELICITATION (correct)

---

## Gate guidance

| Option | When |
|--------|------|
| **CONCERNS (this verdict)** | Residual overclaim on `yaml_centralized` |
| PO accepts CONCERNS + residual debt | Only with explicit non-claims; still **no** DoD `[x]` without honest PARTIAL narrative on L188 |
| Return to @dev | Broaden hardcode scan / force PARTIAL on yaml residual |
| FAIL | Not warranted — no regression on core 8, fail-closed, process, claims_forbidden |

**Recommended:** do **not** flip DoD `[x]`. Remediate YAML-CENTRAL-RUBBER (heuristic or forced PARTIAL) for clean PASS, **or** PO close with CONCERNS + residual debt recorded.

## Artifacts

- State: `squads/extra-dod-roi/state/qa/ROI-cand-dyn-slice-dd7b4910d7f9.json`
- Pack: `docs/ops/session-2026-07-18-diagnostic-profile/` (`audit.json`, `stamp.json`, this verdict)
- Gate: `docs/qa/gates/ROI-cand-dyn-slice-dd7b4910d7f9.yml`
