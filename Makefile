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
	@echo '── PRODUCT (canonical weekly cycle) ─────────────────────────────'
	@echo '  extra-weekly    ONLY product ops entry for Extra consultive pack'
	@echo '                 python -m scripts.ops.weekly_cycle --strict'
	@echo '  WEEKLY_FLAGS=   Extra flags for weekly_cycle'
	@echo ''
	@echo '── ENGINEERING (not product orchestrator) ───────────────────────'
	@echo '  verify          Canonical engineering check: lint + weekly tests'
	@echo '  lint / lint-fix  Ruff check / autofix'
	@echo '  test / test-all   Pytest suites'
	@echo ''
	@echo '── DIAGNOSTIC (not product) ─────────────────────────────────────'
	@echo '  golden-path / golden-path-quick   Validation pipelines'
	@echo '  resilient-local-cycle / resilient-smoke / resilience-gate'
	@echo ''
	@echo '── LEGACY / COMPONENT ───────────────────────────────────────────'
	@echo '  run-pipeline    LEGACY composite (prefer extra-weekly)'
	@echo '  run-crawl / run-report / report-executivo'
	@echo ''
	@echo '── Ambiente ─────────────────────────────────────────────────────'
	@echo '  clean / bootstrap / db-up / db-down'
	@echo ''
	@echo '── ENV ──────────────────────────────────────────────────────────'
	@echo '  current: $(ENV)'
	@echo '  use: make <target> ENV=production'
	@echo ''
	@echo 'Classification: docs/canonical-entry-points.yaml (entrypoint_classification)'

# ── Golden Path ─────────────────────────────────────────────────────────────

.PHONY: golden-path
golden-path:
	@echo '==> [$(ENV)] DIAGNOSTIC golden-path (not product weekly cycle)'
	@echo '    Class: diagnostic'
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
	@echo '==> [$(ENV)] LEGACY composite pipeline (NOT Extra product canonical)'
	@echo '    Prefer: make extra-weekly'
	@echo '    Class: legacy_composite'
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

.PHONY: extra-weekly
extra-weekly:
	@echo '==> [$(ENV)] PRODUCT CANONICAL — Extra weekly consultive cycle'
	@echo '    Entry point: python -m scripts.ops.weekly_cycle --strict'
	@echo '    Class: product_canonical (see docs/canonical-entry-points.yaml)'
	python3 -m scripts.ops.weekly_cycle --strict $(WEEKLY_FLAGS)

.PHONY: verify
verify:
	@echo '==> [$(ENV)] ENGINEERING verify — not a product orchestrator'
	@echo '    Class: engineering (lint + weekly unit tests)'
	ruff check $(SCRIPTS_DIR)/ops/weekly_cycle.py $(SCRIPTS_DIR)/ops/canonical_entry_points.py
	python3 -m pytest $(TESTS_DIR)/test_weekly_cycle.py -q --tb=line --no-cov
	@if [ -f $(TESTS_DIR)/architecture/test_weekly_characterization.py ]; then \
		python3 -m pytest $(TESTS_DIR)/architecture/test_weekly_characterization.py -q --tb=line --no-cov; \
	fi
	python3 -m scripts.ops.canonical_entry_points --json >/dev/null
	@echo '==> verify OK'

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

.PHONY: resilient-smoke
resilient-smoke:
	python3 -m scripts.ops.validate_systemd
	python3 -m pytest -o addopts='' -q \
		tests/test_local_resilience.py \
		tests/test_resilience_vertical_slice.py \
		tests/test_fetch_result.py \
		tests/test_crawler_pncp.py \
		tests/test_sc_compras_crawler.py \
		tests/test_ciga_dom_publications.py \
		tests/test_dlq.py \
		tests/test_watermark.py \
		-m "not database and not slow"

.PHONY: resilient-local-cycle
resilient-local-cycle:
	RESILIENCE_ENV=fixture RESILIENCE_REQUIRE_DB=0 RESILIENCE_PAGE_SIZE=1 RESILIENCE_REQUEST_DELAY=0 \
		python3 -m scripts.ops.resilient_cycle --env fixture
	# Fixture health may be green; live health must stay blocked without live evidence.
	python3 -m scripts.ops.health --env fixture
	@python3 -c "from scripts.ops.health import collect_health; import sys; c,_=collect_health(env='development'); sys.exit(0 if c==2 else 1)"

.PHONY: resilience-gate
resilience-gate:
	ruff check scripts/crawl/ingestion/_base/crawler.py scripts/crawl/resilience scripts/ops tests/test_local_resilience.py tests/test_resilience_vertical_slice.py
	mypy --follow-imports=skip \
		scripts/crawl/ingestion/_base/crawler.py \
		scripts/crawl/resilience \
		scripts/ops/resilient_cycle.py \
		scripts/ops/health.py \
		scripts/ops/validate_systemd.py
	$(MAKE) resilient-smoke
	$(MAKE) resilient-local-cycle

.PHONY: pre-vps-final-gate-offline
pre-vps-final-gate-offline:
	@echo '==> pre-vps-final-gate-offline (no internet)'
	$(MAKE) resilience-gate
	python3 -m pytest -o addopts='' -q tests/test_local_resilience.py tests/test_resilience_vertical_slice.py -m "not database and not slow and not e2e"

.PHONY: pre-vps-live-canary
pre-vps-live-canary:
	@echo '==> pre-vps-live-canary (real sources; never in CI auto)'
	@test -n "$${DATABASE_URL}$${LOCAL_DATALAKE_DSN}" || (echo 'DATABASE_URL or LOCAL_DATALAKE_DSN required for live canary with DB' && exit 2)
	RESILIENCE_ENV=development RESILIENCE_REQUIRE_DB=1 \
		python3 -m scripts.ops.resilient_cycle --live --env development --source pncp
	RESILIENCE_ENV=development RESILIENCE_REQUIRE_DB=1 \
		python3 -m scripts.ops.resilient_cycle --live --env development --source ciga_dom
	RESILIENCE_ENV=development RESILIENCE_REQUIRE_DB=1 \
		python3 -m scripts.ops.resilient_cycle --live --env development --source sc_compras
	python3 -m scripts.ops.health --env development

.PHONY: pre-vps-final-gate
pre-vps-final-gate:
	@echo '==> pre-vps-final-gate (offline + recent live canary evidence)'
	$(MAKE) pre-vps-final-gate-offline
	python3 -c "from scripts.ops.health import collect_health; import sys; c,r=collect_health(env='development'); print(r); sys.exit(0 if c==0 else 2)"

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
