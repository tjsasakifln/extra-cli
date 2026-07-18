# Multi-Source Coverage Report

**run_id:** `r2-n05`
**calc_date:** 2026-07-18
**generated_at:** 2026-07-18T20:57:05.248011+00:00
**window_days:** 30
**as_of:** 2026-07-18

## Methodology

- Approach: `multi_source_file_artifacts_v1`
- Historical metric policy: **preserve_separately** (`historical_editais_raw_coverage` = 4.76%)
- SC municipality universe: 295

> Do **not** compare new multi-source % values to the historical 4.76% without re-basing denominators.

## Global limitations

- All metrics are file-artifact based for this session; they may under-represent full portal coverage when runs are smoke/incremental.
- historical_editais_raw_coverage (4.76%) is preserved with its original 52/1093 methodology and must not be replaced by multi-source percentages.
- Denominators differ by metric (295 municipios vs 1093 entities vs API year totals) — never mix without re-basing.
- No live DB queries are performed by this module.
- Window used for recency metrics: 30 days ending 2026-07-18.

## Metrics summary

| Metric | Result | Numerator | Denominator | Confidence | Unit |
|--------|--------|-----------|-------------|------------|------|
| `historical_editais_raw_coverage` | 4.76 | 52 | 1093 | high | pct |
| `municipalities_with_publication_30d` | 94.58 | 279 | 295 | medium | pct |
| `orgs_with_recent_licitacao` | 43.09 | 471 | 1093 | medium | pct |
| `pncp_sc_reconciled` | 28.27 | 309 | 1093 | low | pct |
| `source_coverage_dados_abertos_sc` | 1.22 | 500 | 41080 | low | pct |
| `source_coverage_ciga_dom` | 94.58 | 279 | 295 | medium | pct |
| `source_coverage_sc_compras` | 0.0 | 0 | 2602 | medium | pct |
| `source_coverage_pncp` | 4.76 | 52 | 1093 | medium | pct |
| `temporal_coverage_ciga_dom` | 19.35 | 6 | 31 | medium | pct |
| `temporal_coverage_sc_compras` | 0.0 | 0 | 31 | none | pct |
| `temporal_coverage_dados_abertos_sc` | 0.0 | 0 | 31 | medium | pct |
| `act_category_distribution_ciga_dom` | 100.0 | 19 | 19 | medium | pct |
| `act_category_distribution_dados_abertos_sc` | 94.74 | 18 | 19 | medium | pct |
| `field_completeness_ciga_dom` | 94.58 | 67414 | 71274 | high | pct |
| `field_completeness_sc_compras` | n/a | 0 | 0 | none | pct |
| `field_completeness_dados_abertos_sc` | 75.0 | 3000 | 4000 | high | pct |
| `document_coverage_ciga_dom` | 100.0 | 10182 | 10182 | high | pct |
| `document_coverage_sc_compras` | n/a | 0 | None | none | pct |
| `document_coverage_dados_abertos_sc` | 0.0 | 0 | 500 | high | pct |
| `freshness_hours_ciga_dom` | 34.07 | 34.07 | 1 | high | hours |
| `freshness_hours_sc_compras` | 34.08 | 34.08 | 1 | high | hours |
| `freshness_hours_dados_abertos_sc` | 42.72 | 42.72 | 1 | high | hours |
| `freshness_hours_pncp` | 0.61 | 0.61 | 1 | high | hours |

## Metric details

### `historical_editais_raw_coverage`

