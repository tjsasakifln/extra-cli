# Dicionário de Dados — Extra Consultoria

> Gerado pelo Archaeologist em 2026-07-13
> doc_level: completo
> Base: PostgreSQL 16 + PostGIS, 41 migrations

---

## 1. Tabelas Principais

### 1.1 pncp_raw_bids (001)

Licitações brutas coletadas da API PNCP.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | SERIAL | ✅ | PK |
| `pncp_id` | TEXT | ✅ | ID único PNCP |
| `orgao_cnpj` | TEXT | | CNPJ do órgão licitante |
| `orgao_nome` | TEXT | | Nome do órgão |
| `objeto_compra` | TEXT | | Descrição do objeto |
| `valor_total_estimado` | NUMERIC | | Valor estimado da licitação |
| `data_publicacao` | TIMESTAMPTZ | | Data de publicação |
| `data_abertura` | TIMESTAMPTZ | | Data de abertura das propostas |
| `data_encerramento` | TIMESTAMPTZ | | Data de encerramento |
| `modalidade` | TEXT | | Modalidade da licitação |
| `situacao_compra` | TEXT | | Status na fonte |
| `numero_controle_pncp` | TEXT | | Número de controle PNCP |
| `uf` | TEXT | | UF do órgão |
| `municipio` | TEXT | | Município do órgão |
| `codigo_ibge` | TEXT | | Código IBGE do município |
| `content_hash` | TEXT | | Hash do conteúdo para dedup |
| `source_url` | TEXT | | URL original |
| `link_edital` | TEXT | | Link do edital |
| `is_active` | BOOLEAN | ✅ | Registro ativo (soft delete) |
| `ingested_at` | TIMESTAMPTZ | ✅ | Timestamp de ingestão |
| `enriched_at` | TIMESTAMPTZ | | Timestamp de enriquecimento |

**Índices:** GIN em `objeto_compra`, B-tree em `orgao_cnpj`, `data_publicacao`, `uf`, `municipio`, `modalidade`

---

### 1.2 pncp_supplier_contracts (002)

Contratos de fornecedores extraídos da API PNCP.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | SERIAL | ✅ | PK |
| `numero_controle_pncp` | TEXT | ✅ | Número de controle PNCP (único) |
| `orgao_cnpj` | TEXT | | CNPJ do órgão contratante |
| `orgao_cnpj8` | TEXT | | CNPJ raiz (8 dígitos) — chave de join |
| `orgao_nome` | TEXT | | Nome do órgão |
| `ni_fornecedor` | TEXT | | CNPJ/CPF do fornecedor |
| `nome_fornecedor` | TEXT | | Nome do fornecedor |
| `objeto_contrato` | TEXT | | Objeto do contrato |
| `valor_global` | NUMERIC | | Valor global do contrato (NÃO é "preço praticado") |
| `data_assinatura` | DATE | | Data de assinatura |
| `data_fim_vigencia` | DATE | | Data de fim da vigência |
| `data_publicacao` | DATE | | Data de publicação no PNCP |
| `uf` | TEXT | | UF |
| `municipio` | TEXT | | Município |
| `is_active` | BOOLEAN | ✅ | Registro ativo |
| `ingested_at` | TIMESTAMPTZ | ✅ | Timestamp de ingestão |

**⚠️ Semântica:** `valor_global` = valor do contrato assinado (ESTIMADO). NÃO reflete pagamentos efetivos, renegociações ou rescisões parciais.

**Índices:** `orgao_cnpj8`, `ni_fornecedor`, `data_assinatura`, `data_fim_vigencia`

---

### 1.3 sc_public_entities (007)

