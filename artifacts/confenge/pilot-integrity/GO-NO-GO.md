# GO-NO-GO — CONFENGE pilot integrity recovery

Date: 2026-08-09T21:50:10Z
Dispatch: **PAUSED** | Kill switch: **ENGAGED** | WhatsApp: OFF | GREEN autorun: OFF

## Verdict

```
NO_GO
```

## Evidence summary

### Incident-10 (COPY-SAMPLE-2026-08-10)

| Metric | Value |
|--------|------:|
| FALSE_TARGET | 6 |
| TRUE_TARGET | 2 |
| TARGET_REQUIRES_RESEARCH | 2 |
| Warmbly service | REAJUSTE_14133 (10/10) |
| EMAIL_SEND_READY after fix | 0 |

### National offline rescore

| Metric | Value |
|--------|------:|
| Rows | 48748 |
| TARGET_CONFIRMED | 5606 |
| TARGET_PROBABLE_RESEARCH | 39212 |
| TARGET_OUT_OF_SCOPE | 3930 |

### Clean feed + samples (fixed router)

| Metric | Value |
|--------|------:|
| Leads | 49 |
| Service mix | {'REEQUILIBRIO': 1, 'PLANILHAS': 8, 'MEDICOES': 8, 'BACKOFFICE': 8, 'ADITIVOS': 8, 'MONITORAMENTO_CONTRATUAL': 8, 'APOIO_LICITACAO': 8} |
| REAJUSTE | 0 |
| Unique why_this_account | 49 |
| Sample30 empty why/micro/fact/ev | 0/0/0/0 |
| Near-duplicate blocked | False (max_sim=0.9394) |
| Concentration flag | None (top 16.3%) |
| Structural sample gates | PASS |

## Why NO_GO (concrete blockers)

1. No live EMAIL_SEND_READY cohort of 50 with real COMPANY_OWNED verified contacts — clean import fail-closed (email_send_ready=0) by design (.invalid contacts + kill switch).
2. Full DSN national universe rebuild (3.6M contracts) not re-executed under construction/target_fit v2; offline rescore of existing 48,748 eligibles only.
3. Operator merge/deploy of fix branches + human review of new-30/new-10 still required.
4. Warmbly import target was local warmbly_dev, not production VPS.

## Safety

- Kill switch ENGAGED
- No dispatch / auto-send / WhatsApp
- No email to real leads
- Contaminated COPY-SAMPLE not reused
- REAJUSTE monoculture broken in clean feed

## Artifact paths

- `current-10-forensics.csv` / `CURRENT-10-FORENSICS.md`
- `target-fit-audit.csv` / `service-routing-audit.json`
- `new-30-draft-sample.md` / `new-10-human-review.md`
- `cross-repo-service-contract.json`
- `rebuild-2026-08-09/confenge-outreach-v1-clean.json`
- `FINAL-REPORT.md`

## Panel submission

- `PANEL-SUBMISSION.md` — package for adversarial verification (ends **NO_GO**)
- extra-cli PR: https://github.com/tjsasakifln/extra-cli/pull/211
- warmbly PR: https://github.com/tjsasakifln/warmbly/pull/34
