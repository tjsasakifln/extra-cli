# AGENTS.md — adaptador fino (Codex / agentes compatíveis)

**Guia canônico:** [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)  
**DoD:** [`DOD.md`](DOD.md)

Este arquivo **não** define requisitos de produto. Em conflito, prevalece:

1. `DOD.md`  
2. ADR vigente  
3. Código testado  
4. Evidência reproduzível  

## Comandos (mesmos do guia canônico)

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m pytest tests/ -q --tb=no -x
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

## Escopo / arquitetura / operação

Ver seções 2–3 de `docs/DEVELOPMENT.md`. Não inventar selos (`LOCAL_READY`, 95%, VPS) sem evidência.

## DOD Convergence (obrigatório)

**Norma:** `DOD.md` prevalece sobre código, stories e handoffs.

**Harness:** `python3 tools/dod_controller.py` · docs: `docs/ops/dod-convergence.md` · estado: `.dod/`

```bash
python3 tools/dod_controller.py scan
python3 tools/dod_controller.py status
python3 tools/dod_controller.py next
python3 tools/dod_controller.py start ITEM_ID
python3 tools/dod_controller.py verify ITEM_ID
python3 tools/dod_controller.py accept ITEM_ID   # só com gates; ACCEPTED no main
python3 tools/dod_controller.py audit
python3 tools/dod_controller.py report
```

**Regras invioláveis:**

- Nenhum merge sem CI verde e sem o teste do item correspondente passando.
- Nenhuma mudança de arquitetura fora do raio de impacto sem aviso explícito.
- Atualizar `DOD.md` / ADRs / handoffs faz parte do Done de cada item.
- Se dois subagentes colidirem no mesmo arquivo, parar a onda.
- Primeira onda pequena e validada antes de escalar.
- Não reduzir thresholds; não `skip`/`xfail`/mocks irreais para ocultar defeitos.
- Job `skipped` ≠ aprovado; ausência de execução ≠ sucesso.
- Somente estado `ACCEPTED` (evidência + main + CI) marca `[x]` no `DOD.md`.
- Um item por vez (máx. 2 pré-requisitos). Spec Kit: integração `grok`, workflow `dod-convergence`.
- Constituição: `.specify/memory/constitution.md`.
