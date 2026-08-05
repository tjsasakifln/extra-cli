# Data quality — live national v3.1

- Table rows: **11997**; **rows_read: 11503** (filters: CNPJ válido, valor>=1, datas, openish)
- sampling_reason: **None**; execution_complete: **True**
- construction: **611**; temporally_mature: **5**
- regime classified: `{'UNKNOWN': 608, 'TRANSITIONAL_REGIME_UNRESOLVED': 3}`
- stages classified: `{'NOT_COMMERCIAL': 604, 'POTENTIAL_ADJUSTMENT_SIGNAL': 7}`
- LIKELY+DIAGNOSTIC live: **0** (antes no replay com ano: **755**; demotions: **732**)
- Schema: sem `data_assinatura` nativa → year context via data_inicio/publicacao only for R-C window
