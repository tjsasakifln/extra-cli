# ERD Completo — Extra Consultoria DataLake

> Gerado pelo Architect em 2026-07-13T17:30:00Z
> doc_level: completo
> Base: commit 249340d, PostgreSQL 18.4 + PostGIS
> Delta: +2 tabelas (coverage_evidence, opportunity_intel), +1 enum (evidence_state)

```mermaid
erDiagram
    sc_public_entities ||--o{ pncp_raw_bids : "matched_entity_id (SET NULL)"
    sc_public_entities ||--o{ coverage_evidence : "entity_id (SET NULL on delete?)"
    sc_public_entities ||--o{ opportunity_intel : "entity_id FK"
    pncp_raw_bids ||--o{ pncp_supplier_contracts : "numero_controle_pncp"
    ingestion_runs ||--o{ coverage_evidence : "run_id FK"
    ingestion_runs ||--o{ ingestion_checkpoints : "source reference"

    sc_public_entities {
        serial id PK "identificador interno"
        text razao_social "nome do ente público"
        text cnpj_8 UK "base CNPJ 8 dígitos"
        text municipio "município sede"
        text codigo_ibge "código IBGE 7 dígitos"
        text natureza_juridica "Prefeitura, Câmara, Fundo..."
        double_precision latitude "coordenada"
        double_precision longitude "coordenada"
        double_precision distancia_fk "km de Florianópolis (Haversine)"
        boolean raio_200km "dentro do raio de 200km? DIAGNÓSTICO, não autoritativo"
        boolean is_active "ente ativo?"
        timestamptz created_at "data de criação"
    }

    pncp_raw_bids {
        text pncp_id PK "ID único da licitação PNCP"
        text numero_controle_pncp "Número de controle PNCP (FK→contracts)"
        text orgao_cnpj "CNPJ do órgão licitante"
        text orgao_nome "Nome do órgão"
        text objeto_compra "Descrição do objeto (GIN index)"
        numeric valor_total_estimado "Valor estimado da licitação"
        text modalidade "Modalidade (concorrência, pregão...)"
        text situacao_compra "Status na fonte original"
        text uf "UF do órgão"
        text municipio "Município do órgão"
        text codigo_ibge "Código IBGE do município"
        text content_hash "SHA-256 para dedup cross-source"
        text source "Fonte de origem (pncp, dom_sc, etc.)"
        text source_url "URL original"
        text link_edital "Link do edital"
        timestamptz data_publicacao "Data de publicação"
        timestamptz data_abertura "Data de abertura das propostas"
        timestamptz data_encerramento "Data de encerramento"
        int matched_entity_id FK "FK→sc_public_entities.id"
        text match_method "CNPJ, name_normalized, fuzzy"
        text match_confidence "high, medium, low"
        boolean is_active "Registro ativo (soft delete)"
        timestamptz ingested_at "Timestamp de ingestão"
        timestamptz enriched_at "Timestamp de enriquecimento"
    }

    pncp_supplier_contracts {
        text numero_controle_pncp PK "Número de controle PNCP (único)"
        text orgao_cnpj "CNPJ do órgão contratante"
        text orgao_cnpj8 "CNPJ raiz 8 dígitos — chave de join"
        text orgao_nome "Nome do órgão"
        text ni_fornecedor "CNPJ/CPF do fornecedor"
        text nome_fornecedor "Nome do fornecedor"
        text objeto_contrato "Objeto do contrato"
        numeric valor_global "Valor global (CONTRATADO, não 'preço praticado')"
        date data_assinatura "Data de assinatura"
        date data_fim_vigencia "Data de fim da vigência"
        date data_publicacao "Data de publicação no PNCP"
        text uf "UF inferida do CNPJ do órgão"
        text municipio "Município inferido"
        boolean is_active "Registro ativo"
        timestamptz ingested_at "Timestamp de ingestão"
        int orgao_entity_id FK "FK→sc_public_entities.id (resolvido)"
    }

    coverage_evidence {
        bigserial id PK "identificador interno"
        int entity_id FK "FK→sc_public_entities.id (pode ser NULL)"
        text source "Fonte de dados (pncp, contracts, etc.)"
        text data_type "Tipo de dado (bids, contracts)"
        date queried_start "Início da janela de consulta"
        date queried_end "Fim da janela de consulta"
        text run_id "ID da execução (UUID)"
        timestamptz started_at "Início da execução"
        timestamptz completed_at "Fim da execução"
        int count_obtained "Registros obtidos (0 = success_zero)"
        evidence_state state "Estado da evidência (enum)"
        text error_code "Código de erro (se houver)"
        text error_message "Mensagem de erro (se houver)"
        text applicability "Aplicabilidade da evidência"
        text notes "Notas adicionais"
        text git_sha "Git SHA do código que gerou"
        text schema_fingerprint "Hash do schema no momento"
    }

    evidence_state {
        text success_with_data "Crawl OK + dados obtidos"
        text success_zero "Crawl OK + zero registros"
        text partial "Crawl degraded (parcial)"
        text connection_failed "Falha de conexão/API"
        text auth_failed "Falha de autenticação"
        text parse_failed "Falha de parsing"
        text transform_failed "Falha de transformação"
        text persist_failed "Falha de persistência"
        text not_applicable "Fonte não aplicável/bloqueada"
        text not_investigated "Nunca investigada (DEFAULT)"
    }

    opportunity_intel {
        bigserial id PK "identificador interno"
        text opportunity_key UK "Hash único: source+source_id"
        text source "Fonte de origem"
        text source_id "ID na fonte"
        text source_ids "IDs em múltiplas fontes (dedup)"
        text official_url "URL oficial"
        int entity_id FK "FK→sc_public_entities.id"
        text orgao_cnpj "CNPJ do órgão"
        text orgao_nome "Nome do órgão"
        text municipio "Município"
        numeric distancia_km "Distância de Florianópolis"
        text objeto "Descrição do objeto"
        text categoria "Categoria inferida"
        text modalidade "Modalidade da licitação"
        numeric valor_estimado "Valor estimado"
        text valor_semantica "Estágio semântico do valor"
        date data_publicacao "Data de publicação"
        date data_abertura "Data de abertura"
        date data_encerramento "Data de encerramento"
        int dias_restantes "Dias até encerramento"
        text status_canonico "Status canônico (open/closed/unknown...)"
        text status_evidence "Evidência do status"
        text ranking "GO, REVIEW, NO_GO"
        int ranking_score "Score 0-100"
        int data_confidence_score "Confiança nos dados 0-100"
        int client_fit_score "Fit com perfil do cliente 0-100"
        text triage_recommendation "Recomendação de triagem"
        jsonb positive_factors "Fatores positivos"
        jsonb negative_factors "Fatores negativos"
        jsonb blockers "Bloqueadores disparados"
        jsonb missing_fields "Campos ausentes"
        timestamptz first_seen_at "Primeira visualização"
        timestamptz last_seen_at "Última visualização"
        text run_id "ID da execução QW-01"
        timestamptz generated_at "Data de geração"
        text git_sha "Git SHA"
        text seed_sha256 "SHA-256 da planilha seed"
        text schema_fingerprint "Hash do schema"
        boolean is_active "Registro ativo"
    }

    ingestion_runs {
        serial id PK "identificador interno"
        text source "Fonte executada"
        text mode "full ou incremental"
        text status "running, completed, failed"
        int records_fetched "Registros obtidos"
        int records_upserted "Registros inseridos/atualizados"
        text error_message "Mensagem de erro"
        timestamptz started_at "Início"
        timestamptz completed_at "Fim"
        text run_id "ID da execução"
    }

    ingestion_checkpoints {
        serial id PK "identificador interno"
        text source "Fonte"
        text last_cursor "Último cursor processado"
        date last_date "Última data processada"
        timestamptz updated_at "Atualização"
    }

    entity_coverage {
        serial id PK "identificador interno"
        int entity_id FK "FK→sc_public_entities"
        text source "Fonte"
        date last_seen_at "Última data com registro"
        boolean is_covered "Coberto nos últimos 90 dias?"
        timestamptz calculated_at "Data do cálculo"
    }
```

