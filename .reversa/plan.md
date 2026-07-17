# Plano de Exploração — extra consultoria

> Reexecução completa e profunda iniciada em **2026-07-17**  
> Motivo: 131 commits desde 2026-07-13 (754 arquivos, +160K/−11K LOC) — plataforma B2G operacional, source_registry, workspace, resilience, official_acts, DoD §40–§44  
> HEAD: `d3e82ba` | `doc_level`: completo | Organização: por módulo  
> Marque cada tarefa com ✅ quando concluída.

---

## Fase 1: Reconhecimento 🔍

- [x] **Scout** — Mapeamento de estrutura de pastas e tecnologias ✅ 2026-07-17
- [x] **Scout** — Análise de dependências e gerenciadores de pacotes ✅ 2026-07-17
- [x] **Scout** — Identificação de entry points, CI/CD e configurações ✅ 2026-07-17

## Decisão de organização das specs 🗂️

> Organização mantida: **por módulo** (persistido em `.reversa/config.toml`).  
> `doc_level` mantido: **completo** (escolha prévia do projeto).

## Fase 2: Escavação 🏗️

> Módulos identificados pelo Scout em 2026-07-17 (**25 módulos**).

- [x] **Archaeologist** — Análise do módulo `crawl` (102 .py, ~40K LOC, resilience, official_acts, multi-fonte SC)
- [x] **Archaeologist** — Análise do módulo `source_registry` (12 .py, ~2.6K LOC) ✨ NOVO
- [x] **Archaeologist** — Análise do módulo `workspace` (6 .py, ~2.7K LOC) ✨ NOVO
- [x] **Archaeologist** — Análise do módulo `coverage` (16 .py, ~8.4K LOC, coverage contract multi-source)
- [x] **Archaeologist** — Análise do módulo `opportunity_intel` (18 .py, ~6.9K LOC)
- [x] **Archaeologist** — Análise do módulo `reports` (12 .py, ~7.9K LOC)
- [x] **Archaeologist** — Análise do módulo `lib` (19 .py, ~4.1K LOC)
- [x] **Archaeologist** — Análise do módulo `matching` (4 .py, ~2.7K LOC)
- [x] **Archaeologist** — Análise do módulo `schema` (3 .py, ~1.8K LOC) ✨ NOVO
- [x] **Archaeologist** — Análise do módulo `ops` (6 .py, ~0.5K LOC) ✨ NOVO
- [x] **Archaeologist** — Análise do módulo `buyer_intel` (2 .py, ~0.7K LOC) ✨ NOVO
- [x] **Archaeologist** — Análise do módulo `extra_ledger` (1 .py, ~0.5K LOC) ✨ NOVO
- [x] **Archaeologist** — Análise do módulo `contract_intel` (3 .py, ~1.7K LOC)
- [x] **Archaeologist** — Análise do módulo `fix` (7 .py, ~4.2K LOC)
- [x] **Archaeologist** — Análise do módulo `pipeline` (2 .py, ~0.9K LOC)
- [x] **Archaeologist** — Análise do módulo `clients` (8 .py, ~1.0K LOC)
- [x] **Archaeologist** — Análise do módulo `ingestion` (9 .py, ~1.1K LOC)
- [x] **Archaeologist** — Análise do módulo `diagnose` (1 .py, ~0.7K LOC)
- [x] **Archaeologist** — Análise do módulo `transparencia` (1 .py, ~0.4K LOC)
- [x] **Archaeologist** — Análise do módulo `config` (config/ + YAMLs + CSV universo)
- [x] **Archaeologist** — Análise do módulo `db` (59 migrations + supabase)
- [x] **Archaeologist** — Análise do módulo `deploy` (25 services / 24 timers)
- [x] **Archaeologist** — Análise do módulo `root_scripts` (~50 scripts CLI top-level / gates)
- [x] **Archaeologist** — Análise do módulo `tests` (126 testes, chaos, unit coverage/workspace/registry)
- [x] **Archaeologist** — Análise do módulo `docs` (ops sessions, audits, baseline, stories, ADRs)

> **Archaeologist concluído 2026-07-17.** 25 módulos; code-analysis, data-dictionary, 9 flowcharts, modules.json.

## Fase 3: Interpretação 🧠

- [x] **Detetive** — Arqueologia Git (131 commits desde última execução)
- [x] **Detetive** — Regras de negócio implícitas (coverage contract, fail-closed resilience, source registry, official_acts, honest commercial coverage)
- [x] **Detetive** — Máquinas de estado (evidence ledger, resilience states, coverage commercial status, workspace queue)
- [x] **Detetive** — ADRs retroativos (novos desde 012–016 + decisões B2G/ops 2026-07-17)
- [x] **Arquiteto** — Diagramas C4 (contexto, containers, componentes atualizados)
- [x] **Arquiteto** — ERD completo (official_acts, source_registry, resilience, watermarks/DLQ)
- [x] **Arquiteto** — Spec Impact Matrix (25 módulos)

## Fase 4: Geração 📝

- [x] **Redator** — Specs SDD por componente (25 módulos)
- [x] **Redator** — Code/Spec Matrix atualizada
- [x] **Redator** — Contracts para módulos de interface CLI/gates

## Fase 5: Revisão ✅

- [x] **Revisor** — Revisão cruzada de specs
- [x] **Revisor** — Perguntas para validação humana
- [x] **Revisor** — Relatório de confiança final
- [x] **Regression check** — step-04 vs `_reversa_forward/001-modulos-alta-confianca/regression-watch.md`

---

## Agentes Independentes

- [ ] **Visor** — Análise de interface via screenshots
- [ ] **Data Master** — Análise completa do banco de dados
- [ ] **Design System** — Extração de tokens de design
- [ ] **Tracer** — Análise dinâmica (requer sistema acessível)

---

## Próximo passo

**Archaeologist** — escavação profunda módulo a módulo, priorizando delta: crawl/resilience, source_registry, workspace, coverage, schema, ops.


---

## Re-extração 2026-07-17 CONCLUÍDA

Scout → Archaeologist → Detective → Architect → Writer → Reviewer → step-04 regression.
Confiança 82%. Watch: 1 vermelho (W006 docker-compose.local).