Entes públicos de SC dentro do raio de 200km de Florianópolis.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | SERIAL | ✅ | PK |
| `razao_social` | TEXT | ✅ | Razão social do ente |
| `cnpj_8` | TEXT | ✅ | CNPJ raiz (8 dígitos) |
| `municipio` | TEXT | | Município sede |
| `codigo_ibge` | TEXT | | Código IBGE (7 dígitos) |
| `natureza_juridica` | TEXT | | Natureza jurídica |
| `latitude` | DOUBLE PRECISION | | Latitude da sede |
| `longitude` | DOUBLE PRECISION | | Longitude da sede |
| `distancia_fk` | DOUBLE PRECISION | | Distância de Florianópolis (km) |
| `raio_200km` | BOOLEAN | | Dentro do raio de 200km? |
| `is_active` | BOOLEAN | ✅ | Ente ativo? |
| `created_at` | TIMESTAMPTZ | ✅ | Data de criação |
| `updated_at` | TIMESTAMPTZ | | Data de atualização |

**Índices:** `cnpj_8`, `raio_200km`, `municipio`, `codigo_ibge`

---

### 1.4 entity_coverage (009)

Matriz de cobertura: entidade × fonte × status de cobertura.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | SERIAL | ✅ | PK |
| `entity_id` | INTEGER | ✅ | FK → sc_public_entities.id |
| `source` | TEXT | ✅ | Nome da fonte |
| `data_type` | TEXT | ✅ | Tipo de dado (bids, contracts) |
| `is_covered` | BOOLEAN | ✅ | Coberto? |
| `match_method` | TEXT | | Método de match |
| `evidence_count` | INTEGER | | Qtd de evidências |
| `last_checked_at` | TIMESTAMPTZ | | Última verificação |
| `created_at` | TIMESTAMPTZ | ✅ | Data de criação |

---

### 1.5 coverage_evidence (024)

Evidence ledger auditável — cada linha é uma observação imutável.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | SERIAL | ✅ | PK |
| `entity_id` | INTEGER | | FK → sc_public_entities (NULL = source-level aggregate) |
| `source` | TEXT | ✅ | Fonte |
| `data_type` | TEXT | ✅ | Tipo de dado |
| `run_id` | INTEGER | ✅ | FK → ingestion_runs |
| `state` | evidence_state | ✅ | Enum: success_with_data, success_zero, partial, connection_failed, auth_failed, parse_failed, transform_failed, persist_failed, not_applicable, not_investigated, success, error, pending, stale, blocked |
| `records_fetched` | INTEGER | ✅ | Total de registros obtidos |
| `open_records` | INTEGER | ✅ | Registros com status aberto |
| `pages_expected` | INTEGER | | Páginas esperadas |
| `pages_processed` | INTEGER | ✅ | Páginas processadas |
| `canonical_entity_key` | TEXT | | Chave canônica da entidade |
| `applicability` | TEXT | ✅ | applicable, not_applicable, unknown |
| `scope_key` | TEXT | | Chave de escopo |
| `checked_at` | TIMESTAMPTZ | | Timestamp da verificação |
| `freshness_status` | TEXT | ✅ | unknown, fresh, stale, never |
| `evidence_metadata` | JSONB | ✅ | Metadados adicionais |
| `created_at` | TIMESTAMPTZ | ✅ | Data de criação |

**Constraints:**
- Partial unique index: `(entity_id, source, data_type, run_id) WHERE entity_id IS NOT NULL`
- Partial unique index: `(source, data_type, run_id) WHERE entity_id IS NULL`
- CHECK: `success_zero` rows must carry query-scope proof in metadata

---

### 1.6 opportunity_intel (027)

