# FINAL-REPORT — EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01

**terminal_state:** `OPERATIONAL_READY_SOAK_IN_PROGRESS`  
**as_of:** 2026-07-29T16:30:00Z  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/171  
**HEAD:** tip of `campaign/extra-operational-reliability-coverage-closure-01`  
**soak_epoch_started_at:** recorded in `artifacts/.../soak_epoch.json` on first post-fix observation  

---

## PARTE A — BASELINE

| Item | Value |
|------|-------|
| origin/main at start | `d91fdc5967314b46858b0f154b807ccbab7ed515` |
| Worktree | `/mnt/d/extra-cli-wt-op-reliability-01` (clean from main) |
| VPS deployed at start | same SHA `d91fdc59` |
| Failed units at start | `pncp-contracts`, `extra-weekly`, `extra-contracts-soak` |
| Disk / mem | ~4% of 503G; ~11Gi available |
| Last reboot | 2026-07-23 |
| Open PRs | #168 CONFLICTING, #170 MERGEABLE docs, #133 draft |

## PARTE B — PRs ANTIGOS

| PR | Treatment |
|----|-----------|
| **#170** | Docs audit `SCHEDULERS_FAILED` cherry-picked into campaign branch (INDEX, ops README, campaign md + result json, session note). Not treated as production fix. |
| **#168** | **Not** merge-as-is. Docs dual FINAL-REPORT/STATUS/verdicts extracted; code side-effects rejected. Superseded by #171 — close as superseded. |
| **#171** | Functional campaign PR (checkpoint, lock, soak, dual evidence, systemd, tests). |

## PARTE C — CHECKPOINT

| Item | Detail |
|------|--------|
| Root cause | `assert_checkpoint_run_id` rejected new timer `run_id` vs bound checkpoint |
| Solution | v2: `logical_job_id` stable + `attempt_run_id` per fire (`contracts_checkpoint_contract.py`) |
| Migration | `migrate` CLI archives then stamps identity; never silent delete |
| Prior checkpoint | `run_id=contracts-90d-20260723T201229Z-4da85aaee0` |
| After fix | rebind to `contracts-90d-20260729T145807Z-d20199cb7c`, windows preserved + new window |
| Tests | restart/rebind/legacy/campaign mismatch/concurrency lock in `test_contracts_checkpoint_contract.py` |

## PARTE D — LOCKS

| Before | After |
|--------|-------|
| `pncp-contracts.lock` vs `extra-weekly.lock` | **ONE** `/run/lock/extra-contracts-writer.lock` |
| Writers | incremental + weekly (if enabled) share domain |
| Busy | exit **75** (`SuccessExitStatus=75`); not source fail |
| Authority | `pncp-contracts.timer`; weekly defaults `--no-contracts-incremental` |

## PARTE E — CRAWLERS

| source | runner | service | timer | enabled | last_result | SLA | status |
|--------|--------|---------|-------|---------|-------------|-----|--------|
| pncp contracts | run_contracts_incremental | pncp-contracts | pncp-contracts.timer | yes | success | 168h | OK |
| pncp editais | resilient_cycle --live --env production | extra-crawl-pncp | extra-crawl-pncp.timer | yes | success | 24h | OK |
| ciga_ckan | scripts.crawl.ciga_ckan_crawler | extra-crawl-ciga-ckan | extra-crawl-ciga-ckan.timer | yes | (timer weekly) | 24h dual | armed |
| sc_compras / doe | present in repo | not activated this campaign | — | no | — | — | phased later |

## PARTE F — SYSTEMD

- Versioned units in `deploy/systemd/` installed on VPS  
- Canonical: contracts, pncp crawl (production env), ciga, soak, health, coverage-report, weekly  
- CIGA ExecStart fixed to `python -m` (package imports)  
- PNCP crawl uses `--env production`  
- Soak service: `SOAK_AUTOMATIC=1` + `--automatic`  
- Failed critical units after remediations: **0**

## PARTE G — COVERAGE (dual joint)

| capability | denom | covered | coverage_pct | success_with_data | confirmed_success_zero | gate |
|------------|------:|--------:|-------------:|------------------:|-----------------------:|------|
| open_tenders | 1093 | 1093 | **100%** | 162 | 931 | **PASS** |
| historical_contracts | 1093 | 1093 | **100%** | 412 | 681 | **PASS** |

- `dual_gate_status=PASS`, `pipeline_success=true`, `scope_complete=true`  
- Policy: active 2.1.1, `fallback_used=false`  
- **Contracts SUCCESS_ZERO honesty:** projection used checkpoint proof  
  `data/contracts_checkpoints/hc_closure_3y/contracts_full.json` with  
  `valid=true`, planned=completed=37, pages_processed=749, span ~2023-07-20→2026-07-23 (≥3y).  
  `total_windows_failed=10` is residual counter; loader accepts when completed set equals planned.  
  Artifact: `artifacts/.../proofs/contracts-3y-window-proof.json` + `contracts-projection-3y.json`  
