# HANDOFF — DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Terminal

- **Functional:** `PASS_LOW_HANGING_ACCEPTED` — **37** items on main with `main_gate=ok`
- **Process:** §15 max-2-PR **violated** by #177 (+ re-accept publish). Do not claim perfect process compliance.

## SHAs

| | |
|--|--|
| Baseline | `e39a75f3` |
| PR A #173 | `97da2c49` |
| PR B #176 | `93b1447c` |
| Integrity #177 | `d39ed05d` |
| Main re-accept HEAD | `d39ed05d` (same tip; re-bound accepts) |

## Evidence of main_gate

```bash
# latest accept for retained ids show main_gate ok
python3 -c "import json; from pathlib import Path
ids=set(json.loads(Path('artifacts/campaigns/DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01/result.json').read_text())['accepted_ids'])
for line in reversed(Path('.dod/log.jsonl').read_text().splitlines()):
  e=json.loads(line)
  if e.get('item_id') in ids and e.get('gates',{}).get('main_gate'):
    print(e['item_id'], e['gates']['main_gate'], e.get('commit','')[:12]); break
"
```

## Residual

- CONFENGE commercial non-required CI still fails on unrelated freeze binding
- §15 PR budget exceeded — future campaigns must not open integrity PR #3
- Demoted POLICY-only items remain open until controller enforces them
