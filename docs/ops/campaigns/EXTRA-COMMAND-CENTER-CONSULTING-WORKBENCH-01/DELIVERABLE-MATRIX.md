# DELIVERABLE-MATRIX

| Flow | PDF | XLSX | Manifest | Extra | Role primary |
|------|-----|------|----------|-------|--------------|
| Extra | `relatorio-executivo-extra.pdf` | `workbook-oportunidades-extra.xlsx` | `run-manifest.json` | `evidence/` | executive_report + workbook |
| CONFENGE suppliers | `relatorio-executivo-fornecedores.pdf` | `planilha-comercial-fornecedores.xlsx` | yes | coverage honesty Top N ≠ population | same |
| CONFENGE agencies | `relatorio-orgaos-publicos.pdf` | `workbook-orgaos-publicos.xlsx` | yes | `pacote-revisao-orgaos.json` | + review_package |
| Process documents | `relatorio-cobertura-documental.pdf` | `indice-documentos.xlsx` | yes | ZIP + per-doc PDFs | coverage + index |
| Regen after correction | new version under new job_id | same matrix | parent_run_id linked | version-meta.json | history preserved |

**Renderers:** `scripts/command_center/deliverables/pdf_render.py`, `excel_render.py`  
**Profiles:** INTERNAL_ANALYSIS | CLIENT_READY | AUDIT_EVIDENCE