- **result:** 4.76 (pct)
- **numerator:** 52
- **denominator:** 1093
- **formula:** entities_with_bids / total_entities_within_200km * 100
- **period:** snapshot as of 2026-07-17 (entity_coverage, radius 200 km FLN)
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/coverage/next30d-metrics-final.json`
  - `output/coverage/next30d-metrics-final.json`
  - `output/sc_compras/coverage-truth/coverage-truth-2026-07-16.json`
- **limitations:**
  - PRESERVED historical metric. Denominator = target_universe entities within 200 km of Florianópolis (1093). Numerator = entities with ≥1 persisted bid in entity_coverage (52). This is NOT municipal publication coverage and must not be conflated with municipalities_with_publication_30d or multi-source artifact metrics produced by this module.
  - New multi-source metrics use different denominators (295 IBGE municipios, artifact-local org sets, API totals). Comparing them to 4.76% is invalid.
  - Evidence ledger was empty at truth generation; bid presence uses entity_coverage only.
- **extras:**
  - preserved: `True`
  - canonical_result_pct: `4.76`
  - do_not_overwrite: `True`
  - denominator_definition: `1093 = public entities in target universe within 200 km of Florianópolis`
  - numerator_definition: `52 = entities with ≥1 persisted bid (entity_coverage.total_bids)`

### `municipalities_with_publication_30d`

- **result:** 94.58 (pct)
- **numerator:** 279
- **denominator:** 295
- **formula:** count(distinct municipio with pub date in [as_of-window, as_of] matched to IBGE SC universe) / len(ibge_cache SC municipios)
- **period:** last 30d ending 2026-07-18 (business date of publication)
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl`
  - `/mnt/d/extra consultoria/output/ciga_dom/latest_summary.json`
  - `/mnt/d/extra consultoria/data/ibge_cache.json`
- **limitations:**
  - Numerator is municipalities with ≥1 collected CIGA DOM publication in the window — not proof that the municipality published something every day.
  - Smoke/partial CIGA runs process only selected resources; full package has more ZIPs.
  - Name matching is accent-insensitive but may miss exotic spelling variants.
  - Other sources (dados_abertos_sc, sc_compras) are not included in this municipal metric because they lack reliable IBGE municipality linkage in the current artifacts.
- **extras:**
  - window_start: `2026-06-18`
  - window_end: `2026-07-18`
  - observed_municipios_all_time_in_artifact: `281`
  - observed_municipios_in_window: `281`
  - matched_to_ibge_in_window: `279`
  - unmatched_name_samples: `["Herval d'Oeste", "Herval d'Oeste", "Herval d'Oeste", "Herval d'Oeste", "Herval d'Oeste", "Herval d'Oeste", "Herval d'Oeste", "Herval d'Oeste", "Herval d'Oeste", "Herval d'Oeste"]`
  - universe_source: `data/ibge_cache.json`
  - primary_source: `ciga_dom`

### `orgs_with_recent_licitacao`

- **result:** 43.09 (pct)
- **numerator:** 471
- **denominator:** 1093
- **formula:** count(distinct org with ≥1 recent bid/procurement signal) / expected_public_orgs_universe
- **period:** last 30d ending 2026-07-18
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/licitacoes.jsonl`
  - `/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl`
  - `/mnt/d/extra consultoria/data/normalized/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/dados-sc-smoke-20260717T021337Z-f4cfe4b907.jsonl`
  - `/mnt/d/extra consultoria/output/coverage/next30d-metrics-final.json`
- **limitations:**
  - Org identity is string-normalized name (or CNPJ when present); no entity resolver applied.
  - Denominator is the 200 km target-universe entity set, while numerator mixes statewide artifact orgs (CIGA/DOM SC + sc_compras + DOE sample) — geographic scopes differ.
  - CIGA/dados contribute only procurement-classified acts; classifier false negatives omit orgs.
  - sc_compras artifact is incremental/smoke-sized (page-limited), not full portal history.
  - This metric is intentionally SEPARATE from historical_editais_raw_coverage (4.76%).
- **extras:**
  - universe_definition: `target universe entities within 200 km of Florianópolis (same denominator family as historical 4.76%)`
  - universe_source: `/mnt/d/extra consultoria/output/coverage/next30d-metrics-final.json`
  - orgs_by_source: `{'sc_compras': 0, 'ciga_dom': 471, 'dados_abertos_sc': 0}`
  - scope_note: `numerator multi-source artifacts; denominator 200km target universe`

### `pncp_sc_reconciled`

- **result:** 28.27 (pct)
- **numerator:** 309
- **denominator:** 1093
- **formula:** FOUND_EXACT entities with PNCP opportunity data / confirmed target universe (entity-level proxy; NOT PNCP-record↔municipal-record join)
- **period:** snapshot 2026-07-15
- **confidence:** low
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/readiness/target-reconciliation-summary.json`
- **limitations:**
  - No record-level PNCP↔state/municipal join artifact found under output/reconciliation/.
  - Using entity-level FOUND_EXACT vs target universe as a PROXY only.
  - Do not interpret this as municipal publication coverage or as the historical 4.76% metric.
- **extras:**
  - reconciliation_mode: `target-reconciliation-summary entity proxy`
  - spreadsheet_total_rows: `2085`

