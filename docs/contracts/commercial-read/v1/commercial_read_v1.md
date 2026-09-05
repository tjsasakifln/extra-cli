# commercial_read_v1

Version: `v1.0.0`  
Issue: #550  
View: `public.v_recent_engineering_wins`  
Role: `confenge_commercial_read_v1` (SELECT-only, NOLOGIN, no credentials in repo)

## Columns

`company_cnpj, company_name, procurement_id, contract_id, trigger_type, event_at, source_published_at, first_seen_at, detection_lag_days, publication_lag_days, object, value, buyer, buyer_cnpj, uf, municipio, engineering_class, engineering_confidence, lifecycle_status, event_confidence, data_freshness, commercial_age_days, commercial_actionability, evidence_refs`

## Independent clocks

| Field | Meaning |
|---|---|
| DATA_FRESHNESS (`data_freshness`) | `first_seen_at - source_published_at` |
| EVENT_RECENCY (`commercial_age_days`) | `today - event_at` (assinatura) |
| COMMERCIAL_ACTIONABILITY | HOT 0–14, WARM 15–45, ACTIVE 46–90, LATE 91–120, COLD else; `NOT_ACTIONABLE` if `lifecycle_event_last` in REVOGACAO/ANULACAO/RESCISAO |

Do not derive one from another.

Engineering class comes from `contract_engineering_class` (#544), never from objeto regex.
