# BASELINE — EXTRA-DECISION-LOOP-01

**Medido em:** 2026-07-19  
**main SHA:** `d6d9e1984e348d64a669546613e192e4ebf610cd` (merge PR #49 / EXTRA-OPERATIONAL-PROOF-01)  
**Branch:** `goal/extra-decision-loop-01`  
**DSN:** `postgresql://test:test@127.0.0.1:5433/extra_test`

## Contagens locais

| Métrica | Valor |
|---------|------:|
| `sc_public_entities` | 2.085 |
| Raio 200 km | 1.093 |
| `opportunity_intel` | 401 |
| open/upcoming ativos | 391 |
| Ranking GO | **0** |
| Ranking REVIEW | 397 |
| Ranking NO_GO | 4 |
| Sem valor estimado (open/upcoming) | 46 |
| Sem prazo | 0 |
| Sem link_edital | 254 |

## Perfil Extra (antes)

- `profile_id=extra_construtora` v2
- Hash resolvido: `db621d0de72e523f…`
- **11 campos críticos PENDING** (capital_giro, margem, CATs, etc.)
- Representações duplicadas: top-level nulls + `elicitation` + `capacity`

## Entry points existentes

| Comando | Papel |
|---------|--------|
| `make extra-weekly` | Ciclo semanal canônico (PROOF-01) — MD+Excel+CSV, **PDF residual** |
| `python -m scripts.opportunity_intel.cli` | Coleta/ranking legado |
| `deliverable_package_final` | Pacote fixture-first |

**Lacuna:** não havia loop vertical de decisão (perfil hash → snapshot → decisão multi-dim → revisão humana → PDF+Excel reconciliados).

## Claims baseline (honestos)

**Permitidos:** universo 1093; 391 open/upcoming; weekly cycle existe; GO=0; perfil incompleto documentado.

**Proibidos:** LOCAL_READY, 95% cobertura/recall, PROJECT_DONE, aceite humano implícito, fabricar PARTICIPAR.

## Objetivo da campanha

```bash
make extra-decision-pack
# → python -m scripts.ops.decision_pack --strict
```

com decisão explicável, snapshot/delta, fila humana e PDF+Excel do mesmo run.
