# GATE-1 — LOCAL_FOUNDATION

**Campanha:** EPIC-PLANO-EXECUTIVO-30D  
**Validação técnica (re-prova HEAD):** 2026-07-16  
**HEAD:** `5355292` (+ fixes de migration/universe/ledger em branch de validação)  
**Status:** **PARTIAL → majoritariamente PASS** (não declarar `LOCAL_READY` DoD global; sem cobertura 95%)

## Scorecard L1 (re-provado)

| Task | Status | Evidência |
|------|--------|-----------|
| L1.1 pré-requisitos | **PASS** | python3 + docker compose + pgvector image; capture `gate1-env.log` |
| L1.2 universo 1093 | **PASS** | `snapshot generate` → included=1093, excluded=992, entities=2085; `target_universe_entities=2085` |
| L1.3 fresh migrations | **PASS** | 54/54 OK em `fresh_mig_test` com pgvector; 049 fix (DROP VIEW + DROP CHECK + ALTER + recreate) |
| L1.4 registry capability | **PASS/PARTIAL** | registry fontes OK; CIGA público sem credencial; matriz ente×fonte×capability ainda agregada (não 100% unknown resolvido) |
| L1.5 golden path | **PASS** | `gp-20260716-194636` SUCCESS pcp+compras_gov; ledger list válido (2 runs); sem crash append |
| L1.6 resume/DLQ | **PASS** | unit suite DLQ/watermark/freshness 8/8; ledger normalize 5/5 |
| L1.7 backup/restore | **PASS** | pg_dump Fc + pg_restore em `restore_drill`: 60 tables, 346 bids, 2085 universe |
| L1.8 manifesto | **DONE** | este arquivo |

## Pode afirmar

- Fresh install **54/54** migrations com imagem `pgvector/pgvector:pg16`.
- Universo canônico materializado no DB (1093 included).
- Golden path essencial (PCP + ComprasGov) sem crash de ledger.
- Backup→restore local testado (não Storage Box remoto).
- CIGA Dados path público sem chave (C2.5).

## Não pode afirmar

- Cobertura ≥95% editais ou contratos.
- DoD gate `LOCAL_READY` (exige ROL1+ROL3 + 95% + aceite Tiago).
- Storage Box / backup remoto Hetzner.
- PNCP sempre online (timeouts ocasionais).

## Capturas (scratch validação)

- `mission-unit.log`, `ciga-runtime.log`, `gate1-fresh-migrations.log`
- `gate1-universe.log`, `gate1-golden-path.log`, `gate1-backup-restore.log`
- `gate1-mig049-applied.log`

## Fixes aplicados nesta validação

1. `049_pncp_resumable_backfill.sql`: DROP views dependentes + DROP `chk_pncp_raw_bids_esfera_id` (integer) antes de ALTER TYPE TEXT + recreate views/check.
2. `tests/test_golden_path_ledger.py`: testes shipped do normalize/save ledger.
3. Universe: `PYTHONPATH=. python3 scripts/universe_tools.py snapshot generate`.
