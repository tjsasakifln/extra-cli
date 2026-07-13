---
story_id: B2G-4
status: draft
priority: P1
epic: EPIC-MASTER-B2G-READINESS
agent: @dev
depends_on: [TD-7.1]
---

# Story B2G-4: Quality Gate Automation

## Context

O projeto Extra Consultoria possui qualidade de codigo em evolucao, mas sem barreiras automatizadas que impeçam regressao. Atualmente:

- Ruff lint: 222 erros (apos auto-fix, antes 932) — sem gate que impeça nova regressao
- Ruff format: 96/96 arquivos formatados — sem verificacao pre-commit
- Mypy: 706+ erros em 60+ arquivos — sem gate de tipos
- Testes: 439 tests passando, cobertura ~6% — sem gate de cobertura
- Bandit: nunca executado — sem scan de seguranca
- Pre-commit hook: nao existe — commits passam com CRITICAL/HIGH findings

Esta story cria um **quality gate automatizado** que:

1. Roda pre-commit (local, rapido): ruff format --check + ruff check
2. Roda CI-like script (manual ou timer): mypy + pytest + bandit
3. Bloqueia commit se CRITICAL/HIGH findings encontrados
4. Reporta PASS/FAIL de forma clara

### Relacao com TD-4.3

TD-4.3 (Code review + lint automatizado) ja existe em EPIC-TD-001 e cobre CI/CD pipeline integracao. B2G-4 foca no **pre-commit hook local** + **script verificavel manualmente** que pode rodar antes de TD-4.2/4.3 estarem prontos. B2G-4 e o gate minimo viavel; TD-4.3 e a evolucao para CI/CD completo.

## Acceptance Criteria

1. **AC1: Pre-commit hook funcional** — `git commit` executa `ruff format --check scripts/` e `ruff check scripts/` automaticamente. Se qualquer um falhar, commit e bloqueado com mensagem clara. Hook instalavel via `scripts/install-hooks.sh`
2. **AC2: `scripts/ci-check.sh` criado** — Script unico que executa: (a) ruff format --check, (b) ruff check, (c) mypy (nos modulos configurados), (d) pytest (com --tb=short), (e) bandit (scan basico). Cada etapa reporta PASS/FAIL independentemente
3. **AC3: Bloqueio por CRITICAL/HIGH** — Se ruff check encontrar erros CRITICAL ou HIGH, o script reporta FAIL e bloqueia o commit. MEDIUM/LOW sao warnings (nao bloqueiam)
4. **AC4: Mypy gate** — Mypy executa nos modulos core configurados em `pyproject.toml`. Se encontrar erros `no-untyped-def` ou `no-any-return` NOVOS (vs baseline), reporta FAIL
5. **AC5: Bandit scan** — `bandit -r scripts/ -c pyproject.toml` executa. Findings HIGH/CRITICAL bloqueiam (FAIL); MEDIUM/LOW sao warnings
6. **AC6: Cobertura minima** — `pytest --cov --cov-fail-under=10` executa. Se cobertura cair abaixo de 10%, reporta FAIL
7. **AC7: Report claro** — `scripts/ci-check.sh` produz saida formatada com cores (via `rich` ou escape codes ANSI): cada etapa com [PASS] ou [FAIL] e resumo ao final: "CI Check: PASS (5/5)" ou "CI Check: FAIL (3/5) - Etapas: ruff-format, ruff-check, mypy"
8. **AC8: Ignore config** — `ci-check.sh` aceita `--ignore=etapa1,etapa2` para pular etapas em emergencia. Lista de ignore e logada no output
9. **AC9: Install hook** — `scripts/install-hooks.sh` instala o pre-commit hook no `.git/hooks/pre-commit` e verifica dependencias (ruff, mypy, pytest, bandit instalados). Reporta se alguma dependencia faltar
10. **AC10: Testes** — Testes unitarios para `ci-check.sh` (simular cada etapa passando/falhando) e `install-hooks.sh` (verificar instalacao)

## Technical Design

### Pre-commit hook

```bash
#!/bin/bash
# .git/hooks/pre-commit (instalado por install-hooks.sh)

echo "=== Extra Consultoria Quality Gate ==="

# Ruff format check
ruff format --check scripts/
if [ $? -ne 0 ]; then
    echo "[FAIL] ruff format --check — execute 'ruff format scripts/' antes de commitar"
    exit 1
fi
echo "[PASS] ruff format --check"

# Ruff check
ruff check scripts/
if [ $? -ne 0 ]; then
    echo "[FAIL] ruff check — corrija os erros antes de commitar"
    exit 1
fi
echo "[PASS] ruff check"

echo "=== Quality Gate PASS ==="
exit 0
```

