# C2.5 — DOM-SC path autenticado BLOCKED (histórico)

**Story original:** PE-C2-02  
**Atualização:** 2026-07-16 — **PE-C2-05** desbloqueia DOM/SC via **CIGA Dados público** (`ciga_ckan`).  
**Ver desbloqueio:** `docs/baseline/c2-domsc-ciga-dados-unblocked.md`

Este documento permanece como evidência do path **legado** `dom_sc` (API `diariomunicipal.sc.gov.br` com CPF/CNPJ/API key), que continua opcional e sem credenciais no `.env` local.

---

## Veredito (path legado `dom_sc` apenas)

| Campo | Valor |
|-------|--------|
| **Status path legado** | **BLOCKED** (sem credenciais) |
| **Status path canônico** | **UNBLOCKED** via `ciga_ckan` (PE-C2-05) |
| **Motivo legado** | Credenciais ausentes / vazias no `.env` |
| **Import** | OK (`scripts.crawl.dom_sc_crawler`) |
| **Dry-run monitor** | OK (não exercita auth) |
| **Crawl real** | Retorna `[]` sem chamar API autenticada |
| **Persistência** | Sem evidência de dados DOM-SC no inventário por source do smoke |

**Nenhum secret foi impresso.** Apenas presença/ausência e comprimento zero.

---

## Credenciais (presença apenas)

| Variável de ambiente | Presente no `.env` | Não-vazio |
|----------------------|--------------------|-----------|
| `DOM_SC_CPF` | chave existe | **NÃO** (len=0) |
| `DOM_SC_CNPJ` | chave existe | **NÃO** (len=0) |
| `DOM_SC_API_KEY` | chave existe | **NÃO** (len=0) |

### Validador central

```python
from scripts.crawl.credential_validator import validate_source_credentials
ok, missing = validate_source_credentials("dom_sc")
# ok == False
# missing inclui DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY (com descrições)
```

Logs observados (sem valores):

```text
Source 'dom_sc': required credential DOM_SC_CPF is missing or empty
Source 'dom_sc': required credential DOM_SC_CNPJ is missing or empty
Source 'dom_sc': required credential DOM_SC_API_KEY is missing or empty
[DOM-SC] Missing credentials — set DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY env vars
```

### Comportamento do crawler

Em `scripts/crawl/dom_sc_crawler.py`:

- Auth: HTTP Basic (`CPF:CNPJ`) + header `X-API-Key`
- Endpoint: `https://diariomunicipal.sc.gov.br/?r=remote/list`
- Se qualquer credencial vazia → warning + **`crawl()` retorna lista vazia** (não levanta exception)
- `DOM_SC_ENABLED` default true; flags de janela `DOM_SC_FULL_DAYS` / `DOM_SC_INCREMENTAL_DAYS` irrelevantes enquanto BLOCKED

Smoke:

```text
dom.crawl("incremental") → n=0
```

---

## O que está implementado (código) mas não exercitável

- Crawler REST v2 completo com paginação (`API_PAGE_SIZE=100`, `API_MAX_PAGES=20`)
- Transform para schema de bids + enrich de detalhe
- Integração no `monitor.py` registry (`dom_sc`)
- Gate de credenciais em `crawl_source` → status `skipped` / `missing_credentials` se monitor rodar mode real

Dry-run **não** valida credenciais (sai antes do crawl).

---

## Histórico / docs (contexto, não desbloqueio)

| Artefato | Nota |
|----------|------|
| `docs/workplans/opportunity-intelligence-truth-v1-plan.md` | Menciona `DOM_SC_*` “já no .env” — **desatualizado vs .env atual** (chaves vazias) |
| `docs/audits/sc-non-pncp-source-coverage-2026-07.md` | DOM-SC ACTIVE no código; depende das 3 env vars |
| Ops guide | SLA/timer DOM-SC planejados; sem evidência runtime autenticada nesta sessão |

---

## Desbloqueio (quando houver credencial)

1. Preencher `DOM_SC_CPF`, `DOM_SC_CNPJ`, `DOM_SC_API_KEY` no `.env` (ou secret store da VPS) — **sem commit de secrets**.  
2. Revalidar: `validate_source_credentials("dom_sc")` → `ok=True`.  
3. Smoke: `crawl("incremental")` com janela curta; se 401 → credencial inválida (ainda BLOCKED, causa diferente).  
4. Só então: monitor `--source dom_sc --mode incremental` + contagem no DB.  
5. Atualizar este arquivo de BLOCKED → OK/PARTIAL com evidência real.

---

## O que NÃO se afirma

- Que a API DOM-SC esteja fora do ar (não testada com auth).  
- Cobertura % de municípios SC via DOM-SC.  
- Que o código do crawler esteja quebrado (gate de credencial funciona como desenhado).

---

## Comandos reproduzíveis (sem vazar secrets)

```bash
python3 - <<'PY'
import os
from pathlib import Path
# load .env
for line in Path(".env").read_text().splitlines():
    line=line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    k,v=line.split("=",1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
from scripts.crawl.credential_validator import validate_source_credentials
ok, missing = validate_source_credentials("dom_sc")
print("ok=", ok)
print("missing_count=", len(missing))
for k in ("DOM_SC_CPF","DOM_SC_CNPJ","DOM_SC_API_KEY"):
    v=os.environ.get(k,"")
    print(k, "nonempty=", bool(v), "len=", len(v))
from scripts.crawl import dom_sc_crawler as d
print("crawl_n=", len(d.crawl("incremental")))
PY
```
