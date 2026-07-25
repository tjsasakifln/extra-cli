# Extra Consultoria — CLI de inteligência B2G

Ferramenta **pessoal, single-user, CLI-first** para apoiar Tiago Sasaki na consultoria à **Extra Construtora**: editais, contratos históricos, concorrentes e referências de valor em licitações públicas.

Norma de pronto: [`DOD.md`](DOD.md).  
Guia canônico de dev/ops local: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).  
Hub de documentação: [`docs/INDEX.md`](docs/INDEX.md).

---

## Escopo

**Incluído**

- Monitoramento e triagem de editais
- Histórico de contratos (backfill multi-ano + incremental)
- Mapeamento de vencedores / concorrentes observáveis
- Referências de valor com semântica explícita (estimado / homologado / contratado / pago)
- Apoio à decisão e à proposta; relatórios Excel/PDF
- Acompanhamento **administrativo** de contratos (prazos, aditivos, publicações…)

**Fora de escopo**

- Acompanhamento físico de obras (medição em campo, diário de obra, avanço físico)

**Universo canônico:** planilha `Extra - alvos de licitação. R-0.xlsx` → denominador de cobertura **1.093** entes no raio de 200 km de Florianópolis.  
Contagens ~2.085 (SC estadual amplo) em docs antigos **não** são o denominador de cobertura.

---

## Estado honesto (atualizado 2026-07-25; HEAD `main`)

| Item | Estado |
|------|--------|
| Host de record | **Netcup** RS 2000 · Debian 13 · PostgreSQL **17** · `ssh ec-prod` · app `/opt/extra-consultoria` |
| Contratos históricos PNCP (VPS) | Backfill ≥3 anos **37/37** janelas · ~**4,4M** linhas em `pncp_supplier_contracts` |
| Dual coverage `historical_contracts` | **PASS 100%** (1093/1093) — ADR-030 / campanha HC |
| Dual coverage `open_tenders` | **PASS 100%** (1093/1093) — campanha open-tenders (candidato; soak pendente) |
| Incremental contratos | Timer `pncp-contracts` (VPS) |
| Weekly timer | `extra-weekly` (enabled; 1º fire ok na campanha OT) |
| Backup off-site | Netcup Storagespace NFS montado; dumps diários |
| Campanha HC-closure | **BLOCKED** por **soak 7d** (calendário) |
| Campanha open-tenders cycle | **BLOCKED** por **soak 7d** + recall estratificado residual |
| Gate agregado “cobertura ≥95% fechada + VPS ops” | Dual 100% **≠** `VPS_OPERATIONAL` / `PROJECT_DONE` sem soak + accepts DOD |
| Recall independente ≥95% (amostra completa) | **Não claimado** (sample parcial / strata faltantes) |
| `LOCAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE` | **Não claimados** sem gates DOD + evidência no HEAD |

Campanhas:  
`artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/` ·  
`artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/` ·  
`artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/`

**Regras anti falso-verde:** fixture ≠ live; linha no banco ≠ cobertura operacional; job skipped ≠ aprovado; host VPS existe ≠ `VPS_OPERATIONAL`.

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| Runtime | Python 3.12, CLI (`scripts/`) |
| Dados | PostgreSQL (local Docker / VPS PG 17) |
| Agendamento | systemd timers (`deploy/systemd/`) |
| Qualidade | pytest, ruff, mypy, bandit, pip-audit, pre-commit |
| CI | GitHub Actions fail-closed (`.github/workflows/ci.yml`) |
| Relatórios | Excel + PDF (ReportLab) |
| IA opcional | análise de editais (quando configurada) |

Remote canônico: `https://github.com/tjsasakifln/extra-cli`.

---

## Estrutura (visão)

```
config/          Setores, SLAs, applicability, perfil Extra
scripts/         Código operacional (crawl, ops, workspace, coverage, reports…)
  crawl/         Crawlers multi-fonte + monitor
  ops/           Migrations apply, weekly cycle, health, campanhas
  workspace/     Facade CLI do dia a dia (ADR-017)
  opportunity_intel/  Licitações abertas
  coverage/      Contrato multi-métrica + dual capability
db/migrations/   Schema versionado
deploy/          systemd, ansible, provisionamento
docs/            Guia canônico, ops, ADRs, stories, evidências
specs/           Spec Kit (ex.: dual coverage, historical contracts)
squads/          Campanhas ROI / force-next
tests/           Suíte de verificação
tools/           dod_controller (convergência DOD)
artifacts/       Evidências de campanha (não confundir com claims de gate)
output/          Artefatos gerados (local; não commitar sensível)
```

---

## Setup local

```bash
# 1. Dependências
pip install -r requirements.txt

# 2. DSN (exemplo de teste — ver também .env.example)
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
# Em produção/VPS prefere-se DATABASE_URL (mesmo papel)

# 3. Banco local (Docker) + migrations
make db-up
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"

# 4. Validação rápida
python3 -m pytest tests/ -q --tb=no -x
ruff check scripts/

# 5. Golden path (prova técnica de pipeline — fail-closed)
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
# ou: make golden-path
```

Assets privados (planilha real de alvos): ver [`docs/ops/private-assets.md`](docs/ops/private-assets.md) e `EXTRA_TARGET_SPREADSHEET`.

---

## Entry-points canônicos

Contrato: [`docs/canonical-entry-points.yaml`](docs/canonical-entry-points.yaml).  
Detalhe completo: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

### Ciclo semanal (produto consultivo)

