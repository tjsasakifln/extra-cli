# ADVERSARIAL REVIEW — DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

| Field | Value |
|-------|-------|
| **Reviewer** | Quinn (Guardian) — independent QA, not the implementer |
| **Campaign** | `DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01` |
| **Worktree** | `/mnt/d/extra-cli-dod-low-hanging` |
| **Branch** | `campaign/dod-low-hanging-boundaries-evidence-01` |
| **HEAD** | `e39a75f35224cdf1acd34c2a8eb2f5ea08fa220e` |
| **Reviewed at** | `2026-07-30T00:39:38Z` |
| **Campaign claim** | `proven=59`, `status=PASS` |
| **QA verdict** | **PASS_WITH_REDUCED_SET** |
| **Surviving PROVEN** | **42** (demoted **17**) |

## Mission

Reduce false accepts. Prefer a smaller honest set over an inflated PASS.
Only write this review + `artifacts/.../qa-verdict.json` (no app code changes, no DOD accept).

## Method (what was checked)

1. `artifacts/.../result.json`, `acceptance-matrix.json`, `candidate-matrix.json`, `scope-audit.json`, `claim-audit.json`, `cli-usability-matrix.json`, `protected-path-audit.json`
2. Source: `config/scope_boundaries.yaml`, `scripts/ops/audit_scope_boundaries.py`, `scripts/ops/dod_low_hanging_audit.py`
3. Live re-audit: `python3 -m scripts.ops.audit_scope_boundaries --capability k8s_kafka_redis_es_sem_necessidade` → **REGRESSION** (12 impl hits on `scripts/redis_pool.py` + crawl redis helpers)
4. Product-code search for redis/kafka/stripe/tenant/aditivo/obra signals
5. `git diff origin/main --name-only` + full `git status` for protected-path leakage
6. Shared-evidence analysis (command groups, hardcoded checks, auditor self-matches)

## Protected path check

| Surface | Result |
|---------|--------|
| `DOD.md` | Not modified in WT |
| `Makefile`, `README.md`, `CHANGELOG.md` | Not modified |
| `docs/DEVELOPMENT.md`, `docs/INDEX.md`, `docs/ops/NEXT-DEV-STEP.md` | Not modified |
| `deploy/systemd/**` | Not modified |
| `scripts/crawl/**` | Not modified |
| commercial / confenge / extra delivery cycles | Not modified |
| Tracked diff vs `origin/main` | Only `.dod/{log,manifest,state}` |
| Untracked campaign surface | `config/scope_boundaries.yaml`, audit scripts, tests, specs, campaign artifacts/docs |

**Protected paths OK for PR A** (no product crawl/commercial/systemd/DOD mutation).

**Caveat:** `protected-path-audit.json` reports `changed_files_sample: []` — it did not inventory untracked files. Independent check above is authoritative.

## Classification quality (non-demotion notes)

| Observation | Severity | Note |
|-------------|----------|------|
| Admin **aditivo** vs physical **obra** | OK | Product monitors contractual aditivos (`valor_aditivos`, vigência); `gestao_aditivos_execucao_fisica` remains absence-proven. Distinction in YAML is correct. |
| Theme `comercial` false-rejects scope item | MEDIUM residual | `O projeto não assume responsabilidade … ou comercial` → `REJECTED_PARALLEL_CONFLICT` because substring `comercial` is in `_FORBIDDEN_THEMES`. This **under-selects** a real B_SCOPE item; does not inflate proven. Fix later. |
| Auditor self-matches | MEDIUM residual | Multi-tenant / scope phrases in `dod_low_hanging_audit.py` classified as documentation — correct for tooling, but over-reliance on allowlist can hide product code if patterns are weak. |
| `scope-audit.json` vs config mtime | HIGH residual | Scope audit written **before** final `scope_boundaries.yaml` (audit `00:33:25Z`, config `00:34:09Z`). Stale PROVEN for redis. |

## Demotions (17)

### A. False accept / evidence integrity (must demote)

| item_id | Family | Reason |
|---------|--------|--------|
| `DOD-definition-of-done-extra-07fdce3052` | B_SCOPE | **Redis present without need-proven ADR.** Live audit: `REGRESSION`, 12 hard findings on `scripts/redis_pool.py` (`RedisPool` / `get_redis_pool` / `import redis.asyncio`). Config notes explicitly: redis helpers without need → **NOT_PROVEN**. Campaign stored `PROVEN` with 0 findings — **false accept**. |

### B. Shared / non-per-item evidence (governance catalog)

Five evidence-type bullets share one weak check: `dod-convergence.md` contains `"verify"` + `"fail-closed"`. That does **not** prove each evidence type is enforced.

| item_id | Text (short) | Reason |
|---------|--------------|--------|
| `DOD-definition-of-done-extra-5fd54bbd01` | teste automatizado reproduzível | Shared `evidence_convention_doc` only |
| `DOD-definition-of-done-extra-56586465e9` | comando documentado exit 0 | Shared `evidence_convention_doc` only |
| `DOD-definition-of-done-extra-374c5965bd` | execução em ledger/manifest | Shared `evidence_convention_doc` only |
| `DOD-definition-of-done-extra-3104de3131` | log datado | Shared `evidence_convention_doc` only |
| `DOD-definition-of-done-extra-349bb54c8f` | commit/PR identificável | Shared `evidence_convention_doc` only |

### C. Hardcoded / docs-only “proof”

