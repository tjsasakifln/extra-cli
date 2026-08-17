# Handoff — web-cfg#83

facts-only producer; no SEO narrative; no publication/index approval.

## Consumer

- `consumer`: `web-cfg#83`
- `schema`: `authority-handoff-contract-analysis/1.0`
- dossier schema: `historical-contract-authority-dossier/1.0`
- public-read schema: `public-read-contract-analysis/1.0`
- `no_index_authorization`: true
- `no_publication_authorization`: true
- public `data_state` only: `DATA_READY` | `DATA_HOLD` | `DATA_REJECT`

## Paths

Root: `exports/authority-handoff/contract-analysis/1.0/`

| Path | SHA-256 |
|------|---------|
| `manifest.json` | `1255682d88cff481b65d9d4efb62e175f43bf9ad4e549bfc13b4d0b5e7078955` |
| `status.json` | `15f54e0af143493591388b747438e0b1097f47d2109490d06098bbc779719906` |
| `lineage.json` | `5a135b50d3fababc32a640af7eb84a5360d2829198cae0f7663b5b7a5feb2f31` |
| `dossiers/0a849765324712f532b68c1e37692f25.json` | `f0e1ddde1c9eaf0b83b9c98d518deb73ee425b1a00221bec2548efd146d3c4ff` |
| `public-read/0a849765324712f532b68c1e37692f25.json` | `015f464d08dd197989d10b4d5b4190c8311bd3306191af7dbe41d91d9dd52e1d` |
| `source-claim-matrix/0a849765324712f532b68c1e37692f25.json` | `a621943fea914b3547f3ebfb62630a4772d21257573af1f535276a8e6627352a` |
| `editorial-briefs/0a849765324712f532b68c1e37692f25.json` | `efa2c92168b5de6ff8f58c9d4b6bcae56ac7121bc2d7c960ed1cbc94595902ee` |

Manifest `content_hash`: `df7633933b3fb3ef3fcb1065a06507162b61edf3ee978950fee6bd07065071ca`.
Official refs use SHA-256 of document bytes (64 hex), never slugs.

## Selected dossier

- `dossier_id`: `0a849765324712f532b68c1e37692f25`
- `catalog_mode`: `fixture`
- `state`: `HANDOFF_READY`
- `DOSSIER_AUTHORITY_SCORE`: 100 (all dimensions 100; all hard gates true)
- public-read `data_state`: `DATA_READY` (not index permission)
- comparability via #415: `COMPARABLE` on admissible fields only
- geography in fixtures: SC / Brusque — not a national claim

The fixture corpus also evaluates 20 adversarial clones. Unique-question selection exports at most five `HANDOFF_READY` dossiers; this run exports one.

## Replay

```bash
python3 -m scripts.historical_contract_authority --mode fixture --as-of 2026-08-17T12:00:00Z
```

Two launches on the same snapshot produce identical `SHA256SUMS`.

## Live official window

`fetch_official_sc_snapshot` was invoked. Result: `source_kind=blocked`, `reason_codes=["dsn_connect_failed"]`, `error_class=OperationalError`, `official_live=false`, `HANDOFF_READY=0`. Gate was not lowered.

## Limitations

- Fixture handoff is not official-live and does not authorize publication or indexation.
- Missing `unidade` / `quantidade` / `regime` / `modalidade` / `valor_semantic` on live rows stay UNKNOWN.
- Outlier is a statistical difference, not irregularity.
- No article, CTA, brand or SEO copy is produced.
- Engines #414 / #415 / #400 are imported, not rewritten.
