# QA Verdict — ROI-cand-dyn-slice-b50513eeb753

**Reviewer:** Quinn (@qa) — independent adversarial audit  
**Date:** 2026-07-18T15:40:18Z  
**Branch:** `epic/advance-30d-local-ready-20260718`  
**Reviewed HEAD:** `c0434581b776d2b21dd2589030c88a471da7d037`  
**Candidate:** `cand-dyn-slice:b50513eeb753`  
**Cycle:** `cyc-2026-07-18T153340Z`  
**Scope:** DoD §12.2 first 8 list items only  

## overall: PASS

List-capability for all 8 §12.2 items is real, fail-closed, and live-proven against PostgreSQL. No LOCAL_READY / 95% claims. Residual risks documented; none block checkbox flips for *list generation* capability.

---

## Per-item classification

| # | Item | Verdict | Evidence |
|---|------|---------|----------|
| 1 | Lista de editais acionáveis | **DONE** | Live CSV GO=6; partition complete; real `pncp_raw_bids` + `compute_ranking` |
| 2 | Lista de editais para revisão | **DONE** | Live CSV REVIEW=1; exclusive partition vs GO/NO_GO |
| 3 | Lista de editais descartados com motivo | **DONE** | Live NO_GO=1; `motivo=Sem identificação do órgão` non-empty |
| 4 | Lista de oportunidades removidas do snapshot | **DONE** | Generator queries `is_active=false`; live N=0 with stable headers (all 8 bids active) |
| 5 | Lista de entes sem cobertura de editais | **DONE** | Real SQL against `sc_public_entities`/`pncp_raw_bids`; empty + limitation explicit (`sc_public_entities empty`) |
| 6 | Lista de entes sem cobertura de contratos | **DONE** | Real SQL against `sc_public_entities`/`pncp_supplier_contracts`; same universe limitation |
| 7 | Lista de blockers por fonte | **DONE** | Live N=1 (`pncp` / `ingestion_failed` with real error detail) |
| 8 | Lista de runs stale | **DONE** | Generator real; default window → 0 (honest); demo `stuck_running_hours=0` → 2 stuck runs |

### DoD lines that MAY be flipped to `[x]`

All 8 above — **list capability only**.

### Must stay open / forbidden

- LOCAL_READY / PRE_VPS / VPS_OPERATIONAL / PROJECT_DONE
- Operational coverage ≥95%
- Universe-wide gap completeness (entities not seeded)
- Any claim that empty gap CSV means “all covered”

---

## Evidence commands + exit codes

```bash
# 1) Unit + integration tests
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m pytest tests/test_operational_outputs.py -q --no-cov -o addopts=
# → exit 0 | 5 passed in ~1.5s

# Without DSN (control): 4 passed, 1 skipped — fixtures ≠ full live proof

# 2) Live generator (independent re-run)
python3 -m scripts.reports.operational_outputs \
  --dsn "$LOCAL_DATALAKE_DSN" --out /tmp/ops-qa-lists --json
# → exit 0 | run_id=ops-lists-20260718-153900-91cb7636
# counts: GO=6 REVIEW=1 NO_GO=1 blockers=1 removed=0 gap_*=0 stale=0
# reliability=DEGRADED
# limitations: ["sc_public_entities empty — gap lists cannot enumerate universe entities"]
# forbidden includes LOCAL_READY

# 3) Partition falsification
# db active pncp_ids (8) == union(GO∪REVIEW∪NO_GO) ; no dups ; set_equal True

# 4) Stale capability (threshold demo, not default SLA)
# stuck_running_hours=0 → runs_stale rows=2 (ids 2,3 status=running)
```

### Live DB snapshot (QA)

| Table | n |
|-------|---|
| pncp_raw_bids | 8 (all is_active=true) |
| sc_public_entities | 0 |
| pncp_supplier_contracts | 0 |
| ingestion_runs | 6 (completed=3, failed=1, running=2) |
| opportunity_intel | 0 |

### Session artifacts audited

- `docs/ops/session-2026-07-18-operational-outputs/MANIFEST.md`
- `lists/*.csv` + `lists/manifest.json`
- `lists-stale-demo/runs_stale.csv` (2 rows)
- `pytest.log` / `pytest.exit` (0)
- Independent re-run: `/tmp/ops-qa-lists/`

---

## Adversarial checks (falsify claims)

| Check | Result |
|-------|--------|
| Silent invention of entities when universe empty | **PASS** — empty CSV + limitation; reliability DEGRADED |
| Empty gap list overclaims coverage | **PASS** — not claimed; forbidden seals present |
| NO_GO without motivo | **PASS** — motivo present |
| Partition leak / double-count | **PASS** — 8/8 exclusive |
| Fake LOCAL_READY / 95% | **PASS** — in `claims.forbidden` only |
| Empty lists without stable headers | **PASS** — headers match EMPTY_HEADERS |
| Tests only fixtures | **PASS** — live PG re-run independent of session fixture narrative |
| Stale list theater | **PASS** — default 0 honest; demo proves detector |

---

## Residual risks (do not block list-capability DONE)

1. **`fonte_confiavel=True` hardcoded** in `classify_bids` — may inflate GO quality; ranking policy debt, not missing list.
2. **`LIMIT 2000`** on bids/gaps — truncation not listed in `limitations` if datasets grow.
3. **Gap SQL non-empty path** not live-exercised (universe n=0). Code path exists; empty+limitation OK for capability.
4. **Removed list** live path only empty (no `is_active=false` rows in proof DB).
5. **`_q` swallows exceptions** into `_error` rows — fail-closed for lists, but schema drift can look like “empty”.
6. **`dentro_raio=bool(matched_entity_id)`** conflates match with radius — ranking fidelity risk.

---

## Gate decision

| Field | Value |
|-------|-------|
| overall | **PASS** |
| reliability of live run | DEGRADED (honest) |
| may flip 8 DoD list items | **YES** (capability) |
| may claim LOCAL_READY / 95% | **NO** |
| next | @po close story → @devops only after state gates |

**Self-QA invalid:** this review was executed by independent @qa against code + live DB, not by the implementer narrative alone.
