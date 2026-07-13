# Onboarding -- Extra Consultoria

> Guia de integracao para novos desenvolvedores na plataforma de inteligencia em
> licitacoes publicas da Extra Consultoria.
>
> **Story:** TD-6.2 -- Runbooks e Onboarding
> **Debito:** TD-SYS-004 -- Estado global mutavel / documentacao insuficiente

## Indice

- [Visao Geral do Sistema](#visao-geral-do-sistema)
- [Dominio: Licitacoes Publicas](#dominio-licitacoes-publicas)
- [Setup do Ambiente](#setup-do-ambiente)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Como Rodar Crawlers](#como-rodar-crawlers)
- [Como Contribuir](#como-contribuir)
- [Referencias](#referencias)

---

## Visao Geral do Sistema

A Extra Consultoria opera uma plataforma CLI de inteligencia em licitacoes publicas
para um unico cliente: **Extra Construtora**. O sistema coleta, processa e analisa
dados de licitacoes de multiplas fontes governamentais, gerando relatorios
estrategicos em PDF e Excel.

Nota de fase:

- baseline atual: `local-first`
- o datalake local pode conter dados legados
- o frescor das fontes criticas deve ser provado antes de confiar nos resultados

### Arquitetura Simplificada

```
[Fontes Externas]                 [VPS Hetzner]              [Cliente]
     PNCP                     +---------------------+      +---------+
     DOM-SC                   | PostgreSQL (4.1 GB)  |----->| PDFs   |
     PCP v2       ===crawl==> | Crawlers (systemd)   |=====>| Excel  |
     ComprasGov               | Intel Pipeline       |      | Web    |
     Portal Transparencia     | Relatorios           |      +---------+
                              +---------------------+
                                   ^
                                   |
                              [Storage Box]
                              (backups diarios)
```

### Stack

| Componente | Tecnologia | Versao |
|------------|-----------|--------|
| Linguagem | Python | 3.12+ |
| HTTP Client | httpx | 0.28+ |
| Database | PostgreSQL | 17 |
| ORM indireto | Supabase SDK (sb) | -- |
| PDF | ReportLab | 4.5+ |
| Excel | openpyxl | 3.1+ |
| CLI | rich | 13+ |
| LLM | OpenAI GPT-4.1-nano | -- |
| Agendamento | systemd timers | -- |
| Infra | Hetzner CX22 (2vCPU, 4GB) | Ubuntu 24.04 |

### Crawlers Disponiveis

| Fonte | Abrangencia | Crawler | Frequencia |
|-------|-------------|---------|------------|
| **PNCP** | Nacional (adesao voluntaria) | `pncp_crawler.py` | 05:00 UTC (full) + 3x inc |
| **DOM-SC** | ~280 municipios SC | `dom_sc_crawler.py` | 06:00, 14:00, 22:00 UTC |
| **PCP v2** | ~100+ municipios SC | `pcp_crawler.py` | Sob demanda |
| **ComprasGov** | Orgaos federais SC | `compras_gov_crawler.py` | Sob demanda |

---

## Dominio: Licitacoes Publicas

### Conceitos Fundamentais

- **Licitacao:** Processo administrativo pelo qual orgaos publicos adquirem bens
  e contratam servicos. Regida pela Lei 14.133/2021 (Nova Lei de Licitacoes).

- **Orgao Publico:** Entidade da administracao direta ou indireta que realiza
  a licitacao (ministerios, prefeituras, autarquias, fundacoes).

- **Modalidades de Licitacao:**
  - Pregao (modalidade mais comum -- menor preco)
  - Concorrencia (maior valor ou tecnica e preco)
  - Concurso (escolha de trabalho tecnico/artistico)
  - Leilao (venda de bens)
  - Dialogo Competitivo (inovacao)

- **Fases da Licitacao:**
  - Edital -> Impugnacao -> Propostas -> Julgamento -> Homologacao -> Contrato

- **PNCP:** Portal Nacional de Contratacoes Publicas -- sistema centralizado
  do governo federal para divulgacao de licitacoes.

- **DOM-SC:** Diario Oficial dos Municipios de Santa Catarina -- fonte primaria
  para licitacoes municipais catarinenses.

### Nosso Pipeline

```
Crawl (coleta) -> Transform (limpeza) -> Enrich (enriquecimento)
  -> Analyze (inteligencia) -> Report (PDF/Excel)
```

### Enriquecimento de Dados

O pipeline de enriquecimento (enricher.py) adiciona dados externos:
- **BrasilAPI:** Dados cadastrais de fornecedores (CNPJ -> razao social, CNAE, porte)
- **IBGE:** Codigos municipais e populacao (municipio+UF -> codigo IBGE)

---

## Setup do Ambiente

### Pre-requisitos

| Requisito | Minimo | Recomendado |
|-----------|--------|-------------|
| Python | 3.10+ | 3.12+ |
| PostgreSQL | 14 | 17 |
| pip | Ultima versao | -- |
| Git | 2.x | Ultima versao |

### Passo a Passo

```bash
# 1. Clonar repositorio
git clone <repo-url>
cd extra-consultoria

# 2. Criar virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configurar variaveis de ambiente
cp .env.example .env
# Editar .env com credenciais reais:
#   LOCAL_DATALAKE_DSN, DOM_SC_API_KEY, OPENAI_API_KEY
nano .env

# 5. Provisionar banco (opcional, apenas se tiver acesso)
bash db/setup_db.sh

# 6. Seed de entidades (opcional)
python db/seed/001_sc_entities.py

# 7. Verificar instalacao
python scripts/health_check.py
```

### Configuracao do .env Variaveis Principais

| Variavel | Obrigatoria? | Descricao |
|----------|-------------|-----------|
| `LOCAL_DATALAKE_DSN` | Sim | PostgreSQL DSN `postgresql://user:pass@host:5432/pncp_datalake` |
| `PNCP_BASE` | Nao (default) | URL base da API PNCP |
| `DOM_SC_API_KEY` | Sim (DOM-SC) | Chave da API DOM-SC |
| `INGESTION_UFS` | Sim | UFs monitoradas (ex: SC) |
| `PORTAL_TRANSPARENCIA_API_KEY` | Sim (Transparencia) | Chave API dados.gov.br |
| `OPENAI_API_KEY` | Sim (Intel) | Chave OpenAI para analise de editais |

### Verificacao

Apos configurar, execute:

```bash
# Testar conexao com banco
psql $LOCAL_DATALAKE_DSN -c "SELECT current_database(), version()"

# Verificar health check
python scripts/health_check.py

# Verificar freshness das fontes criticas
python scripts/freshness_gate.py

# Rodar testes
pytest tests/test_transformer.py -v
```

---

## Estrutura do Projeto

```
extra-consultoria/
  config/              Configuracoes (setores, settings, YAML)
    logging_config.py  Configuracao de logging centralizada
    settings.py        Configuracoes gerais
  scripts/             Pipeline de inteligencia
    crawl/             Crawlers multi-source
      enricher.py      Enriquecimento de dados (fornecedores + IBGE)
      monitor.py       Orquestrador principal de crawlers
      pncp_crawler.py  Crawler PNCP
      dom_sc_crawler.py Crawler DOM-SC
      pcp_crawler.py   Crawler PCP v2
      compras_gov_crawler.py Crawler ComprasGov
      transformer.py   Normalizacao/limpeza de dados
      common.py        Funcoes compartilhadas (upsert, hash)
      config.py        Configuracoes de crawlers
      retry.py         Logica de retry com backoff
      adapter.py       Adaptadores de API
      async_client.py  Cliente HTTP assincrono
      sync_client.py   Cliente HTTP sincrono
      checkpoint.py    Gerenciamento de checkpoints
      circuit_breaker.py Circuit breaker para APIs
      sanctions.py     Verificacao de sancionados
      monitor.py       Orquestrador / coordenador
      loader.py        Loader para DataLake
      orchestrator.py  Orquestracao de crawlers
      _parallel_mixin.py Mixin de paralelismo
      transparencia_crawler.py Crawler Portal Transparencia
      contracts_crawler.py Crawler de contratos
      bids_crawler.py  Crawler de licitacoes
      tce_sc_crawler.py Crawler TCE-SC
      sc_compras_crawler.py Crawler SC Compras
      doe_sc_crawler.py Crawler DOE-SC
      pncp_crawler_adapter.py Adaptador PNCP
      pncp_arp_crawler.py Crawler ARP PNCP
      pncp_pca_crawler.py Crawler PCA PNCP
    reports/           Geracao de relatorios
      panorama.py      Relatorio panoramico
      coverage_gaps.py Gaps de cobertura
      coverage_weekly.py Cobertura semanal
    matching/          Algoritmos de matching
      entity_matcher.py Correspondencia de entidades (CNPJ/nome/fuzzy)
    lib/               Bibliotecas compartilhadas
      constants.py     Constantes do dominio
      retry.py         Funcoes de retry genericas
      name_normalizer.py Normalizacao de nomes
      cost_estimator.py Estimativa de custos
      bid_simulator.py Simulacao de lances
      intel_logging.py Logging para pipeline de inteligencia
    intel_pipeline.py  Pipeline de inteligencia
    intel_analyze.py   Analise de dados
    intel_enrich.py    Enriquecimento inteligente
    intel_collect.py   Coleta inteligente
    intel_report.py    Relatorios inteligentes
    local_datalake.py  CLI do DataLake local
    datalake_helper.py Helper do DataLake
    health_check.py    Verificacao de saude
  db/                  Migrations SQL + seed
    setup_db.sh        Script de provisionamento do banco
    seed/              Seeds (entidades SC, etc.)
  docs/                Documentacao
    ops/               Documentacao operacional
      backup.md        Sistema de backup automatizado
      vps-access.md    Acesso a VPS de producao
      vps-provisioning.md Provisionamento da VPS Hetzner
      troubleshooting.md Problemas comuns e solucoes
      onboarding.md    Este guia
    architecture/      Documentacao de arquitetura
    stories/           Stories de desenvolvimento
    prd/               PRD (Product Requirements Document)
    qa/                Relatorios de qualidade
  deploy/              Scripts de deploy
    provision-vps.sh   Script de provisionamento da VPS
  data/                Dados locais (JSON cache, dumps)
  output/              PDFs e Excels gerados
  tests/               Testes automatizados
  pyproject.toml       Configuracao de ferramentas (ruff, mypy)
  pytest.ini           Configuracao do pytest
  conftest.py          Fixtures compartilhadas
  requirements.txt     Dependencias do projeto
```

---

## Como Rodar Crawlers

### Crawl Completo (todas as fontes)

```bash
python scripts/crawl/monitor.py --source all --mode full
```

### Crawl Incremental (ultimos 3 dias)

```bash
python scripts/crawl/monitor.py --source pncp --mode incremental
```

### Crawl por Fonte Especifica

```bash
# PNCP
python scripts/crawl/monitor.py --source pncp --mode full

# DOM-SC
python scripts/crawl/monitor.py --source dom-sc --mode full

# PCP v2
python scripts/crawl/pcp_crawler.py

# ComprasGov
python scripts/crawl/compras_gov_crawler.py
```

### Relatorio de Cobertura

```bash
python scripts/crawl/monitor.py --report-coverage
```

### Pipeline de Inteligencia

```bash
# Para 1 CNPJ especifico
python scripts/intel_pipeline.py --cnpj <CNPJ> --ufs SC

# Relatorio panoramico
python scripts/reports/panorama.py --output-excel
```

### Explorar DataLake via CLI

```bash
# Buscar licitacoes por UF e periodo
python scripts/local_datalake.py search --uf SC --dias 30

# Ver dados de um fornecedor
python scripts/local_datalake.py supplier --cnpj <CNPJ>

# Estatisticas do DataLake
python scripts/local_datalake.py stats
```

### Crawlers Individuais (modo debug)

Cada crawler tambem pode ser executado diretamente para testes:

```bash
python scripts/crawl/pncp_crawler.py --help
python scripts/crawl/dom_sc_crawler.py --help
```

---

## Como Contribuir

### Workflow Git

Nos usamos um fluxo simplificado baseado em branches:

```bash
# 1. Criar branch a partir da main
git checkout main
git pull
git checkout -b feat/my-feature

# 2. Fazer alteracoes e commitar
git add <files>
git commit -m "feat: descricao concisa do que foi feito [Story X.Y]"

# 3 Manter sincronizado com main
git fetch origin
git rebase origin/main

# 4. Abrir PR (via @devops)
# O push e criacao de PR sao exclusivos do agente @devops
```

### Convencao de Commits

Usamos [Conventional Commits](https://www.conventionalcommits.org/):

| Tipo | Uso |
|------|-----|
| `feat:` | Nova funcionalidade |
| `fix:` | Correcao de bug |
| `docs:` | Documentacao |
| `refactor:` | Refatoracao sem mudanca funcional |
| `test:` | Testes |
| `chore:` | Manutencao (deps, config) |

Sempre referenciar a story: `feat: implement X [Story 2.1]`

### Rodar Testes

```bash
# Todos os testes
pytest

# Testes especificos
pytest tests/test_transformer.py -v

# Com cobertura
pytest --cov=scripts --cov-report=term-missing

# Apenas testes unitarios rapidos
pytest -m unit

# Testes lentos (rede/banco)
pytest -m integration
```

### Lint e Type Checking

Usamos **ruff** para linting e **mypy** para type checking:

```bash
# Lint
ruff check scripts/

# Formatacao
ruff format scripts/

# Type checking (mypy)
mypy scripts/

# Os dois juntos
ruff check scripts/ && mypy scripts/
```

As configs estao em `pyproject.toml`:
- `ruff`: line-length 120, regras E/F/I/N/W/UP
- `mypy`: strict mode com excecoes para pacotes externos

### Code Review

Antes de completar uma story:

1. Rode `pytest` -- todos os testes devem passar
2. Rode `ruff check scripts/` -- sem erros
3. Verifique type hints

---

## Referencias

### Documentacao Operacional

- [Backup](docs/ops/backup.md) -- Sistema de backup automatizado
- [Acesso VPS](docs/ops/vps-access.md) -- Acesso a VPS de producao
- [Provisionamento VPS](docs/ops/vps-provisioning.md) -- Setup da VPS Hetzner
- [Troubleshooting](docs/ops/troubleshooting.md) -- Problemas comuns e solucoes

### Arquitetura

- `docs/architecture/` -- Documentos de arquitetura do sistema
- `docs/stories/` -- Stories de desenvolvimento (contexto das decisoes)

### Documentacao Externa

- [PNCP API](https://pncp.gov.br/api/swagger-ui/index.html)
- [IBGE Localidades API](https://servicodados.ibge.gov.br/api/docs/localidades)
- [BrasilAPI](https://brasilapi.com.br/docs)
- [Nova Lei de Licitacoes (14.133/2021)](https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm)

### Ferramentas

- [Hetzner Cloud Console](https://console.hetzner.cloud/)
- [Supabase Dashboard](https://supabase.com/dashboard) (se aplicavel)

---

> **Ultima atualizacao:** 2026-07-11
> **Responsavel:** @dev (Dex)
