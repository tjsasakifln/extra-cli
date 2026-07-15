# Baseline Verdadeiro — HEAD em 2026-07-15

**Repositorio:** /mnt/d/extra consultoria
**HEAD:** `7616950` (chore: finalizar state GP-01 para publicacao)
**Branch:** `epic-coverage-max-200km`
**origin/main:** `7616950` (sincronizado, 0 ahead/0 behind)
**Working tree:** 62 arquivos modificados (17 Python, 16 Markdown, 29 outros)
**Data da auditoria:** 2026-07-15

---

## 1. State Files (Resumo Tabular)

13 state files em `.aiox/state/stories/` (excluindo schema.json):

| story_id | Status | Risk | QA | PO_Closed | Pub_Auth | Reviewed_Commit | Lint | Tests |
|----------|--------|------|----|-----------|----------|-----------------|------|-------|
| qw-01-radar-auditavel | Done | HIGH-RISK | CONCERNS | true | **true** | **null** | PASS | PASS |
| story-1.1-fix-critical-security | Done | HIGH-RISK | CONCERNS | true | false | d2ff075 | **FAIL** | PASS |
| story-1.2-unify-schema | Done | HIGH-RISK | CONCERNS | true | false | d2ff075 | **FAIL** | PASS |
| story-1.3-universe-authority | Done | STANDARD | CONCERNS | true | false | **null** | **FAIL** | **FAIL** |
| story-1.4-reconcile-open-tenders | Done | STANDARD | CONCERNS | true | false | **null** | **PENDING** | **PENDING** |
| story-1.5-coverage-model | Done | STANDARD | PASS | true | true | d2ff075 | PASS | PASS |
| B2G-FIX-01 | Done | STANDARD | PASS | true | true | d45728d | PASS | PASS |
| B2G-FIX-02 | Done | STANDARD | PASS | true | true | d45728d | PASS | PASS |
| B2G-FIX-03 | Done | STANDARD | PASS | true | true | d45728d | PASS | PASS |
| B2G-FIX-04 | Done | HIGH-RISK | PASS | true | true | d9674e2 | PASS | PASS |
| B2G-FULL-SPECTRUM-W0 | Done | HIGH-RISK | PASS | true | true | 48bfb87 | PASS | PASS |
| GP-01 | Done | HIGH-RISK | PASS | true | true | fbc4cc1 | PASS | PASS |
| MAX-W1-01 | InReview | HIGH-RISK | PASS | false | false | d9674e2 | PASS | PASS |
| b2g-audit-consolidation | Done | FAST | WAIVED | true | true | 02b8ac8 | NA | NA |

**Nenhum reviewed_commit corresponde ao HEAD `7616950`.** O commit mais recente entre os states e o HEAD esta em GP-01 (fbc4cc1) — ha 1 commit de diferenca.

---

## 2. Stories vs States (Matriz de Consistencia)

### Stories em `docs/stories/` com state correspondente: 10/14

| Arquivo Story | State | Consistente? |
|---------------|-------|-------------|
| qw-01-radar-auditavel.md | qw-01-radar-auditavel.json | **MD Status=InReview, State=Done** |
| story-1.1-fix-critical-security.md | story-1.1-fix-critical-security.json | OK |
| story-1.2-unify-schema.md | story-1.2-unify-schema.json | OK |
| story-1.2-canonical-views-contract.md | (nenhum) | **ORFA: story sem state** |
| story-1.3-universe-authority.md | story-1.3-universe-authority.json | OK |
| story-1.4-reconcile-open-tenders.md | story-1.4-reconcile-open-tenders.json | OK |
| story-1.5-coverage-model.md | story-1.5-coverage-model.json | OK |
| story-B2G-FIX-01-imports-pncp-url.md (em epic-master-b2g/) | B2G-FIX-01 | OK |
| story-B2G-FIX-02-code-quality.md (em epic-master-b2g/) | B2G-FIX-02 | OK |
| story-B2G-FIX-03-canonical-universe.md (em epic-master-b2g/) | B2G-FIX-03 | OK |
| story-B2G-FIX-04-schema-alignment.md (em epic-master-b2g/) | B2G-FIX-04 | OK |

### Orfaos (story sem state)

