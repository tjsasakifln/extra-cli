# Cross-PR Architecture Audit — EXTRA-OPEN-PRS-CONSOLIDATION-01

**Generated:** 2026-08-03 (live GitHub + git)  
**Main at baseline:** `704975a7bcdd43d4dc6769fbf6c14726327ab37b`  
**Source of truth:** `artifacts/campaigns/EXTRA-OPEN-PRS-CONSOLIDATION-01/baseline.json`

## Premise check

| Premise | Live result |
|---------|-------------|
| PRs #196, #198, #197 open | **Yes** — exactly these 3 open |
| Order `#196 → #198 → #197` | **Confirmed viable** (no path collision; migration order already correct) |
| Force-order change needed? | **No** |

## PR snapshot

| PR | Branch | HEAD | Ahead/Behind main | Files | +/- | Mergeable | CI |
|----|--------|------|-------------------|-------|-----|-----------|-----|
| #196 | `feat/production-readiness-closeout` | `ecc924389af7…` | 19 / 0 | 162 | +10375/-22 | MERGEABLE CLEAN | 28 SUCCESS (1 CANCELLED duplicate Reviewability) |
| #198 | `campaign/EXTRA-DECISION-OUTCOME-MEMORY-01` | `d56f3d3e484d…` | 23 / 0 | 40 | +5162/-11 | MERGEABLE CLEAN | 28 SUCCESS |
| #197 | `campaign/EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01` | `2af0ff5c7862…` | 9 / 0 | 75 | +9012/-158 | MERGEABLE CLEAN | 28 SUCCESS |

## File path overlaps

| Pair | Shared paths |
|------|----------------|
| 196 ∩ 198 | **0** |
| 196 ∩ 197 | **0** |
| 197 ∩ 198 | **0** |

Path isolation is excellent. Semantic coupling exists (see below).

## Migration numbering

| Owner | Expected file | Actual on branch | Status |
|-------|---------------|------------------|--------|
| main (latest) | `067_process_documents_runs.sql` | present | OK |
| #198 | `068_decision_outcome_memory.sql` | **present** | OK |
| #197 | `069_predictive_intelligence.sql` | **present** (header notes 068 reserved by #198) | OK |
| main gap | `065_*` | **missing** (064→066) | Pre-existing, outside this campaign |

### Documentation divergences (must fix before #197 merge)

| Location | Problem |
|----------|---------|
| PR #197 body | Still says “migration **068**” |
| `docs/decisions/adr-068-predictive-intelligence-claim-gates.md` | ADR number **068** while SQL is **069** |
| PR #198 body Risk | Mentions “orphaned predictive 068” from earlier #197 state — reconcile after renumber |

**Rule after consolidation:** no doc may say “migration 068” for predictive layer.

## PostgreSQL tables

### Decision Memory (#198) — commercial/operational fact ledger (canonical)

- `dm_decision_events` (append-only)
- `dm_action_events` (append-only, FK→decision, client match trigger)
- `dm_outcome_events` (append-only, optional FK→decision, client match trigger)
- `dm_identity_conflicts`, `dm_import_runs`
- Views: `dm_decision_current`, `dm_action_current`, `dm_outcome_current`
- Immutability: `dm_forbid_mutation` blocks UPDATE/DELETE

### Predictive Intelligence (#197) — model lifecycle + evaluation

- `predictive_dataset_runs`, `predictive_training_examples`
- `predictive_models`, `predictive_model_metrics`, `predictive_model_artifacts`
- `predictive_predictions` (immutability trigger)
- `predictive_prediction_explanations`
- **`predictive_outcomes`** — per-prediction reconciliation (`UNIQUE(prediction_id)`), labels for Brier/drift
- `predictive_drift_runs`, `predictive_claim_states`, `predictive_client_profile_versions`

### Outcomes duality (critical)

```
CANONICAL commercial facts:
  dm_outcome_events / dm_outcome_current
        ↓ (must be consumed; not re-ledgers)
PREDICTIVE evaluation:
  predictive_outcomes  (prediction_id → observed label for model metrics)
```

**Current gap:** `predictive_outcomes` has **no FK / structured link** to `dm_outcome_events`.  
It reconciles predictions to procurement/lake observations, not to Decision Memory.

**Required integration before #197 merge (campaign rule 13):**

1. Add optional strong provenance on `predictive_outcomes`:
   - `dm_outcome_event_id UUID NULL` (FK → `dm_outcome_events.event_id` when linked)
   - `link_status TEXT NOT NULL` with closed set e.g.  
     `LINKED_DM | UNLINKED_LEGACY | HISTORICAL_UNVERIFIED | NOT_APPLICABLE_MODEL_ONLY`
2. Prefer resolving commercial outcome types (win/loss/contract) via DM when client_id present.
3. Never invent DM outcomes to fill metrics; `outcome_quality` / link_status fail-closed.
4. Keep `predictive_outcomes` as **evaluation projection**, not a second commercial ledger UI/source.

While #197 is unmerged, fix in migration **069** (do not invent 070 for this).

## Semantic module matrix

