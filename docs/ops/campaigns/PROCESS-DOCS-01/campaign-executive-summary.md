# Campaign PROCESS-DOCS-01 — Executive Summary (updated VPS)

Generated: 2026-07-30T20:12:39.111736+00:00

## Capability
`procurement_process_documents`

## VPS operation
- Host: `ec-prod` (`/opt/extra-consultoria`)
- Module deployed under `scripts/process_documents/`
- Timer: `extra-process-documents-incremental.timer` **enabled / active** (next ~04:30)
- Raw/meta: `/var/lib/extra-consultoria/{raw,output}/process_documents`
- Live PNCP `arquivos` API: **SUCCESS_NONZERO** for 50+80 process downloads
- Live CIGA: 240 SUCCESS_NONZERO; HTML multi-family partial

## Independent metrics (no average)

| Metric | VPS result | Target | Meets |
|--------|------------|--------|-------|
| discovery | 100% (1093/1093) | 100% | yes |
| operational actives | 79.6069% (324/407) | ≥95% | no |
| process recall | 72.5% (87/120) | ≥98% | no |
| financial coverage | 91.7469% | ≥99% | no |
| completeness | low (see document-completeness.json) | 98/95/85/70 | no |

## Corpus (bid_readiness support)

| Target | Result |
|--------|--------|
| ≥30 processes | **188** |
| ≥10 engineering | **17** |
| ≥10 envelopes | **113** |
| ≥5 families | **6** (ciga_ckan, compras_gov, pncp, portal_institucional, sc_compras, tce_sc) |
| ≥500 annotations | **1569** |

`issue_137_unblock_allowed`: **false** until human ground truth + FP/FN + suite on HEAD + no false readiness language.

## Blockers remaining
- Active entities without operational SUCCESS (HTML connection failures / auth / no entity portal)
- Independent recall/financial below thresholds
- Completeness limited by public publication practices
- Full suite/lint not re-run end-to-end in this campaign slice (targeted process_documents tests: 20 passed)

## Commands (VPS)
```bash
cd /opt/extra-consultoria
export PROCESS_DOCUMENTS_META_ROOT=/var/lib/extra-consultoria/output/process_documents
export PROCESS_DOCUMENTS_RAW_ROOT=/var/lib/extra-consultoria/raw/process_documents
.venv/bin/python -m scripts.process_documents discover --all
.venv/bin/python -m scripts.process_documents coverage --full
.venv/bin/python -m scripts.process_documents.vps_live_campaign
systemctl status extra-process-documents-incremental.timer
```
