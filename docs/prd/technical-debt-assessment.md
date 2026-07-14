# Technical Debt Assessment - FINAL

**Projeto:** Extra Consultoria
**Versao:** 2.0 (FINAL)
**Data:** 2026-07-13
**Autor:** Aria (Visionary Architect), com revisoes de Dara (@data-engineer), Uma (@ux-design-expert), e Quinn (@qa)

---

## Executive Summary

Este documento consolida o Technical Debt Assessment final do projeto Extra Consultoria, incorporando todas as revisoes dos especialistas e a revisao de qualidade (QA). O documento integra os achados das 3 fases do Brownfield Discovery (system-architecture.md, DB-AUDIT.md, frontend-spec.md) com as revisoes dos especialistas e as lacunas estruturais identificadas pelo QA.

### Distribuicao por Severidade

| Severidade | Sistema | Database | Frontend/UX | Seguranca | Testes/QA | **Total Geral** |
|------------|---------|----------|-------------|-----------|-----------|-----------------|
| CRITICAL | 2 | 0 | 1 | 0 | 0 | **3** |
| HIGH | 9 | 4 | 2 | 3 | 1 | **19** |
| MEDIUM | 13 | 7 | 9 | 3 | 4 | **36** |
| LOW | 5 | 11 | 5 | 0 | 0 | **21** |
| **Total** | **29** | **22** | **17** | **6** | **5** | **79** |

### Esforco Total Estimado

| Area | Itens | Horas | Percentual |
|------|-------|-------|------------|
| Sistema & Infraestrutura | 29 | ~121.5h | 34% |
| Database | 22 | ~33h | 9% |
| Frontend/UX (incl. UX-01) | 17 | ~162h | 46% |
| Seguranca | 6 | ~16h | 5% |
| Testes & QA | 5 | ~21h | 6% |
| **Total Geral** | **79** | **~353.5h** | 100% |
| **Total sem UX-01 (Web UI)** | **78** | **~273.5h** | -- |
| **Total sem UX-01 + MVP 40h** | **78** | **~313.5h** | -- |

### Custo Estimado

| Cenario | Horas | Custo (R$150/h) |
|---------|-------|-----------------|
| Total completo | 353.5h | R$ 53.025 |
| Sem Web UI (UX-01) | 273.5h | R$ 41.025 |
| Web UI MVP (40h) | 313.5h | R$ 47.025 |

### Distribuicao por Prioridade

| Prioridade | Qtd | Horas | Acao |
|------------|-----|-------|------|
| P0 - Imediata | 8 | 41h | Semana 1-2 (Sprint 0) |
| P1 - Curto Prazo | 19 | 82.5h | Sprints 1-3 |
| P2 - Medio Prazo | 31 | 142h | Sprints 4-7 |
| P3 - Longo Prazo | 21 | ~88h | Backlog |
| **Total** | **79** | **~353.5h** | |

### Principais Mudancas vs. DRAFT (v1.0 de 2026-07-11)

| Aspecto | DRAFT (v1.0) | FINAL (v2.0) | Diferenca |
|---------|------------|------------|-----------|
| Total de debitos | 38 | 79 | +41 (cobertura expandida para incluir UX, novos debts DB, seguranca, testes) |
| Debitos CRITICAL | 4 | 3 | -1 (reclassificacao apos analise) |
| Debitos HIGH | 9 | 19 | +10 (elevacoes de severidade + novas categorias) |
| Esforco total | ~140-170h | ~353.5h | +183.5h (cobertura muito mais ampla) |
| Categorias | 4 (SIS/DB/OPS/DOC) | 5 (+Seguranca, +Testes/QA) | +2 categorias dedicadas |

---

## Inventario Completo de Debitos

### 1. Sistema & Infraestrutura (validado por @architect)

**Fonte:** `docs/architecture/system-architecture.md` (Fase 1)
**Total:** 29 debitos (5 movidos para Seguranca e Testes/QA; 4 novos adicionados)
**Esforco:** ~121.5h

**Nota:** Os debitos TD-016 (SQL injection), TD-024 (migrations silenciosas), TD-026 (cobertura), TD-029 (SA JSON no repo), e TD-030 (modulos sem testes) foram movidos para as novas categorias Seguranca e Testes/QA, onde recebem tratamento especifico. O TD-010 teve sua estimativa revisada de 8h para 20h conforme recomendacao do QA (GAP-008).

#### CRITICAL

| ID | Descricao | Localizacao | Impacto | Horas | Prioridade |
|----|-----------|-------------|---------|-------|------------|
| TD-001 | Imports quebrados para `ingestion/` package inexistente | `scripts/crawl/bids_crawler.py` | Crawl BidsCrawler nao executa sem criar diretorio manualmente | 2h | P0 |
| TD-010 | `monitor.py` com ~1756 linhas, acopla orquestracao + entity matching + coverage | `monitor.py` | Violacao SRP, dificil testar, manutencao cara. **Estimativa revisada de 8h para 20h** (QA GAP-008) | 20h | P0 |

#### HIGH

| ID | Descricao | Localizacao | Impacto | Horas | Prioridade |
|----|-----------|-------------|---------|-------|------------|
| TD-003 | Type hints ausentes em funcao de 341 linhas | `monitor.py:_match_entities_cascade` | Dificuldade de manutencao, sem verificacao estatica | 4h | P1 |
| TD-011 | Duas implementacoes de crawler PNCP (sync adapter + async BidsCrawler) | `pncp_crawler_adapter.py` + `bids_crawler.py` | Duas implementacoes para mesma fonte, risco de divergencia | 6h | P1 |
| TD-019 | Import quebrado para `lib.cli_validation` (path relativo) | `intel_pipeline.py:740` | Falha se PYTHONPATH nao configurado | 1h | P1 |
| TD-021 | PNCP `BASE_URL` divergente: settings.py usa v3, .env.example usa v1 | `config/settings.py` vs `.env.example` | Inconsistencia de versao de API | 0.5h | P1 |
| TD-027 | `_match_entities_cascade()` duplicada entre `monitor.py` e `matching/entity_matcher.py` | `monitor.py` + `matching/entity_matcher.py` | Logica duplicada, bugs por divergencia | 4h | P1 |
| TD-028 | Sem CI/CD automatizado (GitHub Actions) | N/A | Sem pipeline de build/test/deploy | 6h | P1 |
| **TD-031** | **Documentacao desatualizada e sem padronizacao** (GAP-003) | Multiplos diretorios | Docstrings ausentes, READMEs inconsistentes, ADRs faltando, runbooks de operacao inexistentes | 6h | P1 |
| **TD-032** | **Observabilidade insuficiente** (GAP-004) | Toda a pipeline | Sem metricas de latencia (P50/P95/P99), logging estruturado ausente, tracing de pipeline inexistente, healthcheck apenas basico | 8h | P1 |
| **TD-033** | **Dependencias externas sem avaliacao de risco** (GAP-005) | PNCP API, BEC, TCE-SC, IBGE, BrasilAPI | Nao ha SLA conhecido, rate limits, planos de fallback, ou custos documentados para nenhuma API externa | 4h | P1 |

