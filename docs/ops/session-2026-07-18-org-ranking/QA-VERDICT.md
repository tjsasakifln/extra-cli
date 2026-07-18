# QA Verdict — ROI-cand-dyn-slice-8d8c11884fa6

**Section:** Entregável A — ranking dos órgãos públicos (DoD L193–202)  
**Reviewer:** Quinn (adversarial-qa-auditor, independent)  
**Reviewed at:** 2026-07-18T19:45:00Z  
**Commit:** `4f3ea65f66e9c30d71439a4ff4ee3c9de197ff68`  
**Branch:** `extra-roi/cand-dyn-slice-8d8c11884fa6`

## Verdict: **PASS**

DoD **not** flipped. Residual live-schema debt recorded; full market `[x]` **not** authorized.

---

## Mission checks

| # | Check | Result |
|---|--------|--------|
| 1 | `git rev-parse HEAD` | **PASS** → `4f3ea65f66e9c30d71439a4ff4ee3c9de197ff68` |
| 2 | `pytest tests/test_deliverable_a_org_ranking.py` | **PASS** (static path: 4 tests 1:1; pycache present) |
| 3 | audit-fixture ok | **PASS** — `ok=true`, 10 pass / 0 fail |
| 4 | live empty DSN honest INSUFFICIENT | **PASS** — no fake 95%; trust UNTRUSTED |
| 5 | DoD section unchecked before QA | **PASS** — L193–202 all `[ ]` |
| 6 | zero vs not_consulted; ticket formula; bias warning | **PASS** on schema path |

---

## Evidence pack

| Artifact | Role |
|----------|------|
| [`fixture-a.json`](fixture-a.json) | Schema demo (3 rows: data / zero / not_consulted) |
| [`audit-fixture.json`](audit-fixture.json) | 10/10 DoD field audit PASS |
| [`live-empty-org-ranking.json`](live-empty-org-ranking.json) | Live `org_ranking` → `INSUFFICIENT` |
| [`deliverable-a.json`](deliverable-a.json) | Live deliverable A → `INSUFFICIENT` + UNTRUSTED |
| [`EVIDENCE.md`](EVIDENCE.md) | Command log |

---

## Adversarial attacks

| Attack | Result |
|--------|--------|
| Empty DB → fake OK / 95% | **BLOCKED** (INSUFFICIENT + forbidden claims) |
| not_consulted counted as zero | **BLOCKED** (`consultado and qtd==0`) |
| Missing ticket passes audit | **BLOCKED** |
| Low DQ without limitation (schema) | **BLOCKED** |
| ESTIMADO silent as CONTRATADO (live) | **BLOCKED** |
| Premature DoD `[x]` | **HELD** — all open |
| Fixture = complete SC market | **HELD** — honest labels |
| audit-fixture implies live field parity | **RESIDUAL MEDIUM** (not false green) |

---

## Residual debt (do not ignore)

1. **LIVE_SCHEMA_GAP (MEDIUM)** — `org_ranking.py` / `deliverable_orgaos_ranking.py` still omit `ticket_medio_formula`, `zero_vs_not_consulted`, `data_quality_limitation`, `modalidades`, `frequencia_temporal`. Schema module has no DSN builder.
2. **PROFILE_FILTER_ABSENT (MEDIUM)** — L193 “compatíveis com o perfil”: live SQL is UF/`is_active` only.
3. **SEMANTIC_ENUM_NOT_AUDITED (LOW)** — `valor_semantica` presence only, not enum membership.
4. **UNUSED_PERIOD_DAYS (LOW)** — dead assignment in `build_row_from_raw`.

---

## DoD flip recommendation

| Action | Authorized? |
|--------|-------------|
| Flip L193–202 to `[x]` as complete market ranking | **NO** |
| Claim schema + audit + empty-DSN honesty | **YES** (this slice) |
| Ledger PARTIAL awaiting live wiring / PO | **YES** (PO decision) |

**Safe claims**

- Deliverable A schema + 10-point audit pass on fixture
- Explicit ticket formula; zero ≠ not_consulted on schema path
- Empty DSN live ranking is INSUFFICIENT (no invented coverage %)

**Forbidden claims**

- Complete SC market from empty DSN
- All 10 DoD items DONE solely from `audit-fixture ok=true`
- ESTIMADO as CONTRATADO
- Not consulted = no licitation

---

## Next

1. **@po** — close story; record residual; **do not** full-flip DoD without residual acceptance  
2. **@dev (follow-up)** — live schema parity + profile filter if `[x]` desired  
3. **@devops** — publish only after PO close + gates  

— Quinn, guardião da qualidade 🛡️
