# GO / NO-GO — Unconditional CONFENGE email pilot

Generated: `2026-08-10T09:27:23Z`
Emitter: `scripts/confenge/emit_unconditional_go_pack.py` (sole pack writer)

## Terminal state

### `EXTERNAL_BLOCKER_REQUIRES_TIAGO`

All **controllable engineering** §21 booleans are true from live probes
(origin/main == host `.deployed_sha` == runtime == `60223f8881c3…`).

The **sole remaining non-automatable gate** is real human review of the stratified sample
(`HUMAN_REVIEW_PENDING`, n=15). Machine processes must not mint `HUMAN_REVIEW_APPROVED`.

## Live freeze (fail-closed)

| Probe | Value |
|-------|--------|
| extra-cli origin/main | `60223f8881c366469667efbadf05417dcdb7f55c` |
| extra-cli host deployed | `60223f8881c366469667efbadf05417dcdb7f55c` |
| extra-cli runtime | `60223f8881c366469667efbadf05417dcdb7f55c` |
| extra-cli CI | green (https://github.com/tjsasakifln/extra-cli/actions/runs/31373825679) |
| warmbly origin/main | `81d83429316aa6241cc81b3ac8e761bfc59c2487` |
| warmbly host/runtime | `81d83429316aa6241cc81b3ac8e761bfc59c2487` |
| TARGET_FIT_RUNTIME | HEALTHY |
| clean ESR companies | 50 |
| first-50 all_zero | true |
| why_you / why_now unique | 50 / 50 |
| contaminated_sendable | 0 |
| cohort_id | `CLEAN_LIVE_CONFIRMED_IDENTITY_V9` |

## Human review (blocker)

File: `artifacts/confenge/unconditional-go/human-review-sample.json`

### Ação exata

For each of 15 samples set `review_status` ∈ {HUMAN_REVIEW_APPROVED, HUMAN_REVIEW_REJECTED},
`reviewer` (human id), `reviewed_at` (ISO-8601), `decision`, `evidence_inspected`.
Top-level `"status": "HUMAN_REVIEW_COMPLETE"`.

### Critério observável

```bash
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("artifacts/confenge/unconditional-go/human-review-sample.json").read_text())
assert d.get("status") == "HUMAN_REVIEW_COMPLETE", d.get("status")
samples = d["samples"]
assert len(samples) >= 10
assert all(s.get("review_status") in ("HUMAN_REVIEW_APPROVED", "HUMAN_REVIEW_REJECTED") for s in samples)
assert all(s.get("reviewer") and s.get("reviewed_at") for s in samples)
print("OK")
PY
```

### Comando de retomada

```text
Resume CONFENGE-OUTREACH-UNCONDITIONAL-GO-01 after HUMAN_REVIEW_COMPLETE; run python3 -m scripts.confenge.emit_unconditional_go_pack and emit GO_FOR_REAL_CONFENGE_EMAIL_PILOT if eng still green.
```
