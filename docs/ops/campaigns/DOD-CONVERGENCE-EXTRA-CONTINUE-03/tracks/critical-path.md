# Critical path — DOD-CONVERGENCE-EXTRA-CONTINUE-03

**Subagent:** D-critical-path  
**Main SHA:** `432da028f1fed7d70d9d489e689cf3afa350571d`  
**As-of:** 2026-07-21  
**Scope:** next highest unlock **after** (1) normative reconciliation of ready acceptances and (2) public sanitization.

**Normative sources:** `DOD.md` §12.1 Golden path local · controller `next` / `status` · campaign preference (clean-env GP).

---

## 1. Recommended next item (highest unlock)

| Field | Value |
|-------|--------|
| **ID** | `DOD-rol-1-definition-of-done-596584406e` |
| **Literal text** | O golden path pode ser executado em ambiente limpo. |
| **Section** | ROL 1 › 12. Pipeline de inteligência e relatórios › 12.1 Golden path local |
| **DOD line** | 918 |
| **Category** | `MACHINE_ACTIONABLE` |
| **State (manifest)** | `OPEN` |
| **Why highest unlock** | Closes the reproducibility claim for the entire §12.1 chain already ACCEPTED on main (command → db → migrations → seed → planilha → fontes → persist → freshness → coverage). Proves GP is not host-state theater: empty DB → migrations → bootstrap → ledger. Unlocks install/bootstrap narratives, manual accept “Tiago consegue…”, and honest foundation for later integrity/coverage work. |

**Implementation already present (not greenfield):**

- `python3 -m scripts.ops.golden_clean_env --confirm-drop` (`scripts/ops/golden_clean_env.py`)
- Report: `output/golden-path/clean-env-report.json` (`ok`, `public_tables`, `golden_path.exit`, ledger path)
- Explicit non-claims: no `LOCAL_READY`, no “95% coverage from clean env alone”

---

## 2. Prerequisites (at most two)

| # | Kind | Item / condition | Why required |
|---|------|------------------|--------------|
| **P1** | Process / acceptance | Normative **accept on main** of ready GP post-coverage candidates that already have implementation evidence — **minimum:** `DOD-rol-1-definition-of-done-c73b1150d6` *“O golden path reconcilia snapshot de editais.”* (and batch-reprove peers when gates green) | Clean-env is the **closure** of the GP pipeline story. Accepting snapshot reconciliation first keeps the critical chain linear (coverage → snapshot → … → clean-env) and avoids claiming clean-env while the next open §12.1 functional step still sits OPEN with proof on disk. |
| **P2** | Infra (legitimate) | PostgreSQL local with authority to `DROP DATABASE` / `CREATE DATABASE` for a disposable name (default `extra_clean`), plus `--confirm-drop` operator flag | Clean-env proof is destructive by design; refuse path exits `3` without confirm. Not a human product decision — local/CI admin DSN only. |

**Assumed already done before this item starts (campaign gates, not counted as extra prereqs):**

- Wave0 reconciliation of open acceptance PRs vs main (`candidate_accept_items` reproved with CI + independent review).
- Public-repo sanitization / exposure decision path closed enough that clean-env evidence can be published without re-leaking HIGH residual commercial materials.

**Not a hard prereq:** `DOD-rol-1-definition-of-done-2b84ce6e0c` *“O projeto pode ser instalado em ambiente limpo.”* (install-wide, §5.1). Prefer GP clean-env first (narrower, higher unlock for §12); install can run as parallel track A.

---

## 3. Short DAG

```text
[ACCEPTED on main — foundation]
  command · db · migrations · seed · planilha · fontes mínimas
  · persist · freshness · coverage
           |
           v
[P1] Accept ready OPEN impl (min: snapshot reconcile c73b1150d6)
     + batch peers when gates green (ledger/logs/exit/meta/excel/pdf/idemp)
           |
           v
[P2] Local PG admin (DROP/CREATE) + public sanitization gate
           |
           v
★ 596584406e  "O golden path pode ser executado em ambiente limpo."
           |
     +-----+--------+------------------+
     |              |                  |
     v              v                  v
  hash planilha   reports específicos  2b84ce6e0c install limpo
  8990bd3e67      (editais/contratos/  (§5.1 — parallel)
                  concorrentes/valores)
     |
     v
  later: integrity 100% (7d2ae13087) · 95% coverage/recall · LOCAL_READY · human §15
```

**Critical spine (this campaign slice):**  
`coverage ACCEPTED` → **accept snapshot** → **clean-env GP** → (meta/hash gaps) → (domain reports) → (integrity / 95% / manual).

---

## 4. Acceptance criteria (Given / When / Then)

Literal item: **O golden path pode ser executado em ambiente limpo.**  
No threshold weakening. No claim of 95%, LOCAL_READY, VPS, or full live crawl completeness.

### AC-1 — Empty database bootstrap

