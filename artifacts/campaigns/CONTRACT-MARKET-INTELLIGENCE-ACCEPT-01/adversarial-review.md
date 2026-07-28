# Revisão adversarial — CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01

SHA: `ea25c0ff3a382c7df11316344ba129942f40b572`
as_of: 2026-07-28T00:02:47Z

Somente leitura sobre o pacote funcional e artefatos de execução.

| attack_id | target_items | method | result | severity | blocking | evidence | resolution |
|-----------|--------------|--------|--------|----------|----------|----------|------------|
| A01 | CMI-10.1-01, CMI-10.1-02 | scan suppliers-ranking roles + provenance | PASS — only winner_identified / pncp_supplier_contracts | high | False | suppliers-ranking.json roles | no organ as competitor |
| A02 | CMI-10.2-01, CMI-10.2-17 | diff competitor-review columns vs raw contracts | PASS — distinct analytic product | medium | False | competitor-review.md | roles/limitations present |
| A03 | CMI-10.2-16, CMI-10.2-20 | CSV/Excel material row counts | PASS — material rows | high | False | suppliers-ranking.csv | not header-only |
| A04 | CMI-10.2-13 | market_share denominator vs population | PASS — complete_population_aggregated or NOT_COMPUTABLE | high | False | reliability-status.json | fail-closed |
| A05 | CMI-10.2-14 | HHI uses same share universe as market share | PASS | high | False | concentration-by-supplier.csv | same population |
| A06 | CMI-11.1-01, CMI-11.1-03, CMI-11.1-05 | value_type field audit | PASS — valor_contratado not estimated | high | False | value-references.json | types distinct |
| A07 | CMI-11.1-11 | null/missing not coerced to zero | PASS | high | False | value-references.json status MISSING | null preserved |
| A08 | CMI-11.1-19 | outlier flags present when extreme values | PASS | medium | False | proof outliers | flagged |
| A09 | CMI-11.1-14, CMI-11.1-17 | comparability group dimensions | PASS | medium | False | limitations.json | no silent hetero aggregate |
| A10 | CMI-10.1-02 | limitations claim scan for full competitor universe | PASS — does not claim completeness | high | False | limitations.json | honest scope |
| A11 | CMI-10.1-03 | win_rate without proposal denominator | PASS — NOT_COMPUTABLE | high | False | reliability-status.json | fail-closed |
| A12 | CMI-10.1-05, CMI-10.1-06 | capacity inference scan | PASS — no idle capacity claim | high | False | competitor-review.md | hypothesis only if any |
| A13 | CMI-10.1-04 | deságio without comparable pair | PASS — NOT_COMPUTABLE | high | False | reliability-status.json | fail-closed |
| A14 | CMI-10.2-16 | Excel vs JSON reconciliation run_id/code_sha | PASS | medium | False | metadata.json + xlsx sha | same run_id |
| A15 | CMI-10.2-15 | source and as_of present on metrics | PASS | high | False | metadata.json | source+as_of |
| A16 | CMI-10.2-18 | REQUIRE_REAL_DB + RealDict schema | PASS | high | False | cmi_item_proofs real_db | PG real |
| A17 | CMI-10.2-19 | information_schema pncp_supplier_contracts columns | PASS | high | False | schema_check | real names |
| A18 | CMI-10.1-07 | fixture seed labeled not as live national market | PASS (honest) | medium | False | metadata seed_info + limitations | labeled fixture |
| A19 | CMI-10.1-07 | forbidden claims scan LOCAL_READY/95%/CONFENGE | PASS — absent | high | False | claims scan | no forbidden claims |
| A20 | all | evidence SHA and package hash binding | PASS after integrity rebind on main | high | False | hashes.json + proof artifact_hashes | match disk |

**Verdict:** PASS_FOR_MERGE (blocking_findings=0)
