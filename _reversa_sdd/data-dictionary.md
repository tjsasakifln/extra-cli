# Dicionário de Dados — Extra Consultoria

> Gerado pelo Archaeologist em 2026-07-11T13:00:00Z
> doc_level: completo

---

## Tabela: `pncp_raw_bids`

Licitações multi-source unificado. Tabela central do sistema.

| Coluna | Tipo | Obrigatório | Padrão | Descrição |
|--------|------|-------------|--------|-----------|
| `pncp_id` | TEXT | SIM | — | Chave primária. `numeroControlePNCP` ou hash para fontes sem PNCP |
| `objeto_compra` | TEXT | NÃO | NULL | Descrição do objeto da licitação |
| `valor_total_estimado` | NUMERIC(18,2) | NÃO | NULL | Valor total estimado em R$ |
| `modalidade_id` | INT | NÃO | NULL | Código da modalidade (4=Concorrência, 5=Pregão, 6=Pregão Presencial, 7=Dispensa, etc.) |
| `modalidade_nome` | TEXT | NÃO | NULL | Nome da modalidade |
| `esfera_id` | INT | NÃO | NULL | Esfera (1=Federal, 2=Estadual, 3=Municipal) |
| `uf` | TEXT | NÃO | NULL | Sigla UF (SC, PR, RS, etc.) |
| `municipio` | TEXT | NÃO | NULL | Nome do município |
| `codigo_municipio_ibge` | TEXT | NÃO | NULL | Código IBGE de 7 dígitos |
| `orgao_razao_social` | TEXT | NÃO | NULL | Razão social do órgão publicante |
| `orgao_cnpj` | TEXT | NÃO | NULL | CNPJ do órgão (14 dígitos) |
| `data_publicacao` | DATE | NÃO | NULL | Data de publicação |
| `data_abertura` | DATE | NÃO | NULL | Data de abertura das propostas |
| `data_encerramento` | DATE | NÃO | NULL | Data de encerramento |
| `link_pncp` | TEXT | NÃO | NULL | Link para o edital no PNCP |
| `content_hash` | TEXT | NÃO (UNIQUE) | NULL | SHA-256 de objeto+valor+situação (dedup) |
| `tsv` | TSVECTOR | NÃO | NULL | Full-text search vector (PT-BR) |
| `source` | TEXT | SIM | 'pncp' | Fonte: pncp, dom_sc, pcp, compras_gov, sc_compras, contracts, transparencia, tce_sc |
| `source_id` | TEXT | NÃO | NULL | ID original na fonte |
| `matched_entity_id` | INT | NÃO | NULL | FK → sc_public_entities.id |
| `match_method` | TEXT | NÃO | NULL | Método: cnpj, name_normalized, fuzzy, unmatched |
| `match_score` | NUMERIC(5,3) | NÃO | NULL | Score do match (0.0-1.0) |
| `match_confidence` | TEXT | NÃO | NULL | Confiança: high, medium, low |
| `ingested_at` | TIMESTAMPTZ | SIM | NOW() | Timestamp de ingestão |
| `updated_at` | TIMESTAMPTZ | SIM | NOW() | Timestamp de última atualização (auto trigger) |
| `is_active` | BOOLEAN | SIM | TRUE | Soft delete |

**Índices (12):** GIN em `tsv` (FTS PT-BR), B-tree em (uf, data_publicacao), (modalidade_id, data_publicacao), valor_total_estimado, esfera_id, data_encerramento (partial), source, orgao_cnpj, matched_entity_id (partial), ingested_at, (is_active, data_publicacao) partial.

---

## Tabela: `pncp_supplier_contracts`

Histórico de contratos de fornecedores.

| Coluna | Tipo | Obrigatório | Descrição |
|--------|------|-------------|-----------|
| `id` | INT (SERIAL) | SIM | Chave primária |
| `supplier_cnpj` | TEXT | SIM | CNPJ do fornecedor |
| `supplier_name` | TEXT | NÃO | Nome do fornecedor |
| `contract_value` | NUMERIC(18,2) | NÃO | Valor do contrato |
| `contract_date` | DATE | NÃO | Data do contrato |
| `orgao` | TEXT | NÃO | Órgão contratante |
| `uf` | TEXT | NÃO | UF do contrato |
| `municipio` | TEXT | NÃO | Município do contrato |
| `modalidade` | TEXT | NÃO | Modalidade da licitação |
| `pncp_contract_id` | TEXT | NÃO | ID do contrato no PNCP |
| `ingested_at` | TIMESTAMPTZ | SIM | Timestamp de ingestão |

