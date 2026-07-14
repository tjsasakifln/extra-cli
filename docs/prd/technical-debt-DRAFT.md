# Technical Debt Assessment — DRAFT

## Para Revisao dos Especialistas

**Gerado em:** 2026-07-13
**Origem:** Brownfield Discovery — Fase 4: Consolidacao dos Debites (Fases 1-3)
**Autor:** Aria (Visionary Architect)
**Versao:** v2.0 (DRAFT consolidado Phases 1-3, incluindo Frontend/UX)

---

## 1. Debites de Sistema

Fonte: `docs/architecture/system-architecture.md` (Fase 1)
Total: 30 debites identificados

### CRITICAL

| ID | Description | Localizacao | Impacto | Esforco (h) |
|----|-------------|-------------|---------|-------------|
| TD-001 | Imports quebrados para `ingestion/` package inexistente | `scripts/crawl/bids_crawler.py` | Crawl BidsCrawler nao executa sem criar diretorio | 2h |
| TD-010 | `monitor.py` com ~1756 linhas, acopla orquestracao + entity matching + coverage | `monitor.py` | Violacao SRP, dificil testar, manutencao cara | 8h |

### HIGH

| ID | Description | Localizacao | Impacto | Esforco (h) |
|----|-------------|-------------|---------|-------------|
| TD-003 | Type hints ausentes em funcao de 341 linhas | `monitor.py:_match_entities_cascade` | Dificuldade de manutencao, sem verificacao estatica | 4h |
| TD-011 | Duas implementacoes de crawler PNCP (sync adapter + async BidsCrawler) | `pncp_crawler_adapter.py` + `bids_crawler.py` | Duas implementacoes para mesma fonte, risco de divergencia | 6h |
| TD-016 | SQL queries concatenadas com f-strings | `monitor.py` (linhas 67-68) | Risco teorico de SQL injection | 3h |
| TD-019 | Import quebrado para `lib.cli_validation` (path relativo) | `intel_pipeline.py:740` | Falha se PYTHONPATH nao configurado | 1h |
| TD-021 | PNCP `BASE_URL` divergente: settings.py usa v3, .env.example usa v1 | `config/settings.py` vs `.env.example` | Inconsistencia de versao de API | 0.5h |
| TD-027 | `_match_entities_cascade()` duplicada entre `monitor.py` e `matching/entity_matcher.py` | `monitor.py` + `matching/entity_matcher.py` | Logica duplicada, bugs por divergencia | 4h |
| TD-028 | Sem CI/CD automatizado (GitHub Actions) | N/A | Sem pipeline de build/test/deploy | 6h |

### MEDIUM

| ID | Description | Localizacao | Impacto | Esforco (h) |
|----|-------------|-------------|---------|-------------|
| TD-002 | `DEFAULT_DSN` duplicado entre settings.py e monitor.py | `monitor.py` vs `config/settings.py` | Risco de configuracao divergente | 1h |
| TD-004 | Estado global mutavel (cache IBGE module-level) | `enricher.py` | Race condition potencial | 2h |
| TD-008 | Constantes espalhadas vs `config/settings.py` central | `enricher.py` (_BRASILAPI_BASE, etc.) | Duplicacao de config | 3h |
| TD-009 | `supabase_client` importado inline (4 ocorrencias) | `enricher.py` | Performance, violacao PEP 8 | 2h |
| TD-013 | Schema validation ausente nos YAML de config | `config/sectors_config.yaml` | Erro de config silencioso | 4h |
| TD-014 | Sem renovacao automatica de API keys | `settings.py` | Falha quando chave expira | 2h |
| TD-015 | Sem healthcheck unificado | N/A | Nao ha endpoint de saude do sistema | 4h |
| TD-017 | Scripts com hyphen vs underscore duplicados | `scripts/` (ex: `intel-enrich.py` + `intel_enrich.py`) | Confusao de entry points | 4h |
| TD-018 | `backend/` e `config/` duplicam arquivos | `backend/sectors_data.yaml` | Duplicacao de dados (177KB) | 1h |
| TD-020 | `ingestion/transformer.py` e `_base/crawler.py` sao STUBS | `scripts/crawl/ingestion/` | Implementacao adiada indefinidamente | 6h |
| TD-022 | Fallback de DSN hardcoded em varios CLIs | `opportunity_intel/cli.py`, `local_datalake.py` | Risco de conexao acidental | 2h |
| TD-024 | Migrations falham silenciosamente em DB ja migrado | `tests/conftest_db.py` | Erros de migration passam despercebidos | 3h |
| TD-025 | ORM ausente: queries SQL diretas sem abstracao | Todo o projeto | Acoplamento forte ao schema PostgreSQL | 20h+ |
| TD-026 | Testes sem coverage minima definida | `tests/` | Nao ha gate de cobertura minima | 2h |
| TD-029 | Service account JSON no repo | `config/mides-bigquery-sa.json` | Vazamento de credenciais GCP | 1h |
| TD-030 | `opportunity_intel/schema.py` e `coverage/calculator.py` sem testes | `tests/` | Funcionalidades criticas sem cobertura | 4h |

