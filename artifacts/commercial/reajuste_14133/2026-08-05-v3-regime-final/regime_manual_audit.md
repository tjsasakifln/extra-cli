# Auditoria manual de regime — v3.1

**Método:** reclassificação do export nacional de 1.800 contratos + checagens estruturais do código de evidência.
**Limitação honesta:** o DSN local não expõe o PNCP nacional completo; não há PDFs oficiais vinculados em massa neste replay.
A auditoria abaixo valida **consistência da hierarquia** e amostras priorizadas; precisão documental plena exige desk review com edital/contrato.

## Amostras

### 10 — LEI_14133 comprovado (R-A)
Esperado: proven=true, pode ser LIKELY/DIAGNOSTIC se demais gates.

| # | contrato | assinatura | regime_sistema | proven | evidence | estágio | verificação manual |
|---|----------|------------|----------------|--------|----------|---------|--------------------|
| 1 | `92883834000100-2-000004/2025` | 2025-01-20 | LEI_14133_2021 | True | R-A | DIAGNOSTIC_OUTREACH_READY | ver nota abaixo |
| 2 | `04892707000100-2-000578/2024` | 2024-12-12 | LEI_14133_2021 | True | R-A | LIKELY_ADJUSTMENT_OPPORTUNITY | ver nota abaixo |
| 3 | `04892707000100-2-000493/2024` | 2024-10-29 | LEI_14133_2021 | True | R-A | DIAGNOSTIC_OUTREACH_READY | ver nota abaixo |
| 4 | `76669324000189-2-000160/2025` | 2025-11-17 | LEI_14133_2021 | True | R-A | NOT_COMMERCIAL | ver nota abaixo |
| 5 | `76175884000187-2-000146/2024` | 2024-05-23 | LEI_14133_2021 | True | R-A | LIKELY_ADJUSTMENT_OPPORTUNITY | ver nota abaixo |
| 6 | `04892707000100-2-000192/2024` | 2024-06-05 | LEI_14133_2021 | True | R-A | DIAGNOSTIC_OUTREACH_READY | ver nota abaixo |
| 7 | `92883834000100-2-000040/2025` | 2025-09-11 | LEI_14133_2021 | True | R-A | NOT_COMMERCIAL | ver nota abaixo |
| 8 | `68596162000178-2-000022/2025` | 2025-02-25 | LEI_14133_2021 | True | R-A | NOT_COMMERCIAL | ver nota abaixo |
| 9 | `92963560000160-2-000595/2026` | 2026-06-26 | LEI_14133_2021 | True | R-A | NOT_COMMERCIAL | ver nota abaixo |
| 10 | `04892707000100-2-000442/2023` | 2024-01-04 | LEI_14133_2021 | True | R-A | DIAGNOSTIC_OUTREACH_READY | ver nota abaixo |

### 10 — LIKELY_14133 (R-B)
Esperado: proven=false; nunca VERIFIED só com R-B.

_Amostra vazia neste export (sem casos com o predicado)._

### 10 — TRANSITIONAL_REGIME_UNRESOLVED (R-C)
Esperado: sem DIAGNOSTIC 14.133; DOCUMENT_REQUEST ou SIGNAL.

| # | contrato | assinatura | regime_sistema | proven | evidence | estágio | verificação manual |
|---|----------|------------|----------------|--------|----------|---------|--------------------|
| 1 | `76170240000104-2-000215/2024` | 2024-11-25 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 2 | `78680337000184-2-000059/2024` | 2024-12-17 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 3 | `92883834000100-2-000010/2024` | 2024-10-23 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 4 | `04892707000100-2-000508/2024` | 2024-11-05 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 5 | `77996312000121-2-000066/2024` | 2024-09-19 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 6 | `97320030000117-2-000110/2024` | 2024-12-30 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 7 | `83169623000110-2-001328/2024` | 2024-08-22 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 8 | `87890992000158-2-000105/2024` | 2024-10-15 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 9 | `92883834000100-2-000002/2024` | 2024-09-19 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 10 | `82939380000199-2-000573/2024` | 2024-01-08 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |

### 10 — Assinaturas 2022/2023
Ano não deve sozinho gerar LIKELY_14133.

| # | contrato | assinatura | regime_sistema | proven | evidence | estágio | verificação manual |
|---|----------|------------|----------------|--------|----------|---------|--------------------|
| 1 | `76247378000156-2-000038/2023` | 2023-09-05 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 2 | `83169623000110-2-000283/2023` | 2023-10-31 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 3 | `75101873000190-2-000792/2023` | 2023-10-30 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 4 | `83102343000194-2-000403/2023` | 2023-12-14 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 5 | `83169623000110-2-000116/2023` | 2023-09-06 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 6 | `75101873000190-2-001686/2023` | 2023-12-06 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 7 | `83169623000110-2-000082/2023` | 2023-08-24 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 8 | `77821841000194-2-000233/2023` | 2023-12-15 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 9 | `04892707000100-2-000418/2023` | 2023-12-08 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 10 | `04892707000100-2-000324/2023` | 2023-08-25 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |

### 10 — Assinaturas 2024
Sem edital originário no export: deve ser UNKNOWN/TRANSITIONAL, não proven.

