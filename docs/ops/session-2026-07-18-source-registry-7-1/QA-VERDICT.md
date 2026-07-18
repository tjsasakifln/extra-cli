# QA Verdict — DoD §7.1 (first 8 items)

| Field | Value |
|-------|-------|
| **Story** | `ROI-cand-dyn-slice-6c08d1a1d808` |
| **Scope** | DoD §7.1 Registry de fontes — **only first 8 items** |
| **Reviewer** | Quinn (@qa) — independent, not implementer |
| **Date** | 2026-07-18 |
| **Reviewed HEAD (working tree)** | uncommitted changes on `scripts/crawl/registry.py`, `DOD.md`, `tests/test_source_registry_dod71.py` + evidence dir |
| **Overall verdict** | **CONCERNS** |

---

## Commands re-run (this session)

```bash
python3 -m scripts.crawl.registry --validate --json
# → ok=true, n_sources=11, active=3, implemented_not_proven=8, missing_required=[]
# EXIT=0

python3 -m pytest tests/test_source_registry_dod71.py -q --no-cov -o addopts=
# → 5 passed in ~1.3s
# EXIT=0
```

Session artifacts also present: `validation.json`, `pytest.log` (5 passed), `full-export.json`, `registry-export.json`, `MANIFEST.md`.

---

## Per-item matrix (DoD §7.1 first 8)

| # | DoD item | Status | Evidence | Notes |
|---|----------|--------|----------|-------|
| 1 | Existe registry canônico de fontes | **DONE** | `scripts/crawl/registry.py` as single module; CLI `--validate` / `--export`; `validate_registry()` returns structured result | Eliminates multi-list drift claim for this slice |
| 2 | Cada fonte possui identificador estável | **DONE** | `SourceInfo.name` unique across 11 sources; export field `id` | Aliases map via `_ALIAS_MAP`; no duplicate ids |
| 3 | Cada fonte possui URL ou endpoint canônico | **PARTIAL** | All 11 have non-empty `canonical_url`; primaries are real HTTPS endpoints | **`transparencia`** uses pseudo-URL `https:// (portal por ente — batch detect)` — not a fetchable endpoint; validator only rejects empty/`unknown` |
| 4 | Cada fonte informa capacidades suportadas | **DONE** | Every source has non-empty `capabilities` list (typed `SourceCapability`) | Empty-capabilities falsify: **none present** |
| 5 | Cada fonte informa cobertura geográfica | **DONE** | Every source has non-empty `geo_coverage` via `_ENRICHMENT` / defaults | Values are descriptive strings (BR/SC/municipal) |
| 6 | Cada fonte informa necessidade de credenciais | **DONE** | `needs_credentials` bool property + `credential_names` / `credentials` | e.g. `dom_sc`, `doe_sc`, `mides_bigquery` → true; public sources → false |
| 7 | Cada fonte informa limites de paginação conhecidos | **DONE** | Field `pagination_limits` on all; **primaries** non-`unknown` | Residual: `pcp`, `compras_gov`, `doe_sc` still `unknown` (complementary — allowed by validator policy) |
| 8 | Cada fonte informa rate limits conhecidos | **DONE** | Field `rate_limits` on all; **primaries** non-`unknown` | Residual: `pcp`, `compras_gov`, `tce_sc` still `unknown` (complementary) |

**Out of scope (not scored here):** retry, backoff, status operacional checkbox, last validation, blockers, role checkbox, active-vs-crawler-exists checkbox (items 9+). Those remain open in `DOD.md` as expected.

---

## Falsification probes (required)

| Probe | Result | Detail |
|-------|--------|--------|
| **Active without URL** | **PASS (cannot falsify green)** | No source with `operational_status=="active"` lacks URL. Simulation: `operational_validated=True` + empty `canonical_url` → `implemented_not_proven` (requires **both** validated and URL) |
| **Empty capabilities** | **PASS (cannot falsify green)** | Zero sources with empty `capabilities`. `validate_registry` would gap on empty list |
| **Crawler-exists (`module`) as active without `operational_validated`** | **PASS (cannot falsify green)** | 8 sources have `module` + `operational_validated=False` and correctly report `implemented_not_proven`. Simulation: module + URL + not validated → `implemented_not_proven`, never `active` |