| Arquivo | Tipo | Observacao |
|---------|------|-----------|
| `docs/stories/story-1.2-canonical-views-contract.md` | Story MD | Sem state file. Provavelmente substituida por story-1.2-unify-schema |
| `docs/stories/epic-technical-debt.md` | Epic | Documento narrativo, nao story individual |
| `docs/stories/td-3.2-pncp-resilience.md` | Story MD | **Story sem state** (status=Done no MD, mas sem governanca AIOX) |
| `docs/stories/transition-plan-coverage-1.5.md` | Plano | Plano de transicao, nao story |

### State sem story .md em lugar nenhum

| State | story_id | Impacto |
|-------|----------|---------|
| story-B2G-FULL-SPECTRUM-W0.json | B2G-FULL-SPECTRUM-W0 | Sem story markdown para revisao humana |
| story-GP-01-golden-path.json | GP-01 | **Sem story markdown** — estado existe, mas documento humano nao |
| story-MAX-W1-01-golden-path.json | MAX-W1-01 | **Sem story markdown** — estado existe, mas documento humano nao |
| story-b2g-audit-consolidation.json | b2g-audit-consolidation | Sem story markdown (aceitavel: era task FAST de documentacao) |

**Total:** 4 states sem story MD. Destes, GP-01 e MAX-W1-01 sao stories de implementacao sem documento humano.

---

## 3. Epic Mestre (Status Real)

### EPIC-MASTER-B2G-READINESS v3.0

**Local:** `docs/stories/epics/EPIC-MASTER-B2G-READINESS.md`
**Status declarado:** Active
**Data:** 2026-07-14

#### Fase 0 — Critical Fixes (todas as 4 stories Done, gate READY_TO_PROVISION)

| ID | Status Epic | Status Real | Diverge? |
|----|------------|-------------|----------|
| B2G-FIX-01 | Done | Done (state) | Nao |
| B2G-FIX-02 | Done | Done (state) | Nao |
| B2G-FIX-03 | Done | Done (state) | Nao |
| B2G-FIX-04 | Done | Done (state) | Nao |

**Gate READY_TO_PROVISION:** Nao atingido. Faltam:
- [ ] Credenciais Hetzner obtidas
- [ ] push/publicacao autorizada

#### Fase 1 — Provisioning (todas ready)

| ID | Status Epic | Status Real | Diverge? |
|----|------------|-------------|----------|
| B2G-INFRA-01 | ready | Nao existe state | Nao implementado |
| B2G-INFRA-02 | ready | Nao existe state | Nao implementado |
| B2G-INFRA-03 | ready | Nao existe state | Nao implementado |
| B2G-INFRA-04 | ready | Nao existe state | Nao implementado |

#### Demais fases (2-7): status epic coincide com implementacao (todas draft/ready)

### EPIC-B2G-MAX-EVOLUTION

**Local:** `docs/stories/epics/epic-b2g-max-evolution/EPIC-B2G-MAX-EVOLUTION.md`
**Status:** Active
MAX-W1-01 golden path: state InReview (epic declara "ready"? — divergencia menor)

### EPIC-TD-001 Resolution

Epic declara Complete (5/5 stories Done). Stories 1.1-1.5 todas Done nos states, mas:
- 3 tem lint FAIL
- 1 tem gates PENDING
- 1 nao tem story no local esperado (story-1.2-canonical-views-contract.md vs story-1.2-unify-schema.md)

---

## 4. Divergencias CODE vs DOCS

### 4.1 Arquitetura documentada vs realidade

| Documento | Afirma | Realidade |
|-----------|--------|-----------|
| architecture.md | "DataLake PostgreSQL centralizado rodando em Hetzner VPS" | **VPS nunca provisionada.** PostgreSQL roda apenas local (WSL). |
| system-architecture.md | "12 fontes de dados cadastradas" | 14 crawlers implementados, 0 em operacao continua. 3 testados em escala. |
| system-architecture.md | "44 services/timers systemd" | 20 timer pairs existem, 3 padroes de nomenclatura, nunca ativados. |
| system-architecture.md | "~117.099 linhas Python + SQL" | Numero desatualizado (era pre-refatoracao). Atualmente 185 .py files. |
| EPIC-MASTER v3.0 | Fase 0 esta liberando gate | Gate nao atingido (faltam credenciais Hetzner). |

### 4.2 Schema-v3 vs realidade

`schema-v3.md` descreve 3 tracks de migracao (v1, v2, v3). A realidade pos-B2G-FIX-04:
- 47 migrations em `db/migrations/` (nao 41)
- Diretorio `supabase/migrations/` legado ainda existe (ADR-003 revogado)
- diagnostics.py criado mas **nunca executado contra banco real**

