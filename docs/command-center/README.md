# EXTRA Command Center

Camada visual local e segura sobre o `extra-cli`.

**Campanha:** `EXTRA-LOCAL-COMMAND-CENTER-01`  
**Status terminal (quando executável):** `COMMAND_CENTER_READY_FOR_TIAGO_REVIEW`

## Zero to run

```bash
# Requisitos: Python 3.12+, fastapi, uvicorn, pydantic; Node 20+ (build UI)
pip install fastapi uvicorn pydantic   # se ainda não instalados
./bin/command-center
# ou: make command-center
```

Abre `http://127.0.0.1:8765` (bind somente localhost).

Dev (API + Vite):

```bash
./bin/command-center-dev
```

## O que é / o que não é

- É: UI + API local para descobrir capabilities, executar allowlist, acompanhar jobs, ler artifacts e registrar decisões humanas.
- Não é: nova fonte de verdade, SaaS multi-usuário, substituto do CLI, aceitador automático de DOD, nem sender de outreach.

## Portas e dados

| Item | Valor |
|------|--------|
| URL | `http://127.0.0.1:8765` |
| Host | `127.0.0.1` (override público exige `CC_ALLOW_PUBLIC_BIND=1`) |
| SQLite | `data/command_center/command_center.sqlite3` |
| Logs CC | `data/command_center/logs/` |
| Jobs | `data/command_center/jobs/` |

## Variáveis

| Var | Default | Notas |
|-----|---------|--------|
| `CC_HOST` | `127.0.0.1` | Nunca `0.0.0.0` por padrão |
| `CC_PORT` | `8765` | |
| `CC_OPEN_BROWSER` | `1` | `0` em CI |
| `CC_DATA_DIR` | `data/command_center` | |
| `CC_MAX_CONCURRENT_JOBS` | `2` | |
| `CC_JOB_TIMEOUT_SEC` | `3600` | |

Secrets/DSN **nunca** retornam conteúdo — só `configurada` / `ausente` / `inválida`.

## Testes

```bash
python3 -m pytest tests/command_center/ -q --tb=short
cd apps/command-center && npm test
# e2e (servidor rodando ou webServer do Playwright):
cd apps/command-center && npm run test:e2e
```

## Documentação

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [SECURITY.md](./SECURITY.md)
- [CAPABILITY-REGISTRY.md](./CAPABILITY-REGISTRY.md)
- [JOB-RUNNER.md](./JOB-RUNNER.md)
- [UX-PRINCIPLES.md](./UX-PRINCIPLES.md)
- [UX-HEURISTIC-REVIEW.md](./UX-HEURISTIC-REVIEW.md)
- [DEVELOPMENT.md](./DEVELOPMENT.md)
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

## Limpeza

```bash
rm -rf data/command_center/
```

Não remove `output/` nem bases operacionais.
