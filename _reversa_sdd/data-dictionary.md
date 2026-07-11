# Dicionário de Dados — Extra Consultoria

> Gerado pelo Archaeologist em 2026-07-11T21:00:00Z
> doc_level: completo
> Base: commit e9729e1

---

## Tabela: `pncp_raw_bids` (Lícitações Multi-Source)

Schema central. ~199K registros. 8 fontes de dados.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|--------|------|------------|---------|-----------|
| `pncp_id` | TEXT | SIM (PK) | — | ID único da licitação (PNCP ou sintético) |
| `objeto_compra` | TEXT | NÃO | NULL | Descrição do objeto da licitação |
| `valor_total_estimado` | NUMERIC(18,2) | NÃO | NULL | Valor estimado da contratação |
| `modalidade_id` | INT | NÃO | NULL | Código da modalidade (4=Concorrência, 5=Pregao Eletr., 6=Pregao Pres., 7=Contratação Direta, 8=Inexigibilidade, 12=Credenciamento) |
| `modalidade_nome` | TEXT | NÃO | NULL | Nome da modalidade |
| `situacao_compra` | TEXT | NÃO | NULL | Situação da compra |
| `esfera_id` | TEXT | NÃO | NULL | Esfera: 'F'=Federal, 'E'=Estadual, 'M'=Municipal, 'D'=Distrital |
| `uf` | TEXT | NÃO | NULL | Sigla UF (2 caracteres) |
| `municipio` | TEXT | NÃO | NULL | Nome do município |
| `codigo_municipio_ibge` | TEXT | NÃO | NULL | Código IBGE de 7 dígitos |
| `orgao_razao_social` | TEXT | NÃO | NULL | Razão social do órgão contratante |
| `orgao_cnpj` | TEXT | NÃO | NULL | CNPJ do órgão (14 dígitos) |
| `unidade_nome` | TEXT | NÃO | NULL | Nome da unidade administrativa |
| `data_publicacao` | TIMESTAMPTZ | NÃO | NULL | Data de publicação do edital |
| `data_abertura` | TIMESTAMPTZ | NÃO | NULL | Data de abertura das propostas |
| `data_encerramento` | TIMESTAMPTZ | NÃO | NULL | Data de encerramento |
| `link_sistema_origem` | TEXT | NÃO | NULL | Link para o sistema de origem |
| `link_pncp` | TEXT | NÃO | NULL | Link para a página no PNCP |
| `content_hash` | TEXT | SIM (UNIQUE) | — | SHA-256 de campos-chave para dedup |
| `tsv` | TSVECTOR | NÃO | — | Vetor de full-text search (portuguese) |
| `source` | TEXT | NÃO | 'pncp' | Fonte dos dados (pncp, dom_sc, pcp, compras_gov, etc.) |
| `source_id` | TEXT | NÃO | NULL | ID na fonte original |
| `matched_entity_id` | INT | NÃO | NULL | FK → `sc_public_entities.id` (ON DELETE SET NULL) |
| `match_method` | TEXT | NÃO | NULL | Método de match: cnpj, name_normalized, fuzzy, unmatched |
| `match_score` | DECIMAL(4,3) | NÃO | NULL | Score do match (0.0-1.0) |
| `match_confidence` | TEXT | NÃO | NULL | Confiança: high, medium, low |
| `embedding` | VECTOR(256) | NÃO | NULL | Embedding do objeto_compra (text-embedding-3-small) |
| `is_active` | BOOLEAN | NÃO | TRUE | Soft-delete flag |
| `ingested_at` | TIMESTAMPTZ | NÃO | NOW() | Timestamp de ingestão |
| `updated_at` | TIMESTAMPTZ | NÃO | NOW() | Timestamp de última atualização |

**Índices (10+):** GIN em `tsv`, BTREE `(uf, data_publicacao DESC)`, `(modalidade_id, data_publicacao DESC)`, `valor_total_estimado`, `orgao_cnpj`, `matched_entity_id` (partial), `ingested_at DESC`, `(is_active, data_publicacao DESC)` (partial), GIN `objeto_compra gin_trgm_ops` (partial is_active), HNSW em `embedding`.

🟢 **CONFIRMADO** — `supabase/current-schema.sql` + migrations 001, 010, 014, 016, 017.

---

## Tabela: `pncp_supplier_contracts` (Contratos de Fornecedores)