- **Given** a PostgreSQL instance reachable via admin DSN and a disposable database name that does not hold production data  
- **When** `python3 -m scripts.ops.golden_clean_env --admin-dsn "$DSN" --db-name extra_clean --confirm-drop` runs  
- **Then** the tool recreates the DB from empty (`create_exit=0`), applies migrations, reports `public_tables >= 5`, and writes `clean-env-report.json` with `"ok": true`

### AC-2 — Golden path on that empty DB

- **Given** the freshly created empty database DSN from AC-1  
- **When** golden path is invoked as part of the clean-env harness (bootstrap path; crawl/freshness may be skipped only as documented for foundation)  
- **Then** `golden_path.exit == 0`, a ledger file is written under `output/golden-path/`, and the report records ledger path + clean DSN hint — without requiring pre-seeded host state outside the controlled recreate

### AC-3 — Fail-closed destructive guard

- **Given** the same command without `--confirm-drop`  
- **When** the operator runs `python3 -m scripts.ops.golden_clean_env ...` (no confirm)  
- **Then** the process refuses DROP/CREATE and exits non-zero (`3`) with an explicit message (no silent wipe)

### AC-4 — Evidence pack gates (controller accept)

- **Given** AC-1..AC-3 green on a commit reachable from `main`  
- **When** `verify` + `accept` run for `DOD-rol-1-definition-of-done-596584406e`  
- **Then** pack includes `acceptance_criteria.md`, substantive `acceptance_commands`/`tests`, `verify_result.json` `ok=true`, `ci_status.json` success with aligned `head_sha`, non-empty `independent_review.md`, and only then may DOD `[x]` be written — no `skip`/`xfail` to hide failure; dry-run alone is **not** accept

### AC-5 — Non-claims (explicit)

- **Given** a successful clean-env report  
- **When** evidence is reviewed  
- **Then** the pack **must not** assert `LOCAL_READY`, “95% coverage”, full live source SLA, or that generic panorama Excel/PDF satisfies *relatório de editais/contratos/concorrentes/referências de valores*

---

## 5. Four parallel tracks (while ★ is prepared / after P1)

| Track | Focus | Items / work | Collision note |
|-------|--------|--------------|----------------|
| **T1 — Accept-ready GP plumbing** | Batch accept OPEN with impl evidence on main | snapshot `c73b1150d6`; Excel `d5c6584cb7`; PDF `ddfcf1ec8a`; ledger `7d4698cf6a`; logs `05418e32b2`; exit code `3500c05a66`; idempotency `98c4820f19`; timing `d134dd8ca2`; code version `8d63225d5b`; schema version `d495570f4e` | Do **not** treat generic PDF/Excel as domain reports |
| **T2 — Meta gap: planilha hash in run meta** | Small impl if accept requires top-level meta | `8990bd3e67` *O hash da planilha é registrado.* — step details already carry `sha256` / `canonical_ids_sha256`; confirm ledger **run-level** registration before accept | May touch `scripts/golden_path.py` — single owner |
| **T3 — Domain-specific reports** | Real product outputs | `0786ea0c31` editais; `f8f4f1b0a9` contratos; `44e0c95c6e` concorrentes; `7b7184ebb4` referências de valores | **Not** proven by panorama PDF alone |
| **T4 — Install-wide clean env (§5.1)** | Broader than GP | `2b84ce6e0c` *O projeto pode ser instalado em ambiente limpo.* (+ deps declaration if still OPEN) | Parallel; must not block ★ |

---

## 6. Blockers (legitimate only)

| Blocker | Applies? | Note |
|---------|----------|------|
| Human decision (repo private vs OSS sanitize) | **Only if** public residual HIGH still blocks publishing clean-env evidence | From public-exposure track; product owner |
| Credential / secret | No for clean-env itself | Uses local test DSN |
| Live source / PNCP | No for foundation clean-env | Harness documents `--skip-crawl` / `--skip-freshness` / `--allow-zero` |
| Infra | **Yes (P2)** | PG must allow DROP/CREATE; vector extension optional skip is documented |
| Billing / CI public | Resolved historically | Re-check if CI gate fails on accept |

No fake “blocked on 95%” for this item.

---

## 7. Why NOT the controller’s current `next`

| | Controller `next` | This recommendation |
|--|-------------------|---------------------|
| **ID** | `DOD-rol-1-definition-of-done-7d2ae13087` | `DOD-rol-1-definition-of-done-596584406e` |
| **Text** | A integridade do snapshot ativo é 100%. | O golden path pode ser executado em ambiente limpo. |
| **Section** | §15 Aceite manual (end-stage) | §12.1 Golden path local (pipeline) |

**Reasons to override for campaign critical path:**