#### MEDIUM

| ID | Descricao | Localizacao | Impacto | Horas | Prioridade |
|----|-----------|-------------|---------|-------|------------|
| TD-002 | `DEFAULT_DSN` duplicado entre settings.py e monitor.py | `monitor.py` vs `config/settings.py` | Risco de configuracao divergente | 1h | P2 |
| TD-004 | Estado global mutavel (cache IBGE module-level) | `enricher.py` | Race condition potencial | 2h | P2 |
| TD-008 | Constantes espalhadas vs `config/settings.py` central | `enricher.py` (_BRASILAPI_BASE, etc.) | Duplicacao de config | 3h | P2 |
| TD-009 | `supabase_client` importado inline (4 ocorrencias) | `enricher.py` | Performance, violacao PEP 8 | 2h | P2 |
| TD-013 | Schema validation ausente nos YAML de config | `config/sectors_config.yaml` | Erro de config silencioso | 4h | P2 |
| TD-014 | Sem renovacao automatica de API keys | `settings.py` | Falha quando chave expira | 2h | P2 |
| TD-015 | Sem healthcheck unificado | N/A | Nao ha endpoint de saude do sistema | 4h | P2 |
| TD-017 | Scripts com hyphen vs underscore duplicados | `scripts/` (ex: `intel-enrich.py` + `intel_enrich.py`) | Confusao de entry points | 4h | P2 |
| TD-018 | `backend/` e `config/` duplicam arquivos | `backend/sectors_data.yaml` | Duplicacao de dados (177KB) | 1h | P2 |
| TD-020 | `ingestion/transformer.py` e `_base/crawler.py` sao STUBS | `scripts/crawl/ingestion/` | Implementacao adiada indefinidamente | 6h | P2 |
| TD-022 | Fallback de DSN hardcoded em varios CLIs | `opportunity_intel/cli.py`, `local_datalake.py` | Risco de conexao acidental | 2h | P2 |
| TD-025 | ORM ausente: queries SQL diretas sem abstracao | Todo o projeto | Acoplamento forte ao schema PostgreSQL. **Necessita analise de alternativas antes de estimar (QA GAP-009)** | 20h+ | P2 |
| **TD-034** | **Ausencia de distincao de ambientes dev/staging/prod** (GAP-006) | Configuracoes | Nao ha separacao de configuracoes, segredos, ou estrategia de promocao entre ambientes | 4h | P2 |

#### LOW

| ID | Descricao | Localizacao | Impacto | Horas | Prioridade |
|----|-----------|-------------|---------|-------|------------|
| TD-005 | Subprocess sem controle de output estruturado | `intel_pipeline.py` | Perda de logs estruturados | 2h | P3 |
| TD-006 | ANSI color codes manuais com `rich` disponivel | `intel_pipeline.py` | Codigo redundante | 1h | P3 |
| TD-007 | `import json` inline no meio de funcao | `monitor.py` | Violacao PEP 8 | 0.5h | P3 |
| TD-012 | Fallback silencioso `rapidfuzz` -> `difflib` sem alerta | `monitor.py` | Degradacao silenciosa | 1h | P3 |
| TD-023 | Mides BigQuery PULADO sem aviso claro | `.aiox/gotchas.json` | Expectativa falsa de cobertura | 0.5h | P3 |

---

### 2. Database (validado por @data-engineer)

**Fonte:** `supabase/docs/DB-AUDIT.md` (Fase 2), revisado por Dara
**Total:** 22 debitos (17 originais + 6 novos - 1 duplicata DT-17 fundido em DT-01)
**Esforco:** ~33h
**Schema snapshot:** `supabase/current-schema.sql` (2026-07-11)

**Nota:** DT-17 foi fundido em DT-01 (descrevem o mesmo problema sob oticas diferentes).
DT-07 (senha hardcoded) foi movido para Seguranca (SEC-03).

#### HIGH

| ID | Descricao | Objeto | Impacto | Horas | Prioridade |
|----|-----------|--------|---------|-------|------------|
| DT-01 | Colunas match_logging (match_method, match_score, match_confidence) ausentes no schema real **(inclui DT-17)** | `pncp_raw_bids` | Match cascade sem audit trail. Nova migration 005b-v2 necessaria (nao re-executar 005-v2) | 1h | P1 |
| DT-02 | 10 tabelas v3 nao aplicadas ao banco | Multiplas tabelas | Funcionalidades de oportunidade, engenharia e hierarquia ausentes. **Prioridade elevada para P0** (bloqueia pipeline de oportunidade) | 4h | **P0** |
| DT-05 | `upsert_pncp_supplier_contracts` row-by-row | Funcao SQL | Volume comprovado de 3.7M registros. **Elevado de MEDIUM para HIGH** -- gargalo real de performance | 2h | P1 |
| DT-07 | **(REMOVIDO - movido para SEC-03)** | `config/settings.py` | Ver categoria Seguranca | -- | -- |

#### MEDIUM