**Active set (strict):** only `pncp`, `ciga_ckan`, `sc_compras` — all three have `operational_validated=True` and real URLs.

**Honesty check:** `is_active=True` (pipeline inclusion) ≠ `operational_status=="active"`. DoD “não chamar de ativa só porque existe crawler” is **implemented in code** for this slice even though that later checkbox is out of scope / still open.

---

## Code review notes (registry)

### Strengths

- `SourceInfo` carries DoD §7.1 fields (`canonical_url`, `geo_coverage`, `pagination_limits`, `rate_limits`, credentials, role, blockers).
- `_ENRICHMENT` layer documents URL/geo/limits without rewriting entire `_RAW` constructors.
- `operational_status` is a **derived property**, not a free-form string — hard to greenwash.
- `validate_registry()` + CLI give operator-visible gate.
- Unit suite covers stable ids, field presence, PNCP primary active, export JSON, validate ok.

### Concerns (non-blocking for first 8)

1. **`transparencia` canonical_url is a prose placeholder**, not an endpoint. Softens item 3 for that source.
2. **Validator is role-asymmetric:** `unknown` pagination/rate is a **gap only for `role=="primary"`**. Complementary sources can claim “informed” while still unknown. Honest for knowledge state; residual debt for measured limits.
3. **`contracts` is `role=primary` but `operational_status=implemented_not_proven`** (no `operational_validated`) — correct honesty; ensure future “active” flips require validation evidence.
4. **Tests do not encode the three falsification probes** as automated assertions (manual QA re-ran them). Recommend adding negative tests in a follow-up (not blocking this slice).
5. **Process smell:** `.aiox/state/stories/ROI-cand-dyn-slice-6c08d1a1d808.json` already had `qa_verdict: PASS` / `po_closed: true` before this independent write of `QA-VERDICT.md`. This file is the **authoritative independent QA record** for the slice evidence pack; residual process debt for orchestrator self-stamping.

---

## Decision

### **CONCERNS**

| Dimension | Assessment |
|-----------|------------|
| First 8 DoD items | Substantively met (7 DONE, 1 PARTIAL) |
| Automated evidence | validate ok + 5 unit tests pass (reproduced) |
| Anti-false-green (active/URL/caps) | Holds under adversarial simulation |
| Residual risk | Pseudo-URL `transparencia`; unknown limits on complementary sources; missing negative unit tests; process stamp before independent verdict file |

**Not FAIL** because: registry is canonical, ids stable, all sources declare URL/caps/geo/credentials/pagination/rate fields, primaries have real URLs and non-unknown limits, and status machine refuses active-without-validation.

**Not pure PASS** because of item 3 PARTIAL (`transparencia`) + residual unknowns + process hygiene.

### Recommended follow-ups (owner @dev / next slice)

1. Replace `transparencia` URL with documented multi-endpoint scheme (e.g. template or list of detected portal base URLs) or mark endpoint as `varies://entity-portal` with explicit schema.
2. Add unit tests: active requires URL; empty capabilities fail validate; module-without-`operational_validated` ≠ active.
3. Measure real pagination/rate for `pcp` / `compras_gov` / `tce_sc` / `doe_sc` when those sources are promoted.
4. Keep later §7.1 items (retry/backoff/status checkboxes) for a dedicated slice — do **not** flip without evidence.

### Gate implication

- Story may remain **Done** under CONCERNS (residual documented, non-blocking).
- DoD `[x]` on first 8 items is **acceptable** with residual notes above; do **not** claim full §7.1 complete.
- Publication: residual process note — confirm `reviewed_commit` matches the tree that includes registry enrichment + tests before remote publish.

---

## Sign-off

```text
verdict: CONCERNS
scope: DoD §7.1 items 1-8 only
items: DONE=7 PARTIAL=1 FAIL=0
tests: 5 passed (test_source_registry_dod71.py)
validate: ok=true n_sources=11
falsify_active_no_url: held
falsify_empty_capabilities: held
falsify_crawler_as_active: held
reviewer: Quinn (@qa)
```

— Quinn, guardião da qualidade 🛡️