Licitações abertas — tabela core do Opportunity Intelligence.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | SERIAL | ✅ | PK |
| `source` | TEXT | ✅ | Fonte (pncp, compras_gov, etc.) |
| `source_id` | TEXT | ✅ | ID na fonte |
| `content_hash` | TEXT | ✅ | Hash do conteúdo |
| `source_url` | TEXT | | URL original |
| `numero_controle_pncp` | TEXT | | Número controle PNCP |
| `crawl_batch_id` | TEXT | | Lote de crawl |
| `run_id` | INTEGER | | FK → opportunity_runs |
| `ingested_at` | TIMESTAMPTZ | | Data de ingestão |
| `first_seen_at` | TIMESTAMPTZ | | Primeira vez visto |
| `last_seen_at` | TIMESTAMPTZ | | Última vez visto |
| `orgao_cnpj` | TEXT | | CNPJ do órgão |
| `orgao_nome` | TEXT | | Nome do órgão |
| `ente_federativo` | TEXT | | Ente federativo |
| `uf` | TEXT | | UF (default: SC) |
| `municipio` | TEXT | | Município |
| `codigo_ibge` | TEXT | | Código IBGE |
| `numero_processo` | TEXT | | Número do processo |
| `numero_edital` | TEXT | | Número do edital |
| `modalidade` | TEXT | | Modalidade |
| `modalidade_id` | INTEGER | | ID da modalidade |
| `objeto` | TEXT | | Descrição do objeto |
| `categoria` | TEXT | | Categoria |
| `valor_estimado` | NUMERIC | | Valor estimado |
| `valor_homologado` | NUMERIC | | Valor homologado |
| `valor_semantica` | TEXT | | Semântica do valor |
| `data_publicacao` | TIMESTAMPTZ | | Data de publicação |
| `data_abertura` | TIMESTAMPTZ | | Data de abertura |
| `data_encerramento` | TIMESTAMPTZ | | Data de encerramento |
| `data_homologacao` | TIMESTAMPTZ | | Data de homologação |
| `status_fonte` | TEXT | | Status na fonte |
| `status_canonico` | TEXT | | Status canônico (8 valores) |
| `status_motivo` | TEXT | | Motivo do status |
| `qualidade_score` | INTEGER | | Score de qualidade (0-100) |
| `ranking` | TEXT | | GO, REVIEW, NO_GO |
| `ranking_score` | INTEGER | | Score do ranking (0-100) |
| `ranking_fatores` | JSONB | | Fatores do ranking |
| `proveniencia` | JSONB | | Proveniência por campo |
| `is_active` | BOOLEAN | ✅ | Registro ativo |

**Índices (028):** 17 B-tree indexes + composite indexes

---

### 1.7 opportunity_runs (027)

Registro de execuções de crawl de opportunities.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | SERIAL | ✅ | PK |
| `source` | TEXT | ✅ | Fonte |
| `scope` | TEXT | ✅ | Escopo (full, incremental, monitoring) |
| `started_at` | TIMESTAMPTZ | ✅ | Início |
| `finished_at` | TIMESTAMPTZ | | Fim |
| `records_fetched` | INTEGER | | Total obtido |
| `records_inserted` | INTEGER | | Inseridos |
| `records_updated` | INTEGER | | Atualizados |
| `records_skipped` | INTEGER | | Pulados (dedup) |
| `status` | TEXT | | Status da execução |
| `error_message` | TEXT | | Mensagem de erro |
| `git_sha` | TEXT | | Git SHA do código |

---

### 1.8 enriched_entities (003)

Entidades enriquecidas com dados IBGE, geocodificação e matching.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | SERIAL | ✅ | PK |
| `cnpj_8` | TEXT | ✅ | CNPJ raiz |
| `razao_social` | TEXT | | Razão social |
| `nome_fantasia` | TEXT | | Nome fantasia |
| `municipio` | TEXT | | Município |
| `uf` | TEXT | | UF |
| `codigo_ibge` | TEXT | | Código IBGE |
| `latitude` | DOUBLE PRECISION | | Latitude |
| `longitude` | DOUBLE PRECISION | | Longitude |
| `distancia_km` | DOUBLE PRECISION | | Distância até Florianópolis |
| `entity_id` | INTEGER | | FK → sc_public_entities |
| `match_confidence` | TEXT | | Confiança do match |
| `match_method` | TEXT | | Método de match |
| `enriched_at` | TIMESTAMPTZ | | Data de enriquecimento |
| `ttl_hours` | INTEGER | | TTL em horas (migration 015) |

---

## 2. Views Analíticas

### v_contract_historical (026)

Contratos históricos (3 anos, 200km).

