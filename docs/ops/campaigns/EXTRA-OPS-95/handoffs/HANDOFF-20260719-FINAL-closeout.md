# HANDOFF FINAL — EXTRA-OPS-95 recovery session closeout

**UTC:** 2026-07-19T16:21:16Z  
**Branch:** `campaign/extra-ops-95-20260719`  
**HEAD:** `1a18dd3566997fe3bbb1b1a153ed7283865ea1fb`  
**Remote:** `origin/campaign/extra-ops-95-20260719` (SHA local == remoto no push)  
**Status global:** **PARTIAL** (não DONE)

## Primeiros comandos

```bash
cd "/mnt/d/extra consultoria"
git fetch origin && git checkout campaign/extra-ops-95-20260719 && git pull --ff-only
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
docker start extra-test-db
cat docs/ops/campaigns/EXTRA-OPS-95/STATUS.md
cat docs/ops/campaigns/EXTRA-OPS-95/evidence/session-metrics.json
```

## Métricas (session-metrics closeout)

| Métrica | Valor |
|---------|------:|
| DOD | 313/1352 (23.1509%) |
| Presença editais | 279 (25.5261%) |
| Presença contratos | 329 (30.1006%) |
| SZ contratos | 722 |
| **Ops proxy contratos** | **1051/1093 (96.1574%) ≥95%** |
| Gap ops→95% | 0 |
| bids / contracts rows | 10831 / 409490 |

## Definição ops proxy (não 7 estágios)

```
ops_proxy = lake presence(orgao_cnpj8) OR entity success_zero(cnpj14 root + http_204_complete)
```

## Entregue nesta retomada

1. Recovery seguro pós-WSL: inventário, safety patch, commits, branch remota.
2. Restore DB (migrations + dump M5) e rebuild de métricas.
3. Ops proxy contratos reconstruído a **96.1574%** (presence∪SZ).
4. Multi-source editais parcial (sc_compras enrich; PNCP recovery evidence versionada).
5. HTML executivo + STATUS + ledger + handoffs honestos.
6. DECISION-002: cobertura > dyn-slice docs; N09 BLOCKED_SOURCE.

## Frentes

| Frente | Class |
|--------|-------|
| Contracts ops proxy ≥95% | DONE (proxy def) |
| Editais presence/ops | PARTIAL (~25.5%) |
| DOD ≥55% | PARTIAL (~23.2%) |
| N09 gold/recall | BLOCKED_SOURCE |
| Campaign DONE / LOCAL_READY | NOT_READY |

## Próximas frentes (extra-roi / DECISION-002)

1. Expandir **presença/ops de editais** (gap principal).
2. DOD com evidência item-a-item (sem mass flips) em direção a 55%.
3. Manter N09 BLOCKED até amostra-ouro independente.
4. QA adversarial antes de qualquer claim DONE.

## Não repetir

- force push / reset --hard / clean destrutivo
- claim either como meta 95%
- claim 7 estágios ou LOCAL_READY/DONE
- reabrir N01
- inventar CNPJ sem BrasilAPI/root validation
- commitar `.env` / dumps PG / snapshots qw-01 gigantes

## Residual deliberadamente não versionado

| Path | Motivo |
|------|--------|
| `evidence/M5-backup/*.dump` | dump PG binário |
| `data/cnpj14_cache/*.bak`, `*.pre-purge-mismatch` | backup cache |
| `output/qw-01/*/universe_snapshot.json`, `coverage_gaps.csv`, `*.xlsx` | artefatos grandes |
| `ROI-cand-dyn-slice-cb906bb58392` story/state | Draft deferido DECISION-002 |
| `.env*` | secrets |

## Veredito

**PARTIAL** — recovery completo e ops proxy contratos ≥95% sob definição documentada; metas vinculantes editais 95%, DOD 55% e campanha DONE permanecem abertas.

## Artefatos

- `docs/ops/campaigns/EXTRA-OPS-95/STATUS.md`
- `docs/ops/campaigns/EXTRA-OPS-95/evidence/session-metrics.json`
- `docs/ops/campaigns/EXTRA-OPS-95/evidence/M2-remeasure/recovery-final.json`
- `extra-consultoria-plano-executivo.html` (painel ops95)
- `docs/ops/campaigns/EXTRA-OPS-95/roi/DECISION-002-recovery-override.json`
