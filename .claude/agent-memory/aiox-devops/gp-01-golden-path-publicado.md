---
name: gp-01-golden-path-publicado
description: "GP-01 Golden Path Operacional publicado: DB persistente + 298 PNCP oportunidades + briefing funcional"
metadata:
  type: project
---

# GP-01 Golden Path Operacional — Publicado 2026-07-14

**Status:** Done, publicado via @devops
**Commit:** fbc4cc1 (+7616950 para state)

## O que foi entregue

- **DB persistente:** docker-compose.yml com volume PostgreSQL substituindo tmpfs volatil
- **Crawl PNCP funcional:** 298 oportunidades importadas (4 modalidades, SC)
- **Briefing funcional:** 150 oportunidades AEC, 83 orgaos, R$179.5M em valor estimado
- **CLI commands:** de 1/9 para 5/9 comandos funcionais em opportunity_intel
- **State file:** .aiox/state/stories/story-GP-01-golden-path.json completo com evidencias
- **Baseline estrategica:** .reversa/baseline/00-CHAMPION-BET.md documentando decisao

## Arquivos modificados

- `docker-compose.yml` — volume persistente
- `scripts/opportunity_intel/cli.py` — briefing query migrada
- `.aiox/state/stories/story-GP-01-golden-path.json` — state file
- `.reversa/baseline/00-CHAMPION-BET.md` — baseline e decisao
- `output/briefing-extra-2026-07-14.txt` — artefato de briefing

## Pre-condicoes de publicacao

Todas atendidas apos correcao do state file:
- status: Done
- po_closed: true
- qa_verdict: PASS
- publication_authorized: true
- reviewed_commit: fbc4cc1 (HEAD)
- gates.lint: PASS, gates.tests: PASS

## Observacoes

- Working tree continha alteracoes nao-relacionadas ao GP-01 (framework updates,
  skills, hooks) — nao afetaram o push pois o push envia apenas commits.
- State file precisou de atualizacao pos-commit: `reviewed_commit` apontava para
  `7c09470` (commit original substituido por `fbc4cc1`), e campos de publicacao
  estavam em false.

## Proximos passos sugeridos

- Cobrir os 4 comandos CLI restantes (6/9 -> 9/9)
- Expandir cobertura de fontes (CIGA, TCE-SC via Diario Oficial)
- Story GP-02 para evolucao do crawling multi-fonte
