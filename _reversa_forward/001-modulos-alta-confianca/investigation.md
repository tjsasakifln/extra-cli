# Investigation: Consolidação dos Módulos de Alta Confiança

> Feature: `001-modulos-alta-confianca`
> Data: 2026-07-14
> Roadmap: `_reversa_forward/001-modulos-alta-confianca/roadmap.md`

## 1. Pesquisa de fundo

### 1.1 Estado atual da orquestração local

O projeto **não possui** orquestração local reproduzível. O estado corrente:

- `docker-compose.yml`: apenas serviço `test-db` (PostgreSQL 16 + PostGIS para testes de integração)
- Sem Makefile: comandos são executados manualmente via `python scripts/...`
- Sem bootstrap automatizado: migrations e seed dependem de conhecimento tribal
- `provision-vps.sh` existe mas é para VPS remota, não para ambiente local
- `install.sh` instala dependências Python mas não gerencia DB

**Fontes consultadas:**
- `_reversa_sdd/deploy/design.md#riscos-e-lacunas`
- `docker-compose.yml` (raiz do projeto)
- `deploy/install.sh`, `deploy/provision-vps.sh`

### 1.2 Estado atual dos testes e cobertura

- 64 arquivos de teste com pytest 7.x+
- 7 marcadores (unit, integration, e2e, smoke, slow, database, crawler)
- `pytest.ini` configura `--cov=scripts --cov-report=term-missing`
- **Não há gate de coverage.** pytest-cov gera relatório mas nenhum script verifica thresholds
- `conftest.py` tem fixture autouse `_mock_psycopg2_connect` para isolamento padrão
- mypy configurado com `ignore_errors = true` em `tests.*`

**Fontes consultadas:**
- `_reversa_sdd/tests/design.md`
- `_reversa_sdd/tests/requirements.md`
- `pytest.ini`, `pyproject.toml`

### 1.3 Estado atual do QW-01 Radar (opportunity_intel)

- Pipeline 11 etapas (schema check → universe load → crawl → transform → dedup → score → rank → readiness gate → export). A **12ª etapa (snapshot reconciliation) não está implementada.**
- 3 lacunas documentadas no `_reversa_sdd/opportunity_intel/requirements.md`:
  1. Snapshot reconciliation (P0-04)
  2. PNCP-only — 20.95% com link oficial
  3. Competitive intel metrics com colunas incompatíveis
- Stories 1.4 e 1.5 entregaram base: `opportunity_intel` table, `coverage_evidence` ledger, schema unificado v3

**Fontes consultadas:**
- `_reversa_sdd/opportunity_intel/design.md`
- `_reversa_sdd/opportunity_intel/requirements.md`
- `docs/stories/epic-technical-debt.md`
- `_reversa_sdd/state-machines.md#ms8`

## 2. Alternativas avaliadas

### 2.1 Orquestração: Makefile vs Taskfile vs Just vs scripts

| Alternativa | Prós | Contras | Veredito |
|-------------|------|---------|----------|
| **GNU Make** | Universal em Python, zero dependências, `.PHONY` targets, variáveis nativas | Sintaxe arcana para regras complexas | ✅ Escolhido |
| Taskfile (Go) | YAML, mais legível | Dependência extra (Go binary), não padrão Python | ❌ |
| Just | Similar a Make, sintaxe moderna | Dependência extra (Rust binary), não ubiquitário | ❌ |
| Scripts shell soltos | Já existem (`install.sh`) | Difícil descobrir, sem `make help`, duplicação | ❌ (estado atual) |

### 2.2 Coverage gate: script Python vs pytest plugin vs pytest-cov flags

| Alternativa | Prós | Contras | Veredito |
|-------------|------|---------|----------|
| **Script Python autônomo** | Lê `.coveragerc`, threshold por módulo, JSON output, testável | Arquivo extra | ✅ Escolhido |
| pytest `--cov-fail-under=80` | Uma linha, nativo | Threshold GLOBAL, não por módulo. Não atende RN-02. | ❌ |
| pytest plugin customizado | Integrado ao pytest | Complexo, frágil com upgrades, over-engineering | ❌ |
| coverage.py API direta | Flexível | Mesma lógica do script, só que inline | ❌ (melhor isolado) |

### 2.3 Snapshot reconciliation: função Python vs trigger SQL vs CLI comando

| Alternativa | Prós | Contras | Veredito |
|-------------|------|---------|----------|
| **Função Python no pipeline** | Testável, log estruturado, guarda explícita, audit trail em `coverage_evidence` | Acoplada ao pipeline | ✅ Escolhido |
| Trigger PostgreSQL | Atômico, sem esquecimento | Lógica escondida, difícil testar, sem audit trail rico | ❌ |
| Comando CLI separado | Desacoplado | Usuário esqueceria de rodar; reconciliação deve ser obrigatória, não opcional | ❌ |

### 2.4 Docker: expandir existente vs criar novo vs Dockerfile customizado

| Alternativa | Prós | Contras | Veredito |
|-------------|------|---------|----------|
| **Expandir docker-compose.yml existente** | Reutiliza serviço test-db, mesma rede, transição suave para VPS | Precisa renomear para `docker-compose.local.yml` | ✅ Escolhido |
| docker-compose separado | Isolamento total | Duplicação do serviço PostgreSQL, divergência garantida | ❌ |
| Dockerfile customizado | Imagem otimizada | Over-engineering; Python 3.12 + pip install bastam | ❌ |

## 3. Padrões aplicáveis

| Padrão | Origem | Aplicação nesta feature |
|--------|--------|------------------------|
| Fail-closed | `_reversa_sdd/architecture.md#adr-014` | Coverage gate exit 2; CI gate exit 2; reconciliation só em execução completa |
| Evidence-based audit | `_reversa_sdd/architecture.md#adr-013` | Toda reconciliação registra evento em `coverage_evidence` |
| Conservative denominator | `_reversa_sdd/domain.md#glossario` | 7 módulos fixos para coverage; sem inferência automática |
| Idempotência | `_reversa_sdd/deploy/design.md#decisões-de-design` | Bootstrap com guardas por step; reconciliação com `run_id` dedup |
| Circuit breaker | `_reversa_sdd/architecture.md#padrões-de-codigo` | Crawl no pipeline QW-01 já usa; reconciliação herda |
| Content hash | `_reversa_sdd/domain.md#r8` | Não aplicável diretamente, mas consistente com filosofia de auditabilidade |

## 4. Links para fontes externas

- GNU Make manual: https://www.gnu.org/software/make/manual/
- Docker Compose file reference: https://docs.docker.com/compose/compose-file/
- pytest-cov documentation: https://pytest-cov.readthedocs.io/
- coverage.py API: https://coverage.readthedocs.io/
- ReportLab PDF generation: https://www.reportlab.com/docs/

## 5. Histórico de alterações

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-14 | Versão inicial gerada por `/reversa-plan` | reversa |
