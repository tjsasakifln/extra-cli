# QA Verdict — DoD §7.1 remainder (retry / backoff / status machine)

| Field | Value |
|-------|-------|
| **Story** | `ROI-cand-dyn-slice-d8deaa518e86` |
| **Scope** | DoD §7.1 Registry de fontes — **remaining items** (retry, backoff, operational status, last validation, blockers, role, `implemented_not_proven`, `blocked`, `not_applicable`, `active`, crawler≠active) |
| **Reviewer** | Quinn (@qa) — independent, not implementer |
| **Date** | 2026-07-18 |
| **Reviewed HEAD** | `a10c273` (+ uncommitted: `tests/test_source_registry_dod71.py` +70 lines, `DOD.md` §7.1b flips, this evidence pack) |
| **Overall verdict** | **CONCERNS** |

---

## Commands re-run (this independent session)

```bash
cd "/mnt/d/extra consultoria"
python3 -m pytest tests/test_source_registry_dod71.py -q --no-cov -o addopts=
# → 8 passed in ~1.2–1.3s
# EXIT=0

python3 -c "from scripts.crawl.registry import export_registry; import collections; \
c=collections.Counter(s['operational_status'] for s in export_registry()); print(dict(c))"
# → {'active': 3, 'implemented_not_proven': 8}

python3 -m scripts.crawl.registry --validate --json
# → ok=true, n_sources=11, missing_required=[], statuses={active:3, implemented_not_proven:8}
# EXIT=0
```

Session artifacts: `MANIFEST.md`, `export.json`, `pytest.log` (8 passed), `pytest.exit`.

---

## Per-item matrix (DoD §7.1 remainder)

| # | DoD item | Status | Evidence | Notes |
|---|----------|--------|----------|-------|
| 9 | Cada fonte informa estratégia de retry | **DONE** | `retry_strategy` on every `to_dod_record()`; `validate_registry` gaps if empty; unit `test_all_sources_have_retry_backoff_role_status` | Live values mostly `exponential_backoff` (declarative registry default + enrichment) |
| 10 | Cada fonte informa estratégia de backoff | **DONE** | `backoff_strategy` on every record; validate + unit | Live values mostly `exp_jitter` |
| 11 | Cada fonte informa status operacional | **DONE** | Derived `operational_status` ∈ {active, implemented_not_proven, blocked, not_applicable}; export + validate statuses | Live distribution: 3 active / 8 unproven |
| 12 | Cada fonte informa data da última validação | **DONE** | Field `last_validation_at` always present (null if unvalidated); 3 actives have ISO dates | Residual: machine **allows** `active` with `last_validation_at=None` (probe confirmed) |
| 13 | Cada fonte informa bloqueadores conhecidos | **DONE** | `known_blockers: list` always present; populated for all 8 unproven | Blockers without token `"blocked"` do **not** force status=`blocked` (by design) |
| 14 | Cada fonte informa se é primária / complementar / gap-fill | **DONE** | `role` on all 11; unit asserts ∈ {primary, complementary, gap_fill} | Live: 4 primary, 4 complementary, 3 gap_fill |
| 15 | Código existente sem validação real → `implemented_not_proven` | **DONE** | 8 live sources with `module` + `operational_validated=False`; unit machine | Includes `contracts` (primary but unproven — honest) |
| 16 | Fonte sem acesso → `blocked` | **DONE** | Unit `test_operational_status_machine` with `known_blockers=["blocked:no_access"]` | **No live** `blocked` source in export (none currently tagged with `"blocked"` token) |
| 17 | Fonte não aplicável → `not_applicable` | **DONE** | Unit: `is_active=False` → `not_applicable` | **No live** N/A source in export |
| 18 | Fonte aplicável e testada → `active` | **DONE** | Live: `pncp`, `ciga_ckan`, `sc_compras` with `operational_validated=True` + real URL | Unit: validated+URL → active |
| 19 | Fonte não é ativa só porque existe crawler | **DONE** | Unit `test_crawler_exists_not_auto_active`; live 8 modules stay `implemented_not_proven` | Requires `operational_validated` **and** `canonical_url` for active |

**Out of scope:** first 8 §7.1 items (prior story `ROI-cand-dyn-slice-6c08d1a1d808`, prior verdict **CONCERNS** on `transparencia` pseudo-URL). Residual from that slice still open; not re-scored here.

---

## Live registry snapshot (re-export)

| id | role | operational_status | last_validation_at | known_blockers (summary) |
|----|------|--------------------|--------------------|--------------------------|
| pncp | primary | active | 2026-07-18 | [] |
| ciga_ckan | primary | active | 2026-07-17 | [] |
| sc_compras | primary | active | 2026-07-17 | [] |
| contracts | primary | implemented_not_proven | null | backfill_3y_incomplete |
| pcp | complementary | implemented_not_proven | null | implemented_not_proven_live |
| compras_gov | complementary | implemented_not_proven | null | implemented_not_proven_live |
| tce_sc | complementary | implemented_not_proven | null | implemented_not_proven_live |
| doe_sc | complementary | implemented_not_proven | null | credentials_required |
| transparencia | gap_fill | implemented_not_proven | null | heterogeneous_portals, no_single_canonical_http_endpoint |
| mides_bigquery | gap_fill | implemented_not_proven | null | credentials_required, no_pagination_zero_proof |
| dom_sc | gap_fill | implemented_not_proven | null | credentials_required, prefer_ciga_ckan |

**Counts:** `active=3`, `implemented_not_proven=8`, `blocked=0`, `not_applicable=0`.

---

## Falsification probes (required)

