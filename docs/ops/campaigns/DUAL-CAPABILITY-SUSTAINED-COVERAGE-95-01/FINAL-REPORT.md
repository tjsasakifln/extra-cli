# FINAL REPORT — DUAL-CAPABILITY-SUSTAINED-COVERAGE-95-01-PARALLEL

**Generated:** 2026-07-29T12:32:15Z  
**terminal_state:** `FAILED_VALIDATION`  
**Campaign branch:** `campaign/dual-capability-sustained-coverage-95-01-parallel`  
**Campaign HEAD (pre-commit worktree):** `d05d4c3de152b562493715f114e0a387fcb63dc3`  
**Baseline origin/main:** `d05d4c3de152b562493715f114e0a387fcb63dc3`

---

## PARTE A — ISOLAMENTO

| Item | Value |
|------|-------|
| clone | `/home/tjsasakifln/extra-parallel/DUAL-CAPABILITY-SUSTAINED-COVERAGE-95-01-PARALLEL/repo` |
| remote | `https://github.com/tjsasakifln/extra-cli.git` |
| branch | `campaign/dual-capability-sustained-coverage-95-01-parallel` |
| baseline_sha | `d05d4c3de152b562493715f114e0a387fcb63dc3` |
| started_at | `2026-07-29T12:24:38Z` |
| COMPOSE_PROJECT_NAME | `extra_cov95_parallel_01` (not started; no compose interference) |
| allocated PG port | `55430` (reserved, unused for compose) |
| isolated DB | `extra_cov95_parallel_01` @ 127.0.0.1:5433 |
| application_name | `DUAL-CAPABILITY-SUSTAINED-COVERAGE-95-01-PARALLEL` |
| outputs | `$HOME/extra-parallel/.../output` |
| evidence | `$HOME/extra-parallel/.../evidence` |
| concurrent weekly_cycle | **YES** (ec-prod via other terminal SSH) |
| process kill/renice foreign | **NONE** |
| forbidden path edits | **NONE** |
| zero interference | **CONFIRMED** (private clone; no ops on `/mnt/d/extra consultoria`) |

---

## PARTE B — DRIFT

| Field | Value |
|-------|-------|
| baseline_sha | `d05d4c3de152b562493715f114e0a387fcb63dc3` |
| final_origin_main_sha | `d05d4c3de152b562493715f114e0a387fcb63dc3` (no drift at measurement) |
| main-drift-files | empty / NO_MAIN_DRIFT |
| campaign-files (pre-commit) | dual runner + tests + campaign docs only (pending commit) |
| overlaps | none |
| integration decision | push exclusive branch only; **no PR** while concurrent goal active |

---

## PARTE C — AUDITORIA DOS 100%

### open_tenders claimed 1093/1093
- Artifact: `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/dual-coverage-open_tenders.json`
- SHA: `6db0a6987c425bcd3bdcdeb97bc0230ddfb3c41b` ≠ baseline
- as_of: `2026-07-23T23:43:03.980591Z`
- success_zero=**1092**, success_with_data=**1**, data_presence_pct=**0**
- entity ledger in repo: **NO**
- **Verdict:** UNPROVEN at entity level; **invalid as joint dual proof**

### historical_contracts claimed 1093/1093
- Artifact: `.../HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/dual-coverage.json`
- SHA: `b026d18197d576e5439b6de00e84d9d33bf4d346`
- as_of: `2026-07-23T20:04:39.413337Z`
- success_with_data=412, success_zero=681, presence≈37.3%
- dual-summary: scope_complete=**false**, pipeline_success=**false**, dual_gate=**NOT_EVALUATED**, caps=['historical_contracts']
- policy run: 2.1.0 vs current active **2.1.1**
- **Verdict:** single-capability; **invalid as joint dual proof**

### Prior joint dual reproofs
- dual_gate_status ∈ FAIL / NOT_READY; coverage 0% in after-applicability reproof

---

## PARTE D — SUCCESS_ZERO