| ID | Descricao | Objeto | Impacto | Horas | Prioridade |
|----|-----------|--------|---------|-------|------------|
| DT-03 | Ordem de dependencia v2 incorreta (003 depende de 005) | 003-v2, 005-v2 | Aplicacao fora de ordem quebra. Renumerar 003-v2 para ~006-v2 | 1h | P2 |
| DT-04 | `upsert_pncp_raw_bids` row-by-row | Funcao SQL | Volume ~200K, ainda nao e gargalo. Preparar para escala (2h, nao 4h) | 2h | P2 |
| DT-06 | Sem UNIQUE constraint em `sc_public_entities.cnpj_8` | `sc_public_entities` | Permite duplicatas de CNPJ raiz. Pre-check necessario antes de adicionar | 2h | P2 |
| DT-14 | Nao ha coverage reconciliation periodica | `entity_coverage` | Bulk operations que bypassam triggers ficam inconsistentes. Risco baixo hoje, crescente | 3h | P2 |
| DT-19 | `pncp_raw_bids` sem FK entre `orgao_cnpj` e `sc_public_entities` **(NOVO)** | `pncp_raw_bids` | Bids de orgaos nao cadastrados ficam orfaos | 2h | P2 |
| DT-20 | `pncp_supplier_contracts` sem FK para tabela de entidade alguma **(NOVO)** | `pncp_supplier_contracts` | Contracts orfaos sem vinculo com orgao ou fornecedor | 2h | P2 |
| DT-22 | Ausencia de politica de retencao/lifecycle para dados antigos **(NOVO)** | Multiplas tabelas | `purge_old_bids` com 400 dias hardcoded, nao cobre `pncp_supplier_contracts` (3.7M) | 3h | P2 |

#### LOW

| ID | Descricao | Objeto | Impacto | Horas | Prioridade |
|----|-----------|--------|---------|-------|------------|
| DT-08 | Sem CHECK constraint para `esfera_id` | `pncp_raw_bids` | Dominio nao validado (1,2,3,4). Baixo risco | 0.5h | P3 |
| DT-09 | Sem CHECK constraint para `source` | Multiplas tabelas | 4 tabelas com dominios diferentes. Horas ajustada para 2h | 2h | P3 |
| DT-10 | Sem CHECK constraint para `status` em `ingestion_runs` | `ingestion_runs` | Dominio pequeno (running, completed, failed) | 0.5h | P3 |
| DT-11 | `search_datalake` com fallback ILIKE sem index de trigram | `pncp_raw_bids` | Full table scan no fallback. Sem evidencia de uso frequente | 1h | P3 |
| DT-12 | Data types inconsistentes (DATE vs TIMESTAMPTZ) | `pncp_raw_bids` | DATE e apropriado; apenas funcoes precisam de casting | 1h | P3 |
| DT-13 | `ingestion_checkpoints` vazia e sem uso | `ingestion_checkpoints` | 0 registros. Integrar nos crawlers ou remover | 0.5h | P3 |
| DT-15 | `content_hash` UNIQUE sem partial para `is_active` | `pncp_raw_bids` | Re-insercao de registro soft-deletado falha | 1h | P3 |
| DT-16 | GIN index `idx_psc_objeto_trgm` ausente no v2 baseline | `pncp_supplier_contracts` | **Reduzido de MEDIUM para LOW** -- index existe em producao, ausente apenas do arquivo de migration | 0.5h | P3 |
| DT-18 | `pncp_supplier_contracts` sem soft-delete (`is_active`) e sem partial index **(NOVO)** | `pncp_supplier_contracts` | Inconsistencia de design com `pncp_raw_bids` | 1h | P3 |
| DT-21 | `tsv` (full-text vector) populado apenas na funcao upsert, nao via trigger **(NOVO)** | `pncp_raw_bids` | Insercao direta deixa `tsv = NULL`, quebrando FTS | 1h | P3 |
| DT-23 | `objeto_compra` nullable em `pncp_raw_bids` sem NOT NULL enforced **(NOVO)** | `pncp_raw_bids` | Coluna critica para FTS aceita NULL; upsert mascara com COALESCE | 1h | P3 |

---

### 3. Frontend/UX (validado por @ux-design-expert)

**Fonte:** `docs/frontend/frontend-spec.md` (Fase 3), revisado por Uma
**Total:** 17 debitos (12 validados + 5 novos)
**Esforco:** ~82h (excl. UX-01) / ~162h (incl. UX-01)

**Nota:** Severidades ajustadas conforme revisao de Uma. Priorizacao baseada em impacto no usuario final (40% ponderacao).

#### CRITICAL

| ID | Descricao | Impacto | Horas | Prioridade |
|----|-----------|---------|-------|------------|
| UX-02 | No progress indicators -- comandos longos (update, radar, PDF) sem feedback | **Elevado de HIGH para CRITICAL.** Usuarios olham terminal vazio por minutos. Risco real de abortarem comandos prematuramente. 3 comandos afetados | 8h | P0 |

#### HIGH

| ID | Descricao | Impacto | Horas | Prioridade |
|----|-----------|---------|-------|------------|
| UX-01 | No web UI -- toda interacao requer SSH/VPS access | Limita base de usuarios; sem portal client-facing. **MVP viavel em ~40h (FastAPI+HTMX), nao 80h.** Debito estrategico (6-12 meses) | 80h+ | P3 |
| UX-04 | Table truncation -- `_print_table()` trunca em 20 chars / 10 cols | **Elevado de MEDIUM para HIGH.** Colunas `objeto` e `orgao_nome` truncadas, tornando listagem inutil para analise. Afeta Journey 2 (Finding Opportunities) | 4h | P1 |

#### MEDIUM

| ID | Descricao | Impacto | Horas | Prioridade |
|----|-----------|---------|-------|------------|
| UX-03 | Dual display paradigm -- `rich` vs raw `print()` sem componente compartilhado | Qualidade visual inconsistente; duplicacao de codigo. `rich` ja e dependencia do projeto | 12h | P2 |
| UX-07 | No pagination para grandes result sets (500+ linhas) | **Elevado de LOW para MEDIUM.** Terminal overflow em `list --limit 500` ou `supplier` com muitos contratos | 6h | P2 |
| UX-08 | Empty output on errors -- ferramentas printam nada em falha | Usuario nao sabe se comando falhou, esta processando, ou resultado e vazio | 3h | P1 |
| UX-09 | Coverage dashboard duplicado em opportunity_intel e local_datalake CLIs | Dois entry points com UX diferente para mesma funcionalidade. Consolidar em `local_datalake` | 6h | P2 |
| UX-10 | Gerador de relatorio monolitico -- `generate-report-b2g.py` com 287KB | Dificil manter; startup lento. Impacto UX indireto (bugs demoram para corrigir) | 16h | P2 |
| UX-12 | No input validation messages -- args validados so na query DB | Usuario recebe erro SQL em vez de mensagem amigavel. **Mantido como MEDIUM** (draft marcou LOW) | 4h | P2 |
| UX-13 | Ausencia de onboarding / help contextual **(NOVO)** | `--help` minimalista. Sem `--examples` flag. Usuario novo precisa de documentacao externa | 6h | P2 |
| UX-16 | Tracebacks crus expostos ao usuario em erros **(NOVO)** | Usuario nao-tecnico ve `Traceback (most recent call last):` em vez de mensagem amigavel | 4h | P1 |
| UX-17 | Radar output como JSON bruto no stdout **(NOVO)** | "Wall of JSON, no progress". Usuario precisa garimpar o JSON para entender o resultado | 3h | P1 |

