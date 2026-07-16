# C2 — PCP + TCE-SC Runtime Evidence (PE-C2-02)

**Story:** PE-C2-02  
**Data evidência:** 2026-07-16T22:10–22:20Z (aprox.)  
**Branch:** `epic/plano-executivo-30d`  
**HEAD:** `1f7aa7c`  
**Ambiente:** workstation local + Postgres `pncp_datalake` (`127.0.0.1:5433`)

---

## Veredito consolidado

| Fonte | Status runtime | Import | API smoke | Persistência local | Credenciais |
|-------|----------------|--------|-----------|--------------------|-------------|
| **PCP** (`pcp`) | **OK** | OK | OK (página 1 SC) | **Sim** (`source='pcp'`) | Públicas (nenhuma) |
| **TCE-SC** (`tce_sc`) | **OK (API)** / **sem ingestão nesta sessão** | OK | OK (`_fetch_licitacoes` 2026) | **Não observado** em `pncp_raw_bids` no recorte | Públicas (nenhuma) |

Não se inventa % de cobertura. Abaixo: contagens absolutas e amostras.

---

## PCP — Portal de Compras Públicas v2

### Módulo / API

- Código: `scripts/crawl/pcp_crawler.py`
- Base: `https://compras.api.portaldecompraspublicas.com.br`
- Endpoint listagem: `/v2/licitacao/processos`
- Auth: nenhuma
- UF server-side: `codigoUf` (SC = `100142`, mapa `_PCP_UF_CODE`)

### Import + dry-run

```text
IMPORT_OK scripts.crawl.pcp_crawler
monitor --source pcp --mode dry-run --dsn $DATABASE_URL → exit 0, [DRY RUN] Would crawl pcp
```

### Smoke API (limitado, 1 página)

Chamada direta:

```python
pcp._fetch_page(1, data_inicial, data_final, codigo_uf="100142")  # janela 14d
```

| Campo | Valor |
|-------|--------|
| Janela | 2026-07-02 → 2026-07-16 |
| `page1_records` | **10** (page size fixo da API v2) |
| `has_next` | **True** |
| Latência | ~0.7s |
| Transform amostra | 5/5 registros transformáveis |

Amostra bruta (campos públicos, sem PII sensível):

- `identificacao` exemplo: `181 / 2026 - 2153`
- Transform: `uf=SC`, `orgao_cnpj=None` (esperado: API listing não devolve CNPJ — ver CM-06), `pncp_id` sintético `pcp_*`, município preenchido

### Banco (`pncp_raw_bids` WHERE source='pcp') — snapshot evidência

| Métrica | Valor |
|---------|--------|
| Linhas | **340** (ordem de grandeza no momento do smoke; sujeita a crawls concorrentes) |
| Linhas com `uf='SC'` | 340 |
| `matched_entity_id` não nulo | **135** |
| Entidades distintas matched | **78** |
| `min(data_publicacao)` | 2026-05-18 |
| `max(data_publicacao)` | 2026-07-16 |
| `max(ingested_at)` | 2026-07-16 ~22:11Z |

Amostras recentes no DB (órgãos):

- Câmara Municipal de Maravilha  
- Prefeitura Municipal de Araquari  
- Prefeitura Municipal de Maracajá  

### `ingestion_runs` (PCP)

Observado no recorte recente:

| status | count (agg) | Notas |
|--------|-------------|--------|
| completed | 6 | Ex.: run id 27: `records_fetched=181`, `records_upserted=167` (2026-07-16 22:10Z) |
| failed | 7 | Erros históricos de upsert: `ON CONFLICT DO UPDATE command cannot affect row a second time` |
| running | 4 | Runs órfãos com 0 fetched |

**Honesto:** API e ingestão PCP **funcionam** no HEAD; há **dívida operacional** de runs `running` e falhas de upsert por duplicata no mesmo batch (já parcialmente mitigada em histórias anteriores, mas still visible em histórico).

### Histórico reconciliado

| Artefato | Claim |
|----------|--------|
| CM-06-PCP-fix (state Done/PASS) | CNPJ `None` evita FK; smoke monitor full 55 inserted / 14 matched na época |
| CM-07 bootstrap | API aberta; `SOURCE_BLOCKERS` não deve marcar PCP como CAPTCHA |

---

## TCE-SC — SCMWeb JSON

### Módulo / API

- Código: `scripts/crawl/tce_sc_crawler.py`
- Base: `https://www.scmweb.com.br/processos/index.php`
- Auth: nenhuma
- Funções: `_fetch_licitacoes`, `_fetch_contratos`, `crawl`, `crawl_by_year`, `crawl_by_municipio`

### Import + dry-run

```text
IMPORT_OK scripts.crawl.tce_sc_crawler
monitor --source tce_sc --mode dry-run → exit 0, [DRY RUN] Would crawl tce_sc
```

### Smoke API

| Probe | Resultado |
|-------|-----------|
| GET base URL | HTTP 200, HTML (~18 KB), ~0.15s |
| `tce._fetch_licitacoes(ano=2026)` | **2880** registros, ~64.6s |
| Sample keys | `Numero`, `Modalidade`, `Objeto`, `Data_Abertura`, `Valor_Estimado`, `Status`, `Ano` |

### Persistência

- Nenhuma linha `source='tce_sc'` (ou equivalente) observada em `pncp_raw_bids` no inventário por `source` do smoke.  
- Status: **API alcançável e retorna volume material**; **pipeline de upsert TCE→DB não foi exercitado** nesta story (evitou full crawl/ingest caro).

### Nota de escopo

Documento unifica **PCP + TCE** porque o plano C2 trata fontes SC complementares; vereditos permanecem **separados** na tabela acima.

---

## O que NÃO se afirma

- % de cobertura de editais abertos SC.  
- Que TCE esteja “em produção” no datalake (sem linhas observadas).  
- Que falhas históricas de upsert PCP estejam 100% resolvidas (histórico ainda mostra `failed`).

---

## Comandos reproduzíveis

```bash
python3 -c "from scripts.crawl import pcp_crawler as p; from datetime import date,timedelta; \
e=date.today(); s=e-timedelta(days=14); r,h=p._fetch_page(1,s.isoformat(),e.isoformat(),codigo_uf=p._PCP_UF_CODE['SC']); \
print(len(r), h)"

python3 -c "from scripts.crawl import tce_sc_crawler as t; r=t._fetch_licitacoes(ano=2026); print(len(r))"

psql "$DATABASE_URL" -c "SELECT source, count(*), count(*) FILTER (WHERE matched_entity_id IS NOT NULL) FROM pncp_raw_bids GROUP BY 1;"
```
