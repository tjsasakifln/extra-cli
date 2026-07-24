# Independent adversarial review (Trilha G) — CLIENT-READY-RECURRING-CONSULTING-CYCLE-01

**Reviewer:** independent adversarial (did **not** implement the integration)  
**Worktree:** `/tmp/extra-cli-client-ready-01`  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/131  
**Evidence:** `artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01/`  
**Machine-readable findings:** [`independent-adversarial-findings.json`](./independent-adversarial-findings.json)

| Field | Value |
|-------|--------|
| **Verdict** | **CONCERNS** |
| **CRITICAL open** | **0** |
| **HIGH open** | **2** (`IAF-05`, `IAF-08a`) |
| **MEDIUM open** | **3** (`IAF-08b`, `IAF-10`, `IAF-W01`) |
| **RC / evidence stamp** | `aadd65c00599a5dd44a3c2517492eae22a79c6c5` |
| **result.final_status** | `BLOCKED` (vocab PASS\|BLOCKED\|FAIL only) |
| **production_touched** | `false` (boolean) |
| **soak_touched** | `false` (boolean) |
| **package-reconciliation** | field `status=PASS` — **substantive quality CONCERNS** (see §15.5) |
| **linkage-quality** | present (`status=completed`) |
| **user-acceptance** | `PENDING_HUMAN` (`accepted_by=null`) — not agent fake ACCEPT |

---

## Gate checks (required)

| Check | Result |
|-------|--------|
| `result.json` `final_status` ∈ {PASS, BLOCKED, FAIL} | **PASS** → `BLOCKED` |
| `production_touched` / `soak_touched` boolean false (not null) | **PASS** |
| `package-reconciliation.json` status PASS | **PASS field / CONCERNS integrity** |
| `linkage-quality.json` present | **PASS** |
| `user-acceptance` PENDING_HUMAN (not fabricated ACCEPT) | **PASS** |

---

## Attack surfaces (§15)

| # | Surface | Result | Reproduction (short) |
|---|---------|--------|----------------------|
| 1 | Universe contamination / export as population | **PASS** | `eligible_population=1_179_237`; `export_limit=200`; `export_is_not_universe=true`; exec summary labels export ≠ universe |
| 2 | False CNPJ merge | **PASS** | unit `test_never_merge_conflicting_cnpj14` green; `false_merge_strong_cnpj=0` |
| 3 | Historical winner as open-tender participant | **PASS** | dossier contract links `claim_level=similarity` + non_claims `not_observed_participant_of_open_tender` |
| 4 | success_zero without full query | **PASS** | C: `n=14750`, `query_complete=true`, scanned ~1.18M contracts |
| 5 | PDF×Excel divergence | **FAIL** | `reconcile(meta_pdf=meta, meta_excel=meta)`; `same_run_id=True` hardcoded — see IAF-05 |
| 6 | Missing profile version | **PASS** | `extra_construtora@v2` on all A–E + manifest `profile_version=2` |
| 7 | PENDING capacity as known | **PASS** | all E rows `REVIEW`; PENDING fields listed; no GO/PARTICIPAR |
| 8 | Second run rebuild / fake delta | **CONCERNS** | state reused (`reused_previous_state=true`); synthetic `LIVE-DELTA-*` inject; `recurrence.json` falsely all `success_zero` — IAF-08a/b |
| 9 | Production DSN / soak | **PASS** | isolation `@127.0.0.1:5436/extra_live_pack_rc`; hits=[]; tests reject ec-prod/5432 |
| 10 | Mandatory test skipped as pass | **CONCERNS** | junit `skipped=3` real_db/linkage without REQUIRE_*; green suite does not execute pack E2E |
| 11 | Dual national_intel / PR#121 | **PASS** | 060 intel; 059 coverage spine; PR121 superseded; no dual 059_national |
| 12 | DOD marked without proof | **PASS** | `dod-impact` no premature `[x]`; campaign remains BLOCKED; non-claims include LOCAL_READY/VPS/soak |
| 13 | Alternate terminals | **PASS** | only PASS/BLOCKED/FAIL from `decide_terminal`; banned TECHNICAL_PASS returns |
| 14 | Human accept fabricated | **PASS** | PENDING_HUMAN; null accepted_by; agent ACCEPT rejected in code |

