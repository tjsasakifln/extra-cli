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


# --- national intel foundation (migration 060) ---
.PHONY: test-national-intel verify-national-intel-foundation
test-national-intel:
	python -m pytest tests/national_intel/ -q --tb=short

verify-national-intel-foundation:
	@test -f db/migrations/060_national_contracts_intelligence_layers.sql
	@test ! -f db/migrations/059_national_contracts_intelligence_layers.sql

# --- canonical entity linkage (migration 061) ---
.PHONY: test-linkage verify-linkage-foundation
test-linkage:
	python -m pytest tests/test_canonical_entity_linkage.py -q --tb=short

verify-linkage-foundation:
	@test -f db/migrations/061_canonical_entity_linkage.sql

# --- client-ready consulting cycle (integration; no bulk artifacts in git) ---
.PHONY: test-client-ready client-ready-consulting-cycle \
	campaign-gate-client-ready-recurring-consulting-cycle \
	release-candidate-client-ready-recurring-consulting-cycle \
	verify-client-ready-recurring-consulting-cycle-isolated \
	dod-audit-client-ready-recurring-consulting-cycle

test-client-ready:
	python -m pytest \
		tests/test_client_ready_consulting_cycle.py \
		tests/test_commercial_rc_v2_gates.py \
		tests/test_live_consulting_pack.py \
		tests/test_sector_classifier_adversarial.py \
		-q --tb=short

client-ready-consulting-cycle:
	@echo '==> client-ready-consulting-cycle (isolated DSN required)'
	python -m scripts.ops.client_ready_consulting_cycle --help

campaign-gate-client-ready-recurring-consulting-cycle: test-client-ready
	@echo 'campaign-gate-client-ready-recurring-consulting-cycle OK (unit gates)'

release-candidate-client-ready-recurring-consulting-cycle: campaign-gate-client-ready-recurring-consulting-cycle
	@echo 'RC technical only — human acceptance remains PENDING_HUMAN'

verify-client-ready-recurring-consulting-cycle-isolated: test-client-ready
	@test -f scripts/ops/client_ready_consulting_cycle.py
	@test -f db/migrations/060_national_contracts_intelligence_layers.sql
	@test -f db/migrations/061_canonical_entity_linkage.sql
	@echo 'verify-client-ready-recurring-consulting-cycle-isolated OK'

dod-audit-client-ready-recurring-consulting-cycle:
	@echo 'dod-audit-client-ready-recurring-consulting-cycle: technical audit via unit gates'
	$(MAKE) test-client-ready


.PHONY: test-edital-case
test-edital-case:
	python -m pytest tests/edital_case/ -q --tb=short

.PHONY: test-budget-audit
test-budget-audit:
	python -m pytest tests/budget_audit/ -q --tb=short

# --- CONFENGE commercial ready (migration 062/063 + commercial_leads gold) ---
.PHONY: confenge-commercial-cycle \
	campaign-gate-confenge-commercial-ready \
	release-candidate-confenge-commercial-ready \
	verify-confenge-commercial-ready-real \
	verify-soak-non-interference \
	dod-audit-confenge-commercial-ready \
	test-commercial-leads \
	test-confenge-contract-relevance \
	test-confenge-contract-relevance-smoke \
	test-confenge-sector-fit \
	test-confenge-sector-fit-properties \
	verify-confenge-denominator-integrity \
	verify-confenge-full-candidate-history \
	verify-confenge-all-status-history \
	verify-confenge-active-vs-historical-separation \
	verify-confenge-supplier-registry \
	ingest-supplier-registry \
	ingest-confenge-official-cnpj-registry \
	resume-confenge-registry-ingestion \
	verify-supplier-registry-coverage \
	verify-confenge-registry-universe \
	verify-confenge-registry-selection-independence \
	verify-confenge-historical-window \
	export-confenge-authenticated-snapshot \
	verify-confenge-authenticated-snapshot \
	verify-confenge-snapshot-manifest-immutability \
	evaluate-confenge-real-contract-holdout \
	verify-confenge-end-to-end-reproducibility \
	verify-confenge-offer-discrimination \
	verify-confenge-evidence-provenance \
	verify-confenge-source-readonly \
	verify-confenge-state-isolation \
	verify-confenge-snapshot-binding \
	verify-confenge-snapshot-content-binding \
	verify-confenge-full-population \
	verify-confenge-prefilter-recall \
	verify-confenge-ranking-quality \
	verify-confenge-ranking-stability \
	verify-confenge-baseline-superiority \
	verify-confenge-persistence \
	verify-confenge-migrations \
	package-confenge-commercial-evidence \
	verify-confenge-evidence-attestation \
	verify-confenge-commercial-artifact-binding

