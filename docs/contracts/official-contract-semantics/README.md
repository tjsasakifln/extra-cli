# Official contract semantic observations

Camada de observabilidade semântica oficial. Engines de ranking (#414) e comparáveis (#415) não são alterados.

## Contrato de consumo

| Uso downstream | Campos obrigatórios | Como tratar `HOLD_FOR_DATA` | Pode indexar/publicar? |
|---|---|---|---|
| Observação bruta | identidade oficial (`official_url` **ou** `source_document_id`+hash **ou** `source_system`+`contract_identifier`+`raw_record_hash`), `observation_id`, `epistemic_class`, `field_epistemics` | não promover campo `UNKNOWN` a fato | não |
| Engine #415 | `unit` conhecido **ou** `NOT_APPLICABLE` demonstrável; `execution_regime`; `procurement_modality`; `value_semantic`; `period_start`; `value_amount` | `technically_eligible_for_engine=false`; o engine deve recusar ou HOLD | não |
| Engine #414 | snapshot + `hold_report`; `authorizes_publication=false` | estados `HOLD_FOR_DATA` / `REJECT` / `EDITORIAL_REVIEW` apenas | **nunca** `INDEX` / `PUBLISHABLE_*` |
| Conteúdo editorial | nenhum estado desta camada autoriza | ausência ≠ fato negativo | não |

- **Fato oficial** (`FACT_OFFICIAL`): só o que a fonte oficial sustenta.
- **Observação derivada** (`OBSERVATION_DERIVED`): só com `derivation_method` identificável. O produtor não emite copy persuasiva nem diagnostica crédito, pleito, reajuste, irregularidade, capacidade empresarial ou inadimplência.
- **Desconhecido** (`UNKNOWN` / `HOLD_FOR_DATA`): campo necessário não demonstrado. Consumidor **não** preenche.
- **Não aplicável** (`NOT_APPLICABLE`): somente quando a fonte demonstra inaplicabilidade. `empreitada_global` sozinha **não** torna `unit` N/A.
- **Não encontrado / indisponível** (`NOT_FOUND` / `UNAVAILABLE` / `ABSENT`): resultado de busca delimitada ou falha de transporte. Não afirma inexistência no mundo.

## Versionamento e reprocessamento

- Schema `official-contract-observation/1.1`. Mudança de parser/schema altera `schema_version` / `extractor_version` e portanto `observation_id`.
- Replay da mesma entrada produz a mesma saída semântica. `extracted_at` não entra no hash.
- Persistência JSONL é append-only e idempotente por `observation_id`.

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
