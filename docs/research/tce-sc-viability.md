# TCE-SC Viability Research

**Date:** 2026-07-11
**Source:** FEAT-2.1 investigation
**Status:** CONFIRMED

## Summary

SCMWeb JSON API is viable as the primary source for TCE-SC data. The e-Sfinge portal is no longer accessible. Decision: use SCMWeb exclusively.

## Investigated Sources

### 1. SCMWeb JSON API — CONFIRMED (PRIMARY)

- **URL:** `https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285`
- **Parameter `p285`:** Identifies TCE-SC as the publishing entity
- **HTTP Status:** 200 OK (tested 2026-07-11)
- **Response Format:** JSON list (returns all matching records in a single response)
- **Available Endpoints:**
  - `page=licitacoes&export=json&type=licitacoes` — Bids/licitations
  - `page=contratos&export=json&type=contratos` — Contracts
- **Authentication:** None required (public transparency portal)
- **Rate Limiting:** No 429 observed during testing; conservative 2s delay configured
- **Data Quality:** Good for contracts (CNPJ, contractor name, value, status); moderate for licenses (often missing modalidade and objeto)

#### API Characteristics

| Aspect | Detail |
|--------|--------|
| Pagination | API IGNORES `pn` parameter — always returns full dataset |
| Date Filtering | API IGNORES `data_inicio`/`data_fim` — filtering done client-side |
| License Page Size | ~16 records/month filtered by date (up to ~1,318 unfiltered) |
| Contract Page Size | ~874 records (all visible contracts) |
| Record Fields (Licenses) | Numero, Modalidade, Objeto, Data_Abertura, Valor_Estimado, Status, Ano |
| Record Fields (Contracts) | Numero, Contratado, CNPJ, Objeto, Valor, Status |

### 2. e-Sfinge — NOT ACCESSIBLE

- **URL:** `https://e-sfinge.tce.sc.gov.br`
- **HTTP Status:** Connection timeout (no response)
- **Status:** Not viable. Domain appears to be offline or migrated.

### 3. TCE-SC Dados Abertos — MIGRATED

- **Original URL:** `https://www.tce.sc.gov.br/dados-abertos`
- **Redirects To:** `https://www.tcesc.tc.br/dados-abertos`
- **New URL Status:** HTTP 404 (page not found)
- **Status:** Not viable. The new TCESC portal does not expose an equivalent open data page.

## Decision

**Primary source: SCMWeb JSON API** (via `p285` parameter for TCE-SC).

Rationale:
- Only confirmed working source
- No authentication required
- Public transparency data available for both licenses and contracts
- Coverage: all entities publishing via SCMWeb under TCE-SC oversight (~96% of SC entities)
- No viable alternative (e-Sfinge offline, TCESC portal 404)

### Implementation Notes

| Parameter | Value | Description |
|-----------|-------|-------------|
| Crawl method | Single-page fetch (API ignores paging) | Page 1 returns all records |
| Date filtering | Client-side | API date params are ignored |
| Rate limiting | 2s between calls | Conservative to avoid 429 |
| Full window | 365 days | Configurable via `TCE_SC_FULL_DAYS` |
| Incremental window | 7 days | Configurable via `TCE_SC_INCREMENTAL_DAYS` |
| Feature flag | `TCE_SC_ENABLED` | Default: false (opt-in) |

## References

- SCMWeb: https://www.scmweb.com.br/processos/index.php
- TCE-SC portal: https://www.tcesc.tc.br
- Reversa SDD: `_reversa_sdd/crawl/tasks.md` T10
- Reversa SDD: `_reversa_sdd/crawl/requirements.md` FR-C1, FR-C13
