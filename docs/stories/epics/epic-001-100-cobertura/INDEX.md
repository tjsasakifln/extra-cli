# EPIC-001: 100% Cobertura — INDEX

> **Epic:** EPIC-001 | **Status:** Backlog | **PRD:** v1.1

## Stories

| # | Story | Prioridade | Estimativa | Status | Executor | Quality Gate |
|---|-------|------------|------------|--------|----------|-------------|
| [001.1](story-001.1-systemd-timers.md) | Systemd timers — 7 faltantes | P1 | 4h | ✅ Ready | @devops | @architect |
| [001.2](story-001.2-tce-sc-crawler.md) | TCE-SC e-Sfinge crawler | P1 | 16h | ✅ Ready | @dev | @architect |
| [001.3](story-001.3-entity-name-matching.md) | Entity name-matching refinement | P1 | 8h | ✅ Ready | @dev | @architect |
| [001.4](story-001.4-seed-entities.md) | Seed sc_public_entities | P2 | 3h | ✅ Ready | @data-engineer | @dev |
| [001.5](story-001.5-coverage-monitoring.md) | Coverage baseline + monitoring | P2 | 6h | ✅ Ready | @dev | @architect |
| [001.6](story-001.6-transparencia-gap-fill.md) | Transparência gap-fill | P2 | 12h | ✅ Ready | @dev | @architect |
| [001.7](story-001.7-coverage-report.md) | Weekly coverage report | P3 | 4h | ✅ Ready | @dev | @architect |

## Estimativa Total

| Prioridade | Stories | Horas |
|-----------|---------|-------|
| P1 | 3 stories | 28h |
| P2 | 3 stories | 21h |
| P3 | 1 story | 4h |
| **Total** | **7 stories** | **53h** |

## Ordem de Execução Recomendada

```
001.4 (seed) ──→ 001.1 (timers) ──→ 001.3 (matching) ──→ 001.5 (baseline)
                    │
                    └──→ 001.2 (TCE-SC) ──→ 001.6 (gap-fill) ──→ 001.7 (report)
```

**Paralelismo possível:** 001.1 e 001.2 podem rodar em paralelo (sem dependência entre si).  
**Dependência crítica:** 001.5 depende de 001.1 concluído (precisa de dados fluindo para medir baseline).

## Métricas de Sucesso do Epic

- [ ] 100% systemd timers ativos (10/10)
- [ ] Cobertura de entes ≥ 95% em até 4 semanas
- [ ] Entity matching accuracy ≥ 95%
- [ ] TCE-SC crawler funcional e integrado
- [ ] Relatório semanal de cobertura automatizado
- [ ] Gap residual documentado (entes sem publicações digitais)

---

*INDEX gerado por Morgan (PM) — 2026-07-10*
