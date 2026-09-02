# Índice da documentação — Extra Consultoria

**Atualizado:** 2026-08-31
**Regra:** docs **vivas** descrevem o estado atual; sessões e audits datados são **evidência/snapshot**, não onboarding.

Precedência: `DOD.md` → ADR vigente → código testado → evidência reproduzível.

---

## Ler agora (docs vivas)

| Documento | Papel |
|-----------|--------|
| [`README.md`](../README.md) | Onboarding, estado honesto, entry-points |
| [`DOD.md`](../DOD.md) | Definition of Done e gates |
| [`docs/DEVELOPMENT.md`](DEVELOPMENT.md) | Setup e comandos canônicos |
| [`docs/GLOSSARY.md`](GLOSSARY.md) | Termos e contagens |
| [`docs/ops/README.md`](ops/README.md) | Índice operacional |
| [`docs/ops/extra-technical-acervo.md`](ops/extra-technical-acervo.md) | Acervo CAT/CAO Extra (store canônico + CLI) |
| [`docs/ops/NEXT-DEV-STEP.md`](ops/NEXT-DEV-STEP.md) | Próximo passo sem reconstruir contexto |
| [`docs/operations/workspace-guide.md`](operations/workspace-guide.md) | Rotina diária CLI |
| [`docs/architecture/architecture.md`](architecture/architecture.md) | Visão C4 / stack |
| [`docs/architecture/adr/INDEX.md`](architecture/adr/INDEX.md) | ADRs vigentes |
| [`docs/canonical-entry-points.yaml`](canonical-entry-points.yaml) | Contrato de entry-points |
| [`CHANGELOG.md`](../CHANGELOG.md) | Marcos resumidos |

## Operação e campanhas

| Path | Papel |
|------|--------|
| `docs/ops/runbook.md`, `backup.md`, `monitoring.md` | Procedimentos |
| `docs/ops/private-assets.md` | Repo público vs assets privados |
| `docs/ops/dod-convergence.md` | Harness DOD |
| `docs/ops/netcup-*.md`, handoffs Netcup | Host de record |
| [`docs/ops/searxng-private-backend.md`](ops/searxng-private-backend.md) | SearXNG privado CONFENGE (HTTP boundary, runbook) |
| [`docs/ops/confenge-activation-planner.md`](ops/confenge-activation-planner.md) | Ciclo canônico, publicação atômica e freshness do feed Warmbly |
| [`docs/ops/national-census-operation.md`](ops/national-census-operation.md) | Census nacional retomável e gate factual #302 |
| [`docs/ops/handoff-2026-08-31-confenge-source-retry.md`](ops/handoff-2026-08-31-confenge-source-retry.md) | Retry limitado da fonte e pin das unidades-base CONFENGE |
| `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/` | Campanha HC (STATUS/HANDOFF) |
| `specs/001-*`, `specs/002-*` | Spec Kit dual / historical contracts |
| `deploy/systemd/` | Units de produção |

## Arquitetura e produto

| Path | Papel |
|------|--------|
| `docs/architecture/adr/` | Decisões (017–022, 028–030, 007…) |
| `docs/prd/` | PRD e missões |
| `docs/stories/` | Stories AIOX / épicos |
| `config/source_applicability.yaml` | Applicability de fontes |
| `config/coverage_slas.yaml` | SLAs de freshness |

## Histórico / snapshot (não usar como onboarding)

Adicionar mentalmente o banner: *estado atual = README + DEVELOPMENT + DOD*.

| Path | Natureza |
|------|----------|
| `docs/operations/PRE-VPS-*.md` | Auditoria pré-host |
| `docs/operations/LOCAL-RESILIENCE-*.md` | Resiliência local pré-VPS |
| `docs/guides/hetzner-supabase-plan.md` | Plano histórico Hetzner/Supabase |
| `docs/ops/cloud-deployment-plan.md` | Planejamento cloud (parcialmente superado pelo Netcup live) |
| `docs/ops/session-*`, `docs/ops/campaign-*` | Evidências de sessão |
| [`docs/ops/campaigns/SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL.md`](ops/campaigns/SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL.md) | Auditoria soak + systemd 2026-07-29 (`SCHEDULERS_FAILED`) |
| [`docs/ops/incidents/PNCP-458.md`](ops/incidents/PNCP-458.md) | Incidente PNCP #458: causa raiz, runbook, rollback e soak #248 |
| [`docs/ops/campaigns/EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01/PREMORTEM.md`](ops/campaigns/EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01/PREMORTEM.md) | Campanha fechamento operacional: checkpoint, locks, soak fail-closed |
| `docs/audits/`, `docs/baseline/`, `docs/coverage-truth/` | Audits e baselines datados |
| `docs/qa/gates/` | Gates de story (histórico de QA) |
| `docs/td-001/`, `docs/td-003/` | Dívida técnica / diffs |
| `_reversa_sdd/`, `_reversa_forward/` | Extração Reversa — **não** runtime truth |
| `plan/`, `plano-mestre-*.md` | Planos de campanha antigos |

## O que este índice **não** faz

- Não marca itens do `DOD.md`
- Não declara `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE` ou 95% open_tenders
- Não substitui evidência em `artifacts/` ou `output/`
