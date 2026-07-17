# extra-dod-roi

Squad **local e privado** (UNLICENSED) para o repositório Extra Consultoria.

Ciclo evergreen: reconstruir o estado real da codebase → reconciliar com `DOD.md` → grafo de dependências → filtrar UNLOCKED → rankear por ROI → execution card → implementar fatia mínima → QA adversarial independente → evidências → draft PR → apontar próximo ROI.

**Não publica** em aiox-squads, marketplace ou repositórios externos.

| Campo | Valor |
|-------|-------|
| name | `extra-dod-roi` |
| slashPrefix | `extra-roi` |
| author | Tiago Jun Sasaki |
| license | UNLICENSED |
| config | extend |
| aiox.minVersion | 5.3.0 |
| path | `./squads/extra-dod-roi/` |

## Arquitetura (task-first)

| Agente | Papel |
|--------|-------|
| `@roi-orchestrator` | Ciclo, lock, despacho, outcomes |
| `@codebase-cartographer` | Snapshot read-only (não declara DoD DONE) |
| `@dod-truth-auditor` | Verdade conservadora + veto a falso verde |
| `@critical-path-roi-planner` | Grafo, candidatos, ROI, execution card |
| `@delivery-engineer` | Implementação em branch isolada |
| `@adversarial-qa-auditor` | QA independente PASS/FAIL/BLOCKED |
| `@evidence-release-steward` | Evidências, DoD só pós-PASS, draft PR (sem merge) |

Workers determinísticos em `scripts/` para parse, score, snapshot, lock e `rank-next`.

## Comandos

### Read-only

```bash
# Status do squad
python squads/extra-dod-roi/scripts/cli.py status

# Snapshot
python squads/extra-dod-roi/scripts/cli.py scan-state

# Auditoria DoD (summary)
python squads/extra-dod-roi/scripts/cli.py audit-dod --summary

# Rank next (principal prova read-only)
python squads/extra-dod-roi/scripts/cli.py rank-next
python squads/extra-dod-roi/scripts/rank_next_cli.py --top 5

# Explicar próximo
python squads/extra-dod-roi/scripts/cli.py explain-next
```

Via agente `@roi-orchestrator` (AIOX):

- `*status` · `*scan-state` · `*audit-dod` · `*rank-next` · `*explain-next`
- `*plan-next` · `*verify-current` · `*show-blockers`

### Write (exigem permissão de escrita)

- `*execute-next` — implementa fatia do execution card
- `*run-cycle` — workflow `evergreen-roi-cycle` completo
- `*resume-cycle` — retoma ciclo interrompido (com stale detection)

## Persistência

Estado inter-sessão em `state/` (cache/histórico — **nunca** substitui leitura atual do repo):

```
state/
  snapshots/ requirements/ graphs/ rankings/
  execution-cards/ decisions/ handoffs/ cycles/
  qa/ evidence/ blockers/ metrics/ locks/
```

Invalidação: mudança de HEAD, `DOD.md`, PRs, checks, migrations, deps.

## Workflow

`workflows/evergreen-roi-cycle.yaml` — 27 passos, outcomes:

`PASS` | `FAIL_REWORK` | `BLOCKED_EXTERNAL` | `BLOCKED_HUMAN_DECISION` | `CONFLICT_WITH_ACTIVE_WORK` | `NO_UNLOCKED_WORK` | `ABORTED_UNSAFE_STATE`

## ROI

Pesos em `data/roi-weights.yaml`. Fórmula:

```
ROI = Σ(value_dim * w) / Σ(cost_dim * w)
```

Dimensões de valor: gate, unlock, operational, risk_reduction, evidence_gain.  
Dimensões de custo: effort, uncertainty, external_dependency, change_surface.

## Guardrails

- Nunca trabalhar na `main`
- Nunca force-push / auto-merge
- Nunca checkbox DoD sem PASS + evidência
- Fixtures ≠ live health
- PR aberta ≠ código em main
- Sem clones cognitivos; squad operacional de engenharia

## Retomada após interrupção

1. `python squads/extra-dod-roi/scripts/cli.py status`
2. `python squads/extra-dod-roi/scripts/stale_detect.py --state squads/extra-dod-roi/state/rankings/latest.json`
3. Se stale → `rank-next` de novo
4. Se ciclo em andamento → `*resume-cycle` (write)

## Validação

```bash
node -e "const {SquadValidator}=require('./.aiox-core/development/scripts/squad/squad-validator.js'); \
  new SquadValidator().validate('./squads/extra-dod-roi').then(r=>console.log(JSON.stringify(r,null,2)))"

python squads/extra-dod-roi/tests/test_squad_smoke.py
python squads/extra-dod-roi/scripts/cli.py rank-next --write-state
```

## Handoffs

Template: `templates/handoff.md`. Artefatos em `state/handoffs/`.

## Licença

UNLICENSED — uso privado neste repositório apenas.
