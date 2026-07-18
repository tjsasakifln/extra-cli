# Fool-proof operation — extra-dod-roi

## Goal

Make the next highest-ROI unlocked DoD advance **inevitable**, while making
AIOX process violations **impossible to complete silently**.

## Single entry (write)

```bash
python squads/extra-dod-roi/scripts/cli.py force-next
```

This **always**:

1. Recomputes rank from real repo state  
2. Locks to **ranking[0]** only  
3. Writes execution card  
4. Materializes AIOX story **Draft** + `.aiox/state/stories/*.json`  
5. Stops at phase `STORY_DRAFT`  

It **never**:

- Auto-sets Ready (that is **@po** exclusive)  
- Implements product code  
- Runs QA as implementer  
- Updates DoD checkboxes  
- Merges PRs  

## Non-skippable AIOX sequence

```
force-next
  -> @po  validate (Ready, po_validated=true)
  -> enforce implement  (must ok)
  -> @dev implement ranking[0] on non-main branch
  -> @dev InReview handoff
  -> @qa  independent gate
  -> @po  close
  -> @devops draft PR / push authority
  -> force-next   # RERANK — mandatory
```

## Hard gates (exit 2)

| Code | When |
|------|------|
| `STALE_RANK` | HEAD/DOD/age invalidates rank |
| `WRONG_CANDIDATE` | Work ≠ ranking[0] |
| `SKIP_PHASE` | Illegal phase jump |
| `NO_STORY` | Missing AIOX story state |
| `PO_NOT_READY` | Code before Ready |
| `SELF_QA` | Implementer == QA |
| `QA_NOT_PASS` | PO close without verdict |
| `DOD_PREMATURE` | DoD edit before QA |
| `MAIN_WRITE` | Product write on main when mode≠main-direct |
| `WRITER_LOCK_REQUIRED` | main-direct implement without valid main-writer.lock |
| `MAIN_DIRECT_BRANCH` | main-direct publish attempted off main |
| `NO_UNLOCKED` | Nothing unlocked — stop honestly |

```bash
python squads/extra-dod-roi/scripts/enforce_aiox_path.py implement
python squads/extra-dod-roi/scripts/cli.py cycle
```

## What agents must refuse

If the user asks to “just implement X” while a cycle is bound to Y:

1. Show `cli.py cycle` + `selected_id`  
2. Refuse X  
3. Offer only: continue mandatory step for Y, or abort cycle with reason + new `force-next`  

There is **no** `--skip-aiox` flag.

## Policy files

- `data/enforcement-policy.yaml`  
- `data/aiox-binding.yaml`  
- `checklists/aiox-compliance-checklist.md`  
