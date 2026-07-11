# Technical Debt Assessment -- FINAL

**Projeto:** Extra Consultoria (CLI crawling de licitacoes)
**Data:** 2026-07-11
**Versao:** FINAL v1.0
**Status:** Validado por especialistas

---

## Executive Summary

A Extra Consultoria e um sistema CLI de inteligencia em licitacoes publicas com aproximadamente 64.000 linhas de codigo Python + SQL, operando um DataLake PostgreSQL centralizado de 4.1 GB em Hetzner VPS. O sistema faz crawl multi-source de 2.085 orgaos publicos de Santa Catarina em 5+ fontes de dados abertos, combinando ingestao continua (systemd timers) com pipelines de inteligencia sob demanda.

O assessment final, apos revisao de @data-engineer (Dara) e @qa (Quinn), identificou **38 debitos tecnicos** (vs 30 no DRAFT original), sendo **4 CRITICAL**, **9 HIGH**, **18 MEDIUM** e **7 LOW**. O esforco total estimado para resolucao completa e de **140 a 170 horas**, com custo estimado entre **R$ 21.000 e R$ 25.500** (a R$150/h).

### Principais descobertas

1. **Ausencia total de backup (CRITICAL):** 4.1 GB de dados sem nenhum mecanismo de backup -- risco de perda total do DataLake de 2+ anos de crawling. Descoberto pelo @data-engineer, confirmado pelo @qa.
2. **Ausencia total de testes automatizados (CRITICAL):** 64K linhas de codigo com coverage zero. Qualquer refatoracao e um risco elevado de regression silenciosa.
3. **Migrations totalmente divergentes do schema real (CRITICAL):** Nao e possivel recriar o banco a partir das migrations existentes. Nenhuma das 12 migrations corresponde ao schema real.
4. **Imports quebrados no BidsCrawler (CRITICAL):** O modulo bids_crawler.py referencia um package `ingestion/` que nao existe, podendo tornar o crawler PNCP inoperante.
5. **Senha de producao hardcoded em multiplos scripts (HIGH):** A senha do banco PostgreSQL (Hetzner VPS, porta 54399) esta em texto puro em varios scripts versionados no git.
6. **HNSW index inutilizado (HIGH):** Expressao matematica incorreta impede o uso do index de similaridade vetorial -- toda busca hibrida com embedding faz full scan.
7. **Ausencia de CI/CD pipeline (HIGH):** 64K linhas sem lint automatizado, type check ou testes em PR. Toda mudanca e aplicada manualmente via SSH.
8. **Duas implementacoes concorrentes de crawler PNCP (HIGH):** Sync adapter vs async BidsCrawler, comportamento divergente, uma delas potencialmente quebrada.

### Gate do QA: NEEDS WORK (7.5/10) -- RESOLVIDO

O QA Gate (Fase 7) classificou o DRAFT como NEEDS WORK com 7.5/10 devido a 5 gaps de escopo e 2 contradicoes entre documentos fonte. Todas as 5 lacunas foram enderecadas como novos debitos (TD-OPS-01, TD-OPS-02 unificado com TD-DB-15, TD-DOC-01, TD-OPS-03, TD-SEC-02). As 2 contradicoes foram resolvidas (SQL injection classificado como LOW; ORM reclassificado como INFORMATIVO). A estimativa foi ajustada de 105-125h para 140-170h.

---

## 1. Assessment Methodology

O assessment foi conduzido usando o workflow **Brownfield Discovery** (10 fases) do framework AIOX:

| Fase | Agente | Output | Status |
|------|--------|--------|--------|
| 1. System Architecture | @architect (Aria) | `docs/architecture/system-architecture.md` | COMPLETO |
| 2. Database & Audit | @data-engineer (Dara) | `supabase/docs/SCHEMA.md`, `supabase/docs/DB-AUDIT.md` | COMPLETO |
| 3. Frontend Spec | @ux-design-expert (Uma) | N/A (projeto CLI puro) | SKIPPED |
| 4. Technical Debt DRAFT | @architect (Aria) | `docs/prd/technical-debt-DRAFT.md` | COMPLETO |
| 5. DB Specialist Review | @data-engineer (Dara) | `docs/prd/db-specialist-review.md` | COMPLETO |
| 6. UX Specialist Review | @ux-design-expert (Uma) | N/A (projeto CLI puro) | SKIPPED |
| 7. QA Gate | @qa (Quinn) | `docs/prd/qa-review.md` (7.5/10, NEEDS WORK) | RESOLVIDO |
| **8. Assessment Final** | **@architect (Aria)** | **`docs/prd/technical-debt-assessment.md`** | **ATUAL** |

### Fontes consultadas

- `docs/architecture/system-architecture.md` -- 606 linhas de analise arquitetural
- `supabase/docs/SCHEMA.md` -- Schema real documentado com ER textual
- `supabase/docs/DB-AUDIT.md` -- Auditoria completa de banco (schema, seguranca, performance)
- `docs/prd/technical-debt-DRAFT.md` -- DRAFT original com 30 debitos
- `docs/prd/db-specialist-review.md` -- Revisao do @data-engineer com 3 novos debitos
- `docs/prd/qa-review.md` -- Quality gate com 5 gaps e 2 contradicoes

---

## 2. Inventario Completo de Debitos

### 2.1 Sistema (validado por @architect e @qa)

