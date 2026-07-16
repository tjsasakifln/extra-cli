# PE-L1-02 — Source × capability registry (evidência real)

**Story:** PE-L1-02  
**Executado em:** 2026-07-16T22:11:51Z  
**Commit HEAD:** `1f7aa7c`  
**Fonte de verdade no código:** `scripts/crawl/registry.py`  
**API usada:** `iter_sources()`, `get_capability_sources()`

## Veredito

| Check | Status |
|-------|--------|
| Registry central carrega | **PASS** — 11 fontes ativas |
| Capabilities tipadas | **PASS** — 7 literais em `SourceCapability` |
| Matriz applicable / not_applicable | **PASS** (nível **fonte**, não ente) |
| Matriz fonte×**ente**×capability | **PARTIAL / unknown** — schema DB existe; dados de aplicabilidade por ente não reconciliados neste L1 |
| Caps sem nenhuma fonte | **YES (explícito)** — `prices`, `source_health` |
| Cobertura 95% por capability | **NÃO CALCULADA / NÃO INVENTADA** |

## Capabilities conhecidas (`SourceCapability`)

```text
open_tenders
historical_contracts
competitors
prices
entity_matching
coverage_truth
source_health
```

## Inventário de fontes (registry runtime)

| # | source | active | purpose | authority | contract_source | module | freshness_sla_h | zero_proof | credentials |
|---|--------|--------|---------|-----------|-----------------|--------|-----------------|------------|-------------|
| 1 | `pncp` | True | bids | federal | False | `pncp_crawler_adapter` | 4 | True | — |
| 2 | `dom_sc` | True | bids | municipal | False | `dom_sc_crawler` | 24 | False | DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY |
| 3 | `pcp` | True | bids | multi | False | `pcp_crawler` | 24 | False | — |
| 4 | `compras_gov` | True | bids | federal | False | `compras_gov_crawler` | 12 | False | — |
| 5 | `sc_compras` | True | bids | estadual | False | `sc_compras_crawler` | 24 | False | — |
| 6 | `contracts` | True | contracts | federal | **True** | `contracts_crawler` | 24 | True | — |
| 7 | `transparencia` | True | bids | municipal | False | `transparencia_crawler` | 48 | False | — |
| 8 | `tce_sc` | True | bids | estadual | False | `tce_sc_crawler` | 24 | False | — |
| 9 | `doe_sc` | True | bids | estadual | False | `doe_sc_crawler` | 24 | False | DOE_SC_LOGIN, DOE_SC_PASSWORD |
| 10 | `ciga_ckan` | True | coverage_only | municipal | False | `ciga_ckan_crawler` | 48 | False | — |
| 11 | `mides_bigquery` | True | bids | estadual | False | `mides_bigquery_crawler` | 48 | False | GOOGLE_APPLICATION_CREDENTIALS |

**Nota Story 1.5:** `selenium` **não** é fonte (método de crawl). `contracts` ≠ bids (`is_contract_source=True`).

## Matriz fonte × capability

Legenda: **A** = applicable (declarado no `SourceInfo.capabilities`) · **N** = not_applicable

| source | open_tenders | historical_contracts | competitors | prices | entity_matching | coverage_truth | source_health |
|--------|--------------|----------------------|-------------|--------|-----------------|----------------|---------------|
| pncp | **A** | **A** | N | N | **A** | N | N |
| dom_sc | **A** | N | N | N | N | N | N |
| pcp | **A** | N | N | N | N | N | N |
| compras_gov | **A** | N | N | N | N | N | N |
| sc_compras | **A** | N | N | N | N | N | N |
| contracts | N | **A** | **A** | N | N | N | N |
| transparencia | **A** | N | N | N | N | N | N |
| tce_sc | **A** | **A** | N | N | N | N | N |
| doe_sc | **A** | N | N | N | N | N | N |
| ciga_ckan | N | N | N | N | N | **A** | N |
| mides_bigquery | **A** | N | N | N | N | N | N |

## Agrupamento por capability

### `open_tenders` (9 fontes)

`pncp`, `dom_sc`, `pcp`, `compras_gov`, `sc_compras`, `transparencia`, `tce_sc`, `doe_sc`, `mides_bigquery`

### `historical_contracts` (3 fontes)

`pncp`, `contracts`, `tce_sc`

### Outras

| capability | sources |
|------------|---------|
| `competitors` | `contracts` |
| `entity_matching` | `pncp` |
| `coverage_truth` | `ciga_ckan` |
| `prices` | **(none)** |
| `source_health` | **(none)** |

## Credenciais vs runtime local (blocker operacional)

| source | creds no registry | status no `.env` local |
|--------|-------------------|------------------------|
| `dom_sc` | 3 vars | EMPTY/PLACEHOLDER |
| `doe_sc` | 2 vars | EMPTY/PLACEHOLDER |
| `mides_bigquery` | `GOOGLE_APPLICATION_CREDENTIALS` | PRESENT (path) — **não validado** se arquivo existe/funciona |
| demais | public | N/A |

Fontes com credencial vazia **não** devem ser contadas como “cobertas em produção local” até validação de crawl.

## Schema DB relacionado (não preenchido neste L1)

Migrations definem (quando aplicadas):

- `source_applicability_rules`
- `mv_entity_source_applicability`
- `capability_coverage`
- `coverage_evidence` (+ campos de applicability em 040)

No `pncp_datalake` local observado:

- Tabelas de coverage/universo parcialmente presentes.
- **Não** há manifesto reconciliado ente×fonte×capability com contagens auditáveis nesta evidência.
- `target_universe_entities = 0` impede denominador DB-side por ente.

## Unknown / blockers explícitos

1. **`prices` e `source_health` sem fonte no registry** — capability órfã no type system.
2. **Applicability por ente** (qual das 1093 cada fonte cobre) = **unknown** no artefato L1; registry só declara intenção por fonte.
3. **Não confundir “capability applicable” com “cobertura medida”** — A na matriz ≠ dados coletados.
4. **Credenciais DOM-SC / DOE-SC ausentes** no `.env` local → crawls dessas fontes bloqueados.
5. **`pncp` declara `historical_contracts`** e também existe fonte `contracts` — possível overlap semântico; política de dedup entre elas não auditada aqui.
6. **Nenhuma % de cobertura** (ex. 95%) foi medida ou afirmada.

## Como reproduzir

```bash
cd "/mnt/d/extra consultoria"
python3 - <<'PY'
from scripts.crawl.registry import iter_sources, get_capability_sources, SourceCapability
from typing import get_args
print('sources', len(iter_sources()))
for s in iter_sources():
    print(s.order, s.name, s.capabilities)
for c in get_args(SourceCapability):
    print(c, [x.name for x in get_capability_sources(c)])
PY
```
