# Story 1.2 — Canonical Views Contract

**Documento:** Contrato das 5 views canonicas (Secao 6.2 do Plano Mestre)
**Data:** 2026-07-13
**Versao:** 1.0

---

## Principios

1. **Estabilidade:** Nomes de colunas NAO mudam sem major version bump e atualizacao de todos os consumers.
2. **Idempotencia:** CREATE OR REPLACE VIEW — seguro para reaplicacao.
3. **Performance:** Views otimizadas para os usos conhecidos (consulting_readiness, intel_pipeline, opportunity_intel).
4. **Rastreabilidade:** Cada view tem COMMENT com versao e responsavel.

---

## View 1: `v_entities_canonical`

**Proposito:** Visao unificada e estavel de todas as entidades publicas de SC (municipios, orgaos, entidades).

```sql
CREATE OR REPLACE VIEW public.v_entities_canonical AS
SELECT
    e.id               AS entity_id,
    e.cnpj_8           AS cnpj_8_base,
    e.razao_social     AS razao_social,
    e.municipio        AS municipio,
    e.codigo_ibge      AS codigo_ibge,
    e.natureza_juridica AS natureza_juridica,
    e.cod_natureza     AS cod_natureza,
    e.latitude,
    e.longitude,
    e.distancia_fk     AS distancia_fk,
    e.raio_200km       AS within_200km,
    ec.total_bids      AS total_bids,
    ec.matched_bids    AS matched_bids,
    ec.is_covered      AS is_covered,
    ec.last_seen_at    AS last_coverage_at
FROM public.sc_public_entities e
LEFT JOIN public.entity_coverage ec ON ec.entity_id = e.id AND ec.source = 'pncp';
```

**Colunas:**
| Coluna | Origem | Tipo | NotNull |
|--------|--------|------|---------|
| entity_id | sc_public_entities.id | INTEGER | YES |
| cnpj_8_base | sc_public_entities.cnpj_8 | TEXT | YES |
| razao_social | sc_public_entities.razao_social | TEXT | YES |
| municipio | sc_public_entities.municipio | TEXT | NO |
| codigo_ibge | sc_public_entities.codigo_ibge | TEXT | NO |
| natureza_juridica | sc_public_entities.natureza_juridica | TEXT | NO |
| cod_natureza | sc_public_entities.cod_natureza | TEXT | NO |
| latitude | sc_public_entities.latitude | DOUBLE | NO |
| longitude | sc_public_entities.longitude | DOUBLE | NO |
| distancia_fk | sc_public_entities.distancia_fk | DOUBLE | NO |
| within_200km | sc_public_entities.raio_200km | BOOLEAN | YES |
| total_bids | entity_coverage.total_bids | INTEGER | NO |
| matched_bids | entity_coverage.matched_bids | INTEGER | NO |
| is_covered | entity_coverage.is_covered | BOOLEAN | NO |
| last_coverage_at | entity_coverage.last_seen_at | TIMESTAMPTZ | NO |

**Consumers:** consulting_readiness.py, coverage_truth.py, intel_pipeline.py

---

## View 2: `v_open_opportunities_canonical`

**Proposito:** Oportunidades abertas (licitacoes) com dados normalizados e geo-referenciados.

```sql
CREATE OR REPLACE VIEW public.v_open_opportunities_canonical AS
SELECT
    b.id                AS bid_id,
    b.pncp_id           AS pncp_id,
    b.objeto_compra     AS objeto,
    b.valor_total_estimado AS valor_estimado,
    b.modalidade_id,
    b.modalidade_nome   AS modalidade,
    b.esfera_id         AS esfera_id,
    b.uf,
    b.municipio,
    b.codigo_municipio_ibge AS codigo_ibge,
    b.orgao_cnpj,
    b.orgao_razao_social AS orgao_nome,
    b.data_publicacao,
    b.data_abertura,
    b.data_encerramento,
    b.link_pncp         AS link_edital,
    b.source,
    b.source_id,
    b.match_method,
    b.match_score,
    b.match_confidence,
    e.id                AS matched_entity_id,
    e.razao_social      AS matched_entity_nome,
    e.raio_200km        AS within_200km
FROM public.pncp_raw_bids b
LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
WHERE b.data_encerramento >= CURRENT_DATE
   OR (b.data_encerramento IS NULL AND b.data_publicacao >= CURRENT_DATE - INTERVAL '30 days');
```

**Colunas:** Conforme SELECT acima.

**Consumers:** opportunity_intel pipeline, ranking, radar

---

## View 3: `v_contracts_canonical`

**Proposito:** Contratos de fornecedores com dados de entidades e classificacao.

```sql
CREATE OR REPLACE VIEW public.v_contracts_canonical AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato   AS objeto,
    c.valor_total       AS valor,
    c.data_inicio,
    c.data_fim,
    c.data_publicacao,
    c.uf,
    c.municipio,
    c.codigo_municipio_ibge,
    c.municipio_inferido,
    c.source,
    c.source_id,
    e.id                AS entity_id,
    e.razao_social      AS entity_nome,
    e.cnpj_8            AS entity_cnpj_8,
    e.raio_200km        AS within_200km,
    enr.cnae_principal,
    enr.natureza_juridica
FROM public.pncp_supplier_contracts c
LEFT JOIN public.sc_public_entities e ON e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
LEFT JOIN public.enriched_entities enr ON enr.cnpj = c.fornecedor_cnpj;
```

