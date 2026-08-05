# Data Quality Report — reajuste_14133

- run_id: `reajuste_14133-2026-08-04-d60a3969`
- as_of: `2026-08-04`
- source_mode: `ssh`
- source (masked): `ssh:ec-prod`

## Funil

- **examined_raw**: 27634
- **after_dedupe**: 27634
- **private_supplier**: 27077
- **construction**: 7530
- **regime_14133_proven**: 89
- **temporally_mature**: 3798
- **data_base_confirmed**: 0
- **index_located**: 35
- **already_adjusted**: 0
- **universe_eligible_count**: 27634
- **sampled**: 0
- **HOT_VERIFIED**: 0
- **STRONG_CANDIDATE**: 33
- **REVIEW_REQUIRED**: 30
- **RESEARCH_REQUIRED**: 0
- **ALREADY_ADJUSTED**: 0
- **NOT_ELIGIBLE**: 23278
- **LEGAL_REGIME_UNKNOWN**: 3728
- **LEGAL_REGIME_CONFLICT**: 8
- **CLOSED_OR_FINANCIALLY_EXHAUSTED**: 0
- **OUTREACH_READY**: 0
- **OUTREACH_READY_WITHOUT_VALUE_ESTIMATE**: 0
- **DOCUMENT_REQUEST_CANDIDATE**: 61
- **NOT_READY_FOR_OUTREACH**: 27016
- **official_pdf_text_extracted**: 161
- **pdfs_downloaded**: 288
- **arquivos_listed**: 1706

## Métricas

- **top_leads**: 63
- **all_classified**: 7530
- **supplier_portfolios**: 2702
- **outreach_ready_suppliers**: 0
- **outreach_ready_without_value_suppliers**: 0
- **document_request_suppliers**: 39
- **not_ready_suppliers**: 2663
- **valor_potencial_agregado_top**: 0.0
- **teto_teorico_agregado_top**: 0.0
- **document_fetch_coverage**: 220
- **docs_processed_deep**: 165
- **official_pdf_text_extracted**: 161
- **pdfs_downloaded**: 288
- **arquivos_listed**: 1706
- **docs_processed_deep_definition**: contracts with PNCP compra PDF download attempted (not portal HTML alone)
- **excluded_count**: 23835
- **contact_lookups_used**: 60
- **contact_attempts**: 60
- **universe_eligible_count**: 27634
- **rows_read**: 27634
- **execution_complete**: True
- **sampling_reason**: None

## Principais exclusões

- `objeto_nao_construcao:weak_token_alone`: 10695
- `objeto_nao_construcao:no_engineering_signal`: 5272
- `NOT_ELIGIBLE`: 3731
- `objeto_nao_construcao:negative_vocabulary`: 2539
- `objeto_nao_construcao:materials_or_rental_supply_only`: 785
- `fornecedor_nao_privado_ou_orgao`: 557
- `objeto_nao_construcao:intellectual_service_without_material_execution`: 196
- `objeto_nao_construcao:sector_false_positive_regression`: 60

## Gaps estruturais do datalake

- Sem coluna nativa de data do orçamento estimado em `pncp_supplier_contracts`.
- Sem coluna nativa de índice contratual ou regime legal estruturado.
- Document harvest (`process_documents`) pode estar vazio → HOT_VERIFIED raro/zero é esperado (fail-closed).
- Proxy de data-base (assinatura/início/publicação) só para prospecção.

## Política de linguagem

{
  "reajuste_sentido_estrito_only": true,
  "not_reequilibrio": true,
  "not_repactuacao": true,
  "not_atualizacao_por_atraso": true,
  "not_aditivo_quantitativo": true,
  "not_legal_opinion": true,
  "hot_verified_requires_documentary_gates": true,
  "no_hot_from_pncp_supplier_contracts_dates_alone": true,
  "legal_regime_unknown_never_outreach_ready": true,
  "pdf_binary_not_documentary_proof": true,
  "no_prior_adjustment_located_not_proof": true,
  "unit_is_supplier_not_contract": true
}
