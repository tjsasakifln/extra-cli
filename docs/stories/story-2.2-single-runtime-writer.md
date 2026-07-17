# Story 2.2: Writer único PostgreSQL e runtime systemd único

**Epic:** Resolução de Débitos Técnicos v3 / Pre-VPS Truth  
**EPIC focado:** Pre-VPS Truth — Wave 3 (Architecture frontiers: single runtime)  
**Status:** Draft  
**Prioridade:** P0 — Pre-VPS blocker  
**Risk level:** **HIGH-RISK**  
**Estimativa:** ~**20h** (SYS-001 12h + SYS-002 8h)  
**Executor planejado:** @dev (+ @architect se desvio do desenho B)  
**Quality Gate:** @qa  
**Autor draft:** Morgan (@pm) — 2026-07-17

---

## Story

As a **operador da plataforma B2G Extra Consultoria**,  
I want **um único caminho oficial de escrita no PostgreSQL e uma única família de units systemd em produção**,  
so that **deixe de existir split-brain (FS vs banco) e timers oficiais competindo entre si, e a consultoria confie em uma única verdade de dados**.

---

## Problem / Value

### Problema

- **SYS-001:** `resilient_cycle` (e path “oficial” de resiliência) grava evidência em **filesystem**, não no PostgreSQL → split-brain.  
- **SYS-002:** duas famílias de timers/units (`extra-crawl-*` FS-oriented vs `pncp-crawl-*` / monitor DB-oriented) competem.  
- Coleta pode parecer “verde” no disco e vazia no banco (ou o inverso) → decisões de consultoria em evidência errada (**CR-v3-001**).  
- **C6:** claim `VPS_OPERATIONAL` e timers oficiais **proibidos** enquanto SYS-001/002 abertos.

### Valor

- Pré-condição para qualquer operação VPS honesta.  
- Desbloqueia elevação M2 (SYS-008) e fatiamento de monitor (TD-010) **depois**.  
- Elimina a principal fonte de “parece que funciona”.

### Root cause

1. Evolução paralela: stack de resiliência FS-first vs pipeline monitor/DB-first.  
2. Units systemd legadas nunca foram desativadas formalmente.  
3. Preferência arquitetural (Dara/Aria): **(B) monitor único writer** — resilient deve produzir `FetchResult` e o monitor grava PG; dual-write (C) só transitório ≤1 sprint com kill-switch.

---

## Scope

### IN

- Implementar desenho **(B) monitor único writer** (default assessment):  
  - path oficial de crawl/resilience **não** é fonte de verdade de persistência em FS  
  - evidence/rows esperados no PostgreSQL no happy path  
  - 0 “success” de pipeline sem row/evidence esperada  
- Unificar runtime systemd: **uma** família “oficial”; legados `disabled` / non-prod / documentados  
- Health/report deve refletir qual runtime está ativo (sem mentir claim VPS)  
- Ajustar entrypoints/docs de ops para o path único  
- Testes de regressão: happy path grava PG; path FS-only não marca success operacional

### OUT

- Fatiar monólito `monitor.py` (TD-010) — **após** esta story + TQ-04  
- Unificar dual client PNCP (TD-011 / TD-001 reframe) — pós 2.2  
- Elevação M2 (SYS-008)  
- Enable de timers oficiais em VPS de produção (ENV-02) — **só após** esta story + TQ-07  
- Dual-write permanente (opção C) como arquitetura final  
- Mudanças de schema de negócio não relacionadas ao writer

---

## Debt IDs covered

| ID | Descrição | Sev | Horas | Status assessment |
|----|-----------|-----|-------|-------------------|
| **SYS-001** | Split-brain: resilient grava FS, não PG | CRITICAL P0 | 12h | NEW OPEN |
| **SYS-002** | Dual systemd runtimes | CRITICAL P0 | 8h | NEW OPEN |
| **ENV-02** (pré-condição) | Dual units no repo / VPS | HIGH | 0 nesta story* | OPEN — **não** habilitar timers |

\* ENV-02 provisionamento completo fica bloqueado; esta story **remove a dualidade** como pré-requisito.

---

## Acceptance Criteria

### AC-1 — Writer único no path oficial

**Given** o path oficial de coleta (resilient → orquestrador → monitor)  
**When** um ciclo happy-path completa com sucesso  
**Then** existem rows/evidence esperados no **PostgreSQL** e o success de pipeline **não** depende apenas de artefato FS

### AC-2 — Zero success sem persistência

**Given** falha de escrita no PostgreSQL (ou writer desabilitado em teste)  
**When** o ciclo tenta completar  
**Then** o resultado **não** é reportado como success operacional / checkpoint de pipeline sucesso

