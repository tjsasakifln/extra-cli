# DOD Convergence Harness — operação

## Propósito

Sistema persistente que transforma `DOD.md` em manifesto executável, seleciona o
próximo item elegível e só marca `[x]` após gates reais (`ACCEPTED` auditado).

**Fail-closed:** checkbox `[x]` é *claim*, não aceite. Diretório de evidência
sozinho **não** autoriza `ACCEPTED`.

## Layout

| Path | Função |
|------|--------|
| `DOD.md` | Norma de produto |
| `.dod/manifest.yaml` | Itens com IDs estáveis + estado |
| `.dod/state.json` | Item ativo, run_id, fase, `next_step` |
| `.dod/log.jsonl` | Eventos append-only |
| `.dod/blockers/` | Bloqueios estruturados |
| `.dod/evidence/<ITEM_ID>/` | Evidence packs |
| `.dod/schemas/` | JSON Schemas |
| `tools/dod_controller.py` | CLI do controlador |
| `.specify/memory/constitution.md` | Constituição Spec Kit |
| `.specify/workflows/dod-convergence/` | Workflow local |

## Métricas (não confundir)

| Métrica | Significado |
|---------|-------------|
| `claimed_checked` | Checkbox `[x]` no DOD (`dod_checked`) |
| `audited_accepted` | `state=ACCEPTED` **e** evidência não fraca **e** `acceptance_commit` |
| `evidence_located` | Paths de evidência existem no disco |
| `evidence_reproduced` | `verify_result.json` com `ok=true` |
| `proof_debt` | Claim sem aceite auditado, ou ACCEPTED fraco |
| `acceptance_pct` | `audited_accepted / total` (não claimed) |

Um item `[x]` **não** é considerado auditado só por estar marcado.

## Comandos

```bash
python3 tools/dod_controller.py scan
python3 tools/dod_controller.py status
python3 tools/dod_controller.py next
python3 tools/dod_controller.py next --max-items 3
python3 tools/dod_controller.py start ITEM_ID
python3 tools/dod_controller.py verify ITEM_ID
python3 tools/dod_controller.py accept ITEM_ID --update-dod   # só com gates
python3 tools/dod_controller.py block ITEM_ID --kind HUMAN --reason "..."
python3 tools/dod_controller.py resume ITEM_ID --mark-resolved
python3 tools/dod_controller.py audit
python3 tools/dod_controller.py report
```

Todos aceitam `--json`. Falhas de negócio → exit `1`; uso incorreto → exit `2`.

### Verify (fail-closed)

- Exige `acceptance_criteria.md` no pack.
- Exige `acceptance_commands` e/ou `tests` **não triviais**.
- Rejeita: `true`, `:`, `echo…`, `exit 0`, help/version-only, lista vazia.
- Grava `verify_result.json` com cmd, exit code, env (sanitizado), duração,
  contagens pytest (passed/failed/skipped/deselected) quando aplicável.
- `--mark-if-empty` **não** produz `VERIFIED`.

### Accept (fail-closed)

Requer, salvo bypass harness explícito:

1. `state == VERIFIED`
2. Branch `main`/`master` (ou `--allow-non-main` harness)
3. Commit HEAD identificado
4. Pack completo: `acceptance_criteria.md` + `verify_result.json` (`ok=true`)
5. Pelo menos um comando/teste **substantivo** verde no verify
6. `ci_status.json` com `conclusion=success` e `head_sha` alinhado
7. `full_suite_status.json` se o item exige suíte global
8. Sem jobs mandatórios skipped
9. `review_status.json` sem `pending_changes_requested`
10. Sem divergência DOD/manifest crítica
11. `independent_review.md` não vazio
12. `--update-dod` só após gates

Bypass flags (`--skip-ci-gate`, etc.) existem **apenas** para testes do harness;
não usar em campanha real.

Artifacts de exemplo no pack:

```json
// ci_status.json
{"conclusion": "success", "head_sha": "<git sha>", "mandatory_jobs_skipped": []}

// review_status.json
{"pending_changes_requested": false}

// full_suite_status.json (quando necessário)
{"ok": true, "command": "python3 -m scripts.ops.run_full_suite", "exit_code": 0}
```

Se `verify_result.head_sha` ≠ HEAD atual, exigir
`immutability_justification.md` ou re-rodar verify.

## Estados

`OPEN` → `IN_PROGRESS` → `IMPLEMENTED` → `VERIFIED` → `ACCEPTED`

Bloqueios: `BLOCKED_HUMAN|CREDENTIAL|EXTERNAL|INFRA|LIVE` · `DEFERRED_BY_DOD`

**Somente `ACCEPTED` auditado no `main` com CI/evidência autoriza `[x]` no DOD.md.**

Scan **não** promove `[x]` → `ACCEPTED`. Histórico ACCEPTED no manifesto é
preservado no merge; audit reporta *proof debt* sem mass-uncheck.

## Seleção `next`

Não usa só keyword + linha. Considera:

- dependências (`dependencies[]` todas `ACCEPTED`)
- quantos itens o candidato destrava (`unlock_count`)
- fase atual (`state.phase`)
- aplicabilidade/categoria
- caminho crítico (keywords)
- custo aproximado
- impacto esperado no DOD

Quando nada é elegível: `next_step=stop_all_blocked`.

## Workflow Spec Kit

```bash
specify workflow list
# validar definição local:
python3 -c "import yaml; yaml.safe_load(open('.specify/workflows/dod-convergence/workflow.yml'))"
```

O workflow `dod-convergence` **não** usa `audit … || true` nem `verify … || true`.
Falha interrompe ou grava blocker estruturado e tenta outro item se `max_items`
ainda permite. Loop de converge usa sinal objetivo em
`.dod/state.converge_item_continue` (nunca `condition: "false"` fixo).

## Publish boundary

Este harness **não** automatiza push, PR, merge nem “CI verde”.

| Ação | Quem | Como |
|------|------|------|
| Push / PR / merge | `@devops` apenas | `git push`, `gh pr create/merge` fora do workflow |
| Popular `ci_status.json` | operador / script | ex. `gh run list --json conclusion,headSha` |
| Independent review | agente distinto do implementador | `independent_review.md` |
| Refresh main | operador explícito | `git fetch origin main` + rebase/merge consciente |

Scripts de prontidão são documentação + checks locais, não publicação.

## Spec Kit runtime vs artefatos normativos

- **Versionar:** `.dod/manifest.yaml`, schemas, evidence packs relevantes, constitution,
  workflow, `tools/dod_controller.py`, testes.
- **Ignorar (runtime):** `.specify/workflows/**/runs/`,
  `.dod/state.converge_continue`, `.dod/state.converge_item_continue`,
  `.dod/state.max_items` (efêmeros de loop).

## Precedência

1. `DOD.md`
2. Critérios de aceite registrados
3. Testes e evidências reproduzíveis
4. ADRs
5. Código atual

## Campanha harness

Relatório desta trilha:
`docs/ops/campaigns/DOD-CONVERGENCE-EXTRA-CONTINUE-02/tracks/harness-hardening-report.md`
