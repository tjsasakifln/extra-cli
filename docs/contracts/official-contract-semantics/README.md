# Official contract semantic observations

Camada de observabilidade semântica oficial. Engines de ranking (#414) e comparáveis (#415) não são alterados.

## Comandos

```bash
python3 -m scripts.official_contract_semantics extract --input PATH --out out/extract.json
python3 -m scripts.official_contract_semantics validate --input PATH --out out/validate.json
python3 -m scripts.official_contract_semantics reconcile --input out/extract.json --out out/reconciled.jsonl
python3 -m scripts.official_contract_semantics export-comparables --input out/reconciled.jsonl --out out/export-comparables.json
python3 -m scripts.official_contract_semantics export-publication-evidence --input out/reconciled.jsonl --out out/export-publication-evidence.json
python3 -m scripts.official_contract_semantics pipeline --input PATH --out out/pipeline
python3 -m scripts.official_contract_semantics live-readonly --limit 8 --out out/live --skip-pages
```

Replay sobre a exportação, sem tocar nos engines:

```bash
python3 -m scripts.contract_comparables build --corpus out/export-comparables.json --case official_semantics_export
python3 -m scripts.contract_publication rank --snapshot out/export-publication-evidence.json --out out/rank
```

## Integração posterior (não feita aqui)

Nenhuma alteração em `scripts/contract_comparables/**` ou `scripts/contract_publication/**`. Se um consumidor quiser ler esta camada automaticamente, a integração é um import do JSON exportado.