1. **Stage mismatch:** 100% active-snapshot integrity is a late §15 gate. Neighbor items are 95% coverage/recall and `LOCAL_READY`. It is not the next unlock after coverage ACCEPTED.
2. **Controller scoring artifact:** `score_item` treats `"integridade"` and `"golden path"` at the same critical tier (`5`), but clean-env has `needs_clean_db=true` → higher `rough_cost`, so the heuristic prefers `7d2ae13087` (cheaper line) despite **lower product unlock** for the current wave.
3. **Missing dependency graph in manifest:** items have empty `dependencies[]` / `unlock_count=0`, so the harness cannot see that integrity presupposes reconciliation + operational active snapshot + scale — not just a cheap checkbox.
4. **Evidence reality:** snapshot **reconciliation** proof exists (`c73b1150d6` dual ledger, ids_sha256 stable) but is still OPEN; integrity 100% is a stronger claim and must not leapfrog clean-env / accept batch.
5. **Campaign preference (explicit):** after reconciliation + security → prefer clean-env GP `596584406e`.

**When to do integrity:** after GP chain + active snapshot ops are accepted and integrity can be measured fail-closed at 100% without threshold games — not as wave-0 next implement.

---

## 8. Why NOT 95% coverage / 95% recall yet

| Gate | DOD | Current evidence (honest) |
|------|-----|---------------------------|
| Cobertura auditável editais ≥ 95% | §15 | Coverage calculation ACCEPTED with **den=1093, num=214, pct≈19.58%** — calculation proven, threshold **not** met |
| Cobertura auditável contratos ≥ 95% | §15 | Live/ops work exists historically; not closed as 95% audit on this main SHA for this campaign |
| Recall editais relevantes ≥ 95% amostra-ouro | §15 | Requires gold sample + measurement protocol; not unblocked by clean-env alone |
| Integridade snapshot ativo 100% | §15 | Distinct from “reconciliation ran”; needs active snapshot definition + 100% integrity proof |

**Rules:** do not lower thresholds; do not `skip`/`xfail`/mock to simulate 95%; job skipped ≠ pass; absence of run ≠ success. Clean-env report **forbids** claiming 95% from bootstrap alone.

---

## 9. Ready OPEN map (§12.1 after coverage) — accept vs implement

| ID | Literal | Impl signal | Action class |
|----|---------|-------------|--------------|
| `c73b1150d6` | O golden path reconcilia snapshot de editais. | `run_snapshot_reconciliation` + dual ledger evidence | **Accept-first (P1 min)** |
| `d5c6584cb7` | O golden path gera Excel. | panorama xlsx proof | Accept (generic; ≠ relatório de editais) |
| `ddfcf1ec8a` | O golden path gera PDF. | panorama pdf `%PDF` proof | Accept (generic; ≠ domain reports) |
| `7d4698cf6a` | O golden path gera ledger. | ledger JSON + steps | Accept |
| `05418e32b2` | O golden path gera logs. | log path under output/golden-path | Accept |
| `3500c05a66` | O golden path retorna exit code não zero em qualquer gate obrigatório. | essential_fail=2, freshness_fail=3 | Accept |
| `98c4820f19` | O golden path pode ser reexecutado sem duplicação. | dual ledger + counts | Accept |
| `596584406e` | O golden path pode ser executado em ambiente limpo. | `golden_clean_env.py` | **★ Implement verify → accept** |
| `d134dd8ca2` | O tempo total de execução é registrado. | `wall_clock_ms` | Accept if ledger on main proves |
| `8d63225d5b` | A versão do código é registrada. | `collect_run_metadata.git_sha` | Accept if wired into persisted ledger on main |
| `8990bd3e67` | O hash da planilha é registrado. | step details yes; run meta may need tighten | Track T2 |
| `d495570f4e` | A versão do schema é registrada. | `schema_version=migrations_count=N` | Accept if wired |
| `0786ea0c31` / `f8f4f1b0a9` / `44e0c95c6e` / `7b7184ebb4` | Relatórios específicos | Not panorama | Track T3 — **do not** close with generic PDF |

---

## 10. Immediate operator sequence (after wave0 audits)

1. Reprove/accept ready GP candidates on **main** (CI + independent review + controller gates) — prioritize `c73b1150d6`.  
2. Confirm public sanitization residual is not blocking evidence publish.  
3. `start DOD-rol-1-definition-of-done-596584406e`  
4. Run clean-env with `--confirm-drop` on disposable DB; archive report + ledger into `.dod/evidence/DOD-rol-1-definition-of-done-596584406e/`.  
5. `verify` → independent review → `accept` (only with gates).  
6. Parallel: T2 hash meta if still open; T3 domain reports only with real outputs; **defer** `7d2ae13087` and all 95% items.

---

## 11. One-line recommendation

**Next highest unlock:** `DOD-rol-1-definition-of-done-596584406e` — *O golden path pode ser executado em ambiente limpo.* — after accepting snapshot reconciliation (min) and confirming PG DROP/CREATE + sanitization; **not** controller next *integridade 100%* (§15 late gate); **not** 95% coverage/recall (measured ~19.6% coverage; recall/gold sample not ready).
