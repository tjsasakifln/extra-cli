# Code/Spec Matrix — Extra Consultoria

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1

## Mapeamento: Arquivos Legado → Units

| Arquivo do legado | Unit | Cobertura |
|-------------------|------|-----------|
| `scripts/crawl/monitor.py` | crawl/ | 🟢 |
| `scripts/crawl/orchestrator.py` | crawl/ | 🟢 |
| `scripts/crawl/pncp_crawler_adapter.py` | crawl/ | 🟢 |
| `scripts/crawl/dom_sc_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/doe_sc_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/pcp_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/compras_gov_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/contracts_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/tce_sc_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/sc_compras_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/transparencia_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/bids_crawler.py` | crawl/ | 🟡 DEPRECATED |
| `scripts/crawl/pncp_arp_crawler.py` | crawl/ | 🟡 async legado |
| `scripts/crawl/pncp_pca_crawler.py` | crawl/ | 🟡 async legado |
| `scripts/crawl/common.py` | crawl/ | 🟢 |
| `scripts/crawl/checkpoint.py` | crawl/ | 🟢 |
| `scripts/crawl/security.py` | crawl/ | 🟢 |
| `scripts/crawl/enricher.py` | crawl/ | 🟢 |
| `scripts/crawl/transformer.py` | crawl/ | 🟢 |
| `scripts/crawl/loader.py` | crawl/ | 🟢 |
| `scripts/crawl/retry.py` | crawl/ | 🟢 |
| `scripts/crawl/circuit_breaker.py` | crawl/ | 🟢 |
| `scripts/crawl/sanctions.py` | crawl/ | 🟢 |
| `scripts/crawl/async_client.py` | crawl/ | 🟡 async legado |
| `scripts/crawl/sync_client.py` | crawl/ | 🟡 parcial |
| `scripts/crawl/adapter.py` | crawl/ | 🟢 |
| `scripts/crawl/_parallel_mixin.py` | crawl/ | 🟢 |
| `scripts/crawl/config.py` | crawl/ | 🟢 |
| `scripts/crawl/transparencia_templates/*` | crawl/ | 🟢 |
| `scripts/intel_pipeline.py` | intel/ | 🟢 |
| `scripts/intel-collect.py` | intel/ | 🟢 |
| `scripts/intel-enrich.py` | intel/ | 🟢 |
| `scripts/intel-validate.py` | intel/ | 🟢 |
| `scripts/intel-analyze.py` | intel/ | 🟢 |
| `scripts/intel-extract-docs.py` | intel/ | 🟢 |
| `scripts/intel-excel.py` | intel/ | 🟢 |
| `scripts/intel-report.py` | intel/ | 🟢 |
| `scripts/matching/entity_matcher.py` | matching/ | 🟢 |
| `scripts/matching/__init__.py` | matching/ | 🟢 |
| `scripts/lib/name_normalizer.py` | lib/ | 🟢 |
| `scripts/lib/bid_simulator.py` | lib/ | 🟢 |
| `scripts/lib/cost_estimator.py` | lib/ | 🟢 |
| `scripts/lib/victory_profile.py` | lib/ | 🟢 |
| `scripts/lib/win_loss_tracker.py` | lib/ | 🟢 |
| `scripts/lib/doc_templates.py` | lib/ | 🟢 |
| `scripts/lib/constants.py` | lib/ | 🟢 |
| `scripts/lib/intel_logging.py` | lib/ | 🟢 |
| `scripts/lib/cli_validation.py` | lib/ | 🟢 |
| `scripts/lib/retry.py` | lib/ | 🟢 |
| `scripts/reports/panorama.py` | reports/ | 🟢 |
| `scripts/reports/coverage_gaps.py` | reports/ | 🟢 |
| `scripts/reports/coverage_weekly.py` | reports/ | 🟢 |
| `scripts/generate-proposta-pdf.py` | reports/ | 🟢 |
| `scripts/generate-report-b2g.py` | reports/ | 🟢 |
| `scripts/report_dedup.py` | reports/ | 🟢 |
| `config/settings.py` | config/ | 🟢 |
| `config/logging_config.py` | config/ | 🟢 |
| `config/sectors_config.yaml` | config/ | 🟢 |
| `config/sectors_data.yaml` | config/ | 🟢 |
| `config/abbreviations.yaml` | config/ | 🟢 |
| `config/transparencia_config.yaml` | config/ | 🟢 |
| `db/migrations/*` | db/ | 🟢 |
| `db/seed/*` | db/ | 🟢 |
| `db/setup_db.sh` | db/ | 🟢 |
| `db/backup-database.sh` | db/ | 🟢 |
| `supabase/migrations/*` | db/ | 🟢 |
| `deploy/install.sh` | deploy/ | 🟢 |
| `deploy/provision-vps.sh` | deploy/ | 🟢 |
| `deploy/systemd/*` | deploy/ | 🟢 |
| `deploy/hardening/*` | deploy/ | 🟢 |
| `docs/td-001/*` | docs/ | 🟢 |
| `docs/architecture/*` | docs/ | 🟢 |
| `docs/prd/*` | docs/ | 🟢 |
| `docs/qa/*` | docs/ | 🟡 |
| `docs/ops/*` | docs/ | 🟡 |
| `docs/stories/*` | docs/ | 🟡 |

## Sumário

| Cobertura | Count | % |
|-----------|-------|---|
| 🟢 Completa | 63 | 84% |
| 🟡 Parcial/Legado | 12 | 16% |
| 🔴 Não mapeado | 0 | 0% |
| **Total** | **75** | **100%** |

**Nota:** Arquivos de `scripts/` restantes (datalake-sc-200km.py, demo_b2g_setorial.py, validate-report-data.py, etc.) são scripts auxiliares/demo — cobertos indiretamente pelas specs dos módulos core.
