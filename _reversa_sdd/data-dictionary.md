# Dicionário de Dados — Extra Consultoria

> 🟢 **CONFIRMADO** onde há migration/código; 🟡 **INFERIDO** onde só há uso sem DDL lido linha a linha  
> Re-extração 2026-07-17 | Migrations 001–054 (59 arquivos)

---

## 1. Entidades canônicas de domínio (código)

### 1.1 SourceInfo (`scripts/crawl/registry.py`)

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|:-----------:|-----------|
| name | str | sim | Nome canônico underscore |
| aliases | list[str] | não | Sinônimos (hífen/underscore) |
| module | str | sim | Módulo em `scripts.crawl.*` |
| purpose | Literal | sim | bids / contracts / coverage_only / hybrid |
| capabilities | list | não | open_tenders, historical_contracts, competitors, prices, entity_matching, coverage_truth, source_health |
| authority_level | Literal | não | federal / estadual / municipal / multi |
| entity_types | list | não | Tipos de entidade aplicáveis |
| credential_names | list | não | Credenciais necessárias |
| snapshot_semantics | Literal | não | full_refresh / incremental / append_only / coverage_only |
| freshness_sla_hours | int | não | SLA de frescor |
| supports_pagination | bool | não | Paginação |
| supports_zero_proof | bool | não | Aceita success_zero |
| reconciliation_strategy | str | não | Estratégia de reconciliação |
| is_contract_source | bool | não | True se fonte de contratos (≠ bids) |

### 1.2 EntitySourceRecord (`source_registry/models.py` + migration 053)

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|:-----------:|-----------|
| canonical_id | TEXT | sim | ID estável da entidade |
| razao_social | TEXT | sim | Nome legal |
| nome_fantasia | TEXT | não | Nome fantasia |
| cnpj | TEXT | sim | 14 ou 8 dígitos |
| natureza_juridica / entity_type | TEXT | sim | Tipo (generated AS natureza) |
| municipio, uf, ibge_code | TEXT | parcial | Localização |
| lat, lon, distance_km | float | não | Geo / raio 200km |
| portal_institucional / transparencia / licitacoes / diario_oficial | TEXT | não | URLs |
| plataformas | TEXT[] | sim default {} | Plataformas detectadas |
| external_ids | JSONB | sim default {} | IDs externos |
| url_patterns | JSONB | sim default {} | Padrões de URL |
| integration_type | TEXT | sim | api_json, html, pdf, js, ckan, rss, shared_portal, unknown |
| access_status | TEXT | sim | mapped…operational…blocked… |
| last_success_at / last_attempt_at | TIMESTAMPTZ | não | Timestamps |
| sla_hours | INT | não | SLA |
| collection_strategy | TEXT | sim | Estratégia de coleta |
| current_blocker | TEXT | não | Bloqueador atual |
| next_action | TEXT | sim | Próxima ação |
| priority | INT 1–10 | sim default 5 | Prioridade |
| mapping_confidence | float 0–1 | sim | Confiança do mapeamento |
| evidences | JSONB | sim | Evidências |

### 1.3 Official acts (migration 052)

#### official_act_resources

| Campo | Tipo | Notas |
|-------|------|-------|
| source | TEXT | ciga_ckan, doe_sc, dom_sc, … |
| resource_id / package_id / package_name | TEXT | identidade do recurso |
| resource_url, format | TEXT | origem |
| content_sha256, etag, last_modified, size_bytes | * | integridade |
| run_id | TEXT | soft ref pipeline_runs |
| fetch_status | TEXT | discovered\|fetched\|parsed\|failed\|stale |
| metadata | JSONB | livre |

#### official_acts (resumo)

| Conceito | Campos-chave |
|----------|--------------|
| Identidade | source, external_id, record_hash |
| Conteúdo | title, raw_json, raw_text |
| Datas | publication_date, edition_date, event_date, date_semantics |
| Provenance | resource_id, run_id |
| Classificação | via official_act_classifications |
| Links | official_act_links |
| Matches PNCP | official_act_matches |

### 1.4 CoverageEvidence / CoverageState (`coverage/states.py` + mig 054)

| Campo | Tipo | Notas |
|-------|------|-------|
| state | enum/str | success_with_data, success_zero, partial, error, … |
| request_scope | TEXT | escopo da requisição |
| pages_fetched / pages_expected | INT | completude de paginação |
| provenance | JSONB | deve ser ≠ {} se satisfactory |
| satisfactory | BOOLEAN | CHECK: só true se success_* + scope + provenance + pages OK + sem error |
| error_code | TEXT | falha |

### 1.5 DLQ (`dlq_entries` mig 045 + 054)

| Campo | Tipo | Notas |
|-------|------|-------|
| source, run_id, phase | TEXT | fetch/parse/transform/upsert |
| payload | JSONB | registro original |
| payload_hash | TEXT | dedup pending (054) |
| error_code / error_message / error_traceback | TEXT | erro |
| error_kind | TEXT | default 'record' (054) |
| retry_count / max_retries | INT | retries |
| status | TEXT | pending, replayed, dead, archived |
| purge_after | TIMESTAMPTZ | retenção ~90d |

