# HANDOFF — CTO Autopilot

**Data (UTC):** 2026-07-19  
**Branch:** `feat/cto-autopilot-issues-deepseek-20260719`  
**Draft PR:** https://github.com/tjsasakifln/extra-consultoria/pull/48  
**Worktree:** `/mnt/d/extra-consultoria-cto-autopilot`  
**Repo:** `tjsasakifln/extra-consultoria`

## Objetivo operacional cumprido nesta correção

Tiago pode disparar **uma** ação (`run-once` ou timer user systemd) e só precisa voltar quando houver:

- draft PR com CI, **ou**
- decisão humana / blocker real, **ou**
- falha após tentativas de reparo

Sem copiar e colar entre ChatGPT e Grok no ciclo normal.

## O que foi corrigido (bloqueadores de merge da PR #48)

| # | Bloqueador | Status |
|---|------------|--------|
| 1 | CI / Ruff | Corrigido localmente (`ruff check scripts/cto tests/cto` limpo); push revalida CI |
| 2 | Observer com contexto decisório completo | PRs+CI jobs/steps, work items completos, freshness, testes, worktrees/ciclos, divergências |
| 3 | Ranking stale | `ensure_ranking_current` antes de decide; stale explícito se antigo |
| 4 | Readiness real de Issues | deps/blockers bloqueiam ready; #30/#37–39/#43–44/#46–47 reconciliados → review (sem auto-close) |
| 5 | Verifier forte | diff+hash, staged/unstaged/untracked, secrets, matriz PASS/FAIL/UNPROVEN, executor fail bloqueia PASS |
| 6 | CTO Review payload completo | decision, work item, diff, matriz, execução, transcript, tentativas |
| 7 | Fallback DeepSeek | **nunca ACCEPT** se CTO indisponível → ESCALATE + `BLOCKED_CTO_UNAVAILABLE` (+ teste) |
| 8 | Publisher pós-ACCEPT | `scripts/cto/publisher.py` separado; draft PR; WAITING_HUMAN; merge só Tiago |
| 9 | Resume real | continua PREPARING/EXECUTING/VERIFYING/REVIEWING/REPAIRING com artefatos do ciclo |
| 10 | systemd user timer | exemplos live **sem** `--dry-run`, desabilitados por padrão + docs |
| 11 | Executor endurecido | preflight `--deny`, strip credenciais, bloqueio circumvention, `always_approve` só com prova |
| 12 | Exit codes | 10 WAITING_HUMAN, 11 BLOCKED, 12 FAILED — não sucesso genérico |
| 13 | Evidências de execução | unit+integração local; DeepSeek smoke live OK; decide live fail-closed; ciclo mock+verify |
| 14 | HANDOFF/PR/HTML | este arquivo + painel HTML refreshed |

## Arquitetura (sem paralelo)

Continua no pacote `scripts/cto/*` + CLI `python -m scripts.cto.cli`.  
Novo módulo: `scripts/cto/publisher.py` (só publicação, nunca Grok).

## Testes (contagem canônica)

```text
python3 -m pytest tests/cto -q --no-cov
# 87 passed
```

Cobertura inclui: observer context, readiness/reconcile, verifier matrix/UNPROVEN/executor-fail/secrets, review fallback anti-ACCEPT, publisher no-merge, resume EXECUTING/REVIEWING, exit codes, executor env strip/preflight, redaction usage counters.

## Evidências locais (esta sessão)

| Check | Resultado |
|-------|-----------|
| Ruff `scripts/cto` + `tests/cto` | All checks passed |
| `pytest tests/cto` | **87 passed** |
| `cli doctor` | ok |
| `reconcile-queue` | 8 itens PR#48 → review; 3 blocked por blockers; auto_closed=false |
| `run-once --dry-run --mock --skip-tests` | verify PASS → review ACCEPT → publish dry → **WAITING_HUMAN** exit **10** |
| `DEEPSEEK_LIVE_TEST=1 deepseek-smoke` | **ok** (model deepseek-v4-pro) |
| `cli decide` live | DeepSeek respondeu; schema extra field → **BLOCK / BLOCKED_CTO_UNAVAILABLE** fail-closed (não inventou work) |
| Draft PR de ciclo mock | path dry-run publisher (sem push real no dry-run) |

### Não comprovado ao vivo nesta sessão

- Grok executor **live** (não mock) em worktree com push real de draft PR de ciclo  
- Merge (proibido por design)

Se Grok CLI / push remoto não forem autorizados, o restante permanece pronto; integração live completa **não** se declara.

## Issues (#30–#47)

Marcador: `<!-- extra-work-id: … -->`

Itens **implementados nesta PR** (não devem ficar `state:ready` como trabalho novo):

| # | work_id | estado reconcilhado |
|---|---------|---------------------|
| 30 | cto-autopilot-infra | review |
| 37 | executive-html-cto-panel | review |
| 38 | github-issues-queue | review |
| 39 | dod-evidence-discipline | review |
| 43 | ranker-advisory-bridge | review |
| 44 | human-gates-fail-closed | review |
| 46 | publication-policy-docs | review |
| 47 | budget-and-fallback | review |

Evidência: branch `feat/cto-autopilot-issues-deepseek-20260719` + testes 83 + PR #48.

**Nenhuma Issue foi fechada automaticamente.**  
Para sincronizar labels no GitHub: `python3 -m scripts.cto.cli issues-sync --apply` (após revisão humana).

## Comandos para Tiago

```bash
cd /mnt/d/extra-consultoria-cto-autopilot   # ou checkout da branch

python3 -m scripts.cto.cli doctor
python3 -m scripts.cto.cli reconcile-queue
python3 -m scripts.cto.cli run-once --dry-run --mock --skip-tests
# ciclo live conservador (publisher pode abrir draft PR; nunca merge):
# python3 -m scripts.cto.cli run-once

python3 -m scripts.cto.cli resume   # se crash mid-cycle
python3 -m scripts.cto.cli pause

# Timer opcional (desabilitado por padrão) — ver README
# docs/ops/cto-autopilot/systemd-user.example.{service,timer}
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
9. sync Issue/registry/HTML + rerank  

Autonomous merge/deploy = **proibido**.

## Claims

**Não** se declara: `LOCAL_READY`, `PRE_VPS_FINAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, cobertura 95%.


## Hotfix readiness (post-skeptic)

- `sync_issues --apply` calls `_set_state_label` (removes other `state:*` before setting target)
- Observer indexes issues by **effective** state (blocked > human > review > in-progress > ready)
- `decide` / `run-once` call `reconcile_implemented_items` + `apply_readiness_gates` before decision
- `enforce_executable_readiness` rejects EXECUTE on #30/#37–39/#43–44/#46–47
- Evidence: `gh issue list --label state:ready` no longer includes those issues; dual-state count = 0; dry decide selected #32 not banned set
