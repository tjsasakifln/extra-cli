# Epic: Resolução de Débitos Técnicos — Extra Consultoria

**Versão:** 3.0  
**Data:** 2026-07-17  
**Base:** `docs/prd/technical-debt-assessment.md` v3.0 FINAL (~118 IDs canônicos, ~72–80h Pre-VPS) + `docs/reports/TECHNICAL-DEBT-REPORT.md` v3.0  
**Autor:** Morgan (@pm) — Brownfield Discovery Phase 10  
**Status:** **Active / Ready for story drafting** (wave Pre-VPS Truth)  
**Posição operacional:** `LOCAL_RESILIENCE_READY` · **NÃO** `VPS_OPERATIONAL`

---

## Objetivo

Resolver os débitos técnicos que **ainda bloqueiam** claim de VPS e operação honesta da plataforma B2G Extra Consultoria.

A v2 (Sprints 0–3 / Stories 1.1–1.5) fechou o primeiro pacote P0 de segurança, schema v3, universo, reconciliação e modelo de cobertura. A reassessment v3.0 FINAL (2026-07-17) mostrou que o **eixo dominante residual** é a **Onda de verdade Pre-VPS**: split-brain FS vs PostgreSQL, dual runtime systemd, health mentiroso, schema dual-track, SA JSON residual e honesty de UX/ops.

**Orçamento Pre-VPS (Waves 1–3 + pack UX ops):** ~**72–80h** (mid ~76h · ≈ R$ 11.400 a R$ 150/h).

---

## Status consolidado

| Wave | Escopo | Status |
|------|--------|--------|
| **v2 — Sprints 0–3 / Stories 1.1–1.5** | Segurança base, schema v3, universo, reconciliação, cobertura | **Completed (histórico)** |
| **v3 — Epic Wave Pre-VPS Truth** | Waves 1–3 assessment + pack UX honesty | **Active** — stories 2.1–2.5 em Draft |
| Pós Pre-VPS (Waves 4–7) | Coupling, integrity residual, CLI P1, produto M2, Web UI | **Backlog** — não storyficar agora |

---

## Histórico — Completed (v2 wave)

> **Preservar.** Stories 1.1–1.5 passaram pelo fluxo sm → po → dev → qa → close (2026-07-13).  
> **Não reabrir** como se não tivessem sido executadas. Residual de SEC-02 (arquivo SA JSON ainda presente) é **nova story 2.1**, não regressão de status da 1.1.

### Objetivo v2 (cumprido no escopo das 5 stories)

Resolver débitos críticos iniciais e EPICs P0 do plano mestre de fechamento de gaps (seções 5–9), habilitando base de schema/universo/cobertura.

### Stories v2

| ID | Story | EPIC Mestre | Débitos Brownfield | Prioridade | Status |
|----|-------|-------------|-------------------|------------|--------|
| 1.1 | Fix Critical Security | Pré-requisito P0 — segurança e infra | SEC-01 (parcial), SEC-02 (parcial — residual), SEC-03 (parcial), TD-001 imports, TD-019, TD-021 | P0 | **Done** |
| 1.2 | Unify Schema | P0-02 — Schema de Banco | DT-01…06, DT-18…20, DT-22 (parcial) | P0 | **Done** |
| 1.3 | Universe Authority | P0-03 — Autoridade do Universo | TD-001 (universo), TD-005, TD-034 | P0 | **Done** |
| 1.4 | Reconcile Open Tenders | P0-04 — Reconciliação de Editais | TD-002, TD-006, DT-14 (parcial), DT-21, DT-23 (parcial) | P0 | **Done** |
| 1.5 | Coverage Model | P0-05 — Cobertura por Fonte | TD-003, TD-027, TD-033 | P0 | **Done** |

**Estimativa v2 Stories 1.1–1.5:** ~65h · **Resultado:** ~22 débitos resolvidos/mitigados no audit trail v3.

### Sprints v2 (histórico)

| Sprint | Foco | Stories | Status |
|--------|------|---------|--------|
| Sprint 0 (Semana 1) | Segurança + Quick Wins | 1.1 | **Done** |
| Sprint 1 (Semana 2) | Schema + Universo | 1.2 + 1.3 | **Done** |
| Sprint 2 (Semana 3) | Reconciliação + Cobertura | 1.4 + 1.5 | **Done** |
| Sprint 3 (Semana 4+) | Fontes + Contratos + Concorrentes (P0-06…09) | — | **Não coberto por 1.x** (fora do fechamento das 5 stories) |

### O que a v2 **não** fechou (residual explícito v3)

