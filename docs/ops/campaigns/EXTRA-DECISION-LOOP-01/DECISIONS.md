# DECISIONS — EXTRA-DECISION-LOOP-01

## Arquitetura reutilizada

- `scripts/ops/weekly_cycle.py` — DSN, freshness, universe scope SQL, exit codes
- `scripts/opportunity_intel/ranking.py` — GO/REVIEW/NO_GO determinístico + hard blocks
- `config/client_profiles/extra.yaml` — perfil versionado
- PostgreSQL local / `opportunity_intel`

## Decisões de desenho

| # | Decisão | Motivo |
|---|---------|--------|
| D1 | Novos módulos puros + orquestrador, sem reescrever weekly | Non-goal: não reescrever arquitetura |
| D2 | Ranking interno GO/REVIEW/NO_GO preservado; borda PARTICIPAR/REVIEW/NÃO_PARTICIPAR | Compatibilidade + linguagem consultiva |
| D3 | Override sensível em `extra.local.yaml` gitignored | Não commitar capital/margem reais |
| D4 | PARTICIPAR exige reconfirmação `ok` + sem hard block + sem freshness stale | Fail-closed |
| D5 | Perfil pendente material → REVIEW, não auto NÃO_PARTICIPAR | AC explícito |
| D6 | Calibração `PENDING_HUMAN` sem inventar métricas | Labels nunca auto-preenchidos |
| D7 | PDF via reportlab + Excel openpyxl + reconcile fail-closed | Produto utilizável em reunião |
| D8 | Reconfirm offline opt-in (`--offline-reconfirm` / env) para CI/local sem martelar PNCP | Distingue offline de HTTP live |

## Mapeamento

```
GO            → PARTICIPAR
REVIEW        → REVIEW
NO_GO         → NÃO_PARTICIPAR
```
