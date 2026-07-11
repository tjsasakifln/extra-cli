# Technical Debt Assessment — DRAFT

## Para Revisao dos Especialistas

**Projeto:** Extra Consultoria (CLI de crawling de licitacoes)
**Data:** 2026-07-11
**Versao:** DRAFT v1.0
**Status:** Aguardando revisao dos especialistas

---

## 1. Executive Summary

A Extra Consultoria e um sistema CLI de inteligencia em licitacoes publicas com aproximadamente 64.000 linhas de codigo Python + SQL, operando um DataLake PostgreSQL centralizado de 4.1 GB. O sistema faz crawl multi-source de 2.085 orgaos publicos de Santa Catarina em 5+ fontes de dados abertos, combinando ingestao continua (systemd timers) com pipelines de inteligencia sob demanda.

O assessment identificou **30 debitos tecnicos** distribuidos entre sistema (16) e database (14), sendo **3 criticos**, **5 high**, **14 medium** e **8 low**. O esforco total estimado para resolucao completa e de **105 a 125 horas**.

O debito mais critico do sistema e a **ausencia total de testes automatizados** (TD-SYS-009) em 64K linhas de codigo, o que torna qualquer refatoracao um risco elevado. No banco de dados, o maior problema e a **divergencia completa entre migrations e schema real** (TD-DB-01), que impossibilita a reproducao do ambiente a partir das migrations existentes.

Ha uma tensao arquitetural significativa entre duas implementacoes concorrentes de crawler PNCP (TD-SYS-016) e a inexistencia de entity_coverage no banco real (TD-DB-02), o que significa que o sistema de monitoramento de cobertura previsto na arquitetura nunca foi ativado.

**Total de debitos:** 30 | **Criticos:** 3 | **High:** 5 | **Esforco estimado:** 105-125h

---

## 2. Debites de Sistema

Do `system-architecture.md` (16 debitos).
PENDENTE: Revisao cruzada com DB.

| ID | Debito | Severidade | Arquivo/Local | Impacto | Esforco (h) |
|----|--------|------------|---------------|---------|-------------|
| TD-SYS-001 | Imports quebrados para `ingestion/` package que nao existe | CRITICAL | `bids_crawler.py` | Crawl BidsCrawler nao executa sem criar diretorio faltante | 4 |
| TD-SYS-002 | DSN default duplicado (monitor.py vs settings.py) | MEDIUM | `monitor.py:48`, `settings.py:33` | Risco de configuracao divergente | 1 |
| TD-SYS-003 | Ausencia de type hints em funcao de 341 linhas | HIGH | `monitor.py:142-341` (`_match_entities_cascade`) | Dificuldade de manutencao | 4 |
| TD-SYS-004 | Estado global mutavel (cache IBGE module-level) | MEDIUM | `enricher.py:483-484` | Race condition potencial | 3 |
| TD-SYS-005 | Subprocess sem controle de output | LOW | `intel_pipeline.py:168-176` | Perda de logs estruturados | 1 |
| TD-SYS-006 | ANSI color codes manuais com Rich disponivel | LOW | `intel_pipeline.py:65-72` | Codigo redundante | 1 |
| TD-SYS-007 | `import json` inline no meio da funcao | LOW | `monitor.py:493` | Violacao PEP 8 | 0.5 |
| TD-SYS-008 | Constantes de config espalhadas vs settings.py | MEDIUM | `enricher.py` (_BRASILAPI_BASE, _ENRICH_STALENESS_DAYS, etc.) | Duplicacao de config | 3 |
| TD-SYS-009 | Ausencia de testes unitarios automatizados | CRITICAL | TODO o projeto | Nao ha garantia contra regression | 16 |
| TD-SYS-010 | `supabase_client` importado inline em vez de no topo | MEDIUM | `enricher.py:102,209,322,580` | Violacao PEP 8, performance | 2 |
| TD-SYS-011 | Monitor.py com ~687 linhas, acopla orquestracao + entity matching + coverage | HIGH | `monitor.py` | Violacao SRP, dificil testar | 8 |
| TD-SYS-012 | Fallback silencioso para difflib sem alerta | LOW | `monitor.py:216-221` | Pode degradar performance sem notificacao | 0.5 |
| TD-SYS-013 | Sem schema validation nos YAML de config | MEDIUM | `config/sectors_config.yaml` | Erro de config silencioso | 4 |
| TD-SYS-014 | Sem renovacao automatica de API keys | MEDIUM | `settings.py` | Falha quando expira | 4 |
| TD-SYS-015 | Sem healthcheck unificado do sistema | MEDIUM | N/A | Nao ha endpoint de saude | 6 |
| TD-SYS-016 | Duas implementacoes de crawler PNCP (sync adapter vs async BidsCrawler) | HIGH | `monitor.py` + `bids_crawler.py` | Duas implementacoes para mesma API, comportamento divergente | 8 |

