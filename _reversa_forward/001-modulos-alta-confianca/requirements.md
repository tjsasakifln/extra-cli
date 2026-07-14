# Requirements: Consolidação dos Módulos de Alta Confiança

> Identificador: `001-modulos-alta-confianca`
> Data: 2026-07-14
> Pasta da extração reversa: `_reversa_sdd/`
> Confidência: 🟢 CONFIRMADO, 🟡 INFERIDO, 🔴 LACUNA / DÚVIDA

## 1. Resumo executivo

Consolidar os três módulos de maior maturidade do sistema — **deploy**, **tests** e **opportunity_intel** — fechando lacunas remanescentes da auditoria reversa e elevando-os ao estado production-ready. As stories 1.1→1.5 do `epic-technical-debt.md` entregaram a fundação (schema unificado, autoridade do universo, reconciliação de editais, coverage evidence ledger). Esta feature ataca o que ficou pendente: orquestração local reproduzível, gate de cobertura de testes e as três lacunas críticas do QW-01 Radar.

## 2. Contexto a partir do legado

| Fonte | Trecho relevante | Confidência |
|-------|------------------|-------------|
| `_reversa_sdd/architecture.md#subsistemas` | Deploy (42 arquivos, 3.5K LOC), Tests (64 arquivos, 7 marcadores), Opportunity Intel (16 arquivos, 15K LOC) — três módulos mais bem documentados | 🟢 |
| `_reversa_sdd/deploy/design.md#riscos-e-lacunas` | 🔴 Orquestração local reproduzível não implementada (Makefile, docker-compose, bootstrap). Deploy VPS é EPIC P2. | 🟢 |
| `_reversa_sdd/tests/requirements.md#requisitos-nao-funcionais` | 🔴 Gate de cobertura 80% para módulos críticos — NÃO IMPLEMENTADO | 🟢 |
| `_reversa_sdd/opportunity_intel/requirements.md#regras-de-negocio` | 🔴 Snapshot reconciliation (P0-04), 🔴 PNCP-only (20.95% com link oficial), 🔴 Competitive intel metrics não validadas em PostgreSQL | 🟢 |
| `_reversa_sdd/domain.md#glossario` | Evidence Ledger, Canonical Universe, QW-01 Radar, Fail-Closed, Conservative Denominator — conceitos fundamentais para os três módulos | 🟢 |
| `docs/stories/epic-technical-debt.md` | Stories 1.1→1.5 concluídas. Próximos passos: P0-06 (multi-fontes), P0-09 (competitive intel), P1-04 (orquestração local) | 🟢 |
| `.reversa/state.json#checkpoints.reviewer.stats` | 24 lacunas consolidadas: 8 críticas, 7 altas, 5 médias, 4 baixas. 4 specs corrigidas in-place. | 🟡 |

## 3. Personas e cenários de uso

| Persona | Objetivo | Cenário-chave |
|---------|----------|---------------|
| Desenvolvedor (Tiago) | Rodar pipeline completo localmente com um comando | `make run-pipeline` executa crawl→transform→enrich→report sem intervenção manual |
| Desenvolvedor (Tiago) | Garantir que testes cobrem 80% dos módulos críticos antes de commit | `pytest --cov=scripts --cov-report=term-missing` mostra coverage ≥ 80% nos módulos gateados |
| Consultor (Tiago) | Confiar que o radar de oportunidades não exibe editais fantasmas | QW-01 Radar executa, reconcilia snapshot, exporta CSV com 100% de oportunidades verificadas |
| Consultor (Tiago) | Ter URL oficial em toda oportunidade PRIORITARIA | Radar não classifica como PRIORITARIA sem `official_url` preenchida |

## 4. Regras de negócio novas ou alteradas

1. **RN-01:** Orquestração local deve ser reproduzível com um comando (`make run-pipeline`) e produzir os mesmos artefatos do pipeline manual. 🟢
   - Origem no legado: `_reversa_sdd/deploy/design.md#riscos-e-lacunas`
   - Tipo: nova

2. **RN-02:** Gate de cobertura de testes: 7 módulos críticos conforme plano mestre §18 (`opportunity_intel`, `reconciliacao`, `coverage`, `contract_pipeline`, `supplier_metrics`, `price_pipeline`, `report_builder`) exigem ≥ 80% de line coverage. CI falha fail-closed (exit 2) se qualquer módulo abaixo. Consistente com ADR-014. 🟢
   - Origem no legado: `_reversa_sdd/tests/requirements.md#requisitos-nao-funcionais` + `plano-mestre §18`
   - Tipo: nova