| ID | Debito | Severidade | Arquivo/Local | Horas | Dependencias |
|----|--------|------------|---------------|-------|--------------|
| TD-SYS-001 | Imports quebrados para `ingestion/` package que nao existe | CRITICAL | `bids_crawler.py` | 4 | Nenhuma |
| TD-SYS-002 | DSN default duplicado (monitor.py vs settings.py) | MEDIUM | `monitor.py:48`, `settings.py:33` | 1 | Nenhuma |
| TD-SYS-003 | Ausencia de type hints em funcao de 341 linhas | HIGH | `monitor.py:142-341` (`_match_entities_cascade`) | 4 | Nenhuma |
| TD-SYS-004 | Estado global mutavel (cache IBGE module-level) -- AJUSTADO para HIGH | HIGH | `enricher.py:483-484` | 3 | Nenhuma |
| TD-SYS-005 | Subprocess sem controle de output | LOW | `intel_pipeline.py:168-176` | 1 | Nenhuma |
| TD-SYS-006 | ANSI color codes manuais com Rich disponivel | LOW | `intel_pipeline.py:65-72` | 1 | Nenhuma |
| TD-SYS-007 | `import json` inline no meio da funcao | LOW | `monitor.py:493` | 0.5 | Nenhuma |
| TD-SYS-008 | Constantes de config espalhadas vs settings.py | MEDIUM | `enricher.py` | 3 | Nenhuma |
| TD-SYS-009 | Ausencia de testes unitarios automatizados | CRITICAL | Todo o projeto | 16 | TD-SYS-011 (monitor.py dificil de testar) |
| TD-SYS-010 | `supabase_client` importado inline | MEDIUM | `enricher.py:102,209,322,580` | 2 | Nenhuma |
| TD-SYS-011 | Monitor.py com ~687 linhas, acopla orquestracao + entity matching + coverage | HIGH | `monitor.py` | 8 | TD-SYS-009 |
| TD-SYS-012 | Fallback silencioso para difflib sem alerta -- AJUSTADO para MEDIUM | MEDIUM | `monitor.py:216-221` | 0.5 | Nenhuma |
| TD-SYS-013 | Sem schema validation nos YAML de config | MEDIUM | `config/sectors_config.yaml` | 4 | Nenhuma |
| TD-SYS-014 | Sem renovacao automatica de API keys | MEDIUM | `settings.py` | 4 | Nenhuma |
| TD-SYS-015 | Sem healthcheck unificado do sistema | MEDIUM | N/A | 6 | Nenhuma |
| TD-SYS-016 | Duas implementacoes de crawler PNCP (sync adapter vs async BidsCrawler) | HIGH | `monitor.py` + `bids_crawler.py` | 8 | TD-SYS-001, TD-SYS-009 |

### 2.2 Database (validado por @data-engineer)

| ID | Debito | Severidade | Tabela/Objeto | Horas | Dependencias | Nota |
|----|--------|------------|---------------|-------|--------------|------|
| TD-DB-01 | Migrations totalmente divergentes do schema real | CRITICAL | Todas as tabelas | 8 | Nenhuma | Regenerar via pg_dump |
| TD-DB-02a | Migrations 009/011/012 nao aplicadas (entity_coverage + views) | HIGH | entity_coverage, v_coverage_summary, v_unmatched_bids, coverage_snapshots | 4 | TD-DB-01 | Desdobrado do TD-DB-02 original |
| TD-DB-02b | Migration 010 nao aplicada (match_logging) | LOW | match_method, match_score, match_confidence | 1 | TD-DB-01 | Verificar se colunas ja existem |
| TD-DB-03 | enriched_entities sem TTL enforcement | MEDIUM | enriched_entities | 3 | Nenhuma | 13.8K registros, risco baixo hoje |
| TD-DB-04 | upsert_pncp_supplier_contracts row-by-row | MEDIUM | pncp_supplier_contracts | 3 | Nenhuma | Funcao set-based ja existe |
| TD-DB-05 | Senha do DB hardcoded em multiplos scripts -- AJUSTADO para HIGH | HIGH | `config/settings.py` e varios scripts | 2 | Nenhuma | Ver decisao de arbitragem secao 4.1 |
| TD-DB-06 | GIST trigram index superdimensionado (294 MB) | MEDIUM | pncp_raw_bids (objeto_compra) | 2 | Nenhuma | Relacao index/dados 1.1x |
| TD-DB-07 | Missing index em matched_entity_id -- AJUSTADO para MEDIUM | MEDIUM | pncp_raw_bids | 1 | Nenhuma | Coverage queries com LEFT JOIN |
| TD-DB-08 | Missing GIN index em objeto_contrato | HIGH | pncp_supplier_contracts | 2 | Nenhuma | Full table scan em 3.69M registros |
| TD-DB-09 | esfera_id sem CHECK constraint | LOW | pncp_raw_bids | 1 | TD-DB-01 | Resolver junto com migrations |
| TD-DB-10 | ingestion_checkpoints sem uso -- AJUSTADO para MEDIUM | MEDIUM | ingestion_checkpoints | 1 | Nenhuma | Crawlers nao resumeveis |
| TD-DB-11 | search_datalake HNSW pode nao ser usado -- AJUSTADO para HIGH | HIGH | Function search_datalake | 1 | Nenhuma | Expressao impede uso do index |
| TD-DB-12 | Codigo referencia tabela inexistente search_results_cache | LOW | `local_datalake.py` | 0.5 | Nenhuma | 9 tabelas inexistentes na lista CORE |
| TD-DB-13 | Codigo referencia colunas que nao existem no schema | MEDIUM | `datalake_helper.py` | 4 | TD-DB-01 | Query builder sem validacao |
| TD-DB-14 | purge_old_bids faz DELETE fisico (irreversivel) | MEDIUM | pncp_raw_bids | 4 | Nenhuma | Migrar para UPDATE is_active |
| TD-DB-15 | **NOVO** -- Ausencia total de backup strategy | CRITICAL | Todas as tabelas (4.1 GB) | 4 | Nenhuma | Nenhum script de backup encontrado |
| TD-DB-16 | **NOVO** -- Duas funcoes de upsert de contratos (uma obsoleta) | MEDIUM | pncp_supplier_contracts | 2 | TD-DB-04 | Consolidar em funcao set-based |
| TD-DB-17 | **NOVO** -- Sem tabela de tracking de migrations | LOW | Infrastructure | 2 | TD-DB-01 | Criar _migrations table |

