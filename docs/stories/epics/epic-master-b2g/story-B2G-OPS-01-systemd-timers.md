---
story_id: B2G-OPS-01
title: "Unificar e ativar systemd timers — nomenclatura, schedule, OnFailure"
status: ready
priority: P1
risk_level: STANDARD
effort: M
agent: "@devops"
epic: EPIC-MASTER-B2G-READINESS
phase: 7
depends_on: [B2G-INFRA-01]
blocks: [B2G-OPS-04]
---

# Story B2G-OPS-01: Unificar Systemd Timers

## Problema

3 padrões de nomenclatura coexistem (pncp-*, dom-sc-*, extra-*), 2 templates OnFailure, install.sh vs provision-vps.sh inconsistentes, selenium timer zumbi (chama source removido do registry), timers sem service correspondente (extra-panorama-weekly, extra-db-purge).

## Escopo

**IN:** Renomear TODOS para padrão `extra-*`, consolidar 2 OnFailure templates em 1, remover timer selenium zumbi, criar timers faltantes (panorama-weekly, db-purge, ciga-ckan, sc-compras), validar staggered schedule, testar cada timer com dry-run.

## Acceptance Criteria

1. **AC1:** 100% dos timers em `deploy/systemd/` seguem padrão `extra-{source}-{action}`  
2. **AC2:** `extra-onfailure@.service` é o único template; `onfailure@.service` removido
3. **AC3:** Timer selenium (`extra-crawl-selenium`) removido ou corrigido (não chama source inexistente)
4. **AC4:** Todos os timers têm service correspondente com `ExecStart=` funcional
5. **AC5:** Staggered schedule documentado — sem overlap de crawlers
6. **AC6:** `systemctl list-timers 'extra-*'` mostra 20+ timers com próximos agendamentos

## Tasks

- [ ] Task 1: Auditar todos os 44 arquivos em `deploy/systemd/`
- [ ] Task 2: Renomear para padrão `extra-*` unificado
- [ ] Task 3: Consolidar OnFailure templates
- [ ] Task 4: Remover/corrigir timer selenium zumbi
- [ ] Task 5: Criar timers faltantes (panorama-weekly, db-purge, etc.)
- [ ] Task 6: Atualizar `provision-vps.sh` com lista correta
- [ ] Task 7: Testar cada timer com `systemctl start` (dry-run)

## Definition of Done

- [ ] Nomenclatura 100% unificada
- [ ] Nenhum timer zumbi
- [ ] OnFailure único e funcional
- [ ] Staggered schedule documentado
- [ ] systemctl list-timers limpo

## Arquivos Afetados

- `deploy/systemd/*` (rename de ~30 arquivos)
- `deploy/provision-vps.sh`
- `deploy/install.sh`
