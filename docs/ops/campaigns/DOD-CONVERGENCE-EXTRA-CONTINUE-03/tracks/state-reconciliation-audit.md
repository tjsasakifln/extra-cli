# State Reconciliation Audit — Subagent B

**Campaign:** `DOD-CONVERGENCE-EXTRA-CONTINUE-03`  
**Auditor:** Subagent B (read-only normative state)  
**Worktree:** `/mnt/d/extra-consultoria-continue-03`  
**Branch (campaign):** `campaign/continue-03-wave0`  
**main SHA (authoritative):** `432da028f1fed7d70d9d489e689cf3afa350571d`  
**Repo:** `tjsasakifln/extra-cli`  
**Audited at:** 2026-07-21T22:15:00Z (approx.)  
**Scope:** `DOD.md` × `.dod/manifest.yaml` × `.dod/state.json` × `.dod/log.jsonl` × origin/main × open accept PRs #86/#89/#91/#93

> **Method note:** `dod_controller.py audit` and `next` **write** (`save_manifest` / `save_state`). Per MODE read-only, those commands were **not** executed. Metrics and divergences below are reconstructed from the latest controller scan/audit already persisted at `2026-07-21T21:59:32Z` / `21:59:45Z`, plus static cross-checks of DOD/manifest/log/PRs.

---

## 1. Current metrics (authoritative local controller state)

Source: `.dod/state.json` (`updated_at: 2026-07-21T22:00:25Z`) after scan+audit on this worktree.

| Metric | Value | Honesty assessment |
|--------|------:|--------------------|
| `total` | 1356 | OK — matches manifest item count (1355 live + 1 orphan) |
| `accepted` / `accepted_state` | 317 | **State-machine count only** — not fail-closed progress |
| `claimed_checked` | 319 | **Honest as claim**, **not** as acceptance (`[x]` / `dod_checked`) |
| `audited_accepted` | **9** | **Only honest progress metric** (ACCEPTED + commit + non-weak evidence_audit) |
| `acceptance_pct` | **0.66%** | Fail-closed: `9/1356` — **correct** |
| `claimed_pct` | 23.53% | Marketing-risk if misread as “done” |
| `evidence_located` | 119 | Paths exist for some refs (ok/partial) |
| `evidence_reproduced` | 10 | `verify_result.json` with `ok=true` under `.dod/evidence/<id>/` |
| `proof_debt` | **314** | Claimed or ACCEPTED without audited acceptance |
| `open` | 1038 | |
| `blocked` | 1 | `BLOCKED_HUMAN` (Tiago package accept) |
| `verified` / `in_progress` / `implemented` | 0 / 0 / 0 | No active item mid-pipeline |
| Last audit | `divergence_count=399`, `proof_debt=314` | log event `2026-07-21T21:59:45Z` |

### Metrics honesty (explicit)

| Label | Safe to report as progress? | Why |
|-------|----------------------------|-----|
| `claimed_checked` (319) | **NO** | Includes historical `[x]` without acceptance_commit / pack |
| `accepted_state` (317) | **NO** as “done” | Bootstrap ACCEPTED_EXISTING + weak evidence dominate |
| `audited_accepted` (9) | **YES** | Only items with commit identity + non-missing/unverified audit |
| `evidence_reproduced` (10) | **Partial** | Verify ran; does not alone mean ACCEPTED/merged |
| `proof_debt` (314) | **YES as debt** | Inventory of honesty gap, not progress |
| `acceptance_pct` 0.66% | **YES** | Fail-closed denominator |

**Decomposition of claimed_checked 319:**

- `state=ACCEPTED` with `dod_checked=true`: ~317  
- `state=BLOCKED_HUMAN` with `dod_checked=true`: 1 (`0bb5ebff58` — Tiago human accept; still `[x]` in DOD)  
- `state=OPEN` with `dod_checked=true` + orphan: 1 (`DOD-definition-of-done-extra-fd43ee57aa` — demoted double-book of full suite)  
- Total ≈ 319

**Audited accepted (9) — items with non-null `acceptance_commit` still in ACCEPTED:**