### 2.3 Operacoes & Infraestrutura (identificado por @qa)

| ID | Debito | Severidade | Escopo | Horas | Dependencias |
|----|--------|------------|--------|-------|--------------|
| TD-OPS-01 | **NOVO** -- Ausencia de pipeline CI/CD | HIGH | GitHub Actions (lint, typecheck, tests) | 8 | TD-SYS-009 (test suite) |
| TD-OPS-03 | **NOVO** -- Observabilidade e monitoramento insuficientes | MEDIUM | Logging estruturado, metricas, alertas | 8 | Nenhuma |
| TD-SEC-02 | **NOVO** -- PostgreSQL sem hardening de rede | MEDIUM | Firewall, portas, network isolation | 3 | Nenhuma |

### 2.4 Documentacao (identificado por @qa)

| ID | Debito | Severidade | Escopo | Horas | Dependencias |
|----|--------|------------|--------|-------|--------------|
| TD-DOC-01 | **NOVO** -- Documentacao operacional e de setup insuficiente | MEDIUM | Runbook, deploy guide, troubleshooting | 6 | Nenhuma |

### Nota sobre TD-OPS-02

O GAP-02 do QA (backup e disaster recovery) foi unificado com TD-DB-15 (Ausencia total de backup strategy, CRITICAL), ja adicionado pelo @data-engineer na Fase 5. Nao foi criado um ID separado.

---

## 3. Analise Quantitativa

### 3.1 Por Severidade

| Severidade | Sistema | Database | Operacoes | Documentacao | TOTAL |
|------------|---------|----------|-----------|--------------|-------|
| CRITICAL | 2 | 2 | 0 | 0 | **4** |
| HIGH | 4 | 4 | 1 | 0 | **9** |
| MEDIUM | 7 | 8 | 2 | 1 | **18** |
| LOW | 3 | 4 | 0 | 0 | **7** |
| **TOTAL** | **16** | **18** | **3** | **1** | **38** |

### 3.2 Por Area

```
Crawl System         (5)  █████████████▉  13.2%
Database Perf        (4)  ██████████      10.5%
Database Data Qual   (5)  █████████████▉  13.2%
Database Schema      (4)  ██████████      10.5%
Config Management    (3)  ███████▉         7.9%
Intel Pipeline       (3)  ███████▉         7.9%
Testing              (1)  ██▋              2.6%
Observability        (2)  █████▎           5.3%
Enricher             (2)  █████▎           5.3%
Security             (2)  █████▎           5.3%
Documentacao         (1)  ██▋              2.6%
Dead Code            (1)  ██▋              2.6%
CI/CD                (1)  ██▋              2.6%
Operacoes            (1)  ██▋              2.6%
```

### 3.3 Esforco Total

| Area | Horas Min | Horas Max | Notas |
|------|-----------|-----------|-------|
| Sistema | 66 | 79 | 16 debitos, sem grandes alteracoes de horas |
| Database | 52.5 | 60 | Ajustado pelo @data-engineer (+3 debitos, horas realistas) |
| Operacoes & Infra | 19 | 24 | CI/CD (8h), observabilidade (8h), network hardening (3h) |
| Documentacao | 6 | 8 | Runbook, setup guide, troubleshooting |
| **TOTAL** | **143.5** | **171** | Arredondado: **140-170h** |

### 3.4 Custo Estimado (R$150/h)

| Cenario | Horas | Custo |
|---------|-------|-------|
| Apenas CRITICAL + HIGH (13 debitos) | 60-80 | R$ 9.000 - R$ 12.000 |
| CRITICAL + HIGH + MEDIUM (31 debitos) | 110-130 | R$ 16.500 - R$ 19.500 |
| Resolucao completa (38 debitos) | 140-170 | R$ 21.000 - R$ 25.500 |

---

## 4. Matriz de Priorizacao Final

### 4.1 Ajustes de Severidade (Decisoes do Assessor)

A tabela abaixo documenta todas as alteracoes de severidade entre o DRAFT original e a versao final, com a decisao do arquiteto quando houve conflito entre revisores.

