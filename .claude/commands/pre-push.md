# /pre-push — Pre-Push Validation Gate (Shift-Left)

**NON-NEGOTIABLE.** Executa localmente os mesmos gates do CI antes de qualquer commit/push. O agente invoca este comando sozinho — o usuário não precisa lembrar.

## Quick Start

```
/pre-push
```

## O que este comando faz

Executa em sequência, parando na primeira falha bloqueante:

### Backend Gates

| Gate | Comando | Bloqueante? |
|------|---------|-------------|
| Lint | `cd backend && ruff check .` | Advisory (reporta, não bloqueia) |
| Type check | `cd backend && mypy . --ignore-missing-imports --check-untyped-defs` | Advisory (reporta, não bloqueia) |
| Tests | `cd backend && pytest tests/ -m "not benchmark and not external" --ignore=tests/fuzz --ignore=tests/integration --cov=. --cov-report=term-missing --cov-fail-under=71 -v` | **SIM — bloqueia push** |
| Module coverage | `cd backend && python scripts/check_module_coverage.py` | **SIM — bloqueia push** |

### Frontend Gates

| Gate | Comando | Bloqueante? |
|------|---------|-------------|
| Type check | `cd frontend && npx tsc --noEmit --pretty` | **SIM — bloqueia push** |
| Tests | `cd frontend && npm test -- --coverage --ci --no-cache` | **SIM — bloqueia push** |
| Build | `cd frontend && npm run build` | **SIM — bloqueia push** |

## Comportamento

1. Se **todos os gates bloqueantes passam**: reporta ✅ e permite commit/push.
2. Se **algum gate bloqueante falha**: reporta ❌, mostra o erro, e **NÃO permite push**. O agente DEVE corrigir e re-executar `/pre-push` antes de commitar.
3. Gates advisory (ruff, mypy): reporta warnings mas não bloqueiam.

## Quando usar

- **ANTES de `git commit`** (sempre — non-negotiable)
- **ANTES de `git push`** (sempre — non-negotiable)
- Manualmente: `/pre-push` para verificar estado atual

## Princípio

> O custo de feedback mais caro é round-trip até o CI remoto. O que o CI capturaria em minutos, o `/pre-push` captura em segundos localmente. Shift-left: feedback no momento do commit, não no momento do push.

---

Veja `.github/workflows/backend-tests.yml` e `.github/workflows/frontend-tests.yml` para os gates CI oficiais que este comando espelha.