| Tema | Evidência 2026-07-17 | Destino v3 |
|------|----------------------|------------|
| SA JSON ainda no tree | `config/mides-bigquery-sa.json` presente | Story **2.1** |
| Split-brain FS vs PG | SYS-001 NEW OPEN | Story **2.2** |
| Dual systemd runtimes | SYS-002 NEW OPEN | Story **2.2** |
| Health / checkpoint mentiroso | SYS-003…006 NEW OPEN | Story **2.3** |
| Truth gate VPS | TQ-07 NEW OPEN | Story **2.3** |
| Dual migration track + dump ≠ HEAD | DT-23, DT-24+33 NEW OPEN | Story **2.4** |
| Honesty CLI ops | UX-02/14/17 (+04/21) | Story **2.5** |

---

## Epic Wave Pre-VPS Truth (v3)

### Escopo

**IN — Waves 1–3 do assessment + pack UX ops Pre-VPS:**

| Wave assessment | Foco | Horas | Stories |
|-----------------|------|-------|---------|
| **Wave 1** | Segurança + integridade de schema | ~18h | **2.1**, **2.4** (+ DT-35 embutido) |
| **Wave 2** | Build / testes / observabilidade honesta | ~25h | **2.3** (SYS-003…006 + TQ-07; fatia TQ-02) |
| **Wave 3** | Runtime único (writer PG + uma família systemd) | ~20h | **2.2** |
| **Pack UX ops (∥)** | Progresso, health humano, M1≠M2, tabelas, sumário | ~20h | **2.5** |

**Budget total Pre-VPS:** **~72–80h**.

**OUT (não storyficar nesta wave):**

- SYS-008 elevação M2 (40h+) — **após** truth chain
- TD-010 fatiar `monitor.py` — **após** SYS-001 + TQ-04
- UX-01 Web UI — **DEFERRED** pós-VPS
- P0-06…P0-09 plano mestre (fontes, perfil, contratos, concorrentes) — backlog produto
- Waves 4–7 do assessment (coupling, integrity residual, polish)
- Provisionamento timers oficiais / claim `VPS_OPERATIONAL` (ENV-02) — **bloqueado** até 2.1–2.4 + TQ-07 verdes

### Posição de verdade (não negociável — C6)

```text
LOCAL_RESILIENCE_READY  = READY (mecânica local auditável)
VPS_OPERATIONAL         = PROIBIDO até SYS-001/002 + TQ-07 + SEC-02 + schema truth
M2 cobertura operacional = 0/1093 (0%) — meta 95% é alvo, não claim
M1 sinal comercial       = 116/1093 (10,61%) — ≠ cobertura operacional
```

### Stories novas (2.x) — Pre-VPS only

| ID | Story | Débitos cobertos (agrupados) | Wave | Est. | Risco | Status |
|----|-------|------------------------------|------|------|-------|--------|
| **2.1** | Remover SA JSON residual | SEC-02 / TD-029 (+ DT-35 defaults deploy) | 1 | ~3h | **HIGH-RISK** | Draft |
| **2.2** | Writer único + runtime systemd único | SYS-001 + SYS-002 | 3 | ~20h | **HIGH-RISK** | Draft |
| **2.3** | Health/checkpoint honestos + truth gate | SYS-003…006 + TQ-07 (+ TQ-02 passo 1) | 2 | ~19h | **STANDARD** | Draft |
| **2.4** | Migrations single-track + schema truth | DT-23 + DT-24/33 (+ fatia DT-28/34) | 1 | ~12–14h | **HIGH-RISK** | Draft |
| **2.5** | CLI ops UX honesty Pre-VPS | UX-02, UX-14, UX-17 (+ UX-04, UX-21) | pack ∥ | ~20h | **STANDARD** | Draft |

Arquivos:

- [`story-2.1-remove-sa-json-secret.md`](./story-2.1-remove-sa-json-secret.md)
- [`story-2.2-single-runtime-writer.md`](./story-2.2-single-runtime-writer.md)
- [`story-2.3-honest-health-failclosed.md`](./story-2.3-honest-health-failclosed.md)
- [`story-2.4-migration-single-track.md`](./story-2.4-migration-single-track.md)
- [`story-2.5-cli-ops-ux-pre-vps.md`](./story-2.5-cli-ops-ux-pre-vps.md)

Epic focado (navegação): [`epics/epic-pre-vps-truth.md`](./epics/epic-pre-vps-truth.md)

### Dependências entre stories 2.x

```text
2.1 (secrets)  ──────────────────────────────┐
2.4 (schema truth)  ─────────────────────────┤  Wave 1 (∥ seguro entre si)
                                              ▼
2.3 (health + checkpoint fail-closed)  ──► 2.2 (writer único + systemd)
                                              │
                                              ▼
                                         TQ-07 revalidação (embutido 2.3)
                                              │
2.5 (UX pack) ── paralelo a 2.1/2.4; UX-17 DoD completo após 2.3 ──┘

ENV-02 / timers oficiais / claim VPS  →  SÓ após 2.1 + 2.2 + 2.3 + 2.4 Done com evidência
```

