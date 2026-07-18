# QA Verdict — ROI-cand-dyn-slice-b8d41f43fbfc

| Field | Value |
|-------|-------|
| **Verdict** | **FAIL** |
| **Reviewer** | adversarial-qa-auditor (independent) |
| **Reviewed commit** | `cb0be3b8304a4b8d6732c3e95c9678d5ac1cec45` |
| **Branch** | `extra-roi/cand-dyn-slice-b8d41f43fbfc` |
| **Cycle** | `cyc-2026-07-18T172517Z` |
| **Candidate** | `cand-dyn-slice:b8d41f43fbfc` |
| **Section** | Estados, aplicabilidade e bloqueio |
| **Date** | 2026-07-18 |

Artifact JSON: [`squads/extra-dod-roi/state/qa/ROI-cand-dyn-slice-b8d41f43fbfc.json`](../../../squads/extra-dod-roi/state/qa/ROI-cand-dyn-slice-b8d41f43fbfc.json)

---

## Summary

A biblioteca `scripts/ops/requirement_states.py` implementa uma máquina de estados útil (PARTIAL/BLOCKED/NA/SOURCE_UNAVAILABLE/NOT_READY/DONE) com factories fail-closed e testes unitários alinhados. **Não basta para PASS**: (1) DoD já foi marcado `[x]` antes do QA independente (AC3), (2) `is_gate_accepted()` aceita NA ilegítimo, (3) o ledger é demo (5 registros) — o claim de reconstrução de *cada* requisito é overclaim, (4) a lib **não** está ligada ao gate da campanha.

QA **não** alterou código de aplicação nem flipou DoD.

---

## AC Traceability

| AC | Result | Notes |
|----|--------|-------|
| AC1 — 7 dod items com evidência ou abertos | **PARTIAL** | Código+testes reais para a política da seção; overclaim em reconstruct-all e enforcement operacional |
| AC2 — sem NA para meta de campanha | **PASS** | Único NA no ledger é demo multi-tenant fora de escopo §2.3 |
| AC3 — QA independente PASS antes de qualquer `[x]` | **FAIL** | Seção DOD L62–L71 já `[x]`; story ainda Draft; sem QA prévio |

---

## Adversarial falsification

| Attack | Outcome |
|--------|---------|
| PARTIAL vira aceito? | Bloqueado no path principal (`make_partial` + `gate_counts`) |
| NA sem justificativa via `is_gate_accepted()`? | **Bug** — retorna `True` |
| NA sem justificativa via `gate_counts()`? | Bloqueado (illegitimate counter) |
| Ausência → zero? | Bloqueado para `0`/`0.0`; fraco para `None`/`"0"` |
| DONE unchecked em `gate_counts`? | **Bug** — conta como accepted |
| Reconstruct de cada requisito? | **Overclaim** — 5 seeds, sem join 1:1 com 1354 checkboxes |
| Gates de campanha usam a lib? | **Não integrado** |
| Flip DoD antes do QA? | **Violado (AC3)** |

---

## Issues (ordered)

1. **HIGH / process** — Flip DoD antes de QA independente (AC3).
2. **HIGH / code** — `is_gate_accepted()` não valida NA legítimo.
3. **HIGH / requirements** — “estado de cada requisito reconstruível” superestimado.
4. **MEDIUM / architecture** — lib isolada; campanha não consome.
5. **MEDIUM / code** — `gate_counts` aceita DONE sem `validate_record`.
6. **LOW / code** — `is_unchecked_non_accepted` e `coerce_absence_to_zero_forbidden` com buracos.
7. **LOW / process** — Story ainda Draft no fluxo AIOX.

---

## Residual risks

- Callers de `is_gate_accepted()` podem aceitar NA podre.
- Meta de campanha pode divergir da política da lib.
- Seção DoD “verde” com enforcement só em unit/demo.
- Ausência ainda codificável como zero por caminhos não cobertos.

---

## Claims

**Allowed:** política unitária PARTIAL≠DONE, BLOCKED visível em `gate_counts`, NA com campos obrigatórios nas factories, ausência tipada SOURCE_UNAVAILABLE/NOT_READY; sem abuso de NA comercial neste seed.

**Forbidden:** QA PASS pré-flip; gate operacional baseado em `requirement_states`; reconstruct completo de todos os requisitos; LOCAL_READY / PRE_VPS / 95% / PROJECT_DONE.

---

## Decision

**FAIL** — retornar ao @dev.

Remediação mínima:

1. Corrigir `is_gate_accepted()` e `gate_counts` (DONE/NA só se `validate_record` limpo).
2. Reverter ou reabrir checkboxes DoD da seção até re-QA.
3. Estreitar claim de reconstruct **ou** materializar ledger real.
4. Integrar na campanha **ou** não alegar enforcement de gate operacional.
5. Re-submeter a QA independente **antes** de qualquer `[x]`.

---

*Independent adversarial review. Implementer did not author this verdict.*