### 1.6 pipeline_watermarks (046)

| Campo | Tipo | Notas |
|-------|------|-------|
| source, scope_key | TEXT | escopo |
| watermark_type | TEXT | page, date, entity, chunk |
| watermark_value | TEXT | valor |
| run_id | TEXT | run |
| status | TEXT | committed, in_progress, stalled |

### 1.7 CanonicalEntity / CanonicalUniverse (`lib/universe.py`)

| Campo / coleção | Descrição |
|-----------------|-----------|
| included / excluded / unresolved | partições do universo |
| cnpj8, entity_id, geo | identidade |
| conservative_monitoring_population | população conservadora |
| resolution_coverage | % resolvida |
| resolve_opportunity(...) | resolve opp → entidade |

### 1.8 ValorSemantica (`lib/value_semantics.py`)

| Enum | Significado | Exemplo fonte |
|------|-------------|---------------|
| ESTIMADO | valor esperado no edital | PNCP bids |
| HOMOLOGADO | valor adjudicado | ComprasGov |
| CONTRATADO | valor assinado | PNCP contracts |
| PAGO | empenho/desembolso | TCE-SC (futuro) |
| GLOBAL | total indiferenciado | label PNCP — **≠ preço praticado** |

### 1.9 BuyerProfile (`buyer_intel/ranking.py`)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| cnpj_8, razao_social, municipio, distancia_km | * | identidade |
| total_contratos, contratos_aec, valores, tickets, percentis | num | volume |
| primeira_data, ultima_data, frequencia_anual | * | temporal |
| fornecedores_distintos, top_fornecedores, hhi_concentracao | * | competitividade |
| contratos_vincendo_90d/180d/365d | int | pipeline comercial |

### 1.10 Opportunity scoring (`opportunity_intel/scoring.py`)

| Campo RadarScores (conceitual) | Origem |
|--------------------------------|--------|
| match objeto × profile | texto + profile |
| freshness | janela de dias |
| missing fields penalty | campos obrigatórios |
| status evidence | status.py |

### 1.11 Workspace SectionResult

| Campo | Descrição |
|-------|-----------|
| section id/title | nome da seção |
| rows | itens da fila |
| meta | contagens / erros soft |

---

## 2. Tabelas históricas (núcleo DataLake) 🟢/🟡

| Tabela | Papel | Confiança |
|--------|-------|-----------|
| pncp_raw_bids | editais/lances brutos PNCP | 🟢 |
| pncp_supplier_contracts | contratos/fornecedores | 🟢 |
| enriched_entities | entidades enriquecidas | 🟢 |
| ingestion_runs | runs de ingestão | 🟢 |
| entity_coverage / capability_coverage | cobertura por entidade/capability | 🟢/🟡 |
| opportunity_intel* | oportunidades QW-01 | 🟢 |
| coverage_evidence | evidências de cobertura | 🟢 |
| target_universe_* | snapshot universo-alvo | 🟢 |
| official_acts* | atos oficiais unificados | 🟢 |
| entity_source_registry | registry 1093 | 🟢 |
| dlq_entries | dead letter | 🟢 |
| pipeline_watermarks / pipeline_runs | retomada e runs | 🟢 |
| record_hashes | integridade de registros | 🟢 |
| entity_aliases | aliases de matching | 🟢 |

---

## 3. Enums e CHECK constraints relevantes

| Domínio | Valores |
|---------|---------|
| integration_type | api_json, html, pdf, js, ckan, rss, shared_portal, unknown |
| access_status | mapped, accessible, collected, verified, operational, failed, blocked, unknown, source_not_identified |
| fetch_status (resources) | discovered, fetched, parsed, failed, stale |
| dlq status | pending, replayed, dead, archived |
| watermark status | committed, in_progress, stalled |
| SourcePurpose | bids, contracts, coverage_only, hybrid |
| AuthorityLevel | federal, estadual, municipal, multi |

---

## 4. Artefatos de sessão (filesystem) 🟢

| Path típico | Conteúdo |
|-------------|----------|
| output/ reconciliation / evidence / sessions | JSON/JSONL de runs |
| resilience checkpoint/raw/dlq/evidence paths | pré-VPS ADR-021 |
| config/target_entities_200km.csv | seed universo |
| config/coverage_slas.yaml | SLAs do coverage contract |
| config/source_applicability.yaml | aplicabilidade de fontes |

---

## 5. Relacionamentos lógicos (ER resumido)

```
CanonicalUniverse 1──* EntitySourceRecord
EntitySourceRecord *──* SourceInfo (via plataformas / applicability)
SourceInfo 1──* CrawlRun / pipeline_runs
CrawlRun 1──* official_act_resources 1──* official_acts
official_acts *──* pncp_raw_bids/contracts (official_act_matches)
Entity 1──* coverage_evidence
Entity 1──* opportunity records
opportunity ──► workspace queue sections
```

Detalhamento C4/ERD: fase Architect (`erd-complete.md`).
