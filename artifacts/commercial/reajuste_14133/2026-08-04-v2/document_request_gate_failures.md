# DOCUMENT_REQUEST gate failures (149 suppliers)

HEAD=`419da333238e` · deep=211 · READY=0

## Universal blockers (149/149)

| gate | n |
|------|--:|
| `data_base_exata_localizada` | 149 |
| `contato_empresarial_verificavel` | 149 |
| `revisao_humana_concluida` | 149 |
| `indice_ou_formula_localizada` | 123 |
| `clausula_reajuste_localizada` | 26 |

## Best-contract classificacao

```json
{"STRONG_CANDIDATE": 26, "REVIEW_REQUIRED": 123}
```

## Why exhaustion (not invented READY)

- 211 unique contracts with official PDF text extracts (≥200 documentary floor)
- 751 evidence lines with page+excerpt
- 0 contacts verifiable on rebind portfolio for DOC_REQ
- 0 human_review_done
- 0 DATA_BASE_CONFIRMED (all PROXY_PROSPECTION_ONLY for ready path)
