# BASELINE — EXTRA-OPERATIONAL-PROOF-01

**Data da medição:** 2026-07-19  
**HEAD main medido:** `c6570c9` (`campaign(EXTRA-OPS-95): recovery + contracts ops proxy ≥95% (PARTIAL) (#29)`)  
**Branch de campanha:** `campaign/extra-operational-proof-01`  
**DSN local medido:** `postgresql://test:test@127.0.0.1:5433/extra_test` (container `extra-test-db`)

## 1. Estado remoto

| Item | Valor medido |
|------|----------------|
| `origin/main` | `c6570c9` |
| PR #28 | **CLOSED**, `mergeable=CONFLICTING`, head `epic/advance-30d-local-ready-20260718` — **não integrar** |
| PRs abertos | #48 draft (CTO Autopilot) — **fora do escopo** desta campanha |
| Claim EXTRA-OPS-95 na main | Proxy contratos `presence ∪ entity success_zero` — **não** cobertura operacional 7 estágios |

## 2. Dados locais (medição direta)

| Recurso | Contagem |
|---------|----------|
| `sc_public_entities` | 2.085 |
| Universo 200 km (`raio_200km=TRUE`) | **1.093** (confirma denominador canônico) |
| `pncp_raw_bids` | 10.831 |
| `pncp_supplier_contracts` | 498.809 |
| `engineering_opportunities` | 7.768 |
| `opportunity_intel` | 401 (REVIEW=397, NO_GO=4, **GO=0**) |
| open/upcoming ativos | 391 |
| `pipeline_runs` | 0 (schema existe, não usado no ciclo semanal) |
| `opportunity_runs` recentes | runs PNCP em 2026-07-19 (completed/partial/failed) |
| `entity_source_registry` / `target_universe_entities` | 0 |
| `official_acts` | 0 |

## 3. Entry points existentes (fragmentados)

| Comando | Papel | Ciclo semanal completo? |
|---------|-------|-------------------------|
| `python -m scripts.workspace …` | Facade diária (today, opportunities, report weekly parcial) | **Não** — report weekly ≠ coleta+quality+entrega |
| `python -m scripts.golden_path` | Validação pipeline multi-fonte | **Não** — prova técnica, não pacote consultivo Extra |
| `python -m scripts.ops.resilient_cycle` | Ciclo resiliente (fixtures/live) | **Não** — foco crawl/resiliência |
| `python -m scripts.opportunity_intel.cli update` | Coleta oportunidades | Componente |
| `python -m scripts.ops.deliverable_package_final` | Pacote PDF+Excel | **Fixture-first** — não prova entrega real |
| `make golden-path` / `run-pipeline` | Orquestração legada | Múltiplos, sem canônico semanal Extra |

**Lacuna principal:** não existe um único comando que faça collect → process → quality → intelligence → delivery com manifest, freshness e exit codes consultivos.

## 4. CI (medição)

| Job | Quando roda | Observação |
|-----|-------------|------------|
| Lint / type-check | PR + push main | Obrigatório |
| Test (critical readiness) | PR + push main | Subconjunto fixo; `--cov-fail-under=10` |
| Test All (full suite) | **somente `workflow_dispatch`** | Dívida residual; não gate de PR |
| Resilience Gate | PR + push main | Migrations + testes resiliência |

## 5. Claims baseline (honestos)

**Permitidos:**

- Universo canônico 1.093 entidades no raio 200 km no banco local.
- Existem 401 oportunidades em `opportunity_intel` e ~499k contratos PNCP no lake local.
- CI crítico + resiliência existem; full suite não é gate de PR.
- PR #28 está fechado e conflitante.

**Proibidos:**

- `LOCAL_READY` / `PRE_VPS_FINAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE`
- Cobertura operacional 95% (editais ou 7 estágios)
- Proxy de contratos = cobertura completa
- Recall independente ≥95%
- Pacote consultivo semanal canônico (ainda inexistente nesta baseline)

## 6. Objetivo desta campanha

Menor evolução que produza:

```bash
make extra-weekly
# → python -m scripts.ops.weekly_cycle --strict
```

com pacote real (Markdown + Excel + CSV + manifest), freshness, proveniência e exit codes 0/1/2/3.
