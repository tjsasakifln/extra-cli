# Engineering data-release candidate manifesto

CAMPAIGN_ID: `EXTRA-ENGINEERING-DATA-RELEASE-CANDIDATE-01`  
Branch: `integrate/engineering-commercial-data-release-20260905`  
Base: `origin/main` `3919f4d9af1363e2db641c7edadb8a8404874ec4`  
DAG: 26 raw source commits → 12 unique patch-ids; plus candidate commit(s) for migration 116.

No merge to main. No deploy. No production backfill. No SMTP. No crawler start.

## Freeze (PR → HEAD SHA → unique commits → inclusão)

| source PR | issue | source SHA | unique commits | inclusão | motivo | objects | migration | tests | residual live |
|---|---|---|---|---|---|---|---|---|---|
| #555 | #546 | `5f61f28ee628f609f1a98adc2051f695d2b0a7fd` | `831fdbeb` + CI patch-ids `9868fc18`/`db9891ba` (once) | INCLUDE_REVENUE_NOW | Official PNCP tipo/categoria/modalidade/regime/SRP | columns on `pncp_supplier_contracts`, `upsert_pncp_supplier_contracts`, `apply_pncp_structural_fields` | 107 | `tests/test_pncp_structural_fields.py` | backfill of archived payloads not run |
| #557 | #552 | `fbc05737b542c7b36da3bdadd61580c58f73c11f` | `abb29c1d`, `fbc05737` | INCLUDE_REVENUE_NOW | Quarantine year 8406; clocks stay distinct | trigger `fn_quarantine_implausible_contract_dates`, `v_contract_dates_sane` | 108 | `tests/test_contract_date_hygiene.py` | existing prod rows not quarantined until migrate |
| #556 | #549 | `48e201f9178b714582a690cc3b57f3f4dc48d8f8` | `e00effe8` | INCLUDE_REVENUE_NOW | Engineering universe by official categoria; cadastral join | `v_engineering_supplier_universe`, `v_supplier_cadastral_contact` | 109 | `tests/test_engineering_supplier_registry.py` | monthly refresh not started |
| #558 | #544 | `b596cc1308dbd9d87c047dfafccb16916c88e598` | `c55a45c9` | INCLUDE_REVENUE_NOW | Persisted class is the only classification authority | `contract_engineering_class`, `apply_contract_engineering_class` | 110 | `tests/test_engineering_class.py` | labels not stamped in prod |
| #559 | #545 | `f80f0d447b6f6d345f212d04e4528cf33c4f5ea5` | `7ff757d2` | INCLUDE_DORMANT_FAIL_CLOSED | Store results; never claim live homologation without a persisted event | `pncp_procurement_results` | 111 | `tests/test_pncp_procurement_results.py` | ingest not started; view stays UNKNOWN |
| #560 | #548 | `98c711f5e4c385a150267a059cd01d59eb2a7854` | `7cb9bc85` | INCLUDE_REVENUE_NOW | Terminal terms exclude HOT/WARM/ACTIVE | `contract_terms`, `lifecycle_event_last` | 112 | `tests/test_contract_terms_lifecycle.py` | terms ingest not started |
| #561 | #547 | `57de978a28d252162465fc9e5b6d29f7e6104ec4` | `709e16f1` | INCLUDE_REVENUE_NOW | F1–F8 from persisted class | `mv_supplier_structural_profile` | 113 | `tests/test_supplier_structural_profile.py` | matview empty until class backfill + refresh |
| #562 | #551 | `2dbc36c97f013db1040f7c676e93046532b23ca2` | `b100a1c9` | INCLUDE_REVENUE_NOW | Additive F9 view; does not enlarge private-wedge risk | `v_orgaos_contratantes_projeto` | 114 | `tests/test_orgaos_contratantes_projeto.py` | counts need prod class labels |
| #563 | #550 | `c053f7f3a7ccfef259598ec8a0a1eedf29365202` | `1bbcb84f` | INCLUDE_REVENUE_NOW | Stable read contract + NOLOGIN role | `v_recent_engineering_wins`, `confenge_commercial_read_v1` | 115 | `tests/test_commercial_read_v1.py` | no prod rows |
| candidate | — | (this branch) | migration 116 | INCLUDE_REVENUE_NOW | Wire identity + fail-closed #545 into the same view | additive columns on the view | 116 | `tests/test_engineering_data_release_candidate.py` | none in production |

CI adapter/key fixes (`5223f24b` / `5f61f28e` patch-ids) were applied **once**, not nine times.

## Read contract

`v_recent_engineering_wins` consumes persisted class, sanitized dates (`QUARANTINED` excluded), terminal lifecycle (`REVOGACAO|ANULACAO|RESCISAO` → `NOT_ACTIONABLE`), official identity columns, and independent DATA_FRESHNESS / EVENT_RECENCY / COMMERCIAL_ACTIONABILITY.

`procurement_result_status` is `UNKNOWN` unless a persisted #545 event exists. `trigger_type` is never `RESULT_PUBLISHED` / `ADJUDICATED` / `HOMOLOGATED`.

Role `confenge_commercial_read_v1`: NOLOGIN, SELECT-only, no credential in code. Cadastral contact ≠ decision-maker.