#### LOW

| ID | Descricao | Impacto | Horas | Prioridade |
|----|-----------|---------|-------|------------|
| UX-05 | Exit codes inconsistentes -- 0/1 vs 0/1/2 entre ferramentas | Impacto maior em automacao/scripting. Para UX interativa, baixo | 2h | P3 |
| UX-06 | Output flags inconsistentes -- `--format table|json` vs `--json` booleano | Carga cognitiva ao alternar ferramentas. Resolver como parte do UX-03 | 2h | P3 |
| UX-11 | No terminal hyperlinks -- URLs impressas como texto puro | Conveniencia, nao blocker. `rich` ja suporta hyperlinks | 2h | P3 |
| UX-14 | Sem confirmacao antes de operacoes destrutivas **(NOVO)** | `export` sobrescreve arquivo sem aviso. Adicionar `--force` flag | 2h | P3 |
| UX-15 | Formatacao monetaria divergente entre ferramentas **(NOVO)** | `_fmt_money()` vs `f"R$ {v:,.2f}"`. Resolver como parte do UX-03 | 2h | P3 |

---

### 4. Seguranca (adicionado via QA review)

**Fonte:** Extraido de debitos existentes (TD-016, TD-029, DT-07) + novos achados do QA (GAP-001)
**Total:** 6 debitos
**Esforco:** ~16h

**Justificativa:** O QA identificou como GAP CRITICO (GAP-001) a ausencia de uma visao consolidada de seguranca. Credenciais no git, SQL injection potencial, e dependencias sem auditoria representam risco real de incidente.

#### HIGH

| ID | Descricao | Localizacao | Impacto | Horas | Prioridade | Origem |
|----|-----------|-------------|---------|-------|------------|--------|
| SEC-01 | SQL queries concatenadas com f-strings (risco SQL injection) | `monitor.py` (linhas 67-68) | Risco teorico de SQL injection. Originalmente TD-016 (HIGH) | 3h | **P0** | TD-016 (movido de Sistema) |
| SEC-02 | Service account JSON no repo | `config/mides-bigquery-sa.json` | Vazamento de credenciais GCP. Originalmente TD-029 (MEDIUM). **Elevado para P0 pelo QA** | 1h | **P0** | TD-029 (movido de Sistema) |
| SEC-03 | Senha hardcoded em `config/settings.py` | `config/settings.py` | Credencial `postgres:smartlic_local` versionada no git. Originalmente DT-07 (MEDIUM), elevado para HIGH por Dara, **P0 pelo QA** | 1h | **P0** | DT-07 (movido de Database) |

#### MEDIUM

| ID | Descricao | Localizacao | Impacto | Horas | Prioridade | Origem |
|----|-----------|-------------|---------|-------|------------|--------|
| SEC-04 | Dependencias sem auditoria de CVE (bibliotecas desatualizadas) | `requirements.txt`, `pyproject.toml` | Bibliotecas com vulnerabilidades conhecidas podem estar em uso. Sem processo de scanning | 4h | P1 | QA GAP-001 |
| SEC-05 | Ausencia de estrategia de secrets management | Multiplos arquivos | Service account, senha DB, API keys em texto puro. Sem uso de vault, env vars segregadas, ou .env.example | 3h | P2 | QA GAP-001 |
| SEC-06 | Ausencia de threat modeling para o sistema | N/A | Sem analise de superficies de ataque, vetores de exposicao, ou modelo de ameacas para o sistema como um todo | 4h | P2 | QA GAP-001 |

---

### 5. Testes & QA (adicionado via QA review)

**Fonte:** Extraido de debitos existentes (TD-024, TD-026, TD-030) + novos achados do QA (GAP-002)
**Total:** 5 debitos
**Esforco:** ~21h

**Justificativa:** O QA identificou como GAP CRITICO (GAP-002) a ausencia de uma avaliacao consolidada de qualidade de testes. Refatorar 1756 linhas de monitor.py (TD-010) sem baseline de testes e risco alto de quebrar funcionalidade existente sem deteccao.

#### HIGH

| ID | Descricao | Localizacao | Impacto | Horas | Prioridade | Origem |
|----|-----------|-------------|---------|-------|------------|--------|
| TQ-04 | Ausencia de suite de testes de integracao para crawlers | `scripts/crawl/` | **Blocker para TD-010 (refatorar monitor.py).** Sem testes de integracao, qualquer extracao do monitor.py pode quebrar o crawl de producao sem deteccao | 8h | **P0** | QA GAP-002 + CR-001 |

#### MEDIUM

| ID | Descricao | Localizacao | Impacto | Horas | Prioridade | Origem |
|----|-----------|-------------|---------|-------|------------|--------|
| TQ-01 | Migrations falham silenciosamente em DB ja migrado | `tests/conftest_db.py` | Erros de migration passam despercebidos. Originalmente TD-024 (MEDIUM) | 3h | P1 | TD-024 (movido de Sistema) |
| TQ-02 | Testes sem coverage minima definida | `tests/` | Nao ha gate de cobertura minima (ex: >= 60%). Sem metrica de qualidade de testes. Originalmente TD-026 (MEDIUM) | 2h | P1 | TD-026 (movido de Sistema) |
| TQ-03 | Modulos criticos sem testes: `opportunity_intel/schema.py` e `coverage/calculator.py` | `tests/` | Funcionalidades criticas (schema v3, cobertura) sem cobertura. Originalmente TD-030 (MEDIUM) | 4h | P1 | TD-030 (movido de Sistema) |
| TQ-05 | Ausencia de metricas de qualidade dos testes existentes | `tests/` | Nao ha avaliacao de: qualidade dos asserts, proporcao integracao vs unitarios, estrategia de test doubles, velocidade do suite | 4h | P2 | QA GAP-002 |

