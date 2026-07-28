# Plano de Exploração — extra consultoria

> Reexecução **completa e profunda** dos documentos de auditoria iniciada em **2026-07-27/28**  
> Motivo: ~445 commits desde 2026-07-17 (`d3e82ba` → `ffbb9608`) — CMI, CONFENGE, ORPT/reports, coverage recall, commercial_leads, budget_audit, edital_case, national_intel, linkage, ops explosion, mig 055–064  
> HEAD: `ffbb9608` | `doc_level`: **completo** | Organização: por módulo (persistida)  
> Marque cada tarefa com ✅ quando concluída.

---

## Fase 1: Reconhecimento 🔍

- [x] **Scout** — Mapeamento de estrutura de pastas e tecnologias ✅ 2026-07-28
- [x] **Scout** — Análise de dependências e gerenciadores de pacotes ✅ 2026-07-28
- [x] **Scout** — Identificação de entry points, CI/CD e configurações ✅ 2026-07-28

## Decisão de organização das specs 🗂️

> Organização mantida: **por módulo** (persistido em `.reversa/config.toml`).  
> `doc_level` anterior: **completo** — aguardando confirmação do usuário nesta re-extração.

## Fase 2: Escavação 🏗️

> Módulos identificados pelo Scout em 2026-07-28 (**38 unidades**). Prioridade de auditoria marcada com 🔴.

- [x] **Archaeologist** — Análise do módulo `ops` 🔴 (92 .py, ~39K LOC — CONFENGE/CMI/gates)
- [x] **Archaeologist** — Análise do módulo `coverage` 🔴 (26 .py, ~18K LOC — recall/dual capability)
- [x] **Archaeologist** — Análise do módulo `reports` 🔴 (20 .py, ~11K LOC — ORPT)
- [x] **Archaeologist** — Análise do módulo `commercial_leads` ✨ NOVO 🔴
- [x] **Archaeologist** — Análise do módulo `budget_audit` ✨ NOVO 🔴
- [x] **Archaeologist** — Análise do módulo `edital_case` ✨ NOVO 🔴
- [x] **Archaeologist** — Análise do módulo `national_intel` ✨ NOVO 🔴
- [x] **Archaeologist** — Análise do módulo `linkage` ✨ NOVO 🔴
- [x] **Archaeologist** — Análise do módulo `crawl` (108 .py, ~43K LOC)
- [x] **Archaeologist** — Análise do módulo `contract_intel` (CMI)
- [x] **Archaeologist** — Análise do módulo `source_registry`
- [x] **Archaeologist** — Análise do módulo `workspace`
- [x] **Archaeologist** — Análise do módulo `opportunity_intel`
- [x] **Archaeologist** — Análise do módulo `matching`
- [x] **Archaeologist** — Análise do módulo `lib`
- [x] **Archaeologist** — Análise do módulo `schema`
- [x] **Archaeologist** — Análise do módulo `campaigns` ✨ NOVO
- [x] **Archaeologist** — Análise do módulo `fix`
- [x] **Archaeologist** — Análise do módulo `pipeline`
- [x] **Archaeologist** — Análise do módulo `clients` / `ingestion` / `integrations`
- [x] **Archaeologist** — Análise do módulo `buyer_intel` / `extra_ledger` / `transparencia` / `diagnose`
- [x] **Archaeologist** — Análise de módulos satélite (`collect`, `quality`, `ocds_bridge`, `entity_identity`, `data_contracts`)
- [x] **Archaeologist** — Análise do módulo `config` / `db` (mig 055–064) / `deploy` / `root_scripts` / `tests` / `docs` / `tools`

> **Archaeologist concluído 2026-07-28.** 38 módulos; code-analysis, data-dictionary, 14 flowcharts, modules.json.

## Fase 3: Interpretação 🧠

- [x] **Detetive** — Arqueologia Git (~445 commits desde última execução)
- [x] **Detetive** — Regras de negócio (CMI, CONFENGE, ORPT, commercial leads, budget audit, national intel, linkage)
- [x] **Detetive** — Máquinas de estado e ADRs retroativos novos
- [x] **Arquiteto** — C4 + ERD + Spec Impact Matrix atualizados

## Fase 4: Geração 📝

- [x] **Redator** — Specs SDD por módulo (novos + refresh dos expandidos)
- [x] **Redator** — Code/Spec Matrix atualizada
- [x] **Redator** — Contracts para CLIs/gates de campanha

## Fase 5: Revisão ✅ (documentos de auditoria)

- [x] **Revisor** — Revisão cruzada de specs
- [x] **Revisor** — Atualizar `confidence-report.md`, `gaps.md`, `questions.md`
- [x] **Regression check** — step-04 vs `_reversa_forward/001-modulos-alta-confianca/regression-watch.md`

---

## Agentes Independentes

- [ ] **Visor** — Análise de interface via screenshots
- [ ] **Data Master** — Análise completa do banco de dados
- [ ] **Design System** — Extração de tokens de design
- [ ] **Tracer** — Análise dinâmica (requer sistema acessível)

---

## Próximo passo

**Aguardando decisão de `doc_level` do usuário** → depois Archaeologist (prioridade: ops, coverage, reports, novos módulos comerciais).


---

## Re-extração auditoria 2026-07-28 CONCLUÍDA

Scout → Archaeologist → Detective → Architect → Writer (matrix) → Reviewer → step-04 regression.
Confiança **84%**. Watch: 1 vermelho (**W006** docker-compose.local test-db).
doc_level: **completo** | HEAD `ffbb9608`.
