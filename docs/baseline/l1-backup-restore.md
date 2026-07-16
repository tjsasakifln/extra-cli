# L1.7 — Backup e restore local

**Story:** PE-L1-03  
**Data:** 2026-07-16

## Scripts

- `scripts/backup-database.sh` (existe)
- Documentação operacional em `docs/operations/` / deploy

## Execução nesta campanha

| Check | Status |
|-------|--------|
| Script legível e versionado | DONE |
| Postgres local em `:5433` | PASS (compose up) |
| Backup real + restore drill completo | **NOT EXECUTED** nesta sessão (tempo / risco de overwrite) |

## Veredito L1.7

**PARTIAL / OPEN** — script existe; **DoD exige teste efetivamente executado**. Registrar follow-up: backup dump + restore em DB throwaway.

**BLOCKER residual para GATE-1 total:** restore drill.
