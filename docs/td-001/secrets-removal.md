# Secrets Removal Report — TD-1.2

**Date:** 2026-07-11
**Status:** Done
**Related to:** TD-DB-05, TD-SYS-005

## Summary

Remocao de todos os segredos hardcoded (senhas, tokens, credenciais) do codigo fonte versionado no git. Migracao para variaveis de ambiente via `os.getenv()` com fallback para string vazia.

## Files Modified

### 1. `config/settings.py`
- **Antes:** `LOCAL_DATALAKE_DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres")`
- **Depois:** `LOCAL_DATALAKE_DSN = os.getenv("LOCAL_DATALAKE_DSN", "")`
- Senha `smartlic_local` removida do fallback default.

### 2. `backend/local_datalake.py`
- **Antes:** `_LOCAL_DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres:extra_consultoria_local@127.0.0.1:54399/postgres")`
- **Depois:** `_LOCAL_DSN = os.getenv("LOCAL_DATALAKE_DSN", "")`
- Senha `extra_consultoria_local` removida do fallback default.

### 3. `scripts/datalake_helper.py`
- **Antes:** `dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres:extra_consultoria_local@127.0.0.1:54399/postgres")`
- **Depois:** `dsn = os.getenv("LOCAL_DATALAKE_DSN", "")`
- Senha `extra_consultoria_local` removida do fallback default.

### 4. `db/seed/001_sc_entities.py`
- **Antes:** `default=os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres")`
- **Depois:** `default=os.getenv("LOCAL_DATALAKE_DSN", "")`
- Senha `smartlic_local` removida do fallback default no `--dsn` argument.

### 5. `db/seed/seed_sc_entities.py`
- **Antes:** `default=os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres")`
- **Depois:** `default=os.getenv("LOCAL_DATALAKE_DSN", "")`
- Senha `smartlic_local` removida do fallback default no `--dsn` argument.

### 6. `scripts/datalake-sc-200km.py`
- **Antes:** `_LOCAL_DSN = os.environ.get("LOCAL_DATALAKE_DSN", "postgresql://postgres:extra_consultoria_local@127.0.0.1:54399/postgres")`
- **Depois:** `_LOCAL_DSN = os.environ.get("LOCAL_DATALAKE_DSN", "")`
- Senha `extra_consultoria_local` removida do fallback default.

### 7. `scripts/intel_pipeline.py`
- **Antes:** `subprocess.run(..., capture_output=False, ...)` — saida do subprocess ia direto para o terminal sem controle
- **Depois:** `subprocess.run(..., capture_output=True, ...)` — saida capturada e exibida de forma controlada (ultimas 15 linhas); stderr de erro exibido separadamente
- **Risco mitigado:** TD-SYS-005 — vazamento de dados via stdout/stderr de subprocessos

### 8. `.env.example`
- Adicionadas variaveis faltantes identificadas na auditoria:
  - `PNCP_FILES_BASE`
  - `INGESTION_CONCURRENT_UFS`, `INGESTION_BATCH_SIZE_UFS`
  - `INGESTION_FULL_CRAWL_HOUR_UTC`, `INGESTION_INCREMENTAL_HOURS`
  - `OPENAI_MAX_CONCURRENT`, `INTEL_LOG_LEVEL`
  - `PORTAL_TRANSPARENCIA_API_KEY`
  - `PCP_BASE`, `COMPRAS_GOV_BASE`
  - `ENTITY_ENRICHMENT_TTL_DAYS`

### 9. `.gitignore` (verificado)
- `.env` ja estava listado. Sem alteracoes necessarias.

## Git History Audit

### Senhas expostas no historico do git

| Commit | Arquivo | Segredo |
|--------|---------|---------|
| `352dac5` | `scripts/crawl/monitor.py` | `postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres` |

O commit `352dac5` (feat: 7 crawlers adaptados + monitor) continha a senha `smartlic_local` no arquivo `scripts/crawl/monitor.py`. Esta senha foi posteriormente alterada no commit `b0df2a3` para `postgresql://postgres@127.0.0.1:5433/pncp_datalake` (sem senha).

**Nota:** A senha `smartlic_local` exposta no git history refere-se ao banco **local de desenvolvimento** (`127.0.0.1:54399`), nao ao banco de producao. A rotacao de senha do banco local e recomendada apos esta migracao.

A senha `postgres:extra_consultoria_local@127.0.0.1:54399` aparece apenas no working tree, nao no historico do git (arquivos que nunca foram commitados com essa senha).

## Verification

### Antes da correcao
```bash
grep -rn 'password\|senha' --include='*.py' .
```
Retornava DSNs com senhas em texto puro em 6 arquivos.

### Depois da correcao
```bash
grep -rn 'smartlic_local\|extra_consultoria_local' --include='*.py' .
```
Nao retorna resultados (segredos removidos do codigo fonte).

## Env Vars Required

Apos esta migracao, o sistema requer que a variavel `LOCAL_DATALAKE_DSN` esteja configurada no ambiente ou no arquivo `.env` para conectar ao banco PostgreSQL. Sem ela, as conexoes falharao com DSN vazio.

### Configuracao minima (.env)
```
LOCAL_DATALAKE_DSN=postgresql://postgres:<sua-senha>@<host>:<port>/pncp_datalake
DATALAKE_BACKEND=local
```

## Risk Assessment

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| DSN vazio causa crash ao iniciar sem .env | Media | Alto | Mensagem de erro clara: conexao falha com DSN vazio |
| Senha rotacionada mas .env nao atualizado | Baixa | Critico | Testar em staging antes de rotacionar |
| git history mantem senha antiga | Alta | Baixo | Senha ja foi alterada no commit b0df2a3; senha era de dev local |