**Colunas:** Conforme SELECT acima.

**Consumers:** consulting_readiness.py (market share, HHI), contract_intel CLI

---

## View 4: `v_suppliers_canonical`

**Proposito:** Cadastro unificado de fornecedores com metadados de contratos e entidades.

```sql
CREATE OR REPLACE VIEW public.v_suppliers_canonical AS
SELECT
    e.cnpj                       AS cnpj_completo,
    e.razao_social,
    e.nome_fantasia,
    e.cnae_principal,
    e.cnae_secundarios,
    e.municipio,
    e.uf,
    e.codigo_ibge,
    e.natureza_juridica,
    e.situacao,
    e.enriched_at                AS ultima_atualizacao,
    e.enriched_source,
    sc.cnpj_8                    AS entidade_cnpj_8,
    sc.razao_social              AS entidade_nome,
    sc.raio_200km                AS within_200km,
    COUNT(DISTINCT c.contrato_id) AS total_contratos,
    SUM(c.valor_total)           AS valor_total_contratos
FROM public.enriched_entities e
LEFT JOIN public.sc_public_entities sc ON sc.cnpj_8 = LEFT(e.cnpj, 8)
LEFT JOIN public.pncp_supplier_contracts c ON c.fornecedor_cnpj = e.cnpj AND c.is_active = TRUE
GROUP BY e.cnpj, e.razao_social, e.nome_fantasia, e.cnae_principal,
         e.cnae_secundarios, e.municipio, e.uf, e.codigo_ibge,
         e.natureza_juridica, e.situacao, e.enriched_at, e.enriched_source,
         sc.cnpj_8, sc.razao_social, sc.raio_200km;
```

**Colunas:** Conforme SELECT acima.

**Consumers:** intel pipeline, report generation

---

## View 5: `v_value_observations_canonical`

**Proposito:** Observacoes de valor para analise estatistica (bid simulation, precificacao).

```sql
CREATE OR REPLACE VIEW public.v_value_observations_canonical AS
SELECT
    'bid'::TEXT                    AS observation_type,
    b.id                           AS source_id,
    b.orgao_cnpj,
    b.municipio,
    b.uf,
    b.modalidade_id,
    b.modalidade_nome              AS modalidade,
    b.objeto_compra                AS objeto,
    b.valor_total_estimado         AS valor,
    b.data_publicacao,
    e.cnpj_8                       AS entity_cnpj_8,
    e.raio_200km                   AS within_200km
FROM public.pncp_raw_bids b
LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
WHERE b.valor_total_estimado IS NOT NULL AND b.valor_total_estimado > 0

UNION ALL

SELECT
    'contract'::TEXT               AS observation_type,
    c.contrato_id                  AS source_id,
    c.orgao_cnpj,
    c.municipio,
    c.uf,
    NULL::INTEGER                  AS modalidade_id,
    NULL::TEXT                     AS modalidade,
    c.objeto_contrato              AS objeto,
    c.valor_total                  AS valor,
    c.data_publicacao,
    e.cnpj_8                       AS entity_cnpj_8,
    e.raio_200km                   AS within_200km
FROM public.pncp_supplier_contracts c
LEFT JOIN public.sc_public_entities e ON e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
WHERE c.valor_total IS NOT NULL AND c.valor_total > 0;
```

**Colunas:**
| Coluna | Tipo | Origem |
|--------|------|--------|
| observation_type | TEXT | 'bid' ou 'contract' |
| source_id | TEXT | PK da origem |
| orgao_cnpj | TEXT | Orgao contratante |
| municipio | TEXT | Municipio |
| uf | TEXT | UF |
| modalidade_id | INT | Modalidade (bids only) |
| modalidade | TEXT | Nome da modalidade |
| objeto | TEXT | Descricao do objeto |
| valor | NUMERIC | Valor estimado/contratado |
| data_publicacao | DATE | Data de publicacao |
| entity_cnpj_8 | TEXT | CNPJ base da entidade |
| within_200km | BOOLEAN | Raio 200km |

**Consumers:** lib/bid_simulator.py, lib/value_semantics.py, intel pipeline

---

## Versionamento

| Versao | Data | Mudancas | Autor |
|--------|------|----------|-------|
| 1.0 | 2026-07-13 | Definicao inicial das 5 views canonicas | @dev (Story 1.2) |

## Regras de Evolucao

1. **ADD** colunas novas: sempre com valor DEFAULT NULL para nao quebrar consumers existentes.
2. **REMOVE** colunas: proibido sem major version bump e migracao de todos os consumers.
3. **RENAME** colunas: proibido. Criar nova coluna e depreciar a antiga com COMMENT.
4. **CHANGE** tipo: permitido apenas se o novo tipo for coercivel (ex: VARCHAR → TEXT).
5. **DEPRECIACAO**: adicionar `deprecated_since` no COMMENT da coluna, manter por 2 sprints.