### LOW

| ID | Description | Localizacao | Impacto | Esforco (h) |
|----|-------------|-------------|---------|-------------|
| TD-005 | Subprocess sem controle de output estruturado | `intel_pipeline.py` | Perda de logs estruturados | 2h |
| TD-006 | ANSI color codes manuais com `rich` disponivel | `intel_pipeline.py` | Codigo redundante | 1h |
| TD-007 | `import json` inline no meio de funcao | `monitor.py` | Violacao PEP 8 | 0.5h |
| TD-012 | Fallback silencioso `rapidfuzz` -> `difflib` sem alerta | `monitor.py` | Degradacao silenciosa | 1h |
| TD-023 | Mides BigQuery PULADO sem aviso claro | `.aiox/gotchas.json` | Expectativa falsa de cobertura | 0.5h |

---

## 2. Debites de Database

Fonte: `supabase/docs/DB-AUDIT.md` (Fase 2)
Total: 17 debites identificados

:warning: PENDENTE: Revisao do @data-engineer

### HIGH

| ID | Description | Objeto | Impacto | Esforco |
|----|-------------|--------|---------|---------|
| DT-01 | Colunas match_logging (match_method, match_score, match_confidence) ausentes no schema real | `pncp_raw_bids` | Match cascade sem audit trail. Impossivel depurar falsos positivos. | 2h |
| DT-02 | 10 tabelas v3 nao aplicadas ao banco | Multiplas tabelas | Funcionalidades de oportunidade, engenharia e hierarquia ausentes. | 4h |
| DT-17 | Colunas match_logging definidas em 005-v2 mas ausentes no schema real | 005-v2 migration | Colunas nunca aplicadas ou removidas | 1h |

### MEDIUM

| ID | Description | Objeto | Impacto | Esforco |
|----|-------------|--------|---------|---------|
| DT-03 | Ordem de dependencia v2 incorreta (003 depende de 005) | 003-v2, 005-v2 | Aplicacao fora de ordem quebra | 1h |
| DT-04 | `upsert_pncp_raw_bids` row-by-row | Funcao SQL | Loop PL/pgSQL ~5-10x mais lento que set-based | 4h |
| DT-05 | `upsert_pncp_supplier_contracts` row-by-row | Funcao SQL | Mesmo problema, aplicado a tabela de 3.7M registros | 4h |
| DT-06 | Sem UNIQUE constraint em `sc_public_entities.cnpj_8` | `sc_public_entities` | Permite duplicatas de CNPJ raiz | 1h |
| DT-07 | Senha hardcoded em `config/settings.py` | `config/settings.py` | Credencial em texto puro no git | 1h |
| DT-14 | Nao ha coverage reconciliation periodica | `entity_coverage` | Bulk operations que bypassam triggers ficam inconsistentes | 4h |
| DT-16 | GIN index `idx_psc_objeto_trgm` ausente no v2 baseline | `pncp_supplier_contracts` | Divergencia entre migration e banco | 1h |

### LOW

| ID | Description | Objeto | Impacto | Esforco |
|----|-------------|--------|---------|---------|
| DT-08 | Sem CHECK constraint para `esfera_id` | `pncp_raw_bids` | Dominio nao validado | 1h |
| DT-09 | Sem CHECK constraint para `source` | Multiplas tabelas | Fontes invalidas nao rejeitadas | 1h |
| DT-10 | Sem CHECK constraint para `status` em `ingestion_runs` | `ingestion_runs` | Status invalidos sem erro | 1h |
| DT-11 | `search_datalake` com fallback ILIKE sem index de trigram | `pncp_raw_bids` | Full table scan no fallback | 1h |
| DT-12 | Data types inconsistentes (DATE vs TIMESTAMPTZ) | `pncp_raw_bids` | Colunas DATE vs funcoes esperando TIMESTAMPTZ | 1h |
| DT-13 | `ingestion_checkpoints` vazia e sem uso | `ingestion_checkpoints` | Estrutura nunca populada | 1h |
| DT-15 | `content_hash` UNIQUE sem partial para `is_active` | `pncp_raw_bids` | Re-insercao de registro soft-deletado falha | 1h |

