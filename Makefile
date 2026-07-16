# =============================================================================
# Makefile — Extra Consultoria
#
# CLI First, KISS. Use ENV=production para ambientes que não local.
# =============================================================================

ENV ?= local

SCRIPTS_DIR = scripts
TESTS_DIR   = tests
OUTPUT_DIR  = output

# ── Targets ──────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo '╔══════════════════════════════════════════════════════════════╗'
	@echo '║  Extra Consultoria — Makefile                               ║'
	@echo '║  ENV=$(ENV)'
	@echo '╚══════════════════════════════════════════════════════════════╝'
	@echo ''
	@echo 'Usage: make <target> [ENV=local|production]'
	@echo ''
	@echo '── Golden Path ───────────────────────────────────────────────────'
	@echo '  golden-path     Pipeline completo: db-up → bootstrap → crawl'
	@echo '                 (pncp+pcp+compras_gov) → freshness → reports'
	@echo '                 (Excel+PDF). Idempotente.'
	@echo '  golden-path-quick  Igual golden-path mas pula freshness+reports'
	@echo '                 (via --skip-freshness --skip-reports)'
	@echo '  GOLDEN_PATH_FLAGS= Passe flags extras para golden_path.py,'
	@echo '                 ex: make golden-path GOLDEN_PATH_FLAGS="--verbose"'
	@echo ''
	@echo '── Pipeline ──────────────────────────────────────────────────────'
	@echo '  run-pipeline   Executa pipeline completo (bootstrap → crawl →'
	@echo '                 intel → relatório)'
	@echo '  run-crawl      Ingestão: crawl PNCP modo full'
	@echo '  run-report     Relatórios: panorama + Excel'
	@echo '  report-executivo  Relatorio executivo PDF + Excel (Extra Construtora)'
	@echo ''
	@echo '── Testes ─────────────────────────────────────────────────────────'
	@echo '  test           Roda testes (exceto slow) com cobertura'
	@echo '  test-all       Roda todos os testes (inclui slow) com cobertura'
	@echo ''
	@echo '── Lint ───────────────────────────────────────────────────────────'
	@echo '  lint           Verifica lint + formatação (read-only)'
	@echo '  lint-fix       Corrige lint + formata automaticamente'
	@echo ''
	@echo '── Ambiente ───────────────────────────────────────────────────────'
	@echo '  clean          Remove __pycache__, .pytest_cache, .mypy_cache,'
	@echo '                 output/runs/*'
	@echo '  bootstrap      Sobe infra local (idempotente)'
	@echo '  db-up          Sobe banco PostgreSQL via Docker Compose'
	@echo '  db-down        Derruba banco PostgreSQL via Docker Compose'
	@echo ''
	@echo '── ENV ────────────────────────────────────────────────────────────'
	@echo '  current: $(ENV)'
	@echo '  use: make <target> ENV=production'

# ── Golden Path ─────────────────────────────────────────────────────────────

.PHONY: golden-path
golden-path:
	@echo '==> [$(ENV)] Golden Path — Pipeline de validação completa'
	$(MAKE) db-up
	$(MAKE) bootstrap
	python $(SCRIPTS_DIR)/golden_path.py $(GOLDEN_PATH_FLAGS)

.PHONY: golden-path-quick
golden-path-quick:
	@echo '==> [$(ENV)] Golden Path — Rápido (pula freshness e reports)'
	$(MAKE) db-up
	$(MAKE) bootstrap
	python $(SCRIPTS_DIR)/golden_path.py --skip-freshness --skip-reports

# ── Pipeline ────────────────────────────────────────────────────────────────

.PHONY: run-pipeline
run-pipeline:
	@echo '==> [$(ENV)] Pipeline completo: bootstrap → crawl → intel → relatório'
	$(MAKE) bootstrap
	$(MAKE) run-crawl
	python $(SCRIPTS_DIR)/intel_pipeline.py --auto
	$(MAKE) run-report

.PHONY: run-crawl
run-crawl:
	@echo '==> [$(ENV)] Iniciando crawl PNCP modo full'
	python $(SCRIPTS_DIR)/crawl/monitor.py --source pncp --mode full

.PHONY: run-report
run-report:
	@echo '==> [$(ENV)] Gerando relatórios'
	python $(SCRIPTS_DIR)/reports/panorama.py --output-excel

.PHONY: report-executivo
report-executivo:
	@echo '==> [$(ENV)] Gerando relatório executivo PDF + Excel (Extra Construtora)'
	python $(SCRIPTS_DIR)/reports/executive_report.py
	python $(SCRIPTS_DIR)/reports/executive_excel.py
	@echo '==> Relatório executivo gerado em output/reports/'

# ── Testes ──────────────────────────────────────────────────────────────────

.PHONY: test
test:
	@echo '==> [$(ENV)] Rodando testes (exceto slow) com cobertura'
	pytest -m "not slow" --cov=$(SCRIPTS_DIR) --cov-report=term-missing

.PHONY: test-all
test-all:
	@echo '==> [$(ENV)] Rodando todos os testes (inclui slow) com cobertura'
	pytest --cov=$(SCRIPTS_DIR) --cov-report=term-missing

# ── Lint ────────────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	@echo '==> [$(ENV)] Verificando lint e formatação'
	ruff check $(SCRIPTS_DIR)/
	ruff format --check $(SCRIPTS_DIR)/

.PHONY: lint-fix
lint-fix:
	@echo '==> [$(ENV)] Corrigindo lint e formatando'
	ruff check --fix $(SCRIPTS_DIR)/
	ruff format $(SCRIPTS_DIR)/

# ── Ambiente ────────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	@echo '==> [$(ENV)] Limpando artefatos temporários'
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache
	rm -rf $(OUTPUT_DIR)/runs/*

.PHONY: bootstrap
bootstrap:
	@echo '==> [$(ENV)] Bootstrap idempotente'
	bash $(SCRIPTS_DIR)/bootstrap_local.sh

.PHONY: db-up
db-up:
	@echo '==> [$(ENV)] Subindo banco PostgreSQL'
	docker compose -f docker-compose.local.yml up -d

.PHONY: db-down
db-down:
	@echo '==> [$(ENV)] Derrubando banco PostgreSQL'
	docker compose -f docker-compose.local.yml down