3. **RN-03:** Snapshot reconciliation é OBRIGATÓRIO em toda execução completa do QW-01 Radar. Registros `is_active=TRUE` ausentes do snapshot corrente são inativados. Em execução parcial (max_pages, erro), reconciliação NÃO roda. 🟢
   - Origem no legado: `_reversa_sdd/opportunity_intel/requirements.md#regra-8` + `_reversa_sdd/domain.md#r8`
   - Tipo: nova (fecha lacuna P0-04)

4. **RN-04:** Oportunidade classificada como PRIORITARIA sem `official_url` é automaticamente degradada para REVISAR, com `missing_fields` incluindo `"official_url"`. 🟡
   - Origem no legado: `_reversa_sdd/opportunity_intel/requirements.md#criterios-de-aceitacao` (Gherkin já escrito, não implementado)
   - Tipo: nova

5. **RN-05:** Métricas de competitive intelligence (market share, HHI, supplier ranking) devem ser validadas contra o schema operacional real (`db/migrations/026`). Escopo limitado a `validate_competitive_intel_schema(conn)` — verificação de que queries executam sem erro de coluna. Implementação completa de métricas (P0-09) é feature separada. 🟢
   - Origem no legado: `_reversa_sdd/opportunity_intel/requirements.md#lacuna-3` + decisão `/reversa-clarify`
   - Tipo: alterada (corrige colunas incompatíveis; validação apenas)

## 5. Requisitos Funcionais

| ID | Requisito | Prioridade | Critério de aceite | Confidência |
|----|-----------|------------|--------------------|-------------|
| RF-01 | Makefile com targets: `run-pipeline` (crawl→report completo), `run-crawl` (só ingestão), `run-report` (só relatórios), `test` (pytest), `lint` (ruff+bandit), `clean` (reset estado local) | Must | `make run-pipeline` executa do zero e produz `output/reports/` com PDF+Excel | 🟢 |
| RF-02 | `docker-compose.local.yml` com PostgreSQL 16 + serviço de aplicação Python 3.12, volumes para `output/` e `config/`. Desenhado para ser reutilizável em VPS (mesma imagem, mesma rede, override só de env vars). Expande o `docker-compose.yml` existente (hoje só test-db). | Must | `docker compose -f docker-compose.local.yml up` sobe banco + app, migrations aplicadas automaticamente. Mesmo compose file funciona local (WSL2) e remoto (VPS) com `--env-file` diferente. | 🟢 |
| RF-03 | `scripts/bootstrap_local.sh` idempotente: cria DB, aplica todas as migrations, carrega seed (2.085 entes SC + 1.093 universo canônico), verifica schema fingerprint | Must | Execução repetida não quebra; segunda execução é no-op | 🟢 |
| RF-04 | Coverage gate: `pytest --cov=scripts --cov-report=term-missing --cov-fail-under=80` para lista explícita de módulos críticos | Must | CI (ruff+pyright+bandit+pytest) falha com exit 2 se coverage < 80% nos módulos gateados | 🟢 |
| RF-05 | Script `scripts/coverage_gate.py`: lê `.coveragerc` com lista de 7 módulos críticos (plano mestre §18: `opportunity_intel`, `reconciliacao`, `coverage`, `contract_pipeline`, `supplier_metrics`, `price_pipeline`, `report_builder`), verifica coverage por módulo, emite JSON com `{module: {coverage_pct, pass/fail}}` e exit code fail-closed (exit 2 se qualquer módulo < 80%) | Must | `coverage_gate.py` → exit 0 se todos ≥ 80%, exit 2 se algum abaixo | 🟢 |
| RF-06 | Snapshot reconciliation: `reconcile_snapshot(conn, run_id, current_bid_ids)` — inativa registros `is_active=TRUE` cujo `bid_id` NÃO está em `current_bid_ids` | Must | Após execução PNCP completa, zero registros ativos fantasmas. `active_snapshot_integrity` = 100% | 🟢 |
| RF-07 | Guarda de execução parcial: reconciliation só roda se `run_outcome.is_complete == True` e `run_outcome.errors == 0` | Must | Execução com `max_pages=5` ou erro HTTP → manifest registra `reconciliation_skipped: partial_run` | 🟢 |
| RF-08 | URL oficial obrigatória: campo `official_url` populado via `source_url` do adapter contract; PRIORITARIA sem URL → downgrade para REVISAR | Should | Todas as oportunidades PRIORITARIA no CSV têm `official_url` preenchida | 🟡 |
| RF-09 | Validação PostgreSQL de competitive intel: `validate_competitive_intel_schema(conn)` verifica que queries de market share, HHI e supplier ranking executam sem erro de coluna contra `db/migrations/026`. Apenas validação — implementação completa de métricas (P0-09) é feature separada. | Should | `validate_competitive_intel_schema()` retorna `SchemaValidation` com `{market_share: pass/fail, hhi: pass/fail, supplier_ranking: pass/fail}`. Colunas inválidas são reportadas mas NÃO corrigidas neste escopo. | 🟢 |
| RF-10 | CI gate unificado: script `scripts/ci_gate.sh` que roda ruff → pyright → bandit → pytest (com coverage gate) → emite JSON de saída com veredito por etapa | Should | `ci_gate.sh` → exit 0 se todos passam, exit 2 se qualquer etapa falha | 🟡 |