---

## 3. Debites de Frontend/UX

Fonte: `docs/frontend/frontend-spec.md` (Fase 3)
Total: 12 debites identificados

:warning: PENDENTE: Revisao do @ux-design-expert

### HIGH

| ID | Description | Impacto | Esforco (h) |
|----|-------------|---------|-------------|
| UX-01 | No web UI — toda interacao requer SSH/VPS access | Limita base de usuarios; sem portal client-facing | 80+ |
| UX-02 | No progress indicators — comandos longos (update, radar, PDF) sem feedback | Usuarios nao sabem se ferramenta esta travada ou progredindo | 8h |

### MEDIUM

| ID | Description | Impacto | Esforco (h) |
|----|-------------|---------|-------------|
| UX-03 | Dual display paradigm — `rich` vs raw `print()` sem componente compartilhado | Qualidade visual inconsistente; duplicacao de codigo | 12h |
| UX-04 | Table truncation em opportunity_intel — `_print_table()` trunca em 20 chars / 10 cols | Usuarios nao conseguem ler dados chave | 4h |
| UX-08 | Empty output on errors — algumas ferramentas nao mostram nada em falha | Usuarios nao sabem o que deu errado | 3h |
| UX-09 | Coverage dashboard duplicado em opportunity_intel e local_datalake CLIs | Duplicacao de codigo; UX diferente | 6h |
| UX-10 | Gerador de relatorio monolitico — `generate-report-b2g.py` com 287KB | Dificil manter; startup lento | 16h |

### LOW

| ID | Description | Impacto | Esforco (h) |
|----|-------------|---------|-------------|
| UX-05 | Exit codes inconsistentes — 0/1 vs 0/1/2 entre ferramentas | Integracoes de monitoring imprevisiveis | 2h |
| UX-06 | Output flags inconsistentes — `--format table|json` vs `--json` boolean | Carga cognitiva ao alternar ferramentas | 2h |
| UX-07 | No pagination para grandes result sets (500+ linhas) | Overflow de terminal | 6h |
| UX-11 | No terminal hyperlinks — URLs impressas como texto puro | Usuarios nao abrem paginas PNCP rapidamente | 2h |
| UX-12 | No input validation messages — args validados so na query DB | Erros SQL em vez de mensagens amigaveis | 4h |

---

## 4. Matriz Preliminar Consolidada

