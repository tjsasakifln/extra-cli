# QA Verdict — ROI-cand-dyn-slice-55dc8958c51c

**Story:** `ROI-cand-dyn-slice-55dc8958c51c`  
**Scope:** DoD §27 first 5 (module names · sys.path policy · public docstrings · type hints · specific exceptions on critical path)  
**Reviewer:** Quinn (@qa) — independent (not implementer)  
**Date:** 2026-07-18  
**Reviewed HEAD:** `59dbb29` (working tree includes uncommitted gate/tests/session evidence)  
**Verdict:** **CONCERNS**

---

## Commands re-run (independent)

```bash
cd "/mnt/d/extra consultoria"
python3 -m pytest tests/test_code_organization_gate.py -q --no-cov -o addopts=
# → 3 passed (~9.8s)

python3 -m scripts.ops.code_organization_gate --json
# → exit 0; summary.ok=true
```

Session artifacts cross-checked: `gate.json`, `pytest.log` (3 passed), `MANIFEST.md`.

---

## Scope matrix (§27 first 5)

| # | Item | Gate metric | Result |
|---|------|-------------|--------|
| 1 | Nomes de módulos consistentes | `module_names.n_non_snake=0`, `ok=true` (296 `.py` under `scripts/`) | **PASS** |
| 2 | Imports sem hacks `sys.path` desnecessários | Policy + inventory: **86** inserts; **18** disallowed; `sys_path.ok=true` only via brownfield tolerance `<20` | **CONCERNS** (policy/inventory real; residual debt; soft checkbox) |
| 3 | Funções públicas com docstring | Sample critical modules: `docstring_pct=51.9` (≥50) | **PASS** (margin thin) |
| 4 | Funções críticas com type hints | `return_hint_pct=100.0` on same sample | **PASS** |
| 5 | Exceções específicas (critical path) | `except Exception: pass` critical path `n=0` (`scripts/ops|reports|coverage`) | **PASS** |

**Left open (correct — not false green):**

- `Não existem except Exception: pass` — still **25** repo-wide under `scripts/`
- `Erros não são engolidos` / logs vs tratamento / config centralization etc. — not in this slice

---

## Falsification: zero sys.path repo-wide

| Claim | Status |
|-------|--------|
| “Entire codebase free of `sys.path`” | **REJECTED** |
| Evidence | `n_inserts=86`, `n_disallowed=18`, inventory sample + disallowed list in `gate.json` |
| Gate contract | `claims.forbidden` includes `Entire codebase free of sys.path (brownfield false claim)` |

Any narrative or DoD wording that implies **zero** `sys.path` inserts is a **false green**. Honest claim only: *project-root bootstrap policy + inventory + residual debt tracked*.

---

## Technical findings

### Strengths

1. Gate module `scripts/ops/code_organization_gate.py` is focused, AST-based for bare/`Exception: pass`, and produces reproducible JSON evidence.
2. Forbidden claims are encoded in the gate output (anti-false-green).
3. Critical path free of `except Exception: pass` (0 findings).
4. Module naming policy is sensible (snake_case packages; hyphenated legacy CLIs under `scripts/` root).
5. Tests exist and pass for structure + critical bare-except invariant.

### Concerns (non-blocking for FAIL)

1. **Soft sys.path DoD checkbox**  
   DoD marks “sem hacks desnecessários” complete while **18 disallowed** inserts remain (intel_*, *-b2g-collect, monitor, bids_crawler, etc.). Evidence supports *policy + inventory*, not *elimination*. Residual = tech debt, not zero-hack claim.

2. **`summary.ok` omits `sys_path.ok`**  
   Exit code / summary can be green even if disallowed count later exceeds tolerance. Policy hole for future regressions.

3. **Inventory false positives (2)**  
   `intel_enrich.py` L53/L86 are import lines whose comments contain `sys.path.insert`; counted as disallowed. Inflates debt count slightly; detector should ignore comment-only / non-insert lines.

4. **Test thinness**  
   Suite does **not** assert `summary.ok`, `module_names.ok`, `public_api_ok`, or that `n_inserts > 0` (anti-zero claim). Only structure + critical bare-except. Regression risk on the soft thresholds.

5. **Docstring bar barely cleared**  
   51.9% on sample of 52 public funcs; 25 without docstring (incl. several `main`/ops helpers). OK per gate, weak as “when necessary” coverage.

6. **Process smell**  
   `.aiox/state/stories/ROI-cand-dyn-slice-55dc8958c51c.json` already had `qa_verdict=PASS`, `po_closed=true`, `status=Done` **before** this independent `QA-VERDICT.md`. Story AC requires independent QA before `[x]` flips. This file is the independent record; orchestrator pre-mark is residual process debt.

### Not FAIL because

- Re-run evidence is real and reproducible.
- No claim of zero `sys.path` or `LOCAL_READY`.
- Critical-path exception swallows = 0.
- Open DoD items that would require full elimination correctly remain unchecked.
- Residual debt is inventoried, not hidden.

---

## AC traceability

| AC | Verdict |
|----|---------|
| 1. Each of 8 dod_item_ids proven or left open | **Met** for first-5 scope: 5 evidenced; remaining open items not falsely closed in this slice’s open-list intent |
| 2. No NOT_APPLICABLE used to hit campaign meta | **Met** |
| 3. Independent QA before `[x]` flip | **Partial** — technical re-review done now; state/DoD were pre-marked → process CONCERNS |

---

## Allowed vs forbidden claims after this gate

**Allowed**

- Module naming audited under `scripts/`
- sys.path **policy + inventory** (not zero)
- Critical path free of `except Exception: pass`
- Sample public API return hints at 100%; docstring sample ≥50%

**Forbidden**

- Entire codebase free of `sys.path`
- Zero `except Exception: pass` repo-wide (25 remain)
- `LOCAL_READY` / VPS / 95% coverage seals

---

## Decision

| Field | Value |
|-------|--------|
| **Verdict** | **CONCERNS** |
| **Merge / close posture** | Acceptable to proceed to @po with residuals documented; not a technical FAIL |
| **Must-fix before PASS upgrade** | Optional: (a) assert anti-zero-sys.path + `summary.ok` components in tests; (b) exclude comment false-positives; (c) include `sys_path.ok` in `summary.ok` or document intentional exclusion; (d) align DoD wording for item 2 with “policy+inventory, residual debt” |
| **Follow-ups** | Reduce 18 disallowed inserts toward project-root bootstrap; clear remaining 25 bare/`Exception: pass` outside critical path in a later §27 slice |

---

## Evidence paths

- `docs/ops/session-2026-07-18-code-org/gate.json`
- `docs/ops/session-2026-07-18-code-org/pytest.log`
- `docs/ops/session-2026-07-18-code-org/MANIFEST.md`
- `scripts/ops/code_organization_gate.py`
- `tests/test_code_organization_gate.py`
- `docs/stories/ROI-cand-dyn-slice-55dc8958c51c.md`

— Quinn, guardião da qualidade 🛡️