### `source_coverage_dados_abertos_sc`

- **result:** 1.22 (pct)
- **numerator:** 500
- **denominator:** 41080
- **formula:** rows_normalized_in_run / estimated_rows_in_selected_resource_csv
- **period:** mode=smoke; resource subset of package diario-oficial-sc-publicacoes
- **confidence:** low
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/dados_abertos_sc/smoke-dados-sc-smoke-20260717T021337Z-f4cfe4b907.json`
  - `/mnt/d/extra consultoria/data/normalized/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/dados-sc-smoke-20260717T021337Z-f4cfe4b907.jsonl`
- **limitations:**
  - Raw CSV line count is approximate (fields may contain embedded newlines).
  - Smoke mode processes only first N rows of one resource (sample, not full DOE).
  - Source coverage for 'dados_abertos_sc' uses a source-specific denominator; do not average blindly.
- **extras:**
  - source: `dados_abertos_sc`
  - raw_csv_path: `/mnt/d/extra consultoria/data/raw/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/body.csv`
  - denominator_method: `approx_line_count_raw_csv`
  - rows_normalized: `500`
  - resources_selected: `1`
  - resources_listed: `14`

### `source_coverage_ciga_dom`

- **result:** 94.58 (pct)
- **numerator:** 279
- **denominator:** 295
- **formula:** distinct municipios observed in CIGA DOM artifact ∩ IBGE SC / 295
- **period:** publication dates present in current CIGA artifact (may be single-day smoke)
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/ciga_dom/latest_summary.json`
  - `/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl`
  - `/mnt/d/extra consultoria/output/ciga_dom/freshness_manifest.json`
- **limitations:**
  - Smoke runs process subset of monthly package resources.
  - Observed municipio without IBGE match is excluded from numerator.
  - Source coverage for 'ciga_dom' uses a source-specific denominator; do not average blindly.
- **extras:**
  - source: `ciga_dom`
  - records: `10182`
  - observed_municipios: `281`
  - run_mode: `incremental`
  - summary_counts: `{'resources_available': 45, 'zips_available': 45, 'selected': 15, 'completed_resources_prior': 15, 'resources_processed_ok': 15, 'resources_failed': 0, 'resources_skipped_checkpoint': 0, 'files_processed': 15, 'files_skipped_checkpoint': 0, 'records_normalized': 10182, 'municipalities_observed': 281}`

### `source_coverage_sc_compras`

- **result:** 0.0 (pct)
- **numerator:** 0
- **denominator:** 2602
- **formula:** records_normalized_in_run / api_total_elementos_reported (year filter)
- **period:** API year filter=2026; mode=incremental
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/artifact.json`
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/licitacoes.jsonl`
- **limitations:**
  - Denominator is live API total for the requested year filter only — not full historical portal.
  - Incremental/smoke page limits mean numerator is a sample of denominator.
  - Source coverage for 'sc_compras' uses a source-specific denominator; do not average blindly.
- **extras:**
  - source: `sc_compras`
  - api_total_elementos_reported: `2602`
  - records_normalized: `0`
  - coverage_claim: `api_total_elementos is live metadata for the requested year filter only; not claimed as full portal historical coverage`

### `source_coverage_pncp`

- **result:** 4.76 (pct)
- **numerator:** 52
- **denominator:** 1093
- **formula:** entities_with_persisted_pncp_bids / target_universe_200km
- **period:** datalake snapshot 2026-07-17
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/readiness/freshness-gate.json`
  - `/mnt/d/extra consultoria/output/coverage/next30d-metrics-final.json`
- **limitations:**
  - This is entity bid-presence from next30d metrics — same family as historical 4.76%, reported here under source=pncp for cross-source comparison, NOT a new methodology.
  - Source coverage for 'pncp' uses a source-specific denominator; do not average blindly.
- **extras:**
  - source: `pncp`
  - pncp_raw_bids: `2948`
  - covered_200km_entities: `52`
  - editais_denominator: `1093`

### `temporal_coverage_ciga_dom`

- **result:** 19.35 (pct)
- **numerator:** 6
- **denominator:** 31
- **formula:** distinct calendar days with ≥1 record in window / (window_days+1 inclusive)
- **period:** last 30d ending 2026-07-18
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl`
  - `/mnt/d/extra consultoria/output/ciga_dom/latest_summary.json`