CONFENGE_COMMERCIAL_PROFILE ?= config/commercial_profiles/confenge.yaml
CONFENGE_COMMERCIAL_OUT ?= artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/run
CONFENGE_COMMERCIAL_ART ?= artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01

test-commercial-leads:
	python3 -m pytest tests/commercial_leads/ -q --tb=short -o addopts=''

test-confenge-contract-relevance:
	python3 -m pytest tests/commercial_leads/test_contract_relevance_adversarial.py -q --tb=short -o addopts=''
	python3 -m scripts.ops.eval_contract_relevance_holdout \
		--holdout evals/commercial_leads/holdout-v1.jsonl \
		--out $(CONFENGE_COMMERCIAL_ART)/contract-relevance-holdout.json

test-confenge-contract-relevance-smoke: test-confenge-contract-relevance
	@echo 'SMOKE_ADVERSARIAL_SET only — not a real performance claim'

test-confenge-sector-fit:
	python3 -m pytest tests/commercial_leads/test_sector_fit.py -q --tb=short -o addopts=''

test-confenge-sector-fit-properties:
	python3 -m pytest tests/commercial_leads/test_sector_fit_properties.py -q --tb=short -o addopts=''

verify-confenge-denominator-integrity:
	python3 -m scripts.ops.verify_confenge_denominator_integrity \
		--out $(CONFENGE_COMMERCIAL_ART)/denominator-integrity.json

verify-confenge-full-candidate-history:
	python3 -m scripts.ops.confenge_make_gates full-candidate-history

verify-confenge-all-status-history:
	python3 -m scripts.ops.confenge_make_gates all-status-history

verify-confenge-active-vs-historical-separation:
	python3 -m scripts.ops.confenge_make_gates active-vs-historical-separation

ingest-supplier-registry:
	@test -n "$$CONFENGE_SUPPLIER_REGISTRY_JSONL" || (echo 'CONFENGE_SUPPLIER_REGISTRY_JSONL required' && exit 1)
	@test -n "$$CONFENGE_COMMERCIAL_STATE_DSN" || (echo 'CONFENGE_COMMERCIAL_STATE_DSN required' && exit 1)
	python3 -c "from scripts.commercial_leads.supplier_registry import ingest_from_jsonl; from scripts.commercial_leads.dbutil import connect; import os,json; c=connect(os.environ['CONFENGE_COMMERCIAL_STATE_DSN']); r=ingest_from_jsonl(c, os.environ['CONFENGE_SUPPLIER_REGISTRY_JSONL']); c.close(); print(json.dumps(r,indent=2))"

ingest-confenge-official-cnpj-registry:
	@test -n "$$CONFENGE_COMMERCIAL_STATE_DSN" || (echo 'CONFENGE_COMMERCIAL_STATE_DSN required' && exit 1)
	python3 -m scripts.ops.confenge_registry_ingest \
		--dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--run-result $(CONFENGE_COMMERCIAL_OUT)/run-result.json

resume-confenge-registry-ingestion:
	@test -n "$$CONFENGE_COMMERCIAL_STATE_DSN" || (echo 'CONFENGE_COMMERCIAL_STATE_DSN required' && exit 1)
	python3 -m scripts.ops.confenge_registry_ingest \
		--dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--run-result $(CONFENGE_COMMERCIAL_OUT)/run-result.json \
		--resume --failures-only

