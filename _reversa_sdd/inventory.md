# Inventário do Sistema — Extra Consultoria

> 🟢 **CONFIRMADO** — re-extração Scout em **2026-07-27**  
> HEAD: `ffbb9608` | Última extração: 2026-07-17 (`d3e82ba`)  
> Motivo: atualização **completa e profunda** dos documentos de auditoria pós **~445 commits**  
> Delta: **2.547 arquivos** tocados desde `d3e82ba` (**+615.389 / −11.033** LOC no diff global)

> **Escopo almejado:** `DOD.md` (raiz) é a definição canônica do que o projeto deve ser. Inventário abaixo = superfície **as-is**. Ver `_reversa_sdd/target-scope-dod.md`.

---

## 1. Visão geral

| Atributo | Valor |
|----------|-------|
| **Projeto** | Extra Consultoria — plataforma B2G / DataLake de compras públicas |
| **Linguagem principal** | Python 3.12 |
| **Arquivos rastreados (git)** | **5.721** (era 3.352 em 2026-07-17) |
| **LOC Python** | **~293.574** (era ~178.915) |
| **Arquivos Python** | **797** (era 435) |
| **Banco** | PostgreSQL 16 + PostGIS (+ pgvector onde aplicável); local via Docker; produção VPS Netcup |
| **Orquestração** | systemd timers (**26 services / 25 timers**) + CLI scripts + campanhas CONFENGE/CMI |
| **CI** | GitHub Actions fail-closed (`ci.yml`, `pr-reviewability.yml`) — ruff, mypy, pytest, bandit; sem `\|\| true` em gates de integridade |
| **Testes** | **~250** arquivos de teste (unit / integration / smoke / chaos / adversarial) |
| **DoD / CMI** | Campanha de market intelligence com 47 itens ACCEPTED; evidence packages + rebind de SHA |

Sistema **batch/CLI-first** de inteligência de licitações e contratos públicos (SC, nacional, multi-fonte), sem frontend de produto. Documentação, AIOX, Reversa e artefatos de campanha convivem no monorepo.

---

## 2. Contagem por linguagem (git ls-files)

| Linguagem | Extensões | Arquivos | Observação |
|-----------|-----------|---------:|------------|
| Markdown | `.md` | 2.135 | docs, stories, DoD, campanhas, AIOX |
| JSON | `.json` | 1.292 | configs, evidências, packages de campanha |
| **Python** | `.py` | **797** | Núcleo de negócio |
| JavaScript | `.js` | 579 | tooling AIOX / vendors |
| YAML | `.yaml` / `.yml` | 197 | setores, CI, configs |
| Texto | `.txt` | 140 | logs/listas/evidence text |
| SQL | `.sql` | 97 | migrations + schema |
| Shell | `.sh` | 31 | deploy, bootstrap, gates |
| systemd | `.service` / `.timer` | 51 | operação VPS |
| TOML | `.toml` | 16 | pyproject, configs |
| CSV | `.csv` | 56 | universos, samples |
| Outros | png, jsonl, xlsx, hbs… | — | relatórios e fixtures |

---

## 3. Módulos identificados (**37** unidades de spec)

### 3.1 Domínio de aplicação (`scripts/`)