---

## Matriz de Priorizacao Final

Todos os 79 debitos ordenados por prioridade (P0 > P1 > P2 > P3) e, dentro de cada nivel, por ordem de resolucao recomendada (dependencias primeiro).

### P0 -- Imediata (8 items, ~41h)

| Ordem | ID | Debito | Area | Severidade | Horas | Dependencias |
|-------|----|--------|------|------------|-------|--------------|
| 1 | **SEC-03** | Senha hardcoded em config/settings.py (DT-07) | Seguranca | HIGH (P0 elevado) | 1h | -- |
| 2 | **SEC-02** | Service account JSON no repo (TD-029) | Seguranca | HIGH (P0 elevado) | 1h | -- |
| 3 | **TD-001** | Imports quebrados para ingestion/ | Sistema | CRITICAL | 2h | -- |
| 4 | **SEC-01** | SQL queries com f-strings (TD-016) | Seguranca | HIGH (P0 elevado) | 3h | -- |
| 5 | **DT-02** | 10 tabelas v3 nao aplicadas ao banco | Database | HIGH (P0 funcional) | 4h | DT-03 |
| 6 | **TQ-04** | Suite de testes de integracao para crawlers | Testes/QA | HIGH (P0 blocker) | 8h | -- |
| 7 | **UX-02** | Progress indicators em comandos longos | Frontend/UX | CRITICAL | 8h | -- |
| 8 | **TD-010** | monitor.py com 1756 linhas (SRP) | Sistema | CRITICAL | 20h | TQ-04 |

### P1 -- Curto Prazo (19 items, ~82.5h)

| Ordem | ID | Debito | Area | Horas | Depende de |
|-------|----|--------|------|-------|------------|
| 9 | **SEC-04** | Dependencias sem CVE audit | Seguranca | 4h | -- |
| 10 | **DT-01** | Colunas match_logging ausentes | Database | 1h | DT-06 (parcial) |
| 11 | **DT-05** | upsert_pncp_supplier_contracts row-by-row | Database | 2h | DT-02 |
| 12 | **UX-17** | Radar summary human-readable | Frontend/UX | 3h | -- |
| 13 | **UX-04** | Table truncation (20 chars) | Frontend/UX | 4h | -- |
| 14 | **UX-08** | Error handling padrao | Frontend/UX | 3h | UX-03 (parcial) |
| 15 | **UX-16** | Esconder tracebacks com --debug | Frontend/UX | 4h | UX-08 |
| 16 | **TQ-01** | Migrations falham silenciosamente | Testes/QA | 3h | -- |
| 17 | **TQ-02** | Cobertura minima de testes | Testes/QA | 2h | -- |
| 18 | **TQ-03** | Modulos criticos sem testes | Testes/QA | 4h | -- |
| 19 | **TD-027** | Entity matching duplicado | Sistema | 4h | TD-010, DT-01 |
| 20 | **TD-028** | CI/CD (GitHub Actions) | Sistema | 6h | TQ-02 |
| 21 | **TD-003** | Type hints ausentes | Sistema | 4h | TD-010 |
| 22 | **TD-011** | Duas implementacoes de crawler PNCP | Sistema | 6h | DT-02, DT-05 |
| 23 | **TD-019** | Import quebrado lib.cli_validation | Sistema | 1h | -- |
| 24 | **TD-021** | PNCP BASE_URL divergente | Sistema | 0.5h | -- |
| 25 | **TD-031** | Documentacao desatualizada | Sistema | 6h | -- |
| 26 | **TD-032** | Observabilidade (metricas, tracing) | Sistema | 8h | TD-028 |
| 27 | **TD-033** | Dependencias externas sem avaliacao | Sistema | 4h | -- |

### P2 -- Medio Prazo (31 items, ~142h)

| Ordem | ID | Debito | Area | Horas | Depende de |
|-------|----|--------|------|-------|------------|
| 28 | **SEC-05** | Estrategia de secrets management | Seguranca | 3h | SEC-02, SEC-03 |
| 29 | **SEC-06** | Threat modeling | Seguranca | 4h | SEC-05 |
| 30 | **TQ-05** | Metricas de qualidade dos testes | Testes/QA | 4h | TQ-02 |
| 31 | **DT-14** | Coverage reconciliation periodica | Database | 3h | DT-02 |
| 32 | **DT-19** | FK orgao_cnpj em pncp_raw_bids | Database | 2h | DT-06 |
| 33 | **DT-20** | FK contracts para entidades | Database | 2h | DT-19 |
| 34 | **DT-22** | Politica de retencao de dados | Database | 3h | DT-05 |
| 35 | **DT-03** | Renumerar migrations v2 | Database | 1h | -- |
| 36 | **DT-04** | upsert_pncp_raw_bids set-based | Database | 2h | DT-05 |
| 37 | **DT-06** | UNIQUE em sc_public_entities.cnpj_8 | Database | 2h | -- |
| 38 | **UX-13** | Onboarding / help contextual | Frontend/UX | 6h | -- |
| 39 | **UX-12** | Input validation com mensagens | Frontend/UX | 4h | UX-03 |
| 40 | **UX-03** | Migrar CLIs para rich | Frontend/UX | 12h | -- |
| 41 | **UX-09** | Consolidar coverage dashboard | Frontend/UX | 6h | DT-02 |
| 42 | **UX-07** | Pagination para result sets | Frontend/UX | 6h | UX-03 |
| 43 | **UX-10** | Refatorar gerador de relatorio | Frontend/UX | 16h | -- |
| 44 | **TD-025** | Avaliar ORM vs alternativas | Sistema | 20h+ | -- |
| 45 | **TD-020** | Ingestion stubs (transformer, crawler) | Sistema | 6h | DT-02, DT-04 |
| 46 | **TD-013** | Schema validation YAML | Sistema | 4h | -- |
| 47 | **TD-015** | Healthcheck unificado | Sistema | 4h | TD-032 |
| 48 | **TD-017** | Hyphen+underscore scripts duplicados | Sistema | 4h | -- |
| 49 | **TD-008** | Constantes espalhadas vs central | Sistema | 3h | -- |
| 50 | **TD-004** | Estado global mutavel (cache IBGE) | Sistema | 2h | TQ-04 |
| 51 | **TD-009** | supabase_client importado inline | Sistema | 2h | -- |
| 52 | **TD-014** | Renovacao automatica de API keys | Sistema | 2h | SEC-05 |
| 53 | **TD-022** | DSN fallback hardcoded | Sistema | 2h | SEC-03 |
| 54 | **TD-002** | DEFAULT_DSN duplicado | Sistema | 1h | -- |
| 55 | **TD-018** | backend/ e config/ duplicam | Sistema | 1h | -- |
| 56 | **TD-034** | Ambientes dev/staging/prod | Sistema | 4h | TD-028 |
| 57 | **UX-15** | Formatacao monetaria centralizada | Frontend/UX | 1h | UX-03 |
| 58 | **UX-14** | Confirmacao antes de sobrescrever | Frontend/UX | 2h | UX-03 |

