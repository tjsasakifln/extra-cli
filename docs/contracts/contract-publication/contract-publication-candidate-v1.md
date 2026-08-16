# `contract-publication-candidate/1.0`

Score: `publication-value-score/1.0`
Machine-readable twin: [`contract-publication-candidate-v1.json`](contract-publication-candidate-v1.json)

Factual producer for issue #414. Ranks official public-contract records as
editorial investigation candidates. It does not authorize publication,
indexation, pages or brand copy.

Public states: `REJECT | HOLD_FOR_DATA | EDITORIAL_REVIEW`.
`PUBLISHABLE_*` and `INDEX` are out of scope.

```bash
python3 -m scripts.contract_publication rank --snapshot PATH.json --out DIR
python3 -m scripts.contract_publication rebuild-pack --snapshot PATH.json --candidate-id ID --out pack.json
python3 -m scripts.contract_publication export-400 --snapshot PATH.json --out DIR
python3 -m scripts.contract_publication live --out DIR
```
