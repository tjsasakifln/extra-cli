# Análise Técnica — Extra Consultoria

> Gerado pelo Archaeologist em 2026-07-11T13:00:00Z
> Projeto: Extra Consultoria — Inteligência em Licitações
> doc_level: completo

---

## Módulo 1: `crawl` — Coleta Multi-Source

**Propósito:** Coleta de licitações e contratos de 8 fontes distintas, normalização para schema unificado, upsert no DataLake e entity matching com órgãos SC.

**Arquivos primários (25):**
- `monitor.py` — Orquestrador central (687 linhas)
- `pncp_crawler_adapter.py` — Adapter PNCP API → schema unificado
- `dom_sc_crawler.py` — DOM-SC (~280 municípios, 3 categorias: contratos, convênios, empenhos)
- `pcp_crawler.py` — PCP v2 (100+ municípios)
- `compras_gov_crawler.py` — ComprasGov v3 (órgãos federais)
- `sc_compras_crawler.py` — SC Compras
- `contracts_crawler.py` — Contratos históricos PNCP
- `transparencia_crawler.py` — Portais de transparência municipais
- `tce_sc_crawler.py` — TCE-SC via SCMWeb JSON API
- `pncp_arp_crawler.py` — Atas de Registro de Preço
- `pncp_pca_crawler.py` — Plano de Contratação Anual
- `enricher.py` — Enriquecimento cadastral (BrasilAPI CNPJ + IBGE)
- `transformer.py` — Normalização de dados multi-source
- `loader.py` — Upsert PostgreSQL
- `adapter.py` — Interface comum de crawler
- Outros: `async_client.py`, `sync_client.py`, `checkpoint.py`, `circuit_breaker.py`, `retry.py`, `config.py`, `sanctions.py`

### Fluxo de Controle

**Pipeline multi-source (monitor.py):**

```
crawl_source(source, mode)
  ├── _load_crawler(source)          # Dynamic import via importlib
  ├── crawler.crawl(mode)            # Coleta da fonte
  ├── crawler.transform(records)     # Normalização
  ├── upsert_pncp_raw_bids(records)  # RPC PostgreSQL
  ├── _match_entities_cascade(conn, source, entities)
  │     ├── Level 1: CNPJ exact match (8-digit base)
  │     ├── Level 2: Normalized name + municipio constraint
  │     └── Level 3: Fuzzy matching (rapidfuzz/difflib)
  └── _finish_ingestion_run()        # Auditoria
```

### Algoritmos

#### Entity Matching Cascade (3 níveis)
🟢 **CONFIRMADO** — `monitor.py:_match_entities_cascade`

Pipeline de matching progressive-fallback:
1. **CNPJ (Level 1):** Extrai base de 8 dígitos do `orgao_cnpj`, busca exata no índice `cnpj_index`. Se 14 dígitos, tenta prefix match. Score fixo 1.0, confidence "high".
2. **Nome normalizado + IBGE (Level 2a):** Normaliza `orgao_razao_social` via `name_normalizer.py`, busca exata no índice `(nome_norm, codigo_ibge)`. Score 1.0, confidence "high".
3. **Nome normalizado (Level 2b):** Fallback sem constraint de município. Score 1.0, confidence "high".
4. **Fuzzy (Level 3):** `rapidfuzz.ratio()` ou `SequenceMatcher.ratio()` (fallback). Filtra candidatos por IBGE se disponível. Threshold configurável (default 0.85). Confidence: >=0.95 "high", >=threshold "medium", <threshold "low".
5. **Unmatched:** Marca `match_method="unmatched"`, `match_score=0.0`.

#### Content Hash Dedup
🟢 **CONFIRMADO** — `transformer.py:compute_content_hash`

SHA-256 de `objeto_compra|valor_total_estimado|situacao_compra` canonicalizado (lowercase + strip). Evita upserts redundantes no PostgreSQL.

#### Coverage Reporting
🟢 **CONFIRMADO** — `monitor.py:report_coverage`

Query SQL que cruza `sc_public_entities` × `entity_coverage` agrupado por `raio_200km`, com breakdown por source e lista de entidades descobertas.

### Estruturas de Dados

| Estrutura | Tipo | Local | Descrição |
|-----------|------|-------|-----------|
| `pncp_raw_bids` | Tabela SQL | db/migrations/001 | Licitações multi-source (FTS PT-BR, 12 índices) |
| `pncp_supplier_contracts` | Tabela SQL | db/migrations/002 | Contratos de fornecedores |
| `enriched_entities` | Tabela SQL | db/migrations/003 | Cache enriquecimento cadastral |
| `sc_public_entities` | Tabela SQL | db/migrations/007 | 2.085 órgãos SC |
| `entity_coverage` | Tabela SQL | db/migrations/009 | Tracking cobertura |
| `ingestion_runs` | Tabela SQL | db/migrations/004 | Auditoria de crawls |
| `ingestion_checkpoints` | Tabela SQL | db/migrations/004 | Crawl resumable |
| `v_unmatched_bids` | View SQL | db/migrations/011 | Bids não matched |

