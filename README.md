# Extra Consultoria — Inteligência em Licitações

Plataforma CLI de consultoria estratégica para licitações públicas.
Single-client: Extra Construtora.

## Fase Atual

Escopo operacional atual:

- busca de editais abertos
- histórico de contratos para análise
- mapeamento de concorrentes e vencedores
- apoio a leitura de preços praticados

Fora de escopo por enquanto:

- acompanhamento de obras
- execução/monitoramento físico-financeiro de contratos

Importante:

- nesta fase o projeto roda com **datalake local**
- a futura arquitetura com **VPS em nuvem + PostgreSQL + systemd timers** é o alvo, não baseline operacional
- o provedor de nuvem ainda não está definido (ver `docs/architecture/adr/ADR-007-cloud-hosting-strategy.md`)
- base local legada **não deve ser presumida fresca**
- qualquer decisão de uso consultivo deve verificar `source-health`, manifests e `last_seen` antes de confiar nos dados

### Estado de resiliência pré-VPS

**Veredito atual: `NOT_READY` para `PRE_VPS_FINAL_READY`.**  
O selo `LOCAL_RESILIENCE_READY` foi **destruído** pela auditoria adversarial
(`docs/operations/PRE-VPS-FINAL-ADVERSARIAL-AUDIT.md`): fixture ≠ live,
JSON local ≠ PostgreSQL operacional, job recente ≠ conteúdo fresco.

Estados honestos:

| Estado | Significado |
|--------|-------------|
| `PRE_VPS_OFFLINE_READY` | Gates offline (lint/type/unit/chaos/fixture isolation) |
| `PRE_VPS_LIVE_CANARY_READY` | Canaries live + PG das 3 fontes prioritárias |
| `PRE_VPS_FINAL_READY` | Offline + canary + CI + revisão adversarial |
| `NOT_READY` | Qualquer bloqueio acima |

```bash
make pre-vps-final-gate-offline
make pre-vps-live-canary    # exige DATABASE_URL; nunca no CI auto
make pre-vps-final-gate
python3 -m scripts.ops.health              # live only; exit 2 sem evidência
python3 -m scripts.ops.health --env fixture
```

O padrão usa fixtures controladas; acesso live exige `--live`. Veja
`docs/operations/PRE-VPS-READINESS.md` e
`docs/operations/LOCAL-RESILIENCE-RUNBOOK.md`.

## Stack

- **Python 3.12** — scripts de coleta, análise, PDF
- **PostgreSQL 16** — DataLake (versão canônica inicial)
- **systemd timers** — cron jobs
- **ReportLab** — PDFs Big Four aesthetic
- **OpenAI GPT-4.1-nano** — análise de editais

## Estrutura

```
config/         Configurações (setores, settings, YAML)
scripts/        Pipeline de inteligência e crawlers
  crawl/        Crawlers multi-source (PNCP, DOM-SC, PCP, ComprasGov)
  reports/      Relatórios (panorama, sazonalidade, concorrência)
  lib/          Bibliotecas compartilhadas
db/             Migrations SQL + seed
docs/           PRD, stories, arquitetura
data/           Dados locais (JSON cache, SQL dumps)
output/         PDFs e Excels gerados
```

## Setup

```bash
# 1. Dependências
pip install -r requirements.txt

# 2. Database
# Provisionar PostgreSQL e configurar .env:
#   LOCAL_DATALAKE_DSN=postgresql://postgres:pass@<ip>:5432/pncp_datalake
bash db/setup_db.sh

# 3. Seed da planilha de órgãos
python db/seed/001_sc_entities.py

# 4. Verificar
psql $LOCAL_DATALAKE_DSN -c "SELECT count(*) FROM sc_public_entities"
```

## Comandos

```bash
# Golden Path — Pipeline de validação completa (idempotente)
make golden-path
make golden-path GOLDEN_PATH_FLAGS="--verbose"
make golden-path GOLDEN_PATH_FLAGS="--skip-freshness"
make golden-path-quick                                    # pula freshness + reports

# O golden-path executa:
#   1. db-up (PostgreSQL via Docker)
#   2. bootstrap (migrations + seed)
#   3. Crawl de 3 fontes (pncp, pcp, compras_gov) com timeout 120s e retry 3x
#   4. Freshness gate (validação de atualidade dos dados)
#   5. Relatórios Excel + PDF
#
# Ledger de execução: output/golden-path/ledger.json
# Logs: output/golden-path/gp-*.log

# Crawl multi-source
python scripts/crawl/monitor.py --source pncp --mode full
python scripts/crawl/monitor.py --source all --mode incremental

# Coverage report
python scripts/crawl/monitor.py --report-coverage

# Pipeline de inteligência (para 1 CNPJ)
python scripts/intel_pipeline.py --cnpj <CNPJ> --ufs SC

# Panorama de mercado
python scripts/reports/panorama.py --output-excel

# DataLake CLI
python scripts/local_datalake.py search --uf SC --dias 30
python scripts/local_datalake.py supplier --cnpj <CNPJ>
python scripts/local_datalake.py stats

# Opportunity Intelligence — licitações abertas
python scripts/opportunity_intel/cli.py list --status open --limit 20
python scripts/opportunity_intel/cli.py show 1
python scripts/opportunity_intel/cli.py explain 1
python scripts/opportunity_intel/cli.py coverage
python scripts/opportunity_intel/cli.py source-health
python scripts/opportunity_intel/cli.py update --source pncp
python scripts/opportunity_intel/cli.py export --format csv -o opportunities.csv

# Manifestos de cobertura
python scripts/opportunity_intel/manifest.py
python scripts/freshness_gate.py

# SLAs opcionais do freshness gate
#   FRESHNESS_SLA_PNCP_HOURS=24
#   FRESHNESS_SLA_CONTRACTS_HOURS=576
```

