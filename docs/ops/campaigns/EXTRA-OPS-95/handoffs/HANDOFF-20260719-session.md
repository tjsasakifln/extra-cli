# HANDOFF — EXTRA-OPS-95-FOUNDATION (sessão 2026-07-19)

## Estado canônico

| Campo | Valor |
|-------|-------|
| Campanha | EXTRA-OPS-95-FOUNDATION |
| Status global | **PARTIAL** (não DONE) |
| Branch | `campaign/extra-ops-95-20260719` |
| Main start | `dbc5adb` |
| Work tip (pré-commit local) | ver `git rev-parse HEAD` |
| DOD | **195/1355 = 14,39%** (sem inflação) |
| Denominador 200 km | **1093** |
| Universe resolution (radar) | **100%** |
| Presença editais | ~268/1093 (**24,5%**) — não operacional 7 estágios |
| Presença contratos | ~247/1093 (**22,6%**) em janela ~14d; 90d em curso |
| Registry operational | **139/1093 (12,72%)** |
| Oportunidades live | **401** (GO=0, REVIEW=397, NO_GO=4) |
| N09 recall | **BLOCKED_SOURCE** |
| PR #28 | **não mergear** |
| SmartLic dados | **DEFER/REJECT** operacional |

## O que foi entregue nesta sessão

1. **M0 baseline foundation** — `baseline/foundation-baseline.json` + `BASELINE.md`
2. **M0.5 OSS matrix** — `oss/oss-decisions.json` (0 ADOPT sem piloto)
3. **M1 universo** — rebuild PG, migrations 001–057, seed 2085/1093, 2ª import 0 inserts
4. **M2 re-coleta** — 72.925 contratos (14d), 8.221 bids PNCP; promote registry
5. **M3** — fix upsert opportunity (content_hash + arrays); loop modalidades no CLI; 401 opps REVIEW-first
6. **B1 OCDS thin** + **B2 Pydantic contracts** com testes unitários
7. **Bugfix** migration `057` + cast `esfera_id` em 018 para fresh install

## Primeiro comando do próximo agente

```bash
cd "/mnt/d/extra consultoria"
git checkout campaign/extra-ops-95-20260719  # ou main se mergeado
docker start extra-test-db
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
export DATABASE_URL="$LOCAL_DATALAKE_DSN"
# 1) status contracts 90d
cat data/contracts_checkpoints/contracts_full.json
python3 -c "import psycopg2;c=psycopg2.connect('$LOCAL_DATALAKE_DSN');cur=c.cursor();cur.execute('select count(*) from pncp_supplier_contracts');print(cur.fetchone())"
# 2) ROI override cobertura
python3 squads/extra-dod-roi/scripts/cli.py force-next  # se rank claims → ignorar (DECISION-001)
# 3) expandir cobertura + success_zero
CONTRACTS_FULL_DAYS=90 python3 -m scripts.crawl.monitor --source contracts --mode full --dsn "$LOCAL_DATALAKE_DSN"
```

## Documentos a ler (ordem)

1. `docs/ops/campaigns/EXTRA-OPS-95/STATUS.md`
2. `docs/ops/campaigns/EXTRA-OPS-95/baseline/foundation-baseline.json`
3. `docs/ops/campaigns/EXTRA-OPS-95/roi/DECISION-001.json`
4. `docs/ops/campaigns/EXTRA-OPS-95/oss/oss-decisions.json`
5. `docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/scope.json` (N01–N18; N09 blocked)
6. `DOD.md`

## Não repetir

- Reabrir N01 como marco
- Mergear PR #28 às cegas
- Contar either como cobertura
- Usar SmartLic stale no numerador
- Fechar checkbox DOD sem evidência
- Assumir 1M contratos sem re-coleta (volume PG foi zerado nesta sessão)

## Blockers abertos

| ID | Classe | Condição de desbloqueio |
|----|--------|-------------------------|
| N09 | BLOCKED_SOURCE | Amostra-ouro ≥200 independente |
| blk-coverage-95 | WORK | Mais janelas + multi-source + success_zero + promote |
| blk-pncp-429 | RATE_LIMIT | Backoff maior; serializar crawls |
| profile Extra | BLOCKED_HUMAN | 14 campos PENDING no profile |

## Hipóteses a validar

- Expandir contratos 90d/365d eleva presença contratos de 22% → 40%+?
- success_zero auditável fecha gap de entes sem publicação?
- CIGA/sc_compras residual cobre entes sem PNCP?
- Pandera ainda necessário se Pydantic+PG CHECK bastarem?

## Claims proibidos

95% cobertura · either · LOCAL_READY · recall 95% · DOD 55% · SmartLic operacional · campanha DONE
