# L1.2 — Universo canônico (re-prova)

**Data:** 2026-07-16

## Planilha

| Métrica | Valor |
|---------|-------|
| Arquivo | `Extra - alvos de licitação. R-0.xlsx` |
| SHA-256 | `d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486` |
| Total seed | 2085 |
| Included (raio) | **1093** |
| Excluded | 992 |
| Unresolved | 0 |

## Materialização DB

```bash
PYTHONPATH=. python3 scripts/universe_tools.py snapshot generate
```

| Tabela | Count |
|--------|-------|
| `target_universe_runs` | 1 |
| `target_universe_entities` | **2085** |
| radius_decision=included | **1093** |
| radius_decision=excluded | 992 |

Capture: `gate1-universe.log`.
