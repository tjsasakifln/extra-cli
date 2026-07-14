# Code/Spec Matrix — Extra Consultoria

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1
> Atualizado pelo Writer em 2026-07-13. +9 modulos adicionados (opportunity_intel, contract_intel, coverage, fix, pipeline, diagnose, transparencia, tests, root_scripts).
> **Migracao 2026-07-13:** Legacy Intel Pipeline scripts (kebab-case) migrados de `intel/` para `root_scripts/` — todos residem em `scripts/` top-level.
> **Expandido pelo Dev (Dex) em 2026-07-13:** Adicionados ALL Python files faltantes. +108 novas entradas: crawl/ subdirs, lib/, matching/, reports/, tests/ individuais. Total: 255 entradas.

## Mapeamento: Arquivos Legado → Units

| Arquivo do legado | Unit | Cobertura |
|-------------------|------|-----------|
| `scripts/crawl/__init__.py` | `crawl/` | 🟢 |
| `scripts/crawl/_parallel_mixin.py` | `crawl/` | 🟢 |
| `scripts/crawl/adapter.py` | `crawl/` | 🟢 |
| `scripts/crawl/async_client.py` | `crawl/` | 🟡 async legado |
| `scripts/crawl/batch_detect_platforms.py` | `crawl/` | 🟢 |
| `scripts/crawl/batch_detect_platforms_pass2.py` | `crawl/` | 🟢 |
| `scripts/crawl/bids_crawler.py` | `crawl/` | 🟡 DEPRECATED |
| `scripts/crawl/checkpoint.py` | `crawl/` | 🟢 |
| `scripts/crawl/ciga_ckan_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/circuit_breaker.py` | `crawl/` | 🟢 |
| `scripts/crawl/clients/__init__.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/clients/base/__init__.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/clients/base/base.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/clients/pncp/__init__.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/clients/pncp/_parallel_mixin.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/clients/pncp/async_client.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/clients/pncp/circuit_breaker.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/clients/pncp/retry.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/common.py` | `crawl/` | 🟢 |
| `scripts/crawl/compras_gov_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/config.py` | `crawl/` | 🟢 |
| `scripts/crawl/contracts_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/credential_validator.py` | `crawl/` | 🟢 |
| `scripts/crawl/degradation.py` | `crawl/` | 🟢 |
| `scripts/crawl/doe_sc_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/doe_sc_selenium_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/dom_sc_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/enricher.py` | `crawl/` | 🟢 |
| `scripts/crawl/exceptions.py` | `crawl/` | 🟢 |
| `scripts/crawl/generate_transparencia_config.py` | `crawl/` | 🟢 |
| `scripts/crawl/ingestion/__init__.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/ingestion/_base/__init__.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/ingestion/_base/crawler.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/ingestion/checkpoint.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/ingestion/config.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/ingestion/loader.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/ingestion/metrics.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/ingestion/transformer.py` | `crawl/` | 🟡 subdir não analisado |
| `scripts/crawl/loader.py` | `crawl/` | 🟢 |
| `scripts/crawl/metrics.py` | `crawl/` | 🟢 |
| `scripts/crawl/middleware.py` | `crawl/` | 🟢 |
| `scripts/crawl/mides_bigquery_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/monitor.py` | `crawl/` | 🟢 |
| `scripts/crawl/orchestrator.py` | `crawl/` | 🟢 |
| `scripts/crawl/pcp_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/playwright_fallback.py` | `crawl/` | 🟢 |
| `scripts/crawl/pncp_arp_crawler.py` | `crawl/` | 🟡 async legado |
| `scripts/crawl/pncp_contract.py` | `crawl/` | 🟢 |
| `scripts/crawl/pncp_crawler_adapter.py` | `crawl/` | 🟢 |
| `scripts/crawl/pncp_engineering.py` | `crawl/` | 🟢 |
| `scripts/crawl/pncp_geo.py` | `crawl/` | 🟢 |
| `scripts/crawl/pncp_pca_crawler.py` | `crawl/` | 🟡 async legado |
| `scripts/crawl/rate_limiter.py` | `crawl/` | 🟢 |
| `scripts/crawl/redis_pool.py` | `crawl/` | 🟢 |
| `scripts/crawl/registry.py` | `crawl/` | 🟢 |
| `scripts/crawl/retry.py` | `crawl/` | 🟢 |
| `scripts/crawl/sanctions.py` | `crawl/` | 🟢 |
| `scripts/crawl/sc_compras_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/security.py` | `crawl/` | 🟢 |
| `scripts/crawl/selenium_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/selenium_crawler_adapter.py` | `crawl/` | 🟢 |
| `scripts/crawl/selenium_smoke_test.py` | `crawl/` | 🟢 |
| `scripts/crawl/supabase_client.py` | `crawl/` | 🟢 |
| `scripts/crawl/sync_client.py` | `crawl/` | 🟡 parcial |
| `scripts/crawl/tce_sc_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/transformer.py` | `crawl/` | 🟢 |
| `scripts/crawl/transparencia_crawler.py` | `crawl/` | 🟢 |
| `scripts/crawl/transparencia_templates/__init__.py` | `crawl/` | 🟢 |
| `scripts/crawl/transparencia_templates/base.py` | `crawl/` | 🟢 |
| `scripts/crawl/transparencia_templates/betha.py` | `crawl/` | 🟢 |
| `scripts/crawl/transparencia_templates/egov.py` | `crawl/` | 🟢 |
| `scripts/crawl/transparencia_templates/generico.py` | `crawl/` | 🟢 |
| `scripts/crawl/transparencia_templates/ipam.py` | `crawl/` | 🟢 |
| `scripts/crawl/transparencia_templates/selenium_base.py` | `crawl/` | 🟢 |
| `scripts/intel_pipeline.py` | `root_scripts/` | 🟢 |
| `scripts/intel-collect.py` | `root_scripts/` | 🟢 |
| `scripts/intel-enrich.py` | `root_scripts/` | 🟢 |
| `scripts/intel-validate.py` | `root_scripts/` | 🟢 |
| `scripts/intel-analyze.py` | `root_scripts/` | 🟢 |
| `scripts/intel-extract-docs.py` | `root_scripts/` | 🟢 |
| `scripts/intel-excel.py` | `root_scripts/` | 🟢 |
| `scripts/intel-report.py` | `root_scripts/` | 🟢 |
| `scripts/matching/__init__.py` | `matching/` | 🟢 |
| `scripts/matching/entity_matcher.py` | `matching/` | 🟢 |
| `scripts/matching/measure_baseline.py` | `matching/` | 🟡 não analisado |
| `scripts/lib/__init__.py` | `lib/` | 🟢 |
| `scripts/lib/bid_simulator.py` | `lib/` | 🟢 |
| `scripts/lib/cli_validation.py` | `lib/` | 🟢 |
| `scripts/lib/constants.py` | `lib/` | 🟢 |
| `scripts/lib/cost_estimator.py` | `lib/` | 🟢 |
| `scripts/lib/doc_templates.py` | `lib/` | 🟢 |
| `scripts/lib/entity_hierarchy.py` | `lib/` | 🟢 |
| `scripts/lib/geocode.py` | `lib/` | 🟢 |
| `scripts/lib/intel_logging.py` | `lib/` | 🟢 |
| `scripts/lib/name_normalizer.py` | `lib/` | 🟢 |
| `scripts/lib/retry.py` | `lib/` | 🟢 |
| `scripts/lib/universe.py` | `lib/` | 🟢 |
| `scripts/lib/value_semantics.py` | `lib/` | 🟢 |
| `scripts/lib/victory_profile.py` | `lib/` | 🟢 |
| `scripts/lib/win_loss_tracker.py` | `lib/` | 🟢 |
| `scripts/reports/__init__.py` | `reports/` | 🟢 |
| `scripts/reports/coverage_gaps.py` | `reports/` | 🟢 |
| `scripts/reports/coverage_weekly.py` | `reports/` | 🟢 |
| `scripts/reports/panorama.py` | `reports/` | 🟢 |
| `scripts/generate-proposta-pdf.py` | `reports/` | 🟢 |
| `scripts/generate-report-b2g.py` | `reports/` | 🟢 |
| `scripts/report_dedup.py` | `reports/` | 🟢 |
| `config/settings.py` | `config/` | 🟢 |
| `config/logging_config.py` | `config/` | 🟢 |
| `config/sectors_config.yaml` | `config/` | 🟢 |
| `config/sectors_data.yaml` | `config/` | 🟢 |
| `config/abbreviations.yaml` | `config/` | 🟢 |
| `config/transparencia_config.yaml` | `config/` | 🟢 |
| `db/migrations/*` | `db/` | 🟢 |
| `db/seed/*` | `db/` | 🟢 |
| `db/setup_db.sh` | `db/` | 🟢 |
| `db/backup-database.sh` | `db/` | 🟢 |
| `supabase/migrations/*` | `db/` | 🟢 |
| `deploy/install.sh` | `deploy/` | 🟢 |
| `deploy/provision-vps.sh` | `deploy/` | 🟢 |
| `deploy/systemd/*` | `deploy/` | 🟢 |
| `deploy/hardening/*` | `deploy/` | 🟢 |
| `docs/td-001/*` | `docs/` | 🟢 |
| `docs/architecture/*` | `docs/` | 🟢 |
| `docs/prd/*` | `docs/` | 🟢 |
| `docs/qa/*` | `docs/` | 🟡 |
| `docs/ops/*` | `docs/` | 🟡 |
| `docs/stories/*` | `docs/` | 🟡 |
| `scripts/opportunity_intel/__init__.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/backfill.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/cli.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/crawler_base.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/dedup.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/manifest.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/models.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/pncp_audit.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/pncp_crawler.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/profile.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/radar.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/ranking.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/schema.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/scoring.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/status.py` | `opportunity_intel/` | 🟢 |
| `scripts/opportunity_intel/transformer.py` | `opportunity_intel/` | 🟢 |
| `scripts/contract_intel/__init__.py` | `contract_intel/` | 🟢 |
| `scripts/contract_intel/cli.py` | `contract_intel/` | 🟢 |
| `scripts/contract_intel/target_universe.py` | `contract_intel/` | 🟢 |
| `scripts/coverage/__init__.py` | `coverage/` | 🟢 |
| `scripts/coverage/calculator.py` | `coverage/` | 🟢 |
| `scripts/coverage/measure_pncp_expansion.py` | `coverage/` | 🟢 |
| `scripts/coverage/run_matching.py` | `coverage/` | 🟢 |
| `scripts/coverage/validate_coverage.py` | `coverage/` | 🟢 |
| `scripts/coverage_truth.py` | `coverage/` | 🟢 |
| `scripts/consulting_readiness.py` | `coverage/` | 🟢 |
| `scripts/freshness_gate.py` | `coverage/` | 🟢 |
| `scripts/fix/__init__.py` | `fix/` | 🟢 |
| `scripts/fix/activate_dormant_sources.py` | `fix/` | 🟢 |
| `scripts/fix/geocode_missing_entities.py` | `fix/` | 🟢 |
| `scripts/fix/rebuild_evidence_ledger.py` | `fix/` | 🟢 |
| `scripts/fix/resolve_unresolved_entities.py` | `fix/` | 🟢 |
| `scripts/fix/sc_dados_abertos_backfill.py` | `fix/` | 🟢 |
| `scripts/fix/scrape_residual_portals.py` | `fix/` | 🟢 |
| `scripts/pipeline/__init__.py` | `pipeline/` | 🟢 |
| `scripts/pipeline/backfill_multi_source.py` | `pipeline/` | 🟢 |
| `scripts/diagnose/dom_sc_diagnostic.py` | `diagnose/` | 🟢 |
| `scripts/transparencia/run_detect_all.py` | `transparencia/` | 🟢 |
| `tests/__init__.py` | `tests/` | 🟢 |
| `tests/conftest.py` | `tests/` | 🟢 |
| `tests/conftest_db.py` | `tests/` | 🟢 |
| `tests/fixtures/ciga_ckan_ac_data.py` | `tests/` | 🟢 |
| `tests/smoke/test_qw01_pncp_smoke.py` | `tests/` | 🟢 |
| `tests/smoke/test_smoke_contract_intel.py` | `tests/` | 🟢 |
| `tests/smoke/test_smoke_sources.py` | `tests/` | 🟢 |
| `tests/test_backfill_count_covered.py` | `tests/` | 🟢 |
| `tests/test_backfill_pipeline.py` | `tests/` | 🟢 |
| `tests/test_cache_ibge.py` | `tests/` | 🟢 |
| `tests/test_checkpoint.py` | `tests/` | 🟢 |
| `tests/test_ciga_ckan_ac_validation.py` | `tests/` | 🟢 |
| `tests/test_ciga_ckan_crawler.py` | `tests/` | 🟢 |
| `tests/test_common.py` | `tests/` | 🟢 |
| `tests/test_compras_gov_crawler.py` | `tests/` | 🟢 |
| `tests/test_consulting_readiness.py` | `tests/` | 🟢 |
| `tests/test_contract_intel_cli.py` | `tests/` | 🟢 |
| `tests/test_contract_intel_crawl.py` | `tests/` | 🟢 |
| `tests/test_contract_intel_target.py` | `tests/` | 🟢 |
| `tests/test_contract_intel_truth_v1.py` | `tests/` | 🟢 |
| `tests/test_contracts_crawler.py` | `tests/` | 🟢 |
| `tests/test_coverage_calculator.py` | `tests/` | 🟢 |
| `tests/test_coverage_only_evidence.py` | `tests/` | 🟢 |
| `tests/test_coverage_truth.py` | `tests/` | 🟢 |
| `tests/test_crawler_pncp.py` | `tests/` | 🟢 |
| `tests/test_crawler_protocol.py` | `tests/` | 🟢 |
| `tests/test_datalake_helper.py` | `tests/` | 🟢 |
| `tests/test_date_propagation.py` | `tests/` | 🟢 |
| `tests/test_doe_sc_crawler.py` | `tests/` | 🟢 |
| `tests/test_e2e_external.py` | `tests/` | 🟢 |
| `tests/test_entity_hierarchy.py` | `tests/` | 🟢 |
| `tests/test_entity_matcher.py` | `tests/` | 🟢 |
| `tests/test_evidence_projection_db.py` | `tests/` | 🟢 |
| `tests/test_fetch_result.py` | `tests/` | 🟢 |
| `tests/test_freshness_gate.py` | `tests/` | 🟢 |
| `tests/test_geocode.py` | `tests/` | 🟢 |
| `tests/test_integration_crawl.py` | `tests/` | 🟢 |
| `tests/test_intel_pipeline.py` | `tests/` | 🟢 |
| `tests/test_manifest.py` | `tests/` | 🟢 |
| `tests/test_mides_bigquery_crawler.py` | `tests/` | 🟢 |
| `tests/test_monitoring.py` | `tests/` | 🟢 |
| `tests/test_opportunity_dedup.py` | `tests/` | 🟢 |
| `tests/test_opportunity_integration.py` | `tests/` | 🟢 |
| `tests/test_opportunity_models.py` | `tests/` | 🟢 |
| `tests/test_opportunity_ranking.py` | `tests/` | 🟢 |
| `tests/test_opportunity_status.py` | `tests/` | 🟢 |
| `tests/test_opportunity_transformer.py` | `tests/` | 🟢 |
| `tests/test_orchestrator.py` | `tests/` | 🟢 |
| `tests/test_pcp_crawler.py` | `tests/` | 🟢 |
| `tests/test_pncp_contract.py` | `tests/` | 🟢 |
| `tests/test_pncp_pipeline_db.py` | `tests/` | 🟢 |
| `tests/test_qw01_postgres.py` | `tests/` | 🟢 |
| `tests/test_qw01_radar.py` | `tests/` | 🟢 |
| `tests/test_report_dedup.py` | `tests/` | 🟢 |
| `tests/test_resolve_unresolved_entities.py` | `tests/` | 🟢 |
| `tests/test_sc_compras_crawler.py` | `tests/` | 🟢 |
| `tests/test_sc_dados_abertos_backfill.py` | `tests/` | 🟢 |
| `tests/test_scrape_residual_portals.py` | `tests/` | 🟢 |
| `tests/test_selenium_crawler_adapter.py` | `tests/` | 🟢 |
| `tests/test_tce_sc_live.py` | `tests/` | 🟢 |
| `tests/test_transformer.py` | `tests/` | 🟢 |
| `tests/test_transparencia_crawler.py` | `tests/` | 🟢 |
| `tests/test_universe.py` | `tests/` | 🟢 |
| `tests/test_upsert_contracts.py` | `tests/` | 🟢 |
| `scripts/__init__.py` | `root_scripts/` | 🟢 |
| `scripts/_pt_accents.py` | `root_scripts/` | 🟢 |
| `scripts/auditor_deterministic_checks.py` | `root_scripts/` | 🟢 |
| `scripts/build-proposta-data.py` | `root_scripts/` | 🟢 |
| `scripts/check-alerts.py` | `root_scripts/` | 🟢 |
| `scripts/check_imports.py` | `root_scripts/` | 🟢 |
| `scripts/collect-metrics.py` | `root_scripts/` | 🟢 |
| `scripts/collect-report-data.py` | `root_scripts/` | 🟢 |
| `scripts/collect-sicaf.py` | `root_scripts/` | 🟢 |
| `scripts/collect_report_data.py` | `root_scripts/` | 🟢 |
| `scripts/datalake-sc-200km.py` | `root_scripts/` | 🟢 |
| `scripts/datalake_helper.py` | `root_scripts/` | 🟢 |
| `scripts/demo_b2g_setorial.py` | `root_scripts/` | 🟢 |
| `scripts/export-sc-200km-final.py` | `root_scripts/` | 🟢 |
| `scripts/generate_consultoria_pdf.py` | `root_scripts/` | 🟢 |
| `scripts/generate_proposta_pdf.py` | `root_scripts/` | 🟢 |
| `scripts/health-dashboard.py` | `root_scripts/` | 🟢 |
| `scripts/health_check.py` | `root_scripts/` | 🟢 |
| `scripts/healthcheck.py` | `root_scripts/` | 🟢 |
| `scripts/intel_collect.py` | `root_scripts/` | 🟢 |
| `scripts/intel_excel.py` | `root_scripts/` | 🟢 |
| `scripts/intel_llm_gate.py` | `root_scripts/` | 🟢 |
| `scripts/intel_report.py` | `root_scripts/` | 🟢 |
| `scripts/intel_sector_loader.py` | `root_scripts/` | 🟢 |
| `scripts/intel_validate.py` | `root_scripts/` | 🟢 |
| `scripts/local_datalake.py` | `root_scripts/` | 🟢 |
| `scripts/notify.py` | `root_scripts/` | 🟢 |
| `scripts/pncp_client.py` | `root_scripts/` | 🟢 |
| `scripts/pricing-b2g-collect.py` | `root_scripts/` | 🟢 |
| `scripts/radar-b2g-collect.py` | `root_scripts/` | 🟢 |
| `scripts/retention-b2g-collect.py` | `root_scripts/` | 🟢 |
| `scripts/validate-report-data.py` | `root_scripts/` | 🟢 |
| `scripts/war-room-b2g-collect.py` | `root_scripts/` | 🟢 |

