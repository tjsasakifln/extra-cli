# ADVERSARIAL PANEL SUBMISSION — CONFENGE-PILOT-INTEGRITY-RECOVERY-01

**Submitted:** 2026-08-09T22:25:12Z  
**Submitter role:** recovery implementer (not authorizing GO)  
**System posture:** PAUSED | Kill switch **ENGAGED** | WhatsApp OFF | GREEN autorun OFF | **NO dispatch**

## Verdict (recovery package)

```
NO_GO
```

This package **must not** be treated as `GO_FOR_CONTROLLED_PILOT`. Prior GO is insufficient authorization after the COPY-SAMPLE incident. Recovery reduces integrity defects; it does **not** authorize real send.

## PRs (for review only — no merge/deploy as GO)

| Repo | Branch | HEAD | PR |
|------|--------|------|-----|
| extra-cli | `fix/confenge-pilot-target-service-integrity` | `0c7a4645` (tip; see PR) | https://github.com/tjsasakifln/extra-cli/pull/211 |
| warmbly | `fix/confenge-pilot-service-copy-integrity` | `567977b2ff81fa8fcd655713c9a3ba02d0907090` | https://github.com/tjsasakifln/warmbly/pull/34 |

## Artifacts (authoritative)

Base: `artifacts/confenge/pilot-integrity/`

| Artifact | Purpose |
|----------|---------|
| `GO-NO-GO.md` | Formal **NO_GO** + concrete blockers |
| `FINAL-REPORT.md` | Recovery summary |
| `CURRENT-10-FORENSICS.md` + `current-10-forensics.csv` | Incident-10 adversarial forensics |
| `target-fit-audit.csv` | Target-fit rescore evidence |
| `service-routing-audit.json` | Multi-service routing audit |
| `new-30-draft-sample.md` | Structural draft sample (no real send) |
| `new-10-human-review.md` | Human review pack |
| `cross-repo-service-contract.json` | confenge.service.v1 export |
| `rebuild-2026-08-09/*` | Clean feed + Warmbly import evidence + contamination invalidation |
| `PANEL-SUBMISSION.md` | This document |

## What was fixed (code)

### extra-cli
- Target-fit triangulation (CONFIRMED / RESEARCH / OUT_OF_SCOPE); no total-portfolio as pass_count
- FASE7 multi-service ranking (mature reajuste demoted vs gestão; lean backoffice ≥3 contracts)
- Semantic EMAIL_SEND_READY = TARGET_FIT + SERVICE_FIT + CONTACT_SEND + COPY_CONTEXT + NOT_BLOCKED
- Concrete why_this_account + micro_offer catalog
- near-duplicate batch gate
- confenge.service.v1 cross-repo ontology; bridge preserves ontology ids on offer
- Tests: join expects Warmbly playbook codes (`MONITORAMENTO_CONTRATUAL`), not snake_case as `service_code`

### warmbly
- Playbook service identity + aliases synced with ontology
- strategy: fact-based WhyThisAccount; generic → incomplete_copy_context fail-closed
- drafts: incomplete strategy → RED
- clean feed `data/confenge-feeds/pilot-integrity-clean-v1.json` (local no-send)

## Incident-10 (COPY-SAMPLE-2026-08-10) forensics

| Class | N |
|-------|---|
| FALSE_TARGET | 6 |
| TRUE_TARGET | 2 |
| TARGET_REQUIRES_RESEARCH | 2 |
| All REAJUSTE empty copy | 10 |

## Offline rescore (existing 48,748 eligibles)

| Class | N |
|-------|---|
| TARGET_CONFIRMED | 5606 |
| TARGET_PROBABLE_RESEARCH | 39212 |
| TARGET_OUT_OF_SCOPE | 3930 |

## Clean feed post-fix (local)

- 49 leads, REAJUSTE=0, multi-service mix
- 49 unique why_this_account
- Warmbly local import: fail-closed email_send_ready=0; kill switch on
- Structural sample gates: PASS

## Verification evidence (local, this submission)

| Suite | Result |
|-------|--------|
| extra-cli confenge targeted pytest (114 tests) | **============================= 114 passed in 14.03s =============================** |
| warmbly `go test ./...` | **exit 0** (full suite) |
| warmbly `go test ./internal/app/confenge/...` | **ok** |

Logs (scratch, not committed): `/tmp/grok-goal-85afca0088bc/`

## Explicit NO_GO blockers (remaining)

1. No live EMAIL_SEND_READY cohort of 50 with real COMPANY_OWNED verified contacts — clean import fail-closed by design.
2. Full national DSN rebuild (3.6M contracts) not re-executed under construction/target_fit v2; offline rescore of existing 48,748 eligibles only.
3. Operator merge/deploy of fix branches + human review of new-30/new-10 still required.
4. Warmbly import target was local warmbly_dev, not production VPS.

## Safety invariants (must hold)

- [x] Kill switch ENGAGED
- [x] Dispatch PAUSED
- [x] No real-lead email
- [x] No WhatsApp
- [x] No GREEN autorun
- [x] Contaminated COPY-SAMPLE invalidated / not reused
- [x] Package ends in **NO_GO** only
- [x] Recovery **not** treated as GO

## Panel ask

1. Adversarial review of forensics + samples for theater / generic why / weak mature ranking / monoculture.
2. Confirm remaining blockers before any controlled pilot discussion.
3. **Do not** authorize dispatch, merge-as-GO, or production import from this package alone.


## MessageSpine pass (2026-08-09T22:50:53Z)

- Structural spine + gates + organic sample regenerated
- Sample30: hollow_fact=0, hollow_body=0, near_dup_blocked=False, max_sim=0.5273, struct_ok=True
- Organic mix (honest, gestão-heavy after killing invented BDI): {'gestao_monitoramento_contratual': 24, 'apoio_licitacoes_propostas': 6}
- Prior stratified 8/family: **INVALIDATED**
- Terminal verdict remains **NO_GO**


## MessageSpine v2 (2026-08-09T23:09:39Z)

- Aligned `is_hollow_fact` / portfolio_review `why_now` with COPY_CONTEXT generic markers
- Sample30: hollow_why_now=0, copy_context spot-check first10 PASS, struct_ok=True
- TRACADO + JATOBETON forensics: material contracts cited; stale auditoria primary removed
- Terminal **NO_GO** unchanged (safety + concentration + live cohort blockers)