| ID | DRAFT | DB Review | QA Review | **FINAL** | Decisao e Justificativa |
|----|-------|-----------|-----------|-----------|-------------------------|
| TD-SYS-004 | MEDIUM | -- | HIGH | **HIGH** | QA identificou race condition com async Semaphore. Aceito. |
| TD-SYS-012 | LOW | -- | MEDIUM | **MEDIUM** | Fallback silencioso degrada matching sem alerta. Aceito. |
| TD-DB-02 | HIGH | Split | -- | **Split** (ver abaixo) | Desdobrado em TD-DB-02a (HIGH, 4h) e TD-DB-02b (LOW, 1h). |
| TD-DB-05 | MEDIUM | HIGH | MEDIUM | **HIGH** | **Decisao do arquiteto:** @data-engineer investigou codigo e confirmou senha em multiplos scripts, VPS remota, git history permanente. O argumento do QA ("parece ser local dev") e uma suposicao sem confirmacao. A classificaçao prudente e HIGH. |
| TD-DB-07 | LOW | MEDIUM | -- | **MEDIUM** | 199K registros + LEFT JOIN sem index = nested loop scan. Aceito. |
| TD-DB-10 | LOW | -- | MEDIUM | **MEDIUM** | **Decisao do arquiteto:** QA argumentou que tabela com 0 registros significa crawlers nao resumeveis para 2.085 orgaos. Perda de eficiencia operacional real. Aceito. |
| TD-DB-11 | MEDIUM | HIGH | -- | **HIGH** | Expressao impede uso HNSW em TODAS as queries. Aceito. |

### 4.2 Matriz Consolidada

Ordenada por prioridade: CRITICAL > HIGH > MEDIUM (por esforco crescente dentro de cada nivel).

| Prioridade | ID | Debito | Area | Severidade | Horas | Dependencias |
|------------|----|--------|------|------------|-------|--------------|
| 1 | TD-DB-15 | Ausencia total de backup strategy | Database | CRITICAL | 4 | Nenhuma |
| 2 | TD-SYS-001 | Imports quebrados ingestion/ | Crawl System | CRITICAL | 4 | Nenhuma |
| 3 | TD-DB-01 | Migrations divergentes do schema real | Database Schema | CRITICAL | 8 | Nenhuma |
| 4 | TD-SYS-009 | Ausencia de testes automatizados | Testing | CRITICAL | 16 | TD-SYS-011 |
| 5 | TD-DB-08 | Missing GIN index objeto_contrato | Database Perf | HIGH | 2 | Nenhuma |
| 6 | TD-DB-05 | Senha hardcoded em multiplos scripts | Security | HIGH | 2 | Nenhuma |
| 7 | TD-SYS-003 | Ausencia de type hints (341 linhas) | Crawl System | HIGH | 4 | Nenhuma |
| 8 | TD-DB-11 | HNSW expression impede uso do index | Database Perf | HIGH | 1 | Nenhuma |
| 9 | TD-DB-02a | Migrations 009/011/012 nao aplicadas | Database Schema | HIGH | 4 | TD-DB-01 |
| 10 | TD-SYS-004 | Estado global mutavel (cache IBGE) | Enricher | HIGH | 3 | Nenhuma |
| 11 | TD-SYS-011 | Monitor.py superdimensionado (687 linhas) | Crawl System | HIGH | 8 | TD-SYS-009 |
| 12 | TD-SYS-016 | Duas implementacoes de crawler PNCP | Crawl System | HIGH | 8 | TD-SYS-001, TD-SYS-009 |
| 13 | TD-OPS-01 | Ausencia de pipeline CI/CD | CI/CD | HIGH | 8 | TD-SYS-009 |
| 14 | TD-SYS-002 | DSN duplicado | Crawl System | MEDIUM | 1 | Nenhuma |
| 15 | TD-DB-07 | Missing index matched_entity_id | Database Perf | MEDIUM | 1 | Nenhuma |
| 16 | TD-DB-10 | ingestion_checkpoints sem uso | Database Data Qual | MEDIUM | 1 | Nenhuma |
| 17 | TD-SYS-012 | Fallback silencioso difflib | Crawl System | MEDIUM | 0.5 | Nenhuma |
| 18 | TD-DB-06 | GIST trigram index superdimensionado | Database Perf | MEDIUM | 2 | Nenhuma |
| 19 | TD-SYS-010 | supabase_client import inline | Enricher | MEDIUM | 2 | Nenhuma |
| 20 | TD-DB-04 | upsert_pncp_supplier_contracts row-by-row | Database Perf | MEDIUM | 3 | Nenhuma |
| 21 | TD-DB-16 | Duas funcoes de upsert (consolidar) | Database Data Qual | MEDIUM | 2 | TD-DB-04 |
| 22 | TD-SYS-008 | Constantes de config espalhadas | Config Mgmt | MEDIUM | 3 | Nenhuma |
| 23 | TD-DB-03 | enriched_entities sem TTL | Database Data Qual | MEDIUM | 3 | Nenhuma |
| 24 | TD-SYS-013 | Sem schema validation YAML | Config Mgmt | MEDIUM | 4 | Nenhuma |
| 25 | TD-SYS-014 | Sem renovacao de API keys | Config Mgmt | MEDIUM | 4 | Nenhuma |
| 26 | TD-DB-13 | Schema divergence code x banco | Database Data Qual | MEDIUM | 4 | TD-DB-01 |
| 27 | TD-DB-14 | purge_old_bids faz DELETE fisico | Database Data Qual | MEDIUM | 4 | Nenhuma |
| 28 | TD-SYS-015 | Sem healthcheck unificado | Observability | MEDIUM | 6 | Nenhuma |
| 29 | TD-OPS-03 | Observabilidade e monitoramento | Observability | MEDIUM | 8 | Nenhuma |
| 30 | TD-DOC-01 | Documentacao operacional insuficiente | Documentacao | MEDIUM | 6 | Nenhuma |
| 31 | TD-SEC-02 | PostgreSQL sem hardening de rede | Security | MEDIUM | 3 | Nenhuma |
| 32 | TD-SYS-005 | Subprocess sem output control | Intel Pipeline | LOW | 1 | Nenhuma |
| 33 | TD-SYS-006 | ANSI codes manuais com Rich | Intel Pipeline | LOW | 1 | Nenhuma |
| 34 | TD-SYS-007 | import json inline | Intel Pipeline | LOW | 0.5 | Nenhuma |
| 35 | TD-DB-09 | esfera_id sem CHECK constraint | Database Data Qual | LOW | 1 | TD-DB-01 |
| 36 | TD-DB-12 | Referencia tabela inexistente | Database Data Qual | LOW | 0.5 | Nenhuma |
| 37 | TD-DB-02b | Migration 010 (match_logging) | Database Schema | LOW | 1 | TD-DB-01 |
| 38 | TD-DB-17 | Sem tabela de tracking de migrations | Database Schema | LOW | 2 | TD-DB-01 |

