# L1.5 — Golden path no HEAD (re-prova)

**Data:** 2026-07-16  
**Run ID:** `gp-20260716-194636`

## Comando

```bash
python3 scripts/golden_path.py --sources pcp,compras_gov --skip-freshness --skip-reports
```

## Resultado

| Campo | Valor |
|-------|--------|
| Status | **SUCCESS** |
| Exit code | **0** |
| pcp | OK fetched=181 |
| compras_gov | OK fetched=2 |
| Ledger | `list` com 2 runs (sem corrupção nested) |
| Wall clock | ~19.7s |

Capture: `gate1-golden-path.log`.

## Ledger fix

`scripts/golden_path.py` normaliza runs aninhados; testes em `tests/test_golden_path_ledger.py` (5 passed).
