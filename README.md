# Extra Consultoria — Inteligência em Licitações

Plataforma CLI de consultoria estratégica para licitações públicas.
Single-client: Extra Construtora.

## Stack

- **Python 3.12** — scripts de coleta, análise, PDF
- **PostgreSQL 17** — DataLake (Hetzner VPS)
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
# Provisionar PostgreSQL no Hetzner e configurar .env:
#   LOCAL_DATALAKE_DSN=postgresql://postgres:pass@<ip>:5432/pncp_datalake
bash db/setup_db.sh

# 3. Seed da planilha de órgãos
python db/seed/001_sc_entities.py

# 4. Verificar
psql $LOCAL_DATALAKE_DSN -c "SELECT count(*) FROM sc_public_entities"
```

## Comandos

```bash
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
```

## Fontes de Dados

| Fonte | Cobertura | Crawler |
|-------|-----------|---------|
| PNCP | Nacional (adesão voluntária) | `pncp_crawler.py` |
| DOM-SC | ~280 municípios SC | `dom_sc_crawler.py` |
| PCP v2 | ~100+ municípios SC | `pcp_crawler.py` |
| ComprasGov v3 | Órgãos federais SC | `compras_gov_crawler.py` |

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

---

*Extra Consultoria — Tiago Sasaki. Construído sobre Synkra AIOX v5.2.9.*
