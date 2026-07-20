# Próximo passo de desenvolvimento (sem reconstruir contexto)

**Atualizado:** 2026-07-20  
**Campanha arquitetural ativa:** `ARCH-RESET-2026-07-20`  
**Relatório:** `docs/ops/campaigns/ARCH-RESET-2026-07-20/FINAL-REPORT.md`  
**Overview:** `docs/architecture/overview.md`

## Prioridade humana (merge queue)

1. Revisar/mergear draft PRs **#54 → #55 → #56** (baseline, tests, entrypoints).  
2. Revisar spikes **#57 #58 #60** e evidência live **#59**.  
3. Decidir **#52** (decision loop MERGE_CANDIDATE) vs **#53** (ledger thin).  
4. Manter CTO stack **#48–#51** fora do caminho de produto até decisão explícita.

## Comandos de produto / engenharia

```bash
# Produto consultivo semanal (canônico)
make extra-weekly

# Engenharia (quando PR #56 em main)
make verify

# Ranking DoD ROI (governança de campanha, não pipeline de produto)
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

## Estado honesto

| Item | Estado |
|------|--------|
| Arquitetura-alvo | Decidida (ADR-023+); implementação em draft PRs |
| Cobertura operacional 95% | **NÃO claimada** |
| LOCAL_READY | **NOT_READY** |
| Live weekly (limitado) | **Prova em #59** (exit 0, 1 opp; contratos degradados) |
| Suíte completa global | **Debt** (SKIPPED≠verde) |

## Artefatos

- Campanha: `docs/ops/campaigns/ARCH-RESET-2026-07-20/`
- Glossário: `docs/GLOSSARY.md`
- Changelog: `CHANGELOG.md`
- Entry points: `docs/canonical-entry-points.yaml`
