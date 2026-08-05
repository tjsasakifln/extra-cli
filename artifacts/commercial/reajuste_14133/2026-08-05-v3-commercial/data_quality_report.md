# Data Quality Report — reajuste_14133

- run_id: `v3-replay-2026-08-05`
- as_of: `2026-08-04`
- source_mode: `None`
- source (masked): `None`

## Funil

- **DIAGNOSTIC_OUTREACH_READY**: 21
- **LIKELY_ADJUSTMENT_OPPORTUNITY**: 734
- **NOT_COMMERCIAL**: 1029
- **POTENTIAL_ADJUSTMENT_SIGNAL**: 16

## Métricas

- **n_contracts**: 1800
- **n_suppliers**: 846
- **stage_distribution_contracts**: {'DIAGNOSTIC_OUTREACH_READY': 21, 'LIKELY_ADJUSTMENT_OPPORTUNITY': 734, 'NOT_COMMERCIAL': 1029, 'POTENTIAL_ADJUSTMENT_SIGNAL': 16}
- **stage_distribution_suppliers**: {'DIAGNOSTIC_OUTREACH_READY': 18, 'LIKELY_ADJUSTMENT_OPPORTUNITY': 426, 'POTENTIAL_ADJUSTMENT_SIGNAL': 5, 'NOT_COMMERCIAL': 397}
- **old_outreach**: {'DOCUMENT_REQUEST_CANDIDATE': 22, 'NOT_READY_FOR_OUTREACH': 1778}
- **new_outreach**: {'DOCUMENT_REQUEST_CANDIDATE': 755, 'NOT_READY_FOR_OUTREACH': 1045}
- **gate_factors**: {'no_exact_data_base': 1800, 'no_contact': 1760, 'regime_not_probable': 16, 'no_min_interregnum': 1020}
- **source**: output/commercial/reajuste_14133/2026-08-04-v2-real/contratos_analisados.json
- **method**: replay_structured_classify_row_on_prior_national_export

## Principais exclusões


## Gaps estruturais do datalake

- Sem coluna nativa de data do orçamento estimado em `pncp_supplier_contracts`.
- Sem coluna nativa de índice contratual ou regime legal estruturado.
- Document harvest (`process_documents`) pode estar vazio → HOT_VERIFIED raro/zero é esperado (fail-closed).
- Proxy de data-base (assinatura/início/publicação) só para prospecção.

## Política de linguagem

{}
