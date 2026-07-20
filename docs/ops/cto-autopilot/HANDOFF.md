# HANDOFF — CTO Autopilot

**Data (UTC):** 2026-07-19  
**Branch:** `feat/cto-autopilot-issues-deepseek-20260719`  
**Draft PR:** https://github.com/tjsasakifln/extra-consultoria/pull/48  
**Worktree:** `/mnt/d/extra-consultoria-cto-autopilot`  
**Repo:** `tjsasakifln/extra-consultoria`  
**HEAD:** (ver `git rev-parse HEAD` na branch do PR #48)

## Objetivo operacional (PR #48 merge-gate)

Orquestrador CTO headless seguro integrado ao AIOX e ao squad `extra-dod-roi`, com:
registry de testes autorizados, veto absoluto de review, selo de SHA verificado, e headless `dontAsk`+`strict`.

## Correções merge-gate + security remediation

| # | Bloqueador | Delta |
|---|------------|--------|
| 1 | CI sem `tests/cto` | Job **Test (CTO Autopilot)** obrigatório |
| 2 | Live com `--skip-tests` | systemd sem flag; live+skip → `BLOCKED_UNVERIFIED` exit 11 |
| 3 | Env denylist | `build_minimal_child_env` allowlist |
| 4 | HOME real | HOME/TMPDIR isolados; **sem** copiar host auth.json; live exige `XAI_API_KEY` |
| 5 | always-approve operacional | **Removido do path operacional** — usa `--permission-mode dontAsk` + `--sandbox strict` + allow/deny |
| 6 | Free-form `test_commands` | `.cto/authorized_tests.yaml` + `test_ids` only; `shell=False` |
| 7 | Review ACCEPT sobre FAIL | `review_veto.apply_absolute_veto` invariante absoluta |
| 8 | Janela verify→publish | `seal.py` + publisher sem `git add -A` pós-review |
| 9 | AIOX paralelo | `aiox_bridge.py` adaptador fino (não fork de agentes) |
| + | Proveniência canário | `decision_sha256` + `validate_sealed_canary_package` (fail-closed) |

## Testes

```text
python3 -m pytest tests/cto -q -o addopts=''
# 171 passed
```

| Check | Resultado |
|-------|-----------|
| Ruff `scripts/cto` + `tests/cto` | limpo no HEAD |
| `pytest tests/cto` | **171 passed** |
| `run-once --dry-run --mock --skip-tests` | verify PASS → review ACCEPT → publish dry → **`ACCEPTED_DRY_RUN`** / `queue_mutated=false` / terminal **DONE** / exit **0** (não polui fila; WAITING_HUMAN só com draft PR real) |
| live + `--skip-tests` | **BLOCKED_UNVERIFIED** / exit 11 |
| sealed canary-live | ver seção abaixo |

## Dívida residual

| Item | Status |
|------|--------|
| Full suite (`Test All`) | `workflow_dispatch` only |
| Job Test (CTO Autopilot) | **Obrigatório** — protege `scripts/cto` + `tests/cto` |

## Canário live SEALED (única evidência válida)

> Ciclos anteriores (`…204106Z` etc.) são **históricos** e **não** contam como prova de merge-gate.

| Campo | Valor |
|-------|--------|
| cycle_id | `canary-live-20260719T215031Z` |
| decision_id | `dec-canary-live-20260719T215031Z` |
| branch | `cto/canary-live-20260719T215031Z` |
| worktree | `…/extra-consultoria-cto-autopilot-cto-cycles/canary-live-20260719T215031Z` |
| base_commit | `27d977d1e38ec96b61a529cd5cac345fdac38340` (= HEAD PR no start) |
| commit canário | `539b90de16eadebe57a33b432e3e53db60e1c687` |
| draft PR | https://github.com/tjsasakifln/extra-consultoria/pull/51 |
| arquivo | **somente** `docs/ops/cto-autopilot/canary-proof.md` |
| Grok | live (`mock=false`, `dry_run=false`, `status=completed`) |
| auth | `grok_auth.source=XAI_API_KEY`, `staged_auth_file=false`, **sem** `.grok/auth.json` no HOME isolado |
| always_approve | true (opt-in `CTO_GROK_ALWAYS_APPROVE=1` + containment); default continua false |
| verifier | **PASS** |
| test_commands | `grep -qi canary docs/ops/cto-autopilot/canary-proof.md` exit 0 |
| review | **ACCEPT** |
| publisher | **WAITING_HUMAN**, draft PR #51, **sem merge** |
| integrity | **ok=true** (`integrity.json`) |
| decision_sha256 | `4664ace738a44cf1579336ad2c9f042f1aee344fe27b955281ce2db93471600b` |
| main | **inalterada** (`origin/main` = `d6d9e19`) |
| `_meta.source` | `cli canary-live` (sem reconcile) |

### Histórico supersedido (não usar como prova)

- PR #50 / cycle `canary-live-20260719T204106Z` — host auth staging + package reescrito post-hoc.

## Comandos

```bash
cd /mnt/d/extra-consultoria-cto-autopilot
export XAI_API_KEY=...   # required for live Grok under isolated HOME
# export CTO_GROK_ALWAYS_APPROVE=1  # opt-in only
python3 -m scripts.cto.cli canary-live
```

## Claims

**Não** se declara: `LOCAL_READY`, `PRE_VPS_FINAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, 95% coverage, recall 100%.

Merge **só Tiago**.