| # | contrato | assinatura | regime_sistema | proven | evidence | estágio | verificação manual |
|---|----------|------------|----------------|--------|----------|---------|--------------------|
| 1 | `22112109000153-2-000026/2024` | 2024-04-08 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 2 | `88577416000118-2-000111/2024` | 2024-12-09 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 3 | `01612634000168-2-000202/2024` | 2024-09-12 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 4 | `76247329000113-2-000014/2024` | 2024-06-03 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 5 | `92883834000100-2-000025/2024` | 2024-12-30 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 6 | `04892707000100-2-000173/2024` | 2024-05-27 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 7 | `83102343000194-2-000879/2024` | 2024-03-26 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 8 | `83102244000102-2-000717/2024` | 2024-10-10 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 9 | `32370759000152-2-000129/2024` | 2024-11-04 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 10 | `83169623000110-2-001214/2024` | 2024-07-31 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | POTENTIAL_ADJUSTMENT_SIGNAL | ver nota abaixo |

### 20 — Fornecedores Sul (top prioridade)
Fila comercial Sul após correção de regime.

| # | contrato | assinatura | regime_sistema | proven | evidence | estágio | verificação manual |
|---|----------|------------|----------------|--------|----------|---------|--------------------|
| 1 | `76105576000185-2-000036/2024` | 2024-01-08 | LEI_14133_2021 | True | R-A | DIAGNOSTIC_OUTREACH_READY | ver nota abaixo |
| 2 | `04892707000100-2-000192/2024` | 2024-06-05 | LEI_14133_2021 | True | R-A | DIAGNOSTIC_OUTREACH_READY | ver nota abaixo |
| 3 | `04892707000100-2-000442/2023` | 2024-01-04 | LEI_14133_2021 | True | R-A | DIAGNOSTIC_OUTREACH_READY | ver nota abaixo |
| 4 | `04892707000100-2-000445/2023` | 2024-01-08 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 5 | `04892707000100-2-000542/2024` | 2024-11-27 | LEI_14133_2021 | True | R-A | LIKELY_ADJUSTMENT_OPPORTUNITY | ver nota abaixo |
| 6 | `17176399000169-2-000036/2024` | 2024-12-27 | LEI_14133_2021 | True | R-A | DIAGNOSTIC_OUTREACH_READY | ver nota abaixo |
| 7 | `92883834000100-2-000015/2025` | 2025-01-20 | LEI_14133_2021 | True | R-A | LIKELY_ADJUSTMENT_OPPORTUNITY | ver nota abaixo |
| 8 | `92883834000100-2-000028/2025` | 2025-05-29 | LEI_14133_2021 | True | R-A | LIKELY_ADJUSTMENT_OPPORTUNITY | ver nota abaixo |
| 9 | `04892707000100-2-000324/2023` | 2023-08-25 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 10 | `76175884000187-2-000158/2024` | 2024-05-27 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 11 | `04892707000100-2-000142/2024` | 2024-05-09 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 12 | `07854402000100-2-000034/2025` | 2025-04-24 | UNKNOWN | False | R-D | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 13 | `00394452000103-2-007720/2024` | 2025-01-16 | UNKNOWN | False | R-D | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 14 | `12075748000132-2-000061/2024` | 2024-04-24 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 15 | `12075748000132-2-000066/2024` | 2024-04-24 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 16 | `12075748000132-2-000062/2024` | 2024-04-24 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 17 | `82951344000140-2-000031/2024` | 2024-02-27 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 18 | `05472936000139-2-000021/2025` | 2025-05-26 | UNKNOWN | False | R-D | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 19 | `12075748000132-2-000067/2024` | 2024-04-24 | TRANSITIONAL_REGIME_UNRESOLVED | False | R-C | DOCUMENT_REQUEST_READY | ver nota abaixo |
| 20 | `04892707000100-2-000100/2025` | 2025-02-26 | UNKNOWN | False | R-D | DOCUMENT_REQUEST_READY | ver nota abaixo |


## Métricas de consistência (automatizadas sobre o replay)

| Métrica | Valor |
|---------|-------|
| Contratos no replay | 1800 |
| Falsos positivos de provável 14.133 sem R-A/R-B | 0 |
| TRANSITIONAL em DIAGNOSTIC_OUTREACH_READY | 0 |
| LIKELY+DIAGNOSTIC após correção | 23 |
| LIKELY+DIAGNOSTIC antes (v3 ano) | 755 |
| Rebaixados do caminho LIKELY (ano) → doc/signal | 221 |
| TRANSITIONAL_REGIME_UNRESOLVED | 533 |
| LEI_14133_PROVEN | 29 |
| LIKELY_14133 | 0 |
| UNKNOWN | 1238 |

### Precisão estimada (regra de consistência)

- **Precisão anti-FP (ano não prova regime):** 100.0% dos contratos sem elevação indevida
- **Falsos positivos 14.133 (LIKELY sem R-A/R-B):** 0
- **Falsos negativos:** não mensuráveis sem acervo documental completo (export sem texto de edital em massa)
- **Taxa não resolvida (R-C + R-D):** 98.4%
- **Principais causas de “erro” residual:** ausência de PDF/edital no datalake local; menções só em objeto; processos legados sem campo de origem

### Veredito amostral

Para cada linha acima, a **verificação manual plena** (fundamento no edital + ato iniciador) permanece pendente de desk humano com documentos.
O sistema está **fail-closed** para afirmações 14.133 e **fail-open** para solicitação documental — alinhado ao objetivo comercial.