## 6. Requisitos Não Funcionais

| Tipo | Requisito | Evidência ou justificativa | Confidência |
|------|-----------|----------------------------|-------------|
| Desempenho | `make run-pipeline` completo executa em < 15 min (PNCP full crawl é o gargalo) | `_reversa_sdd/architecture.md` — sistema single-tenant, VPS CX22 | 🟡 |
| Segurança | `docker-compose.local.yml` NÃO expõe porta PostgreSQL externamente (só `127.0.0.1:5433`) | `_reversa_sdd/deploy/design.md#dependencias` — UFW + fail2ban | 🟢 |
| Observabilidade | CI gate emite JSON estruturado com `{stage: {status, duration_ms, errors[]}}` por etapa | `_reversa_sdd/architecture.md#padrões-de-codigo` — logging JSON + correlation_id | 🟢 |
| Portabilidade | `docker-compose.local.yml` funciona em Linux (WSL2), macOS (Apple Silicon via `platform: linux/amd64`) e VPS Hetzner (Ubuntu 24.04) — mesmo compose file, override só de env vars | WSL2 é ambiente corrente; VPS é target futuro (EPIC P2) | 🟢 |
| Confiabilidade | Snapshot reconciliation é idempotente — segunda execução com mesmo `run_id` é no-op | `_reversa_sdd/domain.md#r8` — content hash SHA-256, idempotência | 🟢 |
| Auditabilidade | Todo run de reconciliação registra `{run_id, bids_inactivated, bids_kept, timestamp}` em `coverage_evidence` | `_reversa_sdd/architecture.md#adr-013` — evidence ledger | 🟢 |

## 7. Critérios de Aceitação

```gherkin
Cenário: Orquestração local reproduzível
  Dado que o ambiente tem Docker e Python 3.12 instalados
  Quando executo `make run-pipeline`
  Então PostgreSQL sobe via docker-compose
  E migrations são aplicadas automaticamente
  E seed é carregada (2.085 entes + 1.093 universo)
  E pipeline executa crawl → transform → enrich → report
  E `output/reports/` contém PDF e Excel
  E exit code é 0

Cenário: Coverage gate bloqueia módulo abaixo de 80%
  Dado que `scripts/lib/universe.py` tem 72% de line coverage
  Quando `pytest --cov=scripts --cov-fail-under=80` executa
  Então pytest falha com exit code ≠ 0
  E `coverage_gate.py` reporta `universe: FAIL (72.0% < 80%)`

Cenário: Snapshot reconciliation inativa fantasmas
  Dado que QW-01 Radar executou PNCP completo sem erros
  E `active_snapshot_integrity` atual é 85% (673 ativos, 572 no snapshot)
  Quando `reconcile_snapshot()` executa
  Então 101 registros são inativados (`is_active=FALSE`)
  E `active_snapshot_integrity` = 100%
  E `coverage_evidence` registra `{event: "snapshot_reconciled", bids_inactivated: 101}`

Cenário: Execução parcial NÃO reconcilia
  Dado que QW-01 Radar executou com `max_pages=5` (parcial)
  Quando o pipeline chega na etapa de reconciliação
  Então reconciliação é pulada
  E manifest registra `reconciliation_skipped: partial_run`
  E NENHUM registro é inativado

Cenário: PRIORITARIA sem URL é degradada
  Dado uma oportunidade com score ≥ 70 (seria PRIORITARIA)
  E `official_url` é NULL ou vazio
  Quando o ranking é calculado
  Então a classificação final é REVISAR
  E `missing_fields` contém "official_url"

Cenário: Competitive intel validado em PostgreSQL real
  Dado conexão PostgreSQL ativa com schema v3 (migration 026+)
  Quando `validate_competitive_intel_schema(conn)` executa
  Então query de market share retorna TOP 20 fornecedores sem erro
  E query de HHI retorna índice por entidade sem erro
  E query de supplier ranking retorna ranking sem erro de coluna
```

