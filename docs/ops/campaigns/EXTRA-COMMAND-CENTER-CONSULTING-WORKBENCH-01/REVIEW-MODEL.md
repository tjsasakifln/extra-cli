# REVIEW-MODEL

## Rules (`scripts/command_center/review_rules.py`)

- REJECT: rationale ≥ 8 chars, ≠ title
- DEFER: rationale + return_by
- ACCEPT: when review presents artifact_hashes, client must echo matching hashes
- Hash change → prior ACCEPT obsolete (`decision_is_obsolete`)
- DOD item_id prefix → blocked auto-accept
- no_auto_outreach always recorded

## UI

`DecisionPanel` shows question, evidence, limitations, risks, hashes, rationale, return_by.