~3.69M registros. Histórico de contratos por fornecedor.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|--------|------|------------|---------|-----------|
| `id` | SERIAL | SIM (PK) | auto | ID interno |
| `contrato_id` | TEXT | SIM (UNIQUE) | — | ID do contrato no PNCP |
| `numero_controle_pncp` | TEXT | NÃO | NULL | Número de controle PNCP |
| `orgao_cnpj` | TEXT | NÃO | NULL | CNPJ do órgão contratante |
| `orgao_nome` | TEXT | NÃO | NULL | Nome do órgão contratante |
| `fornecedor_cnpj` | TEXT | NÃO | NULL | CNPJ do fornecedor |
| `fornecedor_nome` | TEXT | NÃO | NULL | Nome do fornecedor |
| `objeto_contrato` | TEXT | NÃO | NULL | Objeto do contrato |
| `valor_total` | NUMERIC(18,2) | NÃO | NULL | Valor total do contrato |
| `data_inicio` | DATE | NÃO | NULL | Data de início da vigência |
| `data_fim` | DATE | NÃO | NULL | Data de fim da vigência |
| `data_publicacao` | DATE | NÃO | NULL | Data de publicação |
| `uf` | TEXT | NÃO | NULL | UF do contrato |
| `municipio` | TEXT | NÃO | NULL | Município do contrato |
| `source` | TEXT | NÃO | 'pncp' | Fonte dos dados |
| `source_id` | TEXT | NÃO | NULL | ID na fonte original |
| `content_hash` | TEXT | SIM (UNIQUE) | — | Hash para dedup |
| `ingested_at` | TIMESTAMPTZ | NÃO | NOW() | Timestamp de ingestão |

**Índices (6+):** BTREE `(fornecedor_cnpj, data_publicacao DESC)`, `orgao_cnpj`, `(uf, data_publicacao DESC)`, `valor_total`, GIN `objeto_contrato gin_trgm_ops`, `(data_publicacao DESC)`.

🟢 **CONFIRMADO** — `supabase/current-schema.sql` + migration 002.

---

## Tabela: `sc_public_entities` (Entes Públicos SC)

2.085 registros. Catálogo mestre de entes públicos catarinenses.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|--------|------|------------|---------|-----------|
| `id` | SERIAL | SIM (PK) | auto | ID interno |
| `razao_social` | TEXT | SIM | — | Razão social do ente |
| `cnpj_8` | TEXT | SIM (UNIQUE) | — | Base CNPJ de 8 dígitos |
| `municipio` | TEXT | NÃO | NULL | Município sede |
| `codigo_ibge` | TEXT | NÃO | NULL | Código IBGE do município |
| `natureza_juridica` | TEXT | NÃO | NULL | Natureza jurídica (ex: "Prefeitura Municipal", "Câmara Municipal") |
| `cod_natureza` | TEXT | NÃO | NULL | Código da natureza jurídica |
| `latitude` | DOUBLE PRECISION | NÃO | NULL | Latitude da sede |
| `longitude` | DOUBLE PRECISION | NÃO | NULL | Longitude da sede |
| `distancia_fk` | DOUBLE PRECISION | NÃO | NULL | Distância em km de Florianópolis (Haversine) |
| `raio_200km` | BOOLEAN | NÃO | FALSE | Dentro do raio de 200km de Florianópolis? |
| `is_active` | BOOLEAN | NÃO | TRUE | Ente ativo? |
| `created_at` | TIMESTAMPTZ | NÃO | NOW() | Timestamp de criação |

**Índices (5):** BTREE `cnpj_8`, `municipio`, `codigo_ibge`, `(raio_200km, is_active)`, `cod_natureza`.

🟢 **CONFIRMADO** — `supabase/current-schema.sql` + migration 007.

---

## Tabela: `enriched_entities` (Cache de Enriquecimento)

~13.8K registros. Cache de dados da BrasilAPI e IBGE.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|--------|------|------------|---------|-----------|
| `entity_type` | TEXT | SIM (PK parte) | — | Tipo: 'cnpj' (fornecedor) ou 'municipio' |
| `entity_id` | TEXT | SIM (PK parte) | — | CNPJ (14 dígitos) ou código IBGE (7 dígitos) |
| `data` | JSONB | NÃO | '{}' | Dados completos do enriquecimento |
| `enriched_at` | TIMESTAMPTZ | NÃO | NOW() | Timestamp do enriquecimento |
| `enriched_source` | TEXT | NÃO | 'brasilapi' | Fonte: brasilapi, ibge |