verify-supplier-registry-coverage:
	python3 -m scripts.ops.confenge_make_gates registry-coverage


rerank-confenge-after-registry:
	@test -n "$$CONFENGE_COMMERCIAL_STATE_DSN" || (echo 'CONFENGE_COMMERCIAL_STATE_DSN required' && exit 1)
	python3 -m scripts.ops.confenge_rerank_after_registry \
		--dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--run-result $(CONFENGE_COMMERCIAL_OUT)/run-result.json \
		--out $(CONFENGE_COMMERCIAL_ART)/rerank-after-registry.json

verify-confenge-registry-universe:
	python3 -m scripts.ops.confenge_make_gates registry-universe

verify-confenge-registry-selection-independence:
	python3 -m scripts.ops.confenge_make_gates registry-selection-independence

verify-confenge-historical-window:
	python3 -m scripts.ops.confenge_make_gates historical-window

export-confenge-authenticated-snapshot:
	python3 -m scripts.ops.confenge_make_gates export-authenticated-snapshot

verify-confenge-authenticated-snapshot:
	python3 -m scripts.ops.confenge_make_gates verify-authenticated-snapshot

verify-confenge-snapshot-manifest-immutability:
	python3 -m scripts.ops.confenge_make_gates snapshot-manifest-immutability

extract-confenge-real-holdout-corpus:
	python3 -m scripts.ops.extract_confenge_real_holdout_corpus --min-n 500

evaluate-confenge-real-contract-holdout:
	python3 -m scripts.ops.eval_contract_relevance_real_holdout \
		--holdout evals/commercial_leads/real/holdout-real-v1.jsonl \
		--out $(CONFENGE_COMMERCIAL_ART)/contract-relevance-real-holdout.json

verify-confenge-end-to-end-reproducibility:
	python3 -m scripts.ops.confenge_make_gates end-to-end-reproducibility

verify-confenge-offer-discrimination:
	python3 -m scripts.ops.confenge_make_gates offer-discrimination

verify-confenge-evidence-provenance:
	python3 -m scripts.ops.confenge_make_gates evidence-provenance

verify-confenge-supplier-registry: verify-supplier-registry-coverage

confenge-commercial-cycle:
	@echo '==> confenge-commercial-cycle (CONFENGE commercial intelligence gold)'
	@echo '    Entry: python -m scripts.ops.confenge_commercial_cycle'
	@echo '    Requires: CONFENGE_COMMERCIAL_STATE_DSN + CONFENGE_COMMERCIAL_SNAPSHOT'
	python3 -m scripts.ops.confenge_commercial_cycle \
		--profile $(CONFENGE_COMMERCIAL_PROFILE) \
		--out $(CONFENGE_COMMERCIAL_OUT) \
		$(CONFENGE_CYCLE_FLAGS)

campaign-gate-confenge-commercial-ready:
	python3 -m scripts.ops.confenge_commercial_gates campaign-gate

release-candidate-confenge-commercial-ready: campaign-gate-confenge-commercial-ready
	python3 -m scripts.ops.confenge_commercial_gates release-candidate \
		--run-result $(CONFENGE_COMMERCIAL_OUT)/run-result.json

verify-confenge-commercial-ready-real:
	@echo '==> verify real commercial queue (fails closed without authenticated snapshot)'
	@test -n "$$CONFENGE_COMMERCIAL_STATE_DSN" || (echo 'CONFENGE_COMMERCIAL_STATE_DSN required' && exit 1)
	@test -n "$$CONFENGE_COMMERCIAL_SNAPSHOT" || (echo 'CONFENGE_COMMERCIAL_SNAPSHOT required' && exit 1)
	python3 -m scripts.commercial_leads run \
		--dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--profile $(CONFENGE_COMMERCIAL_PROFILE) \
		--snapshot-manifest "$$CONFENGE_COMMERCIAL_SNAPSHOT" \
		--out $(CONFENGE_COMMERCIAL_OUT) \
		--result-json $(CONFENGE_COMMERCIAL_ART)/real-run.json
	python3 -m scripts.commercial_leads gate \
		--out $(CONFENGE_COMMERCIAL_ART)/gate.json \
		--run-result $(CONFENGE_COMMERCIAL_OUT)/run-result.json
	@test "$$(python3 -c "import json; print(json.load(open('$(CONFENGE_COMMERCIAL_ART)/gate.json'))['ok'])")" = "True"

