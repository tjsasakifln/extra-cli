# Handoff — Extra Consultoria (2026-07-10)

**De:** @pm (Morgan) → **Para:** @dev (Dex) — próxima sessão

---

## 1. Estado Atual

### 1.1 Repositório
- **URL:** `https://github.com/tjsasakifln/extra-consultoria` (privado)
- **Branch:** `main`
- **Commits:** 9 (todos com `Co-Authored-By: Claude Opus 4.8`)
- **Push:** `AIOX_ACTIVE_AGENT=devops git push origin main` (hook bloqueia sem env var)
- **Arquivos:** 83 de projeto + AIOX framework (`.aiox-core/`)

### 1.2 Infra Local
- **PostgreSQL 18:** porta `5433`, user `postgres`, senha `smartlic_local`
- **Database:** `pncp_datalake` — 9 migrations aplicadas, 2.085 órgãos seedados
- **DSN:** `postgresql://postgres@127.0.0.1:5433/pncp_datalake`
- **Python:** 3.12, pacotes instalados: `psycopg2-binary`, `httpx`, `openpyxl`, `pyyaml`, `python-dotenv`

### 1.3 Pipeline Verificado
```
PNCP API → crawl (115 records SC) → transform → upsert → entity match → coverage
```
- ✅ PNCP crawler funcional (parâmetros corretos: `codigoModalidadeContratacao`, datas YYYYMMDD)
- ✅ RPC upsert com dedup por content_hash
- ✅ Entity matching: `orgao_cnpj[:8]` ↔ `sc_public_entities.cnpj_8`
- ✅ Coverage triggers (INSERT + UPDATE) com COALESCE anti-null
- ⚠️ Apenas 1 entidade matched (crawl inicial pequeno — acumula com crawls diários)

### 1.4 Database Schema (8 tabelas)

| Tabela | Registros | Nota |
|--------|-----------|------|
| `pncp_raw_bids` | 1 | Multi-source unificado, `source` field |
| `pncp_supplier_contracts` | 0 | Ainda sem crawl de contratos |
| `enriched_entities` | 0 | Cache BrasilAPI/IBGE |
| `sc_public_entities` | 2.085 | 1.093 raio 200km, 992 fora, 604 sem coordenadas |
| `ingestion_checkpoints` | 0 | Resumable crawl |
| `ingestion_runs` | 0 | Audit trail |
| `entity_coverage` | 1 | Tracking por entidade × source |

### 1.5 Distribuição das Entidades por Natureza Jurídica (raio 200km)

| Natureza Jurídica | Total | Fonte Esperada |
|---|---|---|
| Órgão Executivo Municipal | 179 | DOM-SC |
| Fundação Pública Municipal | 119 | DOM-SC |
| Órgão Executivo Estadual | 99 | PNCP + DOE-SC |
| Órgão Legislativo Municipal (Câmaras) | 98 | DOM-SC |
| Município (Prefeitura) | 95 | DOM-SC + PCP |
| Órgão Judiciário Estadual | 78 | PNCP + DOE-SC |
| Fundo Estadual | 61 | PNCP + DOE-SC |
| Autarquia Municipal | 61 | DOM-SC |
| Sociedade de Economia Mista | 59 | PNCP + DOE-SC |
| Autarquia Federal | 57 | ComprasGov |
| Órgão Executivo Federal | 44 | ComprasGov + PNCP |
| Consórcio Público | 37 | DOM-SC + PNCP |
| Empresa Pública | 34 | PNCP + DOE-SC |
| Autarquia Estadual | 15 | PNCP + DOE-SC |
| Serviço Social Autônomo | 15 | PNCP |

**513 entidades em "SANTA CATARINA" (município = sede do governo estadual)** — são órgãos estaduais publicando no DOE-SC.

---

## 2. PRÓXIMA FASE: Validação de Cobertura + Crawlers

### 2.1 Passo 1 — Medir cobertura real do PNCP

Executar crawl amplo e verificar quantas entidades o PNCP cobre:

