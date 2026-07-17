# Resume after interruption

1. `python squads/extra-dod-roi/scripts/cli.py status`
2. Inspect `state/cycles/` and `state/locks/`
3. `python squads/extra-dod-roi/scripts/stale_detect.py --repo . --state squads/extra-dod-roi/state/rankings/latest.json`
4. If exit 2 (stale): discard ranking trust; re-run `rank-next`
5. If lock held by dead process: human decides `cycle_lock.py release`
6. `*resume-cycle` only with write permission and non-stale card
7. Never skip adversarial QA after implement phase
