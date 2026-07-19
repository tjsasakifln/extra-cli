# HANDOFF — EXTRA-OPS-95-FOUNDATION (PARTIAL)

**UTC:** 2026-07-19T08:15:04.793041+00:00  
**Branch:** `campaign/extra-ops-95-20260719`  
**Status:** PARTIAL

## First commands

```bash
cd "/mnt/d/extra consultoria"
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
git log -1 --oneline
cat docs/ops/campaigns/EXTRA-OPS-95/evidence/session-metrics.json
```

## Metrics

| Metric | Value |
|--------|------:|
| DOD | 270/1352 (19.9704%) |
| Editais presence | 285 (26.075%) |
| Contracts presence | 368 (33.6688%) |
| Contracts SZ | 722 |
| **Contracts ops proxy** | **1090/1093 (99.7255%) ≥95%** |
| Residual | 3 (malformed cnpj_8 PF/PRF) |

## Definition of ops proxy

presence of orgao CNPJ-8 in contracts lake OR entity-scoped success_zero  
(cnpj14 root match + http_204_complete; residual identity via BrasilAPI-validated matriz 0001+DV)

**NOT** seven-stage operational coverage.

## Do not repeat

- token_containment without cnpj8 root
- publicacao cnpjOrgao as filtered API
- claim campaign DONE / editais 95% / DOD 55%
- invent CNPJ without BrasilAPI/Receita+root validation

## Next fronts

1. Editais presence/ops (26% — main gap)
2. DOD toward 55% with evidence only
3. N09 gold sample or formal BLOCKED_SOURCE
4. Independent QA + skeptic
5. Fix 3 malformed cnpj_8 entities (00394494*)

## Veredito

**PARTIAL** — contracts ops proxy ≥95% achieved under documented definition; editais, DOD, N09, 7-stage, full DONE gates open.
