# Evidence — DoD §12.2 Saídas operacionais (8 listas)

**Story:** `ROI-cand-dyn-slice-b50513eeb753`  
**Cycle:** `cyc-2026-07-18T153340Z`  
**Branch:** `epic/advance-30d-local-ready-20260718`  
**Date:** 2026-07-18  
**Module:** `scripts/reports/operational_outputs.py`

## DoD items in scope

| # | Item | Proof |
|---|------|-------|
| 1 | Lista de editais acionáveis | `lists/editais_acionaveis.csv` GO=**6** |
| 2 | Lista de editais para revisão | `lists/editais_revisao.csv` REVIEW=**1** |
| 3 | Lista de editais descartados com motivo | `lists/editais_descartados.csv` NO_GO=**1** + coluna `motivo` |
| 4 | Lista de oportunidades removidas do snapshot | `lists/oportunidades_removidas_snapshot.csv` N=0 (header estável; `is_active=false` query) |
| 5 | Lista de entes sem cobertura de editais | CSV + limitação: `sc_public_entities` empty no DB de prova |
| 6 | Lista de entes sem cobertura de contratos | CSV + mesma limitação de universo |
| 7 | Lista de blockers por fonte | `lists/blockers_por_fonte.csv` N=**1** (ingestion_failed pncp) |
| 8 | Lista de runs stale | gerador + demo `lists-stale-demo/` com stuck_running_hours=0 → **2** runs stuck |

## Commands

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m pytest tests/test_operational_outputs.py -q --no-cov -o addopts=
python3 -m scripts.reports.operational_outputs --dsn "$LOCAL_DATALAKE_DSN" --out docs/ops/session-2026-07-18-operational-outputs/lists --json
# stale capability demo:
python3 -c "from scripts.reports.operational_outputs import run; print(run('$LOCAL_DATALAKE_DSN','docs/ops/session-2026-07-18-operational-outputs/lists-stale-demo',stale_hours=1,stuck_running_hours=0)['counts'])"
```

## Results

- pytest: **5 passed** (`pytest.exit` = 0)
- ranking_source: `pncp_raw_bids+compute_ranking`
- counts default: GO=6 REVIEW=1 NO_GO=1 blockers=1
- reliability: **DEGRADED** (limitations present — honest)
- limitations: universe entities empty on this PG → gap lists cannot enumerate

## Non-claims

- Not LOCAL_READY / PRE_VPS / VPS / PROJECT_DONE
- Not operational coverage ≥95%
- Not claiming universe-wide gap completeness without seeded `sc_public_entities`
