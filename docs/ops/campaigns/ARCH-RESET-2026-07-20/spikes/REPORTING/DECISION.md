# Spike J — None

**Decision:** `KEEP_OPENPYXL_REPORTLAB`

**Reason:** XlsxWriter may be faster for pure write (xlsxwriter won microbench) but openpyxl is already integrated for read/edit paths; fpdf2 not installed and would require full PDF regression. No production dep change without pack-level parity.

**Production dependency added:** False

Evidence: `benchmark.json`