- **limitations:**
  - Measures day-level presence of collected records, not publication completeness of the source.
  - Smoke artifacts often cover a single day → low temporal coverage even if source is healthy.
- **extras:**
  - min_date: `2026-07-01`
  - max_date: `2026-07-06`
  - min_date_in_window: `2026-07-01`
  - max_date_in_window: `2026-07-06`
  - records_with_date: `10182`
  - records_in_window: `10182`

### `temporal_coverage_sc_compras`

- **result:** 0.0 (pct)
- **numerator:** 0
- **denominator:** 31
- **formula:** distinct calendar days with ≥1 record in window / days_in_window
- **period:** last 30d ending 2026-07-18
- **confidence:** none
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/licitacoes.jsonl`
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/artifact.json`
- **limitations:**
  - No parseable dates in artifact records.
- **extras:**
  - records_with_date: `0`

### `temporal_coverage_dados_abertos_sc`

- **result:** 0.0 (pct)
- **numerator:** 0
- **denominator:** 31
- **formula:** distinct calendar days with ≥1 record in window / (window_days+1 inclusive)
- **period:** last 30d ending 2026-07-18
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/data/normalized/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/dados-sc-smoke-20260717T021337Z-f4cfe4b907.jsonl`
  - `/mnt/d/extra consultoria/output/dados_abertos_sc/smoke-dados-sc-smoke-20260717T021337Z-f4cfe4b907.json`
- **limitations:**
  - Measures day-level presence of collected records, not publication completeness of the source.
  - Smoke artifacts often cover a single day → low temporal coverage even if source is healthy.
- **extras:**
  - min_date: `2025-04-01`
  - max_date: `2025-07-01`
  - records_with_date: `500`
  - records_in_window: `0`

### `act_category_distribution_ciga_dom`

- **result:** 100.0 (pct)
- **numerator:** 19
- **denominator:** 19
- **formula:** distinct procurement act_category labels observed / |PROCUREMENT_ACT_CATEGORIES|
- **period:** artifact snapshot
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl`
  - `/mnt/d/extra consultoria/output/ciga_dom/latest_summary.json`
- **limitations:**
  - Distribution reflects classifier output on collected sample, not true publication mix.
  - Taxonomy size=19; residual labels (outros, nao_relacionado, etc.) excluded from numerator.
  - Counts origin: records.
- **extras:**
  - total_records_classified: `10182`
  - procurement_categories_observed: `['anulacao', 'apostilamento', 'ata_registro_precos', 'aviso_licitacao', 'chamamento_publico', 'credenciamento', 'dispensa', 'edital', 'errata', 'extrato_contrato', 'homologacao', 'inexigibilidade', 'outros_atos_contratacao', 'rescisao', 'resultado', 'retificacao', 'revogacao', 'suspensao', 'termo_aditivo']`
  - non_procurement_share_pct: `28.92`
- **distribution (top 15):**
  - ata_registro_precos: {'count': 3942, 'pct': 38.72}
  - outros: {'count': 2635, 'pct': 25.88}
  - outros_atos_contratacao: {'count': 949, 'pct': 9.32}
  - homologacao: {'count': 618, 'pct': 6.07}
  - termo_aditivo: {'count': 409, 'pct': 4.02}
  - extrato_contrato: {'count': 386, 'pct': 3.79}
  - nao_relacionado: {'count': 303, 'pct': 2.98}
  - dispensa: {'count': 193, 'pct': 1.9}
  - inexigibilidade: {'count': 191, 'pct': 1.88}
  - aviso_licitacao: {'count': 161, 'pct': 1.58}
  - chamamento_publico: {'count': 71, 'pct': 0.7}
  - credenciamento: {'count': 63, 'pct': 0.62}
  - edital: {'count': 59, 'pct': 0.58}
  - errata: {'count': 50, 'pct': 0.49}
  - retificacao: {'count': 47, 'pct': 0.46}

### `act_category_distribution_dados_abertos_sc`