| Concern | #196 | #198 | #197 | Risk |
|---------|------|------|------|------|
| Command Center workflows / consulting | **Owns** | — | touches workspace CLI | Low path conflict |
| process_documents queue / quarantine | **Owns** | — | — | Low |
| production_readiness harness | **Owns** | — | — | Low |
| decision_memory module | — | **Owns** | — | — |
| extra_decision_review / weekly board from PG | — | **Owns** | — | — |
| weekly_cycle core | — | light (decision pack) | **modifies** predictive section | Medium post-merge order |
| predictive package | — | — | **Owns** | — |
| bid_simulator honesty | — | — | **Owns** | Must stay after #196 |
| systemd timers | — | — | shadow predictive only | Must not auto-enable |
| requirements.txt (numpy/sklearn) | — | — | **global add** | Prefer optional extras |

## Python dependencies

| PR | Dep changes |
|----|-------------|
| #196 | None in requirements |
| #198 | None in requirements |
| #197 | `numpy>=1.26`, `scikit-learn>=1.4` **into root `requirements.txt`** |

**Preference:** move predictive deps to optional extra (`requirements-predictive.txt` or package extra) with lazy imports; core CLI without ML stack. Only keep global if proven required by CI critical path.

## CLIs

| Entry | PR |
|-------|-----|
| `python -m scripts.production_readiness` | #196 |
| `python -m scripts.decision_memory` | #198 |
| `python -m scripts.predictive` | #197 |
| `scripts.workspace predictive-status` | #197 |
| weekly_cycle predictive section | #197 |

## Timers / systemd

| Unit | PR | Policy |
|------|-----|--------|
| `extra-predictive-shadow.service/.timer` | #197 | Shadow only; **do not enable** on install/merge |

## Weekly cycle / artifacts

| PR | Behavior |
|----|----------|
| #196 | Evidence packs under `artifacts/production-readiness/*` (multiple temporal packages; canonical tip pack `20260802T134234Z`) |
| #198 | Weekly board **from PostgreSQL only** (`weekly_board.py`); integrates review path fail-closed |
| #197 | Appends claim-gated `predictive_status.json`; no PRODUCTION claim without registry |

## Sources of truth (target end-state)

| Domain | Canonical source |
|--------|------------------|
| Human decisions / actions / commercial outcomes | **Decision Memory PG** (`dm_*`) |
| Model predictions (immutable) | `predictive_predictions` |
| Model evaluation outcomes | `predictive_outcomes` **linked to DM when fact is commercial** |
| Claim language | `predictive_claim_states` + static honesty tests |
| Ops readiness evidence | `artifacts/production-readiness/<canonical pack>` + CI on SHA |

## Regression risk ranking

1. **High:** Dual outcomes (#197 vs #198) if merged without link — contradictory commercial truth.
2. **Medium:** #197 `requirements.txt` expands attack/install surface for all installs.
3. **Medium:** #197 ADR/body still say 068 — operator confusion.
4. **Low:** #196 large artifact tree (small bytes ~190KB; intermediate packs superseded by tip pack).
5. **Low:** Path conflicts (none today); still rebase after each merge because `required_linear_history` + `strict` status checks.

## Merge order (confirmed)

```text
#196  production ops base
  → #198  migration 068 Decision Memory
    → #197  migration 069 Predictive (+ DM link + docs renumber + optional deps)
```

**Rationale:**

1. #196 has no migrations; establishes operational/consulting base and queue correctness.
2. #198 owns commercial ledger; must land before predictive can FK to DM.
3. #197 already uses 069 file; body/ADR cleanup + outcome link must happen **after** 068 exists on main.

## #196 artifact packages index (no deletion)

| Package | Role |
|---------|------|
| `20260801T195846Z` | Early evidence |
| `20260801T200107Z` | Early VPS deploy |
| `20260801T203800Z` | Mid pack |
| `20260802T005800Z` | Queue/VPS mid |
| `20260802T115800Z` | Three-cycle mid |
| `20260802T121230Z` | Large mid pack (full-scale nested) |
| `20260802T130202Z` | Near-tip |
| `20260802T130535Z` | Near-tip |
| **`20260802T134234Z`** | **Canonical tip pack cited in PR body (HEAD `ecc92438`)** |

Policy: preserve all for audit trail; cite tip pack as canonical. No secret DSN values found (only `LOCAL_DATALAKE_DSN_set: true`).

## Branch protection relevant to merge

- `required_linear_history: true` → prefer **squash** (matches recent main style `#N`)
- `strict: true` status checks → HEAD must be up to date with main
- Required checks include Lint, mypy, critical/operational/full tests, Resilience, Generated Artifacts, PR Reviewability, Pytest Skip, Security, Dependency Audit
- `required_approving_review_count: 0`
- `required_conversation_resolution: true`
- Admins enforced

## Next actions

1. Review + local tests + merge **#196**
2. Rebase **#198** on new main → migration proof → merge
3. Rebase **#197** on main+068 → fix ADR/body/docs → link `predictive_outcomes` to DM → optional deps → full gates → merge
4. Post-merge main CI + report
