# Actions: Consolidação dos Módulos de Alta Confiança

> Identificador: `001-modulos-alta-confianca`
> Data: 2026-07-14
> Roadmap: `_reversa_forward/001-modulos-alta-confianca/roadmap.md`

## Resumo

| Métrica | Valor |
|---------|-------|
| Total de ações | 21 |
| Paralelizáveis (`[//]`) | 10 |
| Maior cadeia de dependência | 5 (T001→T003→T016) |

## Fase 1, Preparação

| ID | Descrição | Dependências | Paralelismo | Arquivo alvo | Confidência | Status |
|----|-----------|--------------|-------------|--------------|-------------|--------|
| T001 | Criar `docker-compose.local.yml` expandindo o `docker-compose.yml` existente: adicionar serviço `app` (Python 3.12, mesma rede, volumes `output/` e `config/`, env vars para DB e perfil). Manter serviço `test-db` inalterado. | - | `[//]` | `docker-compose.local.yml` | 🟢 | `[X]` |
| T002 | Criar `Makefile` na raiz com variável `ENV ?= local` e targets `.PHONY`: `help`, `run-pipeline`, `run-crawl`, `run-report`, `test`, `lint`, `clean`. Cada target chama scripts Python existentes ou docker compose. | - | `[//]` | `Makefile` | 🟢 | `[X]` |
| T003 | Criar `scripts/bootstrap_local.sh`: script bash idempotente com 4 steps com guardas — (1) `create_db`: sobe PostgreSQL via docker, (2) `run_migrations`: aplica todas migrations v1→v3, (3) `load_seed`: carrega 2.085 entes SC + 1.093 universo canônico, (4) `verify_fingerprint`: checa schema fingerprint. Cada step verifica estado antes de aplicar. | T001 | - | `scripts/bootstrap_local.sh` | 🟢 | `[X]` |
| T004 | Adicionar seção `[coverage_gate]` ao `.coveragerc` (criar se não existir): `modules` com 7 paths (opportunity_intel, coverage, contract_intel, pipeline, lib/universe.py, lib/supplier_metrics.py, lib/price_pipeline.py, reports) e `threshold = 80`. | - | `[//]` | `.coveragerc` | 🟢 | `[X]` |
| T005 | Criar `scripts/ci_gate.sh`: script bash que executa em sequência `ruff check scripts/` → `pyright scripts/` → `bandit -r scripts/` → `pytest -m "not slow" --cov=scripts` → `python scripts/coverage_gate.py`. Cada etapa emite JSON `{stage, status, duration_ms, errors[]}`. Exit code fail-closed: 0 se todos passam, 2 se qualquer falha. | - | `[//]` | `scripts/ci_gate.sh` | 🟢 | `[X]` |

## Fase 2, Testes

| ID | Descrição | Dependências | Paralelismo | Arquivo alvo | Confidência | Status |
|----|-----------|--------------|-------------|--------------|-------------|--------|
| T006 | Criar `scripts/coverage_gate.py`: lê `.coveragerc` seção `[coverage_gate]`, carrega relatório `.coverage` via coverage.py API, verifica `line_coverage_pct >= threshold` por módulo, emite JSON `{module: {coverage_pct, pass}}` + exit code agregado (0 se todos passam, 2 se algum abaixo). | T004 | - | `scripts/coverage_gate.py` | 🟢 | `[X]` |
| T007 | Executar pytest com coverage atual, rodar `coverage_gate.py`, documentar baseline de coverage dos 7 módulos em `output/coverage/baseline-$(date +%Y%m%d).json`. Isso estabelece o ponto de partida antes de melhorar testes. | T006 | - | `output/coverage/baseline-*.json` | 🟢 | `[ ]` |
| T008 | Escrever testes unitários para `reconcile_snapshot()`: (a) reconciliação completa inativa fantasmas, (b) execução parcial NÃO reconcilia, (c) segunda execução com mesmo run_id é no-op, (d) run sem fantasmas não altera nada. Usar mock de conexão PostgreSQL (fixture autouse). | - | `[//]` | `tests/test_snapshot_reconciliation.py` | 🟢 | `[X]` |
| T009 | Escrever teste unitário para URL enforcement no ranking: oportunidade com score ≥ 70 (PRIORITARIA) mas sem `official_url` → downgrade REVISAR com `missing_fields` contendo `"official_url"`. | - | `[//]` | `tests/test_opportunity_ranking.py` | 🟢 | `[X]` |
| T010 | Escrever teste de integração para `validate_competitive_intel_schema()`: conectar PostgreSQL real, executar queries de market share, HHI, supplier ranking, verificar que retornam resultado sem erro de coluna. Usar marcador `@pytest.mark.database`. | - | `[//]` | `tests/test_competitive_intel_validation.py` | 🟡 | `[X]` |

## Fase 3, Núcleo

