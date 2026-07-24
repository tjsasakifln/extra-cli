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
	@echo '── Ciclo semanal Extra (CANÔNICO) ─────────────────────────────────'
	@echo '  extra-weekly    Ciclo operacional semanal: collect→process→quality'
	@echo '                 →intelligence→delivery (manifest+MD+Excel+CSV)'
	@echo '                 python -m scripts.ops.weekly_cycle --strict'
	@echo '  WEEKLY_FLAGS=   Flags extras, ex: --force-collect --skip-collect'
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

.PHONY: extra-weekly
extra-weekly:
	@echo '==> [$(ENV)] Ciclo semanal canônico Extra Construtora'
	@echo '    Entry point: python -m scripts.ops.weekly_cycle --strict'
	@echo '    Open tenders: run_pncp_open_monitoring (aggregated) + SourceSnapshotReconciler'
	python3 -m scripts.ops.weekly_cycle --strict $(WEEKLY_FLAGS)

.PHONY: deliverable-e-live
deliverable-e-live:
	@echo '==> Deliverable E from live DB (operational fail-closed audit)'
	python3 -m scripts.ops.deliverable_e_editais audit-db --operational \
		--out artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/deliverable-e-audit.json

.PHONY: snapshot-integrity
snapshot-integrity:
	@echo '==> Active open-tenders snapshot integrity'
	python3 -m scripts.ops.snapshot_integrity \
		--out artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/snapshot-integrity.json

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
	@echo '==> [$(ENV)] Canonical full suite (no slow exclusion; isolated DSN required)'
	@test -n "$${DATABASE_URL}$${LOCAL_DATALAKE_DSN}" || (echo 'DATABASE_URL or LOCAL_DATALAKE_DSN required for make test-all' && exit 2)
	python -m scripts.ops.run_full_suite

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

# ── Campaign HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01 ─────────────────────

.PHONY: campaign-gate-historical-contracts-vps
campaign-gate-historical-contracts-vps:
	@echo '==> Campaign gate: historical contracts VPS'
	python3 -m scripts.ops.validate_systemd
	bash -n scripts/ops/export_backfill_for_vps.sh
	bash -n scripts/ops/restore_backfill_on_vps.sh
	python3 -m pytest -o addopts='' -q \
		tests/test_contracts_entity_evidence.py \
		tests/test_weekly_cycle.py::test_exit_ok_with_reused_and_products \
		tests/test_weekly_cycle.py::test_exit_unreliable_strict_without_contracts_run \
		tests/test_local_resilience.py::test_systemd_priority_units_are_statically_safe
	@test -f artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/baseline.json
	@echo 'campaign-gate foundation OK (ops evidence still required for PASS)'

# ── Campaign OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01 ─────────────────────

.PHONY: campaign-gate-open-tenders campaign-gate-open-tenders-operational
campaign-gate-open-tenders campaign-gate-open-tenders-operational:
	@echo '==> Campaign gate: open tenders operational decision cycle'
	python3 -m scripts.ops.campaign_open_tenders_gate \
		--out artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/campaign-gate.json
	python3 -m pytest -o addopts='' -q \
		tests/test_open_tenders_campaign_gate.py \
		tests/test_deliverable_e_editais.py \
		tests/test_weekly_cycle.py::test_pncp_opp_sla_default_is_24h \
		tests/test_weekly_cycle.py::test_weekly_collect_uses_aggregated_pncp_audit
	@test -f artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/baseline.json
	@test -f deploy/systemd/extra-weekly.service
	@test -f deploy/systemd/extra-weekly.timer
	@echo 'campaign-gate-open-tenders foundation OK (live coverage/VPS still required for campaign PASS)'

.PHONY: release-candidate-open-tenders
release-candidate-open-tenders:
	@echo '==> release-candidate-open-tenders (fail-closed JSON)'
	python3 -m scripts.ops.campaign_open_tenders_release \
		--out artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/release-candidate.json \
		$(OPEN_TENDERS_RC_FLAGS)

.PHONY: verify-open-tenders-production
verify-open-tenders-production:
	@echo '==> verify-open-tenders-production (local artifacts + ssh ec-prod)'
	python3 -m scripts.ops.campaign_open_tenders_soak \
		--out artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/soak.json || true
	python3 -m scripts.ops.campaign_verify_open_tenders \
		--out artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/verify-production.json \
		$(VERIFY_OPEN_TENDERS_FLAGS)

.PHONY: open-tenders-soak
open-tenders-soak:
	@echo '==> open-tenders soak status (VPS timer/journal)'
	python3 -m scripts.ops.campaign_open_tenders_soak \
		--out artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/soak.json

.PHONY: release-candidate
release-candidate:
	@echo '==> release-candidate wrappers'
	$(MAKE) campaign-gate-historical-contracts-vps
	python3 -m pytest -o addopts='' -q tests/test_contracts_entity_evidence.py tests/test_weekly_cycle.py
	@echo 'release-candidate foundation OK'

.PHONY: verify-production
verify-production:
	@echo '==> verify-production (local artifacts + optional ssh ec-prod)'
	python3 -m scripts.ops.campaign_verify_production \
		--campaign HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01 \
		--output artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/verify-production.json \
		$(VERIFY_PRODUCTION_FLAGS)

# ── Campaign STRATIFIED-RECALL-SOURCE-RESILIENCE-01 ─────────────────────────

.PHONY: campaign-gate-stratified-recall
campaign-gate-stratified-recall:
	@echo '==> Campaign gate: stratified recall source resilience'
	python3 -m scripts.ops.campaign_stratified_recall_gate \
		--out artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/campaign-gate.json
	@test -f artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/baseline.json
	@echo 'campaign-gate-stratified-recall foundation OK (live ≥95% still required for campaign PASS)'

.PHONY: release-candidate-stratified-recall
release-candidate-stratified-recall:
	@echo '==> release-candidate-stratified-recall (fail-closed JSON)'
	python3 -m scripts.ops.campaign_stratified_recall_rc \
		--out artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/release-candidate.json

.PHONY: verify-stratified-recall-isolated
verify-stratified-recall-isolated:
	@echo '==> verify-stratified-recall-isolated (no production DSN)'
	python3 -m scripts.ops.campaign_stratified_recall_verify \
		--sample artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/gold-sample.json \
		--lock artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/sample-lock.json \
		--out artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/verify-isolated.json \
		$(STRATIFIED_RECALL_VERIFY_FLAGS)

