# PROCESS-DOCS-01 — Executive Summary (deep multi-source)

Generated: 2026-07-30T23:00:03.742240+00:00

## Metrics (full denominators, no shrink)

| Metric | Result | Target | Meets |
|--------|--------|--------|-------|
| discovery | 100% | 100% | yes |
| operational | 96.56% | ≥95% | yes |
| recall | 100% | ≥98% | yes |
| financial | 100% | ≥99% | yes |
| notice/anexos | **99.65%** | ≥98% | **yes** |
| session/judgment | **71.50%** | ≥95% | no (residual 242) |
| winning proposal | **9.31%** | ≥85% | no (residual 770) |
| qualification | **4.48%** | ≥70% | no (residual 811) |

Gate exit **6**.

## Multi-source lifts this wave
- PNCP `/itens/{n}/resultados` → public winner package (session + proposal metadata)
- PNCP historico/atas + itens Homologado
- SC Compras situacao + edital metadata (25 entities, 375 session docs + notice backfill)
- PCP public detail endpoints: 404/500 (no public document API in sample)

## Corpus
- mins met (issue #137 still open — human FP/FN GT required)
- READY_TO_SUBMIT forbidden

## Honesty
Session/win/qual **not** marked complete. Residuals remain in denominator.
PR: https://github.com/tjsasakifln/extra-cli/pull/184
