# BASELINE — CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01

**Campaign:** `CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01`  
**Capability:** `confenge_commercial_activation`  
**Class:** `REPAIR_AND_ACTIVATE_VERTICAL`  
**Captured at (UTC):** `2026-07-29T21:43:48Z`  
**Operator / sole commercial acceptance authority:** Tiago Sasaki  
**Pilot client preserved:** Extra Construtora  
**Mode:** AUTONOMOUS / FAIL-CLOSED / REAL-DATA-FIRST / CLI-FIRST  

**Rule for this document:** read-only reconstruction of truth.  
No production code, `DOD.md`, executive HTML, or live services were modified to produce this baseline.

Machine twin: `artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/baseline.json`

---

## 1. Git / main

| Field | Value |
|-------|--------|
| Remote | `https://github.com/tjsasakifln/extra-cli.git` |
| `origin/main` SHA | `d91fdc5967314b46858b0f154b807ccbab7ed515` |
| `origin/main` tip message | `docs(dod): accept proven Extra recurring delivery requirements (#169)` |
| Local workspace branch | `work/recurring-reports-pr2` @ `5c2a960c0293408003657dbb9ca2ab1fc2a5ca6b` |
| Local vs `origin/main` | ahead 4 / behind 2 (dirty tree; unrelated work) |
| Expected pre-mission main | `d91fdc5967314b46858b0f154b807ccbab7ed515` — **confirmed** |

**Non-claims:** this baseline does **not** declare `VPS_OPERATIONAL`, `LOCAL_READY`, or `PROJECT_DONE`.

---

## 2. Open PRs (verified via `gh`)

### PR #171 — merge candidate for pre-campaign reconciliation

| Field | Value |
|-------|--------|
| Title | `fix(ops): contracts checkpoint rebind + shared lock + fail-closed soak` |
| URL | https://github.com/tjsasakifln/extra-cli/pull/171 |
| State | OPEN, not draft |
| HEAD | `50fc9390c6ab886c9e5562f655d4b18b807db324` |
| Branch | `campaign/extra-operational-reliability-coverage-closure-01` |
| Base | `main` |
| mergeable | `MERGEABLE` |
| mergeStateStatus | `CLEAN` |
| production_touched | **yes** (systemd units, contracts checkpoint, soak tracker, crawl lock) |
| Incorporates | PR #170 audit docs (stated in body); dual-coverage **docs** from #168 |

**CI / policies on HEAD `50fc9390` (all SUCCESS):**

- Lint (ruff), Type Check (mypy), Test critical / operational / full suite  
- Resilience Gate, Generated Artifacts Policy, Pytest Skip Policy  
- Security (bandit), Dependency Audit (pip-audit)  
- PR Reviewability Policy  
- Full CONFENGE structural + real evidence job set  
- Edital Relevance Foundation  

**Merge gate (pre-campaign):** all listed points true on the same HEAD → eligible for protected merge (HEAD pin). Soak must not be reset; no fabricated 7-day claim.

### PR #170 — audit, supersede after #171

| Field | Value |
|-------|--------|
| Title | `docs(ops): SOAK + crawler/scheduler health audit (2026-07-29)` |
| URL | https://github.com/tjsasakifln/extra-cli/pull/170 |
| State | OPEN |
| HEAD | `046d8d2942a4b14af11c94b45251208a067d315f` |
| mergeStateStatus | `BEHIND` |
| Intent | documentation audit already folded into #171 |

**Action after #171 merge:** close as superseded with objective comment; **no duplicate merge**.

### PR #133 — independent blocker (do not touch)

| Field | Value |
|-------|--------|
| Title | `[DRAFT][BLOCKED] feat(proposal): bid submission readiness (needs public corpus)` |
| URL | https://github.com/tjsasakifln/extra-cli/pull/133 |
| State | OPEN draft |
| HEAD | `78573f6b25dd20f3e9c1f487e58bcb6512171f2b` |
| mergeable | `CONFLICTING` / DIRTY |

**Campaign policy:** do not rebase, close, merge, or use #133 content.

### Other open PRs

Only #171, #170, #133 were open at capture time.

---

## 3. Relevant worktrees / branches

Selected (non-exhaustive; many historical worktrees exist):

