# Sessão 2026-07-29 — SOAK + scheduler health (Terminal 3)

**Doc canônico da campanha:**  
[`docs/ops/campaigns/SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL.md`](../../ops/campaigns/SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL.md)

| | |
|--|--|
| Estado | **`SCHEDULERS_FAILED`** |
| Read-only | sim |
| SHA | `d05d4c3d` (main = VPS) |
| Contratos soak | FAIL (1/7 dias automáticos OK) |
| Editais soak | FAIL (timers crawl disabled) |
| Bloqueio #1 | checkpoint run_id preso em `contracts-90d-20260723T201229Z-4da85aaee0` |
| Conclusão honesta soak (mais cedo) | 2026-08-06 após fix |

Não promover DOD de soak com base em timer active ou arquivos diários sozinhos.
