# PROCESS-DOCS-01 — Honest residual packaging (final for this wave)

Generated: 2026-07-30T23:37:09.241499+00:00

## Capability
`procurement_process_documents`

## Independent metrics (no average, no denom shrink)

| Metric | Result | Target | Gate |
|--------|--------|--------|------|
| discovery | 100% (1093/1093) | 100% | **MET** |
| operational actives | 96.56% (393/407) | ≥95% | **MET** |
| process recall | 100% (807/807) | ≥98% | **MET** |
| financial | 100% | ≥99% | **MET** |
| notice/anexos | 99.94% | ≥98% | **MET** |
| session/judgment | 99.94% | ≥95% | **MET** |
| winning proposal | **8.91%** | ≥85% | **OPEN** |
| qualification | **1.27%** | ≥70% | **OPEN** |

`coverage --full` exit **6** (win/qual only).

## Residual publication blockers (nominal, in denominator)

### Winning proposal (2946 residual)
- **Blocker:** `winning_proposal_not_published_publicly`
- Tried: PNCP arquivos, PNCP item resultados, ZIP members, SC Compras, PCP detail, HTML, CIGA DOM
- Public when available: winner CNPJ/name + valor homologado (metadata residual)
- Not public in sample: full commercial proposal PDF / planilha do licitante on most portals

### Qualification (3193 residual)
- **Blocker:** `bidder_qualification_not_published_publicly`
- Tried: same multi-source set
- Rare public habilitação/certidão titles only
- Not public: full bidder qualification packs

**Action chosen:** leave win/qual **unclosed**; do not shrink denominators; expand only if new public sources appear.

## bid_readiness / #137
- Corpus min targets: met
- GT slots: 600 structural-labeled from CAS (`present`); **human_confirmed=0**
- FP/FN: automated structural candidates only
- **`candidate_complete`: false**
- **READY_TO_SUBMIT: forbidden**
- **Issue #137: OPEN** (needs human confirmation of GT)
- **PR #133: blocked** until #137 + suite on exact HEAD

## VPS
- host `ec-prod`
- code `/opt/extra-consultoria/scripts/process_documents`
- meta `/var/lib/extra-consultoria/output/process_documents`

## PR
https://github.com/tjsasakifln/extra-cli/pull/184

## Branch
`feat/public-process-documents-coverage`
