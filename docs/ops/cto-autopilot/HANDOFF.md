# HANDOFF — CTO Autopilot

**Data (UTC):** 2026-07-19  
**Branch:** `feat/cto-autopilot-issues-deepseek-20260719`  
**Draft PR:** https://github.com/tjsasakifln/extra-consultoria/pull/48  
**Worktree:** `/mnt/d/extra-consultoria-cto-autopilot`  
**Repo:** `tjsasakifln/extra-consultoria`

## Objetivo operacional (PR #48 merge-gate)

Corrigir bloqueadores objetivos e provar **um** ciclo live controlado:

- testes `tests/cto` obrigatórios no CI
- live sem `--skip-tests`
- env Grok por allowlist + HOME isolado
- `always-approve` desligado por padrão (opt-in + preflight funcional)
- canário live → draft PR → `WAITING_HUMAN` (sem merge)

## Correções merge-gate (esta campanha)

| # | Bloqueador | Delta |
|---|------------|--------|
| 1 | CI sem `tests/cto` | Job obrigatório `Test (CTO Autopilot)` em `.github/workflows/ci.yml` |
| 2 | systemd live com `--skip-tests` | Exemplo live sem flag; live+`--skip-tests` → `BLOCKED_UNVERIFIED` exit 11 |
| 3 | Env por denylist/`os.environ` | `build_minimal_child_env` allowlist explícita |
| 4 | HOME real exposto | `HOME`/`TMPDIR` em runtime isolado sob `*-cto-cycles/_runtime/` |
| 5 | `always-approve` por help text | Default false; `CTO_GROK_ALWAYS_APPROVE=1` + containment funcional |

## Testes (contagem canônica)

```text
python3 -m pytest tests/cto -q --no-cov
# 107 passed
```

Cobertura inclui: allowlist env (ausência de `MY_TOKEN`/`DATABASE_URL`/…), HOME isolado, always_approve default false, skip-tests live block, containment estrutural, claim surfaces, publisher no-merge, verifier matrix.

## Dívida residual (explícita)

| Item | Status | Por quê fora deste merge gate |
|------|--------|-------------------------------|
| Full suite (`Test All`) | Dívida | `workflow_dispatch` only; precisa serviços externos |
| Job `Test (CTO Autopilot)` | **Obrigatório** | Protege `scripts/cto` + `tests/cto` |
| Riscos fora desta proteção | — | pipelines de negócio, crawlers, DB migrations, cobertura full |

## Evidências locais

| Check | Resultado |
|-------|-----------|
| Ruff `scripts/cto` + `tests/cto` | esperado limpo no HEAD |
| `pytest tests/cto` | **107 passed** |
| `run-once --dry-run --mock --skip-tests` | verify PASS → review ACCEPT → publish dry → **`ACCEPTED_DRY_RUN`** / `queue_mutated=false` / terminal **DONE** / exit **0** (não polui fila; WAITING_HUMAN só com draft PR real) |
| live + `--skip-tests` | **BLOCKED_UNVERIFIED** / exit 11 (sem ACCEPT/publish) |
| Canário live | ver seção abaixo (preenchida após execução) |

### Canário live (execução real — 2026-07-19)

| Campo | Valor |
|-------|--------|
| cycle_id | `canary-live-20260719T204106Z` |
| decision_id | `dec-canary-live-20260719T204106Z` |
| branch | `cto/canary-live-20260719T204106Z` |
| worktree | `/mnt/d/extra-consultoria-cto-autopilot-cto-cycles/canary-live-20260719T204106Z` |
| commit | `09de2d4f24774cfe2bd2f40a710e777af358edc7` |
| draft PR | https://github.com/tjsasakifln/extra-consultoria/pull/50 (draft, open) |
| arquivo | **somente** `docs/ops/cto-autopilot/canary-proof.md` |
| verifier | **PASS** (base_commit-scoped) |
| testes | `grep -qi canary docs/ops/cto-autopilot/canary-proof.md` exit 0 |
| CI canário | consultado (run 29703266575; job CTO presente; aguardando/parcial) |
| publisher | **WAITING_HUMAN** — draft PR #50; sem merge |
| terminal | `WAITING_HUMAN` |
| always_approve | **true** nesta execução via `CTO_GROK_ALWAYS_APPROVE=1` + containment funcional OK |
| Grok | **live** (não mock); auth staged só `auth.json` / allowlist; HOME isolado |
| main mutada | **não** (`origin/main` = `d6d9e19`) |
| merge | **não** (proibido; autoridade Tiago) |
| diff hash | verification includes only canary-proof.md |

## Issues (#30–#47)

Itens implementados nesta PR permanecem em `state:review` (sem auto-close).  
**Nenhuma Issue foi fechada automaticamente.**

## Comandos para Tiago

```bash
cd /mnt/d/extra-consultoria-cto-autopilot

python3 -m scripts.cto.cli doctor
python3 -m scripts.cto.cli reconcile-queue
python3 -m scripts.cto.cli run-once --dry-run --mock --skip-tests
# ciclo live conservador (nunca --skip-tests):
# python3 -m scripts.cto.cli run-once
# canário live controlado (só canary-proof.md):
# python3 -m scripts.cto.cli canary-live

python3 -m scripts.cto.cli resume
python3 -m scripts.cto.cli pause
```

## Política de publicação (canônica)

1. worktree  
2. branch do ciclo  
3. commits locais  
4. verify + CTO review  
5. **publisher** → push + **draft PR**  
6. CI  
7. `WAITING_HUMAN`  
8. **merge só Tiago**  

Autonomous merge/deploy = **proibido**.

## Claims

**Não** se declara: `LOCAL_READY`, `PRE_VPS_FINAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, cobertura 95%, recall 100%.

## Publisher dry-run contract

- dry-run publish → `ACCEPTED_DRY_RUN`, `queue_mutated=false`
- WAITING_HUMAN only with real draft PR number