## 8. Prioridade MoSCoW

| Item | MoSCoW | Justificativa |
|------|--------|---------------|
| RF-01 (Makefile) | Must | Sem orquestração local, pipeline depende de script manual frágil |
| RF-02 (docker-compose) | Must | PostgreSQL local é hard dependency de todos os módulos |
| RF-03 (bootstrap) | Must | Seed e migrations são pré-requisito para qualquer execução |
| RF-04 (coverage gate) | Must | Bloqueia regressão de qualidade nos módulos críticos |
| RF-05 (coverage_gate.py) | Must | Ferramenta que implementa o gate; sem ela, RF-04 é intenção |
| RF-06 (snapshot reconciliation) | Must | 🔴 P0-04 — radar não é confiável sem isso |
| RF-07 (guarda parcial) | Must | Impede falso-positivo de reconciliação |
| RF-08 (URL oficial) | Should | Fecha lacuna de qualidade, não bloqueia operação |
| RF-09 (competitive intel validation) | Should | Fecha lacuna P0-09 parcial; validação não é implementação completa |
| RF-10 (CI gate unificado) | Should | Consolida gates existentes; ruff+pyright+bandit já rodam separados |

## 9. Esclarecimentos

### Sessão 2026-07-14

- **Q:** Deploy VPS (Hetzner/Supabase, EPIC P2) está fora do escopo — mas a orquestração local (RF-01, RF-02, RF-03) deve ser desenhada para não impedir o futuro deploy remoto?
  **R:** **Future-proof.** `docker-compose.local.yml` será desenhado com mesma imagem e mesma rede para uso local e VPS. Override apenas de env vars (`--env-file`). Makefile usa variáveis (`ENV ?= local`) para alternar entre ambientes. Custo adicional ~20% de esforço, evita reescrita no EPIC P2.

- **Q:** Competitive intel (RF-09): validação de schema é suficiente, ou implementação completa (P0-09) entra no escopo?
  **R:** **Só validação.** RF-09 limitado a `validate_competitive_intel_schema(conn)` — verifica que queries de market share, HHI e supplier ranking executam sem erro de coluna contra `db/migrations/026`. Implementação completa de métricas (P0-09) é feature separada.

- **Q:** Lista exata de módulos críticos para coverage gate (RF-04, RF-05)?
  **R:** **Plano mestre §18.** 7 módulos: `opportunity_intel`, `reconciliacao`, `coverage`, `contract_pipeline`, `supplier_metrics`, `price_pipeline`, `report_builder`. Exatamente como o DoD (Seção 22) exige.

- **Q:** Coverage gate (RF-04): abaixo de 80%, CI falha (exit 2) ou apenas alerta (exit 0 com warning)?
  **R:** **Fail-closed (exit 2).** Consistente com ADR-014 e com Readiness Gate. Bloqueia commit se qualquer módulo crítico < 80%. Sem warn-only, sem threshold progressivo.

## 10. Lacunas

> Nenhuma lacuna pendente. Todos os `[DÚVIDA]` foram resolvidos na sessão 2026-07-14 do `/reversa-clarify`.

## 11. Histórico de alterações

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-14 | Versão inicial gerada por `/reversa-requirements` | reversa |
| 2026-07-14 | Sessão de esclarecimentos: 4 dúvidas resolvidas via `/reversa-clarify`. Decisões: future-proof deploy, validação-only competitive intel, 7 módulos plano mestre §18, fail-closed coverage gate | reversa |