---

## Tabela: `enriched_entities`

Cache de enriquecimento cadastral (BrasilAPI + IBGE).

| Coluna | Tipo | Obrigatório | Descrição |
|--------|------|-------------|-----------|
| `cnpj` | TEXT | SIM (PK) | CNPJ (14 dígitos) |
| `razao_social` | TEXT | NÃO | Razão social |
| `nome_fantasia` | TEXT | NÃO | Nome fantasia |
| `cnae_principal` | TEXT | NÃO | CNAE principal |
| `cnae_secundarios` | TEXT[] | NÃO | CNAEs secundários |
| `municipio` | TEXT | NÃO | Município |
| `uf` | TEXT | NÃO | UF |
| `natureza_juridica` | TEXT | NÃO | Natureza jurídica |
| `porte` | TEXT | NÃO | Porte da empresa |
| `entity_type` | TEXT | SIM | Tipo: 'fornecedor', 'orgao' |
| `enriched_at` | TIMESTAMPTZ | SIM | Timestamp do enriquecimento |
| `raw_data` | JSONB | NÃO | Dados brutos da API |

---

## Tabela: `sc_public_entities`

Catálogo de 2.085 órgãos públicos de SC.

| Coluna | Tipo | Obrigatório | Descrição |
|--------|------|-------------|-----------|
| `id` | INT (SERIAL) | SIM | Chave primária |
| `razao_social` | TEXT | SIM | Razão social do órgão |
| `cnpj_8` | TEXT | NÃO | Base CNPJ (8 dígitos) |
| `municipio` | TEXT | NÃO | Município |
| `codigo_ibge` | TEXT | NÃO | Código IBGE (7 dígitos) |
| `natureza_juridica` | TEXT | NÃO | Natureza jurídica |
| `raio_200km` | BOOLEAN | SIM | Dentro do raio de 200km de Florianópolis? |
| `is_active` | BOOLEAN | SIM | Entidade ativa? |
| `created_at` | TIMESTAMPTZ | SIM | Timestamp de criação |
| `updated_at` | TIMESTAMPTZ | SIM | Timestamp de atualização |

---

## Tabela: `entity_coverage`

Tracking de cobertura por entidade e fonte.

| Coluna | Tipo | Obrigatório | Descrição |
|--------|------|-------------|-----------|
| `entity_id` | INT | SIM (FK) | FK → sc_public_entities.id |
| `source` | TEXT | SIM | Fonte de dados |
| `is_covered` | BOOLEAN | SIM | Entidade coberta por esta fonte? |
| `within_200km` | BOOLEAN | SIM | Dentro do raio de 200km? |
| `last_seen_at` | TIMESTAMPTZ | NÃO | Última vez que foi vista |
| `bid_count` | INT | SIM (0) | Contagem de licitações |
| `first_seen_at` | TIMESTAMPTZ | NÃO | Primeira vez que foi vista |

**Chave única:** (entity_id, source)

---

## Tabela: `ingestion_runs`

Auditoria de execuções de crawlers.

| Coluna | Tipo | Obrigatório | Descrição |
|--------|------|-------------|-----------|
| `id` | INT (SERIAL) | SIM | Chave primária |
| `source` | TEXT | SIM | Fonte de dados |
| `status` | TEXT | SIM | Status: running, completed, failed |
| `records_fetched` | INT | NÃO | Registros buscados |
| `records_upserted` | INT | NÃO | Registros inseridos/atualizados |
| `entities_covered` | INT | NÃO | Entidades cobertas |
| `started_at` | TIMESTAMPTZ | SIM | Início da execução |
| `finished_at` | TIMESTAMPTZ | NÃO | Fim da execução |
| `error_message` | TEXT | NÃO | Mensagem de erro (se failed) |
| `cursor_data` | JSONB | NÃO | Dados de cursor para resume |

---

## Tabela: `ingestion_checkpoints`

