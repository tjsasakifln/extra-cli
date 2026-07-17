# Entity Source Gaps

**Generated:** 2026-07-17T12:30:49.741054+00:00
**Total entities:** 1093
**Operational:** 0
**Gaps:** 1093 (100.0%)

## By blocker class

| Blocker | Count |
|---------|------:|
| `pending_collection` | 484 |
| `credential` | 264 |
| `pending_live_verification` | 208 |
| `fragmented` | 137 |

## By access status

| Status | Count |
|--------|------:|
| `mapped` | 605 |
| `unknown` | 488 |

## By strategy

| Strategy | Count |
|----------|------:|
| `ciga_ckan_shared_municipio` | 483 |
| `sc_compras_and_doe_sc` | 264 |
| `pncp_cnpj_lookup` | 224 |
| `pncp_monitor_by_cnpj` | 105 |
| `multi_source_probe` | 16 |
| `ciga_ckan_municipio_expand` | 1 |

## Priority 1–2 sample (up to 50)

| Priority | Name | Município | Blocker | Next action | Strategy |
|---------:|------|-----------|---------|-------------|----------|
| 1 | ARAQUARI CAMARA DE VEREADORES | ARAQUARI | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | ASCURRA CAMARA DE VEREADORES | ASCURRA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | ATALANTA CAMARA MUNICIPAL | ATALANTA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | ATALANTA CAMARA MUNICIPAL DE VEREADORES | ATALANTA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | BENEDITO NOVO CAMARA DE VEREADORES | BENEDITO NOVO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | BOM JARDIM DA SERRA CAMARA DE VEREADORES | BOM JARDIM DA SERRA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DE AURORA | AURORA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DE BARRA VELHA | BARRA VELHA | `pending_live_verification` | run_live_pncp_orgao_probe_with_network; then schedule_incremental; do_not_count_offline_index_as_operational | `pncp_monitor_by_cnpj` |
| 1 | CAMARA DE VEREADORES DE IMBUIA | IMBUIA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DE PONTE ALTA/SC | PONTE ALTA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DE POUSO REDONDO | POUSO REDONDO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DE TREVISO | TREVISO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DE URUPEMA | URUPEMA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DO MUNICIPIO DE ALFREDO WAGNE | ALFREDO WAGNER | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DO MUNICIPIO DE CANELINHA | CANELINHA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA DE VEREADORES DO MUNICIPIO DE LAGES | LAGES | `pending_live_verification` | run_live_pncp_orgao_probe_with_network; then schedule_incremental; do_not_count_offline_index_as_operational | `pncp_monitor_by_cnpj` |
| 1 | CAMARA DE VEREADORES DO MUNICIPIO DE VIDAL RAMOS | VIDAL RAMOS | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DA LAGUNA | LAGUNA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE ANGELINA | ANGELINA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE BLUMENAU | BLUMENAU | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE BOCAINA DO SUL/SC | BOCAINA DO SUL | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE BOMBINHAS | BOMBINHAS | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE BRUSQUE | BRUSQUE | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE COCAL DO SUL | COCAL DO SUL | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE CORREIA PINTO | CORREIA PINTO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE DOUTOR PEDRINHO/SC | DOUTOR PEDRINHO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE ERMO | ERMO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE FORQUILHINHA | FORQUILHINHA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE GAROPABA | GAROPABA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE GRAVATAL | GRAVATAL | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE JAGUARUNA | JAGUARUNA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE LAURO MULLER | LAURO MULLER | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE LEOBERTO LEAL | LEOBERTO LEAL | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE NOVA VENEZA | NOVA VENEZA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE PAULO LOPES | PAULO LOPES | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE PESCARIA BRAVA | PESCARIA BRAVA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE PONTE ALTA DO NORTE | PONTE ALTA DO NORTE | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE RANCHO QUEIMADO | RANCHO QUEIMADO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE RIO FORTUNA | RIO FORTUNA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE RIO RUFINO | RIO RUFINO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE SANTA ROSA DE LIMA | SANTA ROSA DE LIMA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE TREZE DE MAIO | TREZE DE MAIO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE URUBICI | URUBICI | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE URUSSANGA | URUSSANGA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE VEREADORES DE BOM RETIRO | BOM RETIRO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE VEREADORES DE GUABIRUBA | GUABIRUBA | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE VEREADORES DE MAJOR GERCINO | MAJOR GERCINO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE VEREADORES DE NOVA TRENTO | NOVA TRENTO | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE VEREADORES DE ORLEANS | ORLEANS | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
| 1 | CAMARA MUNICIPAL DE VEREADORES DE PAINEL | PAINEL | `pending_collection` | ingest_ciga_dom_publications_for_municipio_then_reconcile | `ciga_ckan_shared_municipio` |
