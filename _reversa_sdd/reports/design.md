# Reports — Design

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

**Arquitetura:** PostgreSQL views → fetch → ReportLab PDF / openpyxl Excel → data/output/

**Section Builder Pattern (B2G):** cada seção = função independente → `_build_cover()`, `_build_executive_summary()`, ... → `story.extend()` → `doc.build()`

**Semantic Dedup:** Pass1: composite key exact → Pass2: Jaccard pairwise (UF-scoped). ≥0.85=remove, 0.75-0.85=warn, <0.75=keep.

🟢 CONFIRMADO — Todos os 6 relatórios verificados.
