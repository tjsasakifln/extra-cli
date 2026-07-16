# GATE-1 — LOCAL_FOUNDATION

**Campanha:** EPIC-PLANO-EXECUTIVO-30D  
**Data:** 2026-07-16  
**Status:** **PARTIAL** (não declarar LOCKED total)

## Scorecard L1

| Task | Status | Evidência |
|------|--------|-----------|
| L1.1 pré-requisitos | PARTIAL | `docs/baseline/l1-env-prereqs.md` — python3/docker OK; `python` bare missing |
| L1.2 universo 1093 | PARTIAL | planilha 1093 OK; `target_universe_entities` = 0 no DB |
| L1.3 fresh migrations | **BLOCKED/PARTIAL** | vector fix em compose; mig 049 quebra em fresh (view) — `l1-fresh-migrations.md` |
| L1.4 registry capability | PARTIAL | registry por fonte OK; matriz ente×fonte×capability unknown |
| L1.5 golden path | PARTIAL | PCP+ComprasGov OK; PNCP timeout; ledger bug **corrigido** |
| L1.6 resume/DLQ | PARTIAL | testes majoritários pass |
| L1.7 backup/restore | OPEN | script existe; drill não executado |
| L1.8 este manifesto | DONE (parcial) | este arquivo |

## Pode afirmar

- Ambiente local com Docker Postgres sobe.
- Universo canônico da planilha: **1093** no raio (hash registrado).
- Golden path parcial com fontes essenciais.
- DLQ/watermark implementados (DATA-FOUNDATION).

## Não pode afirmar

- Fresh install 54/54 migrations green.
- Cobertura ≥95% editais ou contratos.
- GATE-1 **LOCKED** sem restore drill + migrations clean.

## Follow-ups (dia 31+)

1. Corrigir migration 049 (DROP VIEW / ordem) para fresh install.
2. Materializar universo no DB.
3. Restore drill documentado.
4. Reexecutar golden path completo com reports.