---

## 3. Debites de Database

Do `DB-AUDIT.md` (14 debitos).
PENDENTE: Revisao do @data-engineer.

| ID | Debito | Severidade | Tabela/Objeto | Impacto | Esforco (h) |
|----|--------|------------|---------------|---------|-------------|
| TD-DB-01 | Migrations totalmente divergentes do schema real | CRITICAL | Todas as tabelas | Rebuild do banco impossivel a partir das migrations | 8 |
| TD-DB-02 | 4 migrations nunca aplicadas (009-012) | HIGH | entity_coverage, views, snapshots | Funcionalidade de cobertura e monitoramento ausente no banco real | 4 |
| TD-DB-03 | enriched_entities sem TTL enforcement | MEDIUM | enriched_entities | Cache de enriquecimento cresce sem controle | 3 |
| TD-DB-04 | upsert_pncp_supplier_contracts row-by-row | MEDIUM | pncp_supplier_contracts | Performance subotima em 3.69M registros | 3 |
| TD-DB-05 | Senha do DB hardcoded em multiplos scripts | MEDIUM | `config/settings.py` e varios scripts | Exposicao de credencial em texto puro no git | 2 |
| TD-DB-06 | GIST trigram index superdimensionado (294 MB) | MEDIUM | pncp_raw_bids (objeto_compra) | Index maior que a propria tabela de dados (268 MB) | 2 |
| TD-DB-07 | Missing index em matched_entity_id | LOW | pncp_raw_bids | Coverage queries com LEFT JOIN sem index | 1 |
| TD-DB-08 | Missing GIN index em objeto_contrato | HIGH | pncp_supplier_contracts | Full table scans de 3.69M registros em buscas textuais | 2 |
| TD-DB-09 | esfera_id sem CHECK constraint | LOW | pncp_raw_bids | Dominio de valores nao validado (F, E, M, D) | 1 |
| TD-DB-10 | ingestion_checkpoints sem uso (0 registros) | LOW | ingestion_checkpoints | Estrutura criada nunca populada — dead code | 1 |
| TD-DB-11 | search_datalake HNSW pode nao ser usado | MEDIUM | Function search_datalake | Expressao `1.0 - (vec <=> ...)` pode impedir uso do HNSW index | 3 |
| TD-DB-12 | Codigo referencia tabela inexistente search_results_cache | LOW | `local_datalake.py` | Confusao na listagem de stats | 0.5 |
| TD-DB-13 | Codigo referencia colunas que nao existem no schema | MEDIUM | `datalake_helper.py` | Queries podem falhar por schema divergence | 4 |
| TD-DB-14 | purge_old_bids faz DELETE fisico (irreversivel) | MEDIUM | pncp_raw_bids | Perda de dados historicos sem soft-delete | 4 |

---

## 4. Debites de Frontend/UX

**N/A — Projeto CLI puro, sem interface web. Fase 3 pulada.**

---

## 5. Matriz Preliminar Consolidada

Ordenada por severidade (CRITICAL > HIGH > MEDIUM > LOW); dentro de cada nivel por esforco crescente (quick wins primeiro).