**Constraints:** CHECK `enriched_at` not future, CHECK `entity_id` not empty, CHECK `enriched_source` not empty.

🟢 **CONFIRMADO** — `supabase/current-schema.sql` (schema real). Schema real diverge da migration 003 (colunas planas).

---

## Tabela: `entity_coverage` (Cobertura por Ente)

Tracking de quais fontes cobrem cada ente público. PK composto.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|--------|------|------------|---------|-----------|
| `entity_id` | INT | SIM (PK, FK) | — | FK → `sc_public_entities.id` (CASCADE) |
| `source` | TEXT | SIM (PK) | — | Fonte de dados |
| `last_seen_at` | TIMESTAMPTZ | NÃO | NULL | Última vez que o ente apareceu nesta fonte |
| `total_bids` | INT | NÃO | 0 | Total de licitações do ente nesta fonte |
| `is_covered` | BOOLEAN | NÃO | FALSE | Coberto nos últimos 90 dias? |
| `within_200km` | BOOLEAN | NÃO | FALSE | Dentro do raio de 200km? |

**Índices (3):** `(is_covered, within_200km)`, `last_seen_at`, `(source, is_covered)`.

🟢 **CONFIRMADO** — `supabase/current-schema.sql` + migration 009.

---

## Tabela: `coverage_snapshots` (Snapshots de Cobertura)

Histórico semanal de cobertura para análise de tendência.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|--------|------|------------|---------|-----------|
| `id` | SERIAL | SIM (PK) | auto | ID interno |
| `snapshot_date` | DATE | NÃO | NULL | Data do snapshot |
| `source` | TEXT | NÃO | NULL | Fonte de dados |
| `total_entities` | INT | NÃO | NULL | Total de entes monitorados |
| `covered_entities` | INT | NÃO | NULL | Entes cobertos nos últimos 90 dias |
| `pct_covered` | DECIMAL(5,2) | NÃO | NULL | Percentual de cobertura |

🟢 **CONFIRMADO** — `supabase/current-schema.sql` + migration 012.

---

## Tabela: `ingestion_checkpoints` (Checkpoints de Crawl)

PK composto. Permite retomada de crawls interrompidos.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|--------|------|------------|---------|-----------|
| `source` | TEXT | SIM (PK) | — | Fonte de dados |
| `scope_key` | TEXT | SIM (PK) | — | Escopo (ex: uf_modalidade) |
| `last_page` | INT | NÃO | NULL | Última página processada |
| `last_date` | DATE | NÃO | NULL | Última data processada |
| `last_id` | TEXT | NÃO | NULL | Último ID processado |
| `records_fetched` | INT | NÃO | 0 | Total de registros baixados |
| `updated_at` | TIMESTAMPTZ | NÃO | NOW() | Timestamp de atualização |

🟢 **CONFIRMADO** — `supabase/current-schema.sql` + migration 004.

---

## Tabela: `ingestion_runs` (Audit Trail de Execuções)

Histórico de cada execução de crawler.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|--------|------|------------|---------|-----------|
| `id` | SERIAL | SIM (PK) | auto | ID da execução |
| `source` | TEXT | NÃO | NULL | Fonte de dados |
| `started_at` | TIMESTAMPTZ | NÃO | NOW() | Início da execução |
| `finished_at` | TIMESTAMPTZ | NÃO | NULL | Fim da execução |
| `records_fetched` | INT | NÃO | 0 | Registros baixados |
| `records_upserted` | INT | NÃO | 0 | Registros inseridos/atualizados |
| `entities_covered` | INT | NÃO | 0 | Entes cobertos nesta execução |
| `status` | TEXT | NÃO | 'running' | running, completed, failed |
| `error_message` | TEXT | NÃO | NULL | Mensagem de erro (se falhou) |
| `metadata` | JSONB | NÃO | '{}' | Metadados adicionais |

🟢 **CONFIRMADO** — `supabase/current-schema.sql` + migration 004.

---

## Views (5)