```bash
make extra-weekly
# equivalente:
python3 -m scripts.ops.weekly_cycle --strict
# flags: WEEKLY_FLAGS="--force-collect" | "--skip-collect" | "--lookback-days 7"
```

### Workspace (dia a dia)

```bash
python3 -m scripts.workspace today
python3 -m scripts.workspace opportunities --status open --limit 20
python3 -m scripts.workspace dossier <id>
python3 -m scripts.workspace coverage
python3 -m scripts.workspace competitors --limit 20
python3 -m scripts.workspace expiring-contracts
python3 -m scripts.workspace prices --keywords reforma
python3 -m scripts.workspace contracts
python3 -m scripts.workspace briefing
python3 -m scripts.workspace report weekly
```

Guia: [`docs/operations/workspace-guide.md`](docs/operations/workspace-guide.md).

### Coleta e opportunity intel

```bash
python3 -m scripts.crawl.monitor --source pncp --mode full
python3 -m scripts.crawl.monitor --source all --mode incremental
python3 -m scripts.crawl.monitor --report-coverage

python3 -m scripts.opportunity_intel.cli list --status open --limit 20
python3 -m scripts.opportunity_intel.cli source-health
python3 -m scripts.opportunity_intel.cli update --source pncp
```

### Cobertura e freshness

```bash
python3 -m scripts.coverage.coverage_contract_cli report --format table
python3 scripts/freshness_gate.py
# Dual capability (ADR-030): relatórios em output/coverage/ — presença ≠ cobertura
```

### DOD / campanhas

```bash
python3 tools/dod_controller.py status
python3 tools/dod_controller.py next
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

### Próximo passo operacional

Ver [`docs/ops/NEXT-DEV-STEP.md`](docs/ops/NEXT-DEV-STEP.md).

---

## Fontes de dados

Fontes e aplicabilidade: `scripts/crawl/registry.py` + `config/source_applicability.yaml` (fonte de verdade — a tabela abaixo é resumo).

| Família | Exemplos de crawler / path | Papel típico |
|---------|----------------------------|--------------|
| PNCP | `pncp_*`, contracts crawler | Editais + contratos nacionais |
| DOM / CIGA | `dom_sc_*`, `ciga_*` | Atos / publicações SC |
| DOE-SC | `doe_sc_*` | Diário oficial SC |
| PCP | `pcp_crawler.py` | Portais municipais PCP |
| ComprasGov | `compras_gov_crawler.py` | Órgãos federais |
| SC Compras / transparência / outros | `sc_compras_*`, `transparencia*`, … | Gap-fill e secundárias |

Cada fonte tem SLA de freshness (`config/coverage_slas.yaml`). **Sucesso de job ≠ cobertura de ente.**

---

## Capacidades de cobertura (dual spine)

Medição canônica separa capacidades (ADR-028, ADR-030; spec `specs/001-dual-capability-coverage-truth/`):

| Capability | Meta DOD | Nota honesta |
|------------|----------|--------------|
| `historical_contracts` | ≥95% | Dual **100%** na campanha HC — soak / gates agregados ainda separam de `VPS_OPERATIONAL` |
| `open_tenders` | ≥95% | Dual **100%** na campanha OT — soak 7d + recall estratificado ainda **BLOCKED** |
| competitors / prices | apoio consultivo | Entregáveis operacionais; ver weekly cycle |

Sinal comercial (`entities_with_recent_commercial_signal`) **não** é cobertura operacional.

---

## Operação VPS (resumo)

```bash
ssh ec-prod
# App: /opt/extra-consultoria
systemctl list-timers 'extra-*' 'pncp-*' 'pcp-*' 'dom-*' 'compras-*'
journalctl -u pncp-contracts.service -n 50
```

Timers versionados em `deploy/systemd/` (crawl multi-fonte, contracts, backup, health, coverage, enrich, purge, etc.).

Runbooks e inventário: [`docs/ops/README.md`](docs/ops/README.md).

---

## Métricas (não misturar)

| Contagem / métrica | Significado |
|--------------------|-------------|
| **1.093** | Universo canônico 200 km (denominador) |
| ~2.085 | Catálogo SC amplo / docs legados — **não** denominador de cobertura |
| Dual coverage | Por capability + set equality ao universo + freshness/SLA |
| Freshness | Dentro do SLA por fonte/capability |
| Recall | Amostra-ouro estratificada independente — não contagem do DB |

Glossário: [`docs/GLOSSARY.md`](docs/GLOSSARY.md).

---

## CI e qualidade

Gates fail-closed no CI (lint, typecheck no caminho crítico, testes, bandit HIGH, pip-audit).  
Local: `pre-commit install` · `make lint` · `make test` · `make resilience-gate` (quando aplicável).

Config: `pytest.ini`, `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.

---

## Onde ler mais

| Documento | Papel |
|-----------|--------|
| [`DOD.md`](DOD.md) | Definition of Done, gates, escopo |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Setup e comandos canônicos |
| [`docs/INDEX.md`](docs/INDEX.md) | Mapa living vs histórico vs evidência |
| [`docs/ops/README.md`](docs/ops/README.md) | Índice operacional |
| [`docs/architecture/`](docs/architecture/) | Arquitetura e ADRs |
| [`docs/operations/workspace-guide.md`](docs/operations/workspace-guide.md) | Rotina diária CLI |
| [`CHANGELOG.md`](CHANGELOG.md) | Marcos resumidos |

---

*Extra Consultoria — Tiago Sasaki. Ferramenta pessoal; não é SaaS multi-tenant.*
