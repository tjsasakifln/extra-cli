# Code/Spec Matrix — Extra Consultoria

> Gerado pelo Writer em 2026-07-11T16:00:00Z
> Mapeia cada arquivo do legado à unit correspondente

## Matriz de Cobertura

| Arquivo do Legado | Unit | Cobertura |
|-------------------|------|-----------|
| `scripts/crawl/monitor.py` | crawl/ | 🟢 |
| `scripts/crawl/pncp_crawler_adapter.py` | crawl/ | 🟢 |
| `scripts/crawl/dom_sc_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/pcp_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/compras_gov_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/sc_compras_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/contracts_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/transparencia_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/tce_sc_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/pncp_arp_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/pncp_pca_crawler.py` | crawl/ | 🟢 |
| `scripts/crawl/enricher.py` | crawl/ | 🟢 |
| `scripts/crawl/transformer.py` | crawl/ | 🟢 |
| `scripts/crawl/loader.py` | crawl/ | 🟢 |
| `scripts/crawl/adapter.py` | crawl/ | 🟢 |
| `scripts/crawl/async_client.py` | crawl/ | 🟡 |
| `scripts/crawl/sync_client.py` | crawl/ | 🟡 |
| `scripts/crawl/checkpoint.py` | crawl/ | 🟢 |
| `scripts/crawl/circuit_breaker.py` | crawl/ | 🟡 |
| `scripts/crawl/retry.py` | crawl/ | 🟡 |
| `scripts/crawl/config.py` | crawl/ | 🟢 |
| `scripts/crawl/sanctions.py` | crawl/ | 🟡 |
| `scripts/crawl/monitor.py` (coverage) | reports/ | 🟢 |
| `scripts/intel_pipeline.py` | intel/ | 🟢 |
| `scripts/intel_collect.py` | intel/ | 🟢 |
| `scripts/intel_enrich.py` | intel/ | 🟢 |
| `scripts/intel_llm_gate.py` | intel/ | 🟢 |
| `scripts/intel_extract_docs.py` | intel/ | 🟢 |
| `scripts/intel_analyze.py` | intel/ | 🟢 |
| `scripts/intel_validate.py` | intel/ | 🟢 |
| `scripts/intel_report.py` | intel/ | 🟢 |
| `scripts/intel_excel.py` | intel/ | 🟢 |
| `scripts/intel_sector_loader.py` | intel/ | 🟢 |
| `scripts/reports/panorama.py` | reports/ | 🟢 |
| `scripts/reports/coverage_gaps.py` | reports/ | 🟢 |
| `scripts/reports/coverage_weekly.py` | reports/ | 🟢 |
| `scripts/lib/name_normalizer.py` | lib/ | 🟢 |
| `scripts/lib/bid_simulator.py` | lib/ | 🟢 |
| `scripts/lib/victory_profile.py` | lib/ | 🟢 |
| `scripts/lib/cost_estimator.py` | lib/ | 🟢 |
| `scripts/lib/win_loss_tracker.py` | lib/ | 🟢 |
| `scripts/lib/doc_templates.py` | lib/ | 🟡 |
| `scripts/lib/constants.py` | lib/ | 🟢 |
| `scripts/lib/intel_logging.py` | lib/ | 🟡 |
| `scripts/lib/cli_validation.py` | lib/ | 🟡 |
| `scripts/lib/retry.py` | lib/ | 🟡 |
| `config/settings.py` | config/ | 🟢 |
| `config/sectors_config.yaml` | config/ | 🟢 |
| `config/sectors_data.yaml` | config/ | 🟢 |
| `config/abbreviations.yaml` | config/ | 🟢 |
| `config/transparencia_config.yaml` | config/ | 🟢 |
| `db/migrations/001-012` | db/ | 🟢 |
| `db/seed/001_sc_entities.py` | db/ | 🟢 |
| `db/seed/seed_sc_entities.py` | db/ | 🟢 |
| `db/setup_db.sh` | db/ | 🟢 |
| `deploy/install.sh` | deploy/ | 🟢 |
| `deploy/systemd/*.service` (13) | deploy/ | 🟢 |
| `deploy/systemd/*.timer` (13) | deploy/ | 🟢 |
| `deploy/systemd/onfailure@.service` | deploy/ | 🟢 |
| `docs/architecture/architecture.md` | docs/ | 🟢 |
| `docs/prd/PRD-consultoria-extra.md` | docs/ | 🟢 |
| `docs/stories/epics/epic-001-*/` | docs/ | 🟢 |
| `docs/qa/gates/*` | docs/ | 🟢 |

## Estatísticas

| Métrica | Valor |
|---------|-------|
| Total de arquivos do legado | 63 |
| Arquivados com 🟢 (cobertura completa) | 53 (84%) |
| Arquivados com 🟡 (cobertura parcial) | 10 (16%) |
| Arquivados sem unit (n/a) | 0 |
