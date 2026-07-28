# Gaps — Reversa 2026-07-28

> Escopo almejado = **`DOD.md`**. Gaps cruzam as-is com metas do DOD (`target-scope-dod.md`).  
> Fechar gap de produto = item/gate DoD com **evidência**, não só documentação Reversa.

| ID | Gap | Severidade | Owner sugerido | vs 07-17 |
|----|-----|------------|----------------|----------|
| G01 | Coverage operacional M2 / 95% DOD §4 — não re-medido live nesta sessão | 🔴 | product + crawl + ESR | mantém |
| G02 | DB live / row counts / VPS health não auditados nesta sessão | 🔴 | data-engineer / ops | mantém |
| G03 | Specs SDD unit folders incompletas para 13 módulos novos | 🟠 | writer próximo ciclo | **novo peso** |
| G04 | W006: unificar `docker-compose.local.yml` test-db com oficial (`pgvector/pgvector:pg16` + volume; vector obrigatório) | 🟢 | devops | **fechado 2026-07-27** — decisão owner: unificar (não aceitar divergência); local = oficial; evidência nos compose do root |
| G05 | C4 context/containers/components não regenerados linha-a-linha | 🟡 | architect | novo |
| G06 | opportunity_intel internals (radar 12 etapas / reconciliation event_type) parciais | 🟡 | opportunity_intel | W001/W004 amarelos |
| G07 | Satélites ocds_bridge / data_contracts / quality só inventário | 🟡 | dev | novo |
| G08 | pip lockfile ausente | 🟡 | devops | mantém |
| G09 | Multi-consultor RBAC inexistente (by design single-tenant) | 🟢 | futuro | mantém |
| G10 | Claim risk: national_intel / commercial scores mal rotulados em materiais externos | 🟠 | product / reports | novo |
| G11 | ERD visual completo não regenerado (dicionário textual sim) | 🟡 | data-engineer | novo |
| G12 | Worktrees `.worktrees/*` no filesystem — risco de confusão com main | 🟡 | devops | novo |

---

## Gaps fechados / melhorados desde 2026-07-17

| Item | Notas |
|------|-------|
| G04 / W006 compose local vs oficial | 🔴→🟢 decisão unificar (local=oficial, vector obrig., persistência PC irrelevante); `docker-compose.local.yml` test-db alinhado a `pgvector/pgvector:pg16` + volume `pgdata` |
| ORPT reports superfície | 🟡→🟢 vertical real PDF/Excel + fail-closed lists |
| Dual capability documented | 🟢 mig 058 + código |
| Commercial leads inexistente | ✨ agora 🟢 código+schema |
| Linkage / national intel | ✨ 🟢 |
| ADRs campanha | +8 ADRs 023–030 |
| ops explosion mapeada | 🟢 clusters |
