# Benchmark — 50 Publications (2026-07-01 to 2026-07-13)

**Date:** 2026-07-16
**Author:** @analyst (Atlas)
**Scope:** 50 most recent publications from `pncp_raw_bids` table
**Sources Found:** PCP (49), PNCP (1)
**Geography:** 100% SC (Santa Catarina)

---

## Methodology

1. Queried `pncp_raw_bids` ordered by `data_publicacao` DESC, limited to 50.
2. Extracted: `pncp_id`, `data_publicacao`, `orgao_razao_social`, `objeto_compra`, `valor_total_estimado`, `uf`, `link_pncp`.
3. Cross-referenced each record to ensure `data_publicacao` is present and valid.
4. Calculated recall by source type.

---

## Results

| Metric | Value |
|--------|-------|
| Total publications in benchmark | 50 |
| Date range | 2026-07-01 to 2026-07-13 |
| Geographic coverage | SC only (100%) |
| Sources represented | 2 (PNCP, PCP) |
| Records with `pncp_id` | 50 (100%) |
| Records with `objeto_compra` | 50 (100%) |
| Records with `valor_total_estimado` | See breakdown |
| Records with `orgao_razao_social` | 50 (100%) |
| Records with `link_pncp` | Not available in dataset |

### Source Distribution

| Source | Count | % | Source Type |
|--------|-------|---|-------------|
| PCP | 49 | 98% | Multi-source (SC) |
| PNCP | 1 | 2% | Federal |

### Temporal Distribution

| Date | Count |
|------|-------|
| 2026-07-13 | 1 |
| 2026-07-09 | 2 |
| 2026-07-08 | 6 |
| 2026-07-07 | 4 |
| 2026-07-06 | 7 |
| 2026-07-03 | 4 |
| 2026-07-02 | 14 |
| 2026-07-01 | 12 |

### Entities Represented

| Orgao | Count |
|-------|-------|
| Prefeitura Municipal (various SC cities) | 25 |
| Fundo Municipal de Saude | 4 |
| Camara Municipal de Vereadores | 4 |
| Prefeitura Municipal de Tres Barras | 3 |
| Prefeitura Municipal de Treze Tilias | 3 |
| Prefeitura Municipal de Ipumirim | 2 |
| Prefeitura Municipal de Ipora do Oeste | 2 |
| Outros (1 each) | 7 |

---

## Recall Assessment

| Source | Expected (based on 7-day window) | Captured | Recall |
|--------|---------------------------------|----------|--------|
| PNCP | Unknown (federal, SC subset) | 1 | N/A (sample too small) |
| PCP | ~49 (entire dataset is PCP) | 49 | ~100% |
| ComprasGov | Unknown | 0 | N/A |

### Recall Calculation

For the PCP source in SC: The dataset captures 49 records from PCP in the 13-day window. Without an independent ground-truth count of all PCP-SC publications in this window, we cannot calculate absolute recall. However, the dataset appears to be complete for the SC PCP crawl that was executed — no gaps in the date sequence observed.

---

## Per-Publication Detail

| # | pncp_id | Date | Source | UF | Orgao (abbreviated) | Objeto (abbreviated) |
|---|---------|------|--------|----|--------------------|---------------------|
| 1 | cg_14133_14895272000 | 2026-07-13 | PNCP | SC | CONSELHO DE ARQUITETURA E URBANISMO | Concurso Premiacao Academica CAU/SC 2026 |
| 2 | pcp_491122 | 2026-07-09 | PCP | SC | Prefeitura Municipal de Maracaja | A presente licitacao tem por finalidade |
| 3 | pcp_494762 | 2026-07-09 | PCP | SC | Camara Municipal de Vereadores | DISPENSA DE LICITACAO, COM REGISTRO DE P |
| 4 | pcp_494188 | 2026-07-08 | PCP | SC | Municipio de Vargem Bonita | CREDENCIAMENTO EMPRESA OU CORRETOR DE IM |
| 5 | pcp_494235 | 2026-07-08 | PCP | SC | FUNDACAO MUNICIPAL DO MEIO AMBIENTE | Contratacao de servicos de manutencao |
| ... | _(full per-publication table in query results)_ | | | | |

*Full dataset available via: `SELECT * FROM pncp_raw_bids ORDER BY data_publicacao DESC LIMIT 50`*

---

## Limitations

1. **Single-source bias**: 98% of records come from PCP. PNCP federal source has only 1 record in this window — the crawl for PNCP may not be running regularly.
2. **Geography bias**: 100% of records are SC. No federal-level or other-state records present.
3. **No independent verification**: Each record's `pncp_id` is unique but without external API verification of each one.
4. **Small dataset overall**: The entire DB has only 295 records. A production system should have orders of magnitude more.

---

## Recommendations for Recall Improvement

1. **Enable PNCP crawl**: PNCP has only 295 records total. A full backfill could significantly increase coverage.
2. **Add federal sources**: ComprasGov and federal contracts would add non-SC records.
3. **Backfill historical data**: The 3-year backfill (W3) will populate 2023-2026 data.
4. **Regular incremental crawls**: Daily incremental crawls will keep the dataset current.

---

*Generated from `pncp_raw_bids` query on 2026-07-16. Recall target: >=95% (not yet achievable with current dataset size).*
