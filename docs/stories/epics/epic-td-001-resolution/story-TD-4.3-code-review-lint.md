# Story TD-4.3: Code Review + Lint Automatizado

**Status:** Done
**Epic:** EPIC-TD-001
**Executor:** @dev
**Quality Gate:** @architect
**Quality Gate Tools:** [coderabbit, pytest]
**Fase:** 4 -- Qualidade de Codigo
**Estimativa:** 1.5 horas
**Prioridade:** P2

## Description

Resolver dois deficits de qualidade de codigo no modulo `intel_pipeline.py`:

1. **TD-SYS-006 (LOW):** Uso de ANSI color codes manuais em `intel_pipeline.py:65-72` quando a biblioteca Rich ja esta disponivel no projeto. Substituir por formatacao Rich.
2. **TD-SYS-007 (LOW):** `import json` inline no meio da funcao em `monitor.py:493`. Mover para o topo do modulo conforme PEP 8.

## Business Value

Embora sejam deficits de baixa severidade, corrigi-los agora (antes da TD-4.2) garante que o primeiro run do CI (TD-4.2) ja passe limpo. ANSI codes manuais sao dificeis de manter e propensos a erros de escape. O `import json` inline viola PEP 8 e pode causar confusao em code review. Sao correcoes de 1.5h que eliminam ruido no lint e melhoram a legibilidade do codigo.

## Acceptance Criteria

- [x] AC1: Dado que `intel_pipeline.py` usa ANSI color codes manuais, Quando for substituido por Rich, Entao `rich.console.Console` ou `rich.markup` deve ser usado
- [x] AC2: Dado que os ANSI codes foram substituidos, Quando a saida visual for comparada, Entao o comportamento visual (cores, estilos) deve ser mantido
- [x] AC3: Dado que `monitor.py` tem `import json` inline na linha 493, Quando for movido para o topo, Entao o import deve estar no topo do modulo conforme PEP 8
- [x] AC4: Dado que as alteracoes sao apenas esteticas, Quando a logica de negocios for verificada, Entao nenhuma mudanca na logica de negocios deve ter sido feita
- [x] AC5: Dado que Rich sera usado, Quando as dependencias do projeto forem verificadas, Entao Rich deve estar disponivel nas dependencias do projeto

## Scope

### IN
- Substituicao de ANSI codes por Rich
- Movimentacao de import json para topo do modulo

### OUT
- Outras correcoes de estilo PEP 8
- Configuracao de linters (sera na TD-4.2)

## Dependencies

- Bloqueado por: TD-4.2 (CI pipeline para validar lint)
- Bloqueia: NONE

## Risks

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Rich nao esta disponivel nas dependencias do projeto | BAIXA | MEDIO | Verificar requirements.txt antes de comecar; se faltar, adicionar como dependencia |
| Substituicao de ANSI codes altera formatacao da saida de forma inesperada | BAIXA | BAIXO | Testar visualmente a saida apos mudanca; manter cores equivalentes |
| Mover import json para topo causa conflito se houver import circular | BAIXA | BAIXO | Verificar se o import inline era para evitar import circular; se sim, documentar e manter |

## Technical Notes

Referencias ao assessment:
- TD-SYS-006 (LOW): ANSI color codes manuais com Rich disponivel -- 1h
- TD-SYS-007 (LOW): `import json` inline no meio da funcao -- 0.5h
- Rich ja disponivel no projeto (verificar requirements.txt)
- PEP 8: imports devem estar no topo do modulo

## Definition of Done

- [x] ANSI codes substituidos por Rich
- [x] import json no topo do modulo (ja resolvido em refatoracao anterior — ver Dev Notes)
- [x] `ruff check .` passando nos arquivos modificados

## Dev Notes

### TD-SYS-006: ANSI codes -> Rich (intel_pipeline.py)
- Removidas 7 constantes ANSI manuais (`_C_RESET`, `_C_GREEN`, `_C_RED`, `_C_YELLOW`, `_C_CYAN`, `_C_BOLD`, `_C_MAGENTA`)
- Substituido por `from rich import print` e funcoes helper com markup Rich (`[green]text[/green]`)
- Adicionado `from rich.markup import escape` para sanitizar dados nao-confiaveis
- Rich ja estava disponivel em `requirements.txt` (`rich>=13.0.0`) — AC5 verificado
- Cores mantidas: green=OK, red=ERRO, yellow=warn, cyan=info, bold=header
- Testes: 175 pytest passaram sem falhas

