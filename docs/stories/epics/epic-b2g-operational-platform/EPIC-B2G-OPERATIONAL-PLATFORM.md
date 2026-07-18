# EPIC-B2G-OPERATIONAL-PLATFORM

| Campo | Valor |
|-------|-------|
| **Epic ID** | EPIC-B2G-OPERATIONAL-PLATFORM |
| **Versão** | 1.0 |
| **Data** | 2026-07-17 |
| **Status** | Active |
| **Branch** | `epic/b2g-operational-platform-2026-07-17` |
| **Autor** | Morgan (PM) |
| **PRD** | `docs/prd/PRD-consultoria-extra.md` + `docs/prd/PRD-b2g-operational-platform-delta.md` |
| **Matriz** | `docs/prd/capability-matrix-b2g-proposta.md` |
| **Arquitetura** | `docs/architecture/b2g-operational-target-architecture.md` |
| **Diagnóstico** | `docs/architecture/adversarial-diagnosis-b2g-2026-07-17.md` |
| **ADRs** | ADR-017 … ADR-022 |

---

## 1. Objetivo

Tornar a plataforma **operacionalmente confiável** para a proposta comercial B2G (universo **1.093** órgãos / 200 km): cobertura operacional mensurável (meta **95%** em M2), rotina diária do consultor via **workspace**, e capacidades verticais (oportunidades, histórico, concorrentes, preços, etc.) sobre base com **prova** — sem confundir **sinal comercial 116/1093** com cobertura 95%.

---

## 2. Baseline honesto

| Métrica | Valor |
|---------|-------|
| `entities_with_recent_commercial_signal` | **116 / 1093 (10,61%)** — 2026-07-17 |
| `operational_source_coverage` | **não canônico** (meta 95%) |
| Histórico 3y | **NO-GO** |
| Scheduler permanente | **não provado** |
| Workspace facade | **não existe** |
| ESR por entidade | **não canônico** |

---

## 3. Princípios do epic

1. **Verticais por valor comercial**, não “foundation genérica” monolítica.
2. **E1–E3 desbloqueiam prova**; E4 torna usável; E5+ entregam inteligência.
3. **Dual-metric** em todo DoD de coverage (ADR-018).
4. **Fail-closed** (ADR-021); **dados operacionais fora do git** (ADR-020).
5. **Client profile = lei** (ADR-022).

---

## 4. Epics verticais (ordem de prioridade)

| ID | Nome | Valor | ADRs | Stories detalhadas |
|----|------|-------|------|--------------------|
| **E1** | Operational coverage 95% | Contrato multi-métrica; caminho para M2≥95% | 018 | **Sim** (abaixo) |
| **E2** | Source registry & discovery | ESR 1093 + discovery PNCP/CIGA | 019 | **Sim** |
| **E3** | Resilient scheduled collection | Scheduler, adapters, 429, raw policy | 020, 021 | **Sim** |
| **E4** | Daily workspace | Facade CLI consultor | 017 | **Sim** |
| **E5** | Opportunities & triage | Lista, score, explain, profile | 022 | **Sim** |
| **E6** | Org history & ranking | Histórico 3y + ranking órgãos | — | Backlog (outline) |
| **E7** | Competitors & winners | Mapa vencedores honesto | — | Backlog |
| **E8** | Expiring contracts | Radar vigência / re-bidding | — | Backlog |
| **E9** | Price intelligence | Preços com N e quantis | ADR-002 | Backlog |
| **E10** | Edital analysis | Anexos / checklist técnico | — | Backlog |
| **E11** | Proposal support | Pacote apoio proposta | — | Backlog |
| **E12** | Admin contract monitoring | Watchlist atos/contratos | — | Backlog |
| **E13** | Weekly/monthly reports | Relatórios cliente | — | Backlog |

---

## 5. Stories — primeiros 5 epics

### E1 — Operational coverage 95%

| Story | Título | Status |
|-------|--------|--------|
| **B2G-E1.S1** | Coverage contract multi-metric (M1–M5) + rename commercial signal | **InProgress** |
| B2G-E1.S2 | Calculadora M2 operational_source_coverage + identity tests | Draft |
| B2G-E1.S3 | Recall benchmark sample (gold set) + relatório gaps | Draft |
| B2G-E1.S4 | Coverage gate no CI/workspace (ban single-metric headline) | Draft |

### E2 — Source registry & discovery

