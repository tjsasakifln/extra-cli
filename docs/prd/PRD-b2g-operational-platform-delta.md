# PRD Delta — B2G Operational Platform

| Campo | Valor |
|-------|-------|
| **Versão** | 1.0 |
| **Data** | 2026-07-17 |
| **Tipo** | Delta / addendum ao PRD completo |
| **PRD completo** | [`docs/prd/PRD-consultoria-extra.md`](./PRD-consultoria-extra.md) v2.0 |
| **Matriz de capacidades** | [`docs/prd/capability-matrix-b2g-proposta.md`](./capability-matrix-b2g-proposta.md) |
| **Epic** | [`docs/stories/epics/epic-b2g-operational-platform/EPIC-B2G-OPERATIONAL-PLATFORM.md`](../stories/epics/epic-b2g-operational-platform/EPIC-B2G-OPERATIONAL-PLATFORM.md) |
| **Arquitetura-alvo** | [`docs/architecture/b2g-operational-target-architecture.md`](../architecture/b2g-operational-target-architecture.md) |

---

## 1. Por que este delta

O PRD v2.0 permanece a visão de produto. Este delta **corrige linguagem de métricas**, **fixa UX primária**, **congela escopo negativo** e **ancora o baseline real de 2026-07-17**, sem reescrever o PRD inteiro.

---

## 2. Mudanças normativas de métrica

| Antes (legado / sessão) | Agora (canônico) | ADR |
|-------------------------|------------------|-----|
| `commercial_opportunity_any` | **`entities_with_recent_commercial_signal`** | ADR-018 |
| “Cobertura 95%” ambígua | **`operational_source_coverage` ≥ 95%** (meta de proposta) | ADR-018 |
| Headline único | **Dual headline obrigatório** (sinal comercial **e** cobertura operacional) | ADR-018 |
| Denominadores variáveis | **1.093** fixo (`raio_200km` ativo) | ADR-018 |

### Baseline carimbado (não negociar para “parecer melhor”)

| Métrica | Valor | Data |
|---------|-------|------|
| `entities_with_recent_commercial_signal` | **116 / 1.093 (10,61%)** | 2026-07-17 |
| `operational_source_coverage` | **Não canônico ainda — meta de E1–E3** | — |
| Editais raw path histórico | 52 / 1.093 (4,76%) | pré-sessão multi-source |

**Regra comercial:** materiais externos podem citar 116 como sinal comercial atual e 95% como **meta de cobertura operacional do roadmap**, nunca como fato presente.

---

## 3. UX primária

| Decisão | Detalhe |
|---------|---------|
| **Workspace é a UX primária** | Facade CLI `workspace today \| opportunities \| coverage` (ADR-017) |
| CLIs legadas | Permanecem para debug/engenharia; não são o caminho feliz do consultor |
| Persona | Tiago Sasaki — inalterada do PRD v2.0 |

---

## 4. Escopo — OUT explícito

| Item | Status |
|------|--------|
| **Acompanhamento físico de obra** | **FORA DE ESCOPO** |
| Gestão de canteiro / medições de obra | FORA |
| Multi-tenant SaaS / billing | FORA (W2/W3 PRD) |
| UI web como interface primária | FORA nesta fase |

Monitoramento de **contratos administrativos** e atos oficiais (C9) **não** é acompanhamento de obra física.

---

## 5. Capacidades da proposta (índice)

Ver matriz completa. Resumo MoSCoW reordenado para operação:

| Prioridade | Capacidade | Meta |
|------------|------------|------|
| Must (ops) | C1 cobertura operacional, C2 oportunidades, C10 rotina | E1–E5 |
| Should | C3 histórico, C4 concorrentes, C7 triagem | E5–E7 |
| Could | C5 expiry, C6 preços, C8 proposal pack, C9 admin contracts, C10 reports | E8–E13 |

---

## 6. Requisitos delta (FR/NFR acréscimos)

### Funcionais

- **FR-DELTA-01:** Sistema expõe M1 e M2 com nomes canônicos em CLI e JSON.
- **FR-DELTA-02:** ESR cobre 100% das 1.093 entidades com binding explícito (inclusive unknown).
- **FR-DELTA-03:** `workspace today` é o comando diário default do consultor.
- **FR-DELTA-04:** Ranking usa somente Client Profile versionado (ADR-022).
- **FR-DELTA-05:** Adapters marcam 429 como `rate_limited` e não contam success de coverage.

### Não funcionais

- **NFR-DELTA-01:** Raw dumps não versionados no git (ADR-020).
- **NFR-DELTA-02:** Freshness SLA por fonte; workspace partial se P0/P1 stale.
- **NFR-DELTA-03:** Fail-closed em partial/rate_limited (ADR-021).

---

## 7. Relação com epics legados

| Artefato legado | Relação |
|-----------------|---------|
| EPIC-MASTER-B2G-READINESS | Infra/readiness — **complementar**; este epic é **vertical comercial-operacional** |
| EPIC-COVERAGE-100PCT / MAX-200KM | Alimenta dados; métricas reinterpretadas via ADR-018 |
| EPIC-B2G-MAX-EVOLUTION | Waves de evolução — alinhar ranking/briefing a E4/E5 |

Não arquivar legados automaticamente; **priorizar** E1–E5 deste programa para destravar a proposta.

---

## 8. Success metrics (programa)

| Métrica | Baseline | Alvo programa |
|---------|----------|---------------|
| M1 commercial signal | 10,61% | crescer com recall real (sem meta % mentirosa) |
| M2 operational_source_coverage | unmeasured | **≥ 95%** |
| Tempo rotina Tiago | N CLIs | **&lt; 15 min** com `workspace today` |
| go_no_go_3y | NO-GO | GO (E6) |
| prices capability | 0 sources | ≥1 fonte com itens (E9) |

---

## 9. Riscos de produto

1. **Overselling 95%** — mitigado por dual-metric e este delta.
2. **Expectativa de win-rate/preço** — declarar NOT_READY até E7/E9.
3. **Obra física** — stakeholder alignment: fora de escopo.

---

## 10. Aprovação

| Papel | Status |
|-------|--------|
| PM | Draft → ready for stakeholder review |
| PO | Validar stories E1–E5 |
| Architect | ADRs 017–022 Accepted |

---

## 11. Changelog

| Data | Mudança |
|------|---------|
| 2026-07-17 | Criação do delta; rename métrica; workspace primary; out obra física |