---

## 5. Plano de Resolucao

### Fase 0: Emergencia (antes de qualquer refatoracao) -- 1 semana

Objetivo: garantir que o estado atual nao seja perdido e que o sistema basico funcione.

| ID | Debito | Horas | Acao |
|----|--------|-------|------|
| TD-DB-15 | Backup strategy | 4 | Setup de pg_dump --format=custom via systemd timer diario para Hetzner Storage Box. Retention: 7 diarios + 4 semanais. |
| TD-SYS-001 | Imports quebrados | 4 | Criar package ingestion/ com os modulos referenciados OU documentar bids_crawler.py como dead code e remover. |

- Esforco: 8h
- Custo: R$ 1.200
- Criterio de sucesso: pg_dump diario executando; BidsCrawler funcional ou documentado como dead code.

### Fase 1: Quick Wins (paralelizavel) -- 1-2 semanas

| ID | Debito | Horas | Acao |
|----|--------|-------|------|
| TD-DB-08 | GIN index objeto_contrato | 2 | CREATE INDEX ... USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = true |
| TD-DB-11 | HNSW expression fix | 1 | Reescrever search_datalake: `(vec <=> p_embedding) < (1.0 - threshold)` |
| TD-DB-05 | Senha hardcoded | 2 | Migrar para .env + pgpass. Auditar scripts. Rotacionar senha. |
| TD-SYS-009 | Iniciar test suite (transformer.py) | 4 | Testes em transformer.py (funcao pura, zero dependencias) |
| TD-DB-07 | Index matched_entity_id | 1 | CREATE INDEX ... ON pncp_raw_bids(matched_entity_id) WHERE matched_entity_id IS NOT NULL |

- Esforco: 10h
- Custo: R$ 1.500
- Criterio de sucesso: GIN/HNSW indexes criados; senha removida do codigo; primeiros testes passando.

### Fase 2: Schema & Migrations -- 2-3 semanas

| ID | Debito | Horas | Acao |
|----|--------|-------|------|
| TD-DB-01 | Regenerar migrations | 8 | pg_dump --schema-only como baseline, criar migrations v2, setup _migrations table |
| TD-DB-17 | Tracking de migrations | 2 | Criar tabela _migrations, registrar historico |
| TD-DB-02a | Aplicar migrations 009/011/012 adaptadas | 4 | Adaptar triggers e views ao schema real |
| TD-DB-13 | Schema divergence Python vs PG | 4 | Auditar queries em datalake_helper.py, local_datalake.py, monitor.py |
| TD-DB-02b | Migration 010 (verificar se ja existe) | 1 | Confirmar se colunas match_logging ja estao no schema |

- Esforco: 19h
- Custo: R$ 2.850
- Criterio de sucesso: pg_dump --schema-only reproduzivel a partir das migrations v2; zero divergencias.

### Fase 3: Refactoring Seguro -- 3-4 semanas

| ID | Debito | Horas | Acao |
|----|--------|-------|------|
| TD-SYS-009 | Expandir test suite | 12 | Testes para entity matching (3-level cascade), loader, intel pipeline |
| TD-SYS-011 | Refatorar monitor.py | 8 | Extrair SRP: orquestracao, entity matching, coverage em modulos separados |
| TD-SYS-016 | Consolidar crawlers PNCP | 8 | Escolher uma implementacao (sync ou async), remover a outra |

- Esforco: 28h
- Custo: R$ 4.200
- Criterio de sucesso: test coverage >= 40% nos modulos core; monitor.py < 300 linhas; um unico crawler PNCP.

### Fase 4: Qualidade de Codigo -- 2-3 semanas