---

## Módulo 2: `intel` — Pipeline de Inteligência

**Propósito:** Pipeline completo de coleta e análise de licitações para um CNPJ alvo, com 5 quality gates entre 7 stages.

**Arquivos primários (10):**
- `intel_pipeline.py` — Orquestrador (600+ linhas)
- `intel_collect.py` — Coleta PNCP + DataLake
- `intel_enrich.py` — Enriquecimento cadastral
- `intel_llm_gate.py` — Gate LLM (GPT-4.1-nano)
- `intel_extract_docs.py` — Extração de documentos
- `intel_analyze.py` — Análise de editais
- `intel_validate.py` — Validação de dados
- `intel_report.py` — Geração de relatório
- `intel_excel.py` — Export Excel estilizado
- `intel_sector_loader.py` — Loader YAML → Python

### Fluxo de Controle

**Pipeline de 7 stages com 5 quality gates:**

```
Stage 1: COLLECT
  ├── intel_collect.py → DataLake + PNCP API
  └── [GATE 1: Cobertura] — >= 80% das entidades no raio?

Stage 2: ENRICH
  ├── intel_enrich.py → BrasilAPI CNPJ + IBGE
  └── [GATE 2: Cadastral] — CNPJ válido? CNAEs batem?

Stage 3: LLM GATE
  ├── intel_llm_gate.py → OpenAI GPT-4.1-nano
  └── [GATE 3: Ruído] — Edital é relevante? Classificação setorial

Stage 4: EXTRACT DOCS
  ├── intel_extract_docs.py → PNCP Files API
  └── [GATE 4: Conteúdo] — Editais contêm keywords de engenharia?

Stage 5: ANALYZE (manual trigger)
  └── intel_analyze.py → OpenAI análise detalhada

Stage 6: VALIDATE
  ├── intel_validate.py
  └── [GATE 5: Recomendação] — Score > threshold?

Stage 7: REPORT
  ├── intel_report.py → PDF (ReportLab)
  └── intel_excel.py → Excel (openpyxl)
```

### Algoritmos

#### Classificação Setorial (LLM Gate)
🟡 **INFERIDO** — `intel_llm_gate.py`

Usa GPT-4.1-nano com prompt template que classifica o edital como SIM/NAO para o setor da empresa. Fallback = REJECT (zero noise philosophy). Threshold de confiança configurável (default 0.40).

#### Weight Profiles por Setor
🟢 **CONFIRMADO** — `config/sectors_config.yaml`

Cada setor tem `weight_profile` com 5 dimensões:
- `hab` (habilitação): 0.15-0.30
- `fin` (financeiro): 0.15-0.30
- `geo` (geográfico): 0.05-0.25
- `prazo` (timeline): 0.15-0.25
- `comp` (competitivo): 0.05-0.40

---

## Módulo 3: `reports` — Relatórios

**Propósito:** Geração de relatórios analíticos sobre o mercado de licitações.

**Arquivos primários (4):**
- `panorama.py` — Panorama de mercado setorial
- `coverage_gaps.py` — Detecção de gaps de cobertura
- `coverage_weekly.py` — Relatório semanal de cobertura

### Fluxo de Controle

**Panorama de Mercado:**
```
panorama.py
  ├── section_volume()     # Volume e valor por modalidade
  ├── section_municipios() # Top municípios por contagem
  ├── section_sazonalidade() # Heatmap mensal
  ├── section_concorrencia() # Top fornecedores
  ├── section_setores()    # Breakdown por setor
  ├── → Terminal (Rich table)
  ├── → Excel (openpyxl)
  └── → PDF (ReportLab)
```

---

## Módulo 4: `lib` — Bibliotecas Compartilhadas

**Propósito:** Funções reutilizáveis de domínio — normalização, simulação, estimativa, tracking.

**Arquivos primários (11):**
- `name_normalizer.py` — Normalização de nomes PT-BR (acentos, abreviações)
- `bid_simulator.py` — Simulador de lance ótimo
- `cost_estimator.py` — Estimativa de custos
- `victory_profile.py` — Perfil de vitória (aprendizado de padrões)
- `win_loss_tracker.py` — Tracking de win/loss
- `doc_templates.py` — Templates de documentos
- `constants.py` — Constantes do projeto
- `intel_logging.py` — Logging estruturado
- `cli_validation.py` — Validação CLI
- `retry.py` — Retry decorator