| Path / branch | SHA | Role |
|---------------|-----|------|
| `/mnt/d/extra-cli-wt-op-reliability-01` → `campaign/extra-operational-reliability-coverage-closure-01` | `50fc9390` | PR #171 worktree |
| `/mnt/d/extra consultoria/.worktrees/docs-soak-scheduler-health` → `docs/soak-crawler-scheduler-health-01` | `046d8d29` | PR #170 |
| `/mnt/d/extra consultoria/.worktrees/confenge-commercial-ready-01` → `campaign/confenge-commercial-ready-01` | `6744a4c2` | prior commercial campaign |
| `/mnt/d/extra-cli-wt-confenge-commercial-queue-01` | `83442549` | commercial queue operational branch |
| `/mnt/d/extra-cli-wt-bid-submission-readiness-01` | `78573f6b` | PR #133 work |

Suggested campaign branch (not created before baseline close):  
`campaign/confenge-commercial-activation-outcome-loop-01`

---

## 4. VPS state (`ec-prod` / host `v2202607385716487230`)

| Field | Observed |
|-------|----------|
| Capture time (host) | 2026-07-29 ~21:41 UTC |
| Deployed code SHA (`/opt/extra-consultoria`) | `50fc9390c6ab886c9e5562f655d4b18b807db324` (**same as PR #171 HEAD**) |
| Database | `pncp_datalake` (PostgreSQL) |
| App root | `/opt/extra-consultoria` |
| Env file | `/opt/extra-consultoria/.env` (present; secrets not recorded) |

### systemd timers (active schedule sample)

| Timer | Notes |
|-------|--------|
| `extra-contracts-soak.timer` | active, waiting; next fire ~21:15 -03 |
| `extra-crawl-pncp.timer` | active |
| `pncp-contracts.timer` | active |
| `extra-weekly.timer` | active |
| `extra-health-check.timer` | active |
| `extra-check-alerts.timer` | active |
| `extra-db-backup.timer` | active |
| `extra-crawl-ciga-ckan.timer` | active |

### Soak honesty

| Field | Value |
|-------|--------|
| `extra-contracts-soak.service` | loaded, **inactive/dead** between fires |
| Last exit | status **2** (fail-closed observation incomplete) |
| Present healthy soak days | only `2026-07-29` in last observe payload |
| Expected window (sample) | 2026-07-23 … 2026-07-29 |
| `complete` | **false** — `missing_days_or_health_or_freshness` |
| Issues noted | `missing_run_id` among health failures |
| Seven-day completion | **NOT claimed**; calendar incomplete |

**Do not** restart soak unnecessarily, zero counters, or invent days.

### 3y contracts window proof (VPS artifact)

Path: `artifacts/campaigns/EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01/proofs/contracts-3y-window-proof.json`

- `window_span_start`: 2023-07-20  
- `window_span_end`: 2026-07-23  
- `window_span_days`: 1099 (~3.01 years)  
- `meets_min_3y`: true  
- `completed_windows` / `planned_windows`: 37/37  

---

## 5. Banco / schema / volumes (VPS `pncp_datalake`)

### Migration head

Applied versions observed (desc): **066**, 064, 063, 062, 061, …

Relevant commercial migrations in repo:

- `db/migrations/062_commercial_leads_ledger.sql`  
- `db/migrations/063_supplier_registry.sql`  
- `db/migrations/064_snapshot_write_guard.sql`  

### Tables of interest (public)

Operational / intel: `pncp_supplier_contracts`, `canonical_suppliers`, `enriched_entities`, `opportunity_*`, `coverage_*`, `official_acts`, …

Commercial state (empty on VPS at capture):

| Table | Row count |
|-------|-----------|
| `pncp_supplier_contracts` | **4 467 364** |
| `supplier_registry` | **0** |
| `commercial_leads` | **0** |
| `commercial_feedback_ledger` | **0** |
| `commercial_exclusions` | (present; count not required for baseline) |
| `commercial_lead_runs` | (present) |
| `commercial_lead_state_overrides` | (present) |

### Contract date envelope (real counts)

| Metric | Value |
|--------|--------|
| Total rows | **4 467 364** |
| Distinct `fornecedor_cnpj` | **521 045** |
| Distinct `fornecedor_cnpj_8` | **509 951** |
| `data_assinatura` sane min (2000…today+30) | **2021-04-01** |
| `data_assinatura` sane max | **2026-08-28** (includes near-future values ≤ today+30) |
| Raw max `data_assinatura` (unsanitized) | **8406-05-16** — **data quality outlier** (82 bad assinatura dates) |
| `data_publicacao` sane min | **2023-07-20** |
| `data_publicacao` sane max | **2026-07-29** |

**Implication for campaign:** source of record holds multi-million contracts and ≥3y publication window; commercial execution must process this universe with SQL set-based work, **not** the prior 60k / 11 974 snapshot as “integral history”.

---

## 6. Estado atual do pipeline comercial (campanha anterior)

Campaign artifact root: `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/`

| Artifact | Status / key numbers |
|----------|----------------------|
| `result.json` | **BLOCKED** — `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` |
| Machine blockers | `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` |
| Human blockers | holdout not reviewed; insufficient labels; pending human acceptance |
| `official_registry_coverage` (result top-level) | **0.0532** (~5.3%) |
| Human metrics | `precision_at_10 = null`, `precision_at_20 = null`, `labels_are_human = false` |
| `commercial_release_ready` | **false** |
| Executed freeze SHA | `8506aebabb0dab327654d420222402ae15f9a3aa` |
| Live tip SHA file | `f82eb9615995abd88ffd8e14dfc003f0dcd859b7` |

### `queue-summary.json` (divergent narrative)

| Metric | Value |
|--------|--------|
| status | BLOCKED |
| candidates | **7091** |
| `full_history_contract_count` | **19 328** |
| `db_contract_count` | **60 000** |
| discovery_mode | `PREFILTERED_CANDIDATE_DISCOVERY` |
| registry coverage all candidates | **1.65%** (117/7091) |
| registry coverage top100 | **9%** |
| registry coverage top20 | **100%** |
| `cnae_coverage` | 0.0165 |

### `run/cycle-manifest.json` (another narrative)

| Metric | Value |
|--------|--------|
| status | still **BLOCKED** |
| candidates | **169** |
| `full_history_contract_count` | **291** |
| `db_contract_count` | **11 974** |
| registry all / top100 / top20 | **1.0** |
| `block_reason` nested | `null` |
| human_review_status | PENDING |

### `snapshot-manifest.json`

| Field | Value |
|-------|--------|
| row_count | **11 974** |
| min_date | 2024-08-07 |
| max_date | 2026-07-26 |
| source | `confenge-restorable-csv-package` |

### Entry points already in tree (reuse, do not fork)

- `make confenge-commercial-cycle` → `scripts/ops/confenge_commercial_cycle.py`  
- `scripts/commercial_leads/*`  
- `config/commercial_profiles/confenge.yaml`  
- `config/commercial_profiles/signal_catalog.yaml`  
- `docs/ops/confenge-commercial-ready.md`  
- Spec prior: `specs/006-confenge-commercial-ready/`  

---

## 7. Inconsistências entre artefatos (must fix)

1. **Coverage multi-truth:** `result.json` (~5% official registry) vs `queue-summary` (1.65% all / 100% top20) vs `run/cycle-manifest` (100% on 169 candidates) — same campaign root, incompatible denominators.  
2. **Status vs nested block_reason:** nested `registry.block_reason = null` and 100% coverage while terminal status remains BLOCKED / `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`.  
3. **Contract universe:** 60 000 vs 11 974 vs 19 328 “full history” vs VPS reality **4 467 364** — prior evidence is **not** integral market scan.  
4. **Empty operational commercial tables** on VPS while packages claim registry resolution.  
5. **Human precision** remains null (correct until Tiago labels).  
6. **Soak** incomplete while PR #171 already deployed on VPS — reliability work is in progress, not seven-day complete.

---

## 8. Blockers at campaign start

| ID | Type | Notes |
|----|------|-------|
| PR #171 not yet on `main` | process | merge when gates hold (VPS already runs HEAD) |
| PR #170 open | process | supersede after #171 |
| PR #133 draft corpus | independent | out of scope |
| Official registry empty on VPS | machine | `supplier_registry` = 0 |
| Coverage metric divergence | machine | no single canonical coverage function enforced across exports |
| Snapshot not integral | machine | 60k / 12k packages ≠ 4.4M lake |
| Human acceptance | human (Tiago only) | precision null; `PENDING` |
| Soak incomplete | calendar | fail-closed; do not fabricate days |
| Dirty local workspace | operator | unrelated branch; campaign must start from clean `main` after pull |

---

## 9. DOD.md initial state (honest snapshot)

| Field | Value |
|-------|--------|
| File | `DOD.md` |
| Focus section | `### 2.7 Inteligência comercial CONFENGE — prioridade imediata` |
| Checkbox inventory (whole file) | **442** checked `[x]` / **1016** unchecked `[ ]` / ~2851 lines |
| Campaign rule | Do **not** justify progress by DOD %; only by real commercial artifacts + integrated code |
| Seals | None of `VPS_OPERATIONAL` / `LOCAL_READY` / `PROJECT_DONE` asserted by this baseline |

---

## 10. Input hashes (SHA-256)

| Path | sha256 | size |
|------|--------|------|
| `config/commercial_profiles/confenge.yaml` | `f029dcd688f6e533e52ebab94f53e496fa04c6a9ebe36bfea8f291142b9c048a` | 6378 |
| `config/commercial_profiles/signal_catalog.yaml` | `a02e6c66adef2795c71906e4a3fd0d1a2c2c55c9449d2205940a637011e1004d` | 6879 |
| `scripts/ops/confenge_commercial_cycle.py` | `9983f37e2564e2019bfb6d71269369be11f0d4f09e3aec0b785466105b37f57c` | 5404 |
| `artifacts/.../result.json` | `902c5a7e22cb17f639eefaaf5b2238bfa2dbcccfd513d6d82f28f6c294b47e38` | 2824 |
| `artifacts/.../queue-summary.json` | `0d39e79e1e0245406f64b3f507e21a0d513e381a9cf499199ff1cf5697db01fa` | 10044 |
| `artifacts/.../snapshot-manifest.json` | `8fd30c54434498df811e26885d095163a9c0027e1de374cd94a0c183b76455bf` | 1555 |
| `artifacts/.../run/cycle-manifest.json` | `cefc32210778530d91694115eeead11b7ad6ef9e741da3d228f6a73fbb8b4211` | 3247 |
| `db/migrations/062_commercial_leads_ledger.sql` | `6399c9861a8d56a586b3b47ec9efa59b32b58c8d69c7872267d9fb5b226b69a1` | 5465 |
| `db/migrations/063_supplier_registry.sql` | `920546c2c8d66db57e213f682cc43f5513145833b83669fd1588cbb0fad266b5` | 1129 |

Pinned SHAs:

- `main_sha` (pre-merge): `d91fdc5967314b46858b0f154b807ccbab7ed515`  
- `pr_171_head`: `50fc9390c6ab886c9e5562f655d4b18b807db324`  
- `pr_170_head`: `046d8d2942a4b14af11c94b45251208a067d315f`  
- `pr_133_head`: `78573f6b25dd20f3e9c1f487e58bcb6512171f2b`  
- prior commercial freeze: `8506aebabb0dab327654d420222402ae15f9a3aa`  

---

## 11. Next actions (after baseline close)

1. Re-verify PR #171 HEAD + checks; merge with HEAD protection if still green.  
2. Close PR #170 as superseded (comment → #171).  
3. Leave PR #133 untouched.  
4. `git checkout main && git pull --ff-only`; record new `main_sha`.  
5. Branch `campaign/confenge-commercial-activation-outcome-loop-01`.  
6. Spec Kit → `specs/007-confenge-commercial-activation-outcome-loop/` (next free after `006`).  
7. Only then implement: integral history, official registry, single coverage truth, Top 20/dossiers/kits, outcome ledger, dual execution.

---

## 12. Signature of capture

- Captured by: autonomous campaign agent (Grok)  
- Authority for commercial accept: **Tiago Sasaki only**  
- Baseline closed: **yes** (this file + `baseline.json`)  
- Code / DOD / production mutated for baseline: **no**  