| Priority | ID | Debito | Area | Severidade | Esforco (h) | Dependencias |
|----------|----|--------|------|------------|-------------|--------------|
| 1 | TD-SYS-001 | Imports quebrados ingestion/ | Crawl System | CRITICAL | 4 | Nenhuma |
| 2 | TD-DB-01 | Migrations divergentes do schema real | Database Schema | CRITICAL | 8 | Nenhuma |
| 3 | TD-SYS-009 | Ausencia de testes automatizados | Testing | CRITICAL | 16 | TD-SYS-011 (monitor.py dificil de testar) |
| 4 | TD-DB-08 | Missing GIN index objeto_contrato | Database Performance | HIGH | 2 | Nenhuma |
| 5 | TD-SYS-003 | Ausencia de type hints (341 linhas) | Crawl System | HIGH | 4 | Nenhuma |
| 6 | TD-DB-02 | 4 migrations nao aplicadas | Database Schema | HIGH | 4 | TD-DB-01 (schema atual precisa ser baseline) |
| 7 | TD-SYS-011 | Monitor.py superdimensionado (687 linhas) | Crawl System | HIGH | 8 | TD-SYS-009 (testes para refatorar seguro) |
| 8 | TD-SYS-016 | Duas implementacoes de crawler PNCP | Crawl System | HIGH | 8 | TD-SYS-009, TD-SYS-001 |
| 9 | TD-SYS-002 | DSN duplicado | Crawl System | MEDIUM | 1 | Nenhuma |
| 10 | TD-DB-05 | Senha hardcoded | Security | MEDIUM | 2 | Nenhuma |
| 11 | TD-DB-06 | GIST trigram index superdimensionado | Database Performance | MEDIUM | 2 | Nenhuma |
| 12 | TD-SYS-010 | supabase_client import inline | Enricher | MEDIUM | 2 | Nenhuma |
| 13 | TD-SYS-004 | Estado global mutavel (cache IBGE) | Enricher | MEDIUM | 3 | Nenhuma |
| 14 | TD-SYS-008 | Constantes de config espalhadas | Config Management | MEDIUM | 3 | Nenhuma |
| 15 | TD-DB-03 | enriched_entities sem TTL | Database Data Quality | MEDIUM | 3 | Nenhuma |
| 16 | TD-DB-04 | upsert_pncp_supplier_contracts row-by-row | Database Performance | MEDIUM | 3 | Nenhuma |
| 17 | TD-DB-11 | HNSW expression impede uso do index | Database Performance | MEDIUM | 3 | Nenhuma |
| 18 | TD-SYS-013 | Sem schema validation YAML | Config Management | MEDIUM | 4 | Nenhuma |
| 19 | TD-SYS-014 | Sem renovacao de API keys | Config Management | MEDIUM | 4 | Nenhuma |
| 20 | TD-DB-13 | Schema divergence code x banco | Database Data Quality | MEDIUM | 4 | TD-DB-01 (schema precisa ser estabilizado) |
| 21 | TD-DB-14 | purge_old_bids faz DELETE fisico | Database Data Quality | MEDIUM | 4 | Nenhuma |
| 22 | TD-SYS-015 | Sem healthcheck unificado | Observability | MEDIUM | 6 | Nenhuma |
| 23 | TD-SYS-007 | import json inline | Intel Pipeline | LOW | 0.5 | Nenhuma |
| 24 | TD-SYS-012 | Fallback silencioso difflib | Crawl System | LOW | 0.5 | Nenhuma |
| 25 | TD-DB-12 | Referencia tabela inexistente | Database Data Quality | LOW | 0.5 | Nenhuma |
| 26 | TD-SYS-005 | Subprocess sem output control | Intel Pipeline | LOW | 1 | Nenhuma |
| 27 | TD-SYS-006 | ANSI codes manuais com Rich | Intel Pipeline | LOW | 1 | Nenhuma |
| 28 | TD-DB-07 | Missing index matched_entity_id | Database Performance | LOW | 1 | Nenhuma |
| 29 | TD-DB-09 | esfera_id sem CHECK constraint | Database Data Quality | LOW | 1 | TD-DB-01 |
| 30 | TD-DB-10 | ingestion_checkpoints sem uso | Dead Code | LOW | 1 | Nenhuma |

---

## 6. Analise de Cobertura

### 6.1 Por Severidade

| Severidade | Sistema | Database | TOTAL |
|------------|---------|----------|-------|
| CRITICAL | 2 | 1 | 3 |
| HIGH | 3 | 2 | 5 |
| MEDIUM | 7 | 7 | 14 |
| LOW | 4 | 4 | 8 |
| **TOTAL** | **16** | **14** | **30** |

### 6.2 Por Area

```
Crawl System       (6)  ████████████████▌  20.0%
Database Perf      (4)  ██████████         13.3%
Database Data Qual (4)  ██████████         13.3%
Config Management  (3)  ███████▉           10.0%
Intel Pipeline     (3)  ███████▉           10.0%
Database Schema    (2)  █████▎              6.7%
Enricher           (2)  █████▎              6.7%
Testing            (1)  ██▋                 3.3%
Observability      (1)  ██▋                 3.3%
Security           (1)  ██▋                 3.3%
Dead Code          (1)  ██▋                 3.3%
```

### 6.3 Esforco Total Estimado

| Area | Horas Min | Horas Max |
|------|-----------|-----------|
| Sistema | 66 | 79 |
| Database | 38.5 | 46 |
| **TOTAL** | **104.5** | **125** |

---

## 7. Perguntas para os Especialistas

### 7.1 Para @data-engineer (Dara)