### P3 -- Longo Prazo (21 items, ~88h)

| Ordem | ID | Debito | Area | Horas |
|-------|----|--------|------|-------|
| 59 | **TD-005** | Subprocess sem output estruturado | Sistema | 2h |
| 60 | **TD-006** | ANSI color codes manuais | Sistema | 1h |
| 61 | **TD-007** | import json inline | Sistema | 0.5h |
| 62 | **TD-012** | Fallback silencioso rapidfuzz | Sistema | 1h |
| 63 | **TD-023** | Mides BigQuery pulado | Sistema | 0.5h |
| 64 | **DT-08** | CHECK constraint esfera_id | Database | 0.5h |
| 65 | **DT-09** | CHECK constraint source | Database | 2h |
| 66 | **DT-10** | CHECK constraint status | Database | 0.5h |
| 67 | **DT-11** | GIN trigram index | Database | 1h |
| 68 | **DT-12** | DATE vs TIMESTAMPTZ | Database | 1h |
| 69 | **DT-13** | ingestion_checkpoints | Database | 0.5h |
| 70 | **DT-15** | UNIQUE partial content_hash | Database | 1h |
| 71 | **DT-16** | Atualizar migration baseline | Database | 0.5h |
| 72 | **DT-18** | Soft-delete em pncp_supplier_contracts | Database | 1h |
| 73 | **DT-21** | tsv via trigger | Database | 1h |
| 74 | **DT-23** | objeto_compra NOT NULL | Database | 1h |
| 75 | **UX-05** | Exit codes inconsistentes | Frontend/UX | 2h |
| 76 | **UX-06** | Output flags inconsistentes | Frontend/UX | 2h |
| 77 | **UX-11** | Terminal hyperlinks | Frontend/UX | 2h |
| 78 | **UX-01** | Web UI (MVP ~40h / completo 80h+) | Frontend/UX | 40-80h+ |
| 79 | **UX-14** | Confirmacao antes de sobrescrever | Frontend/UX | 2h |

---

## Plano de Resolucao

### Fase 0: Seguranca e Quick Wins (1-2 semanas -- ~41h)

Foco: eliminar riscos de seguranca imediatos, desbloquear funcionalidades criticas, e preparar base para refatoracoes maiores.

| Ordem | ID | Debito | Horas | Criterio de Sucesso |
|-------|----|--------|-------|---------------------|
| 1 | SEC-03 | Migrar senha DB para .env + BFG cleanup | 1h | Zero senhas em texto puro no repo; credencial rotacionada |
| 2 | SEC-02 | Remover SA JSON do repo + Workload Identity | 1h | Nenhum arquivo JSON de service account no diretorio do projeto |
| 3 | TD-001 | Criar ingestion/ __init__.py ou ajustar imports | 2h | BidsCrawler executa sem erro de import |
| 4 | SEC-01 | Migrar f-strings SQL para query parameters | 3h | grep por f-strings em queries SQL retorna zero |
| 5 | DT-02 | Aplicar migration 006-v3 (dry-run + producao) | 4h | 10 tabelas, 6 views, 4 funcoes existem; opportunity_intel funciona |
| 6 | TQ-04 | Criar suite de testes de integracao para crawlers | 8h | Testes com snapshot de dados reais passam; cobertura > 50% em crawl/ |
| 7 | UX-02 | Adicionar rich.progress.Progress nos 3 comandos | 8h | update, radar, generate-report mostram barra de progresso |
| 8 | TD-010 | Iniciar refatoracao do monitor.py (extrair entity matching) | 20h | monitor.py reduzido de 1756 para < 1000 linhas; zero regressao |

### Fase 1: Fundacao (2-4 semanas -- ~82.5h)

Foco: consolidar a base do sistema apos as correcoes de seguranca, estabelecer quality gates, e entregar melhorias de UX de alto impacto.

| Ordem | ID | Debito | Horas | Sprint Sugerido |
|-------|----|--------|-------|-----------------|
| 1 | UX-17 | Radar summary human-readable | 3h | Sprint 1 |
| 2 | UX-04 | Table truncation (60 chars + rich.Table) | 4h | Sprint 1 |
| 3 | UX-08 | Error handling padrao [ERROR] + acao | 3h | Sprint 1 |
| 4 | UX-16 | Esconder tracebacks, --debug flag | 4h | Sprint 1 |
| 5 | TQ-01 | Corrigir migrations silenciosas | 3h | Sprint 1 |
| 6 | TQ-02 | Estabelecer coverage minima (>= 60%) | 2h | Sprint 1 |
| 7 | TQ-03 | Adicionar testes para schema.py e calculator.py | 4h | Sprint 1 |
| 8 | DT-05 | Refatorar upsert_pncp_supplier_contracts (set-based) | 2h | Sprint 1 |
| 9 | DT-01 | Criar migration 005b-v2 com colunas match_logging | 1h | Sprint 2 |
| 10 | TD-019 | Corrigir import lib.cli_validation | 1h | Sprint 2 |
| 11 | TD-021 | Unificar PNCP BASE_URL (v3) | 0.5h | Sprint 2 |
| 12 | TD-027 | Unificar entity matching (eliminar duplicacao) | 4h | Sprint 2 |
| 13 | TD-028 | Implementar GitHub Actions (ruff, mypy, pytest) | 6h | Sprint 2 |
| 14 | TD-003 | Adicionar type hints em _match_entities_cascade | 4h | Sprint 2 |
| 15 | SEC-04 | Auditoria de CVE em dependencias | 4h | Sprint 2 |
| 16 | TD-031 | Documentacao: ADRs, READMEs, runbooks | 6h | Sprint 3 |
| 17 | TD-033 | Matriz de riscos de dependencias externas | 4h | Sprint 3 |
| 18 | TD-011 | Decidir e unificar implementacao de crawler PNCP | 6h | Sprint 3 |
| 19 | UX-13 | Onboarding: --examples flag + help melhorado | 6h | Sprint 3 |
| 20 | TD-032 | Observabilidade (logging estruturado, metricas) | 8h | Sprint 3 |

