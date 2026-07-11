# EPIC: Expansão de Cobertura & Crawlers — Extra Consultoria

**Epic ID:** EPIC-FEAT-001
**Criado por:** Orion (aiox-master) — consolidação Reversa + Brownfield
**Data:** 2026-07-11
**Status:** Ready for Development
**Fontes:** Handoff 2026-07-10, Reversa `_reversa_sdd/`, Brownfield Assessment

---

## 🎯 Objetivo

Expandir a cobertura de monitoramento de licitações de 1 fonte funcional (PNCP, ~10% cobertura) para 8+ fontes (>90% cobertura dos 2.085 órgãos SC), executar o pipeline de inteligência para o CNPJ da Extra Construtora, e provisionar infraestrutura de produção.

## 📊 Escopo

### Incluído
- Validação de cobertura real do PNCP (crawl amplo, 3 UFs, 30 dias)
- Adaptação de 4 crawlers existentes (DOM-SC, PCP v2, ComprasGov v3, Contracts)
- Criação de 3 novos crawlers (TCE-SC, Portal Transparência, DOE-SC)
- Pipeline de inteligência completo para CNPJ da Extra Construtora
- Provisionamento do Hetzner VPS + systemd timers

### Excluído
- Débitos técnicos (cobertos pelo EPIC-TD-001)
- Interface web/portal (fora do escopo)
- Integração com CRM/ERP
- SC Compras crawler (baixa prioridade, sem source code)

## 🏗️ Fases

| Fase | Nome | Stories | Horas | Descrição |
|------|------|---------|-------|-----------|
| 0 | Validação | 1 story | 2h | Medir cobertura real do PNCP |
| 1 | Adaptação Crawlers | 4 stories | 11-14h | DOM-SC, PCP v2, ComprasGov, Contracts |
| 2 | Novos Crawlers | 3 stories | 13-22h | TCE-SC, Portal Transparência, DOE-SC |
| 3 | Pipeline Intel | 1 story | 2-4h | Executar para CNPJ Extra Construtora |
| 4 | Infraestrutura | 1 story | 4-6h | Provisionar Hetzner VPS |
| **TOTAL** | | **10 stories** | **32-48h** | **R$ 4.800-7.200** |

## 📈 Critérios de Sucesso

- [ ] Cobertura real do PNCP medida e documentada (>X% das 2.085 entidades)
- [ ] DOM-SC crawler funcional (cobre ~600 entidades municipais)
- [ ] PCP v2 crawler funcional (cobre ~100+ municípios)
- [ ] ComprasGov v3 crawler funcional (cobre ~101 entidades federais)
- [ ] TCE-SC crawler funcional (cobre ~96% entidades SC de uma vez)
- [ ] Portal Transparência com detecção de plataforma (Betha/Ipam/E-gov)
- [ ] DOE-SC crawler funcional (513 entidades estaduais)
- [ ] Relatório de inteligência gerado para CNPJ Extra Construtora
- [ ] Hetzner VPS provisionado com 13 systemd timers ativos

## 🔗 Dependências

- **EPIC-TD-001** (Technical Debt): Fase 0 (backup) deve ser concluída antes de provisionar VPS
- **Assessment:** `docs/prd/technical-debt-assessment.md`
- **Specs Reversa:** `_reversa_sdd/crawl/requirements.md`, `_reversa_sdd/crawl/tasks.md`
- **Handoff:** `.aiox/handoffs/NEXT-SESSION.md`
- **Database:** PostgreSQL local (porta 5433), schema `pncp_datalake`

## 📋 Story List

| ID | Story | Fase | Horas | Prioridade |
|----|-------|------|-------|------------|
| FEAT-0.1 | Validar cobertura real do PNCP | 0 | 2h | P1 |
| FEAT-1.1 | Adaptar DOM-SC crawler | 1 | 3-4h | P1 |
| FEAT-1.2 | Adaptar PCP v2 crawler | 1 | 2-3h | P2 |
| FEAT-1.3 | Adaptar ComprasGov v3 crawler | 1 | 2-3h | P2 |
| FEAT-1.4 | Adaptar Contracts crawler | 1 | 2h | P3 |
| FEAT-2.1 | Criar TCE-SC crawler | 2 | 4-8h | P1 |
| FEAT-2.2 | Criar Portal Transparência crawler | 2 | 6-10h | P2 |
| FEAT-2.3 | Criar DOE-SC crawler | 2 | 3-4h | P2 |
| FEAT-3.1 | Pipeline Intel CNPJ Extra Construtora | 3 | 2-4h | P1 |
| FEAT-4.1 | Provisionar Hetzner VPS | 4 | 4-6h | P1 |

## 🚀 Ordem de Execução Recomendada

```
FEAT-0.1 (validação) → FEAT-1.1 (DOM-SC) → FEAT-2.1 (TCE-SC)
                    → FEAT-1.2 (PCP)      → FEAT-2.3 (DOE-SC)
                    → FEAT-1.3 (ComprasGov) → FEAT-2.2 (Transparência)
                    → FEAT-1.4 (Contracts)
FEAT-3.1 (pipeline intel) — paralelo, depende só do DB populado
FEAT-4.1 (VPS) — após FEAT-0.1 confirmar viabilidade, paralelo aos crawlers
```

**Dependência externa:** EPIC-TD-001 Fase 0 (backup + imports) antes de FEAT-4.1 (VPS).

---

## 📎 Anexos

- [Handoff 2026-07-10](../../../.aiox/handoffs/NEXT-SESSION.md) — Estado atual, crawlers pendentes
- [Reversa Crawl Specs](../../../_reversa_sdd/crawl/requirements.md) — 13 FRs, 6 NFRs
- [Reversa Crawl Tasks](../../../_reversa_sdd/crawl/tasks.md) — 10 tarefas detalhadas
- [Brownfield Assessment](../../prd/technical-debt-assessment.md) — 38 débitos
- [Database Schema](../../../supabase/docs/SCHEMA.md) — Schema atual
