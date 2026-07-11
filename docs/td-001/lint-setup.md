# Lint Setup — Progress Report (TD-4.3)

**Story:** TD-4.3 (Code Review + Lint Automatizado)
**Date:** 2026-07-11
**Status:** Done
**Related to:** TD-SYS-006, TD-SYS-007

## Summary

Substituicao de ANSI color codes manuais por Rich markup em `intel_pipeline.py`. Verificacao e correcao de `import json` inline em `monitor.py` (ja resolvido). Linting automatizado via `ruff` com correcoes aplicadas.

## Changes Made

### 1. `scripts/intel_pipeline.py` — ANSI codes para Rich (TD-SYS-006)

**Problem:** O arquivo usava constantes ANSI manuais (`\033[92m`, `\033[91m`, etc.) nas linhas 64-72, apesar de Rich ja estar disponivel como dependencia do projeto.

**Solution:**
- Removidas 7 constantes ANSI (`_C_RESET`, `_C_GREEN`, `_C_RED`, `_C_YELLOW`, `_C_CYAN`, `_C_BOLD`, `_C_MAGENTA`)
- Adicionado `from rich import print` como substituto do built-in `print()` — Rich's print entende markup e gerencia deteccao de TTY automaticamente
- `_c()` function modificada para retornar markup Rich (`[green]text[/green]`) em vez de ANSI escapes
- Adicionado `from rich.markup import escape` para sanitizar dados nao-confiaveis (subprocess stdout/stderr, dados de editais)
- Renomeadas variaveis `BID_WEIGHTS` e `THRESHOLD` para `bid_weights` e `threshold` (N806)
- Variavel `l` renomeada para `ln` (E741 — nome ambíguo)

**Ruff auto-fixes aplicados:**
- `UP017`: `timezone.utc` -> `datetime.UTC`
- `UP015`: `open(path, "r")` -> `open(path)`
- `F541`: f-strings sem placeholders -> strings normais
- `F401`: `typing.Any` importado mas nao usado -> removido
- `I001`: imports reordenados

### 2. `scripts/crawl/monitor.py` — Import json inline (TD-SYS-007)

**Status:** Ja resolvido em refatoracao anterior.

O arquivo atual nao contem `import json` em lugar nenhum. O debito TD-SYS-007 (que referenciava `import json` inline na linha 493 de uma versao anterior) ja foi resolvido em uma refatoracao previa.

Adicionados `# noqa: E402` nos re-exports apos `sys.path.insert()` para documentar que a posicao e intencional.

## Ruff Configuration

Nenhuma configuracao de ruff foi adicionada (configuracao de linters prevista para TD-4.2). O ruff roda com regras default e apresenta 0 erros nos arquivos modificados.

## Verification

| Check | Result |
|-------|--------|
| `ruff check scripts/intel_pipeline.py` | All checks passed |
| `ruff check scripts/crawl/monitor.py` | All checks passed |
| `pytest tests/ -v` | 175 passed |

## Remaining Items (for TD-4.2)

- Configuracao de `ruff.toml` ou `pyproject.toml` com regras do projeto
- Pre-commit hook via `.pre-commit-config.yaml`
- CI integration