| ID | Debito | Horas | Acao |
|----|--------|-------|------|
| TD-SYS-003 | Type hints (341 linhas) | 4 | Adicionar type hints em _match_entities_cascade |
| TD-SYS-004 | Estado global mutavel | 3 | Remover cache IBGE module-level, usar instancia |
| TD-SYS-008 | Constantes para settings.py | 3 | Migrar constantes de enricher.py para settings.py |
| TD-SYS-013 | Schema validation YAML | 4 | Validar sectors_config.yaml com Pydantic |
| TD-DB-04 + TD-DB-16 | Consolidar upsert de contratos | 3 | Deprecar row-by-row, padronizar em upsert_supplier_contracts |
| TD-SYS-010 | supabase_client import topo | 2 | Mover imports inline para topo do modulo |
| TD-SYS-002 | DSN duplicado | 1 | Unificar DSN default em settings.py |

- Esforco: 20h
- Custo: R$ 3.000
- Criterio de sucesso: PEP 8 compliant; YAML validado; upsert set-based; type hints nos modulos core.

### Fase 5: Resiliencia & Observabilidade -- 3-4 semanas

| ID | Debito | Horas | Acao |
|----|--------|-------|------|
| TD-OPS-01 | CI/CD pipeline | 8 | GitHub Actions com ruff lint, mypy typecheck, pytest |
| TD-OPS-03 | Observabilidade | 8 | Logging estruturado (JSON), correlation IDs, metricas de cobertura, alertas |
| TD-SYS-015 | Healthcheck unificado | 6 | Endpoint/script de saude do sistema (DB, crawlers, API keys) |
| TD-DB-14 | Soft-delete purge | 4 | Migrar purge_old_bids de DELETE para UPDATE is_active |
| TD-DB-03 | TTL enforcement | 3 | Job de cleanup periodico para enriched_entities |
| TD-SEC-02 | Network hardening | 3 | Firewall, fail2ban, porta 54399 restrita |
| TD-SYS-014 | API key renewal | 4 | Sistema de renovacao automatica com alerta de expiracao |
| TD-DB-06 | GIST vs GIN evaluation | 2 | Coletar metricas de word_similarity(), decidir migracao |

- Esforco: 38h
- Custo: R$ 5.700
- Criterio de sucesso: CI/CD passando; backup diario verificavel; healthcheck respondendo; soft-delete ativo.

### Fase 6: Polish & Documentacao -- 1-2 semanas

| ID | Debito | Horas | Acao |
|----|--------|-------|------|
| TD-DOC-01 | Documentacao operacional | 6 | Runbook, setup guide, deploy instructions, troubleshooting |
| TD-DB-12 | Limpar lista CORE | 0.5 | Remover tabelas inexistentes de local_datalake.py |
| TD-DB-09 | CHECK constraint esfera_id | 1 | Adicionar CHECK (esfera_id IN ('F','E','M','D')) |
| TD-DB-10 | ingestion_checkpoints | 1 | Decidir: integrar nos crawlers ou remover tabela |
| TD-SYS-012 | Fallback difflib logging | 0.5 | Adicionar logging.warning quando fallback e usado |
| TD-SYS-006 | ANSI codes -> Rich | 1 | Substituir cores manuais por Rich |
| TD-SYS-005 | Subprocess output | 1 | Adicionar capture_output com logging |
| TD-SYS-007 | import json inline | 0.5 | Mover para topo do modulo |

- Esforco: 11.5h
- Custo: R$ 1.725
- Criterio de sucesso: README + runbook completo; zero LOW debits abertos.

### Sumario de Fases

| Fase | Descricao | Semanas | Horas | Custo | Debitos |
|------|-----------|---------|-------|-------|---------|
| 0 | Emergencia | 1 | 8 | R$ 1.200 | 2 CRITICAL |
| 1 | Quick Wins | 1-2 | 10 | R$ 1.500 | 1 CRITICAL, 3 HIGH, 1 MEDIUM |
| 2 | Schema & Migrations | 2-3 | 19 | R$ 2.850 | 1 CRITICAL, 1 HIGH, 3 MEDIUM/LOW |
| 3 | Refactoring Seguro | 3-4 | 28 | R$ 4.200 | 1 CRITICAL, 2 HIGH |
| 4 | Qualidade de Codigo | 2-3 | 20 | R$ 3.000 | 2 HIGH, 5 MEDIUM |
| 5 | Resiliencia & Obs. | 3-4 | 38 | R$ 5.700 | 1 HIGH, 7 MEDIUM |
| 6 | Polish & Docs | 1-2 | 11.5 | R$ 1.725 | 1 MEDIUM, 7 LOW |
| **TOTAL** | | **13-19** | **134.5** | **R$ 20.175** | **38** |

Nota: horas totais sao ~134.5h (min) aplicando estimativas conservadoras. Com margem de imprevistos (10-20%), o range final e **140-170h**.

---

## 6. Resolucao de Contradicoes entre Documentos Fonte

### Contradicao 1: Risco de SQL Injection

**Fontes conflitantes:**
- `system-architecture.md` (sec. 10): Classifica SQL queries em `monitor.py` como **MEDIO** risco de SQL injection.
- `DB-AUDIT.md` (sec. 2): Classifica como **Baixo** risco.

**Analise do @data-engineer (investigacao no codigo fonte):**
O trecho apontado (monitor.py:66-68) nao usa f-strings. A concatenacao condicional adiciona apenas literais fixos (`AND raio_200km = TRUE`, `ORDER BY id`) controlados por uma variavel booleana `within_200km_only`. Nao ha interpolacao de dados externos. Todas as demais queries em `monitor.py` usam `%s` placeholders com `cur.execute()`. O unico uso de f-string com nome de tabela (`local_datalake.py:94-98`) e mitigado por regex `re.match(r'^[a-z_][a-z0-9_]*$')`.