| item_id | Reason |
|---------|--------|
| `DOD-definition-of-done-extra-cb23ed5034` | `optional_policy` is **hardcoded `True`** in `prove_governance_item` — no enforcement assertion |
| `DOD-definition-of-done-extra-d3db8c3907` | Scope-change policy only checks `AGENTS.md` mentions `DOD.md` + DOD title string — not a process gate |

### D. Fragment bullets under three-rolls (inflate + VPS-adjacent)

Parent `aa0cc46c52` already proves three-roll gate logic. Sub-bullets only check dict key names.

| item_id | Reason |
|---------|--------|
| `DOD-definition-of-done-extra-f0f41447dd` | “requisitos do estágio atual” — fragment; key existence only |
| `DOD-definition-of-done-extra-b5522727b0` | “posteriores ao provisionamento da **VPS**” — fragment + VPS-adjacent theme |
| `DOD-definition-of-done-extra-107a7ac4da` | “independentes de infraestrutura” — fragment; key existence only |

### E. CLI matrix overclaim (auditor / help ≠ product UX)

| item_id | Reason |
|---------|--------|
| `DOD-definition-of-done-extra-383035c911` | “causa provável e próximo passo” — only command with `has_error_next_step=true` is the **auditor** error path (`audit_scope_boundaries --capability __no_such_cap__`), not workspace/ops product errors |
| `DOD-definition-of-done-extra-ef20844eb2` | “dado não é confiável” — only imports `FIELD_ABSENCE_STATES`; no operator-facing CLI reliability surface proven |
| `DOD-definition-of-done-extra-ea60d7c534` | “repetir sem inconsistência” — only `idempotent_help` (re-run `--help`), not execution idempotency |

### F. Coverage truth self-labeled “not accepted”

| item_id | Reason |
|---------|--------|
| `DOD-rol-1-definition-of-done-5412da3ad7` | Text includes `**Code-ready (not accepted):**` — campaign must not auto-PROVEN accept |
| `DOD-rol-1-definition-of-done-5eca319947` | Same self-label |
| `DOD-rol-1-definition-of-done-0c828cadb4` | Same self-label |

Clean semantic twins without the self-label remain in the surviving set.

## Surviving PROVEN (42)

### A_GOVERNANCE (11) — real policy/state machinery

- `a362715e4d` — checkbox requires evidence (`POLICY`)
- `75164c86da` — code without execution not done
- `59ea375492` — unit ≠ e2e
- `c94d735e7c` — mandatory items block gate
- `aa0cc46c52` — three rolls for project_done
- `f96c0779f9` — PARTIAL not gate-accepted
- `793fb2e8b5` — BLOCKED with owner/cause/next
- `a6aa7190ac` — field absence ≠ zero
- `794600a043` — external blocker stays visible
- `fa4a690d5c` — gate only DONE + legitimate NA
- `5865b9f10c` — reconstruct without chat history

### B_SCOPE_EXCLUDED (23) — static absence (redis demoted)

All obra/field modules, portal/public UI, multi-tenant, stripe, complex auth, aesthetic dashboard, auto-sign, auto-protocol, lawyer substitution, in-person representation, guarantees, win promises, object execution.

**Kept with residual caution:** `e3fab7341c` multi_tenant (soft disclaimer only in product code).

### C_CLI_UX (4)

- `fc3bf86724` — primary flow without web (workspace CLI)
- `bcceab4099` — help surfaces for recurring ops
- `3c79408c03` — human-readable help output
- `38c4c0fe6f` — limitations / claims_forbidden in dual coverage

### D_COVERAGE_TRUTH (4) — semantic code, not live 95%

- `bb9d5de811` — data_presence descriptive
- `3fb8978ae7` — no average masking
- `b9c4d94a8e` — contracts source ≠ tenders coverage
- `90c4a972f6` — data_presence never called coverage

**Limitation (explicit):** semantic/code only; not live 95% / recall / soak.

## What was correctly rejected (campaign did well)

- Human eval / Tiago manual validation → `REJECTED_HUMAN`
- 95% / recall / soak / VPS_OPERATIONAL themes → `REJECTED_NOT_LOW_HANGING` or live-dep
- Confenge / commercial queue → `REJECTED_PARALLEL_CONFLICT`
- Already ACCEPTED/checked items → not re-selected
- `mutated_dod: false`, `called_accept: false`

## Residual risks

1. **Stale scope-audit artifact** must be regenerated before any PR claims scope_ok with redis item.
2. **`comercial` theme** blocks legitimate “não assume … comercial” exclusion (fix classifier).
3. **CLI proofs** remain offline help-level; do not claim operator UX complete.
4. **Negative scope proofs** are static; no CI gate yet that fails on future obra modules.
5. **`.dod/manifest.yaml`** large local mutation — out of PR-A product scope but noisy; keep out of “proven product” claims.
6. Surviving coverage items are **code-ready semantics**, not operational coverage acceptance.

## Gate decision

**PASS_WITH_REDUCED_SET**

- Campaign claimed 59 PROVEN → **not** acceptable as-is (redis false accept + shared evidence inflation).
- After adversarial demotion: **42** honest low-hanging candidates remain.
- No protected-path product collision detected.
- Do **not** call `dod_controller accept` on demoted IDs.
- Prefer re-running scope audit after config freeze; fix redis item to NOT_PROVEN/REGRESSION in harness before merge narrative.

## Machine-readable

See `artifacts/campaigns/DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01/qa-verdict.json`.