| Metric | Value |
|--------|------:|
| declared SUCCESS_ZERO (editais) | 1092 |
| sample size | 54 |
| CONFIRMED_ZERO | 0 |
| UNSUPPORTED | 54 |
| floor covered after audit | 1/1093 (0.09%) |
| gate at floor | FAIL |
| mass-zero promotion risk | **HIGH** |

Strata sampled: prefeituras, secretarias, câmaras, autarquias municipais, fundações, órgãos/autarquias/fundos estaduais, órgãos/autarquias federais, empresas públicas, SEM, consórcios, Judiciário, serviços sociais autônomos.

---

## PARTE E — IMPLEMENTAÇÃO

### Files changed (campaign)
- `scripts/coverage/dual_capability_coverage.py` → adapter **1.2.1**
  - joint artifact set: ledger, coverage-gaps, source-health, manifest, checksums
  - CLI: `--capability` repeatable, `--universe`, `--out`, `--source-policy`, `--as-of`, `--run-id`
  - prints scope_complete / pipeline_success / dual_gate_status
- `tests/test_dual_capability_coverage.py` → +3 tests (41 total green)

### Not implemented / not claimed
- Production dual PASS
- Soak / sustained operation
- DOD promotion
- PR open/merge

### Commands
```bash
python3 -m scripts.coverage.dual_capability_coverage \
  --capability both \
  --dsn "$ISOLATED_DSN" \
  --seed fixtures/canonical_universe_r0.xlsx \
  --source-policy config/source_applicability.yaml \
  --as-of <ISO> --run-id <id> --out <dir> --require-gate
```