- **TD-DB-01: Migrations divergentes** — Qual o plano de reconciliacao? Regenerar do zero com `pg_dump --schema-only` ou criar novas migrations incrementais que corrigem o schema atual?
- **TD-DB-02: Migrations 009-012 nao aplicadas** — Necessario aplicar ou descartavel? As tabelas/views de coverage existem em outro lugar?
- **TD-DB-06: GIST trigram index (294 MB)** — Viavel substituir por GIN trigram em `pncp_raw_bids.objeto_compra`? O `word_similarity()` fallback e usado com frequencia suficiente para justificar o custo do GIST?
- **TD-DB-08: GIN index em supplier_contracts.objeto_contrato** — Confirmar que as queries ILIKE em `datalake_helper.py` justificam o index. Sugestao: `USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = true`.
- **TD-DB-11: search_datalake HNSW** — A expressao `1.0 - (embedding <=> p_embedding) > threshold` impede o uso do HNSW index? Recomendacao: reescrever como `(embedding <=> p_embedding) < (1.0 - threshold)`.
- **TD-DB-14: purge_old_bids DELETE fisico** — Ha necessidade de reter historico de bids removidas pelo purge? Migrar para soft-delete com flag?
- **Contradicao entre docs:** System-architecture.md (secao 10) classifica SQL queries em `monitor.py` como MEDIO risco de SQL injection. DB-AUDIT.md (secao 2) classifica como baixo risco. A funcao `_match_entities_cascade` usa f-strings em SQL (linha 67-68) — isso e um risco real ou aceitavel para single-user?

### 7.2 Para @qa (Quinn)

- **Cobertura do assessment:** O DRAFT cobre todas as areas criticas? Ha lacunas na analise?
- **Riscos cruzados:** TD-SYS-009 (zero tests) combinado com TD-SYS-011 (monitor.py superdimensionado) cria risco alto para qualquer refatoracao — como priorizar?
- **Testes: por onde comecar?** Sugestao: transformer.py (funcao pura, sem dependencias externas) como primeiro alvo de test suite. Concorda?
- **TD-SYS-001 e TD-SYS-016:** O BidsCrawler inteiro pode estar inacessivel devido aos imports quebrados. Isso foi verificado experimentalmente?
- **Contradicao:** System-architecture.md trata a falta de ORM como anti-padrao. DB-AUDIT.md aceita como seguro para single-user. Qual e a posicao do projeto sobre isso?

---

## 8. Quick Wins (Baixo Esforco, Alto Impacto)

Debitos com esforco <= 4h e severidade >= HIGH, viaveis para resolucao imediata:

| ID | Debito | Severidade | Esforco (h) | Acao |
|----|--------|------------|-------------|------|
| TD-SYS-001 | Imports quebrados `ingestion/` | CRITICAL | 4 | Criar o package `ingestion/` com os modulos referenciados ou remover o arquivo orphan bids_crawler.py |
| TD-DB-08 | Missing GIN index em objeto_contrato | HIGH | 2 | `CREATE INDEX ... ON pncp_supplier_contracts USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = true` |
| TD-SYS-003 | Type hints em _match_entities_cascade | HIGH | 4 | Adicionar type hints nos parametros e retorno da funcao de 341 linhas |
| TD-DB-02 | Aplicar migrations 009-012 | HIGH | 4 | Adaptar migrations ao schema atual e aplicar |

**Total quick wins:** 4 debitos, ~12-14h de esforco, resolvem 2 CRITICAL + 2 HIGH.

---

## 9. Riscos Identificados (Preliminar)

| Risco | Probabilidade | Impacto | Debites Relacionados |
|-------|---------------|---------|---------------------|
| Ambiente impossivel de replicar | ALTA | CRITICO | TD-DB-01 |
| Refatoracao causa regression silenciosa | ALTA | CRITICO | TD-SYS-009 |
| BidsCrawler nao executa em producao | MEDIA | ALTO | TD-SYS-001 |
| Duas implementacoes de crawler divergem em resultados | MEDIA | ALTO | TD-SYS-016 |
| Cache de enriquecimento cresce sem limites | BAIXA | MEDIO | TD-DB-03 |
| Queries de busca em contratos degradam com crescimento | MEDIA | MEDIO | TD-DB-08 |
| Schema Python vs PG diverge ainda mais com o tempo | ALTA | MEDIO | TD-DB-13 |
| DELETE fisico do purge remove dados sem possibilidade de recuperacao | BAIXA | ALTO | TD-DB-14 |

---

## 10. Proximos Passos

1. @data-engineer revisa secoes 3 e 7.1 → `docs/reviews/db-specialist-review.md`
2. @qa faz review geral com quality gate → `docs/reviews/qa-review.md`
3. @architect incorpora reviews → `docs/prd/technical-debt-assessment.md` (FINAL)
4. @analyst cria relatorio executivo → `docs/reports/TECHNICAL-DEBT-REPORT.md`

---

*Documento gerado por Aria (Visionary Architect) em 2026-07-11.*
*Fontes: docs/architecture/system-architecture.md (Fase 1) + supabase/docs/SCHEMA.md + supabase/docs/DB-AUDIT.md (Fase 2)*
*Status: DRAFT — aguardando revisao dos especialistas.*