| Módulo | `.py` | LOC (approx) | Papel | Status vs 2026-07-17 |
|--------|------:|-------------:|-------|----------------------|
| **crawl** | 108 | 42.684 | Crawlers multi-fonte, resilience, DLQ, watermarks, provenance | Expandido |
| **ops** | 92 | 39.140 | Gates, CONFENGE, CMI, weekly, migrations, hygiene, campaigns | ✨ **explodiu** (era ~0,5K LOC) |
| **coverage** | 26 | 18.484 | Coverage contract, dual capability, edital relevance recall, evidence | Expandido forte |
| **reports** | 20 | 11.238 | ORPT vertical: PDF/Excel, listas operacionais fail-closed, metadata | Expandido (ORPT #159–#160) |
| **commercial_leads** | 19 | 8.052 | Ledger de leads comerciais, scoring, supplier registry | ✨ **NOVO** |
| **opportunity_intel** | 18 | 7.117 | Radar QW-01, ranking, scoring, CLI | Estável/refresh |
| **budget_audit** | 26 | 5.359 | Auditoria orçamentária (BDI, compositions, materiality, gates) | ✨ **NOVO** |
| **lib** | 23 | 5.196 | Universe, geocode, value semantics, normalizers | Expandido |
| **edital_case** | 14 | 4.871 | Pipeline de caso de edital (acquire→analyze→report) | ✨ **NOVO** |
| **fix** | 7 | 4.236 | Repair residual, evidence, entity resolve | Estável |
| **source_registry** | 12 | 3.015 | ESR: discovery, gap, promote, política canônica | Expandido |
| **workspace** | 6 | 3.017 | Fila operacional do consultor | Estável |
| **matching** | 4 | 2.700 | Entity matcher cascade + reconcile | Estável |
| **linkage** | 8 | 1.888 | Canonical entity linkage / dossier | ✨ **NOVO** |
| **schema** | 3 | 1.774 | official_acts helpers, diagnostics | Estável |
| **contract_intel** | 3 | 1.660 | Inteligência de contratos + CMI (competitors/values/concentration) | Expandido (CMI) |
| **ingestion** | 9 | 1.137 | Ingestão top-level | Estável |
| **clients** | 8 | 1.022 | Clientes HTTP compartilhados | Estável |
| **pipeline** | 2 | 876 | Backfill multi-fonte | Estável |
| **campaigns** | 4 | 771 | Campanhas (ex.: edital relevance) | ✨ **NOVO** |
| **buyer_intel** | 2 | 695 | Ranking de compradores | Estável |
| **integrations** | 2 | 673 | Integrações pontuais | ✨ **NOVO** |
| **diagnose** | 1 | 651 | Diagnóstico DOM-SC / portais | Estável |
| **national_intel** | 9 | 598 | Camada nacional de contratos (agencies, competitors, benchmarks) | ✨ **NOVO** |
| **extra_ledger** | 1 | 470 | Ledger operacional | Estável |
| **transparencia** | 1 | 406 | Portais de transparência | Estável |
| **collect** | 2 | 331 | Coletores auxiliares | ✨ **NOVO** |
| **quality** | 2 | 225 | Qualidade / checks | ✨ **NOVO** |
| **ocds_bridge** | 2 | 150 | Ponte OCDS | ✨ **NOVO** |
| **entity_identity** | 2 | 116 | Identidade canônica de entidades | ✨ **NOVO** |
| **data_contracts** | 2 | 115 | Contratos de dados | ✨ **NOVO** |
| **root_scripts** | ~50 | alto | Entry points CLI: intel_*, golden_path, health, B2G collectors | Expandido |

### 3.2 Infraestrutura e conhecimento

| Módulo | Conteúdo | Papel |
|--------|----------|-------|
| **config** | `settings.py`, `constants.py`, YAMLs de setores/SLA/aplicabilidade, CSV universo, client/commercial profiles | Configuração central |
| **db** | **69** migrations em `db/migrations/` (+ 8 supabase); latest **064_snapshot_write_guard** | Schema DataLake |
| **deploy** | **26** services / **25** timers em `deploy/systemd/`, install, provision, hardening, ansible | Operação VPS |
| **tests** | ~250 testes (unit / integration / smoke / chaos / adversarial / campaign) | Qualidade fail-closed |
| **docs** | ~529 MD em `docs/` (+ DoD, stories, campaigns, ADRs) | Operação e auditoria humana |
| **tools** | `tools/dod_controller.py` (~2,2K LOC) | Harness de convergência DoD |

---

## 4. Entry points principais

### 4.1 CLI / Makefile (canônicos)

| Comando / target | Função |
|------------------|--------|
| `make extra-weekly` / `scripts.ops.weekly_cycle` | Ciclo semanal |
| `make golden-path` | Smoke path local |
| `python3 -m scripts.workspace` | Workspace do consultor |
| `python3 -m scripts.crawl.monitor` | Orquestração de crawlers |
| `python3 -m scripts.opportunity_intel.cli` | Radar / opportunities |
| `python3 -m scripts.ops.apply_migrations` | Migrations |
| `python3 tools/dod_controller.py` | DoD harness |
| `make resilience-gate` / `resilient-local-cycle` | Gates de resiliência local |
| `make campaign-gate-*` / CONFENGE targets | Gates de campanha comercial |
| `make test-national-intel` / `test-linkage` / `test-client-ready` | Gates de verticais novas |

### 4.2 systemd (amostra)

`pncp-crawl-*`, `pncp-contracts`, `extra-weekly`, `extra-health-check`, `extra-db-backup`, `coverage-report*`, crawlers SC/DOM/transparência/CIGA, etc. — sob `deploy/systemd/`.

### 4.3 CI/CD

| Workflow | Papel |
|----------|-------|
| `.github/workflows/ci.yml` | Lint → typecheck → test + security; CONFENGE dual-head SHA truth |
| `.github/workflows/pr-reviewability.yml` | Política de reviewability de PRs |

---

## 5. Banco de dados (superfície)

- **Migrations `db/migrations/`:** 045–064 (novas desde última extração): national intel layers, linkage, commercial leads ledger, supplier registry, snapshot write guard, dual capability coverage views, etc.
- **Supabase:** 8 migrations legadas em `supabase/migrations/`
- **Docker local:** `docker-compose.local.yml` + `docker-compose.yml` — `pgvector/pgvector:pg16` (test-db :5433, volume `pgdata`; W006 unificado)

---

## 6. Testes

| Aspecto | Valor 🟢 |
|---------|----------|
| Framework | pytest (+ hypothesis para adversarial/budget) |
| Arquivos de teste | ~250 |
| Categorias | unit, integration, smoke, chaos, adversarial, campaign gates |
| Políticas | skip policy, generated-artifacts, PR reviewability |

---

## 7. Delta material desde 2026-07-17 (auditoria)

| Tema | Evidência (commits / módulos) |
|------|--------------------------------|
| **ORPT / reports** | #159 fail-closed lists + metadata; #160 vertical PDF/Excel |
| **CMI** | #151–#158 competitors, values, concentration; 47 itens ACCEPTED; evidence rebind |
| **CONFENGE** | Pipeline comercial + freeze/gates fail-closed massivos |
| **Coverage** | Edital relevance recall foundation; dual capability views |
| **Ops explosion** | CONFENGE, CMI proofs, campaign gates, hygiene, weekly |
| **Novas verticais** | `commercial_leads`, `budget_audit`, `edital_case`, `national_intel`, `linkage`, `campaigns` |
| **Schema** | mig 055–064 |
| **DoD harness** | `tools/dod_controller.py` |

---

## 8. Integrações externas (detectadas)

| Integração | Tipo | Notas |
|------------|------|-------|
| PNCP | API HTTP | Crawlers + contratos |
| Portais SC / transparência / CIGA / DOM / TCE | HTTP / HTML | Multi-fonte |
| OpenAI | API | Classificação / intel (gpt-nano lineage) |
| PostgreSQL | DB | Core |
| Docker / PostGIS | Local stack | test-db |
| GitHub Actions | CI | Fail-closed |
| Prometheus client | Metrics | Opcional |

---

## 9. Organização sugerida das specs

| Campo | Valor |
|-------|-------|
| **granularity** | `module` |
| **rationale** | Pastas top-level em `scripts/<domínio>/` com papéis de negócio distintos; re-extração mantém organização por módulo já persistida. |
| **signals** | `scripts/crawl/`, `scripts/ops/`, `scripts/coverage/`, `scripts/commercial_leads/`, `scripts/national_intel/`, etc. |

---

## 10. Lacunas de inventário (Scout)

| ID | Descrição | Confiança |
|----|-----------|-----------|
| INV-01 | LOC de `root_scripts` top-level parece inflado por arquivos grandes/gerados — Archaeologist deve revalidar | 🟡 |
| INV-02 | Worktrees `.worktrees/*` no filesystem não entram no inventário canônico (git tracked) | 🟢 |
| INV-03 | Runtime VPS e dumps live não inspecionados nesta sessão | 🔴 |

---

*Gerado pelo Scout Reversa — 2026-07-27 | HEAD `ffbb9608`*
