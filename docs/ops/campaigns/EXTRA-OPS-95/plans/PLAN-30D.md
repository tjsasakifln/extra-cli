# EXTRA-OPS-95 — Plano de marcos (~30 dias úteis coordenados)

**HEAD start:** `dbc5adb` · **Denominador:** 1093 · **Metas:** editais ≥95% e contratos ≥95% **separadas**

## Caminho crítico (PERT resumido)

```
M0 recovery ✓
 → M1 metric contract + baseline
 → M2 coverage waves (editais ‖ contracts)  [CRÍTICO]
 → M3 opportunity decision cycle
 → M4 competitors/values/admin contracts
 → M5 automation + 3 cycles + backup/restore
 → M6 recall benchmark (or BLOCKED_SOURCE honest)
 → M7 acceptance + HTML + DOD + handoff
```

| Marco | Dias úteis (esforço) | Dependências | Critério |
|-------|---------------------:|--------------|----------|
| M0 Recovery | 0.5 | — | Inventário + baseline live |
| M1 Contrato métricas | 1.5 | M0 | Baseline JSON + semântica fixa |
| M2.1 Promote ops stages | 2.0 | M1 | Promover entidades com evidência real |
| M2.2 Contracts 365d+ | 5.0 | M1 | Mais entidades + janela |
| M2.3 Editais multi-source | 5.0 | M1 | PNCP/CIGA/SC-Compras residual |
| M2.4 Success_zero + matching | 3.0 | M2.1 | Zeros explícitos contam |
| M2.5 Marco 60% | 2.0 | M2.* | ≥656/1093 cada (ou blocker nominal) |
| M2.6 Marco 80% | 3.0 | M2.5 | ≥875/1093 cada |
| M2.7 Marco 95% | 4.0 | M2.6 | ≥1039/1093 cada ou BLOCKED |
| M3 Intel + decisão | 3.0 | M2.1+ | GO/REVIEW/NO_GO live + dossiers |
| M4 Concorrentes/valores | 2.0 | M2.2 | Outputs com semântica de valor |
| M5 Automação/idempotência | 3.0 | M3 | 3 run_ids + restore |
| M6 Benchmark recall | 2.5 | M3 | ≥200 obs ou BLOCKED_SOURCE |
| M7 Aceitação/HTML/DOD | 2.0 | M5+ | HTML + handoff |
| **Total esforço** | **≥38.5** | | Paralelismo reduz calendário |

## Regras

- Nunca substituir editais∪contratos por either.
- Nunca fixture como live.
- Nunca SmartLic dataset no caminho crítico.
- Extra-roi após cada onda M2.
- WIP: no máximo uma migration writer; um editor DOD; um editor HTML.

## Sequência canônica operacional (alvo H)

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
export DATABASE_URL="$LOCAL_DATALAKE_DSN"
# 1 coleta
python3 -m scripts.crawl.monitor --source pncp --mode incremental
# 2 contratos incremental
CONTRACTS_FULL_DAYS=7 python3 -c "from scripts.crawl.contracts_crawler import crawl; crawl('incremental')"
# 3 promote registry
python3 -m scripts.source_registry.cli acquire --strategy pipeline_evidence --dsn "$LOCAL_DATALAKE_DSN" --limit 0
# 4 coverage report
python3 -m scripts.coverage.coverage_contract_cli report --output docs/ops/campaigns/EXTRA-OPS-95/evidence/contract-report.json
# 5 opportunity cycle
python3 -m scripts.opportunity_intel.cli update --source pncp
python3 -m scripts.workspace today
# 6 packages (quando estáveis)
python3 -m scripts.ops.deliverable_package_final
```

(Comandos refinados conforme evidência de cada onda.)
