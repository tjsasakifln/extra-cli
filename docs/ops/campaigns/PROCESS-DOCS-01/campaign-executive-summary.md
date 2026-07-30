# PROCESS-DOCS-01 — Executive Summary (completeness multi-source)

Generated: 2026-07-30T22:25:09.905861+00:00

## Capability
`procurement_process_documents`

## Metrics (independent — no average, no denominator shrink)

| Metric | Result | Target | Meets |
|--------|--------|--------|-------|
| discovery | 100% (1093/1093) | 100% | yes |
| operational actives | **96.56%** (393/407) | ≥95% | **yes** |
| process recall | **100%** (807/807) | ≥98% | **yes** |
| financial coverage | **100%** | ≥99% | **yes** |
| completeness edital/anexos | **98.80%** (824/834) | ≥98% | **yes** |
| completeness julgamento | **10.07%** | ≥95% | no — residual blocked |
| completeness proposta | **3.84%** | ≥85% | no — residual blocked |
| completeness habilitação | **4.56%** | ≥70% | no — residual blocked |

`coverage --full` exit **6** (session/win/qual only).

## Completeness work (this wave)
- Multi-source: PNCP arquivos + CIGA CKAN + generic HTML + **ZIP member expansion** (895 members / 137 processes) + `collect_process_key` residual (79 processes).
- Classifier: DFD/ETP/TR_/PE/EDITAL\d/dispensa + PNCP untitled process blobs → `anexo`.
- Denominator: **full** (834 processes with ≥1 doc). No shrink.
- Residual nominal blockers: `vps/pd-completeness-residuals.json`.

### Residual honesty (session/win/qual)
Public PNCP/CIGA packs rarely include ata, proposta vencedora or habilitação de licitantes. Residual counts remain in the denominator and block the completeness gate. Not counted as SUCCESS.

## Corpus / #137
- corpus min targets met; **issue_137_unblock_allowed=false**
- FP/FN automated candidates only; READY_TO_SUBMIT forbidden
- Issue #137 / PR #133 **not closed**

## VPS
- `/opt/extra-consultoria/scripts/process_documents`
- evidence `/var/lib/extra-consultoria/output/process_documents`
- PR https://github.com/tjsasakifln/extra-cli/pull/184
