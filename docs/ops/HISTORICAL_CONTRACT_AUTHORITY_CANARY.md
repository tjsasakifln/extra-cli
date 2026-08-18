# HISTORICAL_CONTRACT_AUTHORITY_CANARY

Bounded canary for factual historical-contract dossiers.

## Recorte

- Preferential window: last 36 months of official AEC contracts.
- Initial geography: SC via `scripts.contract_publication.official_snapshot.fetch_official_sc_snapshot`.
- SC is not a national claim.

## Entry points reused

- `#414` `scripts.contract_publication.engine.rank_candidates`
- `#415` `scripts.contract_comparables.engine.build_peer_group`
- `#400` `scripts.public_read_consumers.contract_analysis` field contract
- `scripts.process_documents.inventory_pipeline.extract_text`

## Commands

```bash
python3 -m scripts.historical_contract_authority --mode fixture --as-of 2026-08-17T12:00:00Z
python3 -m scripts.historical_contract_authority --mode live --limit 40 --output /tmp/authority-handoff-live
```

`--mode live` refuses to write to `exports/authority-handoff/contract-analysis/1.0/` (the committed fixture handoff). Use an isolated `--output`.

Live SELECT is read-only. A blocked DSN is `official_unavailable`, not `official_projection`. Document download is bounded (user-agent, timeout, retry, rate limit, SHA-256). PDFs are not committed.

## Honest zero

If no dossier reaches score 88, the handoff publishes 0 `HANDOFF_READY` artifacts and keeps the gates.
