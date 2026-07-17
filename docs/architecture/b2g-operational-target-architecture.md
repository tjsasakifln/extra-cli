# Arquitetura-Alvo — B2G Operational Platform

| Campo | Valor |
|-------|-------|
| **Versão** | 1.0 |
| **Data** | 2026-07-17 |
| **Status** | Target (to-be) |
| **ADRs** | 017–022 |
| **Epic** | EPIC-B2G-OPERATIONAL-PLATFORM |

---

## 1. Propósito

Descrever a arquitetura **operacional** que transforma coleta multi-fonte em rotina diária do consultor e entregáveis comerciais — com **prova de cobertura**, **fail-closed** e **métricas honestas**.

Não substitui `system-architecture.md` (as-is amplo); **especializa** o caminho feliz comercial 200 km SC.

---

## 2. Diagrama C4-ish (containers / fluxos)

```
                    ┌──────────────────────────────────────┐
                    │         CLIENT PROFILE (ADR-022)     │
                    │   sole commercial law for ranking    │
                    └──────────────────┬───────────────────┘
                                       │
┌─────────────┐   discover    ┌────────▼─────────┐
│  Portals /  │──────────────►│ ENTITY SOURCE    │
│  APIs / DO  │               │ REGISTRY (ESR)   │◄── ADR-019
└──────┬──────┘               │ 1093 × sources   │
       │                      └────────┬─────────┘
       │ target set                    │
       ▼                               ▼
┌─────────────────────────────────────────────┐
│              SOURCE ADAPTERS                │  ADR-021
│  PNCP │ SC Compras │ CIGA │ DOM │ PCP │ …  │
│  fetch() → FetchResult (fail-closed 429)    │
└──────────────────────┬──────────────────────┘
                       │ raw payloads
                       ▼
              ┌─────────────────┐
              │   RAW ZONE      │  ADR-020 (not in git)
              │ output/{src}/   │
              │ run_id + hash   │
              └────────┬────────┘
                       │ normalize()
                       ▼
              ┌─────────────────┐
              │  CANONICAL /    │
              │  RESOLVE        │  entity match, dedup
              │  PostgreSQL     │
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌────────────┐ ┌─────────┐ ┌──────────────┐
   │ EVIDENCE   │ │ BIDS /  │ │ CONTRACTS /  │
   │ LEDGER     │ │ OPPTY   │ │ ACTS         │
   └─────┬──────┘ └────┬────┘ └──────┬───────┘
         │             │             │
         └─────────────┼─────────────┘
                       ▼
              ┌─────────────────┐
              │ BUSINESS RULES  │  ranking, triage, expiry
              │ + PROFILE LAW   │
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │   WORKSPACE     │  ADR-017
              │ today / oppty / │
              │ coverage        │
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │ REPORTS / PDF   │  weekly/monthly
              │ client packs    │
              └─────────────────┘

  HUMAN FEEDBACK ──► labels ──► RULES/PROFILE (loop)
  SCHEDULER (systemd/cron) ──► ADAPTERS (E3)
```

---

## 3. Camadas

| Camada | Responsabilidade | SoT |
|--------|------------------|-----|
| **Source Registry (global)** | Capabilities, SLA, credentials, module path | `scripts/crawl/registry.py` |
| **Entity Source Registry** | Applicability por órgão | ESR table/JSON (ADR-019) |
| **Adapters** | Fetch + status semântico | crawlers sob contrato ADR-021 |
| **Raw** | Payload imutável por run | `output/` gitignored |
| **Normalize** | Mapear para schema canônico | transformers |
| **Resolve** | Entity + supplier match, dedup cross-source | matcher + dedup |
| **Persist** | PostgreSQL canônico + evidence | DB |
| **Rules** | Score, triage, expiry heuristics | profile-bound |
| **Workspace** | UX operacional CLI | facade |
| **Reports** | Entregáveis cliente | generators |

---

## 4. SLAs de freshness (alvo)

| Fonte | SLA `last_success` | Severidade se estourar |
|-------|--------------------|------------------------|
| PNCP bids | 4 h | HIGH — bloqueia `workspace today` GO pleno |
| SC Compras | 24 h | HIGH |
| CIGA DOM | 24–48 h | MEDIUM |
| Contracts backfill | 24 h (job), janelas históricas best-effort | MEDIUM |
| Portais municipais | 48 h | LOW–MEDIUM |

**Regra workspace:** se fonte P0/P1 acima do SLA → exit 2 (partial) e alerta no `today`.

---

## 5. Fail-closed (resumo operacional)

```
rate_limited | partial_unreconciled | auth_blocked
        → NÃO grava evidence success
        → NÃO incrementa M2 coverage
        → propaga alerta no workspace
        → checkpoint para retoma
```

Zero records só é sucesso com `empty_confirmed` auditável.

---

## 6. Dual-metric coverage (ADR-018)

```
M1 entities_with_recent_commercial_signal   # baseline 116/1093
M2 operational_source_coverage              # meta ≥ 95%
```

Ambos com denominador **1.093** fixo. Workspace e relatórios **sempre** emitem os dois.

---

## 7. Human feedback loop

```
Tiago: workspace opportunities → label GO|NO-GO|WATCH
     → store (opportunity_id, profile_version, label, reason, ts)
     → lista operacional respeita override
     → batch review mensal pode ajustar weights do profile (version bump)
```

---

## 8. Segurança e dados

- Segredos só em env / secret store.
- Raw e DB backups fora do git (ADR-020).
- Single-user CLI; sem superfície web multi-tenant nesta fase.

---

## 9. Fora de escopo (arquitetura)

- Acompanhamento físico de obra.
- Multi-tenant SaaS.
- UI web como primária.

---

## 10. Mapa de implementação por epic

| Epic | Entrega arquitetural |
|------|----------------------|
| E1 | Calculadora multi-métrica + identity tests |
| E2 | ESR 1093 + discovery writers |
| E3 | Scheduler + adapters fail-closed + raw policy |
| E4 | Workspace facade |
| E5 | Profile law + triage |
| E6–E13 | Domínios analíticos sobre a base estável |

---

## 11. Referências

- `docs/architecture/adversarial-diagnosis-b2g-2026-07-17.md`
- `docs/architecture/source-acquisition-strategy.md`
- `docs/architecture/system-architecture.md`
- `docs/prd/capability-matrix-b2g-proposta.md`
