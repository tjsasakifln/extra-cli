# CONFENGE-OFFICIAL-REGISTRY-TO-REVENUE-01 — FINAL REPORT

**Date:** 2026-07-30  
**Branch:** `feat/confenge-official-registry-revenue`  
**Base main:** `8ff80eef`

## Objetivo

Eliminar o bloqueio cadastral oficial do pipeline comercial CONFENGE com espelho local, versionado e consultável da base pública de CNPJ (Receita Federal), sem reconstruir o projeto nem criar segundo pipeline comercial.

## Arquitetura

Módulo canônico novo:

```text
scripts/company_registry/
  models, paths, normalization, integrity, downloader,
  release_discovery, extract, loader, store, lookup,
  coverage, activate, refresh, diff, health, locks,
  commercial_bridge, selective_fetch, outcome_ledger, cli
```

Armazenamento: SQLite por release sob `data/company_registry/` (fora do Git), com pointer atômico `active/ACTIVE_RELEASE.json`.

Integração comercial:

- `scripts/ops/confenge_commercial_cycle.py` — fail-closed se não houver release `ACTIVE` (`CONFENGE_REQUIRE_OFFICIAL_REGISTRY=1` default).
- `commercial_bridge.publish_matches_to_supplier_registry` grava em `supplier_registry` com labels RFB-authority (`rfb_public_cadastral*`).
- Reutiliza `official_registry_coverage` / `is_official_registry_source` existentes — **não** cria segundo conceito.

## Fonte oficial

| Item | Valor |
|------|--------|
| Autoridade | RECEITA_FEDERAL |
| Discovery URLs | `arquivos.receitafederal.gov.br/.../dados_abertos_cnpj/`, `dadosabertos.rfb.gov.br/CNPJ/`, `200.152.38.155/CNPJ/` |
| Resultado discovery (este ambiente) | **FAILED** — 404 / timeout |
| Caminho usado | **selective** via redistribuidor OpenCNPJ de dados públicos RFB |
| Source label | `rfb_public_cadastral_via_opencnpj` |
| Bulk completeness claimed | **false** |

## Release ativa

| Campo | Valor |
|-------|--------|
| release_id | `selective-selective-official` |
| status | ACTIVE |
| establishments | 211 |
| companies | 211 |
| mode | selective_jsonl |
| snapshot | `selective-selective-official:196608` |

## Cobertura (universo de interesse medido)

Universo = 211 CNPJs do shortlist comercial (top20 durable + leads/candidatos em artefatos de campanhas CONFENGE existentes), **não** os 22.882 candidatos do histórico completo.

| Métrica | Valor | Meta |
|---------|-------|------|
| valid_cnpj_share | 1.0 | — |
| official_match_coverage | 1.0 | ≥0.995 |
| commercial_registry_usable_coverage | 1.0 | ≥0.98 |
| top20_official_registry_coverage | 1.0 | 1.0 |

**Baseline pré-campanha (população full):** `official_registry_coverage ≈ 0.0292` (result.json campanha commercial activation).

## Top 20 / Top 5

- `top20-official.json` — 20/20 MATCHED com situação, CNAE, release, provenance.
- `top5-manual-outreach.json` — kits completos; `auto_send=false`; estados humanos não forjados.
- Visão de ranking: **establishment_level** (CNPJ-14).

## Outcome ledger

- Implementado em `scripts/company_registry/outcome_ledger.py`.
- Estados humanos `APPROVED_FOR_CONTACT`, `CONTACTED`, `REPLIED`, `MEETING_SCHEDULED`, `WON` exigem `human_confirmed` e proíbem actor machine.
- Eventos reais nesta sessão: **0** → `COMMERCIAL_OUTCOME_OBSERVED=false`.

## Testes

```text
python3 -m pytest tests/company_registry/ -q
# 15 passed
```

Cobertura: normalize/DV, HTML/truncado, download skip, load/activate/rollback, statuses, coverage denominators, markers oficiais, ledger human-only, fail-closed precheck, CLI, partial activate, HTTP 403/404/429/5xx.

## Paralelismo

Não alterados:

- `DOD.md`
- `scripts/source_registry/`, `scripts/process_documents/`, `scripts/crawl/`, `scripts/bid_readiness/`
- systemd/timers de coletores
- definição dos 1.093 entes

Sem migration SQL (registry oficial em SQLite isolado).

## VPS / soak

- Execução local; VPS não SSH nesta sessão.
- Prova de não-interferência por isolamento de paths + claim documentado em `soak-non-interference.json`.
- Disco local livre ~504 GB.

## Limitaciones honestas

1. Bulk RFB ZIP não baixado (endpoints inacessíveis daqui).
2. Cobertura 100% refere-se ao **shortlist de interesse (211)**, não à população full 22.882.
3. Ciclo comercial full (`make confenge-commercial-cycle`) sobre 4,4M contratos exige DSN+snapshot autenticado no ambiente do operador — pré-check de registry agora falha fechado sem ACTIVE.
4. Outreach / aceites humanos **não** foram forjados.
5. OpenCNPJ é redistribuidor; label explícito; não é CRM privado como autoridade, mas também não é o ZIP bulk direto da RFB.

## Próximos passos operacionais

```bash
# Quando ZIPs RFB estiverem acessíveis / staged:
python3 -m scripts.company_registry refresh --raw-dir data/company_registry/raw/<release_id>

# Ou selective full candidates (22k):
python3 -m scripts.company_registry selective-fetch --cnpj-file candidates.txt --out /path/sel.jsonl --workers 8
python3 -m scripts.company_registry refresh --jsonl /path/sel.jsonl --source-label rfb_public_cadastral_via_opencnpj --force

# Publicar no supplier_registry e rodar ciclo:
export CONFENGE_OFFICIAL_INTEREST_CNPJ_FILE=...
export CONFENGE_COMMERCIAL_STATE_DSN=...
export CONFENGE_COMMERCIAL_SNAPSHOT=...
make confenge-commercial-cycle
```

## Non-claims

`PROJECT_DONE`, `VPS_OPERATIONAL`, `LOCAL_READY`, receita gerada, bulk RFB completo, `READY_FOR_MANUAL_OUTREACH`, `COMMERCIAL_OUTCOME_OBSERVED`.