### AC-3 — Desenho B documentado

**Given** a implementação  
**When** revisamos ADRs/notas de dev  
**Then** está explícito: monitor = writer único; adapters **não** marcam success de pipeline (alinhado SYS-006 da story 2.3)

### AC-4 — Uma família systemd oficial

**Given** units no repositório e docs de deploy  
**When** listamos timers/services “produção”  
**Then** existe **uma** família oficial nomeada; unidades legadas estão disabled, mascaradas ou explicitamente non-prod

### AC-5 — Health reporta runtime

**Given** o health check operacional  
**When** consultamos o status  
**Then** o payload indica runtime/família ativa e **não** emite `claim=VPS_OPERATIONAL` se dual runtime ou writer FS-only ainda existirem (integra TQ-07)

### AC-6 — Legados não competem

**Given** um ambiente de staging com units instaladas  
**When** o path oficial roda  
**Then** nenhuma unit legada sobrescreve o mesmo destino de dados sem kill-switch documentado

---

## Tests required

| Tipo | O quê |
|------|-------|
| Integração | Happy path: resilient/monitor grava evidence no PG (test DB) |
| Negativo | PG down / write fail → não success operacional |
| Unit | Contratos de FetchResult / writer boundary |
| Ops / smoke | `systemctl list-timers` (ou inventário no repo) mostra uma família oficial |
| Regressão | TQ-07 (story 2.3) revalida FAIL se dual runtime reaparecer |
| Manual | Checklist adversarial F1–F7 subset CRITICAL (SYS-001/002) |

---

## Files likely affected

| Path | Motivo |
|------|--------|
| `scripts/crawl/monitor.py` | Writer único / orquestração |
| Paths `resilient*` / cycle resilience | Deixar de ser source of truth FS |
| `scripts/ops/health.py` (ou equivalente) | Reportar runtime |
| `deploy/` / `systemd/` / units `extra-crawl-*`, `pncp-crawl-*` | Unificar família |
| Docs ops / ADRs | Desenho B |
| Testes em `tests/` relacionados a crawl/monitor/resilience | Cobertura |

---

## Dependencies

| Depende de | Relação |
|------------|---------|
| **2.3** (preferível / quase obrigatório) | SYS-005/006 + health honesty antes de unificar writer — truth chain: checkpoint → health → writer |
| **2.1** | Recomendado secrets limpos antes de ops sensível |
| **2.4** | Recomendado schema truth estável para evidence rows |

| Desbloqueia | Relação |
|-------------|---------|
| TQ-07 verde real | Gate só passa com writer único |
| ENV-02 timers oficiais | C6 |
| TD-010, TD-011, SYS-008 | Pós single runtime |

**Não iniciar 2.2 em paralelo cego com 2.3** se checkpoint ainda engole erro (SYS-005) ou adapter marca success (SYS-006).

---

## Definition of Done

- [ ] ACs 1–6 com evidência (logs, queries, listagem de units)  
- [ ] Desenho B implementado ou desvio aprovado por @architect com ADR  
- [ ] Units legadas non-prod documentadas  
- [ ] Testes de integração/negativo passam  
- [ ] Nenhum claim VPS no health sem gate  
- [ ] File List e checkboxes atualizados no ciclo dev  
- [ ] QA veredito + PO close  
- [ ] Follow-up: recomendar re-extração Reversa (crawl/resilience/ops) — **não** automática  

---

## Rollback notes

| Cenário | Ação |
|---------|------|
| Writer único quebra coleta em produção local | Kill-switch documentado: feature flag dual-write **≤1 sprint** (opção C) com métrica; **não** reabilitar dual runtime permanente |
| Unit oficial falha | Reverter unit package; manter legados disabled até fix |
| Dados só em FS de ciclos antigos | Script de import one-shot (se necessário) — fora do happy path contínuo |

---

## Risks

| Risco | Mitigação |
|-------|-----------|
| CR-v3-001 split-brain | Esta story é a mitigação principal |
| Refator ampla sem testes | Depender de 2.3 + testes integração; não misturar TD-010 |
| Opção C virar permanente | Kill-switch + prazo ≤1 sprint no DoD se usada |
| Quebra de timers legados em uso manual | Docs + disable explícito; comunicação ops |

---

## Referências

- Assessment §1.1 SYS-001/002; Wave 3; preferência Dara (B)  
- CR-v3-001, C6  
- Parent: `epic-technical-debt.md` v3.0 · `epic-pre-vps-truth.md`  

---

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (@pm) | Draft criado — Brownfield Phase 10 |