verify-soak-non-interference:
	python3 -m scripts.ops.verify_soak_non_interference \
		--baseline $(CONFENGE_COMMERCIAL_ART)/soak-baseline.json \
		--final $(CONFENGE_COMMERCIAL_ART)/soak-final.json \
		--out $(CONFENGE_COMMERCIAL_ART)/soak-non-interference.json

dod-audit-confenge-commercial-ready:
	python3 -m scripts.ops.confenge_commercial_gates dod-audit

verify-confenge-source-readonly:
	python3 -m scripts.ops.confenge_make_gates source-state-isolation

verify-confenge-state-isolation:
	python3 -m scripts.ops.confenge_make_gates source-state-isolation

verify-confenge-snapshot-binding verify-confenge-snapshot-content-binding:
	python3 -m scripts.ops.confenge_make_gates snapshot-content-binding

verify-confenge-full-population:
	python3 -m scripts.ops.confenge_make_gates full-population

verify-confenge-prefilter-recall:
	python3 -m scripts.ops.confenge_make_gates prefilter-recall

verify-confenge-ranking-quality:
	python3 -m scripts.ops.confenge_make_gates ranking-quality

verify-confenge-ranking-stability:
	python3 -m scripts.ops.confenge_make_gates ranking-stability

verify-confenge-baseline-superiority:
	python3 -m scripts.ops.confenge_make_gates baseline-superiority

verify-confenge-persistence:
	python3 -m pytest tests/commercial_leads/test_persistence_rollback.py -q --tb=short -o addopts=''

verify-confenge-migrations:
	python3 -m scripts.ops.confenge_make_gates migrations

package-confenge-commercial-evidence:
	python3 -m scripts.ops.confenge_make_gates package-evidence

verify-confenge-evidence-attestation:
	python3 -m scripts.ops.confenge_make_gates verify-attestation

verify-confenge-commercial-artifact-binding:
	python3 -m scripts.ops.verify_confenge_artifact_binding \
		--result $(CONFENGE_COMMERCIAL_ART)/result.json \
		--queue-summary $(CONFENGE_COMMERCIAL_ART)/queue-summary.json


# --- CONFENGE final evidence closure (PR #144) ---
.PHONY: build-confenge-historical-snapshot \
	verify-confenge-historical-snapshot \
	verify-confenge-contract-status-reconciliation \
	download-confenge-official-cnpj-dataset \
	ingest-confenge-official-cnpj-dataset \
	verify-confenge-official-registry-provenance \
	export-confenge-authenticated-snapshot-real \
	restore-confenge-authenticated-snapshot \
	verify-confenge-restored-snapshot \
	verify-confenge-independent-snapshot-anchor \
	verify-confenge-full-universe-e2e-reproducibility \
	extract-confenge-real-contract-corpus \
	verify-confenge-real-corpus-provenance \
	build-confenge-human-review-package \
	verify-confenge-offer-sensitivity \
	verify-confenge-code-freeze \
	verify-confenge-post-execution-artifact-only-diff \
	mark-confenge-code-freeze \
	bulk-confenge-official-cnpj-opencnpj \
	freeze-confenge-final-integrity-code \
	verify-confenge-final-integrity-code-freeze \
	verify-confenge-sha-semantics \
	verify-confenge-executed-tree-integrity \
	verify-confenge-full-pipeline-e2e-reproducibility \
	verify-confenge-downstream-reproducibility \
	verify-confenge-human-review-artifact-package \
	verify-confenge-cross-artifact-consistency \
	build-confenge-final-campaign-status