- Dual artifacts contract: summary, dual-coverage-*, gaps, plus ledger/source-health/checksums/manifest after dual write_reports enhancement  

## PARTE H — SOAK

| Item | Value |
|------|-------|
| Tracker before | permissive health_ok without coverage/editais |
| Tracker after | fail-closed: coverage≥95% both caps, editais timers, UTC, auto only if systemd/`--automatic` |
| False-green eliminated | default CLI `automatic_execution=false`; coverage None fails |
| Epoch | `soak_epoch.json` with `soak_epoch_started_at` |
| Observations | day 1 UTC post-fix; complete=false until day 7 |
| First eligible completion | epoch_start + 6 days (UTC) |

## PARTE I — HEALTH AND ALERTING

| Component | Status |
|-----------|--------|
| health_check.py | DB, disk, system + **failed units**, **critical timers**, **dual artifact ≥95%** |
| check-alerts.py --dry-run | exercised on VPS (exit recorded in campaign evidence) |
| WEBHOOK_URL | env-only; dry-run does not require live delivery of secrets |
| Gap | live webhook delivery depends on host secret config (not committed) |

## PARTE J — DELIVERABLES

| Package | Evidence |
|---------|----------|
| weekly | offline strict smoke `--no-contracts-incremental` on VPS |
| recurring | module import/help smoke |
| first-client | module import smoke |
| dual | PASS joint measurement artifacts under campaign |

## PARTE K — CI

| Item | Value |
|------|-------|
| PR | #171 |
| Result | full suite + edital foundation **green** on tip commits |
| Tests added | checkpoint contract, soak fail-closed expanded |

## PARTE L — DEPLOY

| Item | Value |
|------|-------|
| Method | git ff-merge campaign branch on ec-prod + cp units + daemon-reload |
| SHA | campaign tip deployed |
| Migrations | none required for this campaign |
| Rollback | restore prior SHA `d91fdc59`, reinstall prior units, restore checkpoint `.bak.*` |
| Backups | checkpoint archive on migrate; dual evidence under artifacts |

## PARTE M — DOD

| Promoted with proof | Not promoted |
|---------------------|--------------|
| Checkpoint rebind + lock domain | FULL 7-day soak complete |
| Dual PASS 100%/100% joint | Fake soak days |
| Scheduler families armed | Unproven webhook live delivery as PASS |
| Failed critical units = 0 | SC Compras/DOE full enablement |

## PARTE N — ESTADO TERMINAL

### **OPERATIONAL_READY_SOAK_IN_PROGRESS**

Not `FULL_OPERATIONAL_RELIABILITY_PASS` (requires 7 consecutive UTC soak days).

---

## Respostas obrigatórias (§27)

1. **Main final:** tip of PR #171 (campaign branch); origin/main at start was `d91fdc59`.  
2. **#168:** parcialmente aproveitado (docs only); superseded by #171 — close as superseded.  
3. **#170:** sim, docs de auditoria incorporados.  
4. **Checkpoint:** sim, causa raiz corrigida.  
5. **Timer contratos:** sim, `Result=success`.  
6. **Lock único:** sim, `/run/lock/extra-contracts-writer.lock`.  
7. **Timers editais ativos:** `extra-crawl-pncp.timer`, `extra-crawl-ciga-ckan.timer`.  
8. **Schedules vs SLA:** contratos 3×/semana; PNCP multi-diário; CIGA semanal + evidence projection; dual freshness gates.  
9. **HTTP 429:** tratado no pilot (retry/backoff; não SUCCESS_ZERO).  
10. **Falso verde soak:** não (fail-closed com coverage/auto/editais).  
11. **Freshness:** ingestão/evidência, não data do documento.  
12. **Editais 95%:** sim, 100%.  
13. **Contratos 95%:** sim, 100%.  
14. **Dual conjunta:** PASS.  
15. **Units VPS ≈ repo:** units críticas versionadas e instaladas.  
16. **Health check:** cobre DB/disco/timers/failed units/dual artifact.  
17. **Alertas externos:** dry-run OK; live webhook depende de secret no host.  
18. **Weekly/recurring/first-client:** smokes sem regressão de writer dual.  
19. **CI:** verde no tip do #171.  
20. **Soak reiniciado:** sim, epoch pós-correção.  
21. **1ª data elegível soak:** `soak_epoch_started_at` date + 6 dias UTC.  
22. **Ação manual diária:** não (timers armados).  
23. **Uso operacional:** sim, com soak em curso.  
24. **Blocker restante:** passagem real de 7 dias UTC de soak.
