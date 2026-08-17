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
| `manifest.json` | `017ea41e9ae2a05478c0554cb477bc4f1b48ed8f2135fe4ea20c06343a030b8c` |
| `status.json` | `15f54e0af143493591388b747438e0b1097f47d2109490d06098bbc779719906` |
| `lineage.json` | `979ea60893898d8e4e291101bb39fa5d716c01f27a025cc08d9ed6dfdabf16ac` |
| `dossiers/0a849765324712f532b68c1e37692f25.json` | `8f28f6db6e87f23b45df3ad5a8550f0fa75e049c3aa86739429e8fb1fcef5e2a` |
| `public-read/0a849765324712f532b68c1e37692f25.json` | `66c0aa580f4c88f07e2a01ef4d1ed626e1a1f8453277e03fe8e8c8d004badd33` |
| `source-claim-matrix/0a849765324712f532b68c1e37692f25.json` | `a621943fea914b3547f3ebfb62630a4772d21257573af1f535276a8e6627352a` |
| `editorial-briefs/0a849765324712f532b68c1e37692f25.json` | `efa2c92168b5de6ff8f58c9d4b6bcae56ac7121bc2d7c960ed1cbc94595902ee` |

Manifest `content_hash`: `418a87307123502caa6730cab21c48533bdffe27291719ef3d4579a9dabaaac4`.

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
