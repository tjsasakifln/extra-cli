# EXTRA-CLI Strategic Execution — Fase 0 Diagnosis

**Campaign umbrella:** `/goal` EXTRA-CLI strategic convergence  
**Date (UTC):** 2026-07-30  
**Executor:** autonomous agent (Grok Build)  
**Remote:** `https://github.com/tjsasakifln/extra-cli`

## 1. Initial repository state

| Item | Value |
|------|--------|
| Working tree branch (dirty) | `work/recurring-reports-pr2` (ahead 4 / behind 10 vs origin/main) |
| **origin/main at start** | `75cf6df09c4dd138d67ffcb27a480df97019644d` |
| **origin/main after PR #180 merge** | `2c65bf434e3d580af54f9e79117b409f24aba108` |
| Dirty tree | Many local campaign artifacts, Makefile staged deletes for recurring delivery, untracked worktrees — **not used as integration base** |
| Worktree for PR #179 | `/mnt/d/extra-cli-wt-confenge-activation-01` → `campaign/confenge-skeptic-remediation` |
| Worktree for PR #180 | `/mnt/d/extra-cli-dod-low-hanging-promo` → `campaign/dod-low-hanging-main-reaccept-publish` |

**Rule adopted:** never integrate from the dirty primary workspace; use dedicated worktrees and `origin/main`.

## 2. Open strategic PRs (baseline)

| PR | Title | State | Base | Head | Checks |
|----|-------|-------|------|------|--------|
| **#180** | fix(dod): re-accept low-hanging items on main | **MERGED** (this session) | main@75cf6df0 | `42c054bf…` | All green incl. Edital Relevance Foundation, Test All, Reviewability |
| **#179** | fix(commercial): Top10 official RFB gate + holdout | OPEN | main@75cf6df0 → rebased via merge | `affcba5b…` (+ merge) | **Edital Relevance Foundation FAILED**; rest green |
| **#133** | bid submission readiness | DRAFT/BLOCKED | stale main | corpus blocker #137 | Not strategic for merge |

## 3. PR #179 failure root cause

Job: **Edital Relevance Foundation**  
Failed step: **`sector_classifier + CONFENGE policy isolation (no feature allowlist)`**

Mechanism:

1. Campaign rebinds freeze SHAs so `EXECUTED_CODE_SHA == FINAL_CODE_FREEZE_SHA`.
2. Post-freeze delta is only evidence-lag under `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/`.
3. `verify_code_freeze()` correctly returns `ok=True`, `protected_changed=[]`, `free_changed=[]`.
4. CI assert required `free` non-empty:
   ```python
   assert any("edital_relevance" in p ...) or free, free
   ```
5. Empty `free` on a freeze-self-bound commercial tip → **false FAIL** (not a sector_classifier coupling bug in product code).

**Not a product regression in Top10 gate logic.** Official RFB gate tests: 6/6 local pass; commercial suite 181 pass after merge.

## 4. DoD controller snapshot (start)

```
campaign=DOD-CONVERGENCE-EXTRA-CONTINUE-03 phase=audit
active=None next=DOD-35-gates-consolidados-8e6b4fa8ad
total=1462 audited_accepted=129 claimed_checked=443 proof_debt=360
state_ACCEPTED=441 OPEN=1020 blocked=1 acceptance=8.82%
```

PR #180 re-accepts 37 low-hanging items with `main_gate=ok` (process §15 max-2-PR exception disclosed).

## 5. Canonical commands (discovered, not invented)

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m pytest tests/ -q --tb=no -x
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
make extra-weekly   # python3 -m scripts.ops.weekly_cycle --strict
python3 tools/dod_controller.py status|next|start|verify|accept
python3 -m scripts.ops.check_generated_artifacts_policy --base origin/main
python3 -m scripts.ops.check_pr_reviewability --base origin/main
```

Existing surfaces relevant to later phases:

- Profile: `config/client_profiles/extra.yaml`, `scripts/opportunity_intel/profile.py`, `scripts/commercial_leads/profile.py`, ADR-022
- Weekly: `scripts/ops/weekly_cycle.py` / `make extra-weekly`
- Review: `scripts/commercial_leads/review.py`, `scripts/opportunity_intel` human review
- Top10 official gate: `scripts/commercial_leads/top10_gate.py` (PR #179)
- Soak: systemd on `ec-prod` — do not restart / rebind locks

## 6. Known blockers (honest)

| Blocker | Impact |
|---------|--------|
| No human acceptance recorded for Extra decision loop | Cannot emit `PASS_EXTRA_DECISION_LOOP_ACCEPTED` |
| Official RFB bulk dataset may be absent locally | Top10 commercial remains `FAIL_TOP10_VALIDITY` until ingest |
| Public tender corpus blocked (#137 / PR #133) | No operational recall / bid readiness accept |
| Soak in progress | Must not restart; only observe / report |
| Dirty primary workspace | Integration only via worktrees |

## 7. Execution sequence adopted

1. **Fase 0** — this diagnosis (versioned).
2. **Fase 1.1** — merge PR #180 (green, up-to-date).
3. **Fase 1.2** — merge `origin/main` into #179; re-verify freeze isolation + tests; push; merge when CI green.
4. **Fase 2** — campaign `EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01` on clean main (profile → actionable → review → package).
5. **Fase 3** — RFB ingest + commercial reprocess (or blocked infrastructure).
6. **Fase 4–6** — corpus infra / soak health / contract pilot only if real inputs exist.
7. Handoff + DoD promotions only with evidence.

## 8. Soak preservation

- No timer/crawler/writer/lock changes planned.
- No soak restart.
- No synthetic `NEW_TENDER` / commercial events for DoD.

## 9. Risks of regression

- Re-freeze loops on CONFENGE artifacts (known PR-budget pressure).
- Coupling of CI isolation assert to empty `free_changed`.
- Dirty local tree accidentally committed (mitigated by worktrees).
- Promoting DoD without human acceptance or official RFB (forbidden).

---

*Generated as required Phase 0 deliverable before code changes beyond PR convergence.*
