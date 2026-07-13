# /code-review — Revisão de Código Local com Foco em Python

## Propósito

Revisar mudanças locais (uncommitted) ou PR com foco em qualidade, segurança e padrões Python.
Bloqueia commit se encontrar CRÍTICO ou ALTO.

## Modos

### Modo Local (default)

Roda sobre mudanças não commitadas. 3 fases.

#### Fase 1 — COLETAR

```bash
git diff --name-only HEAD
git diff HEAD  # diff completo
```

Se sem mudanças → para.

#### Fase 2 — REVISAR

Ler cada arquivo modificado. Classificar achados:

**🔴 CRÍTICO (bloqueia):**
- Hardcoded secrets, tokens, senhas
- `eval`, `exec`, `pickle.load` com dados externos
- `shell=True` em subprocess
- `yaml.load` sem SafeLoader
- SQL injection (string concatenada em query)
- `except:` bare ou `except: pass`
- `verify=False` em requests

**🟠 ALTO (bloqueia):**
- Função > 50 linhas
- Arquivo > 800 linhas
- Mais de 4 níveis de aninhamento
- Função pública sem type hints
- `except Exception` sem log nem raise
- Mutable default argument (`def f(x=[])`)
- Falta de timeout em chamada HTTP
- `== None` em vez de `is None`
- Uso de `type()` em vez de `isinstance()`
- Log sem contexto (URL, etapa, erro)

**🟡 MÉDIO (reporta):**
- PEP 8 (nomes, espaçamento)
- Docstring ausente em função pública
- `print()` em vez de `logging`
- Wildcard import (`from x import *`)
- Shadowing de builtins
- Número mágico sem constante
- Código comentado sem explicação

#### Fase 3 — REPORTAR

```markdown
## Review de Código — {data}

### Arquivos modificados
{lista}

### Achados

| Sev | Arquivo:Linha | Problema | Correção |
|-----|---------------|----------|----------|

### Validação automatizada

| Ferramenta | Resultado |
|------------|-----------|
| `ruff check` | ✅ / ❌ (N erros) |
| `mypy` | ✅ / ❌ (N erros) |
| `pytest` | ✅ / ❌ (N falhas) |
| `bandit` | ✅ / ❌ (N issues) |

### Decisão
- ✅ APPROVE — sem CRÍTICO/ALTO
- 🔴 BLOCK — CRÍTICO ou ALTO encontrado
```

### Modo PR

Quando `$ARGUMENTS` contém número de PR, URL ou `--pr`:

```bash
gh pr view $PR_NUMBER --json title,body,headRefName,baseRefName,state
gh pr diff $PR_NUMBER
gh pr view $PR_NUMBER --json reviews,statusCheckRollup
```

8 fases: FETCH → CONTEXT → REVIEW → VALIDATE → DECIDE → REPORT → PUBLISH → OUTPUT

Publica review via `gh pr review` com `--approve`, `--request-changes` ou `--comment`.

## Validação Automatizada

Detecta tipo de projeto e roda ferramentas:

| Projeto | Ferramentas |
|---------|------------|
| Python (`pyproject.toml`, `setup.py`) | `ruff check`, `mypy`, `pytest --cov`, `bandit` |
| Node.js (`package.json`) | `npm run lint`, `npm run typecheck`, `npm test` |
| Ambos | Todas acima |

## Edge Cases

- **gh CLI ausente** → fallback para modo local
- **Sem pyproject.toml** → usa `ruff check scripts/`, `mypy scripts/`, `pytest`
- **PR > 50 arquivos** → alerta de escopo, prioriza source → tests → config
- **Draft PR** → sempre COMMENT (nunca APPROVE/REQUEST_CHANGES)
- **Apenas docs/config** → review mais leve (só CRÍTICO bloqueia)
