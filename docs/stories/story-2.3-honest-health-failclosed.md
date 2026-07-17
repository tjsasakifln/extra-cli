# Story 2.3: Health e checkpoint honestos + truth gate fail-closed

**Epic:** Resolução de Débitos Técnicos v3 / Pre-VPS Truth  
**EPIC focado:** Pre-VPS Truth — Wave 2 (Build / Tests / Observability)  
**Status:** Draft  
**Prioridade:** P0 — Pre-VPS blocker  
**Risk level:** **STANDARD**  
**Estimativa:** ~**19h** (SYS-005/006 6h + SYS-003/004 7h + TQ-07 4h + TQ-02 passo 1 2h)  
**Executor planejado:** @dev  
**Quality Gate:** @qa  
**Autor draft:** Morgan (@pm) — 2026-07-17

---

## Story

As a **operador e gestor da plataforma Extra Consultoria**,  
I want **que health, checkpoints e o gate pré-VPS falhem de forma fechada quando a verdade operacional não existe**,  
so that **ninguém confie em “verde falso”, fixture pintada como live, SLA inventado ou claim VPS com dual runtime**.

---

## Problem / Value

### Problema

| ID | Sintoma |
|----|---------|
| **SYS-005** | Checkpoint schema engolido (`TypeError: pass`) — erro silencioso |
| **SYS-006** | Adapter CIGA salva checkpoint **success** indevidamente |
| **SYS-003** | Health “healthy” após fixtures (falso verde) |
| **SYS-004** | Freshness SLA hardcoded ≠ registry (ex. PNCP 24h vs 4h) |
| **TQ-07** | Truth gate **não** bloqueia claim VPS (warn em vez de FAIL) |
| **TQ-02** | Coverage threshold 10% frouxo (passo 1 pré-VPS → 30%) |

- **CR-v3-002 / CR-v3-007:** operador e gestão confiam em status falso; `LOCAL_RESILIENCE_READY` confundido com VPS/95%.  
- Aliases: OBS-01→SYS-003, OBS-02→SYS-004 (não double-count).

### Valor

- Truth chain assessment: **SYS-005/006 → SYS-003/004 → (depois) SYS-001/002**.  
- Impede declaração falsa de produção.  
- Base para UX-17 (`--human`) na story 2.5 sem pintar verde mentiroso.

### Root cause

1. Checkpoints sem tipagem/validação fail-closed.  
2. Adapters assumindo responsabilidade de “success de pipeline”.  
3. Health sem flags `mode` / `environment` / `fixture` / `claim`.  
4. Thresholds de freshness hardcoded em vez de `coverage_slas.yaml` / registry.  
5. Gate pré-VPS adverso só documentado, não enforced.

---

## Scope

### IN

- **SYS-005:** schema de checkpoint tipado; inválido → erro (fail-closed), sem `pass` silencioso  
- **SYS-006:** adapter CIGA (e padrão) **não** marca success de pipeline; só orquestrador/writer  
- **SYS-003:** fixture **nunca** produz `overall=healthy` com `claim=operational_live`; flags mode/env/fixture  
- **SYS-004:** thresholds de freshness do registry / `coverage_slas.yaml`; hardcoded removido ou fail-closed se divergir  
- **TQ-07:** gate pré-VPS **FAIL** (exit ≠ 0) se SYS-001/002 abertos ao autorizar timers/claim VPS; `ALLOW_PRE_VPS_WARN=1` **somente** dev explícito  
- **TQ-02 (passo 1):** elevar coverage progressivo para **≥30%** no denominador `scripts/` crítico (omit list documentada para monólitos legados)  
- Subset checklist adversarial F1–F7 CRITICAL (SYS-001…006) como **gate de release**, não só doc  

### OUT

- Implementar SYS-001/002 (story **2.2**)  
- OBS métricas P50/P95 completas (TD-032 residual amplo)  
- TQ-04 suite integração crawlers completa (pré TD-010)  
- Coverage 45%/60% (passos futuros de TQ-02)  
- UX-17 UI humana (story **2.5**) — mas health JSON deve já ser honesto  
- Web UI  

---

## Debt IDs covered

| ID | Descrição | Sev | Horas | Status |
|----|-----------|-----|-------|--------|
| **SYS-005** | Checkpoint schema engolido | CRITICAL P0 | 3h | NEW OPEN |
| **SYS-006** | CIGA success no adapter | CRITICAL P0 | 3h | NEW OPEN |
| **SYS-003** / OBS-01 | Health healthy com fixtures | CRITICAL P0 | 4h | NEW OPEN |
| **SYS-004** / OBS-02 | SLA hardcoded ≠ registry | CRITICAL P0 | 3h | NEW OPEN |
| **TQ-07** | Truth gate não bloqueia VPS | HIGH P0 | 4h | NEW OPEN |
| **TQ-02** | Coverage 10% frouxo (passo 1→30%) | MEDIUM P0 pré-VPS | 2h | OPEN |
| **TD-015** | Healthcheck unificado | PARTIAL | 0 residual* | honesty = SYS-003/004 |

---

## Acceptance Criteria

### AC-1 — Checkpoint fail-closed (SYS-005)