### 4.3 PRD vs implementacao

PRD v2.0 define metricas que dependem de dados que APIs publicas nao expoem (preco praticado, win rate). Auditoria de 14/07 ja documentava isso como risco. Nada mudou.

---

## 5. O Que Mudou Desde 14/07

### Auditorias de 14/07

| Arquivo | Data | Resumo |
|---------|------|--------|
| audit-b2g-readiness-2026-07-14.md | 14/07 09:06 | Auditoria tecnica completa: 14 crawlers, schema, infra. Recomendou consolidacao em ~35 stories. |
| audit-delta-b2g-2026-07-14.md | 14/07 12:07 | Verificacao cruzada dos achados da auditoria original. Reclassificou PNCP-URL como PARTIALLY_RESOLVED. |
| audit-full-spectrum-b2g-2026-07-14.md | 14/07 21:33 | Auditoria de prontidao comercial. 12 capacidades: 1 READY, 3 PARTIAL, 8 NOT_READY. |
| audit-max-evolution-2026-07-14.md | 14/07 20:32 | Baseline Max Evolution: PostgreSQL OFFLINE, 0% CLI funcional, 0 crawlers em producao. |
| migration-forensics-2026-07-14.md | 14/07 19:25 | 16 achados (7 CRITICAL) nas migrations. Base para B2G-FIX-04. |

### O que foi implementado desde 14/07

Com base no git log entre audit-b2g-readiness e HEAD:

| Commit | O que fez |
|--------|-----------|
| fbc4cc1 | Golden Path Operacional: DB persistente + crawl PNCP + briefing funcional (GP-01) |
| 5b0dd79 | fix: sync reviewed_commit to HEAD |
| 48bfb87 | push gate: gitignore runtime files + state file for Full-Spectrum W0 |
| 7616950 | chore: finalizar state GP-01 para publicacao |

**Principais avancos concretos:** GP-01 estabeleceu DB persistente com Docker, 298 oportunidades PNCP importadas, briefing funcional com 150 oportunidades AEC, 83 orgaos, R$179.5M.

**O que NAO mudou:** Credenciais Hetzner (gate bloqueado), VPS provisionada, crawlers em producao, backup testado. As auditorias de 14/07 continuam validas — as recomendacoes de acao seguem pendentes.

---

## 6. Violacoes de Protocolo

### 6.1 `publication_authorized=true` com `reviewed_commit=null`

| Story | Problema |
|-------|----------|
| **qw-01-radar-auditavel** | Pub autorizada sem commit revisado. State diz `reviewed_commit: null`. **Protocolo exige que publication_authorized so seja true apos reviewed_commit apontar para HEAD.** |

### 6.2 Status=Done com gates PENDING

| Story | Problema |
|-------|----------|
| **story-1.4-reconcile-open-tenders** | Status Done mas gates = { lint: PENDING, typecheck: PENDING, tests: PENDING }. **Story fechada sem gates executados.** |

### 6.3 Status=Done com lint=FAIL

| Story | Problema |
|-------|----------|
| story-1.1-fix-critical-security | lint: FAIL |
| story-1.2-unify-schema | lint: FAIL |
| story-1.3-universe-authority | lint: FAIL, tests: FAIL |

Todas tem qa_verdict=CONCERNS e publication_authorized=false — o que mitiga o risco (nao serao publicadas), mas o padrao de "Done com gates vermelhos" e preocupante.

### 6.4 Story MD vs State divergentes

| Story | MD Status | State Status |
|-------|-----------|-------------|
| qw-01-radar-auditavel.md | InReview | Done |

### 6.5 Stories sem documento humano

GP-01 e MAX-W1-01 tem state files completos com evidencias, mas **nao existe story markdown** (`docs/stories/story-GP-01-golden-path.md` ou similar). O protocolo AIOX exige story markdown como documento humano. O state file e a fonte operacional, mas o MD e necessario para revisao humana.

### 6.6 Branch ativa diferente de main

Branch atual `epic-coverage-max-200km` esta sincronizada com origin/main (0 ahead/0 behind), mas o working tree tem 62 arquivos modificados. **Nao e possivel publicar com working tree sujo.**

---

## 7. Acoes Corretivas Necessarias

### Imediatas (bloqueadores)

