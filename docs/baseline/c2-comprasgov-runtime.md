# C2 — ComprasGov Runtime Evidence (PE-C2-02)

**Story:** PE-C2-02  
**Data evidência:** 2026-07-16T22:10–22:20Z (aprox.)  
**Branch:** `epic/plano-executivo-30d`  
**HEAD:** `1f7aa7c`  
**Ambiente:** workstation local + Postgres `pncp_datalake` (`127.0.0.1:5433`)

---

## Veredito

| Campo | Valor |
|-------|--------|
| **Status** | **OK** (API + transform + ingestão recente) |
| **Import** | OK (`scripts.crawl.compras_gov_crawler`) |
| **Dry-run monitor** | OK |
| **API Lei 14.133** | OK (UF=SC, janela 45d, 1 página) |
| **`crawl('incremental')`** | OK (2 registros na janela incremental default) |
| **Persistência** | **Sim** — `source='compras_gov'` no DB |
| **Credenciais** | Não requer (dados abertos) |
| **Geo-restrição** | Não observada (API responde da workstation) |

Reconciliação com claim CM-09: **validado no HEAD** — crawler continua funcional contra API real.

Não se inventa % de cobertura nacional/SC.

---

## Módulo / API

- Código: `scripts/crawl/compras_gov_crawler.py`
- Base: `https://dadosabertos.compras.gov.br` (`COMPRASGOV_BASE`)
- Endpoint primário: `/modulo-contratacoes/1_consultarContratacoes_PNCP_14133`
- Filtro UF server-side: `unidadeOrgaoUfSigla` (não `uf` solto — param incorreto → 404)
- Datas: `dataPublicacaoPncpInicial` / `dataPublicacaoPncpFinal` em **YYYY-MM-DD** (≠ PNCP YYYYMMDD)
- Legado: `/modulo-legado/1_consultarLicitacao` só se `COMPRASGOV_LEGACY_ENABLED=true` (default off)

---

## Testes executados

### 1. Import + dry-run

```text
IMPORT_OK scripts.crawl.compras_gov_crawler
monitor --source compras_gov --mode dry-run --dsn $DATABASE_URL → exit 0
[DRY RUN] Would crawl compras_gov
```

### 2. Smoke `_paginate` (1 página, SC, 45 dias)

Parâmetros:

```text
dataPublicacaoPncpInicial = 2026-06-01
dataPublicacaoPncpFinal   = 2026-07-16
codigoModalidade          = 0
unidadeOrgaoUfSigla       = SC
tamanhoPagina             = 10
max_pages                 = 1
```

| Campo | Valor |
|-------|--------|
| Status | **API_OK** |
| Registros página | **8** |
| Latência | ~1.0s |
| Transform | 5/5 (amostra) com `uf=SC`, `orgao_cnpj` preenchido |

Amostra transform:

- `orgao_razao_social`: MUNICIPIO DE IBIAM  
- `orgao_cnpj`: 01612745000174  
- `uf`: SC  

Keys brutas (parcial): `idCompra`, `numeroControlePNCP`, `orgaoEntidadeCnpj`, `orgaoEntidadeRazaoSocial`, …

### 3. `crawl('incremental')` no módulo

| Campo | Valor |
|-------|--------|
| `raw` length | **2** |
| Latência | ~0.19s |
| Janela | `INGESTION_INCREMENTAL_DAYS` (default 1 dia no código) |

### 4. Banco — snapshot

| Métrica | Valor |
|---------|--------|
| `count(*) WHERE source='compras_gov'` | **3** (no momento do inventário) |
| `uf='SC'` | 3 |
| matched | 2 |
| `min/max data_publicacao` | 2026-07-13 … 2026-07-15 |
| `max(ingested_at)` | 2026-07-16 ~22:11Z |

Amostras no DB:

| Órgão | UF | data_publicacao | CNPJ |
|-------|----|-----------------|------|
| CONSELHO REGIONAL DE ENGENHARIA E AGRONOMIA DE SANTA CATARINA | SC | 2026-07-15 | 82511643000164 |
| CONSELHO DE ARQUITETURA E URBANISMO DE SANTA CATARINA | SC | 2026-07-13 | 14895272000101 |

### 5. `ingestion_runs`

| status | count | Notas |
|--------|-------|--------|
| completed | 4 | Ex. run id 28 (22:11Z): fetched=2, upserted=2 |

Nenhum `failed` de `compras_gov` no agg recente.

---

## Reconciliação CM-09 (2026-07-15)

| Claim CM-09 | HEAD 2026-07-16 |
|-------------|-----------------|
| Lei 14.133 SC ~45d retorna registros | **Confirmado** (8 na página 1) |
| Transform schema `pncp_raw_bids` | **Confirmado** (CNPJ/UF) |
| Sem geo-restrição | **Confirmado** (smoke local) |
| Ex.: CREA-SC / 8 raw | CREA-SC ainda presente no DB; volume total no datalake **baixo** (3 linhas) — janelas curtas / poucas execuções full |

Diferença honesta: CM-09 documentou 8 raw na janela de teste; o **datalake local não acumula histórico longo** de ComprasGov (apenas 3 linhas). Isso é **estado de ingestão**, não falha da API.

---

## Armadilhas documentadas

1. Query com `uf=SC` em vez de `unidadeOrgaoUfSigla=SC` → **HTTP 404**.  
2. `DEFAULT_DSN` ≠ `DATABASE_URL` quebra monitor sem `--dsn`.  
3. Incremental de 1 dia pode retornar poucos registros (2) mesmo com API saudável.

---

## O que NÃO se afirma

- Cobertura % de órgãos SC via ComprasGov.  
- Paridade de volume com PNCP.  
- Ativação de timer systemd em VPS (fora do escopo).

---

## Comandos reproduzíveis

```bash
python3 - <<'PY'
from datetime import date, timedelta
from scripts.crawl import compras_gov_crawler as cg
params = {
  "dataPublicacaoPncpInicial": (date.today()-timedelta(days=45)).isoformat(),
  "dataPublicacaoPncpFinal": date.today().isoformat(),
  "codigoModalidade": 0,
  "unidadeOrgaoUfSigla": "SC",
  "tamanhoPagina": 10,
}
recs = cg._paginate(cg.LEI_14133_ENDPOINT, params, max_pages=1)
print("n=", len(recs))
print("transform=", len(cg.transform(recs[:5])))
print("incremental=", len(cg.crawl("incremental")))
PY

psql "$DATABASE_URL" -c "SELECT orgao_razao_social, data_publicacao, orgao_cnpj FROM pncp_raw_bids WHERE source='compras_gov';"
```