**Decisao final:** **LOW.** O risco de SQL injection e aceitavel para single-user com as mitigacoes existentes. Registrar como finding, nao como debito formal. Recomenda-se usar `psycopg2.sql.Identifier()` no lugar de f-strings em `local_datalake.py` como boa pratica, mas nao como correcao urgente.

### Contradicao 2: ORM Anti-pattern

**Fontes conflitantes:**
- `system-architecture.md` (sec. 7.4): Lista "psycopg2 queries diretas sem ORM" como anti-padrao.
- `DB-AUDIT.md` (sec. 2): Aceita como seguro para single-user.

**Analise do @data-engineer:** Para um sistema CLI single-user com 6 tabelas e queries majoritariamente customizadas (RPCs, triggers, full-text search, TSVECTOR, VECTOR(256)), um ORM como SQLAlchemy adicionaria complexidade sem beneficio. ORMs tratam mal tipos PostgreSQL avancados como vetores e triggers.

**Posicao do @qa:** Concorda. Para single-user com Python puro, raw SQL com psycopg2 e pragmatico.

**Decisao final:** **INFORMATIVO** (nao e debito tecnico). A ausencia de ORM e uma escolha arquitetonica valida para o contexto atual. Se o projeto evoluir para multi-usuario ou API REST, recomenda-se adotar `psycopg2.sql` (query builder type-safe) ou SQLAlchemy naquele momento. Registrar como nota arquitetural, nao como debito.

---

## 7. Riscos e Mitigacoes

| Risco | Probabilidade | Impacto | Fase Afetada | Mitigacao |
|-------|---------------|---------|-------------|-----------|
| Perda total do DataLake por falha de disco | BAIXA | CRITICO | 0 | Setup imediato de backup (TD-DB-15) antes de qualquer refatoracao |
| Refatoracao de crawler quebra producao sem testes | ALTA | CRITICO | 3 | Criar test suite com transformer.py primeiro (Fase 1); congelar mudancas no monitor.py ate ter testes |
| Correcao de migrations corrompe dados | MEDIA | CRITICO | 2 | pg_dump --schema-only primeiro; trabalhar em copia; rollback documentado |
| BidsCrawler ja esta quebrado em producao | MEDIA | ALTO | 1 | Verificar experimentalmente; se inoperante, documentar como dead code |
| Duas implementacoes PNCP divergem em resultados | MEDIA | ALTO | 3 | Audit de resultados entre implementacoes antes de consolidar |
| YAML de config com erro silencioso (2.116 linhas) | BAIXA | ALTO | 4 | Schema validation com Pydantic ASAP (TD-SYS-013) |
| DELETE fisico do purge remove dados irreversivelmente | BAIXA | ALTO | 5 | Soft-delete com retention antes do proximo purge agendado (TD-DB-14) |
| Senha do DB exposta se repositorio comprometido | BAIXA | ALTO | 1 | Rotacionar senha imediatamente, migrar para .env (TD-DB-05) |
| Overflow de contexto na migracao de schema (12 migrations v2) | MEDIA | MEDIO | 2 | Manter script current-schema.sql como source of truth; migrations v2 criadas a partir dele |
| Custo de manutencao de indexes cresce com dados | BAIXA | MEDIO | 5 | Auditar indexes nao utilizados com pg_stat_user_indexes |

### Bloqueios Identificados

| Bloqueio | Debitos Afetados | Descricao | Desbloqueio |
|----------|-----------------|-----------|-------------|
| Schema baseline precisa ser estabelecido | TD-DB-02a, TD-DB-02b, TD-DB-09, TD-DB-13, TD-DB-17 | Nao da para aplicar migrations sem saber qual e o schema real | Executar pg_dump --schema-only e criar migrations v2 (Fase 2) |
| Zero testes impedem refactoring seguro | TD-SYS-011, TD-SYS-016 | Monitor.py (687 linhas) e consolidacao de crawlers sao alto risco sem testes | Iniciar test suite com transformer.py (Fase 1); expandir antes da Fase 3 |
| BidsCrawler pode estar inoperante | TD-SYS-001, TD-SYS-016 | Se BidsCrawler nao executa, consolidacao pode ser apenas remocao de dead code | Verificar experimentalmente se roda (Fase 0) |

---

## 8. Governanca de Debito Tecnico

### 8.1 Processos para evitar acumulo futuro

1. **Code review checklist (pre-merge):**
   - Testes acompanham toda mudanca funcional?
   - Schema validation nos YAMLs modificados?
   - Nenhuma secret hardcoded?
   - Nenhum DDL avulso (tudo via migration)?

2. **Pre-commit hooks (recomendado):**
   - `ruff check` -- lint obrigatorio
   - `detect-secrets` -- scan de secrets hardcoded
   - Validacao basica de tipos com `mypy` nos modulos modificados

3. **Migration policy:**
   - Toda alteracao de schema DEVE ser uma migration numerada
   - NUNCA executar DDL avulso em producao
   - Toda migration deve ter rollback documentado
   - Tabela `_migrations` para tracking obrigatorio

4. **Test coverage threshold:**
   - Core modules (transformer, entity matching, loader): >= 60%
   - Demais modulos: >= 30%
   - Gate de PR: coverage nao pode diminuir

