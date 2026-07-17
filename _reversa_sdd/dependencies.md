# Dependências — Extra Consultoria

> 🟢 **CONFIRMADO** — re-extração Scout 2026-07-17  
> Fontes: `requirements.txt`, `pyproject.toml`, `docker-compose.yml`, `.github/workflows/ci.yml`

---

## 1. Runtime (requirements.txt)

### Core HTTP / API

| Pacote | Versão | Uso |
|--------|--------|-----|
| httpx | >=0.28.1 | Cliente HTTP moderno (crawlers async/sync) |
| requests | >=2.32.0 | Cliente HTTP legado / integrações |
| openai | >=1.55.0 | LLM (intel pipeline, gates) |

### Dados / banco

| Pacote | Versão | Uso |
|--------|--------|-----|
| psycopg2 | >=2.9.9 | PostgreSQL (produção; binary só em dev/test) |
| python-dotenv | >=1.0.0 | Carregamento de `.env` |
| pyyaml | >=6.0 | Configs YAML (setores, SLA, transparência) |

### Processamento e matching

| Pacote | Versão | Uso |
|--------|--------|-----|
| lxml | >=5.0.0 | Parse HTML/XML |
| beautifulsoup4 | >=4.12.0 | Scraping HTML |
| rapidfuzz | >=3.0.0 | Fuzzy match de nomes (fallback difflib) |

### Relatórios e CLI

| Pacote | Versão | Uso |
|--------|--------|-----|
| reportlab | >=4.5.1 | PDF executivo |
| openpyxl | >=3.1.5 | Excel |
| rich | >=13.0.0 | Terminal / CLI |

### Opcionais (comentados)

| Pacote | Versão | Quando |
|--------|--------|--------|
| playwright | >=1.40.0 | SICAF / automação browser |
| selenium | >=4.15.0 | Portais JS / DOE Selenium |
| webdriver-manager | >=4.0.0 | ChromeDriver automático |
| psycopg2-binary | >=2.9.9 | **Apenas** dev/test — não produção |

---

## 2. Infraestrutura de dados

| Componente | Versão / imagem | Fonte |
|------------|-----------------|-------|
| PostgreSQL + pgvector | `pgvector/pgvector:pg16` | docker-compose.yml |
| PostGIS-compatible stack | incluído na imagem | migrations (extensões) |
| Supabase | schema dump + migrations | `supabase/` |

**Variáveis críticas (`.env.example`):**

- `DATABASE_URL` / `LOCAL_DATALAKE_DSN`
- `DATALAKE_BACKEND`, `DATALAKE_QUERY_ENABLED`
- `PNCP_BASE`, `PNCP_MAX_PAGES`, `PNCP_PAGE_SIZE`, timeouts/retries
- `INGESTION_UFS`, `INGESTION_MODALIDADES`, ranges e delays

---

## 3. Ferramentas de desenvolvimento e CI

| Ferramenta | Config | Papel no CI |
|------------|--------|-------------|
| **ruff** | `pyproject.toml` | Lint fail-closed em `scripts/` |
| **mypy** | boundary crítica listada no workflow | Type check fail-closed |
| **pytest** | `tests/` + markers | Critical readiness suite |
| **bandit** | ruleset S no ruff + job dedicado | Segurança |
| **pip-audit** | job CI | Vulnerabilidades de deps |

### Ruff (resumo)

- target: Python 3.12  
- line-length: 120  
- selects: E, F, I, N, S, W, UP  
- ignores notáveis: E501; per-file ignores em testes e scripts legados com N/F/E402

---

## 4. Gerenciador de pacotes

| Item | Valor |
|------|-------|
| Gerenciador | **pip** |
| Lockfile | 🔴 não há `requirements.lock` / poetry.lock (lacuna operacional) |
| Python | 3.12 (CI `PYTHON_VERSION: "3.12"`) |

---

## 5. Integrações externas (dependências de rede)

| Sistema | Protocolo | Credencial / config |
|---------|-----------|---------------------|
| PNCP | HTTPS REST | público + rate limits env |
| Compras.gov | HTTPS | público |
| Portais SC (DOE/DOM/Compras/TCE/CIGA) | HTTPS scrape/API | cookies/headers/templates |
| BigQuery MIDES | API Google | `config/mides-bigquery-sa.json` (SA) |
| OpenAI | HTTPS | API key env |
| Supabase | HTTPS / Postgres | URL + keys env |
| IBGE | HTTPS | cache local |

---

## 6. Dependências operacionais (não-Python)

| Item | Uso |
|------|-----|
| systemd | 25 services / 24 timers de crawl e manutenção |
| Docker Engine | DB local de teste/prod data |
| GitHub Actions | CI em push/PR para `main` |
| SSH / VPS | deploy (`ec-prod` em runbooks) |

---

## 7. Grafo de dependência lógica (alto nível)

```
config ──► crawl / clients / ingestion ──► db (Postgres)
                │
                ├──► matching / lib / schema
                │         │
                ├──► source_registry / coverage / opportunity_intel
                │         │
                ├──► workspace / buyer_intel / contract_intel
                │         │
                └──► reports / root_scripts (gates, intel_pipeline)
                              │
                              └──► ops / deploy (systemd) / CI
```

---

## 8. Riscos de dependência 🟡/🔴

| Risco | Severidade | Nota |
|-------|------------|------|
| Sem lockfile de pip | 🟡 INFERIDO | builds CI podem driftar entre runs |
| Selenium/Playwright opcionais | 🟢 | crawlers JS degradam sem deps instaladas |
| SA BigQuery em `config/` | 🟡 | arquivo listado no inventário — validar se é placeholder/gitignored em prod |
| psycopg2 vs binary | 🟢 | documentado: binary só dev/test |

---

## 9. Artefatos relacionados

- Inventário: `_reversa_sdd/inventory.md`  
- Superfície: `.reversa/context/surface.json`  
- Schema detalhado: fase Data Master / Architect (ERD)