| # | Acao | Responsavel | Story |
|---|------|------------|-------|
| 1 | Corrigir qw-01 state: ou preencher reviewed_commit ou revogar publication_authorized | @po/@devops | qw-01 |
| 2 | Executar gates para story-1.4 ou reverter status para InProgress | @qa | story-1.4 |
| 3 | Criar story MD para GP-01 e MAX-W1-01 | @sm | -- |
| 4 | Sincronizar qw-01 MD status (InReview) com state (Done) | @po | qw-01 |
| 5 | Limpar working tree ou commitar mudancas pendentes | @dev | -- |

### Recomendadas

| # | Acao | Justificativa |
|---|------|--------------|
| 6 | Resolver lint FAIL nas stories 1.1, 1.2, 1.3 | Impedem publicacao |
| 7 | Obter credenciais Hetzner para destravar gate READY_TO_PROVISION | Gate mestre do EPIC-MASTER |
| 8 | Remover ou arquivar `docs/stories/story-1.2-canonical-views-contract.md` | Substituido por story-1.2-unify-schema |
| 9 | Arquivar `docs/stories/td-3.2-pncp-resilience.md` sem state | Story orfa |
| 10 | Remover referencia a "Hetzner VPS" na arquitetura docs enquanto VPS nao existir | Documentos enganosos |

---

## 8. Baseline de Arquivos

| Tipo | Contagem | Observacao |
|------|----------|-----------|
| `scripts/*.py` | 185 | Codigo de producao |
| `tests/*.py` | 72 | Testes |
| Proporcao testes/codigo | **28,0%** | (72/257 do total .py) |
| `docs/*.md` | 199 | Documentacao |
| `docs/stories/*.md` | 11 | Stories (mais ~60 em subdiretorios de epics) |
| State files | 13 | Em `.aiox/state/stories/` |
| Epics | 8 | Em `docs/stories/epics/` |
| ADRs | 3 | `adr-002`, `adr-003`, `adr-006` |
| Auditorias | 5 | Em `docs/audits/` |
| Arquivos `.py` totais (projeto) | 266 | Excluindo `.aiox*`, `.claude*`, `_reversa*`, `node_modules` |

### ADRs Existentes

| ADR | Status | Relevancia Atual |
|-----|--------|-----------------|
| ADR-002: Preco Praticado | Proposto | Nao implementado. Metricas bloqueadas por dados que APIs nao expoem. |
| ADR-003: Supabase Self-Hosted | **Revogado** (decisao: PostgreSQL bare metal) | Documento ainda existe, decisoes do EPIC-MASTER v3.0 o revogaram. |
| ADR-006: Fresh Install Scope | **ACCEPTED** | Implementation: diagnostics.py + 46 migrations verificadas. |

### ADRs Ausentes

Nao ha ADR-001, ADR-004, ADR-005. `contract-intelligence-truth-v1.md` e `qw-01-canonical-opportunity-pipeline.md` funcionam como ADRs informais mas nao seguem a numeracao.

---

## Resumo Executivo

**O repositorio esta em um estado de transicao.** As auditorias de 14/07 permanecem validas — as correcoes da Fase 0 (B2G-FIX-01 a -04) foram implementadas e verificadas com QA PASS, mas:

1. **Gate READY_TO_PROVISION nao foi atingido** — faltam credenciais Hetzner.
2. **4 stories tem state files sem story MD** — GP-01 e MAX-W1-01 sao as mais criticas.
3. **1 violacao direta de protocolo** (qw-01: pub_auth sem reviewed_commit).
4. **1 violacao de gate** (story-1.4: Done com gates PENDING).
5. **Working tree sujo** com 62 arquivos modificados em `epic-coverage-max-200km`.
6. **13/13 states com reviewed_commit desatualizado** em relacao ao HEAD.
7. **28% de proporcao testes/codigo** — abaixo do desejavel.
8. **Documentacao de arquitetura desatualizada** — refere-se a Hetzner VPS que nunca foi provisionada.

O avanco real desde 14/07 foi o GP-01 (Golden Path Operacional com Docker + PNCP + briefing), que estabeleceu um baseline funcional local. O proximo passo logico e destravar o gate READY_TO_PROVISION (credenciais Hetzner) para iniciar a Fase 1 do EPIC-MASTER.

---

*Auditoria gerada em 2026-07-15 por Claude Code*
*Branch: epic-coverage-max-200km | HEAD: 7616950*