| Probe | Result | Detail |
|-------|--------|--------|
| **Crawler/module exists ⇒ active** | **PASS (cannot falsify green)** | SourceInfo with module + URL + `operational_validated=False` → `implemented_not_proven`. Live 8 modules confirm. |
| **Active without URL** | **PASS (held from prior slice)** | `operational_validated=True` without URL cannot become active (property requires both). |
| **Active without last_validation_at** | **RESIDUAL (can greenwash date)** | Probe: `operational_validated=True` + URL + `last_validation_at=None` → still `active`. Field is *informed* (null), but status machine does not couple date to active. |
| **blocked requires explicit token** | **HELD** | `known_blockers=["credentials_required"]` alone → still `implemented_not_proven` (not silent blocked). |
| **not_applicable only when inactive** | **HELD** | `is_active=False` → `not_applicable`. |
| **Empty retry/backoff** | **HELD for validate** | Empty strings gap in `validate_registry`; dataclass defaults prevent empty on live registry. |

---

## Code review notes

### Strengths

- Status is a **derived property**, not a free-form stamp — hard to claim `active` without `operational_validated` + URL.
- `to_dod_record()` exports the full §7.1 remainder field set; CLI `--validate` / `--export` operator-visible.
- Unit suite now covers status machine (4 states) + crawler≠active + field presence on all live sources (8 tests total).
- Live honesty: majority of sources remain `implemented_not_proven`; only three primaries are active.
- Retry/backoff are registry *declarations* (DoD wording: “informa”), not a claim that every crawler already implements them (crawler-level retry items remain open elsewhere in DoD).

### Concerns (non-blocking for this remainder slice)

1. **Process / AC3 hygiene:** Story AC requires *“Independent QA PASS before any [x] flip”*. `DOD.md` already has the 11 remainder items flipped to `[x]` and `.aiox/state/stories/ROI-cand-dyn-slice-d8deaa518e86.json` was pre-stamped `qa_verdict: PASS` / `po_closed: true` / `status: Done` **before** this independent `QA-VERDICT.md`. Same orchestrator smell as §7.1 first pack. **This file is the authoritative independent QA record.**
2. **`active` decoupled from `last_validation_at`:** machine allows active with null date (probe). Live actives happen to have dates via `_ENRICHMENT`; recommend coupling or a validate gap for primaries/actives without date.
3. **`blocked` / `not_applicable` proven only by synthetic unit tests** — no live source currently exercises those two statuses. Acceptable for machine proof; not a live inventory claim.
4. **`validate_registry` does not assert** `last_validation_at` key presence, `known_blockers` type, or `operational_status` membership — those rely on unit tests + export shape.
5. **Declarative retry/backoff defaults** are homogeneous (`exponential_backoff` / `exp_jitter`); source-specific strategies are not differentiated except where enrichment overrides. Honest as “informed”, weak as operational differentiation.
6. **Prior residual** (`transparencia` multi-portal endpoint) from first §7.1 pack remains; not reopened as FAIL here.

---

## Acceptance criteria (story)

| AC | Assessment |
|----|------------|
| 1. Each of N dod_item_ids proven with evidence or left open | **MET** — 11 remainder items DONE with tests + live export; none left open without reason |
| 2. No NOT_APPLICABLE used to hit campaign meta | **MET** — no DoD item marked N/A; status `not_applicable` is machine-only, zero live sources |
| 3. Independent QA PASS before any [x] flip | **PARTIAL / process fail** — flips and state stamp preceded this independent write |

---

## Decision

### **CONCERNS**

| Dimension | Assessment |
|-----------|------------|
| Remainder §7.1 items (11) | Substantively **DONE** (11/11) |
| Automated evidence | 8 unit tests pass; validate ok; export counts honest |
| Anti-false-green (crawler≠active) | Holds under live + synthetic probes |
| Residual risk | Process pre-stamp; active without forced last_validation; blocked/N/A synthetic-only; validate incomplete for new fields |

**Not FAIL** because: every remainder checkbox has real registry fields + automated proof; active set is strict (3); crawler existence does not greenwash active; no campaign meta via N/A.

**Not pure PASS** because: AC3 process order violated (DoD/[state] stamped before independent verdict); residual soft gap on `last_validation_at` enforcement for active; blocked/N/A lack live exemplars.

### Recommended follow-ups (owner @dev / next slice — non-blocking)

1. Couple `active` → require non-null `last_validation_at` (property and/or `validate_registry` gap for actives).
2. Extend `validate_registry` to check `known_blockers` is list and `operational_status` ∈ allowed set.
3. Stop orchestrator self-stamping `qa_verdict` / DoD `[x]` before independent `QA-VERDICT.md` exists.
4. When a source is truly access-denied, tag `known_blockers` with explicit `blocked:…` so live inventory exercises `blocked`.
5. Keep prior `transparencia` endpoint residual tracked (first pack CONCERNS).

### Gate implication

- Story may remain **Done** under **CONCERNS** (residuals documented, non-blocking for remainder substance).
- DoD `[x]` on remainder items is **acceptable** with notes above; do **not** claim crawler-level retry/backoff implementation (separate open DoD lines).
- Publication: independent record is this file; reconcile state `qa_verdict` to `CONCERNS` if process hygiene is enforced strictly.

---

## Sign-off

```text
verdict: CONCERNS
scope: DoD §7.1 remainder (items 9-19)
items: DONE=11 PARTIAL=0 FAIL=0
tests: 8 passed (test_source_registry_dod71.py)
validate: ok=true n_sources=11 active=3 implemented_not_proven=8
falsify_crawler_as_active: held
falsify_active_without_last_validation: residual (allowed by machine)
live_blocked: 0 (synthetic only)
live_not_applicable: 0 (synthetic only)
reviewer: Quinn (@qa)
story: ROI-cand-dyn-slice-d8deaa518e86
```

— Quinn, guardião da qualidade 🛡️