| ID | Debito | Area | Severidade | Esforco (h) | Prioridade |
|----|--------|------|------------|-------------|------------|
| TD-010 | monitor.py com 1756 linhas (SRP violation) | Sistema | CRITICAL | 8h | P0 |
| TD-001 | Imports quebrados para ingestion/ package | Sistema | CRITICAL | 2h | P0 |
| DT-02 | 10 tabelas v3 nao aplicadas ao banco | Database | HIGH | 4h | P0 |
| UX-02 | No progress indicators — comandos longos sem feedback | Frontend/UX | HIGH | 8h | P0 |
| TD-028 | Sem CI/CD automatizado (GitHub Actions) | Sistema | HIGH | 6h | P1 |
| TD-027 | Entity matching duplicado (monitor.py + entity_matcher.py) | Sistema | HIGH | 4h | P1 |
| TD-011 | Duas implementacoes de crawler PNCP | Sistema | HIGH | 6h | P1 |
| TD-016 | SQL queries com f-strings (risco SQL injection) | Sistema | HIGH | 3h | P1 |
| TD-019 | Import quebrado lib.cli_validation | Sistema | HIGH | 1h | P1 |
| TD-003 | Type hints ausentes em funcao de 341 linhas | Sistema | HIGH | 4h | P1 |
| TD-021 | PNCP BASE_URL divergente (v3 vs v1) | Sistema | HIGH | 0.5h | P1 |
| DT-01 | Colunas match_logging ausentes no schema real | Database | HIGH | 2h | P1 |
| DT-17 | Colunas match_logging em migration mas ausentes no banco | Database | HIGH | 1h | P1 |
| UX-04 | Table truncation em opportunity_intel (20 chars) | Frontend/UX | MEDIUM | 4h | P1 |
| UX-08 | Empty output on errors | Frontend/UX | MEDIUM | 3h | P1 |
| TD-025 | ORM ausente: queries SQL diretas sem abstracao | Sistema | MEDIUM | 20h+ | P2 |
| TD-020 | ingestion/transformer.py e _base/crawler.py sao STUBS | Sistema | MEDIUM | 6h | P2 |
| TD-017 | Scripts hyphen + underscore duplicados | Sistema | MEDIUM | 4h | P2 |
| TD-013 | Schema validation ausente nos YAML de config | Sistema | MEDIUM | 4h | P2 |
| TD-015 | Sem healthcheck unificado | Sistema | MEDIUM | 4h | P2 |
| TD-024 | Migrations falham silenciosamente em DB ja migrado | Sistema | MEDIUM | 3h | P2 |
| TD-008 | Constantes espalhadas vs settings.py central | Sistema | MEDIUM | 3h | P2 |
| TD-004 | Estado global mutavel (cache IBGE module-level) | Sistema | MEDIUM | 2h | P2 |
| TD-009 | supabase_client importado inline (4 ocorrencias) | Sistema | MEDIUM | 2h | P2 |
| TD-014 | Sem renovacao automatica de API keys | Sistema | MEDIUM | 2h | P2 |
| TD-022 | Fallback de DSN hardcoded em varios CLIs | Sistema | MEDIUM | 2h | P2 |
| TD-026 | Testes sem coverage minima definida | Sistema | MEDIUM | 2h | P2 |
| TD-002 | DEFAULT_DSN duplicado (monitor.py vs settings.py) | Sistema | MEDIUM | 1h | P2 |
| TD-018 | backend/ e config/ duplicam arquivos | Sistema | MEDIUM | 1h | P2 |
| TD-029 | Service account JSON no repo | Sistema | MEDIUM | 1h | P2 |
| TD-030 | schema.py e calculator.py sem testes | Sistema | MEDIUM | 4h | P2 |
| DT-04 | upsert_pncp_raw_bids row-by-row | Database | MEDIUM | 4h | P2 |
| DT-05 | upsert_pncp_supplier_contracts row-by-row | Database | MEDIUM | 4h | P2 |
| DT-14 | Nao ha coverage reconciliation periodica | Database | MEDIUM | 4h | P2 |
| DT-03 | Ordem de dependencia v2 incorreta | Database | MEDIUM | 1h | P2 |
| DT-06 | Sem UNIQUE constraint em sc_public_entities.cnpj_8 | Database | MEDIUM | 1h | P2 |
| DT-07 | Senha hardcoded em config/settings.py | Database | MEDIUM | 1h | P2 |
| DT-16 | GIN index trigram ausente no v2 baseline | Database | MEDIUM | 1h | P2 |
| UX-03 | Dual display paradigm — rich vs raw print() | Frontend/UX | MEDIUM | 12h | P2 |
| UX-09 | Coverage dashboard duplicado em dois CLIs | Frontend/UX | MEDIUM | 6h | P2 |
| UX-10 | Gerador de relatorio monolitico (287KB) | Frontend/UX | MEDIUM | 16h | P2 |
| UX-01 | No web UI — toda interacao requer SSH/VPS | Frontend/UX | HIGH | 80h+ | P3 |
| TD-005 | Subprocess sem controle de output estruturado | Sistema | LOW | 2h | P3 |
| TD-006 | ANSI color codes manuais com rich disponivel | Sistema | LOW | 1h | P3 |
| TD-012 | Fallback silencioso rapidfuzz -> difflib | Sistema | LOW | 1h | P3 |
| TD-007 | import json inline no meio de funcao | Sistema | LOW | 0.5h | P3 |
| TD-023 | Mides BigQuery PULADO sem aviso claro | Sistema | LOW | 0.5h | P3 |
| DT-08 | Sem CHECK constraint para esfera_id | Database | LOW | 1h | P3 |
| DT-09 | Sem CHECK constraint para source | Database | LOW | 1h | P3 |
| DT-10 | Sem CHECK constraint para status | Database | LOW | 1h | P3 |
| DT-11 | Fallback ILIKE sem index de trigram | Database | LOW | 1h | P3 |
| DT-12 | Data types inconsistentes DATE vs TIMESTAMPTZ | Database | LOW | 1h | P3 |
| DT-13 | ingestion_checkpoints vazia e sem uso | Database | LOW | 1h | P3 |
| DT-15 | content_hash UNIQUE sem partial para is_active | Database | LOW | 1h | P3 |
| UX-07 | No pagination para grandes result sets | Frontend/UX | LOW | 6h | P3 |
| UX-05 | Exit codes inconsistentes entre ferramentas | Frontend/UX | LOW | 2h | P3 |
| UX-06 | Output flags inconsistentes | Frontend/UX | LOW | 2h | P3 |
| UX-11 | No terminal hyperlinks | Frontend/UX | LOW | 2h | P3 |
| UX-12 | No input validation messages | Frontend/UX | LOW | 4h | P3 |