CONFENGE_COMMERCIAL_STATE_DSN ?= postgresql://postgres:postgres@127.0.0.1:5433/confenge_commercial
CONFENGE_SOURCE_DSN ?= postgresql://postgres:postgres@127.0.0.1:5433/pncp_datalake
CONFENGE_RESTORE_DSN ?= postgresql://postgres:postgres@127.0.0.1:5433/confenge_restore

build-confenge-historical-snapshot:
	python3 -m scripts.ops.confenge_historical_snapshot build \
		--source-dsn "$$CONFENGE_SOURCE_DSN" \
		--target-dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--preferred-days 730 --min-days 365

verify-confenge-historical-snapshot:
	python3 -m scripts.ops.confenge_historical_snapshot verify \
		--target-dsn "$$CONFENGE_COMMERCIAL_STATE_DSN"

verify-confenge-contract-status-reconciliation:
	python3 -m scripts.ops.confenge_historical_snapshot reconcile \
		--target-dsn "$$CONFENGE_COMMERCIAL_STATE_DSN"

download-confenge-official-cnpj-dataset:
	python3 -m scripts.ops.confenge_official_cnpj download || true
	python3 -m scripts.ops.confenge_opencnpj_bulk --workers 12

ingest-confenge-official-cnpj-dataset:
	@test -n "$$CONFENGE_COMMERCIAL_STATE_DSN" || (echo 'CONFENGE_COMMERCIAL_STATE_DSN required' && exit 1)
	python3 -m scripts.ops.confenge_official_cnpj ingest \
		--dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--run-result $(CONFENGE_COMMERCIAL_OUT)/run-result.json

verify-confenge-official-registry-provenance:
	python3 -m scripts.ops.confenge_official_cnpj verify-provenance

bulk-confenge-official-cnpj-opencnpj:
	python3 -m scripts.ops.confenge_opencnpj_bulk --workers 12

# Override export to use real restorable CSV package
export-confenge-authenticated-snapshot:
	python3 -m scripts.ops.confenge_dump_restore export \
		--source-dsn "$$CONFENGE_COMMERCIAL_STATE_DSN"

restore-confenge-authenticated-snapshot:
	python3 -m scripts.ops.confenge_dump_restore restore \
		--source-dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--restore-dsn "$$CONFENGE_RESTORE_DSN"

verify-confenge-restored-snapshot:
	python3 -m scripts.ops.confenge_dump_restore verify \
		--source-dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--restore-dsn "$$CONFENGE_RESTORE_DSN"

verify-confenge-independent-snapshot-anchor: verify-confenge-restored-snapshot

verify-confenge-full-universe-e2e-reproducibility: verify-confenge-downstream-reproducibility

verify-confenge-downstream-reproducibility:
	python3 -m scripts.ops.confenge_full_universe_e2e \
		--dsn "$$CONFENGE_COMMERCIAL_STATE_DSN" \
		--run-result $(CONFENGE_COMMERCIAL_OUT)/run-result.json

verify-confenge-full-pipeline-e2e-reproducibility:
	python3 -m scripts.ops.confenge_full_pipeline_e2e \
		--dsn "$$CONFENGE_COMMERCIAL_STATE_DSN"

extract-confenge-real-contract-corpus:
	python3 -m scripts.ops.extract_confenge_real_holdout_corpus --min-n 500

verify-confenge-real-corpus-provenance:
	python3 -m scripts.ops.confenge_human_review_packages verify-corpus

build-confenge-human-review-package:
	python3 -m scripts.ops.confenge_human_review_packages build

verify-confenge-human-review-artifact-package:
	python3 -m scripts.ops.confenge_human_review_packages verify-package

verify-confenge-offer-sensitivity:
	python3 -m scripts.ops.confenge_offer_sensitivity \
		--dsn "$$CONFENGE_COMMERCIAL_STATE_DSN"