### TD-SYS-007: import json inline (monitor.py)
- **Ja resolvido** — o arquivo `scripts/crawl/monitor.py` atual (187 linhas) nao contem `import json` em lugar nenhum. A linha 493 referenciada no assessment pertence a uma versao anterior do arquivo que foi refatorada antes desta story.
- Adicionados `# noqa: E402` nos re-exports apos `sys.path.insert(0, ...)` para documentar que a posicao e intencional.

### Ruff auto-fixes aplicados
- `F401`: `typing.Any` unused import removido
- `UP017`: `timezone.utc` -> `datetime.UTC`
- `UP015`: `open(path, "r")` -> `open(path)`
- `F541`: f-strings sem placeholders convertidas para strings
- `I001`: imports reordenados
- `E741`: variavel `l` renomeada para `ln`
- `N806`: `BID_WEIGHTS` -> `bid_weights`, `THRESHOLD` -> `threshold`

### Lint report
- `ruff check scripts/intel_pipeline.py` — All checks passed
- `ruff check scripts/crawl/monitor.py` — All checks passed
- Configuracao de linters e pre-commit hooks sera feita na TD-4.2 (OUT de escopo)

## File List

- `scripts/intel_pipeline.py` (modificado -- ANSI codes para Rich + ruff fixes)
- `scripts/crawl/monitor.py` (modificado -- noqa E402 adicionado)
- `docs/td-001/lint-setup.md` (criado -- documentacao das alteracoes)
- `plan/self-critique-TD-4.3.json` (criado -- autoavaliacao)

## Change Log

| Data | Versao | Descricao | Autor |
|------|--------|-----------|-------|
| 2026-07-11 | 1.0.0 | Story criada | @pm |
| 2026-07-11 | 1.0.1 | Validated GO (10/10) — Adicionados: Business Value, Risks, ACs em GWT, Executor, Quality Gate, Prioridade | @po |
| 2026-07-11 | 2.0.0 | Development started (YOLO mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | 2.0.0 | ANSI codes substituidos por Rich em intel_pipeline.py — TD-SYS-006 | @dev |
| 2026-07-11 | 2.0.0 | import json inline ja resolvido em monitor.py — TD-SYS-007 ja fixado | @dev |
| 2026-07-11 | 2.0.0 | ruff auto-fixes + N806/E741 manuais — 0 erros nos arquivos | @dev |
| 2026-07-11 | 2.0.0 | pytest: 175 passed, 0 failed — sem regressoes | @dev |
| 2026-07-11 | 2.0.0 | Development complete — Status: InProgress → InReview | @dev |
| 2026-07-11 | 2.0.1 | QA Gate PASS — Status: InReview → Done | @qa |

## QA Results

### Review Date: 2026-07-11

### Reviewed By: Quinn (Guardian)

### 7 Quality Checks

| Check | Result | Details |
|-------|--------|---------|
| 1. Code Review | PASS | ANSI codes substituidos por Rich markup (7 funcoes helper: _c, _ok, _err, _warn, _info, _bold, _magenta). Rich.escape() sanitiza dados nao-confiaveis. noqa E402 documentado em monitor.py. Ruff fixes: F401, UP017, UP015, F541, I001, E741, N806 — todos limpos. |
| 2. Unit Tests | PASS (190/191) | 190 passed, 1 failed pre-existente (test_transparencia_crawler.py::TestDetectPlatform::test_not_found — DuckDuckGo API behavior change, nao relacionado a esta story). |
| 3. Acceptance Criteria | PASS (5/5) | AC1: Rich markup implementado ✓. AC2: Cores equivalentes mantidas ✓. AC3: import json ja resolvido ✓. AC4: Nenhuma logica de negocios alterada ✓. AC5: rich>=13.0.0 em requirements.txt ✓. |
| 4. No Regressions | PASS | Nenhum teste quebrado pelas alteracoes. _run_script() e funcoes gate mantidas. |
| 5. Performance | PASS | Rich markup negligivel vs ANSI. escape() adiciona overhead minimo. |
| 6. Security | PASS | Rich.escape() adicionado para sanitizar stdout/stderr e dados de editais — melhoria de seguranca. |
| 7. Documentation | PASS | docs/td-001/lint-setup.md criado com sumario completo. Dev Notes detalhados na story. |

### Additional Verification

| Check | Result |
|-------|--------|
| ruff check scripts/intel_pipeline.py | All checks passed |
| ruff check scripts/crawl/monitor.py | All checks passed |
| Rich dependency | rich>=13.0.0 em requirements.txt |

### Gate Status

Gate: PASS → docs/qa/gates/td-4.3-code-review-lint-automatizado.yml