5. **Documentacao minima obrigatoria:**
   - README com setup, .env example, comandos basicos
   - Runbook com procedimentos de operacao (crawl, purge, backup)
   - Troubleshooting guide com erros comuns

### 8.2 Metricas de Governanca

| Metrica | Frequencia | Responsavel |
|---------|-----------|-------------|
| Auditoria de secrets no repositorio | Semanal | @qa |
| Verificacao de divergencia schema vs migrations | Mensal | @data-engineer |
| Revisao de indexes nao utilizados | Trimestral | @data-engineer |
| Test coverage report | A cada PR | CI pipeline |
| Backup restore drill | Mensal | @devops |

---

## 9. Criterios de Sucesso

| Metrica | Baseline | Target | Como Medir |
|---------|----------|--------|------------|
| Test coverage (linhas) | 0% | >= 60% (core), >= 30% (geral) | pytest --cov |
| Debitos CRITICAL | 4 | 0 | Assessment tracker |
| Debitos HIGH | 9 | <= 2 | Assessment tracker |
| SQL injection vectors | 1 (local_datalake.py f-string) | 0 | bandit scan + manual review |
| Migrations divergentes | 12/12 divergentes | 0/12 divergentes | diff migration vs pg_dump --schema-only |
| CI/CD pipeline | Inexistente | Lint + typecheck + tests por PR | GitHub Actions status |
| Backup automatizado | Inexistente | Daily pg_dump com retention 7+4 | systemd timer + verificacao semanal |
| Secrets hardcoded no codigo | 1+ (smartlic_local) | 0 | detect-secrets scan |
| Sequential scans em tabelas > 100K | 2+ (contracts, bids) | 0 | EXPLAIN ANALYZE + pg_stat_user_tables |
| Documentacao operacional | README basico | Runbook + setup guide + troubleshooting | Review checklist |

---

## 10. Proximos Passos

1. [ ] **@analyst (Alex)** -- Criar relatorio executivo (Fase 9): `docs/reports/TECHNICAL-DEBT-REPORT.md`
2. [ ] **@pm (Morgan)** -- Criar epic + stories para resolucao (Fase 10)
3. [ ] **Stakeholders** -- Aprovar budget de resolucao (R$ 21.000 a R$ 25.500)
4. [ ] **@devops (Gage)** -- Iniciar Fase 0: setup de backup e verificacao do BidsCrawler
5. [ ] **Revisao trimestral** -- Reavaliar metricas de divida tecnica

---

## Apendice A: Documentos Fonte

| Documento | Fase | Local |
|-----------|------|-------|
| System Architecture | 1 | `docs/architecture/system-architecture.md` |
| SCHEMA.md | 2 | `supabase/docs/SCHEMA.md` |
| DB-AUDIT.md | 2 | `supabase/docs/DB-AUDIT.md` |
| Technical Debt DRAFT | 4 | `docs/prd/technical-debt-DRAFT.md` |
| DB Specialist Review | 5 | `docs/prd/db-specialist-review.md` |
| QA Review | 7 | `docs/prd/qa-review.md` |

## Apendice B: Agentes Participantes

| Agente | Fase | Contribuicao |
|--------|------|-------------|
| @architect (Aria) | 1, 4, 8 | System architecture, DRAFT 30 debitos, Assessment final consolidado |
| @data-engineer (Dara) | 2, 5 | Schema/DB audit, DB specialist review (+3 debitos, severidades ajustadas) |
| @qa (Quinn) | 7 | Quality gate (7.5/10), 5 gaps identificados, 2 contradicoes, test strategy |

## Apendice C: Debitos Removidos ou Reclassificados vs DRAFT Original

| Mudanca | ID Original | Acao | Justificativa |
|---------|------------|------|--------------|
| Split | TD-DB-02 | Dividido em TD-DB-02a (HIGH, 4h) e TD-DB-02b (LOW, 1h) | Migration 010 tem severidade muito menor que 009/011/012 |
| Upgrade | TD-SYS-004 | MEDIUM -> HIGH | Race condition em modulo async confirmado pelo QA |
| Upgrade | TD-SYS-012 | LOW -> MEDIUM | Fallback silencioso degrada matching sem alerta |
| Upgrade | TD-DB-05 | MEDIUM -> HIGH | Senha em git history para VPS remota (decisao do arquiteto) |
| Upgrade | TD-DB-07 | LOW -> MEDIUM | LEFT JOIN sem index em 199K registros |
| Upgrade | TD-DB-10 | LOW -> MEDIUM | Crawlers nao resumeveis para 2.085 orgaos |
| Upgrade | TD-DB-11 | MEDIUM -> HIGH | HNSW index inutilizado em TODAS as queries de embedding |
| Removido | SQL injection (implicito) | Reclassificado como LOW | Codigo fonte confirmou seguranca; nao e debito formal |
| Removido | ORM anti-pattern (implicito) | Reclassificado como INFORMATIVO | Escolha arquitetonica valida para single-user |

---

*Documento gerado por Aria (Visionary Architect) em 2026-07-11.*
*Fases 1-8 do workflow Brownfield Discovery, framework AIOX.*
*Status: FINAL v1.0 -- Validado por @data-engineer (Dara) e @qa (Quinn).*
*Proximo passo: Fase 9 (Relatorio Executivo por @analyst) e Fase 10 (Epic + Stories por @pm).*