| Coluna | Origem |
|--------|--------|
| `contrato_id` | `pncp_supplier_contracts.numero_controle_pncp` |
| `orgao_cnpj` | `pncp_supplier_contracts.orgao_cnpj` |
| `orgao_nome` | `pncp_supplier_contracts.orgao_nome` |
| `fornecedor_cnpj` | `pncp_supplier_contracts.ni_fornecedor` |
| `fornecedor_nome` | `pncp_supplier_contracts.nome_fornecedor` |
| `objeto_contrato` | `pncp_supplier_contracts.objeto_contrato` |
| `valor_contrato` | `pncp_supplier_contracts.valor_global` |
| `data_inicio_contrato` | `pncp_supplier_contracts.data_assinatura` |
| `data_fim_contrato` | `pncp_supplier_contracts.data_fim_vigencia` |
| `ente_razao_social` | `sc_public_entities.razao_social` |
| `ente_distancia_km` | `sc_public_entities.distancia_fk` |

### v_supplier_winners (026)

Ranking de fornecedores com métricas competitivas.

| Coluna | Descrição |
|--------|-----------|
| `fornecedor_cnpj` | CNPJ do fornecedor |
| `fornecedor_nome` | Nome do fornecedor |
| `qtd_contratos` | Quantidade de contratos |
| `valor_total_contratos` | Soma dos valores globais |
| `ticket_medio_contrato` | Valor médio por contrato |
| `qtd_orgaos_distintos` | Órgãos distintos atendidos |
| `hhi_concentracao` | Índice Herfindahl-Hirschman |
| `orgaos_lista` | Lista de órgãos |

### v_expiring_contracts (026)

Contratos expirando em 90-180 dias.

| Coluna | Descrição |
|--------|-----------|
| `dias_ate_fim` | Dias até o fim da vigência |

---

## 3. Enums e Constantes de Domínio

### evidence_state (024)

```sql
CREATE TYPE evidence_state AS ENUM (
    'success_with_data', 'success_zero',
    'partial',
    'connection_failed', 'auth_failed',
    'parse_failed', 'transform_failed', 'persist_failed',
    'not_applicable', 'not_investigated',
    'success', 'error', 'pending', 'stale', 'blocked'  -- QW-01 additions (029)
);
```

### status_canonico (027)

```
open, upcoming, closed, suspended, revoked, annulled, failed, unknown
```

### ranking tiers

```
GO (≥70), REVIEW (40-69), NO_GO (<40)
```

### confidence levels

```
HIGH, MEDIUM, LOW
```

### triage values

```
PRIORITARIA, REVISAR, DESCARTAR
```

### applicability (029)

```
applicable, not_applicable, unknown
```

### freshness_status (029)

```
unknown, fresh, stale, never
```

---

## 4. Tipos de Valor (value_semantics.py)

| Enum | Significado | Fonte |
|------|-------------|-------|
| `ESTIMADO` | Valor do edital — expectativa do governo | PNCP bids |
| `HOMOLOGADO` | Valor homologado — resultado do pregão | ComprasGov |
| `CONTRATADO` | Valor assinado em contrato | PNCP contracts |
| `PAGO` | Valor efetivamente pago (empenho) | TCE/SC |
| `GLOBAL` | Valor indiferenciado — NÃO é "preço praticado" | PNCP default |

---

## 5. Mapa de Fontes → Tabelas

| Fonte | Tabela Raw | Tipo | Status |
|-------|-----------|------|--------|
| PNCP bids | `pncp_raw_bids` | REST API | ✅ Ativo |
| PNCP contracts | `pncp_supplier_contracts` | REST API | ✅ Ativo |
| Compras.gov | — | REST API | 🔴 Bloqueado (Selenium) |
| TCE-SC | — | Scraping | ✅ Ativo |
| DOE-SC | — | Selenium | 🔴 Bloqueado |
| DOM-SC | — | Scraping | 🔴 Bloqueado |
| CIGA/CKAN | — | CKAN API | ✅ Ativo |
| SC Compras | — | Scraping | 🟡 Instável |
| MIDES/BigQuery | — | BigQuery | 🔴 Bloqueado |
| Portais Transparência | — | Scraping | 🟡 Parcial (295+ portais) |
| Oportunidades | `opportunity_intel` | Agregada | ✅ Ativo |