| ID | Descrição | Dependências | Paralelismo | Arquivo alvo | Confidência | Status |
|----|-----------|--------------|-------------|--------------|-------------|--------|
| T011 | Implementar `reconcile_snapshot(conn, run_id, current_bid_ids)` em `scripts/opportunity_intel/reconciliation.py`: (a) SELECT `bid_id` FROM `opportunity_intel` WHERE `is_active=TRUE`, (b) calcular diff = ativos - current_bid_ids, (c) UPDATE `is_active=FALSE` para bids no diff, (d) INSERT em `coverage_evidence` com `event_type='snapshot_reconciled'` e payload `{bids_inactivated, bids_kept, run_id}`, (e) retornar `ReconciliationResult`. Incluir `--dry-run` flag que reporta sem inativar. | T008 | - | `scripts/opportunity_intel/reconciliation.py` | 🟢 | `[X]` |
| T012 | Implementar URL enforcement em `scripts/opportunity_intel/ranking.py`: após calcular triage, se `triage == 'PRIORITARIA'` e `official_url` é NULL/vazio, downgrade para `'REVISAR'` e adicionar `'official_url'` a `missing_fields`. Regra executada DEPOIS do scoring, ANTES da export. | T009 | - | `scripts/opportunity_intel/ranking.py` | 🟢 | `[X]` |
| T013 | Implementar `validate_competitive_intel_schema(conn)` em `scripts/opportunity_intel/competitive_intel_validation.py`: (a) executar query market share TOP 20 contra `db/migrations/026` schema, capturar `UndefinedColumn` ou similar, (b) executar query HHI por entidade, (c) executar query supplier ranking, (d) retornar `SchemaValidation` dataclass com `{market_share, hhi, supplier_ranking}` cada como `pass/fail` + `error_message` se fail. Read-only, sem corrigir colunas. | T010 | - | `scripts/opportunity_intel/competitive_intel_validation.py` | 🟡 | `[X]` |

## Fase 4, Integração

| ID | Descrição | Dependências | Paralelismo | Arquivo alvo | Confidência | Status |
|----|-----------|--------------|-------------|--------------|-------------|--------|
| T014 | Integrar `reconcile_snapshot()` no pipeline QW-01 Radar (`scripts/opportunity_intel/radar.py`): após export (step 11), antes do manifest final, chamar reconciliação SE `run_outcome.is_complete == True AND run_outcome.errors == 0`. Caso contrário, registrar `reconciliation_skipped: partial_run` no manifest. | T011 | - | `scripts/opportunity_intel/radar.py` | 🟢 | `[X]` |
| T015 | Integrar `coverage_gate.py` no `ci_gate.sh`: verificar que a etapa coverage_gate emite JSON e o exit code agregado é consumido corretamente pelo script. Testar sequência completa: ruff→pyright→bandit→pytest→coverage_gate. | T005, T006 | - | `scripts/ci_gate.sh` | 🟢 | `[X]` |
| T016 | Teste de integração ponta a ponta: executar `./scripts/bootstrap_local.sh` → `make run-pipeline` → verificar `output/reports/` tem PDF+Excel → executar QW-01 Radar → verificar reconciliação no manifest → verificar CSV sem PRIORITARIA sem URL. Documentar resultado em `output/verification/e2e-$(date +%Y%m%d).log`. | T003, T014, T012 | - | `output/verification/e2e-*.log` | 🟡 | `[ ]` |

## Fase 5, Polimento

| ID | Descrição | Dependências | Paralelismo | Arquivo alvo | Confidência | Status |
|----|-----------|--------------|-------------|--------------|-------------|--------|
| T017 | Adicionar logging JSON estruturado em `reconciliation.py`: `log_info` com `{event: "snapshot_reconciliation", run_id, bids_active_before, bids_inactivated, bids_kept, dry_run}`, `log_error` com `{event: "snapshot_reconciliation_failed", error, run_id}`. Consistente com padrão de logging do projeto (ADR-010). | T011 | `[//]` | `scripts/opportunity_intel/reconciliation.py` | 🟢 | `[X]` |
| T018 | Adicionar docstrings (Google style) em todas as funções públicas novas: `reconcile_snapshot()`, `validate_competitive_intel_schema()`, `coverage_gate.main()`. Incluir exemplos de uso, parâmetros, retorno, e edge cases documentados. | T011, T013, T006 | `[//]` | `scripts/opportunity_intel/reconciliation.py`, `scripts/opportunity_intel/competitive_intel_validation.py`, `scripts/coverage_gate.py` | 🟢 | `[X]` |
| T019 | Atualizar `scripts/opportunity_intel/manifest.py`: adicionar campo `reconciliation` ao manifest com `{bids_inactivated, bids_kept, run_id, skipped_reason}`. Métricas de reconciliação visíveis no `coverage` e `source-health`. | T014 | - | `scripts/opportunity_intel/manifest.py` | 🟢 | `[X]` |
| T020 | Adicionar `--dry-run` flag ao `reconcile_snapshot()`: quando True, calcula diff e reporta quais bids seriam inativados, mas NÃO executa UPDATE. Registra em `coverage_evidence` com `event_type='snapshot_reconciliation_dry_run'`. Exposto via CLI: `python scripts/opportunity_intel/cli.py reconcile --dry-run`. | T011 | `[//]` | `scripts/opportunity_intel/reconciliation.py`, `scripts/opportunity_intel/cli.py` | 🟢 | `[X]` |
| T021 | Atualizar `_reversa_sdd/deploy/requirements.md`, `_reversa_sdd/tests/requirements.md`, `_reversa_sdd/opportunity_intel/requirements.md` para refletir as novas implementações. Adicionar novos RFs onde aplicável. Registrar re-extração necessária no state do Reversa. | T016 | - | `_reversa_sdd/deploy/requirements.md`, `_reversa_sdd/tests/requirements.md`, `_reversa_sdd/opportunity_intel/requirements.md` | 🟡 | `[ ]` |

## Notas de execução

<!-- Reservado para /reversa-coding -->

## Histórico de alterações

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-14 | Versão inicial gerada por `/reversa-to-do` | reversa |
