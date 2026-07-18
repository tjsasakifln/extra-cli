# QA Verdict — ROI-cand-dyn-slice-34174823e54a (DoD §32.1 remainder)

**Date:** 2026-07-18  
**Reviewer:** Quinn (@qa) — independent (not implementer)  
**Story:** `ROI-cand-dyn-slice-34174823e54a` / `cand-dyn-slice:34174823e54a`  
**Scope:** DoD §32.1 remainder (5 items) + residual checks  
**Risk:** HIGH-RISK (docs/process contract; no runtime product mutation)

---

## Verdict: **PASS**

All five remainder items are proven with independent evidence. Residuals are non-blocking and mapped to already-open DoD sub-items (CLAUDE body slimming / protocol-protected maintenance), not to the remainder slice.

**DoD checkbox flips for the five remainder items are authorized** under story AC (“Independent QA PASS before any [x] flip”), provided @po closes and evidence paths below are cited.

---

## Evidence commands (re-run by QA)

```bash
cd "/mnt/d/extra consultoria"
python3 -m pytest tests/test_canonical_entry_points.py -q --no-cov -o addopts=
# → 5 passed (exit 0)

python3 -m scripts.ops.canonical_entry_points --json
# → summary.ok=true
# → three_entry_points_same_commands=true
# → three_entry_points_same_docs=true
# → adapters_dispensable.ok=true
# → precedence_documented=true
# → false_claim_hits=[]
# → claude_pointer.ok=true (mode=pointer_to_canonical_guide)
```

Session artifacts:

| File | Role |
|------|------|
| `docs/ops/session-2026-07-18-canonical-entry-points/validation.json` | CLI snapshot |
| `docs/ops/session-2026-07-18-canonical-entry-points/pytest.log` | 5 passed |
| `docs/canonical-entry-points.yaml` | Machine contract |
| `docs/DEVELOPMENT.md` | Canonical guide |
| `AGENTS.md` | Thin Codex adapter |
| `.cursor/rules/00-extra-canonical.mdc` | Thin Cursor adapter |
| `CLAUDE.md` § Canonical development guide | Pointer + same command block |

---

## Per-item results (remainder)

| # | DoD remainder item | Result | Evidence / notes |
|---|--------------------|--------|------------------|
| 1 | Three entry points share the same setup / validate / golden-path commands | **DONE** | Identical bash blocks in `AGENTS.md`, `.cursor/rules/00-extra-canonical.mdc`, and `CLAUDE.md` (canonical section). Every command line also present in `docs/DEVELOPMENT.md` §2. Tokens: `LOCAL_DATALAKE_DSN`, `scripts.ops.apply_migrations`, `pytest tests/`, `scripts.golden_path`, `force-next`. CLI `three_entry_points_same_commands=true`. |
| 2 | Three entry points indicate the same scope / architecture / ops documents | **DONE** | `docs/DEVELOPMENT.md` §1–3 lists `DOD.md`+`docs/prd/`, `docs/architecture/`, `docs/ops/`. Cursor rule lists the same set explicitly. AGENTS/CLAUDE defer to DEVELOPMENT (thin-adapter pattern). CLI `three_entry_points_same_docs=true` (required tokens `DOD.md` + `docs/DEVELOPMENT.md`). |
| 3 | Tool-specific instructions function as thin, dispensable adapters | **DONE** | AGENTS (25 lines) and Cursor rule (35 lines) are thin adapters. CLAUDE adds explicit “adaptador fino” section pointing to DEVELOPMENT and does **not** invent parallel product gates. Pre-existing CLAUDE bulk (AIOX/Reversa/comandos frequentes) is tool process + cheat-sheet also present in README/`docs/ops` — not sole product source. Residual: CLAUDE body is not *size*-thin (see residual). |
| 4 | Removing Claude/Codex/Cursor files does not eliminate product requirements | **DONE** | Product roots exist independently: `DOD.md`, `docs/DEVELOPMENT.md`, `docs/prd/`, `scripts/`, `tests/`, `db/migrations/`. CLI `adapters_dispensable.ok=true`. Adversarial: crawl/intel/datalake command references also live in README and `docs/ops`. |
| 5 | Conflict precedence: DOD → ADR → tested code → evidence | **DONE** | Documented in `docs/DEVELOPMENT.md` header, `AGENTS.md`, Cursor rule, `CLAUDE.md` canonical section, and `docs/canonical-entry-points.yaml` `precedence:`. CLI `precedence_documented=true`. |

---

## Residual checks (requested)

| Residual | Result | Evidence |
|----------|--------|----------|
| `CLAUDE.md` points to `docs/DEVELOPMENT.md` | **DONE** | Section “Canonical development guide (DoD §32.1)” with link + contract path |
| Cursor rule exists | **DONE** | `.cursor/rules/00-extra-canonical.mdc` (`alwaysApply: true`) |
| `AGENTS.md` aligned | **DONE** | Same commands as DEVELOPMENT/Cursor; precedence; no false seals |

---

## Falsification attempts (adversarial)

| Attempt | Outcome |
|---------|---------|
| Adapters invent `LOCAL_READY` as achieved | **Failed to falsify.** Mentions are prohibitions only (“Não inventar…”, “Never invent…”). CLI `false_claim_hits=[]`. |
| Product requirements only in `CLAUDE.md` | **Failed to falsify.** Product roots + README/`docs/ops` hold operational commands and DoD gates. |
| Divergent setup/validate/golden-path across entry points | **Failed to falsify.** AGENTS bash == Cursor bash == CLAUDE canonical bash; DEVELOPMENT is a superset. |

---

## Quality / process observations (non-blocking)

1. **CLAUDE body remains large** (~164 lines AIOX/Reversa/cheat-sheet). Separate open DoD items already note protocol-protected maintenance (“apenas adaptações indispensáveis”). Not a failure of the remainder’s dispensability test.
2. **Validator leniency:** `scripts/ops/canonical_entry_points.py` clears missing command tokens for thin adapters when a DEVELOPMENT pointer is present. Safe today because `development_complete` is still required for `three_entry_points_same_commands`, but a future hardening could require exact command-block equality. Tech debt only.
3. **Story process gap:** state/story still `Ready` at review time (no InProgress/InReview transition logged by @dev). Does not invalidate technical evidence; @po should reconcile status on close.
4. **No NOT_APPLICABLE** used for campaign meta (AC2 respected).
5. **Forbidden claims** still forbidden: no `LOCAL_RESILIENCE_READY`, no `PRE_VPS_FINAL_READY`, no 95% operational seal, no VPS seal.

---

## AC traceability

| Story AC | Result |
|----------|--------|
| Each of 5 dod_item_ids proven with evidence or left open | **PASS** — all 5 DONE with evidence above |
| No NOT_APPLICABLE used to hit campaign meta | **PASS** |
| Independent QA PASS before any [x] flip | **PASS** — this verdict |

---

## Decision summary

| Field | Value |
|-------|-------|
| **Gate** | **PASS** |
| Item 1 commands | DONE |
| Item 2 documents | DONE |
| Item 3 thin adapters | DONE (residual: CLAUDE size) |
| Item 4 dispensable | DONE |
| Item 5 precedence | DONE |
| Residual CLAUDE pointer | DONE |
| Residual Cursor rule | DONE |
| Residual AGENTS aligned | DONE |
| Blocking issues | **none** |
| Follow-ups | Optional: slim CLAUDE to pointer+protocol only in protocol-maintenance session; tighten validator equality checks |

---

*Quinn (Guardian) — independent QA. Does not modify application source. Does not flip DoD checkboxes (owner: implementer/@po with this evidence). Does not commit or push.*
