# PE-L1-01 — Pré-requisitos de ambiente (evidência real)

**Story:** PE-L1-01  
**Executado em:** 2026-07-16T22:11:51Z  
**Host:** CMTESASAKI (WSL2 Linux 6.6.87.2-microsoft-standard-WSL2)  
**Commit HEAD:** `1f7aa7c`  
**Branch:** `epic/plano-executivo-30d`

## Veredito resumido

| Item | Status | Evidência |
|------|--------|-----------|
| Python 3.12+ | **PASS** (via `python3`) | `Python 3.12.3` — `/usr/bin/python3` |
| Comando `python` | **FAIL** | `python: command not found` (alias/shim ausente) |
| Docker | **PASS** | Docker 28.3.2, Compose v2.38.2 |
| Postgres local (compose default) | **PASS (após start)** | `docker compose up -d test-db` → healthy em `:5433` |
| `.env` presente | **PASS** | `test -f .env` → yes; `.env.example` → yes |
| DSN local | **PASS** | `DATABASE_URL` / `LOCAL_DATALAKE_DSN` apontam para `127.0.0.1:5433` |
| Extensão `vector` no compose default | **FAIL** | Imagem `postgis/postgis:16-3.4` **não** tem `pgvector` |
| Fresh migrations exit 0 no HEAD | **BLOCKED** | Ver `l1-fresh-migrations.md` |

## Comandos executados (verbatim / resultados)

```text
$ python --version
/bin/bash: line 1: python: command not found

$ python3 --version
Python 3.12.3

$ which docker
/usr/bin/docker

$ docker --version
Docker version 28.3.2, build 578ccf6

$ docker compose version
Docker Compose version v2.38.2

$ docker compose ps   # antes do start: vazio / container exited
$ docker compose up -d test-db
# → Container extraconsultoria-test-db-1 Running / healthy
# PORTS: 0.0.0.0:5433->5432/tcp

$ test -f .env && echo ENV_EXISTS=yes
ENV_EXISTS=yes

$ test -f .env.example && echo ENV_EXAMPLE=yes
ENV_EXAMPLE=yes

$ which psql && psql --version
/usr/bin/psql
psql (PostgreSQL) 18.4 (Ubuntu 18.4-1.pgdg24.04+1)
```

## Stack Docker do projeto

| Arquivo | Serviço | Imagem | Porta host | Observação |
|---------|---------|--------|------------|------------|
| `docker-compose.yml` | `test-db` | `postgis/postgis:16-3.4` | 5433 | Persistente (`pgdata`); **sem pgvector** |
| `docker-compose.local.yml` | `test-db` | `postgis/postgis:16-3.4` | 5433 | tmpfs; **sem pgvector** |
| Workaround PE-L1 | container `pe-l1-pgvector` | `pgvector/pgvector:pg16` | 54397 | Usado para tentativa de fresh migrate com vector |

`db/setup_db.sh` declara requisitos:

- PostgreSQL 16
- Extensions: `pg_trgm`, `uuid-ossp`, **`vector` (pgvector)**
- `psql` no PATH

**Gap documentado:** o compose default do repositório **não** atende o requisito de `vector` do setup script.

## Variáveis de ambiente (presença — sem valores)

| Variável | Status no `.env` |
|----------|------------------|
| `DATABASE_URL` | PRESENT (host redacted: `postgresql://test:***@127.0.0.1:5433/pncp_datalake`) |
| `LOCAL_DATALAKE_DSN` | PRESENT |
| `TEST_DSN` | PRESENT |
| `SUPABASE_URL` | EMPTY/PLACEHOLDER |
| `SUPABASE_ANON_KEY` | EMPTY/PLACEHOLDER |
| `SUPABASE_SERVICE_ROLE_KEY` | EMPTY/PLACEHOLDER |
| `OPENAI_API_KEY` | EMPTY/PLACEHOLDER |
| `DOM_SC_*` | EMPTY/PLACEHOLDER |
| `DOE_SC_*` | EMPTY/PLACEHOLDER |
| `GOOGLE_APPLICATION_CREDENTIALS` | PRESENT (path len=29) |