```bash
cd "/mnt/d/extra consultoria"

# Crawl amplo: 3 UFs × modalidades 4,5,6,7 × 30 dias × 20 páginas
export LOCAL_DATALAKE_DSN="postgresql://postgres@127.0.0.1:5433/pncp_datalake"
export PNCP_MAX_PAGES=20
export INGESTION_UFS="SC,PR,RS"
export INGESTION_MODALIDADES="4,5,6,7"
export INGESTION_DATE_RANGE_DAYS=30

python3 -c "
import sys, os, json; sys.path.insert(0, '.')
os.environ.update({k:v for k,v in os.environ.items() if k.startswith('PNCP') or k.startswith('INGESTION') or k.startswith('LOCAL')})
import psycopg2
from scripts.crawl.pncp_crawler_adapter import crawl, transform

raw = crawl(mode='full')
records = transform(raw)
for r in records: r['source']='pncp'

conn = psycopg2.connect(os.environ['LOCAL_DATALAKE_DSN'])
cur = conn.cursor()
for i in range(0, len(records), 500):
    cur.execute('SELECT * FROM upsert_pncp_raw_bids(%s)', (json.dumps(records[i:i+500]),))
    conn.commit()

# Entity matching
cur.execute('SELECT id, cnpj_8 FROM sc_public_entities')
entities = {r[1]: r[0] for r in cur.fetchall() if r[1]}
cur.execute(\"SELECT pncp_id, orgao_cnpj FROM pncp_raw_bids WHERE matched_entity_id IS NULL AND orgao_cnpj IS NOT NULL\")
for pncp_id, cnpj in cur.fetchall():
    c8 = ''.join(c for c in (cnpj or '') if c.isdigit())[:8]
    if c8 in entities:
        cur.execute('UPDATE pncp_raw_bids SET matched_entity_id=%s WHERE pncp_id=%s', (entities[c8], pncp_id))
conn.commit()
cur.close(); conn.close()
print('Done. Run: python scripts/crawl/monitor.py --report-coverage')
"

# Verificar cobertura REAL
python scripts/crawl/monitor.py --dsn "$LOCAL_DATALAKE_DSN" --report-coverage
```

**Objetivo:** Saber exatamente quantas entidades o PNCP NÃO cobre. O gap entre o total (2.085) e as cobertas pelo PNCP é o que precisa de crawlers adicionais.

### 2.2 Passo 2 — Criar DOM-SC Crawler (MAIOR IMPACTO)

DOM-SC (`diariomunicipal.sc.gov.br`) cobre ~280 municípios SC com editais publicados em diário oficial municipal. É a fonte #1 para entidades municipais.

**Arquivo fonte:** `scripts/crawl/dom_sc_crawler.py` (copiado do smartlic, NÃO adaptado)

**O que precisa:**
1. Remover dependências de ARQ/Redis/Supabase (mesmo padrão do `pncp_crawler_adapter.py`)
2. Implementar interface `crawl(mode) → list[dict]` + `transform(records) → list[dict]`
3. Schema de saída compatível com `upsert_pncp_raw_bids` (campo `source='dom_sc'`)

**API DOM-SC:**
- Base: `https://www.diariomunicipal.sc.gov.br`
- Autenticação: API key (env var `DOM_SC_API_KEY`)
- Formato: HTML (precisa parser BeautifulSoup/lxml)
- Endpoints: pesquisa por município + data

**Investigação necessária (usar Playwright MCP):**
```
Navegar para https://www.diariomunicipal.sc.gov.br
Entender estrutura do site, busca de licitações
Identificar se há API REST ou só HTML scraping
```

### 2.3 Passo 3 — Criar PCP v2 Crawler

Portal de Compras Públicas v2 — usado por ~100+ municípios SC.

**Arquivo fonte:** `scripts/crawl/pcp_crawler.py` (copiado do `portal_compras_client.py`)

**API PCP v2:**
- Base: `https://compras.api.portaldecompraspublicas.com.br/v2`
- Open API, sem autenticação
- Endpoint: `/licitacao/processos` com filtros por UF, município, data

### 2.4 Passo 4 — Criar ComprasGov v3 Crawler

Para órgãos federais em SC (44 executivos + 57 autarquias = 101 entidades).

**Arquivo fonte:** `scripts/crawl/compras_gov_crawler.py`

**API ComprasGov:**
- Base: `https://dadosabertos.compras.gov.br`
- Open data, sem autenticação

### 2.5 Passo 5 — Investigar TCE-SC e-Sfinge (AGREGADOR)

Se acessível, cobre ~96% das entidades de uma vez. Usar **Exa MCP** e **Playwright MCP**:

```
1. WebSearch: "TCE-SC e-Sfinge API dados abertos licitações"
2. Playwright: navegar para https://e-sfinge.tce.sc.gov.br
3. Identificar: API REST? Scraping HTML? Autenticação?
4. Se viável → criar scripts/crawl/tce_sc_crawler.py
```

### 2.6 Passo 6 — Portal Transparência Genérico (GAP FILL)

Para municípios não cobertos por nenhuma fonte acima. Usar **Selenium/Playwright** para scraping.

Plataformas comuns em SC:
| Plataforma | Padrão URL | Municípios estimados |
|-----------|-----------|---------------------|
| Betha | `{municipio}.atende.net/transparencia` | ~80 |
| Ipam | `{municipio}.ipm.org.br/transparencia` | ~50 |
| E-gov | `{municipio}.e-gov.betha.com.br` | ~40 |
| Domínio próprio | variável | ~125 |

**Estratégia:**
1. Para cada município sem cobertura após passos 2-5
2. Detectar plataforma (headless request → analisar HTML)
3. Aplicar template de scraping específico da plataforma
4. Extrair licitações → transformar → upsert

