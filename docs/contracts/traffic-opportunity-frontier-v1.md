# `traffic-opportunity-frontier/1.0` producer contract

Version: `v1.0.0`
Schema: `traffic-opportunity-frontier/1.0`
Machine-readable twin: [`traffic-opportunity-frontier-v1.json`](traffic-opportunity-frontier-v1.json)

Producer: Extra CLI (`python3 -m scripts.traffic_frontier`)
Canonical consumer: `web-cfg / traffic-opportunity-frontier` (`tjsasakifln/web-cfg#65`, PR `#73`)
Related producer issues: extra-cli `#415` (comparables), `#302` (denominador nacional), `#400` (research flagship)

## Boundary

This is a **producer-only**, versioned, fail-closed planning pack. It is not a
page publisher, indexer, keyword list, second score engine, crawler, or
datalake writer.

- SELECT-only when a DSN is present; queries are bounded.
- No backfill, no truth-plane mutation, no organic Content Value Score change.
- `no_publication_authorization=true` and `no_index_authorization=true` on
  every opportunity and on the pack manifest.
- Extra 1093 is never a national denominator. A recorte (SC, Sul, 4-UF) is
  never claimed as Brasil. `#302` `nacional_completo` is not closed.

web-cfg may read the pack to plan Market Answers, calculators, comparativos
and aggregated analyses. It must not publish or index from this artifact alone.

## Score

Auditable 0–100. Weights (sum 100), **distinct** from
`scripts.organic.score.CONTENT_VALUE_WEIGHTS`:

| Dimension | Weight | Notes |
|---|---|---|
| Search / Question Demand Evidence | 20 | GSC if present; MARKET_JOB plausibility otherwise. Missing GSC ≠ 0. |
| Commercial Pain and Ticket Fit | 20 | Dor econômica + ticket CONFENGE |
| Data Coverage and Freshness | 20 | Recorte honesto; stale → HOLD |
| Proprietary Differentiation | 15 | Por que a CONFENGE responde melhor |
| Citability / Earned Distribution | 10 | Citabilidade factual |
| Time to Publish | 10 | Tempo até publicação *segura* |
| Maintenance Cost | 5 | **Invertido** (custo alto reduz score) |

High score never promotes insufficient coverage to `READY`.

## Hard gates

| Gate | Fail state |
|---|---|
| Pergunta genérica / sem edge | `REJECT` |
| Resposta independente ausente | `REJECT` |
| Cobertura incompleta ou stale | `HOLD_FOR_DATA` |
| Método irreproduzível | `REJECT` |
| CTA desconectada | score reduzido; não passa o gate |
| Doorway | `REJECT` |
| Duplicata de URL/ativo existente | `REJECT` (`MERGE`) |
| Claim jurídico/econômico não sustentado | `REJECT` |
| Nacionalização de recorte estadual | `REJECT` |
| Troca de UF/CNPJ sem diferença intelectual | `REJECT` |

## States

Opportunity: `READY` | `HOLD_FOR_DATA` | `REJECT`

Campaign: `READY_FOR_WEB_CONSUMER` | `BLOCKED_DATA_COVERAGE` | `BLOCKED_SOURCE_ACCESS` | `BLOCKED_CI`

`READY_FOR_WEB_CONSUMER` requires three `READY` top items, pairwise distinct
questions, at least two `funnel_stage` values, and no unauthorized national
claim. Otherwise the pack stays fail-closed.

## Epistemic split

Every scored item separates `SEARCH_SIGNAL`, `MARKET_JOB`, `DATA_COVERAGE`,
`COMMERCIAL_FIT`, `DISTINCTIVE_EDGE`, `UNKNOWN`, `PROHIBITED_CLAIM`.

Absence of GSC is not absence of demand. External keyword volumes are not
invented. Unknown stays unknown.

## Families

A preço/ticket · B reajuste/reequilíbrio · C licitação/proposta ·
D execução contratual · E inteligência de mercado.

## Determinism

`as_of` comes from the frozen catalog snapshot, never wall-clock. JSON is
canonical (`sort_keys`, stable separators). Two builds on the same inputs
emit identical `SHA256SUMS.txt`.

## Consume

```bash
python3 -m scripts.traffic_frontier --out DIR --as-of 2026-08-01
```

web-cfg reads `exports/traffic-opportunity-frontier/v1/` (`opportunities.json`
+ `top3/<id>/`). Editorial writing still needs a human pass and the public-read
claim gate before any page is published.
