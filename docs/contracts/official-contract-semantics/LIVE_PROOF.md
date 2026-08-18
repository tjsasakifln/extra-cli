# Live-readonly proof — SC window 2026-07-01..2026-07-07

**no publication, no production write, no inferred fact from absence**

## Replay

Exact argv that produced the hashes below:

```bash
python3 -m scripts.official_contract_semantics live-readonly --limit 8 --as-of 2026-08-17 --skip-pages --cache-dir /tmp/grok-goal-beb0997cc248/implementer/live-cache --out /tmp/grok-goal-beb0997cc248/implementer/live
```

Portable form (same extract; local `--out` / `--cache-dir`):

```bash
python3 -m scripts.official_contract_semantics live-readonly --limit 8 --as-of 2026-08-17 --skip-pages
```

## Result

| Métrica | Valor |
|---|---|
| Documentos oficiais considerados | 5 |
| Obtidos | 5 |
| Falhas de documento | 0 |
| Observações válidas | 5 |
| Conflitos | 0 |
| HOLD_FOR_DATA (todos) | 5 |
| Tecnicamente elegíveis para o engine | 0 |
| Escrita em produção | false |

DSN local (`pncp_supplier_contracts`) ficou **indisponível** (conexão recusada / DSN ausente no processo). A consulta oficial usada foi `GET https://pncp.gov.br/api/consulta/v1/contratos?dataInicial=20260701&dataFinal=20260707&pagina=1&tamanhoPagina=10`, com filtro SC no cliente.

## Cobertura por campo (5 observações)

| Campo | known | unknown |
|---|---|---|
| object_text | 5 | 0 |
| value_amount | 5 | 0 |
| value_semantic (`valor_global` quando o campo oficial é `valorGlobal`) | 5 | 0 |
| period_start / period_end | 5 | 0 |
| supplier_identifier | 5 | 0 |
| unit | 0 | 5 |
| quantity | 0 | 5 |
| execution_regime | 0 | 5 |
| procurement_modality | 0 | 5 |
| currency | 0 | 5 |

A API de contratos do PNCP, nesta janela, **não publica** unidade, quantidade, regime nem modalidade. Esses campos permaneceram `null`. Nada foi inferido.

## Engine #415 sobre a exportação live

`status=HOLD_FOR_DATA`  
`reason_codes=ambiguous_typology, unit_unknown, fields_unavailable, fixture_not_official_live`  
`usable_n=0`

## Hashes

`sha256sum` of the final on-disk files (manifest is written once; it hashes sibling `live-observations.jsonl` only, never a self-hash after rewrite):

- `live-observations.jsonl` SHA256 `f535a32aefa29b57a5d7cf6e666911b9dd19f0e512c3698b115036eeea809328`
- `live-manifest.json` SHA256 `8bc96cc9f4292d7c6f7cbdfc35ba057e1f7dd108adcb5ffb76b6b24ee4a53b7d`

Baseline #414/#415: a primeira janela oficial terminou sem candidato editorial por falta destas observações. Esta camada agora **mostra** o que falta. Não fabrica avanço.