| View | Propósito | Colunas Chave |
|------|----------|--------------|
| `v_coverage_summary` | Cobertura % por source | source, total_entities, covered_entities, pct_covered |
| `v_coverage_gaps` | Entes sem cobertura | id, razao_social, cnpj_8, municipio, gap_total |
| `v_coverage_gaps_by_municipio` | Gaps agregados por município | municipio, total_entities, uncovered_entities |
| `v_coverage_trend` | Tendência semanal com LAG | snapshot_date, source, pct_covered, prev_pct_covered |
| `v_unmatched_bids` | Bids sem match | pncp_id, orgao_razao_social, orgao_cnpj, match_opportunity |

🟢 **CONFIRMADO** — `supabase/current-schema.sql` + migrations 009, 011, 012.

---

## Estruturas de Dados do Pipeline Intel (JSON)

### Edital (dict)
```
_id: str                    # "{cnpj}/{ano}/{seq}"
objeto: str
orgao: str
cnpj_orgao: str
uf: str
municipio: str
valor_estimado: float
modalidade_code: int
modalidade_nome: str
data_publicacao: str        # DD/MM/YYYY
data_abertura_proposta: str
data_encerramento_proposta: str
link_pncp: str
status_temporal: str        # EXPIRADO|CRITICO|URGENTE|ATENCAO|NORMAL|CONFORTAVEL
dias_restantes: int
cnae_compatible: bool
cnae_confidence: float      # 0.0-1.0
keyword_density: float
match_keywords: list[str]
needs_llm_review: bool
gate2_decision: str         # COMPATIVEL|INCOMPATIVEL|NEEDS_REVIEW
distancia: float            # km
distancia_duracao_horas: float
ibge: {populacao, pib_mil_reais, pib_per_capita}
custo_proposta: {total, deslocamento, hospedagem, alimentacao, pedagio, hora_tecnica, preparo}
roi_proposta: {ratio, classificacao}
_bid_simulation: BidSimulation
_victory_fit: float         # 0.0-1.0
_victory_fit_label: str     # Poor|Moderate|Good|Excellent
analise: dict               # 21 campos (resultado do GPT-4.1-nano)
texto_documentos: str       # Texto extraído dos PDFs
extraction_quality: str     # COMPLETO|PARCIAL|INSUFICIENTE|VAZIO
_delta_status: str          # NOVO|ATUALIZADO|VENCENDO|INALTERADO
```

### BidSimulation (dataclass)
```
lance_sugerido: float
desconto_sugerido_pct: float
p_vitoria_pct: float
margem_liquida_pct: float
valor_esperado: float
lance_agressivo: float
lance_conservador: float
desconto_agressivo_pct: float
desconto_conservador_pct: float
competidores_esperados: int
historico_contratos: int
confianca: str              # ALTA|MEDIA|BAIXA|INSUFICIENTE
racional: str
```

### VictoryProfile (dataclass)
```
valor_mean: float
valor_std: float
valor_q25: float
valor_q75: float
valor_min: float
valor_max: float
modalidade_weights: dict[int, float]
pop_bracket_weights: dict[str, float]
keyword_freq: dict[str, float]
dist_mean_km: float
dist_max_km: float
uf_weights: dict[str, float]
total_contracts: int
period_months: int
company_capital: float
```

### CostParams (dataclass)
```
custo_km: float             # 0.80
diaria_hospedagem_interior: float  # 180
diaria_hospedagem_capital: float   # 280
per_diem_alimentacao: float # 80
custo_hora_tecnico: float   # 150
horas_sessao: float         # 4.0
limiar_hospedagem_km: int   # 200
limiar_duas_diarias_km: int # 500
pedagio_por_faixa: dict[int, float]
custo_fixo_proposta: float
custo_fixo_mobilizacao: float
```

🟢 **CONFIRMADO** — `intel-collect.py`, `bid_simulator.py`, `victory_profile.py`, `cost_estimator.py`.

---

## Extensões PostgreSQL

| Extensão | Versão | Uso |
|----------|--------|-----|
| `pg_trgm` | 1.6 | Trigram indexes para ILIKE e similarity (GIN) |
| `uuid-ossp` | 1.1 | Geração de UUIDs |
| `unaccent` | 1.1 | Remoção de acentos para normalização |
| `vector` | 0.8.0 | pgvector para embeddings (HNSW index) |

🟢 **CONFIRMADO** — `supabase/current-schema.sql:1-10`.