---

## 5. Perguntas para Especialistas

### @data-engineer (Dara):

1. **Estado real das colunas match_logging (DT-01/DT-17):** As colunas `match_method`, `match_score`, `match_confidence` estao presentes no schema real de producao, ou a migration 005-v2 ainda nao foi aplicada?

2. **Status da migration 006-v3 (DT-02):** As 10 tabelas v3 foram aplicadas ao banco de producao? Se sim, qual o estado atual? Se nao, qual o bloqueio?

3. **Volume real e performance (DT-04/DT-05):** Qual o volume atual de `pncp_raw_bids` e `pncp_supplier_contracts`? O loop row-by-row nos upserts ja causa lentidao perceptivel?

4. **ingestion_checkpoints (DT-13):** Tabela vazia nunca populada. Devemos integra-la aos crawlers ou remove-la?

5. **Coverage reconciliation (DT-14):** Qual a frequencia de bulk inserts que bypassam triggers? Precisamos de job periodico de reconciliacao?

6. **UNIQUE em cnpj_8 (DT-06):** Existem duplicatas de CNPJ raiz conhecidas? Adicionar UNIQUE constraint quebraria algo?

7. **Senha hardcoded (DT-07):** A credencial `postgres:smartlic_local` em config/settings.py e usada em producao ou apenas dev local?

8. **Ordem de migrations (DT-03):** 003-v2 referencia match_method que so existe em 005-v2. Como as migrations foram aplicadas sem quebrar?

### @ux-design-expert (Uma):

1. **Unificacao de display paradigm (UX-03):** Migrar TODOS os CLIs para `rich` ou manter dois paradigmas deliberadamente?

2. **Output flag pattern (UX-06):** Padrao recomendado: `--format table|json|csv` ou `--json` booleano?

3. **Exit code strategy (UX-05):** Padronizar em `sys.exit(0/1/2)` como health-dashboard?

4. **Progress indicators (UX-02):** Preferencia: `rich.progress.Progress` (ja disponivel) ou `tqdm`?

5. **Web UI requirement (UX-01):** Requisito real de curto prazo ou estrategico? Qual perfil de usuario e funcionalidades prioritarias?

6. **Coverage consolidation (UX-09):** Consolidar coverage dashboard em unico entry point?

7. **Table component (UX-04):** Criar componente compartilhado `scripts/lib/rich_table.py` para todos os CLIs?

8. **Error handling pattern (UX-08):** Formato padrao `[ERROR] Human-readable message` com ou sem sugestao de acao?

---

## 6. Dependencias Cruzadas Identificadas

### Grupo 1: Monitor.py Refactor (Epicentro)

```
TD-010 (monitor.py 1756 linhas) -> TD-027 (matching duplicado)
                                -> TD-003 (type hints ausentes)
                                -> TD-016 (f-strings SQL)
                                -> TD-007 (import inline)
                                -> TD-012 (fallback silencioso)
```

### Grupo 2: Entity Matching Chain

```
TD-027 (matching duplicado) -> DT-01 (match_logging ausente)
                            -> DT-17 (colunas em migration mas ausentes)
                            -> DT-06 (UNIQUE em cnpj_8)
```

### Grupo 3: Database Schema v3

```
DT-02 (v3 tables nao aplicadas) -> UX-09 (coverage consolidation)
                                -> TD-030 (schema.py sem testes)
```

### Grupo 4: CI/CD Pipeline

```
TD-028 (sem CI/CD) -> TD-024 (test DB gate)
                   -> TD-026 (coverage minima)
                   -> TD-029 (SA JSON no repo)
```

### Grupo 5: Database Performance

```
DT-04 (upsert row-by-row bids) -> impacto em TD-011 (dual crawlers)
                               -> impacto em TD-020 (ingestion stubs)
```

### Grupo 6: UX CLI Standardization

