# Fluxograma — Módulo Crawl

> Gerado pelo Archaeologist em 2026-07-11T21:00:00Z
> doc_level: completo
> Base: commit e9729e1

## Pipeline de Ingestão (orchestrator.py)

```mermaid
flowchart TD
    START(["crawl_source(source, entities, mode, dsn)"]) --> LOAD[Carrega entidades SC<br/>sc_public_entities<br/>raio_200km]
    LOAD --> CHECK_MODE{Modo?}
    CHECK_MODE -->|full| FETCH[Executa crawler.crawl('full')]
    CHECK_MODE -->|incremental| CHECKPOINT{is_crawl_completed_today?}
    CHECKPOINT -->|sim| SKIP[Retorna skipped_by_checkpoint=True]
    CHECKPOINT -->|não| FETCH_INC[Executa crawler.crawl('incremental')]
    FETCH --> TRANSFORM[Transforma registros<br/>crawler.transform(records)]
    FETCH_INC --> TRANSFORM
    TRANSFORM --> UPSERT{Source == 'contracts'?}
    UPSERT -->|sim| UPSERT_CTR[upsert_pncp_supplier_contracts<br/>ON CONFLICT contrato_id]
    UPSERT -->|não| UPSERT_BID[upsert_pncp_raw_bids<br/>ON CONFLICT content_hash]
    UPSERT_CTR --> SAVE_CHECK[Salva checkpoint<br/>save_checkpoint()]
    UPSERT_BID --> MATCH[Executa match_entities_cascade<br/>do módulo matching]
    MATCH --> SAVE_CHECK
    SAVE_CHECK --> FINISH[finish_ingestion_run<br/>status, fetched, upserted, covered]
    FINISH --> END(["Fim"])
```

## Entity Matching Cascade (matching/entity_matcher.py)

```mermaid
flowchart TD
    START(["match_entities_cascade(conn, source, entities)"]) --> FETCH_BIDS[Busca bids sem match<br/>WHERE matched_entity_id IS NULL]
    FETCH_BIDS --> BUILD_IDX[Constrói índices in-memory<br/>cnpj_index | name_exact_index<br/>name_muni_index (nome+ibge)]
    BUILD_IDX --> LOOP{"Para cada bid"}

    LOOP --> LV1{"CNPJ do órgão presente?"}
    LV1 -->|sim| CNPJ_MATCH[Busca cnpj_index<br/>8 dígitos → 14 dígitos]
    CNPJ_MATCH --> LV1_OK{"Match?"}
    LV1_OK -->|sim| SET1["method='cnpj' score=1.0 conf='high'"]

    LV1 -->|não| LV2
    LV1_OK -->|não| LV2{"Nome normalizado + município?"}
    LV2 -->|sim| NAME_MATCH[Busca name_muni_index<br/>(norm_name, codigo_ibge)<br/>→ fallback name_exact_index]
    NAME_MATCH --> LV2_OK{"Match?"}
    LV2_OK -->|sim| SET2["method='name_normalized' score=1.0 conf='high'"]

    LV2 -->|não| LV3
    LV2_OK -->|não| LV3[Fuzzy Matching<br/>rapidfuzz (preferido)<br/>ou difflib.SequenceMatcher]
    LV3 --> FUZZ[Calcula fuzz_ratio<br/>contra candidatos filtrados por IBGE]
    FUZZ --> BEST{"Melhor score ≥ 0.85?"}
    BEST -->|"≥ 0.95"| SET3H["method='fuzzy' conf='high'"]
    BEST -->|"≥ 0.85"| SET3M["method='fuzzy' conf='medium'"]
    BEST -->|não| SET4["method='unmatched' score=0.0"]

    SET1 --> UPDATE[UPDATE pncp_raw_bids<br/>SET matched_entity_id + metadata]
    SET2 --> UPDATE
    SET3H --> UPDATE
    SET3M --> UPDATE
    SET4 --> UPDATE
    UPDATE --> NEXT{"Próximo bid?"}
    NEXT -->|sim| LOOP
    NEXT -->|não| COMMIT["COMMIT<br/>retorna stats: cnpj, name, fuzzy, unmatched"]
    COMMIT --> END(["Fim"])
```

## Crawler Individual (ex: PNCP)