**Ordem de execução recomendada (topológica assessment):**

1. **2.1** + **2.4** (Wave 1 — secrets e schema, paralelizáveis)
2. **2.3** (Wave 2 — honesty health/checkpoint + gate)
3. **2.2** (Wave 3 — single runtime; depende de honesty de checkpoint)
4. **2.5** em paralelo seguro (exceto DoD de UX-17 que referencia health honesto)

### Critérios de sucesso Pre-VPS (binários)

| Critério | Evidência |
|----------|-----------|
| SEC-02 | `test ! -f config/mides-bigquery-sa.json` + pattern no `.gitignore` + CI greps limpos |
| Schema truth | `_migrations` max == HEAD; dump regenerado 043–054+; apply só via `db/setup_db.sh` |
| Health honesty | fixture **nunca** `overall=healthy` com `claim=operational_live` |
| Single writer | path oficial grava evidence/rows em PostgreSQL (desenho B — monitor único writer) |
| Single runtime | uma família systemd oficial; legados disabled/non-prod |
| TQ-07 | gate **FAIL** (não warn) se dual runtime ao autorizar claim VPS |
| Claims | health distingue `LOCAL_RESILIENCE_READY` ≠ `VPS_OPERATIONAL`; M1 ≠ M2 |

### Riscos (v3)

| # | Risco | Sev | Mitigação |
|---|-------|-----|-----------|
| CR-v3-001 | Split-brain FS vs PG + dual systemd | CRITICAL | Story 2.2; freeze timers; TQ-07 |
| CR-v3-002 | Health healthy com fixtures + SLA hardcoded | CRITICAL | Story 2.3 + 2.5 |
| CR-v3-003 | Credenciais compostas (SA JSON + smartlic_local) | CRITICAL | Story 2.1 (HIGH-RISK, **não FAST**) |
| CR-v3-004 | Dump ≠ HEAD + dual track migrations | HIGH | Story 2.4 |
| CR-v3-005 | M1 lido como M2 ou como GO | HIGH | Story 2.5 (UX-14) |
| CR-v3-007 | `LOCAL_RESILIENCE_READY` = VPS / 95% | HIGH | C6 + TQ-07 em 2.3 |
| CR-v3-008 | Waves sem sequenciamento | MEDIUM | Ordem 2.1/2.4 → 2.3 → 2.2 |

---

## Fora de escopo deste epic (backlog pós Pre-VPS)

| Item | Quando |
|------|--------|
| Wave 4 Coupling (TQ-04 residual, TD-010, TD-011) | Após 2.2 Done |
| Wave 5 Integrity residual (DT-26/27/14/22…) | Após writer único |
| Wave 6 residual CLI (UX-03/08/15/19) | Após pack 2.5 |
| SYS-008 elevação M2 40h+ | Após Onda truth |
| UX-01 Web UI | Após VPS claim legítimo + CLI estável |
| P0-06…P0-09 plano mestre produto | Após Pre-VPS |

---

## Referências

| Documento | Papel |
|-----------|-------|
| [`docs/prd/technical-debt-assessment.md`](../prd/technical-debt-assessment.md) | **Fonte definitiva** v3.0 FINAL |
| [`docs/reports/TECHNICAL-DEBT-REPORT.md`](../reports/TECHNICAL-DEBT-REPORT.md) | Relatório executivo Phase 9 |
| [`docs/reviews/qa-review.md`](../reviews/qa-review.md) | Gate QA Phase 7 — APPROVED WITH CONDITIONS |
| [`docs/reviews/db-specialist-review.md`](../reviews/db-specialist-review.md) | Revisão Dara (~46h DB abertas) |
| [`docs/reviews/ux-specialist-review.md`](../reviews/ux-specialist-review.md) | Revisão Uma (~101h UX sem web) |
| [`docs/architecture/system-architecture.md`](../architecture/system-architecture.md) | Arquitetura v3 |
| `plano-mestre-fechamento-gaps-extra-consultoria.md` | Plano mestre histórico (DoD seção 22) |

---

## Change Log

| Data | Versão | Descrição | Autor |
|------|--------|-----------|-------|
| 2026-07-13 | 1.0 | Criação do epic com 5 stories iniciais (P0) + mapeamento dos 9 Epics do plano mestre | Morgan (@pm) |
| 2026-07-13 | 2.0 | Epic completo (5/5 stories done). Stories 1.1–1.5 Done. Próximos: P0-06 a P0-09 | Pax (@po) |
| 2026-07-17 | **3.0** | Brownfield Discovery Phase 10. Histórico 1.1–1.5 preservado como **Completed (v2)**. Nova wave **Pre-VPS Truth**: stories **2.1–2.5** Draft (~72–80h). Status epic → Active. Fonte: assessment + report v3.0 FINAL. | Morgan (@pm) |