### CI-like script

```bash
#!/bin/bash
# scripts/ci-check.sh

set -e

PASS=0
FAIL=0
STEPS=("ruff-format" "ruff-check" "mypy" "pytest" "bandit")
IGNORE=()

# Parse --ignore
for arg in "$@"; do
    case $arg in
        --ignore=*)
            IGNORE+=("${arg#*=}")
            shift
            ;;
    esac
done

run_step() {
    local name="$1"
    local cmd="$2"
    local severity="$3"

    # Check if ignored
    for ign in "${IGNORE[@]}"; do
        if [ "$ign" == "$name" ]; then
            echo "[SKIP] $name (ignored via --ignore)"
            return 0
        fi
    done

    echo "=== $name ==="
    if eval "$cmd"; then
        echo "[PASS] $name"
        PASS=$((PASS + 1))
        return 0
    else
        echo "[FAIL] $name"
        FAIL=$((FAIL + 1))
        if [ "$severity" == "block" ]; then
            return 1
        fi
        return 0
    fi
}

echo "=== Extra Consultoria CI Check ==="
echo ""

run_step "ruff-format" "ruff format --check scripts/" "block" || exit 1
run_step "ruff-check" "ruff check scripts/" "block" || exit 1
run_step "mypy" "mypy scripts/ --stats" "warn" || true
run_step "pytest" "python3 -m pytest tests/ -v --tb=short --cov --cov-fail-under=10 2>&1 | tail -20" "warn" || true
run_step "bandit" "bandit -r scripts/ -c pyproject.toml 2>&1 | tail -10" "block" || exit 1

echo ""
echo "=== Resultado: $PASS/$(( ${#STEPS[@]} - ${#IGNORE[@]} )) etapas passaram ==="
if [ $FAIL -eq 0 ]; then
    echo "CI Check: PASS"
    exit 0
else
    echo "CI Check: FAIL ($FAIL etapa(s) falharam)"
    exit 1
fi
```

### pyproject.toml changes

```toml
[tool.bandit]
exclude_dirs = ["tests", "supabase"]
skips = ["B101", "B303", "B311", "B404", "B603", "B607"]
```

## Files to Create/Modify

- **CREATE** `scripts/ci-check.sh` — Script de CI check
- **CREATE** `scripts/install-hooks.sh` — Instalador de pre-commit hook
- **CREATE** `tests/test_ci_check.sh` — Testes para o CI check (bats ou shell script)
- **MODIFY** `pyproject.toml` — Adicionar configuracao bandit
- **MODIFY** `.gitignore` — Garantir que arquivos gerados nao sejam versionados (se necessario)

## Rollback

- `scripts/install-hooks.sh --uninstall` remove o pre-commit hook
- `scripts/ci-check.sh` e apenas um script — deletar ou ignorar

## Observability

- Pre-commit hook loga falhas no console e retorna exit code 1 (bloqueia commit)
- `scripts/ci-check.sh` pode ser executado manualmente a qualquer momento
- Cron sugerido: `ci-check.timer` semanal para verificar regressao

## Security Considerations

- Bandit escaneia por vulnerabilidades OWASP — faz parte do gate
- Pre-commit hook e local (sem envio de dados para servidores externos)
- Nenhum secret ou credencial e exposto pelo hook

## Tests

- `test_ci_check_ruff_format_pass` — Simular ruff format passando
- `test_ci_check_ruff_format_fail` — Simular ruff format falhando
- `test_ci_check_ignore` — Verificar que --ignore funciona
- `test_install_hooks` — Verificar instalacao do hook
- `test_pre_commit_block` — Verificar que pre-commit bloqueia com erro

## Definition of Done

- [ ] AC1 a AC10 implementados e verificados
- [ ] `scripts/install-hooks.sh` instalado e funcional
- [ ] `git commit` bloqueado quando ruff check falha
- [ ] `scripts/ci-check.sh` executa e reporta PASS/FAIL corretamente
- [ ] `ruff check scripts/` retorna 0 erros apos cleanup
- [ ] `pytest tests/` passa sem falhas
- [ ] Projeto .claude/CLAUDE.md atualizado com comando `scripts/ci-check.sh`