```mermaid
flowchart TD
    START(["crawl(mode)"]) --> DATES[Calcula date range<br/>full: 90 dias | incremental: 1 dia]
    DATES --> CHUNKS[Quebra em chunks diários<br/>14 dias por chunk]
    CHUNKS --> UF_LOOP{"Para cada UF (SC + 26)"}
    UF_LOOP --> MOD_LOOP{"Para cada modalidade (4,5,6,7)"}
    MOD_LOOP --> DAY_LOOP{"Para cada dia no chunk"}
    DAY_LOOP --> PAGE_LOOP{"Para cada página"}
    PAGE_LOOP --> FETCH[_fetch_page<br/>GET + query params<br/>User-Agent: Extra-Consultoria/1.0]
    FETCH --> RATE[AdaptiveRateLimiter.wait<br/>150ms base, 2s max]
    RATE --> CHECK{HTTP Status?}
    CHECK -->|200| PARSE[Parseia registros JSON<br/>extrai campos padronizados]
    CHECK -->|429| BACKOFF[Exponential backoff<br/>5s × (attempt+1)]
    BACKOFF --> RETRY{"attempt < MAX_RETRIES?"}
    RETRY -->|sim| FETCH
    RETRY -->|não| FAIL[Registra falha<br/>retorna dados parciais]
    CHECK -->|404/400| EMPTY[Retorna vazio<br/>fim dos dados]
    PARSE --> HAS_NEXT{"temProximaPagina?"}
    HAS_NEXT -->|sim| PAGE_LOOP
    HAS_NEXT -->|não| NEXT_DAY{"Próximo dia?"}
    NEXT_DAY -->|sim| DAY_LOOP
    NEXT_DAY -->|não| NEXT_MOD{"Próxima modalidade?"}
    NEXT_MOD -->|sim| MOD_LOOP
    NEXT_MOD -->|não| NEXT_UF{"Próxima UF?"}
    NEXT_UF -->|sim| UF_LOOP
    NEXT_UF -->|não| END(["Retorna records[]"])
```

## Transparência Templates (template-driven scraping)

```mermaid
flowchart TD
    START(["crawl(mode)"]) --> LOAD_ENT[Carrega entidades<br/>15 municípios principais SC]
    LOAD_ENT --> CONFIG[Carrega transparencia_config.yaml]
    CONFIG --> MUNI_LOOP{"Para cada município"}

    MUNI_LOOP --> DETECT[detect_platform(slug, municipio)]
    DETECT --> TRY_BETHA{"{slug}.atende.net?<br/>(Betha, ~80 municípios)"}
    TRY_BETHA -->|200| BETHA[Template Betha<br/>7 seletores CSS<br/>fallback div-based]
    TRY_BETHA -->|falha| TRY_IPAM{"{slug}.ipm.org.br?<br/>(Ipam, ~50 municípios)"}
    TRY_IPAM -->|200| IPAM[Template Ipam<br/>7 seletores CSS<br/>fallback genérico]
    TRY_IPAM -->|falha| TRY_EGOV{"{slug}.e-gov.betha.com.br?<br/>(E-gov, ~40 municípios)"}
    TRY_EGOV -->|200| EGOV[Template E-gov<br/>div.lista-licitacoes<br/>fallback tabela]
    TRY_EGOV -->|falha| GENERIC[Template Genérico<br/>3 níveis:]
    GENERIC --> G1[1. Score tabelas por keywords<br/>12 keywords de licitação]
    G1 --> G2[2. Div-based extraction<br/>classes/ids de licitação]
    G2 --> G3[3. Any table ≥ 3 linhas]

    BETHA --> SCRAPE[scrape_municipio<br/>BeautifulSoup + seletores]
    IPAM --> SCRAPE
    EGOV --> SCRAPE
    GENERIC --> SCRAPE

    SCRAPE --> EXTRACT[Extrai linhas<br/>_extract_row(tr, selectors)]
    EXTRACT --> RECORD[make_record<br/>modalidade, data, objeto,<br/>órgão, valor, link]
    RECORD --> NEXT_MUNI{"Próximo município?"}
    NEXT_MUNI -->|sim| MUNI_LOOP
    NEXT_MUNI -->|não| END(["Retorna records[]"])

    style G1 fill:#f9f,stroke:#333
    style G2 fill:#f9f,stroke:#333
    style G3 fill:#f9f,stroke:#333
```