- **result:** 94.74 (pct)
- **numerator:** 18
- **denominator:** 19
- **formula:** distinct procurement act_category labels observed / |PROCUREMENT_ACT_CATEGORIES|
- **period:** artifact snapshot
- **confidence:** medium
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/data/normalized/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/dados-sc-smoke-20260717T021337Z-f4cfe4b907.jsonl`
  - `/mnt/d/extra consultoria/output/dados_abertos_sc/smoke-dados-sc-smoke-20260717T021337Z-f4cfe4b907.json`
- **limitations:**
  - Distribution reflects classifier output on collected sample, not true publication mix.
  - Taxonomy size=19; residual labels (outros, nao_relacionado, etc.) excluded from numerator.
  - Counts origin: records.
- **extras:**
  - total_records_classified: `500`
  - procurement_categories_observed: `['anulacao', 'apostilamento', 'ata_registro_precos', 'aviso_licitacao', 'chamamento_publico', 'credenciamento', 'dispensa', 'edital', 'errata', 'extrato_contrato', 'homologacao', 'inexigibilidade', 'outros_atos_contratacao', 'rescisao', 'resultado', 'revogacao', 'suspensao', 'termo_aditivo']`
  - non_procurement_share_pct: `34.0`
- **distribution (top 15):**
  - outros: {'count': 144, 'pct': 28.8}
  - outros_atos_contratacao: {'count': 92, 'pct': 18.4}
  - suspensao: {'count': 57, 'pct': 11.4}
  - extrato_contrato: {'count': 46, 'pct': 9.2}
  - termo_aditivo: {'count': 33, 'pct': 6.6}
  - nao_relacionado: {'count': 26, 'pct': 5.2}
  - resultado: {'count': 26, 'pct': 5.2}
  - aviso_licitacao: {'count': 19, 'pct': 3.8}
  - ata_registro_precos: {'count': 13, 'pct': 2.6}
  - edital: {'count': 7, 'pct': 1.4}
  - homologacao: {'count': 7, 'pct': 1.4}
  - inexigibilidade: {'count': 7, 'pct': 1.4}
  - rescisao: {'count': 6, 'pct': 1.2}
  - anulacao: {'count': 3, 'pct': 0.6}
  - chamamento_publico: {'count': 3, 'pct': 0.6}

### `field_completeness_ciga_dom`

- **result:** 94.58 (pct)
- **numerator:** 67414
- **denominator:** 71274
- **formula:** sum(nonempty field cells) / (n_records * n_core_fields)
- **period:** artifact snapshot
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl`
  - `/mnt/d/extra consultoria/output/ciga_dom/latest_summary.json`
- **limitations:**
  - Core field set is project-defined, not a legal completeness standard.
  - Empty string / null / empty list count as missing.
- **extras:**
  - n_records: `10182`
  - fields: `['municipio', 'orgao', 'data', 'titulo', 'url', 'act_category', 'texto']`
  - mean_field_fill_pct: `94.58`
- **per_field:**
  - municipio: {'filled': 6322, 'total': 10182, 'pct': 62.09}
  - orgao: {'filled': 10182, 'total': 10182, 'pct': 100.0}
  - data: {'filled': 10182, 'total': 10182, 'pct': 100.0}
  - titulo: {'filled': 10182, 'total': 10182, 'pct': 100.0}
  - url: {'filled': 10182, 'total': 10182, 'pct': 100.0}
  - act_category: {'filled': 10182, 'total': 10182, 'pct': 100.0}
  - texto: {'filled': 10182, 'total': 10182, 'pct': 100.0}

### `field_completeness_sc_compras`

- **result:** None (pct)
- **numerator:** 0
- **denominator:** 0
- **formula:** mean over fields of (nonempty_count / n_records); reported as overall fill rate
- **period:** artifact snapshot
- **confidence:** none
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/licitacoes.jsonl`
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/artifact.json`
- **limitations:**
  - No records available.
- **extras:**
  - n_records: `0`
- **per_field:**

### `field_completeness_dados_abertos_sc`

