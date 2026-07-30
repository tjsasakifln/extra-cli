# Extra — Profile → Actionable → Decision loop

**CLI-first.** No dashboard.

## 1. Profile (canonical)

Path: `config/client_profiles/extra.yaml`

```bash
python3 -m scripts.ops.extra_profile validate
python3 -m scripts.ops.extra_profile stamp          # version + sha256
python3 -m scripts.ops.extra_profile show
python3 -m scripts.ops.extra_profile intake         # questions; no invented answers
python3 -m scripts.ops.extra_profile diff --other path/to/other.yaml
python3 -m scripts.ops.extra_profile init --dest /tmp/extra-scaffold.yaml
```

Absence tokens: `UNKNOWN`, `NOT_PROVIDED`, `NOT_APPLICABLE`, `PENDING`.  
Never interpret null capacity as ability to bid.

Every report must include `profile_id`, `version`, `profile_hash` from `stamp`.

## 2. Actionable classification

```bash
python3 -c "from scripts.ops.extra_actionable import classify_batch; ..."
# or via orchestrator
python3 -m scripts.ops.extra_decision_loop run --weekly-dir ... --out ...
```

States: `ACTIONABLE`, `EXPIRED`, `NO_VERIFIABLE_FUTURE_DEADLINE`, `STATUS_UNCONFIRMED`,
`PROFILE_BLOCKED`, `INSUFFICIENT_SOURCE_EVIDENCE`, `DUPLICATE`, `REVIEW_REQUIRED`.

Empty shortlist → result `NO_ACTIONABLE_TENDER` (success, not failure).

## 3. Weekly

```bash
make extra-weekly
# WEEKLY_FLAGS="--skip-collect"  # reuse lake when fresh
```

## 4. Human review

```bash
python3 -m scripts.ops.extra_decision_review list --run-dir OUT
python3 -m scripts.ops.extra_decision_review decide ID --run-dir OUT \
  --decision ACCEPT|REJECT|DEFER --reason "..." --actor tiago
python3 -m scripts.ops.extra_decision_review accept-empty --run-dir OUT \
  --reason "..." --actor tiago
python3 -m scripts.ops.extra_decision_review finalize --run-dir OUT \
  --actor tiago --package-decision ACCEPTED
```

`PASS_EXTRA_DECISION_LOOP_ACCEPTED` requires explicit human package decision.
