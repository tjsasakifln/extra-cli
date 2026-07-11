# EPIC: Resolucao de Debitos Tecnicos -- Extra Consultoria

**Epic ID:** EPIC-TD-001
**Criado por:** @pm (Morgan)
**Data:** 2026-07-11
**Status:** Ready for Development

---

## Objetivo

Resolver os 38 debitos tecnicos identificados no Brownfield Discovery Assessment, transformando a plataforma Extra Consultoria de um prototipo funcional em um sistema profissional pronto para escala.

## Escopo

### Incluido

- Fase 0: Emergencia -- Backup automatizado e correcao de imports quebrados (2 debitos CRITICAL)
- Fase 1: Quick Wins -- Otimizacao de queries, remocao de segredos, inicio da suite de testes
- Fase 2: Schema & Migrations -- Reconstrucao de migrations do zero, normalizacao de schema
- Fase 3: Refactoring Seguro -- Refatoracao de monitor.py, consolidacao de crawlers, type hints, tratamento de erros
- Fase 4: Qualidade de Codigo -- Expansao de cobertura de testes, CI/CD pipeline, lint automatizado
- Fase 5: Resiliencia & Observabilidade -- Logging estruturado, resume de crawlers, otimizacao de performance, hardening, monitoramento
- Fase 6: Documentacao -- Documentacao operacional, runbooks e onboarding

### Excluido

- Novas fontes de dados (DOM-SC, PCP v2, ComprasGov, TCE-SC, Portal Transparencia)
- Features de produto (relatorios, dashboards, portal web)
- Integracoes externas alem das ja existentes
- Migracao para cloud/Supabase
- Migracao para ORM (decidido como INFORMATIVO pelo assessment)

## Fases

| Fase | Nome | Horas | Custo | Stories |
|------|------|-------|-------|---------|
| 0 | Emergencia | 8h | R$ 1.200 | 2 stories |
| 1 | Quick Wins | 10h | R$ 1.500 | 3 stories |
| 2 | Schema & Migrations | 21h | R$ 3.150 | 3 stories |
| 3 | Refactoring Seguro | 30.5h | R$ 4.575 | 4 stories |
| 4 | Qualidade de Codigo | 31.5h | R$ 4.725 | 3 stories |
| 5 | Resiliencia & Observabilidade | 30h | R$ 4.500 | 5 stories |
| 6 | Documentacao | 9.5h | R$ 1.425 | 2 stories |
| **TOTAL** | | **140.5h** | **R$ 21.075** | **22 stories** |

## Criterios de Sucesso

- [ ] Zero debitos CRITICAL abertos
- [ ] Maximo 2 debitos HIGH abertos
- [ ] Cobertura de testes >= 60% (modulos core), >= 30% (geral)
- [ ] CI/CD pipeline funcional (lint + test + typecheck por PR)
- [ ] Backup automatizado diario via systemd timer com retention 7+4
- [ ] Migrations 100% sincronizadas com schema real
- [ ] Zero senhas/segredos em codigo versionado
- [ ] Documentacao operacional completa (runbook + setup + troubleshooting)

## Dependencias

- Assessment tecnico: `docs/prd/technical-debt-assessment.md`
- Aprovacao de budget pelos stakeholders
- Acesso ao servidor Hetzner VPS para backup e migrations

## Story List