```
UX-03 (dual paradigm rich vs raw) -> UX-04 (table truncation)
                                  -> UX-05 (exit codes)
                                  -> UX-06 (output flags)
                                  -> UX-08 (empty errors)
                                  -> UX-11 (hyperlinks)
                                  -> UX-12 (input validation)
```

### Grupo 7: Longo Prazo / Estrategico

```
UX-01 (web UI) -> depende de TD-025 (ORM) e TD-028 (CI/CD)
```

### Matriz de Dependencias

| Debito | Depende de | Bloqueia |
|--------|------------|----------|
| TD-010 | — | TD-027, TD-003, TD-016, TD-007, TD-012 |
| TD-027 | TD-010 | DT-01, DT-17 |
| DT-06 | — | DT-01, TD-027 |
| DT-02 | — | UX-09, TD-030 |
| TD-028 | — | TD-024, TD-026, TD-029 |
| UX-03 | — | UX-04, UX-05, UX-06, UX-08, UX-11, UX-12 |
| TD-025 | — | UX-01 |
| TD-028 | — | UX-01 |
| TD-011 | — | DT-04 (impacto) |
| TD-020 | — | DT-04 (impacto) |

---

## 7. Resumo Executivo Preliminar

### Distribuicao por Severidade

| Severidade | Sistema | Database | Frontend/UX | Total Geral |
|------------|---------|----------|-------------|-------------|
| CRITICAL | 2 | 0 | 0 | 2 |
| HIGH | 7 | 3 | 2 | 12 |
| MEDIUM | 16 | 7 | 5 | 28 |
| LOW | 5 | 8 | 5 | 18 |
| **Total** | **30** | **18** | **12** | **60** |

### Esforco Total Estimado

| Area | Esforco (h) |
|------|-------------|
| Sistema (TD) | ~84h |
| Database (DT) | ~30h |
| Frontend/UX (UX) excl. UX-01 (web UI) | ~65h |
| **Subtotal (sem web UI)** | **~179h** |
| Web UI (UX-01) | ~80h+ |
| **Total Geral** | **~259h+** |

### Distribuicao por Prioridade

| Prioridade | Qtd | Esforco (h) | Acao Sugerida |
|------------|-----|-------------|---------------|
| P0 — Imediata (CRITICAL + bloqueios) | 4 | 22h | Sprint 0 |
| P1 — Curto Prazo (HIGH + quick wins) | 11 | 37.5h | Sprints 1-2 |
| P2 — Medio Prazo (MEDIUM) | 27 | 112h | Sprints 3-5 |
| P3 — Longo Prazo (LOW + web UI) | 18 | ~88h | Backlog |
| **Total** | **60** | **~259h** | |

### Top 5 Recomendacoes (Ordem de Execucao)

1. **P0: TD-010 (8h)** — Refatorar `monitor.py` (1756 linhas): extrair entity matching, database helpers e coverage reporting para modulos proprios. Desbloqueia 5 outros debitos.

2. **P0: DT-02 (4h)** — Aplicar migration 006-v3 (unified schema) ao banco de producao apos validacao em staging. Desbloqueia opportunity intel e hierarquia.

3. **P0: UX-02 (8h)** — Adicionar `rich.progress.Progress` aos comandos `update`, `radar` e geracao de PDF. Elimina maior dor de UX.

4. **P1: TD-028 (6h)** — Implementar GitHub Actions com ruff, mypy, pytest + `REQUIRE_TEST_DB=1`. Quality gates automaticos.

5. **P1: TD-027 (4h)** — Unificar entity matching: eliminar duplicacao monitor.py vs entity_matcher.py. Pre-requisito para DT-01.

### Principais Riscos

| Risco | Impacto | Mitigacao |
|-------|---------|-----------|
| Migration v3 (DT-02) sem rollback testado | Perda de dados | Testar staging primeiro |
| Refactor monitor.py (TD-010) quebrar crawlers | Crawlers param | Branch separada + testes com dados reais |
| Senha hardcoded (DT-07) exposta em commits | Credencial comprometida | Rotacionar senha, BFG repo |

---

*Documento gerado por Aria (Visionary Architect) em 2026-07-13.*
*Fontes: system-architecture.md (30 debitos), DB-AUDIT.md (18 debitos), frontend-spec.md (12 debitos). Total: 60 debitos.*
*Proxima etapa: Revisao pelos especialistas (@data-engineer, @ux-design-expert).*