### 2.7 Passo 7 — Pipeline Intel para CNPJ da Extra Construtora

```bash
python scripts/intel_pipeline.py \
  --cnpj <CNPJ_EXTRA_CONSTRUTORA> \
  --ufs SC \
  --dias 90 \
  --top 20
```

**Dependências:** `OPENAI_API_KEY` no `.env`, datalake populado.

---

## 3. Arquivos que Precisam de Adaptação

### Crawlers (interface monitor.py)
Cada crawler precisa expor duas funções:
```python
def crawl(mode: str) -> list[dict]:        # coleta dados brutos da fonte
def transform(records: list[dict]) -> list[dict]:  # normaliza para schema pncp_raw_bids
```

| Arquivo | Estado | Trabalho estimado |
|---------|--------|-------------------|
| `scripts/crawl/pncp_crawler_adapter.py` | ✅ FUNCIONAL | — |
| `scripts/crawl/dom_sc_crawler.py` | ❌ Source code, não adaptado | 3-4h |
| `scripts/crawl/pcp_crawler.py` | ❌ Source code, não adaptado | 2-3h |
| `scripts/crawl/compras_gov_crawler.py` | ❌ Source code, não adaptado | 2-3h |
| `scripts/crawl/contracts_crawler.py` | ❌ Source code, não adaptado | 2h |
| `scripts/crawl/tce_sc_crawler.py` | 🆕 NÃO EXISTE | 4-8h (investigação + dev) |
| `scripts/crawl/transparencia_crawler.py` | 🆕 NÃO EXISTE | 6-10h (múltiplas plataformas) |
| `scripts/crawl/doe_sc_crawler.py` | 🆕 NÃO EXISTE | 3-4h |

### Pipeline Intel (imports/paths)
| Arquivo | Problema |
|---------|----------|
| `scripts/intel_collect.py` | OK (paths corrigidos) |
| `scripts/intel_enrich.py` | Pode ter refs a `backend.*` |
| `scripts/intel_analyze.py` | OK |
| `scripts/intel_extract_docs.py` | OK |
| `scripts/intel_report.py` | OK (branding corrigido) |
| `scripts/intel_excel.py` | OK |
| `scripts/collect_report_data.py` | Arquivo grande (9.862 linhas), pode ter refs a `backend.*` |
| `scripts/local_datalake.py` | OK |
| `scripts/datalake_helper.py` | OK (adaptado) |

---

## 4. Comandos Úteis

```bash
# Conexão DB
psql -h 127.0.0.1 -p 5433 -U postgres -d pncp_datalake

# Crawl PNCP
python scripts/crawl/monitor.py --dsn "postgresql://postgres@127.0.0.1:5433/pncp_datalake" --source pncp --mode full

# Coverage report
python scripts/crawl/monitor.py --dsn "postgresql://postgres@127.0.0.1:5433/pncp_datalake" --report-coverage

# Panorama mercado
python scripts/reports/panorama.py --dsn "postgresql://postgres@127.0.0.1:5433/pncp_datalake" --output-excel

# DataLake stats
python scripts/local_datalake.py stats

# Git push (hook bypass)
AIOX_ACTIVE_AGENT=devops git push origin main

# Verificar entidades sem cobertura no raio 200km
psql -h 127.0.0.1 -p 5433 -U postgres -d pncp_datalake -c "
SELECT e.razao_social, e.cnpj_8, e.municipio, e.natureza_juridica
FROM sc_public_entities e
WHERE e.raio_200km = TRUE AND e.is_active = TRUE
  AND e.id NOT IN (
    SELECT entity_id FROM entity_coverage WHERE is_covered = TRUE
  )
ORDER BY e.municipio, e.razao_social
LIMIT 50;
"
```

---

## 5. Métricas de Sucesso para Próxima Sessão

- [ ] Coverage report mostra >10% cobertura com PNCP (após crawl amplo)
- [ ] `dom_sc_crawler.py` adaptado com interface `crawl()`/`transform()`
- [ ] `pcp_crawler.py` adaptado
- [ ] `tce_sc_crawler.py` investigado (viabilidade confirmada ou descartada)
- [ ] Pipeline intel executado para CNPJ da Extra Construtora
- [ ] Hetzner VPS provisionado (se credenciais disponíveis)
- [ ] Número real de entidades NÃO cobertas pelo PNCP identificado

---

## 6. Princípios (CLAUDE.md)

- **P1:** Executar, não delegar. Usuário não sai do terminal.
- **P3:** Web Search via Exa MCP (não WebSearch nativo).
- **P6:** Subagents obrigatórios para tarefas paralelizáveis.
- **Git push:** `AIOX_ACTIVE_AGENT=devops git push origin main`
- **Idioma:** Português Brasil com ortografia completa.
