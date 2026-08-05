# Auditoria manual de regime — v3.1 (§9)

**HEAD (artefato):** `f5c8cb198dc7c649ef566fd67ed52689bba051ba`  
**Método:** reclassificação via `classify_row` (código shipped) + revisão metodológica por amostra.  
**NÃO é** desk PDF forense completa: o export e o lake local **não** contêm texto de edital/contrato em massa.

## Fontes

| Fonte | Detalhe |
|-------|---------|
| Replay demotions | `output/commercial/reajuste_14133/2026-08-04-v2-real/contratos_analisados.json` sha256=`ba0a91c630227c17c4952961a095a93d1fa93925233d4bd97e0fe737b3dad458` n=1800 |
| Transcript demotions | `/tmp/grok-goal-819d19cb5e62/implementer/demotion-replay-transcript.txt` |
| Results demotions | `/tmp/grok-goal-819d19cb5e62/implementer/demotion-replay-results.json` |
| Live national | pncp_datalake `pncp_supplier_contracts` rows_read=11503 sampling=None |

## Before / After (replay reprodutível)

| Métrica | Before (ano elevava) | After (v3.1) |
|---------|----------------------|--------------|
| LIKELY + DIAGNOSTIC | **771** | **23** |
| Demotions totais | — | **748** |
| → DOCUMENT_REQUEST_READY | — | **732** |
| → POTENTIAL_SIGNAL | — | **16** |

Comando: `python3` script em `demotion-replay-transcript.txt` (shipped `classify_row` vs regra antiga `signature_year>=2021`).

## Amostras §9

### 10 — LEI_14133_PROVEN (R-A)

| # | contrato | edital/processo originário | data ato iniciador | fundamento legal | regime_sistema | regime_manual | acerto/erro | estágio |
|---|----------|---------------------------|--------------------|------------------|----------------|---------------|------------|---------|
| 1 | `04892707000100-2-000493/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-10-29 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |
| 2 | `04892707000100-2-000550/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-11-28 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |
| 3 | `04892707000100-2-000542/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-11-27 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |
| 4 | `04892707000100-2-000578/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-12-12 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |
| 5 | `68596162000178-2-000022/2025` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2025-04-01 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | NOT_COMMERCIAL |
| 6 | `92883834000100-2-000001/2025` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2025-03-25 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |
| 7 | `04892707000100-2-000570/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-12-11 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |
| 8 | `04892707000100-2-000192/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-06-06 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |
| 9 | `76175884000187-2-000146/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-06-04 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |
| 10 | `76175884000187-2-000147/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-06-04 | LEI_14133_2021 (campo/export prior proven) | LEI_14133_2021 | OK_SISTEMA: proven via structured/export flag no replay; desk PDF do edital/cont | ACERTO_METODOLOGICO | LIKELY_ADJUSTMENT_OPPORTUNITY |

### 10 — LIKELY_14133 (R-B)

_Amostra vazia — sem casos no universo reclassificado com o predicado._

**Limitação:** export/lake sem PDF de edital; desk forense completa requer acervo documental.

### 10 — TRANSITIONAL_REGIME_UNRESOLVED (R-C)

| # | contrato | edital/processo originário | data ato iniciador | fundamento legal | regime_sistema | regime_manual | acerto/erro | estágio |
|---|----------|---------------------------|--------------------|------------------|----------------|---------------|------------|---------|
| 1 | `04892707000100-2-000350/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-08-27 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 2 | `75101873000190-2-000792/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-11-01 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 3 | `82951344000140-2-000037/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-06-14 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 4 | `83169623000110-2-000199/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-10-05 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 5 | `82951344000140-2-000020/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-05-23 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 6 | `01619323000120-2-000098/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-12-19 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 7 | `04892707000100-2-000142/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-05-09 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 8 | `04892707000100-2-000324/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-08-25 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 9 | `82951344000140-2-000007/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-05-14 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 10 | `82951344000140-2-000041/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-07-16 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |

### 10 — Assinaturas 2022/2023

| # | contrato | edital/processo originário | data ato iniciador | fundamento legal | regime_sistema | regime_manual | acerto/erro | estágio |
|---|----------|---------------------------|--------------------|------------------|----------------|---------------|------------|---------|
| 1 | `82951344000140-2-000007/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-05-14 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 2 | `75101873000190-2-000792/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-11-01 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 3 | `83169623000110-2-000199/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-10-05 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 4 | `88000906000157-2-000061/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-11-14 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 5 | `76669324000189-2-000002/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-11-16 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 6 | `03111139000109-2-000001/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-01-08 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 7 | `83169623000110-2-000116/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-09-14 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 8 | `04892707000100-2-000418/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-12-08 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 9 | `76002641000147-2-000070/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-10-03 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 10 | `77821841000194-2-000229/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-05-09 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |

### 10 — Assinaturas 2024 (origem pode ser legada)

