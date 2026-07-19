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
	@echo '  resilient-smoke       Contrato/fail-closed/checkpoint/DLQ/chaos controlado'
	@echo '  resilient-local-cycle Ciclo canônico local com fixtures (sem VPS/internet)'
	@echo '  resilience-gate       Gate completo de prontidão técnica pré-VPS'
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

# ── CTO Autopilot ───────────────────────────────────────────────────────────

.PHONY: cto-doctor cto-bootstrap cto-observe cto-decide cto-run-once cto-status cto-audit issues-plan issues-sync executive-refresh

cto-doctor:
	python3 -m scripts.cto.cli doctor

cto-bootstrap:
	python3 -m scripts.cto.cli bootstrap

cto-observe:
	python3 -m scripts.cto.cli observe

cto-decide:
	python3 -m scripts.cto.cli decide --dry-run

cto-run-once:
	python3 -m scripts.cto.cli run-once --dry-run

cto-status:
	python3 -m scripts.cto.cli status

cto-audit:
	python3 -m scripts.cto.cli audit

issues-plan:
	python3 -m scripts.cto.cli issues-plan

issues-sync:
	python3 -m scripts.cto.cli issues-sync --dry-run

executive-refresh:
	python3 -m scripts.cto.cli refresh-executive