### Algoritmos

#### Name Normalizer (7-step pipeline)
🟢 **CONFIRMADO** — `name_normalizer.py:normalize_name`

```
1. NFKD normalize (remove acentos)
2. Uppercase
3. Remove pontuação (mantém espaços)
4. Remove números CNPJ soltos (8-14 dígitos)
5. Collapse whitespace
6. Expande abreviações (SEC → SECRETARIA, MUN → MUNICIPIO, etc.)
7. Remove termos irrelevantes (opcional)
```

Dicionário de 18 abreviações da administração pública brasileira.

#### Bid Simulator
🟢 **CONFIRMADO** — `bid_simulator.py:simulate_bid`

Calcula lance ótimo maximizando `P(vitória) × margem_líquida`. Usa:
- Distribuição de descontos históricos do órgão
- HHI (Herfindahl-Hirschman Index) → número esperado de concorrentes
- Margem mínima do setor (5 perfis: engenharia_obras, ti_software, consultoria, avaliacao, default)
- Valor estimado do edital
- Output: lance sugerido, agressivo, conservador + EV (expected value)

#### Victory Profile
🟢 **CONFIRMADO** — `victory_profile.py:build_victory_profile`

Aprende padrões de sucesso de contratos ganhos:
- Faixa de valor (média, std, quartis)
- Modalidades preferidas (frequência normalizada)
- Porte de município (5 faixas populacionais)
- Keywords recorrentes (frequência em contratos ganhos)
- Proximidade geográfica (distância média, máxima)
- Output: `score_edital_fit()` → 0.0-1.0

---

## Módulo 5: `config` — Configuração

**Propósito:** Configuração centralizada do projeto (12-factor, env vars + YAML).

**Arquivos primários (5):**
- `settings.py` — Settings from env vars (122 linhas)
- `sectors_config.yaml` — 13 setores com CNAEs e heurísticas (2.116 linhas)
- `sectors_data.yaml` — Dados complementares
- `abbreviations.yaml` — Abreviações PT-BR
- `transparencia_config.yaml` — Config de portais de transparência

### Estrutura de Configuração

**Sectors Config (13 setores):**
1. `engenharia` — Construção civil (17 CNAEs, 260+ padrões)
2. `engenharia_rodoviaria` — Rodovias (2 CNAEs)
3. `manutencao_predial` — Manutenção predial (4 CNAEs)
4. `vestuario` — Uniformes (12 CNAEs)
5. `alimentos` — Alimentos e merenda (15 CNAEs)
6. `informatica` — Hardware (7 CNAEs)
7. `software` — TI e serviços (8 CNAEs)
8. `facilities` — Limpeza e facilities (8 CNAEs)
9. `vigilancia` — Segurança (4 CNAEs)
10. `saude` — Saúde e medicamentos (14 CNAEs)
11. `transporte` — Veículos e combustíveis (14 CNAEs)
12. `mobiliario` — Mobiliário (6 CNAEs)
13. `papelaria` — Papelaria (6 CNAEs)
14. `materiais_eletricos` — Materiais elétricos (6 CNAEs)
15. `materiais_hidraulicos` — Materiais hidráulicos (6 CNAEs)

Cada setor define: `cnae_prefixes`, `sector_hints`, `heuristic_patterns` (strong_compat, strong_incompat, weak_compat), `cross_sector_exclusions`, `competition_keywords`, `weight_profile`, `base_win_rate`, `habilitacao` (capital mínimo, atestados, certificações), `timeline_rules`, `priority_modalidades`, `cnae_gate_threshold`.

---

## Módulo 6: `db` — Database

**Propósito:** Schema, migrations, seed data e setup do PostgreSQL.

**Arquivos primários (15):**
- 12 migrations SQL (001 a 012)
- 3 seed scripts Python (001_sc_entities.py, seed_sc_entities.py, __init__.py)
- `setup_db.sh`

### Schema Core

