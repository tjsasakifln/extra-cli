# Dependências — Extra Consultoria

> Atualizado pelo Scout em 2026-07-11T19:00:00Z (re-scout pós commit e9729e1)

---

## Python (pip + requirements.txt)

| Pacote | Versão | Categoria | Uso |
|--------|--------|-----------|-----|
| httpx | >=0.28.1 | HTTP Client | Chamadas síncronas/assíncronas para APIs externas (PNCP, PCP, ComprasGov) |
| openai | >=1.55.0 | LLM | Classificação de licitações via GPT-4.1-nano (intel-analyze) |
| psycopg2-binary | >=2.9.9 | Database | Conexão PostgreSQL (todos os crawlers, datalake, pipeline) |
| python-dotenv | >=1.0.0 | Config | Carregamento de .env |
| pyyaml | >=6.0 | Config | Parsing de YAMLs de setores e configuração |
| reportlab | >=4.5.1 | PDF | Geração de propostas comerciais (generate_proposta_pdf) |
| openpyxl | >=3.1.5 | Excel | Geração de planilhas (intel-excel, relatórios) |
| rich | >=13.0.0 | CLI | Tabelas, progress bars, formatação de terminal |
| lxml | >=5.0.0 | HTML/XML | Parsing de páginas web (crawlers web scraping) |
| beautifulsoup4 | >=4.12.0 | HTML | Parsing de HTML (complementar ao lxml) |
| rapidfuzz | >=3.0.0 | Fuzzy Matching | Casamento de nomes de entidades (entity_matcher, enricher) |

### Opcional (comentado)

| Pacote | Versão | Motivo |
|--------|--------|--------|
| playwright | >=1.40.0 | SICAF checking (sanctions.py) — requer browser |

---

## Dev Tools (pyproject.toml)

| Ferramenta | Versão/Alvo | Configuração | Propósito |
|------------|-------------|--------------|-----------|
| ruff | py312 | lint.select: E,F,I,N,W,UP | Lint + formatação |
| mypy | py312 | strict (check_untyped_defs, disallow_untyped_defs, strict_equality) | Type checking |
| pytest | — | testpaths: tests, addopts: --cov=scripts | Testes + coverage |
| pytest-cov | — | html: docs/td-001/coverage-reports/ | Relatórios HTML de cobertura |

---

## Runtime

| Componente | Versão | Local |
|------------|--------|-------|
| Python | 3.12 | .python-version |
| PostgreSQL | 17 | Hetzner VPS (self-hosted) |
| Ubuntu | 24.04 | Hetzner VPS |

---

## Mapa de Dependências entre Módulos

```
crawl/
├── httpx (sync + async HTTP)
├── psycopg2-binary (loader.py → PostgreSQL)
├── lxml + beautifulsoup4 (web scraping crawlers)
├── rapidfuzz (enricher.py → entity matching)
├── lib/ (name_normalizer)
└── config/ (settings, sectors_config, transparencia_config)

intel/
├── subprocess.run → crawl/monitor.py (⚠️ acoplamento via CLI, não import)
├── httpx (chamadas IBGE, BrasilAPI)
├── openai (GPT-4.1-nano classificação)
├── psycopg2-binary (leitura/escrita DataLake)
├── openpyxl (intel-excel)
├── reportlab (intel-report → PDF)
├── rapidfuzz (entity matching)
├── lib/ (constants, doc_templates, intel_logging)
├── matching/ (entity_matcher)
└── config/ (settings, sectors)

reports/
├── psycopg2-binary (consulta PostgreSQL)
├── openpyxl (export Excel)
├── rich (output CLI)
└── lib/ (victory_profile, bid_simulator)

lib/
├── rapidfuzz (name_normalizer)
└── config/ (settings)

matching/
├── rapidfuzz (fuzzy string matching)
└── psycopg2-binary (consulta entidades)

B2G scripts/
├── psycopg2-binary (consulta DataLake)
├── httpx (APIs externas)
├── openpyxl (Excel)
├── reportlab (PDF)
└── lib/ (cost_estimator, victory_profile, bid_simulator)
```

---

## Integrações Externas (runtime)

| API | URL Base | Auth | Módulos Consumidores |
|-----|----------|------|---------------------|
| PNCP API v1 | https://pncp.gov.br/api/consulta/v1 | Pública | crawl (pncp_crawler, contracts_crawler, bids_crawler) |
| PCP v2 | https://compras.api.portaldecompraspublicas.com.br/v2 | Pública | crawl (pcp_crawler) |
| ComprasGov v3 | https://dadosabertos.compras.gov.br | Pública | crawl (compras_gov_crawler) |
| DOM-SC | https://www.diariomunicipal.sc.gov.br | API Key | crawl (dom_sc_crawler) |
| DOE-SC | https://www.doe.sc.gov.br | Pública | crawl (doe_sc_crawler) |
| TCE-SC | Portal ESFINGE | Pública | crawl (tce_sc_crawler) |
| Transparência | Portal SC | Pública | crawl (transparencia_crawler) |
| OpenAI | https://api.openai.com/v1 | API Key | intel (intel-analyze) |
| BrasilAPI | https://brasilapi.com.br | Pública | crawl (enricher), intel (intel-enrich) |
| IBGE | https://servicodados.ibge.gov.br | Pública | crawl (enricher), intel (intel-enrich) |

---

## Dependências de Infraestrutura

| Recurso | Provedor | Tipo |
|---------|----------|------|
| VPS | Hetzner | Ubuntu 24.04 |
| PostgreSQL | Self-hosted | Banco principal |
| systemd | OS | Orquestração de crawlers (18 timers) |
| fail2ban | OS | Proteção de acesso |
| ufw | OS | Firewall |
| Supabase | Self-hosted? | Camada adicional de migrations |

---

## Alertas do Scout

1. **httpx sem version pin exato** — `>=0.28.1` permite breaking changes em minor updates.
2. **psycopg2-binary em produção** — psycopg2-binary é recomendado apenas para dev; produção deve usar psycopg2 compilado.
3. **playwright comentado** — sanctions.py (SICAF) depende de Playwright mas está comentado no requirements.txt.
4. **Duplicação kebab/snake_case** — 10 scripts duplicados. `intel_pipeline.py` importa snake_case, mas existem versões kebab-case idênticas.
5. **subprocess.run** — `intel_pipeline.py` chama scripts via `subprocess.run()` em vez de importar funções. Acoplamento frágil via CLI args.
