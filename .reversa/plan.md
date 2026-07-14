# Plano de Exploração — extra consultoria

> Reexecução completa iniciada pelo Reversa em 2026-07-13
> Motivo: 30 novos commits (591 arquivos, +252K/-24K LOC) após última execução em 2026-07-11
> `doc_level`: completo | Organização: por módulo
> Marque cada tarefa com ✅ quando concluída.

---

## Fase 1: Reconhecimento 🔍

- [x] **Scout** — Mapeamento de estrutura de pastas e tecnologias ✅
- [x] **Scout** — Análise de dependências e gerenciadores de pacotes ✅
- [x] **Scout** — Identificação de entry points, CI/CD e configurações ✅

## Decisão de organização das specs 🗂️

> Organização mantida: **por módulo** (persistido em `.reversa/config.toml`).

## Fase 2: Escavação 🏗️

> Módulos identificados pelo Scout em 2026-07-13 (17 módulos).

- [ ] **Archaeologist** — Análise do módulo `crawl` (51 .py, ~65K LOC, 10+ crawlers, ingestion pipeline)
- [ ] **Archaeologist** — Análise do módulo `opportunity_intel` (16 .py, ~15K LOC, QW-01 Radar, ranking, scoring)
- [ ] **Archaeologist** — Análise do módulo `contract_intel` (3 .py, ~60K LOC, universo-alvo, CLI contratos)
- [ ] **Archaeologist** — Análise do módulo `lib` (15 .py, ~12K LOC, universe, geocode, name normalizer, victory profile)
- [ ] **Archaeologist** — Análise do módulo `matching` (3 .py, ~28K LOC, entity matcher cascade 3 níveis)
- [ ] **Archaeologist** — Análise do módulo `coverage` (4 .py, ~44K LOC, validate, calculator, measure expansion)
- [ ] **Archaeologist** — Análise do módulo `reports` (4 .py, ~64K LOC, PDF/Excel executivo, cobertura semanal)
- [ ] **Archaeologist** — Análise do módulo `fix` (7 .py, ~165K LOC, scrape residual, repair scripts)
- [ ] **Archaeologist** — Análise do módulo `pipeline` (2 .py, ~34K LOC, backfill multi-fonte)
- [ ] **Archaeologist** — Análise do módulo `diagnose` (1 .py, ~25K LOC, DOM-SC diagnostics)
- [ ] **Archaeologist** — Análise do módulo `transparencia` (1 .py, ~14K LOC, detecção automática de portais)
- [ ] **Archaeologist** — Análise do módulo `config` (config/, 3 .py + YAMLs, settings, 13 setores B2G)
- [ ] **Archaeologist** — Análise do módulo `db` (33 + 8 migrations, schema completo, seed)
- [ ] **Archaeologist** — Análise do módulo `deploy` (20 systemd timers, provisionamento, hardening)
- [ ] **Archaeologist** — Análise do módulo `root_scripts` (~40 scripts CLI top-level, entry points principais)
- [ ] **Archaeologist** — Análise do módulo `tests` (64 testes, fixtures, smoke)
- [ ] **Archaeologist** — Análise do módulo `docs` (590 arquivos, 7 epics, ADRs, PRDs, runbooks)

## Fase 3: Interpretação 🧠

- [ ] **Detetive** — Arqueologia Git (30 commits desde última execução) ✅
- [ ] **Detetive** — Regras de negócio implícitas (R18-R26: deságio, competitive intel, QW-01, gates, evidence ledger) ✅
- [ ] **Detetive** — Máquinas de estado (MS7-MS10: evidence_state, QW-01 Radar, Readiness Gate, Freshness Gate) ✅
- [ ] **Detetive** — ADRs retroativos (012-016: QW-01, Coverage Truth, Fail-Closed CI, Semantic Values, Competitive Intel) ✅
- [ ] **Arquiteto** — Diagramas C4 (Contexto +2 sistemas, Containers +4, Componentes +3 diagramas) ✅
- [ ] **Arquiteto** — ERD completo (+2 tabelas: coverage_evidence, opportunity_intel; +1 enum: evidence_state) ✅
- [ ] **Arquiteto** — Spec Impact Matrix (+8 módulos, +9 regras, +5 ADRs, +1 cross-cutting concern) ✅

## Fase 4: Geração 📝

- [x] **Redator** — Specs SDD por componente (17 módulos) ✅
- [x] **Redator** — Code/Spec Matrix (147 entradas, 92% cobertura) ✅

> **Concluído em 2026-07-13.** 32 arquivos gerados: 9 novos módulos + 2 parciais completados + 2 contracts.md + code-spec-matrix atualizada.
> **Fontes brownfield integradas:** plano-mestre (9 EPICs P0, DoD §22), epic-technical-debt (5 stories), 35 lacunas documentadas.

## Fase 5: Revisão ✅

- [x] **Revisor** — Revisão cruzada de specs (5 agentes QA paralelos) ✅
- [x] **Revisor** — Perguntas para validação humana (5 questões, todas respondidas) ✅
- [x] **Revisor** — Relatório de confiança final (78% geral, 17 módulos) ✅

> **Concluído em 2026-07-13.** 24 lacunas consolidadas (8 críticas, 7 altas, 5 médias, 4 baixas).
> 4 correções in-place: reports/design.md expandido, docs/tasks.md expandido, diagnose e transparencia aprofundados.
> 4 sub-specs lib geradas. Code-spec-matrix expandida para 263 entradas (100%).
> Intel/ migrado para root_scripts/. Confiança: 78% 🟡 (escopo 2× maior que extração anterior).

---

## Agentes Independentes

- [ ] **Visor** — Análise de interface via screenshots
- [ ] **Data Master** — Análise completa do banco de dados
- [ ] **Design System** — Extração de tokens de design
- [ ] **Tracer** — Análise dinâmica (requer sistema acessível)

---

## Próximo passo

Fase de Geração — Redator produz specs SDD por módulo. Em seguida, Revisor faz revisão cruzada.

Após o Time de Descoberta concluir, disparar `/reversa-migrate` ou `/reversa-reconstructor`.
