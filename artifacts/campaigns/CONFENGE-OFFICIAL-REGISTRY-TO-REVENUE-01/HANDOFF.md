# HANDOFF — CONFENGE-OFFICIAL-REGISTRY-TO-REVENUE-01

**HEAD:** `1419c444` (atualizar se avançar) · **PR:** https://github.com/tjsasakifln/extra-cli/pull/183  
**Status:** `PARTIAL_PASS_SELECTIVE_WITH_FULL_COMMERCIAL_RERUN`

## O que está pronto (máquina)

1. Módulo `scripts/company_registry` (lifecycle + CLI + selective-fetch + outcome ledger).
2. Fail-closed no `confenge_commercial_cycle`: ACTIVE + load não vazio + provenance + coverage/Top20 quando interest file; **postcheck** Top20 oficial.
3. Release seletiva ACTIVE `selective-selective-merged` com **2497** estabelecimentos oficiais.
4. **Ciclo comercial full history EXECUTADO:** `cl-20260730T201737Z-a35bd698` (22.882 candidatos, 20 leads).
5. Top20 **20/20** `registry_is_official`; kits Top5 com contratos/valores/evidências reais.
6. Coverage seletiva (interest matched): official_match **1.0**, usable **0.9976**, top20 **1.0**.
7. Testes `tests/company_registry/` — **19 passed**.
8. Make targets `company-registry-*`.
9. `DOD-PROPOSED-CHANGES.md` (sem editar `DOD.md`).

## Estados de liberação

| Estado | Valor | Nota |
|--------|-------|------|
| REGISTRY_READY | **true** | no universo seletivo carregado (2497) |
| REGISTRY_READY_FULL_POPULATION_22882 | **false** | bulk RFB não completo |
| RANKING_READY | **true** | re-run + Top20 oficial 100% |
| READY_FOR_TIAGO_REVIEW | **true** | kits + dossiers; humano pendente |
| READY_FOR_MANUAL_OUTREACH | **false** | não forjado |
| COMMERCIAL_OUTCOME_OBSERVED | **false** | sem eventos humanos |

Terminal comercial residual: `BLOCKED_INSUFFICIENT_HUMAN_LABELS`.

## Cobertura honesta (não confundir denominadores)

| Universo | n | official_match |
|----------|---|----------------|
| Interest matched (ACTIVE load) | 2497 | **1.0** |
| Full frozen interest | 5660 | **~0.325** (rate-limit residual) |
| Full commercial population (pipeline) | 22882 | **~0.047** |
| Baseline pré-campanha | 22882 | **~0.029** |

## O que a próxima sessão deve fazer

1. **Bulk RFB** quando listing/ZIP acessível (ou stage local) → `refresh --raw-dir` → claim bulk só então.
2. **Retry residual** dos ~3.8k CNPJs interest com rate-limit (OpenCNPJ) ou ZIP RFB.
3. **Tiago review** → aceite humano; nunca auto `APPROVED_FOR_CONTACT`.
4. Promover itens de `DOD-PROPOSED-CHANGES.md` após merge das campanhas paralelas.

## Comandos

```bash
export COMPANY_REGISTRY_ROOT=$PWD/data/company_registry
export CONFENGE_COMMERCIAL_STATE_DSN='postgresql://test:test@127.0.0.1:5433/confenge_commercial_activation'
export CONFENGE_COMMERCIAL_SNAPSHOT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/snapshot/snapshot-manifest.json
export CONFENGE_OFFICIAL_INTEREST_CNPJ_FILE=artifacts/campaigns/CONFENGE-OFFICIAL-REGISTRY-TO-REVENUE-01/matched-interest-cnpjs.txt

python3 -m scripts.company_registry health
python3 -m scripts.company_registry lookup --cnpj 43371025000104
python3 -m scripts.company_registry commercial-precheck
make confenge-commercial-cycle   # fail-closed sem ACTIVE
python3 -m pytest tests/company_registry/ -q
```

## Bloqueios residuais

| Bloqueio | Tipo |
|----------|------|
| RFB bulk listing 404/timeout | Rede / fonte |
| Residual interest ~67% sem match seletivo | Rate-limit API redistribuidor |
| Full 22.8k official_match ≥99.5% | Exige bulk ou selective completo |
| Human outreach / labels | Tiago |
| VPS SSH proof | Não executado nesta sessão (NI por isolamento de paths) |

## Non-claims

`bulk_rfb_mirror_complete`, `official_match_1.0_on_22882`, `READY_FOR_MANUAL_OUTREACH`, `COMMERCIAL_OUTCOME_OBSERVED`, `PROJECT_DONE`, `VPS_OPERATIONAL`, receita, auto-send.
