# Dependências — Extra Consultoria

> 🟢 **CONFIRMADO** — Scout re-extração 2026-07-27 | HEAD `ffbb9608`  
> Fontes: `requirements.txt`, `pyproject.toml`, `Makefile`, Dockerfiles/compose, CI

---

## 1. Runtime Python (requirements.txt)

| Pacote | Versão | Uso |
|--------|--------|-----|
| httpx | ≥0.28.1 | HTTP cliente moderno (crawlers/APIs) |
| requests | ≥2.32.0 | HTTP legado / compat |
| openai | ≥1.55.0 | Classificação e intel LLM |
| psycopg2 | ≥2.9.9 | PostgreSQL (produção; binary só dev/test) |
| python-dotenv | ≥1.0.0 | Env local |
| pyyaml | ≥6.0 | Configs YAML |
| reportlab | ≥4.5.1 | PDF (reports / propostas) |
| openpyxl | ≥3.1.5 | Excel |
| rich | ≥13.0.0 | CLI UX |
| lxml | ≥5.0.0 | Parse HTML/XML |
| beautifulsoup4 | ≥4.12.0 | Scraping |
| rapidfuzz | ≥3.0.0 | Fuzzy match (fallback difflib) |
| prometheus_client | ≥0.20.0 | Métricas |
| hypothesis | ≥6.100.0 | Property-based / adversarial (budget) |

### Opcionais (comentados)

| Pacote | Uso se habilitado |
|--------|-------------------|
| playwright | SICAF checking |
| selenium + webdriver-manager | Portais JS (FEAT-2.4) |

---

## 2. Tooling de qualidade (pyproject.toml)

| Ferramenta | Config | Notas |
|------------|--------|-------|
| **ruff** | target py312, line 120 | E/F/I/N/S/W/UP; S=bandit rules |
| **mypy** | python 3.12, strict-ish | disallow_untyped_defs; overrides para 3rd-party e modules legados |
| **pytest** | via Makefile / CI | unit + integration markers |

---

## 3. Infraestrutura

| Componente | Versão / imagem | Fonte |
|------------|-----------------|-------|
| PostgreSQL + pgvector | `pgvector/pgvector:pg16` | `docker-compose.yml`, `docker-compose.local.yml` (W006 unificado) |
| Docker Compose | local + prod overlays | `docker-compose.yml`, `docker-compose.local.yml` |
| Python CI | 3.12 | `.github/workflows/ci.yml` |
| systemd | services/timers | `deploy/systemd/` |

---

## 4. Gerenciadores e entry de build

| Item | Detalhe |
|------|---------|
| Package manager | **pip** (`requirements.txt`) |
| Project meta | `pyproject.toml` (tooling, não packaging app) |
| Make | Targets canônicos: golden-path, extra-weekly, resilience, campaign gates, lint, test |
| Shell helpers | `scripts/bootstrap_local.sh`, `scripts/apply-migrations.sh`, deploy scripts |

---

## 5. Dependências externas (serviços)

| Serviço | Dependência de runtime | Fail mode |
|---------|------------------------|-----------|
| PNCP API | Rede + HTTP | Crawl/resilience fail-closed + DLQ |
| Portais municipais/SC | Rede + HTML | Adapters por fonte |
| OpenAI API | `OPENAI_API_KEY` | Gates LLM / fallback documentado no domínio |
| PostgreSQL DSN | `LOCAL_DATALAKE_DSN` / prod DSN | Scripts exigem DSN explícito |
| GitHub Actions | Repo remoto | PR gates |

---

## 6. Dependências de monorepo (não-Python de produto)

| Área | Notas |
|------|-------|
| AIOX / `.aiox-core` | Framework de agentes — não é runtime de produção B2G |
| Reversa / `.reversa` | Extração de specs — output em `_reversa_sdd/` |
| Squads / tools | `tools/dod_controller.py`, squads de campanha |

---

## 7. Mudanças relevantes desde 2026-07-17

| Mudança | Impacto |
|---------|---------|
| Hypothesis no requirements | Suite adversarial de budget_audit |
| Crescimento de ops/CONFENGE | Mais scripts de gate sem novas libs major |
| ORPT reports | Continua reportlab + openpyxl como stack de entrega |
| CI dual-head CONFENGE | Env `CONFENGE_PR_HEAD_SHA` / `CONFENGE_WORKFLOW_MERGE_SHA` |

---

## 8. Riscos de dependência 🟡

| Risco | Severidade | Nota |
|-------|------------|------|
| Playwright/Selenium opcionais | Média | Portais JS e SICAF podem ficar cegos se não instalados |
| openai pin largo | Média | Classificação sensível a mudanças de modelo/API |
| psycopg2 vs binary | Baixa | Documentado: binary só dev/test |
| Monorepo com muitos JSON de campanha | Baixa/ops | Infla clone; política de artefatos gerados em docs |

---

*Gerado pelo Scout Reversa — 2026-07-27 | HEAD `ffbb9608`*