verify-confenge-code-freeze:
	python3 -m scripts.ops.confenge_code_freeze verify-freeze

verify-confenge-post-execution-artifact-only-diff:
	python3 -m scripts.ops.confenge_code_freeze verify-artifact-only

mark-confenge-code-freeze:
	python3 -m scripts.ops.confenge_code_freeze mark-freeze

freeze-confenge-final-integrity-code:
	python3 -m scripts.ops.confenge_code_freeze mark-final-integrity-freeze

verify-confenge-final-integrity-code-freeze:
	python3 -m scripts.ops.confenge_code_freeze verify-final-integrity-freeze

verify-confenge-sha-semantics:
	python3 -m scripts.ops.confenge_code_freeze verify-sha-semantics

verify-confenge-executed-tree-integrity:
	python3 -m scripts.ops.confenge_code_freeze verify-executed-tree-integrity

build-confenge-final-campaign-status:
	python3 -m scripts.ops.confenge_final_status build

verify-confenge-cross-artifact-consistency:
	python3 -m scripts.ops.confenge_final_status verify-consistency

# re-bind evidence provenance to code freeze module
verify-confenge-evidence-provenance:
	python3 -m scripts.ops.confenge_code_freeze verify-provenance


# =============================================================================
# Edital relevance recall foundation (DOD §8.4) — blocked on human dual labeling
# Foundation green ≠ DOD accept. Final gate must fail until human gold exists.
# =============================================================================
.PHONY: test-edital-relevance-foundation verify-edital-relevance-final

test-edital-relevance-foundation:
	@echo "=== Edital relevance foundation (evaluator + human workflow) ==="
	python3 -m pytest \
		tests/coverage/test_edital_relevance_recall.py \
		tests/coverage/test_human_labeling.py \
		-q --tb=short -o addopts=''
	@mkdir -p artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01
	python3 -m scripts.coverage.edital_relevance_recall diagnose \
		--corpus evals/edital_relevance/machine_draft_candidate_pool.jsonl \
		--manifest evals/edital_relevance/machine_draft_candidate_pool-manifest.json \
		--output artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/machine_diagnostic_result.json \
		> artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/machine_diagnostic_stdout.txt
	@python3 -c "import json; r=json.load(open('artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/machine_diagnostic_result.json')); assert r['status']=='DIAGNOSTIC_ONLY' and r['pass'] is False and r['acceptance_eligible'] is False and r['dod_item_accepted'] is False and r.get('sealed_holdout') is False; print('diagnostic OK: DIAGNOSTIC_ONLY / non-accept')"
	@test -f evals/edital_relevance/pilot_36_reviewer_a.csv
	@test -f evals/edital_relevance/pilot_36_reviewer_b.csv
	@echo "foundation gate PASS"

verify-edital-relevance-final:
	@echo "=== Edital relevance FINAL accept gate (expect BLOCKED_HUMAN_DUAL_LABELING) ==="
	@set +e; \
	python3 -m scripts.coverage.edital_relevance_recall evaluate-final \
		--corpus evals/edital_relevance/machine_draft_candidate_pool.jsonl \
		--manifest evals/edital_relevance/machine_draft_candidate_pool-manifest.json \
		--output artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/final-gate-result.json \
		> artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/final-gate-stdout.txt 2> artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/final-gate-stderr.txt; \
	code=$$?; \
	set -e; \
	if [ $$code -eq 0 ]; then echo "ERROR: final gate must not pass without human gold"; exit 1; fi; \
	if ! grep -q 'BLOCKED_HUMAN_DUAL_LABELING' artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/final-gate-stderr.txt artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/final-gate-stdout.txt artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/final-gate-result.json; then \
		echo "ERROR: missing blocker BLOCKED_HUMAN_DUAL_LABELING"; exit 1; fi; \
	echo "final gate correctly blocked: BLOCKED_HUMAN_DUAL_LABELING"