### Fase 2: Otimizacao (4-8 semanas -- ~142h)

Foco: qualidade estrutural, performance de database, padronizacao UX.

| Bloco | Itens | Horas | Dependencias |
|-------|-------|-------|--------------|
| **Database Integrity** | DT-14, DT-19, DT-20, DT-06, DT-04, DT-22, DT-03 | 15h | DT-02, DT-05 |
| **UX Standardization** | UX-03, UX-09, UX-07, UX-12, UX-15, UX-14 | 31h | UX-02, UX-04 |
| **Quality & Security** | SEC-05, SEC-06, TQ-05 | 11h | SEC-02, SEC-03 |
| **System Architecture** | TD-025, TD-020, TD-013, TD-015 | 34h+ | TD-028, DT-02 |
| **Housekeeping** | TD-017, TD-008, TD-004, TD-009, TD-014, TD-022, TD-002, TD-018, TD-034 | 19h | SEC-05, TQ-04 |
| **UX Content** | UX-10 (relatorio monolitico) | 16h | -- |

### Fase 3: Longo Prazo (backlog)

Itens P3: housekeeping de database (CHECK constraints, indexes, types), LOW items de sistema, e Web UI (UX-01, 40-80h+).

---

## Dependencias entre Debitos (Matriz Atualizada)

### Principais Chains

```
CHAIN 1 -- Seguranca (CR-002):
SEC-03 (senha) + SEC-02 (SA JSON) -> SEC-05 (secrets mgmt) -> SEC-06 (threat model)

CHAIN 2 -- Pipeline de Oportunidade:
DT-03 (renumerar) -> DT-16 (baseline) -> DT-02 (v3) -> UX-09 (coverage) + TQ-03 (schema tests)

CHAIN 3 -- Monitor.py Refactor:
TQ-04 (integration tests) -> TD-010 (refactor) -> TD-027 (matching) -> DT-01 (match_logging) -> DT-14 (coverage rec)

CHAIN 4 -- CI/CD Pipeline:
TQ-02 (coverage gate) -> TD-028 (CI/CD) -> TD-024 (test DB gate) + TD-034 (environments)

CHAIN 5 -- Database Performance:
DT-05 (contracts upsert) -> DT-04 (bids upsert) -> DT-22 (retention policy)

CHAIN 6 -- UX CLI Standardization:
UX-03 (rich migration) -> UX-04 (table), UX-05 (exit), UX-06 (flags), UX-08 (errors),
                             UX-11 (hyperlinks), UX-12 (validation), UX-15 (format)

CHAIN 7 -- Web UI (estrategico):
TD-025 (ORM) + TD-028 (CI/CD) -> UX-01 (Web UI)
```

### Ciclos
Nenhum ciclo de dependencia identificado. A ordem topologica e viavel.

### Bloqueios Potenciais

1. **TQ-04 antes de TD-010:** Sem testes de integracao, refatorar monitor.py e risco alto. TQ-04 precisa ser executado primeiro ou em paralelo.
2. **SEC-03 antes de qualquer deploy:** Se a senha for de producao, qualquer deploy expoe a senha. SEC-03 e P0 por este motivo.
3. **DT-02 depende de validacao pos-migration:** Rollback script precisa ser testado antes da execucao.
4. **UX-03 nao pode ser ignorado:** Embora UX-02 e UX-04 tenham prioridade maior, UX-03 (migrar para rich) desbloqueia 7 outros debitos UX. Recomenda-se comecar UX-03 no Sprint 2.

---

## Riscos e Mitigacoes

### Riscos Identificados

| # | Risco | Areas Afetadas | Probabilidade | Impacto | Mitigacao |
|---|-------|---------------|---------------|---------|-----------|
| CR-001 | Refatoracao do monitor.py (TD-010) quebrar crawlers em producao | Sistema, Database | ALTA | CRITICO | (1) TQ-04 primeiro. (2) Branch separada. (3) Execucao paralela por 1 semana. (4) Rollback plan. |
| CR-002 | Exposicao composta de credenciais (DT-07 + TD-029) | Seguranca, Sistema | ALTA | CRITICO | (1) SEC-03, SEC-02 como P0. (2) BFG cleanup imediato. (3) Rotacionar senhas. (4) Auditoria de acessos. |
| CR-003 | DT-02 (v3 migration) sem rollback testado | Database, Sistema | MEDIA | ALTO | (1) Dry-run em copia do banco real. (2) Rollback script testado. (3) Feature flag. |
| CR-004 | UX-01 bloqueado por TD-025 + TD-028 sem cronograma | Frontend/UX, Sistema | ALTA | MEDIO | Definir marco "Web UI desbloqueada" com datas. Alternativa: SQL raw com dataclasses. |
| CR-005 | Sprint 0 com 3 areas diferentes sem coordenacao | Multiplas | MEDIA | MEDIO | Sequenciar: Semana 1 = SEC + TD-001 + UX-02. Semana 2 = DT-02 + TQ-04. Semana 3+ = TD-010. |
| CR-006 | TD-010 com estimativa subestimada (8h -> 20h) | Sistema | ALTA | MEDIO | Dividir em sub-debitos: (a) entity matching 8h, (b) coverage 6h, (c) helpers 4h, (d) cleanup 4h. |
| CR-007 | DT-07 (senha) pode ser de producao -- severidade CRITICAL | Seguranca | MEDIA | CRITICO | Verificar com operador. Se for de producao: rotacao imediata, BFG, auditoria completa. |

---

## Criterios de Sucesso

### Metricas Pos-Resolucao

