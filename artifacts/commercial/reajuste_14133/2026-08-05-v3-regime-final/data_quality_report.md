# Data quality — full national prod

| Métrica | Valor |
|---------|-------|
| table_count | 4,503,049 |
| universe_eligible | 3,886,745 |
| rows_read | 3,886,745 |
| private_supplier | 3,864,037 |
| construction | 149,180 |
| temporally_mature | 75,154 |
| DOCUMENT_REQUEST_READY | 73,783 |
| POTENTIAL_SIGNAL | 1,371 |
| LIKELY+DIAGNOSTIC | 0 |
| suppliers | 31,076 |
| document_request_suppliers | 30,851 |
| execution_complete | true |
| sampling_reason | null |

### Por que rows_read < table_count?

Pré-filtro legítimo (não amostragem):
- valor nulo / inválido
- sem marco temporal (assinatura/início/publicação)
- CNPJ fornecedor inválido
- `data_fim` muito antiga (>24m antes de as_of)

(616,304 linhas fora do pré-filtro)
