# FINAL-REPORT — CONFENGE-PILOT-INTEGRITY-RECOVERY-01

Generated: 2026-08-09T21:50:10Z

## Verdict: **NO_GO**

Dispatch **PAUSED**. Kill switch **ENGAGED**. No real-lead email.

## Incident (proven)

| Class | Count | Notes |
|-------|------:|-------|
| FALSE_TARGET | 6 | imobiliária, móveis, frota, metrologia, ônibus, médico, etc. |
| TRUE_TARGET | 2 | TRACADO, JATOBETON with construction execution |
| TARGET_REQUIRES_RESEARCH | 2 | |
| Warmbly service | 10/10 REAJUSTE_14133 | empty why_you/micro_offer, clone bodies |

Root causes: permissive POSSIBLE ICP; pass_count total fallback; service taxonomy / REAJUSTE account default; missing COPY_CONTEXT_READY.

## Code fixes (committed)

**extra-cli** `fix/confenge-pilot-target-service-integrity`: target_fit triangulation; semantic EMAIL_SEND_READY; FASE7 router; confenge.service.v1; concrete why_this_account; real micro_offers; adversarial + 10-family e2e tests.

**warmbly** `fix/confenge-pilot-service-copy-integrity`: full aliases; DIAGNOSTICO/INTELIGENCIA/BACKOFFICE; unknown≠REAJUSTE; fact-based WhyThisAccount; generic copy → needs_review.

## National offline rescore

```json
{
  "n": 48748,
  "tf_dist": {
    "TARGET_PROBABLE_RESEARCH": 39212,
    "TARGET_OUT_OF_SCOPE": 3930,
    "TARGET_CONFIRMED": 5606
  },
  "tier_dist": {
    "RESEARCH_ONLY": 39212,
    "OUT_OF_SCOPE": 3930,
    "A_AUTOMATIC": 2369,
    "B_EVIDENCE_SUPPORTED": 3237
  },
  "confirmed": 5606,
  "fp50": 0,
  "struct_ok": false,
  "svc_dist": {
    "apoio_licitacoes_propostas": 3,
    "gestao_monitoramento_contratual": 28,
    "reforco_temporario_backoffice": 10,
    "auditoria_orcamento_bdi": 8,
    "medicoes_glosas_memoria": 1
  },
  "dup_blocked": true,
  "verdict": "NO_GO",
  "concentration_flag": null
}
```

## Clean no-send proof

- Feed: 49 TARGET_CONFIRMED leads from **fixed** router
- Services: {'REEQUILIBRIO': 1, 'PLANILHAS': 8, 'MEDICOES': 8, 'BACKOFFICE': 8, 'ADITIVOS': 8, 'MONITORAMENTO_CONTRATUAL': 8, 'APOIO_LICITACAO': 8} — REAJUSTE=0
- Sample30: empty fields 0/0/0/0; near-dup blocked=False
- Unique why_this_account in feed: 49
- Warmbly local import: multi-service preserved; email_send_ready=0 fail-closed

## Remaining blockers for GO_FOR_CONTROLLED_PILOT

- No live EMAIL_SEND_READY cohort of 50 with real COMPANY_OWNED verified contacts — clean import fail-closed (email_send_ready=0) by design (.invalid contacts + kill switch).
- Full DSN national universe rebuild (3.6M contracts) not re-executed under construction/target_fit v2; offline rescore of existing 48,748 eligibles only.
- Operator merge/deploy of fix branches + human review of new-30/new-10 still required.
- Warmbly import target was local warmbly_dev, not production VPS.

## Principle

Automation must not scale a wrong commercial premise. Honest state: **NO_GO**, dispatch PAUSED.

## MessageSpine recovery pass (2026-08-09T22:50:53Z)

Structural production-spine fix:

1. `message_spine.py` — single observed_fact/body_seed from contract objeto/órgão
2. Gates: hollow fact, service evidence, any-pair near-dup
3. Router specialty only with specialty signals
4. Organic sample `sampling=organic_top_n` — prior 8/family mix invalidated
5. Verdict remains **NO_GO**

Organic sample30 struct_ok=True near_dup_blocked=False
svc={'gestao_monitoramento_contratual': 24, 'apoio_licitacoes_propostas': 6} top_frac=0.8 concentration=ROUTING_CONCENTRATION_REVIEW_REQUIRED

