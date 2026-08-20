# Integration notes — web-cfg #155

Producer: `tjsasakifln/extra-cli` (`python3 -m scripts.bid_readiness_public`).
Consumer: `web-cfg` issue **#155** (not closed by this wave).

## What extra-cli owns

- Deterministic envelope `public-read-bid-readiness/1.0`
- Private local analysis of explicit paths
- Redacted public fixture + SELECT-only read model
- Fail-closed FACT/RISK/UNKNOWN semantics

## What extra-cli does not own

- Public upload, storage, auth, or malware pipeline as a product
- UX, CTA, indexation, SEO, pricing
- Final commercial GO
- Writes into web-cfg / Warmbly / SmartLic
- Closing #155

## Consumer contract

Read model: `exports/public-read-bid-readiness/1.0/web-cfg-155-read-model.sql`

- SELECT only
- `publication_authorization=false`
- `index_authorization=false`
- `page_authorized=false`
- Fixture kind: `redacted_fixture`

Do not implement the web-cfg page in this repository.
