# DECISIONS — EXTRA-OPERATIONAL-PROOF-01

## Benchmark matrix (Kingfisher Collect / Process / Cardinal)

| Padrão observado | Problema Extra | Decisão | Justificativa | Custo | Risco complexidade |
|------------------|----------------|---------|---------------|-------|---------------------|
| Separação collect vs process (Kingfisher) | Workspace, golden_path e crawlers misturam papéis | **ADAPT** | Fronteiras lógicas em `scripts/collect`, `quality`, `ops/weekly_cycle` sem reescrever o monólito | Baixo | Baixo |
| Collection ID + run rastreável | Execuções sem vínculo produto→coleta | **ADAPT** | `CollectionRun` + `collection_id` + persist em `pipeline_runs.params` | Baixo | Baixo |
| Raw em disco isolado do derivado | Raw URI/hash inconsistentes | **ADAPT** | Campos `raw_uri` + `content_hashes` no contrato; raw físico já existe em crawlers | Baixo | Baixo |
| Spider por fonte com contrato comum (Collect) | Fontes heterogêneas | **ADAPT** | Só PNCP oportunidades + reuse de contratos no ciclo semanal | Médio se expandir todas as fontes | Médio se forçar 100% fontes |
| OCDS schema strict (Process) | Claims OCDS-inspired confusos | **REJECT** (nesta campanha) | Não há conformidade OCDS a validar; prioridade é pacote Extra | Alto | Alto |
| Indicadores Cardinal com fórmulas explícitas | Métricas misturadas (presence/proxy/coverage) | **ADAPT** | `scripts/quality/indicator_catalog.py` fail-closed | Baixo | Baixo |
| CI em mudanças comuns | Full suite só manual | **ADAPT** | Critical + operational expanded no PR; full suite ainda `workflow_dispatch` com dívida documentada | Médio | Baixo |
| Scrapy/Kingfisher stack completa | Preferência estética de framework | **REJECT** | Não resolve produto semanal; reescrita cara | Muito alto | Muito alto |

## Decisões de implementação

### D1 — Entry point canônico

- **Escolha:** `make extra-weekly` → `python -m scripts.ops.weekly_cycle --strict`
- **Não canônicos (componentes internos):** `scripts.workspace`, `golden_path`, `opportunity_intel.cli`, `resilient_cycle`, `deliverable_package_final`
- **Por quê:** um comando para Tiago; reutiliza código existente.

### D2 — PR #28

- **Estado medido:** CLOSED + CONFLICTING
- **Ação:** não integrar; sem extração de delta exclusivo necessário para o ciclo semanal (main já contém EXTRA-OPS-95 #29)

### D3 — Contratos no ciclo semanal

- **Estratégia:** reutilizar lake `pncp_supplier_contracts` com freshness explícita (SLA 168h)
- **Não** re-crawl de ~500k linhas a cada semana nesta campanha
- Status: `reused_fresh` ou `partial` se stale

### D4 — Oportunidades PNCP

- Coleta live via crawler existente **ou** `reused_fresh` se SLA 48h
- Terminal statuses do contrato uniforme

### D5 — PDF

- **RESIDUAL** — não bloqueia campanha
- Produtos canônicos: Markdown + Excel + CSV + manifest

### D6 — CI

- Ampliar critical com `test_weekly_cycle.py`
- Novo job PR: operational expanded (lista explícita) com cov≥35% nos módulos críticos
- Full suite permanece `workflow_dispatch` até dívida residual de schema/env ser eliminada
- Owner da dívida full suite: @devops + @dev; prazo alvo: próximo ciclo operacional (não inventar data de PROJECT_DONE)

### D7 — Aceite humano

- Sempre `PENDING_HUMAN` até Tiago registrar
- Campanha **não** pode ser DONE sem AC10

## Gate arquitetural (resumo)

| Pergunta | Resposta |
|----------|----------|
| Falha operacional? | Tiago não tinha um comando único que gerasse pacote semanal auditável com freshness/proveniência |
| Benchmark? | Kingfisher separation + collection tracking; Cardinal-style indicator definitions |
| Menor mudança? | Orquestrador + contrato de run + catálogo + Makefile; sem reescrita |
| Medição? | exit code, manifest, checksums, contagens, testes unitários |
| Reversão? | Remover target Makefile + módulo weekly_cycle; lake intacto |
| Complexidade nova? | Baixa (1 orquestrador + 2 pacotes finos) |
| Trabalho manual Tiago? | **Reduz** — um comando + MD executivo |