## Fontes de Dados

| Fonte | Cobertura | Crawler |
|-------|-----------|---------|
| PNCP | Nacional (adesão voluntária) | `pncp_crawler.py` |
| DOM-SC | ~280 municípios SC | `dom_sc_crawler.py` |
| PCP v2 | ~100+ municípios SC | `pcp_crawler.py` |
| ComprasGov v3 | Órgãos federais SC | `compras_gov_crawler.py` |

## Opportunity Intelligence (V1)

Vertical de licitações abertas para Extra Construtora.
Raio de 200 km de Florianópolis. Threshold: 95%.

Estado real nesta fase:

- a estrutura de oportunidade existe
- cobertura e freshness ainda precisam ser provadas por fonte e por ente
- o threshold de 95% nao deve ser considerado atendido apenas por presenca de registros no banco

**Fluxo:** fonte oficial → fetch → raw zone → normalização →
PostgreSQL → deduplicação → status canônico → ranking → CLI → manifesto.

**Estados:** open, upcoming, closed, suspended, revoked, annulled, failed, unknown.
**Ranking:** GO, REVIEW, NO_GO (score 0–100, fatores explicáveis, regras determinísticas).
**Deduplicação:** ID oficial → número PNCP → órgão+processo+edital → hash (nunca similaridade textual).

Arquivos gerados:
- `output/readiness/opportunity-coverage-manifest.json`
- `output/readiness/opportunity-coverage-gaps.csv`
- `output/readiness/opportunity-source-health.csv`
- `output/readiness/freshness-gate.json`
- `output/readiness/freshness-gate.csv`

## Cron (systemd timers)

```bash
systemctl enable pncp-crawl-full.timer    # Diário 05:00 UTC
systemctl enable pncp-crawl-inc.timer     # 11:00, 17:00, 23:00 UTC
systemctl enable dom-sc-crawl.timer       # 06:00, 14:00, 22:00 UTC
systemctl enable coverage-report.timer    # Diário 09:00 UTC
systemctl enable pncp-report-weekly.timer # Seg 07:00 UTC
```

## Métricas

- **2.085** órgãos públicos SC no universo-alvo
- Cobertura verificada via `scripts/consulting_readiness.py` (consulte `coverage_manifest.json`)
- **5** fontes de dados
- **13** setores configurados

Observação:

- o indicador mais importante nesta fase é **freshness auditável**
- cobertura, histórico de contratos e inteligência competitiva só são confiáveis quando a coleta recente estiver provada nas fontes críticas

## CI Gates (Regra #10 — B2G-4)

Gates **fail-closed**: qualquer falha = CI vermelho. Nenhum job usa `continue-on-error: true` ou `|| true`.

| Gate | Job | Ferramenta | Onde | Fail-Close |
|------|-----|-----------|------|------------|
| Lint | `lint` | `ruff check scripts/` | `.github/workflows/ci.yml` | SIM — quebra em qualquer violação no código de produção |
| Type Check | `type-check` | `mypy` no caminho crítico de freshness/readiness | `.github/workflows/ci.yml` | SIM — escopo expandido gradualmente via TD-7.1 |
| Testes Críticos | `test` | suíte de freshness/readiness + `--cov-fail-under=10` | `.github/workflows/ci.yml` | SIM — threshold mínimo 10% no caminho crítico |
| Testes Completos | `test-all` | `pytest -m ""` (sem exclusão) | `.github/workflows/ci.yml` | MANUAL — fail-closed via `workflow_dispatch` enquanto dependências externas são provisionadas |
| Segurança | `security` | `bandit -r scripts/` (HIGH severity) | `.github/workflows/ci.yml` + `pyproject.toml` | SIM — quebra em falha HIGH |
| Auditoria Deps | `dependency-audit` | `pip-audit --strict` | `.github/workflows/ci.yml` | SIM — quebra em CVE conhecido |
| Pre-Commit (local) | — | ruff + mypy + bandit + secrets | `.pre-commit-config.yaml` | SIM — bloqueia commit local |

**Configurações:**
- `pytest.ini`: exclui `slow` por default; `integration` e `smoke` rodam no CI
- `pyproject.toml`: `[tool.bandit]` exclui `tests/` e `tests/fixtures/`
- `.pre-commit-config.yaml`: bandit scoped a HIGH severity em `scripts/`; secrets detecta AWS credentials e chaves privadas

**Instalação local do pre-commit:**
```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files  # verificação manual
```

---

*Extra Consultoria — Tiago Sasaki. Construído sobre Synkra AIOX v5.2.9.*
