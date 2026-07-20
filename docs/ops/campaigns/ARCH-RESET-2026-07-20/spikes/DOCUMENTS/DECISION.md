# Spike G — document parsers

**Decision:** `DEFERRED_NO_CORPUS`

**Honest statement:** `KEEP_CURRENT_STACK` is **not** a proven evaluation outcome. Three synthetic digital PDFs (`_tmp_bench/pdfs/`) are insufficient for multi-column/table/scanned claims. `benchmark.json` is exploratory microbench only.

**Required corpus strata (before engine adoption decision):**

| Stratum | Minimum |
|---------|--------:|
| digital_simple | 5 |
| multicolumn | 5 |
| tables | 5 |
| scanned | 5 |

**Also:**

- PyMuPDF only with AGPL/commercial license ADR  
- No private editais committed to Git  

**Production dependency added:** no  

**ADR:** ADR-027 (rewritten for honesty; same file path)  
