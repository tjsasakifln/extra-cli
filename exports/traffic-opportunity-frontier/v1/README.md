# Traffic opportunity frontier `traffic-opportunity-frontier/1.0`

**Campaign status:** `READY_FOR_WEB_CONSUMER`
**as_of:** `2026-08-01` (frozen snapshot, not wall-clock)
**Consumer:** web-cfg only · producer-only · SELECT-only · no backfill · no publication

## Authorization

- `no_publication_authorization=true`
- `no_index_authorization=true`

This pack does not claim traffic, indexação, lead or receita.

## Top 3

1. `tof-data-base-reajuste-reequilibrio` (mofu, READY, score 84) — Como a data-base e o índice declarado distinguem reajuste de reequilíbrio em contrato de obra pública — e o que o extrato público não prova sobre margem?
1. `tof-eventos-contratuais-revisao` (bofu, READY, score 81) — Quais eventos contratuais (aditivo, atraso, glosa, alteração) merecem revisão técnica da equação — e o que o extrato público não permite concluir?
1. `tof-ticket-edificacao-sc` (tofu, READY, score 80) — Qual o ticket típico (P25/mediana/P75) de contratos de edificação pública em Santa Catarina, e por que esse valor não é custo unitário?

## Counts

- prioritized: 12
- READY: 4
- HOLD_FOR_DATA: 10
- REJECT: 5

## How web-cfg consumes

1. Read `opportunities.json` for the ranked ≤12.
2. For editorial, open `top3/<id>/editorial_brief.md` plus `evidence.json` and `method.json`.
3. Do not publish or index from this pack. Run the public-read claim gate first.
4. Recorte SC is never Brasil. Extra 1093 is never the national denominator.

## Reproduce

```bash
python3 -m scripts.traffic_frontier --out DIR --as-of 2026-08-01
```

Two builds on this catalog emit identical `SHA256SUMS.txt`.

