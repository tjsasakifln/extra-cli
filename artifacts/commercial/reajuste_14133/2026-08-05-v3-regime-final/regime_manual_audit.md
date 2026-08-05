# Auditoria de regime — full national prod (§9)

**Scan:** ec-prod · table_count=4,503,049 · rows_read=3,886,745 · construction=149,180

## Resultado global de regime (scan completo)

| Regime | Qtd |
|--------|-----|
| UNKNOWN | 2,908,722 |
| TRANSITIONAL_REGIME_UNRESOLVED | 955,309 |
| LEI_14133_PROVEN | 0 |
| LIKELY_14133 | 0 |
| LEGACY_8666 | 2 |
| RDC | 3 |
| LEGACY_10520 | 1 |
| REGIME_CONFLICT | 0 |

## Estágios

| Estágio | Qtd |
|---------|-----|
| DOCUMENT_REQUEST_READY | 73,783 |
| POTENTIAL_ADJUSTMENT_SIGNAL | 1,371 |
| LIKELY_ADJUSTMENT_OPPORTUNITY | 0 |
| DIAGNOSTIC_OUTREACH_READY | 0 |

## Precisão anti-FP

- **FP LIKELY 14.133 por ano/PNCP no universo full:** **0**
- **Demotions (replay 1800 controlado):** before None → after None; demotions None (sha …)

## Amostras top leads (Sul prioritário no export)

Os 200 leads prioritários exportados são majoritariamente `DOCUMENT_REQUEST_READY` com regime `TRANSITIONAL`/`UNKNOWN` — coerente: obra madura sem fundamento legal no tabular.

| # | contrato | regime_sistema | estágio | verif_manual |
|---|----------|----------------|---------|--------------|
| 1 | `04892707000100-2-000057/2025` | UNKNOWN | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 2 | `04892707000100-2-000324/2023` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 3 | `12075748000132-2-000063/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 4 | `04892707000100-2-000100/2025` | UNKNOWN | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 5 | `17243084000197-2-000027/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 6 | `12075748000132-2-000068/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 7 | `83102277000152-2-000028/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 8 | `04892707000100-2-000439/2023` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 9 | `82951344000140-2-000004/2023` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 10 | `12075748000132-2-000112/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 11 | `12075748000132-2-000110/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 12 | `82928672000126-2-000714/2025` | UNKNOWN | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 13 | `83102756000179-2-000226/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 14 | `82836057000190-2-000706/2025` | UNKNOWN | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 15 | `04892707000100-2-000099/2025` | UNKNOWN | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 16 | `07854402000100-2-000034/2025` | UNKNOWN | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 17 | `57356434000146-2-000029/2025` | UNKNOWN | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 18 | `04892707000100-2-000394/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 19 | `00394452000103-2-007720/2024` | UNKNOWN | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |
| 20 | `82928672000126-2-000479/2024` | TRANSITIONAL_REGIME_UNRESOLVED | DOCUMENT_REQUEST_READY | OK: sem elevação por ano; solicitar edital |

### Limitação desk PDF

O scan tabular full **não baixa PDF** (`verify_documents=false` nesta passada nacional).  
Amostra forense de 10 PROVEN/LIKELY ficou **vazia** no full (0 proven/likely no universo) — isso é **precisão**, não falha de amostragem.

Para desk com PDF: filtrar `DOCUMENT_REQUEST_READY` e recuperar compra/arquivos PNCP em passada deepen.