## Sumário

| Cobertura | Count | % |
|-----------|-------|---|
| 🟢 Completa | 238 | 90.5% |
| 🟡 Parcial/Não analisado | 25 | 9.5% |
| 🔴 Não mapeado | 0 | 0% |
| **Total** | **263** | **100%** |

**Nota:** Atualizado em 2026-07-13 pelo Dev (Dex). Expansão completa ALL Python files: 178 em `scripts/` + 64 em `tests/` agora mapeados individualmente. +116 novas entradas adicionadas (263 total). Destaques: `transparencia_templates/` (7 individuais), `crawl/clients/` (7), `crawl/ingestion/` (8), `lib/` (5 novos: `__init__`, `entity_hierarchy`, `geocode`, `universe`, `value_semantics`), `matching/measure_baseline.py`, `reports/__init__.py`, `tests/` (64 individuais substituindo entrada genérica). 25 entradas marcadas 🟡: subdirs não analisados (`clients/`, `ingestion/`), deprecados (`bids_crawler`) e legado async (`async_client`, `pncp_arp_crawler`, `pncp_pca_crawler`).

**Migracao:** Legacy Intel Pipeline scripts — documentados originalmente como `intel/`, migrados para `root_scripts/` em 2026-07-13. Os scripts residem em `scripts/` (top-level) e sao referenciados como `root_scripts/`. Consulte `_reversa_sdd/intel/README.md` para historico.