---

## Open HIGH findings

### IAF-05 — PDF×Excel reconcile is theater (HIGH)

**Command**

```bash
rg -n 'meta_pdf=meta, meta_excel=meta|same_run_id' scripts/ops/live_consulting_pack.py
python3 -c "import json; print(json.load(open('artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01/package-reconciliation.json')))"
```

| | |
|--|--|
| **Expected** | Independent PDF vs Excel identity/hash comparison; computed `same_run_id` |
| **Observed** | Same `meta` object passed for both; `same_run_id: True` always; `status=PASS`, `divergences=[]` |
| **Impact** | Package reconciliation cannot catch real PDF×Excel divergence |

### IAF-08a — recurrence.json false success_zero (HIGH)

**Command**

```bash
python3 -c "import json; r=json.load(open('artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01/recurrence.json')); print({k:v for k,v in r['categories'].items()})"
python3 -c "import json; m=json.load(open('artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01/monthly/monthly-monitor-live.json')); print('new', m['cycle_2']['new_editais']); print('deltas', m['cycle_2']['status_deltas'][:1])"
```

| | |
|--|--|
| **Expected** | LIVE path maps `cycle_2.new_editais` → `new_opportunities`, `status_deltas` → `status_changes`, etc. |
| **Observed** | All categories `count=0` / `success_zero=true` while monthly cycle_2 has deltas |
| **Root cause** | `build_recurrence_delta` only copies **top-level** keys matching category names; live monitor nests under `cycle_1`/`cycle_2` |

---

## Medium findings (open)

| ID | Severity | Summary |
|----|----------|---------|
| IAF-08b | medium | LIVE-ISOLATED injects synthetic `LIVE-DELTA-{date}`; proofs `new_editais_detected=true` without organic dump change |
| IAF-10 | medium | 3 real_db/linkage tests skipped in campaign junit; skip ≠ fail |
| IAF-W01 | medium | Weekly `exit_code=2` treated as `ok`; universe 1090≠1093; PDF residual; collect skipped |

---

## What is solid

- Isolation fail-closed; `production_touched`/`soak_touched` never null-success.
- Population not silently replaced by export_limit=200.
- Linkage non-claims protect winner≠participant.
- PENDING capacity does not auto-promote to GO/PARTICIPAR.
- Terminal vocabulary clean; human gate not bypassed.
- national_intel single authority (060); PR#121 not dual-merged.
- Campaign correctly **BLOCKED** pending Tiago ACCEPT — not a false PASS.

---

## Verdict rationale

**CONCERNS** (not FAIL): global terminal and isolation are honest; human acceptance is not fabricated.  
**Not PASS:** two HIGH defects undermine package reconciliation and recurrence evidence quality.  

Prior review (`review/findings.json` / earlier independent-review table) claimed all surfaces PASS and zero Critical/High — **this adversarial pass disagrees on §15.5 and §15.8.**

**CRITICAL/HIGH remaining open: YES (2 HIGH).**

### Recommended before elevating technical confidence

1. Fix `reconcile()` to compare independent PDF/Excel hashes (or meta built from each artifact) and compute `same_run_id`.
2. Fix `build_recurrence_delta` LIVE path to parse `cycle_2` fields; never mark success_zero when data not extracted.
3. Label synthetic LIVE-DELTA in claims/non-claims; require `REQUIRE_REAL_DB=1` for campaign gate junit or attach live-run as mandatory residual.

---

*Trilha G — independent adversarial — 2026-07-24*