| Story ID | Nome | Fase | Horas | Debitos |
|----------|------|------|-------|---------|
| TD-0.1 | Setup backup automatizado | 0 | 4h | TD-DB-15 |
| TD-0.2 | Corrigir imports quebrados | 0 | 4h | TD-SYS-001 |
| TD-1.1 | Otimizacao de queries | 1 | 3h | TD-DB-08, TD-DB-11 |
| TD-1.2 | Remover segredos hardcoded | 1 | 3h | TD-DB-05, TD-SYS-005 |
| TD-1.3 | Iniciar suite de testes | 1 | 4h | TD-SYS-009 |
| TD-2.1 | Reconstruir migrations do zero | 2 | 10h | TD-DB-01, TD-DB-17 |
| TD-2.2 | Aplicar migrations 009-012 adaptadas | 2 | 5h | TD-DB-02a, TD-DB-02b |
| TD-2.3 | Normalizacao e constraints | 2 | 6h | TD-DB-03, TD-DB-06, TD-DB-07 |
| TD-3.1 | Refatorar monitor.py | 3 | 8h | TD-SYS-011 |
| TD-3.2 | Eliminar codigo duplicado | 3 | 11h | TD-SYS-016, TD-SYS-002, TD-DB-16 |
| TD-3.3 | Adicionar type hints | 3 | 4h | TD-SYS-003 |
| TD-3.4 | Melhorar tratamento de erros | 3 | 7.5h | TD-SYS-008, TD-SYS-013, TD-DB-12 |
| TD-4.1 | Expandir cobertura de testes | 4 | 16h | TD-SYS-009, TD-SYS-014 |
| TD-4.2 | Setup CI/CD pipeline | 4 | 14h | TD-OPS-01, TD-SYS-015 |
| TD-4.3 | Code review + lint automatizado | 4 | 1.5h | TD-SYS-006, TD-SYS-007 |
| TD-5.1 | Logging estruturado | 5 | 10h | TD-SYS-010, TD-OPS-03 |
| TD-5.2 | Sistema de resume para crawlers | 5 | 1h | TD-DB-10 |
| TD-5.3 | Otimizacao de performance | 5 | 12h | TD-DB-04, TD-DB-09, TD-DB-13, TD-DB-14 |
| TD-5.4 | Hardening de seguranca | 5 | 3h | TD-SEC-02 |
| TD-5.5 | Monitoramento e alertas | 5 | 4h | TD-OPS-03 expandido |
| TD-6.1 | Documentacao operacional | 6 | 6.5h | TD-DOC-01, TD-SYS-012 |
| TD-6.2 | Runbooks e onboarding | 6 | 3h | TD-SYS-004 |

## Grafo de Dependencias entre Stories

```
TD-0.1 ─┬─ (nenhuma)
TD-0.2 ─┤
         │
TD-1.1 ─┤
TD-1.2 ─┤
TD-1.3 ─┤
         │
TD-2.1 ─┤
TD-2.2 ─┤ ← TD-2.1
TD-2.3 ─┤ ← TD-2.1 (parcial)
         │
TD-3.1 ─┤ ← TD-1.3
TD-3.2 ─┤ ← TD-0.2, TD-1.3
TD-3.3 ─┤ (independente)
TD-3.4 ─┤ (independente)
         │
TD-4.1 ─┤ ← TD-1.3, TD-3.1, TD-3.2
TD-4.2 ─┤ ← TD-4.1
TD-4.3 ─┤ ← TD-4.2 (parcial)
         │
TD-5.1 ─┤ ← TD-3.1, TD-3.4 (preferencial)
TD-5.2 ─┤ (independente)
TD-5.3 ─┤ ← TD-2.1 (parcial)
TD-5.4 ─┤ ← TD-1.2
TD-5.5 ─┤ ← TD-5.1
         │
TD-6.1 ─┤ ← (fases anteriores)
TD-6.2 ─┤ ← TD-6.1
```

## Riscos

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Perda do DataLake durante migracao de schema | BAIXA | CRITICO | Backup antes de qualquer alteracao (TD-0.1 primeiro) |
| Refatoracao quebra producao sem testes | ALTA | CRITICO | TD-1.3 e TD-4.1 antes de TD-3.1 e TD-3.2 |
| Senha rotacionada sem comunicacao | BAIXA | ALTO | Coordenar com stakeholders a janela de rotacao |

---

## Documentos Referenciados

- Assessment final: `docs/prd/technical-debt-assessment.md`
- System Architecture: `docs/architecture/system-architecture.md`
- DB Audit: `supabase/docs/DB-AUDIT.md`
- DB Schema: `supabase/docs/SCHEMA.md`
- DB Specialist Review: `docs/prd/db-specialist-review.md`
- QA Review: `docs/prd/qa-review.md`

---

**Criado por:** @pm (Morgan)
**Data:** 2026-07-11
**Framework:** AIOX Brownfield Discovery -- Fase 10