**Mínimo para migrations/DB local:** `DATABASE_URL` ou `LOCAL_DATALAKE_DSN` + Postgres saudável + `psql` + imagem com extensões corretas.

**Não mínimo para L1 de schema, mas necessário para crawlers com credencial:** DOM-SC, DOE-SC, MIDES/GCP, OpenAI.

## Conectividade Postgres (evidência)

1. **Antes do start:** `DATABASE_URL` host `127.0.0.1:5433` → `TimeoutError` (container `Exited (255)`).
2. **Após `docker compose up -d test-db`:** TCP open; `pg_isready` OK; `psql \l` lista DBs:

| Database | Papel |
|----------|-------|
| `extra_test` | tests |
| `pncp_datalake` | datalake local existente |
| `pe_l1_fresh` | criado para tentativa de fresh install no compose default |
| `template_postgis` | template |

## Tooling Python auxiliar verificado

| Tool | Resultado |
|------|-----------|
| `openpyxl` | 3.1.5 (necessário para universo) |
| `psycopg2` | OK |
| `psycopg` (v3) | **ausente** (`ModuleNotFoundError`) |
| `ruff` / `mypy` / `pytest` | presentes em `~/.local/bin` |

## Contagem de migrations no HEAD

```text
$ ls -1 db/migrations/*.sql | wc -l
54
```

Arquivos em `db/migrations/` de `001_pncp_raw_bids.sql` até `049_pncp_resumable_backfill.sql` (inclui sufixos `a/b/c/d`).

## Tabelas canônicas críticas esperadas (derivadas das migrations)

Lista de `CREATE TABLE` parseada de `db/migrations/*.sql` (nomes normalizados, sem schema):

**Núcleo de dados / cobertura / universo**

- `pncp_raw_bids`, `pncp_supplier_contracts`, `enriched_entities`
- `sc_public_entities`, `sc_municipalities`, `sc_dados_abertos_backfill_log`
- `entity_coverage`, `entity_hierarchy`, `entity_aliases`
- `coverage_evidence`, `coverage_snapshots`, `capability_coverage`
- `source_applicability_rules`, `source_snapshot_membership`
- `target_universe_entities`, `target_universe_runs`
- `opportunity_intel`, `opportunity_runs`, `opportunity_checkpoints`, `opportunity_coverage`
- `ingestion_runs`, `ingestion_checkpoints`
- `dlq_entries`, `pipeline_runs`, `pipeline_watermarks`, `record_hashes`
- `pncp_backfill_runs`, `pncp_backfill_pages`, `pncp_backfill_records` (migration 049)
- `contract_version_history`, `engineering_opportunities`, `pncp_enrichment_cache`
- `dedup_cross_source`, `retention_policy`, `_migrations`

## Estado do DB local `pncp_datalake` (não-fresh)

- Ledger: **53 linhas** em `_migrations` (mistura de version keys legadas `1`/`001`/`21a` e statuses `applied`/`failed` — ledger sujo).
- Tabelas presentes: **28**.
- Contagens amostrais: `pncp_raw_bids=343`, `sc_public_entities=2085`, `entity_coverage=18765`, `target_universe_entities=0`.
- Ausentes vs HEAD migrations: `pipeline_runs`, `pipeline_watermarks`, `record_hashes`, `opportunity_coverage`, `pncp_backfill_*`.

## Blockers / unknown (explícitos)

1. **BLOCKER:** compose default sem `pgvector` → fresh migrate falha na `014`.
2. **BLOCKER:** mesmo com `pgvector/pgvector:pg16`, `049` falha (ver doc de migrations).
3. **GAP:** shim `python` ausente; scripts/docs que usam `python` quebram neste host.
4. **UNKNOWN:** não validado neste L1 se a VPS de produção usa a mesma imagem/extensões.
5. **UNKNOWN:** Supabase remoto não testado (placeholders no `.env` local).

## Como reproduzir

```bash
cd "/mnt/d/extra consultoria"
python3 --version
docker compose up -d test-db
docker compose ps
test -f .env && echo ENV_EXISTS=yes
PGPASSWORD=test psql -h 127.0.0.1 -p 5433 -U test -d extra_test -c 'SELECT 1'
ls -1 db/migrations/*.sql | wc -l
```
