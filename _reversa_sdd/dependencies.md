# Dependências — Extra Consultoria

> Gerado pelo Scout em 2026-07-13

---

## 1. Linguagem e Runtime

| Componente | Versão | Fonte |
|------------|--------|-------|
| **Python** | 3.12 | `pyproject.toml` (target-version), `ruff` config |
| **pip** | — | `requirements.txt` |

---

## 2. Dependências Principais (requirements.txt)

### Core

| Pacote | Versão | Função |
|--------|--------|--------|
| `httpx` | >=0.28.1 | HTTP client async para crawlers |
| `requests` | >=2.32.0 | HTTP client síncrono |
| `openai` | >=1.55.0 | Integração GPT-4.1 Nano (classificação) |
| `psycopg2` | >=2.9.9 | Driver PostgreSQL |
| `python-dotenv` | >=1.0.0 | Variáveis de ambiente |
| `pyyaml` | >=6.0 | Parsing de configurações YAML |

### Geração de Documentos

| Pacote | Versão | Função |
|--------|--------|--------|
| `reportlab` | >=4.5.1 | Geração de PDFs (Big Four: consultoria, proposta, B2G, panorama) |
| `openpyxl` | >=3.1.5 | Geração de Excel |

### CLI

| Pacote | Versão | Função |
|--------|--------|--------|
| `rich` | >=13.0.0 | Formatação rica de terminal (tabelas, progress bars, cores) |

### Processamento de Dados

| Pacote | Versão | Função |
|--------|--------|--------|
| `lxml` | >=5.0.0 | Parsing XML/HTML rápido |
| `beautifulsoup4` | >=4.12.0 | Parsing HTML (crawlers) |
| `rapidfuzz` | >=3.0.0 | Fuzzy string matching (entity resolution) |

### Opcionais

| Pacote | Versão | Função | Status |
|--------|--------|--------|--------|
| `playwright` | >=1.40.0 | Automação browser (SICAF) | Comentado |
| `selenium` | >=4.15.0 | Automação browser (portais JS) | Comentado |
| `webdriver-manager` | >=4.0.0 | Gerenciamento ChromeDriver | Comentado |

---

## 3. Ferramentas de Desenvolvimento

| Ferramenta | Versão | Config | Função |
|------------|--------|--------|--------|
| **ruff** | 0.15.12 | `pyproject.toml` | Linter + formatter |
| **mypy** | — | `pyproject.toml` | Type checking (strict config) |
| **bandit** | — | `pyproject.toml` | Security scanning |
| **pytest** | — | `conftest.py` | Test framework |
| **pytest-cov** | — | — | Coverage |

### Regras Ruff Ativas

- `E` — pycodestyle errors
- `F` — pyflakes (logic errors)
- `I` — isort (import ordering)
- `N` — pep8-naming
- `W` — pycodestyle warnings
- `UP` — pyupgrade (modern Python idioms)

### Config mypy (Strict)

```toml
check_untyped_defs = true
warn_return_any = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
no_implicit_optional = true
strict_equality = true
```

---

## 4. Infraestrutura

| Componente | Versão | Uso |
|------------|--------|-----|
| **PostgreSQL** | 16 | Banco de dados principal |
| **PostGIS** | 3.4 | Extensão geoespacial |
| **Docker** | — | PostgreSQL para testes (`docker-compose.yml`) |
| **systemd** | — | Orquestração de crawlers/timers na VPS |
| **GitHub Actions** | — | CI/CD pipeline |

---

## 5. Integrações Externas

| Sistema | Tipo | Crawlers |
|---------|------|----------|
| **PNCP** (gov.br) | API REST | `pncp_crawler_adapter.py`, `pncp_contract.py`, `pncp_arp_crawler.py`, `pncp_pca_crawler.py` |
| **Compras.gov** | API REST | `compras_gov_crawler.py` |
| **TCE-SC** | Web scraping | `tce_sc_crawler.py` |
| **DOE-SC** | Web scraping | `doe_sc_crawler.py`, `doe_sc_selenium_crawler.py` |
| **DOM-SC** | Web scraping | `dom_sc_crawler.py` |
| **CIGA/CKAN** | API CKAN | `ciga_ckan_crawler.py` |
| **SC Compras** | Web scraping | `sc_compras_crawler.py` |
| **MIDES/BigQuery** | BigQuery API | `mides_bigquery_crawler.py` |
| **Portais de Transparência** | Web scraping | `transparencia_crawler.py` + templates |
| **IBGE** | API + cache local | `enricher.py` (geocodificação) |
| **OpenAI GPT-4.1 Nano** | API | `intel_llm_gate.py` (classificação) |
| **Supabase** | API REST | `supabase_client.py` |

---

## 6. Árvore de Dependências (Simplificada)

```
scripts/
├── crawl/          → httpx, requests, lxml, bs4, psycopg2, yaml, rapidfuzz
│   + clients/      → httpx (APIs tipadas)
│   + ingestion/    → psycopg2 (escrita no banco)
├── opportunity_intel/ → psycopg2, rich, yaml, httpx
├── contract_intel/ → psycopg2, rich, yaml
├── lib/            → rapidfuzz, psycopg2, httpx (puro Python, sem I/O pesado)
├── matching/       → rapidfuzz, psycopg2
├── reports/        → reportlab, openpyxl, psycopg2
├── fix/            → psycopg2, httpx, bs4
├── coverage/       → psycopg2
├── diagnose/       → psycopg2, httpx
└── intel_pipeline  → openai, psycopg2, rich, reportlab, openpyxl
```

---

## 7. Versionamento de Dependências

Todas as dependências têm versão mínima (`>=`) sem upper bound. Apenas `psycopg2` (não `psycopg2-binary`) é usado em produção.

---

## 8. Scripts de Setup

| Script | Função |
|--------|--------|
| `db/setup_db.sh` | Criação do banco local |
| `scripts/apply-migrations.sh` | Aplicação de migrations |
| `deploy/install.sh` | Instalação na VPS |
| `deploy/provision-vps.sh` | Provisionamento completo da VPS |
| `scripts/ci-check.sh` | Verificação pré-CI |
| `scripts/backup-database.sh` | Backup do PostgreSQL |
| `scripts/restore-database.sh` | Restore do PostgreSQL |
| `scripts/verify-schema-divergence.sh` | Verificação de divergência schema |
