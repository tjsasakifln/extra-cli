---
name: technical-debt-draft-v1
description: Technical debt DRAFT consolidado por Aria (Brownfield Fase 4) com 30 debitos (3 CRITICAL, 5 HIGH, 14 MEDIUM, 8 LOW)
metadata:
  type: reference
---

## Technical Debt Assessment DRAFT v1.0

**Arquivo:** `docs/prd/technical-debt-DRAFT.md`
**Criado em:** 2026-07-11
**Fases fonte:** Fase 1 (system-architecture.md) + Fase 2 (SCHEMA.md, DB-AUDIT.md)

### Numeros Chave

| Metrica | Valor |
|---------|-------|
| Total debitos | 30 (16 sistema + 14 database) |
| CRITICAL | 3 |
| HIGH | 5 |
| Esforco total | 105-125h |
| Quick wins (<=4h, >=HIGH) | 4 (12-14h) |

### Debitos CRITICAL

- **TD-SYS-001** (4h): Imports quebrados ingestion/ -- impeditivo BidsCrawler
- **TD-DB-01** (8h): Migrations divergentes do schema real -- banco irreproduzivel
- **TD-SYS-009** (16h): Zero testes automatizados em 64K linhas

### Proximos Passos

Pendente revisao dos especialistas (@data-engineer, @qa) conforme workflow Brownfield Fase 5-7.
