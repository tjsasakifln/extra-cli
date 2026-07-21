# DOD Convergence Harness — operação

## Propósito

Sistema persistente que transforma `DOD.md` em manifesto executável, seleciona o
próximo item elegível e só marca `[x]` após gates reais (`ACCEPTED`).

## Layout

| Path | Função |
|------|--------|
| `DOD.md` | Norma de produto |
| `.dod/manifest.yaml` | Itens com IDs estáveis + estado |
| `.dod/state.json` | Item ativo, run_id, fase |
| `.dod/log.jsonl` | Eventos append-only |
| `.dod/blockers/` | Bloqueios estruturados |
| `.dod/evidence/<ITEM_ID>/` | Evidence packs |
| `.dod/schemas/` | JSON Schemas |
| `tools/dod_controller.py` | CLI do controlador |
| `.specify/memory/constitution.md` | Constituição Spec Kit |
| `.specify/workflows/dod-convergence/` | Workflow local |

## Comandos

```bash
python3 tools/dod_controller.py scan
python3 tools/dod_controller.py status
python3 tools/dod_controller.py next
python3 tools/dod_controller.py start ITEM_ID
python3 tools/dod_controller.py verify ITEM_ID
python3 tools/dod_controller.py accept ITEM_ID --update-dod   # só com gates
python3 tools/dod_controller.py block ITEM_ID --kind HUMAN --reason "..."
python3 tools/dod_controller.py resume ITEM_ID --mark-resolved
python3 tools/dod_controller.py audit
python3 tools/dod_controller.py report
```

Todos aceitam `--json`. Falhas de negócio → exit `1`; uso incorreto → exit `2`.

## Estados

`OPEN` → `IN_PROGRESS` → `IMPLEMENTED` → `VERIFIED` → `ACCEPTED`

Bloqueios: `BLOCKED_HUMAN|CREDENTIAL|EXTERNAL|INFRA|LIVE` · `DEFERRED_BY_DOD`

**Somente `ACCEPTED` no `main` com CI/evidência autoriza `[x]` no DOD.md.**

## Workflow Spec Kit

```bash
specify workflow list
# validar definição local:
python3 -c "import yaml; yaml.safe_load(open('.specify/workflows/dod-convergence/workflow.yml'))"
```

O workflow `dod-convergence` orquestra scan/audit/next + ciclo Spec Kit por item.
Gates humanos permanecem onde o schema exige `type: gate`.

## Spec Kit runtime vs artefatos normativos

- **Versionar:** `.dod/manifest.yaml`, schemas, evidence packs relevantes, constitution,
  workflow, `tools/dod_controller.py`, testes.
- **Ignorar (runtime):** `.specify/workflows/**/runs/`, estado efêmero de workflow se
  criado sob cache local (ver `.gitignore`).

## Precedência

1. `DOD.md`
2. Critérios de aceite registrados
3. Testes e evidências reproduzíveis
4. ADRs
5. Código atual
