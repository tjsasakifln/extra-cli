# CI/CD Pipeline — Documentacao

**Story:** TD-4.2 | Setup CI/CD Pipeline
**Debts:** TD-OPS-01 (HIGH), TD-SYS-015 (MEDIUM)
**Data:** 2026-07-11

## Visao Geral

Pipeline de CI/CD implementado via GitHub Actions para garantir qualidade de codigo
em todo PR e push para `main`. Anteriormente, toda mudanca era aplicada manualmente
via SSH sem verificacoes automatizadas.

## Workflow

**Arquivo:** `.github/workflows/ci.yml`

### Trigger

| Evento | Branches |
|--------|----------|
| `push` | `main` |
| `pull_request` | `main` |

### Stages

```
push/PR
  |
  +-- lint (ruff check .)
  |
  +-- type-check (mypy .)
  |
  +-- test (pytest tests/ --cov)
  |
  +-- security (bandit -r scripts/)
  |
  All stages run in parallel for maximum speed.
```

| Stage | Ferramenta | Comando | Quando falha |
|-------|-----------|---------|-------------|
| Lint | ruff | `ruff check .` | Block PR |
| Type Check | mypy | `mypy .` | Block PR |
| Testes | pytest | `pytest tests/ --cov` | Block PR |
| Seguranca | bandit | `bandit -r scripts/` | Warning (continue-on-error) |

### Artefatos

- Relatorio de cobertura HTML disponivel como artefato do job `test`
- Cobertura tambem disponivel em `docs/td-001/coverage-reports/` (gerado localmente)

## Pre-requisitos Locais

Para rodar o mesmo pipeline localmente antes do push:

```bash
# Instalar ferramentas de qualidade
pip install ruff mypy pytest pytest-cov bandit

# Executar pipeline completo
bash scripts/ci-check.sh

# Apenas lint
bash scripts/ci-check.sh --lint-only

# Pular security scan (mais rapido)
bash scripts/ci-check.sh --quick
```

## Healthcheck Unificado

**Arquivo:** `scripts/healthcheck.py`

Healthcheck que verifica:

| Componente | O que verifica | Critico? |
|-----------|---------------|----------|
| DB | Conectividade PostgreSQL via `psql` | Sim |
| API Keys | Variaveis de ambiente obrigatorias (`OPENAI_API_KEY`) | Sim |
| Crawlers | Timers systemd ativos (via `systemctl list-timers`) | Warning |
| Disco | Uso de disco (>80% warn, >90% crit) | Warning/Critico |

**Uso:**

```bash
# Saida legivel
python scripts/healthcheck.py

# Saida JSON para monitoring tools
python scripts/healthcheck.py --json

# JSON silencioso
python scripts/healthcheck.py --json --quiet
```

**Exit codes:**
- `0` — Tudo OK
- `1` — Avisos (ex: disco > 80%)
- `2` — Falhas criticas (DB offline, API keys ausentes)

## Configuracao de Qualidade

### pyproject.toml

Myl configuracao de ferramentas de qualidade esta centralizada em `pyproject.toml`:

| Ferramenta | Secao |
|-----------|-------|
| mypy | `[tool.mypy]` — configuracao granular (sem `--strict` global) |
| ruff | `[tool.ruff]` — line-length 120, regras E/F/I/N/W/UP |
| pytest | `pytest.ini` — coverage, caminho de testes |

### Ignorando Regras

**mypy:** Modulos de terceiros (`psycopg2`, `httpx`, etc.) tem `ignore_missing_imports`.
Modulos de teste (`tests.*`, `scripts.reports.*`) tem `ignore_errors = true`.

**ruff:** `E501` (line length) e `N802` (lowercase function names) sao ignorados globalmente.
`__init__.py` permite `F401` (unused imports).

## Badge

[![CI Pipeline](https://github.com/tjsasakifln/extra-consultoria/actions/workflows/ci.yml/badge.svg)](https://github.com/tjsasakifln/extra-consultoria/actions/workflows/ci.yml)

```markdown
[![CI Pipeline](https://github.com/tjsasakifln/extra-consultoria/actions/workflows/ci.yml/badge.svg)](https://github.com/tjsasakifln/extra-consultoria/actions/workflows/ci.yml)
```

## Proximos Passos

- [ ] TD-4.3: Configurar lint automatizado como gatilho de pre-commit
- [ ] Adicionar CodeRabbit para code review automatizado (opcional)
- [ ] CD: Deploy automatico via GitHub Actions (atualmente manual via SSH)
- [ ] Monitoramento continuo com healthcheck schedule (TD-5.5)

## Referencias

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [ruff](https://docs.astral.sh/ruff/)
- [mypy](https://mypy.readthedocs.io/)
- [pytest](https://docs.pytest.org/)
- [bandit](https://bandit.readthedocs.io/)