## Relacionamentos

| Origem | Destino | Cardinalidade | FK | Notas |
|--------|---------|:---:|-----|-------|
| sc_public_entities | pncp_raw_bids | 1:N | matched_entity_id | SET NULL on entity delete |
| sc_public_entities | coverage_evidence | 1:N | entity_id | Pode ser NULL (run sem entity match) |
| sc_public_entities | opportunity_intel | 1:N | entity_id | Pode ser NULL |
| pncp_raw_bids | pncp_supplier_contracts | 1:N | numero_controle_pncp | Nem todo bid tem contrato |
| ingestion_runs | coverage_evidence | 1:N | run_id | Uma run gera N evidências |
| ingestion_runs | ingestion_checkpoints | 1:N | source | Checkpoint por fonte |

## Views Analíticas

| View | Base | Propósito |
|------|------|-----------|
| `entity_coverage` | sc_public_entities + pncp_raw_bids | Trigger-maintained: entidade coberta se teve licitação em 90 dias |
| `coverage_summary` | coverage_evidence | Agregação: cobertura por source, data_type, state |
| `latest_evidence` | coverage_evidence | DISTINCT ON (entity_id, source, data_type): último estado por entidade |
| `vw_opportunity_ranking` | opportunity_intel | Ranking materializado: GO/REVIEW/NO_GO com scores |
| `vw_competitive_intel` | pncp_supplier_contracts + sc_public_entities | Fornecedores agregados por entidade |
| `readiness_dashboard` | coverage_evidence + sc_public_entities | Métricas de readiness: cobertura%, gaps, blockers |

## Índices Críticos

| Tabela | Índice | Tipo | Propósito |
|--------|--------|------|-----------|
| coverage_evidence | `idx_evidence_entity_source` | B-tree (entity_id, source, data_type) | Latest evidence query |
| coverage_evidence | `idx_evidence_run` | B-tree (run_id) | Run-level aggregation |
| coverage_evidence | `idx_evidence_state` | Partial (state = 'success_with_data') | Readiness metrics |
| opportunity_intel | `idx_oi_status_ranking` | B-tree (status_canonico, ranking) | List/filter queries |
| opportunity_intel | `idx_oi_entity` | B-tree (entity_id) | Entity-level queries |
| opportunity_intel | `idx_oi_opportunity_key` | UNIQUE (opportunity_key) | Dedup UPSERT |
| opportunity_intel | `idx_oi_numero_controle` | B-tree (numero_controle_pncp) | PNCP cross-reference |
| pncp_raw_bids | `idx_bids_objeto_gin` | GIN (objeto_compra) | Full-text search |
| pncp_raw_bids | `idx_bids_content_hash` | B-tree (content_hash) | Dedup lookup |
