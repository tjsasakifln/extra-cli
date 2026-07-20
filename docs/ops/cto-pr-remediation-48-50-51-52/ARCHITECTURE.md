# ARCHITECTURE — CTO Autopilot as AIOX adapter

## Principle

CTO Autopilot is **not** a second backlog/ranker/story system. It adapts:

- `squads/extra-dod-roi` for audit-dod, ranking, force-next
- AIOX agents `@po/@dev/@qa/@devops` + squad agents for delivery
- DeepSeek for strategic ACCEPT_TOP / RECOMPUTE / ESCALATE / NOOP only
- Grok Build for sandboxed implementation (dontAsk + strict)

## Canonical flow

```
OBSERVE → snapshot + audit-dod + rank
  → DeepSeek strategic ACCEPT_TOP (ranking[0] only)
  → force-next / story Draft
  → @po validates
  → Grok @dev in worktree (no GH/DeepSeek creds, no push)
  → verifier (authorized test_ids, seal SHA/tree)
  → absolute veto (non-PASS forbids ACCEPT)
  → @qa independent
  → @po confirms
  → publisher pushes exact sealed SHA, draft PR
  → DOD/HTML cycle status upsert
  → WAITING_HUMAN
  → mandatory rerank
```

## Security modules (PR #48)

| Module | Role |
|--------|------|
| `.cto/authorized_tests.yaml` | Human registry of test_ids |
| `test_registry.py` | Resolve/execute shell=False |
| `review_veto.py` | Absolute ACCEPT veto |
| `seal.py` | commit_sha + tree_hash seal |
| `publisher.py` | No git add -A after review; seal check |
| `grok_executor.py` | strict + dontAsk, no always-approve ops |
| `aiox_bridge.py` | Thin squad CLI adapter |
| `strategic_decide.py` | ACCEPT_TOP schema |
| `cycle_status.py` | Idempotent DOD/HTML block |

## Forbidden

- Parallel ranker / invented backlog
- LLM free shell tests
- Model ACCEPT over FAIL/UNSAFE
- Push/merge by executor
- DoD checkbox flips without full proof
