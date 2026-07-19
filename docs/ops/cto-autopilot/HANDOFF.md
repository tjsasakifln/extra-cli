# HANDOFF — CTO Autopilot

**Data (UTC):** 2026-07-19  
**Branch:** `feat/cto-autopilot-issues-deepseek-20260719`  
**Base:** `origin/main` @ `dbc5adb`  
**Worktree:** `/mnt/d/extra-consultoria-cto-autopilot`  
**Repo:** `tjsasakifln/extra-consultoria`

## O que foi implementado

Sistema **CTO Autopilot**:

| Camada | Implementação |
|--------|----------------|
| Observer | `scripts/cto/observer.py` → `output/cto/current/observation.json` |
| DeepSeek CTO | `scripts/cto/deepseek_client.py` + `decision.py` (JSON schema fail-closed) |
| Ranker | `squads/extra-dod-roi/` preservado; ranking é **consultivo** via observe/rank |
| Issues | `scripts/cto/github_issues.py` + `config/work_registry.yaml` |
| Executor Grok | `scripts/cto/grok_executor.py` (dry-run / mock / live; sandbox + deny) |
| Verifier | `scripts/cto/verifier.py` (PASS/FAIL/INCOMPLETE/UNSAFE) |
| State machine | `scripts/cto/state_machine.py` + lock + ledger append-only |
| HTML | painel CTO injetado em `extra-consultoria-plano-executivo.html` |
| CLI | `python -m scripts.cto.cli …` + targets Makefile |
| Docs | `docs/ops/cto-autopilot/` |

Charter: `.cto/CHARTER.md`  
Policies: `.cto/policies.yaml`  
Schemas: `.cto/decision.schema.json`, `.cto/review.schema.json`

## Auditoria pré-implementação (revalidada)

| Item | Valor |
|------|--------|
| Branch primária suja | `campaign/extra-ops-95-20260719` (não misturada) |
| PR #29 EXTRA-OPS-95 | open, CI majoritariamente SUCCESS |
| PR #28 advance-30d | draft, CI com FAILURE |
| DoD (campanha) | ~22.7% checked (snapshot audit) |
| DoD em main/worktree | painel reportou ~14.39% (HEAD main) |
| gh auth | OK (`tjsasakifln`) |
| Isolamento | worktree + branch próprias |

## Issues criadas (18 — dentro do limite 15–35)

Marcador: `<!-- extra-work-id: … -->`

| # | work_id |
|---|---------|
| 30 | cto-autopilot-infra |
| 31 | stabilize-open-pr-ci |
| 32 | integrate-extra-ops-95 |
| 33 | full-suite-schema-debt |
| 34 | freshness-coverage-sla |
| 35 | recall-stratified-95 |
| 36 | opportunities-open-pipeline |
| 37 | executive-html-cto-panel |
| 38 | github-issues-queue |
| 39 | dod-evidence-discipline |
| 40 | source-health-pncp-timeout |
| 41 | contracts-admin-tracking |
| 42 | reports-pdf-excel-stable |
| 43 | ranker-advisory-bridge |
| 44 | human-gates-fail-closed |
| 45 | coverage-operational-progress |
| 46 | publication-policy-docs |
| 47 | budget-and-fallback |

Re-sync dry-run: **0 creates / 18 updates** (idempotente).  
**Nenhum checkbox DoD foi marcado** por esta migração.  
**Nenhuma Issue foi fechada** sem evidência.

Labels (`state:`, `type:`, `priority:`, `risk:`, `area:`) e milestones (`LOCAL_READY`, `PRE_VPS_FINAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, `CTO_AUTOPILOT`) criados.

## Testes

```text
python3 -m pytest tests/cto -q --no-cov
# 43 passed
```

Cobertura: redaction, schema, DeepSeek mock (empty/trunc/retry/429), issues, state/lock, verifier (DoD/main/unsafe cmd), executor dry/mock, observer, executive HTML, fallback BLOCKED_CTO_UNAVAILABLE.

CI **não** chama DeepSeek real. Smoke opt-in:

```bash
DEEPSEEK_LIVE_TEST=1 python3 -m scripts.cto.cli deepseek-smoke
```

## Demo ciclo (seguro)

```bash
python3 -m scripts.cto.cli run-once --dry-run --mock --skip-tests
```

Resultado observado:

1. observe ✓  
2. decide → **EXECUTE** (`work_id=cto-autopilot-infra`)  
3. execute → **mock_completed**  
4. verify → **PASS**  
5. review → **ACCEPT**  
6. refresh-executive ✓  

## Comandos para Tiago

```bash
cd /mnt/d/extra-consultoria-cto-autopilot   # ou checkout da branch

# 1) saúde
python3 -m scripts.cto.cli doctor

# 2) observar / decidir (dry)
python3 -m scripts.cto.cli observe
python3 -m scripts.cto.cli decide --dry-run

# 3) ciclo seguro
python3 -m scripts.cto.cli run-once --dry-run

# 4) com DeepSeek real (requer DEEPSEEK_API_KEY)
python3 -m scripts.cto.cli decide
# NÃO use --always-approve live sem revisar policies

# 5) Issues
python3 -m scripts.cto.cli issues-sync --dry-run
python3 -m scripts.cto.cli issues-audit

# 6) HTML
python3 -m scripts.cto.cli refresh-executive

# 7) pausar / retomar
python3 -m scripts.cto.cli pause
python3 -m scripts.cto.cli resume
```

Variáveis: ver `.env.example` e `docs/ops/cto-autopilot/README.md`.

**DeepSeek:** chave em `.env` local (`DEEPSEEK_API_KEY`). **Rotacione** se foi exposta em chat. Default model: `deepseek-v4-pro` (não `deepseek-chat` / `deepseek-reasoner`).

## Política de publicação (canônica v1)

1. worktree  
2. branch por work item  
3. commits locais  
4. verify independente  
5. **draft PR**  
6. CI  
7. review  
8. **merge só com autorização humana**  
9. sync  
10. rerank  

Autonomous merge/deploy = **proibido**.

## Limitações / riscos

- Executor Grok live depende de flags `--deny` suportadas pela CLI instalada; fail-closed se inseguro.  
- Decide dry-run não chama API; live depende de disponibilidade DeepSeek.  
- Observer usa `gh`; sem auth, Issues ficam vazias na observation.  
- PR #28 com CI vermelho e campanha EXTRA-OPS-95 **não** foram estabilizadas neste PR (registradas como work items #31/#32).  
- HTML painel é derivado — **não** eleva selos `LOCAL_READY` / 95%.  
- systemd user service só como exemplo — **não** habilitado.

## O que ainda requer Tiago

1. Revisar e mergear este draft PR (ou pedir ajustes).  
2. Rotacionar DeepSeek API key se exposta.  
3. Autorizar ciclo **live** (`decide` sem `--dry-run`, executor sem mock).  
4. Decidir integração das PRs #28/#29.  
5. Qualquer merge/deploy/gasto/claim ao cliente.

## Primeira ação recomendada

```bash
python3 -m scripts.cto.cli doctor
python3 -m scripts.cto.cli status
python3 -m scripts.cto.cli run-once --dry-run --mock --skip-tests
# Revisar Issues #30–#47 no GitHub
# Revisar draft PR desta branch
```

## Claims

**Não** se declara: `LOCAL_READY`, `PRE_VPS_FINAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, cobertura 95%.