**Given** um checkpoint com schema inválido ou tipo errado  
**When** o código de checkpoint processa o payload  
**Then** lança erro / exit fail-closed e **não** engole com `pass` silencioso

### AC-2 — Adapter sem success de pipeline (SYS-006)

**Given** o adapter CIGA (e contratos de adapter)  
**When** um fetch parcial ou completo ocorre no adapter  
**Then** **não** persiste checkpoint de **success de pipeline**; apenas o orquestrador/writer pode marcar sucesso de pipeline

### AC-3 — Fixture ≠ live healthy (SYS-003)

**Given** health rodando em modo fixture / non-live  
**When** overall status é calculado  
**Then** **nunca** retorna healthy operacional live (`claim=operational_live` / equivalente) sem flags explícitas de fixture/mode; claim VPS permanece proibido

### AC-4 — SLA do registry (SYS-004)

**Given** fonte PNCP (e outras no registry)  
**When** freshness é avaliada  
**Then** o threshold vem do registry / `coverage_slas.yaml` (ex. PNCP alinhado ao valor canônico, não hardcoded divergente)

### AC-5 — TQ-07 FAIL (não warn)

**Given** SYS-001 e/ou SYS-002 ainda abertos **e** tentativa de autorizar claim VPS / timers oficiais  
**When** o truth gate roda **sem** `ALLOW_PRE_VPS_WARN=1`  
**Then** o gate **FAIL** (exit ≠ 0); com a env de dev explícita, comportamento de warn documentado

### AC-6 — Claims separados

**Given** payload de health  
**When** inspecionamos campos de claim  
**Then** `LOCAL_RESILIENCE_READY` e `VPS_OPERATIONAL` são **distintos**; resiliência local **não** implica VPS nem cobertura 95%

### AC-7 — Coverage passo 1 (TQ-02)

**Given** CI de coverage  
**When** o threshold é aplicado  
**Then** o piso documentado é **≥30%** no denominador crítico (omit list de monólitos legados versionada)

---

## Tests required

| Tipo | O quê |
|------|-------|
| Unit | Checkpoint inválido → exception |
| Unit / contract | Adapter CIGA não grava success pipeline |
| Unit / integration | Health fixture mode flags; nunca operational_live healthy indevido |
| Unit | Freshness lê registry/SLA yaml |
| Integration / script | TQ-07 FAIL quando dual-runtime flags simulados |
| CI | Coverage threshold 30% (passo 1) |
| Adversarial | Subset F1–F7 CRITICAL checklist |

---

## Files likely affected

| Path | Motivo |
|------|--------|
| Checkpoint modules (crawl/resilience) | SYS-005 |
| Adapter CIGA | SYS-006 |
| `scripts/ops/health.py` (ou equivalente) | SYS-003/004, claims |
| `coverage_slas.yaml` / source registry | SYS-004 |
| Gate scripts / CI pré-VPS | TQ-07 |
| `pytest` / CI coverage config | TQ-02 |
| `PRE-VPS-FINAL-ADVERSARIAL-AUDIT.md` (se existir) | Gate link |

---

## Dependencies

| Depende de | Relação |
|------------|---------|
| **2.1** | Recomendado (secrets) antes de endurecer ops |
| **2.4** | Útil se diagnostics/schema forem usados no health |

| Desbloqueia | Relação |
|-------------|---------|
| **2.2** | Truth chain: honesty antes de writer único |
| **2.5** UX-17 | Human health sem verde falso |
| ENV-02 / claim VPS | TQ-07 + 2.2 |

**Ordem interna obrigatória desta story:** SYS-005/006 → SYS-003/004 → TQ-07 (TQ-02 pode paralelizar no final).

---

## Definition of Done

- [ ] ACs 1–7 com evidência  
- [ ] Nenhum `pass` silencioso em checkpoint schema path  
- [ ] Adapters sem success de pipeline  
- [ ] Health com flags mode/env/fixture/claim honestos  
- [ ] TQ-07 fail-closed documentado e testado  
- [ ] Coverage ≥30% no denominador acordado  
- [ ] Testes novos/atualizados verdes  
- [ ] QA + PO close  
- [ ] **Não** declarar SYS-001/002 resolvidos nesta story  

---

## Rollback notes

| Cenário | Ação |
|---------|------|
| Gate TQ-07 quebra CI de feature branches | Usar `ALLOW_PRE_VPS_WARN=1` **só** em dev documentado; não enfraquecer default |
| Health “mais vermelho” quebra dashboards | Atualizar consumidores para ler `claim`/`mode`; não reintroduzir healthy mentiroso |
| Checkpoint fail-closed interrompe crawl legado | Corrigir produtores de schema; não reengolir TypeError |

---

## Risks

| Risco | Mitigação |
|-------|-----------|
| CR-v3-002 health mentiroso | ACs 3–4 + testes fixture |
| CR-v3-007 confusão de claims | AC-6 |
| TQ-07 só warn “por enquanto” | AC-5 binário FAIL |
| Scope creep para SYS-001/002 | OUT explícito → story 2.2 |

---

## Referências

- Assessment Wave 2; §1.1 SYS-003…006; §5 TQ-02/07  
- Q2/Q5 respostas QA no assessment  
- Parent epics v3  

---

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (@pm) | Draft criado — Brownfield Phase 10 |
