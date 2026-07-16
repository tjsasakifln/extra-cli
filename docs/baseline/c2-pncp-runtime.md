# C2 — PNCP Runtime Evidence (PE-C2-02)

**Story:** PE-C2-02  
**Data evidência:** 2026-07-16T22:10–22:20Z (aprox.)  
**Branch:** `epic/plano-executivo-30d`  
**HEAD:** `1f7aa7c` (`1f7aa7c feat: publish data foundation pipeline changes`)  
**Ambiente:** workstation local (WSL/Linux) + Postgres `pncp_datalake` em `127.0.0.1:5433`

---

## Veredito

| Campo | Valor |
|-------|--------|
| **Status** | **PARTIAL → BLOCKED para crawl de publicações** |
| **Import** | OK (`scripts.crawl.pncp_crawler_adapter`) |
| **Dry-run monitor** | OK (skipped by design; carrega 2085 entidades) |
| **API consulta publicações** | **FALHA** neste ambiente (timeout / disconnect) |
| **API host parcial** | OK em endpoint de catálogo de órgãos |
| **Persistência `source='pncp'`** | **0 linhas** em `pncp_raw_bids` |
| **Credenciais** | Não requer (fonte pública) |

Não se declara cobertura % de oportunidades PNCP. Contagens absolutas abaixo.

---

## O que foi testado (barato / seguro)

### 1. Import

```text
IMPORT_OK scripts.crawl.pncp_crawler_adapter
IMPORT_OK scripts.crawl.monitor
```

### 2. Dry-run via monitor

```bash
python3 scripts/crawl/monitor.py --source pncp --mode dry-run --dsn "$DATABASE_URL"
```

Resultado:

- Exit code `0`
- `2085` entidades ativas carregadas (`1093` com `raio_200km`)
- `[DRY RUN] Would crawl pncp` → status skipped (esperado)
- `DEFAULT_DSN` do settings aponta para `127.0.0.1:54399` **sem senha**; dry-run **só funciona** com `--dsn` = `DATABASE_URL` (`5433/pncp_datalake`)

### 3. Probe HTTP — endpoint de publicação (crawl real)

Base usada pelo adapter: `https://pncp.gov.br/api/consulta/v1`  
(`PNCP_CONSULTA_BASE` / `scripts/crawl/pncp_crawler_adapter.py`)

| Tentativa | Resultado |
|-----------|-----------|
| `GET .../v1/contratacoes/publicacao?dataInicial=YYYYMMDD&dataFinal=YYYYMMDD&codigoModalidadeContratacao=6&uf=SC&pagina=1&tamanhoPagina=10` (timeout 15–30s) | `TimeoutError: The read operation timed out` |
| Mesmo path com `PNCP_BASE` env (`.../api/consulta/v3`) | `HTTP 404` |
| Tentativas anteriores na sessão | `RemoteDisconnected: Remote end closed connection without response` |

Conclusão: o **endpoint de publicações usado pelo crawler não respondeu a tempo** a partir desta rede. Isso bloqueia dry-run “de verdade” (fetch de editais) sem inventar sucesso.

### 4. Probe HTTP — host PNCP parcialmente alcançável

| Endpoint | Resultado |
|----------|-----------|
| `GET https://pncp.gov.br/api/pncp/v1/orgaos` | **HTTP 200**, ~45.8 MB JSON (lista), ~11.8s |
| `GET https://pncp.gov.br/` | `RemoteDisconnected` |

Interpretação honesta: o host `pncp.gov.br` **não está 100% inalcançável**, mas o **caminho de consulta de contratações/publicação falha ou trava** daqui. Compatível com hipóteses de rate-limit, WAF, geo/path específico ou degradação do serviço de consulta — **não confirmado causalmente neste smoke**.

### 5. Banco local (`pncp_datalake`)

| Métrica | Valor observado |
|---------|-----------------|
| `count(*) FROM pncp_raw_bids WHERE source = 'pncp'` | **0** |
| `ingestion_runs` status=`running` source=`pncp` | **vários** (ex.: ids 14–17, 23, 26) com `records_fetched=0`, sem `finished_at` |
| `ingestion_runs` status=`failed` source=`pncp` | **1** (sem detalhe útil de API no recorte) |
| Linhas totais `pncp_raw_bids` | dominadas por `pcp` + `compras_gov` (não PNCP) |

Runs `running` órfãos sugerem crawls interrompidos/timeout sem cleanup — **sintoma**, não prova isolada de bug de código.

---

## Reconciliação com evidências históricas (não reexecutadas aqui)

| Artefato | Data | Claim |
|----------|------|-------|
| `docs/stories/CM-08-pncp-api-validation.md` | 2026-07-15 | API real: publicações `tamanhoPagina=50` OK; UF=SC `totalRegistros=1185` naquele momento; contratos page 500 OK; filtro UF contratos quebrado server-side |
| `.aiox/state/stories/CM-08-pncp-api-validation.json` | Done / QA CONCERNS | AC de page size validados |
| `docs/audits/pncp-entity-coverage-2026-07.md` | 2026-07-15 | Documenta endpoints; DB local offline naquele audit |

**HEAD atual:** constantes/page sizes e adapter existem e importam. **Runtime de publicação no ambiente PE-C2-02:** não reproduziu o sucesso de CM-08.

---

## Causa real do BLOCKED/PARTIAL (honesta)

1. **Fetch de `/contratacoes/publicacao` timeout/disconnect** no ambiente de evidência (2026-07-16).  
2. **Zero linhas** `source='pncp'` no datalake local.  
3. **Ingestion runs PNCP** em `running` com 0 fetched — sem conclusão de sucesso.  
4. Código e dry-run de orquestração **não** são o bloqueio principal; o bloqueio é **runtime de rede/API de consulta** (+ possível limpeza de runs).

---

## O que NÃO foi feito (escopo)

- Crawl full/incremental massivo (caro / risco de hang longo).  
- Deploy/crawl na VPS Brasil.  
- Declaração de % de cobertura de editais abertos ou “monitoring coverage”.  
- Mutação de schema ou push.

---

## Próximos passos sugeridos (fora desta story)

1. Reexecutar smoke de publicação a partir de IP/VPS BR (`ec-prod`) e comparar latência.  
2. Encerrar/limpar `ingestion_runs` PNCP `running` órfãos.  
3. Alinhar `DEFAULT_DSN` vs `DATABASE_URL` para monitor sem `--dsn` manual.  
4. Só após fetch OK: incremental limitado + contagem `source='pncp'`.

---

## Comandos reproduzíveis

```bash
# Import
python3 -c "import scripts.crawl.pncp_crawler_adapter as m; print('ok')"

# Dry-run (DB necessário para entidades)
python3 scripts/crawl/monitor.py --source pncp --mode dry-run --dsn "$DATABASE_URL"

# Contagem honesta no DB
psql "$DATABASE_URL" -c "SELECT source, count(*) FROM pncp_raw_bids GROUP BY 1;"
psql "$DATABASE_URL" -c "SELECT status, count(*) FROM ingestion_runs WHERE source='pncp' GROUP BY 1;"
```