| Story | Título | Status |
|-------|--------|--------|
| **B2G-E2.S1** | Entity source registry canônico — 1093 bindings | **InProgress** |
| **B2G-E2.S2** | Source discovery + aquisição PNCP/CIGA → ESR | **InProgress** |
| B2G-E2.S3 | Portal/unknown resolution queue + confidence | Draft |
| B2G-E2.S4 | ESR export + integração M2 | Draft |

### E3 — Resilient scheduled collection

| Story | Título | Status |
|-------|--------|--------|
| B2G-E3.S1 | Adapter contract + PNCP 429 fail-closed | **Done** (QA CONCERNS accepted @po 2026-07-17; no READY seals) |
| B2G-E3.S2 | Checkpoint/resume unificado + DLQ smoke | **Done** (QA CONCERNS accepted @po 2026-07-17; no READY seals) |
| B2G-E3.S3 | Scheduler permanente + prova journalctl/last_success | Draft |
| B2G-E3.S4 | Operational data paths + gitignore policy (ADR-020) | Draft |

### E4 — Daily workspace

| Story | Título | Status |
|-------|--------|--------|
| **B2G-E4.S1** | Workspace CLI: today / opportunities / coverage | **InProgress** |
| B2G-E4.S2 | Freshness hard-gate + exit codes | Draft |
| B2G-E4.S3 | Runbook rotina &lt;15 min + testes CLI | Draft |

### E5 — Opportunities & triage

| Story | Título | Status |
|-------|--------|--------|
| B2G-E5.S1 | Client profile v1 como lei de ranking | Draft |
| B2G-E5.S2 | Triage GO/NO-GO/WATCH + explain profile-bound | Draft |
| B2G-E5.S3 | Human feedback store + override na lista | Draft |

Arquivos: `story-B2G-E{n}.S{m}.md` neste diretório.

---

## 6. Outline E6–E13 (sem story files ainda)

| Epic | Outcome | Deps | Riscos |
|------|---------|------|--------|
| E6 | Histórico 36m por órgão com flag de incompletude; go_no_go_3y path | E2, E3 | Rate limit; volume |
| E7 | Top vencedores + limitações honestas (sem win-rate falso) | E6 | Só vencedores públicos |
| E8 | Lista contratos a vencer 90/180d + heurística re-bid | E6 | Vigência missing |
| E9 | P25/P50/P75 ou NOT_READY explícito | E6, itens | Capability prices vazia |
| E10 | Ficha técnica edital (anexos + checklist) | E5 | PDF/OCR |
| E11 | `proposal-pack` one-shot | E5–E10 | Dados vazios em PDF |
| E12 | Watchlist atos ↔ contratos | E3, official_acts | False positive match |
| E13 | Relatório semanal/mensal carimbado | E4, E1 | Stale attestation |

---

## 7. Dependências entre E1–E5

```
E1.S1 (contract) ─────────────────────────────┐
     │                                         │
E2.S1 (ESR 1093) ──► E2.S2 (discovery) ──► E1.S2 (M2 calc)
     │                                         │
     └──────────────► E3.* (collection) ───────┤
                                               ▼
                                    E4.S1 workspace
                                               │
                                    E5.* triage/profile
```

---

## 8. Gates de programa

### Gate OP-A — Truth

- [ ] ADR-018 implementado (M1 rename + dual headline)
- [ ] List identity tests verdes
- [ ] Baseline 116/1093 reproduzível ou explicitamente supersedido com mesmo contrato

### Gate OP-B — Registry

- [ ] 1093 entidades no ESR
- [ ] Discovery PNCP/CIGA gravando bindings com evidence_ref

### Gate OP-C — Operate

- [ ] Scheduler com prova de last_success
- [ ] 429 fail-closed testado
- [ ] `workspace today` usável (&lt;15 min runbook)

### Gate OP-D — Commercial path

- [ ] Profile v1 + explain
- [ ] M2 medido (mesmo que &lt;95%) com plano de gaps

---

## 9. Riscos do programa

| Risco | Mitigação |
|-------|-----------|
| Overselling 95% | Dual-metric + PRD delta |
| Paralelo com EPIC-MASTER sem foco | Este epic é prioridade vertical comercial |
| Escopo obra física | OUT no PRD delta |
| Execução manual continua | E3+E4 DoD com prova |

---

## 10. Definition of Done (epic-level E1–E5)

- Stories E1–E5 com AC Given/When/Then atendidos ou explicitamente waived pelo PO
- ADRs 017–022 referenciados no código/docs tocados
- Nenhuma métrica comercial single-headline em outputs novos
- Inventário de gaps M2 priorizado para waves seguintes

---

## 11. Changelog

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-07-17 | Morgan (PM) | Criação do epic vertical + stories E1–E5 |