Estado de crawl resumable por fonte.

| Coluna | Tipo | Obrigatório | Descrição |
|--------|------|-------------|-----------|
| `source` | TEXT | SIM (PK) | Fonte de dados |
| `last_crawl_at` | TIMESTAMPTZ | NÃO | Timestamp do último crawl |
| `last_pncp_id` | TEXT | NÃO | Último ID processado |
| `mode` | TEXT | NÃO | Modo: full, incremental |
| `cursor_data` | JSONB | NÃO | Dados de cursor (página, offset, etc.) |

---

## Tabela: `coverage_snapshots`

Snapshots históricos de cobertura.

| Coluna | Tipo | Obrigatório | Descrição |
|--------|------|-------------|-----------|
| `snapshot_date` | DATE | SIM (PK) | Data do snapshot |
| `total_entities` | INT | SIM | Total de entidades ativas |
| `covered_entities` | INT | SIM | Entidades cobertas |
| `coverage_pct` | NUMERIC(5,1) | SIM | Percentual de cobertura |
| `uncovered_within_200km` | INT | SIM | Entidades descobertas no raio |
| `by_source` | JSONB | NÃO | Breakdown por fonte |

---

## View: `v_unmatched_bids`

View de licitações não matched para análise de gaps.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `pncp_id` | TEXT | ID da licitação |
| `orgao_razao_social` | TEXT | Nome do órgão (não normalizado) |
| `orgao_cnpj` | TEXT | CNPJ do órgão |
| `municipio` | TEXT | Município |
| `codigo_municipio_ibge` | TEXT | Código IBGE |
| `source` | TEXT | Fonte de dados |
| `data_publicacao` | DATE | Data de publicação |

---

## Estruturas Python (lib)

### `BidSimulation` (bid_simulator.py)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `lance_sugerido` | float | Valor sugerido do lance (R$) |
| `desconto_sugerido_pct` | float | % de desconto do valor estimado |
| `p_vitoria_pct` | float | Probabilidade estimada de vitória (0-100) |
| `margem_liquida_pct` | float | Margem líquida esperada |
| `valor_esperado` | float | EV = P(win) × margem × valor_estimado |
| `lance_agressivo` | float | Limite inferior (mais desconto) |
| `lance_conservador` | float | Limite superior (menos desconto) |
| `competidores_esperados` | int | Número estimado de concorrentes |
| `historico_contratos` | int | Contratos usados como benchmark |
| `confianca` | str | ALTA / MEDIA / BAIXA |
| `racional` | str | Explicação em linguagem natural |

### `VictoryProfile` (victory_profile.py)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `valor_mean` | float | Valor médio dos contratos ganhos |
| `valor_std` | float | Desvio padrão |
| `valor_q25` / `valor_q75` | float | Quartis |
| `modalidade_weights` | dict[int, float] | Pesos por modalidade |
| `pop_bracket_weights` | dict[str, float] | Pesos por faixa populacional |
| `keyword_freq` | dict[str, float] | Frequência de keywords |
| `dist_mean_km` | float | Distância média |
| `total_contracts` | int | Total de contratos analisados |
| `company_capital` | float | Capital social da empresa |

### `SECTOR_MARGINS` (bid_simulator.py)

| Setor | margem_minima | margem_alvo | bdi_referencia |
|-------|---------------|-------------|-----------------|
| engenharia_obras | 5% | 12% | 25% |
| ti_software | 10% | 20% | 30% |
| consultoria | 15% | 25% | 35% |
| avaliacao | 10% | 18% | 28% |
| default | 8% | 15% | 25% |

### `POP_BRACKETS` (victory_profile.py)

| Faixa (hab) | Label |
|-------------|-------|
| < 5.000 | micro |
| 5.000-20.000 | pequeno |
| 20.000-100.000 | medio |
| 100.000-500.000 | grande |
| > 500.000 | metropole |

### `ABBREVIATIONS` (name_normalizer.py)

18 abreviações da administração pública: SEC→SECRETARIA, MUN→MUNICIPIO, PM→PREFEITURA MUNICIPAL, FMS→FUNDO MUNICIPAL DE SAUDE, FME→FUNDO MUNICIPAL DE EDUCACAO, etc.