- **result:** 75.0 (pct)
- **numerator:** 3000
- **denominator:** 4000
- **formula:** sum(nonempty field cells) / (n_records * n_core_fields)
- **period:** artifact snapshot
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/data/normalized/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/dados-sc-smoke-20260717T021337Z-f4cfe4b907.jsonl`
  - `/mnt/d/extra consultoria/output/dados_abertos_sc/smoke-dados-sc-smoke-20260717T021337Z-f4cfe4b907.json`
- **limitations:**
  - Core field set is project-defined, not a legal completeness standard.
  - Empty string / null / empty list count as missing.
- **extras:**
  - n_records: `500`
  - fields: `['orgao', 'titulo', 'data_publicacao', 'tipo_ato', 'act_category', 'texto_ou_extrato', 'link_edicao', 'link_extrato']`
  - mean_field_fill_pct: `75.0`
- **per_field:**
  - orgao: {'filled': 500, 'total': 500, 'pct': 100.0}
  - titulo: {'filled': 500, 'total': 500, 'pct': 100.0}
  - data_publicacao: {'filled': 500, 'total': 500, 'pct': 100.0}
  - tipo_ato: {'filled': 500, 'total': 500, 'pct': 100.0}
  - act_category: {'filled': 500, 'total': 500, 'pct': 100.0}
  - texto_ou_extrato: {'filled': 500, 'total': 500, 'pct': 100.0}
  - link_edicao: {'filled': 0, 'total': 500, 'pct': 0.0}
  - link_extrato: {'filled': 0, 'total': 500, 'pct': 0.0}

### `document_coverage_ciga_dom`

- **result:** 100.0 (pct)
- **numerator:** 10182
- **denominator:** 10182
- **formula:** records with ≥1 document/link field populated / n_records
- **period:** artifact snapshot
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl`
  - `/mnt/d/extra consultoria/output/ciga_dom/latest_summary.json`
- **limitations:**
  - Presence of URL/link only — does not verify HTTP reachability or PDF parseability.
  - Link fields checked: ['url']
- **extras:**
  - link_keys: `['url']`
  - n_records: `10182`

### `document_coverage_sc_compras`

- **result:** None (pct)
- **numerator:** 0
- **denominator:** None
- **formula:** records with ≥1 document/link field populated / n_records
- **period:** artifact snapshot
- **confidence:** none
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/licitacoes.jsonl`
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/artifact.json`
- **limitations:**
  - Presence of URL/link only — does not verify HTTP reachability or PDF parseability.
  - Link fields checked: ['link_pncp', 'documentos']
- **extras:**
  - link_keys: `['link_pncp', 'documentos']`
  - n_records: `0`

### `document_coverage_dados_abertos_sc`

- **result:** 0.0 (pct)
- **numerator:** 0
- **denominator:** 500
- **formula:** records with ≥1 document/link field populated / n_records
- **period:** artifact snapshot
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/data/normalized/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/dados-sc-smoke-20260717T021337Z-f4cfe4b907.jsonl`
  - `/mnt/d/extra consultoria/output/dados_abertos_sc/smoke-dados-sc-smoke-20260717T021337Z-f4cfe4b907.json`
- **limitations:**
  - Presence of URL/link only — does not verify HTTP reachability or PDF parseability.
  - Link fields checked: ['link_edicao', 'link_extrato']
- **extras:**
  - link_keys: `['link_edicao', 'link_extrato']`
  - n_records: `500`

### `freshness_hours_ciga_dom`

- **result:** 34.07 (hours)
- **numerator:** 34.07
- **denominator:** 1
- **formula:** (now_utc - last_collection_completed_at).total_seconds()/3600
- **period:** as of 2026-07-18T20:57:05.248011+00:00
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/ciga_dom/latest_summary.json`
  - `/mnt/d/extra consultoria/output/ciga_dom/freshness_manifest.json`
  - `/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl`
- **limitations:**
  - freshness_hours is wall-clock age of last collection completion (or business date fallback).
  - Negative business-date age can occur when max data_publicacao is in the future (planned openings).
  - Does not prove downstream DB persistence — file artifact only.
- **extras:**
  - last_collection_at: `2026-07-17T10:52:51.560906+00:00`
  - latest_business_date: `2026-07-17`
  - hours_since_collection: `34.07`
  - hours_since_latest_business_date: `44.95`
  - method: `summary.completed_at + freshness_manifest.generated_at + freshness_manifest.latest_resource_modified + max(record business dates)`

### `freshness_hours_sc_compras`