| Tabela | Colunas principais | Índices | Descrição |
|--------|-------------------|---------|-----------|
| `pncp_raw_bids` | pncp_id, objeto_compra, valor_total_estimado, modalidade_id/nome, esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social, orgao_cnpj, data_publicacao/abertura/encerramento, link_pncp, content_hash, tsv (TSVECTOR), source, source_id, matched_entity_id, ingested_at, updated_at, is_active | 12 (GIN FTS, B-tree) | Licitações unificadas |
| `pncp_supplier_contracts` | supplier_cnpj, supplier_name, contract_value, contract_date, orgao, uf, municipio, modalidade | 6 | Histórico de contratos |
| `enriched_entities` | cnpj, razao_social, cnae_principal, cnae_secundarios, municipio, uf, natureza_juridica, entity_type, enriched_at | 4 | Cache enriquecimento |
| `sc_public_entities` | id, razao_social, cnpj_8, municipio, codigo_ibge, natureza_juridica, raio_200km, is_active | 5 | 2.085 órgãos SC |
| `entity_coverage` | entity_id, source, is_covered, within_200km, last_seen_at | 3 | Tracking cobertura |
| `ingestion_runs` | id, source, status, records_fetched/upserted, entities_covered, started_at, finished_at, error_message | 3 | Auditoria crawls |
| `ingestion_checkpoints` | source, last_crawl_at, last_pncp_id, mode, cursor_data (JSONB) | 2 | Crawl resumable |
| `coverage_snapshots` | snapshot_date, total_entities, covered_entities, coverage_pct, uncovered_within_200km, by_source (JSONB) | 1 | Snapshots históricos |

### RPCs (Stored Procedures)

| RPC | Migration | Descrição |
|-----|-----------|-----------|
| `upsert_pncp_raw_bids(jsonb)` | 006 | Upsert otimizado de batch |
| `search_datalake(query, uf, dias, limite)` | 005 | Full-text search PT-BR |
| `purge_old_records()` | 008 | Limpeza de registros antigos |

---

## Módulo 7: `deploy` — Deployment

**Propósito:** Instalação e operação no Hetzner VPS via systemd.

**Arquivos primários (28):**
- `install.sh` — Script de instalação
- 13 systemd `.service` files
- 13 systemd `.timer` files
- 1 systemd `onfailure@.service` template

### Systemd Timers

| Timer | Schedule UTC | Descrição |
|-------|-------------|-----------|
| `pncp-crawl-full.timer` | Diário 05:00 | Crawl completo PNCP |
| `pncp-crawl-inc.timer` | 11:00, 17:00, 23:00 | Crawl incremental PNCP |
| `dom-sc-crawl.timer` | 06:00, 14:00, 22:00 | DOM-SC (~280 municípios) |
| `pcp-crawl.timer` | Diário 08:00 | PCP v2 |
| `compras-gov-crawl.timer` | Diário 10:00 | ComprasGov v3 |
| `pncp-contracts.timer` | Diário 07:00 | Contratos PNCP |
| `pncp-enrich.timer` | Diário 08:00 | Enriquecimento cadastral |
| `pncp-purge.timer` | Diário 04:00 | Limpeza registros antigos |
| `coverage-report.timer` | Diário 09:00 | Relatório cobertura |
| `coverage-report-weekly.timer` | Seg 07:00 | Relatório semanal |
| `pncp-report-weekly.timer` | Seg 07:00 | Relatório semanal PNCP |
| `tce-sc-crawl.timer` | Diário 12:00 | TCE-SC ESFINGE |
| `transparencia-crawl.timer` | Diário 13:00 | Portais transparência |

Template `onfailure@.service` — notificação de falha para qualquer serviço.

---

## Módulo 8: `docs` — Documentação

**Propósito:** Documentação técnica, de produto e de processo.

**Arquivos primários (15+):**
- `architecture/architecture.md` — C4 (Contexto + Containers), schema, fluxo de dados, decisões
- `prd/PRD-consultoria-extra.md` — PRD completo (visão, features MoSCoW, fontes, métricas)
- `stories/epics/epic-001-100-cobertura/` — 7 stories + INDEX
- `qa/gates/` — 7 QA gates executados
- `research/2026-07-10-tce-sc-esfinge/` — Pesquisa técnica
- `guides/hetzner-supabase-plan.md` — Guia de infra
- `sessions/2026-07/` — Handoffs de sessão

---

## Resumo de Complexidade

| Módulo | Arquivos | LOC | Complexidade | Algoritmos chave |
|--------|----------|-----|--------------|------------------|
| crawl | 25 | ~20.000 | HIGH | Entity matching 3-level cascade, content hash dedup |
| intel | 10 | ~15.000 | HIGH | 7-stage pipeline, LLM classification, sector weights |
| reports | 4 | ~3.000 | MEDIUM | SQL aggregation, PDF/Excel generation |
| lib | 11 | ~5.000 | MEDIUM | Name normalization, bid simulation, victory profiling |
| config | 5 | ~2.100 (YAML) | LOW | YAML-driven sector configuration |
| db | 15 | ~1.800 | MEDIUM | FTS PT-BR, upsert RPC, cascade matching |
| deploy | 28 | ~500 | LOW | systemd orchestration |
| docs | 15+ | — (Markdown) | LOW | Documentation |
| **TOTAL** | **113+** | **~50.600** | — | — |
