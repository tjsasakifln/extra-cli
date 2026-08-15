# Documentação operacional — Extra Consultoria

> **Atualizado:** 2026-07-25  
> **Propósito:** índice da documentação operacional **viva**.  
> **Estado de produto / onboarding:** [`README.md`](../../README.md) · **Dev canônico:** [`DEVELOPMENT.md`](../DEVELOPMENT.md) · **DoD:** [`DOD.md`](../../DOD.md)

## Host de record

| Item | Valor |
|------|--------|
| Provedor | Netcup RS 2000 G12 |
| SO / DB | Debian 13 · PostgreSQL 17 |
| SSH | `ssh ec-prod` |
| App | `/opt/extra-consultoria` |
| Remote | `https://github.com/tjsasakifln/extra-cli` |

Existência do host **não** autoriza claims `VPS_OPERATIONAL` / `LOCAL_READY` / `PROJECT_DONE`.

## Comece por aqui

| Documento | Descrição |
|-----------|-----------|
| [`NEXT-DEV-STEP.md`](NEXT-DEV-STEP.md) | Próximo passo operacional sem reconstruir contexto |
| [`runbook.md`](runbook.md) | Procedimentos: crawl, purge, backup, restore, migrations, health |
| [`monitoring.md`](monitoring.md) | Monitoramento e alertas |
| [`backup.md`](backup.md) | Backup PostgreSQL |
| [`private-assets.md`](private-assets.md) | Assets privados (repo público) |
| [`dod-convergence.md`](dod-convergence.md) | Harness de convergência DOD |
| [`onboarding.md`](onboarding.md) | Onboarding operacional |
| [`METRIC-DEFINITION-POLICY.md`](METRIC-DEFINITION-POLICY.md) | Política de definição de métricas |
| [`extra-technical-acervo.md`](extra-technical-acervo.md) | Acervo CAT/CAO Extra (store + CLI) |
| [`searxng-private-backend.md`](searxng-private-backend.md) | SearXNG privado CONFENGE (HTTP only, AGPL, canário) |

## Host / Netcup / recovery

| Documento | Descrição |
|-----------|-----------|
| [`netcup-inventory-live.md`](netcup-inventory-live.md) | Inventário live Netcup |
| [`netcup-phase0-activate.md`](netcup-phase0-activate.md) | Ativação fase 0 |
| [`handoff-2026-07-23-netcup-vps-backfill.md`](handoff-2026-07-23-netcup-vps-backfill.md) | Handoff backfill VPS |
| [`cloud-deployment-plan.md`](cloud-deployment-plan.md) | Plano de deploy (parcialmente histórico — ver banner) |
| Sessões `recovery-*` / `session-*` | Evidências pontuais (não docs vivas) |

## Campanhas (artefatos)

| Campanha | Path | Nota |
|----------|------|------|
| Historical contracts closure | `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/` | Backfill 3y + dual + off-site; soak 7d |
| Dual capability coverage | `specs/001-dual-capability-coverage-truth/` + evidências em `docs/ops/` / `output/coverage/` | ADR-030 |
| ADVANCE-30D (histórico) | `squads/extra-dod-roi/` + sessions 2026-07-18 | Campanha anterior |

## Workspace e produto diário

| Documento | Local |
|-----------|--------|
| Workspace guide | [`docs/operations/workspace-guide.md`](../operations/workspace-guide.md) |
| Weekly cycle | `make extra-weekly` / `python3 -m scripts.ops.weekly_cycle --strict` |
| Systemd units | `deploy/systemd/` |

## Pré-VPS / resiliência local (histórico)

Documentos em [`docs/operations/`](../operations/) com prefixo `PRE-VPS-*` e `LOCAL-RESILIENCE-*` são **snapshots** da fase pré-host.  
Use-os como auditoria; estado atual está no README e neste índice.

## Relacionados

| Documento | Local |
|-----------|--------|
| Arquitetura | [`docs/architecture/architecture.md`](../architecture/architecture.md) |
| ADRs | [`docs/architecture/adr/INDEX.md`](../architecture/adr/INDEX.md) |
| Stories | [`docs/stories/`](../stories/) |
| Hub geral | [`docs/INDEX.md`](../INDEX.md) |

---

**Não claimar** cobertura 95% open_tenders, `LOCAL_READY`, `VPS_OPERATIONAL` ou `PROJECT_DONE` a partir deste índice sem evidência no HEAD + DOD.

## Campanhas / sessões recentes

- [SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL (2026-07-29)](campaigns/SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL.md) — auditoria read-only soak + timers (`SCHEDULERS_FAILED`)
- [EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01](campaigns/EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01/PREMORTEM.md) — reparo checkpoint/locks/soak (campanha funcional)
