# Metodologia — full national reajuste 14.133 v3.1

## Fonte

- **Host:** ec-prod Postgres `pncp_datalake`
- **Tabela:** `pncp_supplier_contracts` (**4,503,049** linhas totais)
- **Pré-filtro elegível:** 3,886,745 (CNPJ válido, data, openish 24m, valor≥1)
- **rows_read:** **3,886,745**
- **max_source_rows:** null
- **sampling_reason:** null
- **execution_complete:** true

## Regime

Ano/PNCP **não** elevam LIKELY_14133. R-B exige sinal normativo positivo.

Distribuição no scan (todos os rows lidos):

```json
{
  "LEI_14133_PROVEN": 0,
  "LIKELY_14133": 0,
  "TRANSITIONAL_REGIME_UNRESOLVED": 955309,
  "UNKNOWN": 2908722,
  "LEGACY_8666": 2,
  "RDC": 3,
  "LEGACY_10520": 1,
  "REGIME_CONFLICT": 0
}
```

## Estágios comerciais (funil)

| Estágio | Qtd |
|---------|-----|
| construction | 149,180 |
| DOCUMENT_REQUEST_READY | 73,783 |
| POTENTIAL_ADJUSTMENT_SIGNAL | 1,371 |
| LIKELY / DIAGNOSTIC | 0 |
| suppliers | 31,076 |

0 LIKELY sem prova documental de regime — comportamento esperado.
