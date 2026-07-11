# Dependências — Extra Consultoria

> Gerado pelo Scout em 2026-07-11T12:00:00Z

---

## Dependências Python (requirements.txt)

### Core

| Pacote | Versão | Tipo | Descrição |
|--------|--------|------|-----------|
| `httpx` | >=0.28.1 | HTTP | Cliente HTTP moderno com suporte async |
| `openai` | >=1.55.0 | LLM | SDK OpenAI para GPT-4.1-nano |
| `psycopg2-binary` | >=2.9.9 | Database | Driver PostgreSQL nativo |
| `python-dotenv` | >=1.0.0 | Config | Carrega .env |
| `pyyaml` | >=6.0 | Config | Parse de YAML (setores, configs) |

### PDF Generation

| Pacote | Versão | Tipo | Descrição |
|--------|--------|------|-----------|
| `reportlab` | >=4.5.1 | PDF | Geração de PDFs (Big Four aesthetic) |

### Excel

| Pacote | Versão | Tipo | Descrição |
|--------|--------|------|-----------|
| `openpyxl` | >=3.1.5 | Excel | Leitura/escrita de .xlsx |

### CLI

| Pacote | Versão | Tipo | Descrição |
|--------|--------|------|-----------|
| `rich` | >=13.0.0 | Terminal | Terminal UI (tabelas, progress bars, cores) |

### Data Processing

| Pacote | Versão | Tipo | Descrição |
|--------|--------|------|-----------|
| `lxml` | >=5.0.0 | XML/HTML | Parsing de HTML (portais) |
| `beautifulsoup4` | >=4.12.0 | HTML | Web scraping |
| `rapidfuzz` | >=3.0.0 | Fuzzy | String matching (fallback: difflib) |

### Opcional

| Pacote | Versão | Tipo | Descrição |
|--------|--------|------|-----------|
| `playwright` | >=1.40.0 | Browser | SICAF checking (comentado, não instalado) |

---

## Dependências Externas (APIs e Serviços)

### Fontes de Dados de Licitações

| Serviço | URL Base | Tipo | Cobertura | Autenticação |
|---------|----------|------|-----------|--------------|
| PNCP API | `https://pncp.gov.br/api/consulta/v1` | REST | Nacional | Pública |
| PNCP Files | `https://pncp.gov.br/api/pncp/v1` | REST | Documentos | Pública |
| DOM-SC | `https://www.diariomunicipal.sc.gov.br` | Portal | ~280 municípios SC | API Key |
| PCP v2 | `https://compras.api.portaldecompraspublicas.com.br/v2` | REST | 100+ municípios SC | Pública |
| ComprasGov v3 | `https://dadosabertos.compras.gov.br` | REST | Órgãos federais SC | Pública |

### Enriquecimento

| Serviço | URL Base | Tipo | Dados |
|---------|----------|------|------|
| BrasilAPI | `https://brasilapi.com.br/api/cnpj/v1/` | REST | CNPJ, razão social, CNAE |
| IBGE API | `https://servicodados.ibge.gov.br/api/v1/` | REST | Municípios, códigos IBGE |
| SICAF | Portal ComprasNet | Web | Sanções (opcional, requer Playwright) |

### LLM

| Serviço | Modelo | Uso | Timeout |
|---------|--------|-----|---------|
| OpenAI API | `gpt-4.1-nano` | Classificação de editais, análise | 10s |
| DeepSeek API | (configurável) | Fallback LLM | — |
| OpenRouter | (configurável) | Multi-model routing | — |

---

## Infraestrutura

### Ambiente de Produção

| Componente | Tecnologia | Local |
|-----------|-----------|-------|
| Servidor | Ubuntu 24.04 (Hetzner VPS) | Alemanha (Nuremberg) |
| Banco de Dados | PostgreSQL 17 | Hetzner VPS (porta 5432) |
| Scheduler | systemd timers (13 timers) | Hetzner VPS |
| Runtime | Python 3.12 | Hetzner VPS |
| Acesso | SSH (WSL → Hetzner) | — |

### Serviços Cloud (configurados, não essenciais)

| Serviço | Uso | Status |
|---------|-----|--------|
| Supabase | Database/Storage opcional | Configurado, não usado |
| Sentry | Error tracking | Configurado |
| Railway | Deploy alternativo | Configurado |
| Vercel | Deploy alternativo | Configurado |
| ClickUp | Project management | Configurado |
| N8N | Workflow automation | Configurado |
| GitHub | Version control | Ativo |
| Exa | Web search (agentes) | Configurado |
| Stripe | Pagamentos (não usado) | Configurado |

---

## Sistema Operacional e Ferramentas

| Ferramenta | Uso |
|-----------|-----|
| systemd | Gerenciamento de timers e serviços |
| PostgreSQL 17 | DataLake (psycopg2 acesso direto) |
| Python 3.12 | Runtime principal |
| pip | Gerenciador de pacotes |
| Git + GitHub | Version control |
| WSL2 | Ambiente de desenvolvimento (Windows) |

---

## Grafo de Dependências Internas

```
monitor.py
  ├── pncp_crawler_adapter.py → PNCP API
  ├── dom_sc_crawler.py → DOM-SC
  ├── pcp_crawler.py → PCP API
  ├── compras_gov_crawler.py → ComprasGov API
  ├── sc_compras_crawler.py → SC Compras
  ├── contracts_crawler.py → PNCP Contracts API
  ├── transparencia_crawler.py → Portais Transparência
  ├── tce_sc_crawler.py → TCE-SC ESFINGE
  ├── enricher.py → BrasilAPI + IBGE
  ├── sanctions.py → SICAF (opcional)
  ├── transformer.py (normalização)
  ├── loader.py (upsert PostgreSQL)
  ├── name_normalizer.py (lib)
  └── checkpoint.py (resume)

intel_pipeline.py
  ├── intel_collect.py → DataLake
  ├── intel_enrich.py → BrasilAPI
  ├── intel_llm_gate.py → OpenAI
  ├── intel_extract_docs.py → PNCP Files API
  ├── intel_analyze.py → OpenAI
  ├── intel_validate.py
  ├── intel_report.py → PDF
  ├── intel_excel.py → Excel
  └── intel_sector_loader.py → sectors_config.yaml

panorama.py
  ├── datalake_helper.py → PostgreSQL
  └── intel_excel.py → Excel

local_datalake.py
  └── datalake_helper.py → PostgreSQL
```

---

## Versões dos Runtimes

| Runtime | Versão | Fixa? |
|---------|--------|-------|
| Python | 3.12 | Sim (.python-version) |
| PostgreSQL | 17 | Sim (Hetzner) |
| Ubuntu | 24.04 | Sim (Hetzner) |
| AIOX | 5.2.9 | Sim (.env) |