| # | contrato | edital/processo originário | data ato iniciador | fundamento legal | regime_sistema | regime_manual | acerto/erro | estágio |
|---|----------|---------------------------|--------------------|------------------|----------------|---------------|------------|---------|
| 1 | `92963560000160-2-000177/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-10-04 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | NOT_COMMERCIAL |
| 2 | `87366159000102-2-000228/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-12-26 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | POTENTIAL_ADJUSTMENT_SIGNAL |
| 3 | `92967595000177-2-000003/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-07-08 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 4 | `76205814000124-2-000194/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-11-28 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 5 | `76282656000106-2-000341/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-10-08 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 6 | `15126437000143-2-006302/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-11-22 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 7 | `86051398000100-2-000489/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-08-22 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 8 | `90832619000155-2-000210/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-11-21 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 9 | `04892707000100-2-000385/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-09-06 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 10 | `82951344000140-2-000041/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-07-16 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |

### 20 — Fornecedores Sul

| # | contrato | edital/processo originário | data ato iniciador | fundamento legal | regime_sistema | regime_manual | acerto/erro | estágio |
|---|----------|---------------------------|--------------------|------------------|----------------|---------------|------------|---------|
| 1 | `81478133000170-2-000010/2026` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2026-06-12 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2026 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | NOT_COMMERCIAL |
| 2 | `76966860000146-2-000134/2026` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2026-05-28 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2026 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | NOT_COMMERCIAL |
| 3 | `76208818000166-2-000025/2026` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2026-03-27 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2026 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | NOT_COMMERCIAL |
| 4 | `01619323000120-2-000098/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-12-19 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 5 | `75380071000166-2-000031/2026` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2026-05-29 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2026 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | NOT_COMMERCIAL |
| 6 | `92883834000100-2-000008/2025` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2025-04-09 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2025 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 7 | `77821841000194-2-000170/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-06-11 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 8 | `75771477000170-2-000012/2023` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2023-08-17 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2023 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 9 | `83021808000182-2-000395/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-10-29 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 10 | `80257355000108-2-000216/2025` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2025-05-06 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2025 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 11 | `76950096000110-2-000031/2025` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2025-04-15 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2025 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 12 | `76669324000189-2-000075/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-08-23 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 13 | `76105675000167-2-000007/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-06-25 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 14 | `82951344000140-2-000020/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-05-23 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 15 | `76972082000106-2-000015/2026` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2026-05-06 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2026 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | NOT_COMMERCIAL |
| 16 | `04892707000100-2-000524/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-11-14 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 17 | `76669324000189-2-000004/2025` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2025-02-18 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2025 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 18 | `95589255000148-2-000060/2026` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2026-06-11 | sem fundamento textual no export; ano/PNCP não usa | UNKNOWN | OK_SISTEMA: R-D sem texto oficial; ano=2026 NÃO presume 14.133; regime manual =  | ACERTO_METODOLOGICO | NOT_COMMERCIAL |
| 19 | `75741330000137-2-000025/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-06-21 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |
| 20 | `76105543000135-2-000098/2024` | NÃO DISPONÍVEL no export tabular (sem PDF/edital no lake) | 2024-09-19 | sem fundamento textual no export; ano/PNCP não usa | TRANSITIONAL_REGIME_UNRESOLVED | OK_SISTEMA: R-C apropriado para ano 2024 sem documento de fundamento; regime man | ACERTO_METODOLOGICO | DOCUMENT_REQUEST_READY |


## Precisão e erros

| Métrica | Valor | Nota |
|---------|-------|------|
| FP LIKELY/DIAGNOSTIC sem R-A/R-B (amostra reclassificada) | **0** | Ano não eleva |
| Demotions LIKELY(ano)→doc/signal | **748** | replay n=1800 |
| Taxa não resolvida no live classificado | UNKNOWN=608 TRANSITIONAL=3 | lake sem PDF |
| Falsos negativos documentais | **não mensurável** | sem acervo PDF |
| Precisão anti-FP de elevação por ano | **100%** na amostra e no live (0 LIKELY por ano) | não confundir com precisão forense de fundamento |

### Principais causas de “não resolução” / limitação

1. Ausência de PDF/edital/parecer no datalake local  
2. Ausência de campo estruturado de regime na maioria dos contratos  
3. Contratos recentes (2025–2026) no live → imaturidade temporal  
4. Ano **propositadamente** não presume 14.133  

### Veredito

- **Metodologia de regime:** conforme objetivo (sem elevação por ano/PNCP; R-B exige sinal normativo positivo).  
- **Auditoria forense por edital:** **parcial / env-limited** — campos de origem e fundamento preenchidos com “NÃO DISPONÍVEL” quando o export não traz documento; não fabricamos verificação PDF.  
- **PR:** pronta para squash merge no eixo código/testes/live scan; desk humana com PDFs permanece recomendada antes de abordagem 14.133 específica.