| Metrica | Baseline (pre) | Alvo (pos) | Ferramenta |
|---------|---------------|------------|------------|
| Cobertura de codigo (total) | Nao medida | >= 75% | pytest --cov |
| Cobertura: scripts/crawl/ | Nao medida | >= 60% | pytest --cov=crawl |
| Cobertura: scripts/opportunity_intel/ | Nao medida | >= 60% | pytest --cov=opportunity_intel |
| Erros de lint (ruff) | Nao medida | 0 (zero) | ruff check |
| Erros de type check (mypy) | Nao medida | 0 (zero) | mypy |
| Linhas do monitor.py | 1756 | < 800 | wc -l |
| Senhas no git history | 2+ (DT-07, TD-029) | 0 (zero) | trufflehog ou git leaks |
| Duplicacao de entity matching | 2 implementacoes | 1 (unificada) | grep -r "match_entities" |
| Debitos P0/P1 abertos | 27 | Decrescente (zero em 3 meses) | Issue tracker |
| Testes de integracao passando | Nao definido | 100% | pytest -m integration |
| Progress indicators | 0 comandos | 3 comandos (update, radar, report) | Checklist |
| Radars com summary | 0% | 100% | Checklist |

### Criterios de Aceite por Debito P0/P1

| ID | Criterio de Aceite | Tipo de Validacao |
|----|-------------------|-------------------|
| SEC-03 | Zero senhas em texto puro no repo. BFG cleanup executado. Conexao funciona via DATABASE_URL de env var. | Automatizado + revisao |
| SEC-02 | SA JSON removido do repo. Workload Identity Federation configurado. | Automatizado |
| TD-001 | BidsCrawler executa sem erro de import em ambiente limpo. | Teste automatizado |
| SEC-01 | Todas as f-strings em queries SQL substituidas por query parameters. | Code review + ruff rule |
| DT-02 | 10 tabelas, 6 views, 4 funcoes existem. opportunity_intel funciona. Zero alteracao em tabelas existentes. | Teste de schema automatizado |
| TQ-04 | Suite de testes de integracao passa. Cobertura >= 50% em scripts/crawl/. | pytest --cov=crawl |
| UX-02 | rich.progress.Progress visivel nos 3 comandos. < 1s de overhead. | Teste CLI + inspecao |
| TD-010 | monitor.py < 1000 linhas. Zero regressao. Output de crawl identico. | Teste comparativo |
| DT-05 | Set-based upsert leva <= 30% do tempo do row-by-row. Triggers intactos. | Teste performance + equivalencia |
| UX-04 | Nenhuma coluna truncada em < 60 chars. rich.Table implementado. | Revisao de codigo |
| UX-08+16 | 100% dos erros tem [ERROR] + sugestao. Traceback com --debug only. | grep + checklist |
| TQ-01 | Migration executada N vezes sem erro (idempotente). | Teste automatizado |
| TQ-02 | CI/CD bloqueia PR com coverage < 60%. | CI gate |
| TQ-03 | schema.py e calculator.py tem testes passando. | pytest --cov |
| DT-01 | Colunas match_logging existem. Migration idempotente. Selects existentes funcionam. | Teste de schema |
| TD-028 | GitHub Actions < 5 min. PR com fail em quality gate bloqueado. | CI pipeline |

---

## Sumario de Mudancas do DRAFT (v1.0, 2026-07-11) para FINAL (v2.0, 2026-07-13)

| Aspecto | DRAFT v1.0 | FINAL v2.0 | Fonte da Mudanca |
|---------|------------|------------|------------------|
| Debitos de Sistema | 16 items | 29 items | TD-010 revisado (8->20h), 5 movidos, 4 novos (GAPs 003-006) |
| Debitos de Database | 18 items | 22 items | Dara: +6 novos, -1 duplicata (DT-17), severidades ajustadas |
| Debitos de Frontend/UX | 0 (nao coberto) | 17 items | Uma: cobertura UX adicionada (12 validados + 5 novos) |
| Debitos de Seguranca | 1 (TD-SEC-02) | 6 items | QA GAP-001: categoria criada, 3 extraidos + 3 novos |
| Debitos de Testes/QA | 1 (TD-SYS-009) | 5 items | QA GAP-002: categoria criada, 3 extraidos + 2 novos |
| **Total** | **38 items, ~140-170h** | **79 items, ~353.5h** | +41 items, cobertura muito mais ampla |
| TD-010 (monitor.py) | 8h | 20h | QA GAP-008: estimativa revisada |
| TD-025 (ORM) | INFORMATIVO (removido) | 20h+ (com nota) | Reconsiderado como debito arquitetural |
| UX-01 (Web UI) | Nao coberto | 80h+ / 40h MVP | Uma: proposta FastAPI+HTMX adicionada |
| DT-07 / TD-029 | MEDIUM / -- | HIGH elevado P0 | QA CR-002: exposicao composta de credenciais |
| Riscos identificados | 3 | 7 | QA: CR-001 a CR-007 |
| Cobertura de areas | 60% | 85% | QA GAPs enderecados |

---

## Referencias

- `docs/architecture/system-architecture.md` -- Fase 1 do Brownfield Discovery
- `supabase/docs/DB-AUDIT.md` -- Fase 2 do Brownfield Discovery
- `docs/frontend/frontend-spec.md` -- Fase 3 do Brownfield Discovery
- `docs/prd/technical-debt-DRAFT.md` -- DRAFT original (v1.0)
- `docs/reviews/db-specialist-review.md` -- Revisao de Dara (@data-engineer, 2026-07-13)
- `docs/reviews/ux-specialist-review.md` -- Revisao de Uma (@ux-design-expert, 2026-07-13)
- `docs/reviews/qa-review.md` -- Revisao de Quinn (@qa, 2026-07-13)
- `docs/reviews/qa-review.md` -- QA Gate (Fase 7) com gaps e recomendacoes
- `.aiox/gotchas.json` -- Registro de riscos operacionais conhecidos

---

*Documento final gerado por Aria (Visionary Architect) em 2026-07-13.*
*Status: COMPLETO -- 79 debitos, 5 categorias, ~353.5h estimadas, 7 riscos mapeados.*
*Proxima etapa: Aprovacao pelo @pm (Morgan) para geracao de epics e stories de desenvolvimento.*