- **result:** 34.08 (hours)
- **numerator:** 34.08
- **denominator:** 1
- **formula:** (now_utc - last_collection_completed_at).total_seconds()/3600
- **period:** as of 2026-07-18T20:57:05.248011+00:00
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/artifact.json`
  - `/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/licitacoes.jsonl`
- **limitations:**
  - freshness_hours is wall-clock age of last collection completion (or business date fallback).
  - Negative business-date age can occur when max data_publicacao is in the future (planned openings).
  - Does not prove downstream DB persistence — file artifact only.
- **extras:**
  - last_collection_at: `2026-07-17T10:52:20+00:00`
  - hours_since_collection: `34.08`
  - method: `summary.completed_at`

### `freshness_hours_dados_abertos_sc`

- **result:** 42.72 (hours)
- **numerator:** 42.72
- **denominator:** 1
- **formula:** (now_utc - last_collection_completed_at).total_seconds()/3600
- **period:** as of 2026-07-18T20:57:05.248011+00:00
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/dados_abertos_sc/smoke-dados-sc-smoke-20260717T021337Z-f4cfe4b907.json`
  - `/mnt/d/extra consultoria/data/normalized/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/dados-sc-smoke-20260717T021337Z-f4cfe4b907.jsonl`
- **limitations:**
  - freshness_hours is wall-clock age of last collection completion (or business date fallback).
  - Negative business-date age can occur when max data_publicacao is in the future (planned openings).
  - Does not prove downstream DB persistence — file artifact only.
- **extras:**
  - last_collection_at: `2026-07-17T02:13:40.425813+00:00`
  - latest_business_date: `2025-07-01`
  - hours_since_collection: `42.72`
  - hours_since_latest_business_date: `9188.95`
  - method: `summary.completed_at + max(record business dates)`

### `freshness_hours_pncp`

- **result:** 0.61 (hours)
- **numerator:** 0.61
- **denominator:** 1
- **formula:** (now_utc - last_collection_completed_at).total_seconds()/3600
- **period:** as of 2026-07-18T20:57:05.248011+00:00
- **confidence:** high
- **calc_date:** 2026-07-18
- **run_id:** `r2-n05`
- **sources:**
  - `/mnt/d/extra consultoria/output/readiness/freshness-gate.json`
  - `/mnt/d/extra consultoria/output/readiness/freshness-gate.json`
- **limitations:**
  - freshness_hours is wall-clock age of last collection completion (or business date fallback).
  - Negative business-date age can occur when max data_publicacao is in the future (planned openings).
  - Does not prove downstream DB persistence — file artifact only.
- **extras:**
  - last_collection_at: `2026-07-18T20:20:44.076021+00:00`
  - latest_business_date: `2026-07-18`
  - hours_since_collection: `0.61`
  - hours_since_latest_business_date: `20.95`
  - method: `freshness-gate critical_sources[pncp] + max(record business dates)`

## Artifacts used

```json
{
  "ciga_dom": {
    "summary": "/mnt/d/extra consultoria/output/ciga_dom/latest_summary.json",
    "records": "/mnt/d/extra consultoria/output/ciga_dom/ciga-dom-20260717T105219Z-9f86448a90/publications.jsonl",
    "n_records": 10182,
    "freshness": "/mnt/d/extra consultoria/output/ciga_dom/freshness_manifest.json"
  },
  "sc_compras": {
    "summary": "/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/artifact.json",
    "records": "/mnt/d/extra consultoria/output/sc_compras/sc_compras-incremental-20260717T105219Z-41a1f57d62/licitacoes.jsonl",
    "n_records": 0
  },
  "dados_abertos_sc": {
    "summary": "/mnt/d/extra consultoria/output/dados_abertos_sc/smoke-dados-sc-smoke-20260717T021337Z-f4cfe4b907.json",
    "records": "/mnt/d/extra consultoria/data/normalized/dados_abertos_sc/0f2223f5-df6c-4860-96d6-f25636107379/dados-sc-smoke-20260717T021337Z-f4cfe4b907.jsonl",
    "n_records": 500,
    "records_are_samples_only": false
  },
  "pncp": {
    "opportunity_manifest": "/mnt/d/extra consultoria/output/readiness/opportunity-coverage-manifest.json",
    "next30d_metrics": "/mnt/d/extra consultoria/output/coverage/next30d-metrics-final.json",
    "target_reconciliation": "/mnt/d/extra consultoria/output/readiness/target-reconciliation-summary.json",
    "reconciliation_dir": "/mnt/d/extra consultoria/output/reconciliation",
    "freshness_gate": "/mnt/d/extra consultoria/output/readiness/freshness-gate.json"
  },
  "ibge_cache": {
    "path": "/mnt/d/extra consultoria/data/ibge_cache.json",
    "available": true,
    "count": 295
  }
}
```
