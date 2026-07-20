# Spike G — document_parsers

**Decision:** `KEEP_CURRENT_STACK`

**Reason:** Digital PDFs: pypdf/pdfplumber adequate for simple text; no corpus of scanned/multi-column private editais committed. PyMuPDF blocked by AGPL without commercial license decision. No production dep change.

**Production dependency added:** False

Evidence: `benchmark.json`