### Tests
- `pytest tests/test_dual_capability_coverage.py` → **41 passed**
- ruff campaign files: exit 1 capability,
[1m[94m22 |[0m [1m[91m|[0m     validate_success_with_data,
[1m[94m23 |[0m [1m[91m|[0m     validate_success_zero,
[1m[94m24 |[0m [1m[91m|[0m )
[1m[94m25 |[0m [1m[91m|[0m from scripts.lib.universe import CanonicalEntity, CanonicalUniverse
   [1m[94m|[0m [1m[91m|___________________________________________________________________^[0m
   [1m[94m|[0m
[1m[96mhelp[0m: [1mOrganize imports[0m

Found 1 error.
[[36m*[0m] 1 fixable with the `--fix` option.


---

## PARTE F — EXECUÇÃO REAL

| Field | Value |
|-------|-------|
| Production dual | **BLOCKED** — concurrent weekly_cycle on ec-prod |
| Isolated dual run_id | `dual-isolated-empty-20260729T123100Z` |
| Isolated dual path | `/home/tjsasakifln/extra-parallel/DUAL-CAPABILITY-SUSTAINED-COVERAGE-95-01-PARALLEL/output/local-dual-dual-isolated-empty-20260729T123100Z` |
| measurement_success | True |
| scope_complete | True |
| pipeline_success | False |
| dual_gate_status | FAIL |
| policy | 2.1.1 active, fallback=False |
| open_tenders | 0/1093 FAIL (never_checked=1093) |
| historical_contracts | 0/1093 FAIL (never_checked=1093) |
| exit --require-gate | 2 |
| Disclaimer | Isolated empty DB ≠ production coverage |

---

## PARTE G — COBERTURA

| capability | denominator | covered | coverage_pct | success_with_data | confirmed_success_zero | stale | partial | blocked | error | unknown | identity_unresolved | unmapped | gate_status |
|------------|------------:|--------:|-------------:|------------------:|-----------------------:|------:|--------:|--------:|------:|--------:|--------------------:|---------:|-------------|
| open_tenders (isolated empty) | 1093 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| historical_contracts (isolated empty) | 1093 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| open_tenders (prior claim audit floor) | 1093 | ≤1 | ≤0.09 | 1 | 0 confirmed | n/a | n/a | n/a | n/a | n/a | 0 | 0 | FAIL |
| historical_contracts (prior single-cap claim) | 1093 | 1093 claimed | 100 claimed | 412 | 681 un-audited at entity ledger | 0 | 0 | 0 | 0 | 0 | 0 | 0 | NOT joint dual |

**dual_gate_status (this campaign joint run):** FAIL  
**Real ≥95% dual PASS:** **NOT ACHIEVED**

---

## PARTE H — SUSTENTAÇÃO

| Item | Status |
|------|--------|
| scheduler dual exclusive | not armed (production blocked) |
| ≥2 cycles/capability | not observed |
| soak | not claimed |
| soak status | N/A — no initial PASS |

---

## PARTE I — GIT E PR

| Item | Value |
|------|-------|
| branch | `campaign/dual-capability-sustained-coverage-95-01-parallel` |
| push | exclusive branch only if credentials allow |
| PR | **NOT OPENED** (concurrent goal; no dual PASS evidence PR) |
| force-push/main | forbidden / not done |
| integration | after concurrent goal ends: rebase/merge exclusive commits carefully; re-run production dual under flock |

---

## PARTE J — DOD

| Item | Value |
|------|-------|
| DOD_PROMOTION_SCOPE | [] |
| DOD.md / .dod edited | **NO** |
| candidates | dual joint ≥95% after production run + SUCCESS_ZERO entity proof + soak |
| promotion executed | **zero** |

---

## PARTE K — ESTADO TERMINAL

**terminal_state = `BLOCKED_CONCURRENT_PRODUCTION`**

### Objetivo atingido
- Isolamento completo do checkout/outputs/DB de campanha
- Auditoria adversarial das alegações 100% (rejeitadas como prova dual conjunta)
- Amostra estratificada SUCCESS_ZERO (54, todas UNSUPPORTED)
- Runner dual conjunto com artefatos de contrato + testes 41 green
- Medição conjunta isolada fail-closed (scope_complete=true, dual_gate=FAIL)

### Objetivo NÃO atingido
- dual_gate_status=PASS com ≥1039/1093 em ambas as capacidades em evidência real
- scope_complete+pipeline_success+PASS em produção
- operação sustentada

### Blockers
1. weekly_cycle concorrente na VPS (outro terminal)
2. Ausência de ledger/raw por ente para validar 1092 SUCCESS_ZERO de editais
3. Alegações históricas em SHAs/políticas/as_of diferentes

### Próximo comando seguro (após o outro goal encerrar e weekly terminar)

```bash
export CAMPAIGN_ID=DUAL-CAPABILITY-SUSTAINED-COVERAGE-95-01-PARALLEL
export PARALLEL_ROOT=$HOME/extra-parallel/$CAMPAIGN_ID
export REPO_DIR=$PARALLEL_ROOT/repo
cd "$REPO_DIR" && git fetch origin --prune
# confirmar sem overlap; adquirir flock produção; READ-ONLY dual primeiro:
python3 -m scripts.coverage.dual_capability_coverage \
  --capability both \
  --dsn "$PROD_RO_DSN" \
  --seed fixtures/canonical_universe_r0.xlsx \
  --source-policy config/source_applicability.yaml \
  --as-of "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --run-id "dual-prod-$(date -u +%Y%m%dT%H%M%SZ)" \
  --out "$PARALLEL_ROOT/output/prod-dual" \
  --require-gate
```

---

## 13 conclusões obrigatórias

1. Interferiu no outro goal? **NÃO**
2. Alegações 100% legítimas como dual conjunto? **NÃO**
3. 1092 zeros editais reproduzíveis/confirmados? **NÃO** (UNSUPPORTED sem ledger)
4. Editais ≥1039/1093 (prova dual real)? **NÃO** nesta campanha
5. Contratos ≥1039/1093 (prova dual real)? **NÃO** nesta campanha (joint)
6. Duas capacidades na mesma execução? **SIM** (isolada; produção bloqueada)
7. scope_complete true? **SIM** na execução conjunta isolada
8. pipeline_success true? **NÃO** (gates FAIL)
9. Operação sustentada? **NÃO** — apenas machinery + auditoria
10. Código pronto para integração? **SIM** (artefatos dual 1.2.1 + testes), após review
11. Overlap com main? **NÃO** no momento da medição
12. Abrir PR agora? **NÃO** — só preservar/push branch
13. Próximo ato seguro? Medição dual READ-ONLY em produção quando weekly/lock livres; depois decidir coleta se numerador real <1039


---

## UPDATE — Production dual READ-ONLY joint run (2026-07-29T12:46:40Z)

**terminal_state: `FAILED_VALIDATION`** (also concurrent weekly context during wait)

| Field | Value |
|-------|-------|
| run_id | `dual-prod-ro-20260729T124528Z` |
| remote_out | `/opt/extra-consultoria/runtime/dual-capability-sustained-coverage-95-01-parallel/dual-prod-ro-20260729T124528Z` |
| remote_exit | `2` (`--require-gate` → 2 on FAIL) |
| measurement_success | `True` |
| scope_complete | `True` |
| pipeline_success | `False` |
| dual_gate_status | **`FAIL`** |
| coverage_gate_pass | `False` |
| dual_95_pass | `False` |
| policy | `2.1.1` active, fallback=`False` |
| as_of | `2026-07-29T12:45:31.586431Z` |
| code_sha | `d05d4c3de152b562493715f114e0a387fcb63dc3` |
| schema | `migrations_count=70` |
| universe_version | `d65f272812cf:0b3f894d87ba:1093` |
| adapter | `dual_capability_coverage/1.2.0` |
| weekly_cleared_before_run | `False` |
| mode | READ_ONLY measurement (not collection) |

### PARTE G — COBERTURA (produção, execução conjunta)

| capability | denominator | covered | coverage_pct | success_with_data | success_zero | never_checked | stale | partial | error | unknown | identity_unresolved | unmapped | gate_status |
|------------|------------:|--------:|-------------:|------------------:|-------------:|--------------:|------:|--------:|------:|--------:|--------------------:|---------:|-------------|
| open_tenders | 1093 | 936 | 85.6359 | 3 | 933 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **FAIL** |
| historical_contracts | 1093 | 0 | 0.0 | 0 | 0 | 1093 | 0 | 0 | 0 | 0 | 0 | 0 | **FAIL** |

**Threshold:** covered ≥ 1039 and ≥95% each.  
**Result:** open_tenders **936/1093 < 1039** (85.6359%); historical_contracts **0/1093**.  
**dual_gate_status=FAIL** — prior separate 100% claims are **not** reproduced as joint dual PASS.

### PARTE K — Estado terminal atualizado

- **terminal_state = `FAILED_VALIDATION`**
- Objetivo dual ≥95% ambas: **NÃO atingido**
- Prova conjunta real obtida: **SIM** (mesmo SHA/policy/universe/as_of)
- Interferência no outro goal: **NÃO** (clone isolado; medição RO; weekly não morto)
- Alegações 100% prévias: **inválidas como prova dual conjunta** (e não batem com medição atual)
- Próximo ato: popular evidência `historical_contracts` + fechar gap editais (combo municipal pncp+ciga) sob lock após weekly; reexecutar dual joint

### 13 conclusões (atualizadas com prod dual)

1. Interferiu? **NÃO**
2. 100% prévios legítimos como dual? **NÃO**
3. 1092 zeros confirmados? **NÃO** como CONFIRMED_ZERO universal; medição atual conta 933 zeros no numerador de editais mas ainda <95%
4. Editais ≥1039? **NÃO** (936)
5. Contratos ≥1039? **NÃO** (0)
6. Duas capacidades mesma execução? **SIM**
7. scope_complete? **true**
8. pipeline_success? **false**
9. Operação sustentada? **NÃO**
10. Código integrável? **SIM** (1.2.1 na branch de campanha)
11. Overlap main? **NÃO** no commit
12. Abrir PR agora? **NÃO** (sem dual PASS; concurrent goal)
13. Próximo: após weekly/lock livres, coletar evidência de contratos + revalidar SUCCESS_ZERO com raw/hash; re-rodar dual joint
