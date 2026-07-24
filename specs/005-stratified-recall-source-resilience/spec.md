# Spec 005 — Stratified Recall Source Resilience

**Campaign:** `STRATIFIED-RECALL-SOURCE-RESILIENCE-01`  
**Status:** active  
**Base SHA at creation:** `64549385144fd02304063bb538be31b8feed9900`  
**Authority:** `DOD.md` > constitution > ADR > this spec > code > live evidence

## Problem

Coverage dual for `open_tenders` can be 100% without proving the system finds
relevant tenders. Existing recall evidence is PARTIAL (4 PNCP items, missing
strata, exit 0 on PARTIAL, silent auto-match failures). The project needs
independent stratified recall ≥95% with fail-closed gates.

## Goals

1. Fail-closed stratified recall evaluation (min 50 unique, ≥5 per required stratum, global ≥95%, critical stratum floor ≥90%).
2. Independent gold inventory frozen before system match (hash-stable denominator).
3. Capture + match by official ID / exact URL / content hash on isolated DB only.
4. Nominal miss queue with reasons; controllable misses corrected + idempotent replay.
5. Campaign gates: `make campaign-gate-stratified-recall`, `release-candidate-stratified-recall`, `verify-stratified-recall-isolated`.
6. `production_touched=false` always for this campaign.

## Non-goals

- Redefine dual coverage metrics or inflate coverage with recall.
- Accept 4/4 PNCP as stratified recall.
- Treat Selenium as a source.
- VPS/prod/soak mutation or inspection.
- Full consulting pack A–E.

## Functional requirements

| ID | Requirement | DOD |
|----|-------------|-----|
| FR-01 | Evaluator returns non-zero exit unless status=PASS | §8.4, §34 |
| FR-02 | NOT_READY for scaffold/EXAMPLE-only samples | §8.4 |
| FR-03 | PARTIAL for unlabeled, missing/thin strata, missing evidence/reason, n&lt;50 | §8.4 |
| FR-04 | FAIL when structurally ready but global &lt;95% or any critical stratum &lt;90% | §8.4 |
| FR-05 | Denominator hash frozen; misses never remove denominator rows | §8.4 |
| FR-06 | Forbidden: DB COUNT(*) as recall denominator | §4, §8.4 |
| FR-07 | Independent inventory collector does not query operational tables for denominator | §8.4 |
| FR-08 | Auto-match fails closed on connection/query errors | §7, §23 |
| FR-09 | Platforms PNCP, SC Compras, CIGA represented when applicable | §7, §8.1 |
| FR-10 | Acquisition media API/HTML/PDF/JS represented | §8.1 |
| FR-11 | Entity strata: município size + admin direta/indireta + autarquia/fundação/câmara/consórcio | §8.4 |
| FR-12 | Source-health / contracts / misses / operational report artifacts | §7, §34 |
| FR-13 | CI deterministic (no full live inventory every push); live controlled offline | §29 |

## Acceptance

| Gate | Criterion |
|------|-----------|
| G1 | Adversarial unit suite green on fail-closed behaviors |
| G2 | Gold sample ≥50 unique, ≥5/stratum, validation ok, lock frozen before match |
| G3 | Evaluate exit matches status (PASS→0 else non-zero) |
| G4 | `make campaign-gate-stratified-recall` foundation PASS |
| G5 | Isolated verify writes recall/misses/by-stratum; production DSN refused |
| G6 | Replay idempotent (same denominator hash after re-capture) |
| G7 | Campaign terminal status PASS\|BLOCKED\|FAIL with regenerable proof |

Operational campaign PASS additionally requires global recall ≥95% and floors on the frozen gold sample after capture — not foundation gate alone.
