# ADR: CONFENGE freeze scopes to frozen campaign inputs (v1)

## Status

Accepted (policy PR `policy/confenge-freeze-scope-v2`)

## Context

The monorepo freezes commercial CONFENGE evidence after a code freeze SHA. The
legacy model treated **the entire repository** as frozen except for
`ALLOWED_POST_FREEZE_PREFIXES` (artifacts, docs/ops, real holdout).

That model forces every unrelated feature (edital relevance, other campaigns)
to either:

1. expand the commercial allowlist inside the feature PR (policy self-service), or
2. fail CONFENGE freeze/binding CI despite not touching commercial inputs.

PR #146 demonstrated the failure mode: the foundation PR expanded freeze
allowlists and **self-allowlisted the freeze/binding verifiers**, so the
policy that decides whether the PR may pass was modified by the PR itself.

## Decision

Replace monorepo-wide allowlisting with **explicit frozen CONFENGE inputs**:

- Manifest schema `confenge-frozen-inputs/1.0` at
  `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/frozen-inputs-manifest.json`
- Fields: `campaign`, `freeze_sha`, per-input `path` + `blob_sha` + `sha256`
- Protected set derived from real execution seeds (commercial package, confenge
  ops scripts, profile/config, commercial migrations, freeze gates) plus
  transitive local imports — **not** invented feature allowlists
- **Gates are protected inputs**:
  `scripts/ops/confenge_code_freeze.py`,
  `scripts/ops/verify_confenge_artifact_binding.py`,
  `scripts/ops/confenge_frozen_inputs.py`
- Shared surfaces (`Makefile`, `.github/workflows/ci.yml`) are **not**
  whole-file frozen; only CONFENGE sections are hashed via tested fail-closed
  extractors (`Makefile#CONFENGE`, `.github/workflows/ci.yml#CONFENGE`)
- Evidence lag prefixes remain allowed (campaign artifacts, docs/ops, real
  holdout) — these are not a feature allowlist

## Consequences

### Positive

- Unrelated monorepo work (e.g. `scripts/coverage/edital_relevance_recall.py`,
  `evals/edital_relevance/`, other campaign tests) passes freeze/binding
  **without** editing commercial allowlists
- Changing commercial pipeline, scoring, profile, schema, gates, or CONFENGE
  Make/CI commands still **invalidates** freeze evidence
- Changing the freeze policy code itself requires re-freeze + rebind

### Negative / costs

- Policy changes require honest re-freeze and regeneration of SHA-bound
  commercial package fields at the new HEAD
- Shared-surface extractors must stay fail-closed (missing markers → fail)

### Re-freeze procedure

1. Land policy code on the branch tip
2. `python3 -m scripts.ops.confenge_code_freeze mark-final-integrity-freeze`
   (writes freeze SHA files + frozen-inputs manifest with real hashes)
3. Run canonical verify targets (`verify-confenge-*-freeze`, artifact binding,
   final campaign status)
4. Commit generated gate artifacts only after tools write them — never
   hand-edit SHAs in JSON

## Non-goals

- Permanent allowlisting of edital paths
- Permanent self-exemption of freeze/binding gates
- Accepting DOD items unrelated to CONFENGE policy
- Fabricating human/live commercial evidence

## References

- `scripts/ops/confenge_frozen_inputs.py`
- `scripts/ops/confenge_code_freeze.py`
- `scripts/ops/verify_confenge_artifact_binding.py`
- `tests/commercial_leads/test_confenge_frozen_inputs_policy.py`
