# Dual measurement artifacts (compact)

**PASS as_of** (see `dual-capability-coverage-summary.json`): open_tenders 1093/1093, historical_contracts 1093/1093, `dual_gate_status=PASS`.

Full entity gaps + ledger remain on VPS (too large for PR):

`/opt/extra-consultoria/output/coverage/dual-campaign-orrc-01/`

| VPS file | proof |
|----------|-------|
| entity-capability-ledger.jsonl | 2186 lines; sha256 in `../proofs/dual-vps-artifact-hashes.json` |
| dual-coverage-gaps-*.json/csv | sha256 in same proof file |
| contracts-3y-window-proof.json | SUCCESS_ZERO 3y window validity |

Committed here: summary, per-capability summaries, source-health, checksums, manifest.
Proof of VPS full pack: `../proofs/dual-vps-artifact-hashes.json` + `../proofs/dual-vps-ls-sha256.txt`.