| ID | Topic | PR | evidence_audit |
|----|-------|----|----------------|
| `b42bd49e1d` | GP comando canônico | #69 | partial |
| `16267c473a` | GP sobe/valida banco | #70 | partial |
| `7aa1d9bfc5` | GP migrations | #71 | ok |
| `e9a3ea535d` | GP seed | #72 | (commit present) |
| `e405d6a61c` | GP planilha | #75 | ok |
| `faaf47c790` | GP fontes mínimas | #77 | ok |
| `9c996cb14e` | GP persiste | #79 | ok |
| `94ff481872` | GP freshness exec | #81 | partial |
| `4efe05fc94` | GP cobertura | #83 | ok |

Orphan `fd43ee57aa` still has `acceptance_commit` but **state=OPEN** → excluded from audited_accepted.

---

## 2. Controller / campaign identity fields (stale)

| Field | Observed | Expected for CONTINUE-03 | Severity |
|-------|----------|--------------------------|----------|
| `campaign_id` | `DOD-CONVERGENCE-EXTRA-CONTINUE-02` | `DOD-CONVERGENCE-EXTRA-CONTINUE-03` | **CRITICAL** |
| `active_branch` | `campaign/continue-02-accept-planilha` | `campaign/continue-03-wave0` or null | **HIGH** |
| `main_sha` | `432da028…` | same (matches PR #92 merge) | OK |
| `active_item_id` | `null` | null until start | OK |
| `active_run_id` | `run-20260721T022411Z` | stale run from e9a3 seed accept | **MEDIUM** |
| `next_eligible_id` | `DOD-rol-1-definition-of-done-7d2ae13087` | after re-score post-accept-queue | **MEDIUM** (suboptimal) |
| `phase` | `converge` | `converge` / wave0-audit | OK-ish |
| `resume_step` / `next_step` | `accept` / `start` | recompute after reconcile | **MEDIUM** |
| `notes` | “Next: freshness gate” | freshness already ACCEPTED (#81) | **HIGH** (stale narrative) |
| `last_report_path` | `/mnt/d/extra-consultoria-dod-conv/.dod/evidence/report-…` | this worktree path | **MEDIUM** (foreign worktree) |
| Campaign status file | CONTINUE-03 | — | OK (separate file) |

**Conclusion:** Controller state was never promoted from CONTINUE-02 identity; branch pointer frozen on planilha accept branch long after main advanced to `432da028`.

---

## 3. Critical divergences (severity-ordered)

### CRITICAL

| ID | Divergence | Detail |
|----|------------|--------|
| C1 | **Campaign identity lag** | `state.campaign_id=CONTINUE-02` while ops campaign is CONTINUE-03 |
| C2 | **Accept PRs would clobber newer controller state** | All of #86/#89/#91/#93 rewrite whole `.dod/state.json` + large slices of `manifest.yaml` + append-biased `log.jsonl` from **older bases** (except #93 base == current main) |
| C3 | **Proof-debt mass** | 314 items claimed/accepted without audited evidence; last audit `divergence_count=399` |
| C4 | **PR #86 mergeable_state=dirty** | Base main `8daf991…` far behind `432da028`; cannot merge cleanly; naive force-merge would rewind metrics/main_sha |

### HIGH

| ID | Divergence | Detail |
|----|------------|--------|
| H1 | **Stale `active_branch`** | Still `campaign/continue-02-accept-planilha` |
| H2 | **Stale notes / next narrative** | Notes claim next=freshness; freshness ACCEPTED; coverage ACCEPTED |
| H3 | **OPEN §12.1 items with evidence packs on disk** | 10 packs present; manifest still OPEN/`dod_checked=false`; DOD still `[ ]` — implementation PRs merged (#85/#88/#90/#92) but accept PRs not merged |
| H4 | **`next_eligible_id` ignores ready accept queue** | Points to `7d2ae13087` (“integridade do snapshot ativo é 100%”, line 1093, no pack) while 10 GP items have packs ready |
| H5 | **Orphan double-book** | `fd43ee57aa` ORPHANED_FROM_DOD, OPEN, still has pack + acceptance_commit + priority_boost 100 |
| H6 | **BLOCKED_HUMAN still `[x]` in DOD** | `0bb5ebff58` demoted in manifest but DOD line 269 remains checked — contributes to claimed_checked without ACCEPTED |

### MEDIUM

| ID | Divergence | Detail |
|----|------------|--------|
| M1 | **Accepted with weak/partial path audit** | e.g. `b42bd49e1d`, `16267c473a`, `94ff481872` — still audited if commit present, but path hygiene debt |
| M2 | **Stale item justification** | `9c996cb14e` justification still “do not accept until persisted>0” while state=ACCEPTED |
| M3 | **Blocker file residual** | `.dod/blockers/DOD-rol-1-definition-of-done-9c996cb14e.json` has `resolved_at` but item still lists TECHNICAL blocker object |
| M4 | **log vs accept PR timelines** | Local log ends with scan/audit 21:59; missing accept events that live only on PR branches (86/89/91/93) |
| M5 | **Foreign last_report_path** | Points at `extra-consultoria-dod-conv` worktree |

### LOW

| ID | Divergence | Detail |
|----|------------|--------|
| L1 | **No duplicate item IDs** in manifest (IDs unique by construction `DOD-{slug}-{fp10}`) |
| L2 | **No log-only orphan IDs** unknown to manifest for recent accepts |
| L3 | **1 manifest orphan fingerprint** | `fd43ee57aa` no longer in DOD.md text (expected after rescan) |

---

## 4. Checkbox × manifest alignment (summary)

| Class | Count / note |
|-------|----------------|
| Manifest `state=ACCEPTED` | 317 |
| Manifest `dod_checked=true` | 319 |
| DOD `[x]` lines | ≥199 matched by grep (file large; controller scan uses full parse → claimed 319) |
| Last controller audit | **399 divergences** (checkbox mismatches + accepted_weak_evidence + proof_debt_claimed_without_evidence + 1 orphan) |
| `accepted_but_unchecked` | Not expected for continue-02 core GP items (those are `[x]`) |
| `checked_but_not_accepted` | Dominant residual: historical `[x]` still OPEN/BLOCKED or ACCEPTED without commit |
| OPEN GP with pack but DOD `[ ]` | **10 items** (see §5) — intentional until accept merge |

§12.1 on **current main / worktree DOD.md** (lines 898–924):

- `[x]` through coverage (`4efe05fc94`)
- Still `[ ]` for: snapshot, domain reports (4), Excel, PDF, ledger, logs, exit≠0, idempotency, clean env, wall clock, git sha, planilha hash, schema, report period/limitations

---

## 5. OPEN golden-path items with evidence packs present

Evidence dirs under `.dod/evidence/` with **manifest state still OPEN**:

| Item ID | Text (short) | Accept PR | Impl PR | Pack maturity |
|---------|--------------|-----------|---------|---------------|
| `c73b1150d6` | reconcilia snapshot editais | **#89** | #88 | README/proof/ledger + PR adds verify/ci/review |
| `d5c6584cb7` | gera Excel | **#91** | #90 | xlsx + proof + PR verify |
| `ddfcf1ec8a` | gera PDF | **#91** | #90 | pdf + proof + PR verify |
| `7d4698cf6a` | gera ledger | **#86** | #85 | pack + PR meta gates |
| `05418e32b2` | gera logs | **#86** | #85 | pack + PR meta gates |
| `3500c05a66` | exit code ≠0 | **#86** | #85 | pack + PR meta gates |
| `d134dd8ca2` | tempo total | **#86** | #85 | pack + PR meta gates |
| `8d63225d5b` | versão código | **#86** | #85 | pack + PR meta gates |
| `d495570f4e` | versão schema | **#86** | #85 | pack + PR meta gates |
| `98c4820f19` | reexec sem duplicação | **#93** | #92 | ledger dual + proof; verify on PR |

**Count: 10 OPEN with packs present.**

Also present but already ACCEPTED: packs for `b42bd49e1d`, `16267c473a`, `7aa1d9bfc5`, `e9a3ea535d`, `e405d6a61c`, `faaf47c790`, `9c996cb14e`, `94ff481872`, `4efe05fc94`, plus orphan `fd43ee57aa`.

---

## 6. Overwrite risk matrix — PRs #86 / #89 / #91 / #93

| PR | Title | Head branch | Base SHA (at open) | vs main `432da028` | Touches | Mergeable | Overwrite risk | If merged naively |
|----|-------|-------------|--------------------|--------------------|---------|-----------|----------------|-------------------|
| **#86** | accept ledger/logs/meta/exit (6 items) | `campaign/continue-02-accept-meta` | base `8daf991…` (old) | **far behind** | `DOD.md`, `manifest.yaml`, **`state.json`**, `log.jsonl`, 6× evidence gate files | **dirty / not mergeable** | **CRITICAL** | Rewinds `main_sha`→`07e9986`, metrics to 321 ACCEPTED fantasy on stale base; **loses** freshness/coverage/snapshot/excel/pdf/idempotency accepts already on main timeline; truncates log history relative to CONTINUE-03 rescan |
| **#89** | accept snapshot `c73b1150d6` | `campaign/continue-02-accept-snapshot` | base `a0caf2ac…` | behind (pre-#90/#92) | DOD checkbox + item ACCEPTED + **full state.json metrics rewrite** + log append | clean* | **HIGH** | State metrics set as if only +1 from stale 317 baseline; can **drop** later local scan fields (`main_sha` already newer, campaign notes); conflicts with concurrent accept PRs on same three files |
| **#91** | accept Excel+PDF | `campaign/continue-02-accept-reports` | base `5a3ab319…` | parent of #92 merge | 2 items ACCEPTED + **state.json** (sets `main_sha=$MERGE`, notes next idempotency) + log | clean* | **HIGH** | Same three-file collision; state assumes product PRs list up to #90 only |
| **#93** | accept idempotency `98c4820f19` | `campaign/continue-02-accept-idempotency` | base **`432da028`** (= current main) | **current** | 1 item + state (+1 ACCEPTED) + log + DOD | clean* | **MEDIUM** (safest base) | Still rewrites whole `state.json` (campaign_id remains CONTINUE-02; active_branch still planilha); safe only if merged **alone after rebase of others** or as last of a **rebase-serial** chain |

\*GitHub reported `mergeable=true` for #89/#91/#93 at audit time, but concurrent merges of sibling accept PRs will immediately dirty the others because they all edit the same three controller files.

### Collision pattern (root cause)

Every accept PR treats controller files as **whole-file snapshots**, not item-scoped patches:

1. `.dod/manifest.yaml` — huge file; item-local ACCEPTED patches OK in isolation, **rebase required** after each merge  
2. `.dod/state.json` — **metrics + notes + main_sha + active_branch** always rewritten  
3. `.dod/log.jsonl` — append-only **if** bases share tip; otherwise conflict or silent history loss  
4. `DOD.md` — independent line checkboxes can merge if non-overlapping; #86/#89/#91/#93 touch **different lines** → combinable after rebase

### Severity if all four merged in random order

- **Highest damage:** #86 first or last without rebase → state/main_sha/log chaos  
- **Medium damage:** #89 then #91 without rebase → second wins metrics, first’s ACCEPTED may survive in manifest if merge is 3-way clean on item hunks, but **state metrics lie**  
- **Lowest damage:** #93 only → +1 audited item on current main, still leaves CONTINUE-02 identity  

---

## 7. Completed items still selected as next?

| Question | Answer |
|----------|--------|
| Is `next_eligible_id` already ACCEPTED? | **No** — `7d2ae13087` is OPEN |
| Is next the best unlock given packs ready? | **No** — 10 OPEN items with packs should be drained via accept reconcile before opening new MACHINE_ACTIONABLE work |
| Does controller “select completed as next”? | **Not literally** — but **selects wrong OPEN** while accept queue is pending |

---

## 8. Orphans / duplicates / log integrity

| Check | Result |
|-------|--------|
| Duplicate IDs in manifest | **None observed** |
| Orphan in manifest not in DOD | **1:** `DOD-definition-of-done-extra-fd43ee57aa` (`ORPHANED_FROM_DOD`, demoted OPEN) |
| IDs in log not in manifest | **None** for accept/verify events of known IDs |
| IDs in accept PRs not in manifest | **None** — all target known §12.1 fingerprints |
| Log tip (local) | scan 21:59 + audit 21:59; **no** accept events for c73b/d5c6/ddfc/meta/idemp (those exist only on PR heads) |
| Evidence without ACCEPTED | 10 OPEN packs (§5) — intentional queue |

---

## 9. Recommended single reconciliation approach

**Do not merge any of #86/#89/#91/#93 as-is onto main without rebase onto `432da028` and item-scoped state regeneration.**

### Preferred order (item commits, not PR-number order)

Work **one accept item (or tightly coupled batch) at a time** from a **fresh branch off current main**, replaying only the **item delta** + evidence gate files. Suggested sequence:

1. **Close or supersede #86** (dirty / multi-item). Split into **one PR per item or one rebased multi-item PR** regenerated on `432da028`:
   - `7d4698cf6a` ledger  
   - `05418e32b2` logs  
   - `3500c05a66` exit≠0  
   - `d134dd8ca2` wall clock  
   - `8d63225d5b` git sha  
   - `d495570f4e` schema version  
2. **#89 content** → accept `c73b1150d6` (snapshot) — re-verify on main if verify head ≠ `432da028`  
3. **#91 content** → accept `d5c6584cb7` + `ddfcf1ec8a` (Excel+PDF) — re-verify  
4. **#93 content** → accept `98c4820f19` (idempotency) — already base-aligned; still re-run `verify` if any gate files missing on main  
5. After each merge:  
   ```bash
   python3 tools/dod_controller.py scan
   python3 tools/dod_controller.py audit --json
   python3 tools/dod_controller.py next --json
   ```
6. Only then `start` a **new** OPEN item without pack (e.g. domain report lists or clean-env), not `7d2ae13087` unless score still wins after packs drained.

### Forbidden shortcuts

- Do **not** `git merge` #86 into main to “batch accept 6”  
- Do **not** copy PR branch `state.json` over CONTINUE-03 state  
- Do **not** mass-uncheck proof_debt to “fix” metrics  
- Do **not** mark `audited_accepted` by editing metrics by hand  

### Alternative (if coordinator must keep PR numbers)

For each PR: `gh pr checkout N && git rebase origin/main`, resolve `manifest`/`DOD.md` by **keeping both sides’ ACCEPTED items**, regenerate `state.json` via controller (`scan`+metrics), append-only merge `log.jsonl`, force-push branch, then merge **serially** in order #89 → #91 → #93 → rebuilt #86.

---

## 10. Controller fields that MUST be fixed after merge (coordinator)

After any successful accept merge (or batch reconcile), set via controller + explicit edit of non-metric identity fields:

| Field | Target value / action |
|-------|------------------------|
| `campaign_id` | `DOD-CONVERGENCE-EXTRA-CONTINUE-03` |
| `active_branch` | current campaign branch or `null` when idle |
| `main_sha` | `git rev-parse origin/main` (must stay = merge tip) |
| `active_item_id` | `null` unless `start` in flight |
| `active_run_id` | new run id on next `start`, or null |
| `metrics.*` | **only** via `scan`/`metrics_from_items` — never hand-edit to match PR fantasy |
| `next_eligible_id` | recompute with `next` after scan |
| `phase` | `converge` (or campaign-defined) |
| `resume_step` / `next_step` | `start` or item-specific; clear stale `accept` if idle |
| `notes` | rewrite: list actually ACCEPTED PRs (#75–#83 core + any new); **remove** “Next: freshness gate” |
| `last_report_path` | path under this worktree after `report` |
| `billing_blocker` | keep RESOLVED |
| Manifest item fields for newly accepted | `state=ACCEPTED`, `dod_checked=true`, `acceptance_commit`, `acceptance_pr`, `accepted_at`, history accept event, evidence_audit refresh |
| DOD.md | `[x]` **only** for items that pass accept gates on main |
| log.jsonl | append verify/accept only; never truncate |
| Orphan `fd43ee57aa` | keep OPEN; do not re-ACCEPT; clear `priority_boost` if it distorts `next` |
| BLOCKED_HUMAN `0bb5ebff58` | keep BLOCKED; consider unchecking DOD `[x]` or leave with proof_debt explicit |

### Post-reconcile honesty target (if all 10 OPEN packs accepted cleanly)

Approximate after +10 audited accepts (order-dependent):

| Metric | Now | After 10 clean accepts (approx.) |
|--------|----:|----------------------------------:|
| audited_accepted | 9 | **~19** |
| accepted_state | 317 | **~327** |
| claimed_checked | 319 | **~329** |
| open | 1038 | **~1028** |
| proof_debt | 314 | **~304** (only if those 10 leave proof_debt) |
| acceptance_pct | 0.66% | **~1.4%** |

Still far from 95% operational coverage claims — do not conflate GP §12.1 accept with universe coverage.

---

## 11. Controller command stand-ins (read-only equivalents)

### `status --json` (equivalent payload)

```json
{
  "campaign_id": "DOD-CONVERGENCE-EXTRA-CONTINUE-02",
  "phase": "converge",
  "active_item_id": null,
  "next_eligible_id": "DOD-rol-1-definition-of-done-7d2ae13087",
  "main_sha": "432da028f1fed7d70d9d489e689cf3afa350571d",
  "metrics": {
    "total": 1356,
    "accepted": 317,
    "accepted_state": 317,
    "claimed_checked": 319,
    "audited_accepted": 9,
    "evidence_located": 119,
    "evidence_reproduced": 10,
    "proof_debt": 314,
    "open": 1038,
    "blocked": 1,
    "acceptance_pct": 0.66,
    "claimed_pct": 23.53
  },
  "critical_path_hint": "A integridade do snapshot ativo é 100%."
}
```

### `audit --json` (from last run, not re-executed)

```json
{
  "ok": false,
  "divergence_count": 399,
  "proof_debt_count": 314,
  "parsed_count": 1355,
  "manifest_count": 1356,
  "note": "claimed_checked is not audited_accepted; do not treat [x] alone as ACCEPTED"
}
```

### `next --json` (stand-in; would write state if run)

```json
{
  "ok": true,
  "item": {
    "id": "DOD-rol-1-definition-of-done-7d2ae13087",
    "text": "A integridade do snapshot ativo é 100%.",
    "state": "OPEN",
    "category": "MACHINE_ACTIONABLE"
  },
  "warning": "Suboptimal while 10 OPEN items have evidence packs pending accept merge"
}
```

---

## 12. Executive summary

1. **Honest progress is 9 audited_accepted / 1356 (0.66%)**, not 319 checked or 317 ACCEPTED-state.  
2. **CONTINUE-02 identity is frozen** in `.dod/state.json` (campaign_id, active_branch, notes) while main and CONTINUE-03 campaign advanced.  
3. **10 OPEN §12.1 items already have evidence packs** and open accept PRs; none are ACCEPTED on main yet.  
4. **PRs #86/#89/#91/#93 all rewrite controller state**; #86 is **dirty/critical** overwrite risk; #93 is base-aligned but still identity-stale.  
5. **Single safe path:** supersede/rebase accepts onto `432da028`, merge **serially**, regenerate metrics via controller, then fix campaign identity fields for CONTINUE-03.  
6. **Do not** treat next=`7d2ae13087` as the wave-0 priority until the accept queue is drained.

---

## 13. Sources

- Local: `.dod/state.json`, `.dod/manifest.yaml`, `.dod/log.jsonl`, `DOD.md`, `.dod/evidence/**`, `docs/ops/campaigns/DOD-CONVERGENCE-EXTRA-CONTINUE-03/campaign-status.json`  
- Remote: GitHub API `tjsasakifln/extra-cli` pulls **#86, #89, #91, #93** (files + metadata)  
- Commit: `432da028` = merge PR #92 (idempotency tests on main)

---

*End of Subagent B audit. No normative files modified.*
