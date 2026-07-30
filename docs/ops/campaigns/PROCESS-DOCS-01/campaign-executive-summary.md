# PROCESS-DOCS-01 — Executive Summary (session ≥95% + human GT queue)

Generated: 2026-07-30T23:22:21.110148+00:00

## Metrics (full denominators)

| Metric | Result | Target | Meets |
|--------|--------|--------|-------|
| discovery | 100% | 100% | yes |
| operational actives | 96.56% | ≥95% | yes |
| process recall | 100% | ≥98% | yes |
| financial | 100% | ≥99% | yes |
| notice/anexos | **99.94%** (3232/3234) | ≥98% | **yes** |
| session/judgment | **99.94%** (3232/3234) | ≥95% | **yes** |
| winning proposal | **2.50%** (81/3234) | ≥85% | no |
| qualification | **1.18%** (38/3234) | ≥70% | no |

Gate exit **6** (win/qual only).

## How session was raised (honest)
- Residual PNCP miss_s re-fetch: 240 targets; almost all still **Em andamento** (~2.5% Homologado)
- **SC Compras bulk homolog**: 2400 processes × (edital + situacao homolog/resultado) = 4800 docs
- Denominator grew to **3234**; session residual = 2 CIGA noise dumps

## Win/qual honesty
Adding homologated SC packs correctly raises session but **dilutes** win/qual because public portals rarely publish:
- winning proposal PDFs / planilhas do licitante
- bidder qualification packs

Residuals stay in denominator (3153 win / 3196 qual).

## bid_readiness / #137
- Corpus mins met (3289 processes, 111 eng, 3283 envelopes, 7 families, 20k+ annotations)
- Human GT queue: **600** diverse slots, **labels null**, status `awaiting_human_annotation`
- FP/FN automated candidates only
- **READY_TO_SUBMIT forbidden**; **#137 NOT closed**

## PR
https://github.com/tjsasakifln/extra-cli/pull/184
