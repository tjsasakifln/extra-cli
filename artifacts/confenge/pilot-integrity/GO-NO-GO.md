# GO-NO-GO — CONFENGE pilot integrity recovery

Date: 2026-08-09T21:24:20Z
Dispatch: **PAUSED** | Kill switch: **ENGAGED** | WhatsApp: OFF | GREEN autorun: OFF

## Verdict

```
NO_GO
```

## Warmbly import evidence (this session)

| Item | Result |
|------|--------|
| Feed | `warmbly/data/confenge-feeds/pilot-integrity-clean-v1.json` |
| Dry-run | creates=48 updates=2 blocked=0 errors=0 (50 leads) |
| Apply | creates=48 updates=2 blocked=0 errors=0 (50 leads) |
| Service mix | MONITORAMENTO 19 · PLANILHAS 16 · APOIO_LICITACAO 10 · BACKOFFICE 5 |
| **REAJUSTE count** | **0 / 50** (monoculture broken) |
| `email_send_ready=true` | **0 / 50** (fail-closed) |
| Hard ICP FP (incident class) | **0 / 50** |
| Borderline names | 2 (TREINAMENTOS, ASSESSORIA) — not auto-send |
| Kill switch file | `warmbly/data/confenge-kill-switch` present |
| Import run IDs | see `rebuild-2026-08-09/warmbly-import-evidence.json` |

### Why `email_send_ready` is all false (correct)

1. Synthetic contacts on `.invalid` domains (no real delivery possible)
2. Feed explicitly set `email_send_ready=false` / `dispatch_authorized=false`
3. Kill switch engaged (`confenge stop-sending`)
4. `CONFENGE_AUTO_SEND_ENABLED=false`

This is **not** a regression: the previous bug was false EMAIL_SEND_READY on non-ICP firms with REAJUSTE. Post-fix import refuses send-ready while preserving multi-service routing on construction names.

## Offline structural gates (extra-cli rescore)

| Gate | Result |
|------|--------|
| Universe rescore 48748 | CONFIRMED 5606 / RESEARCH 39212 / OUT 3930 |
| Sample50 human hard FP | 0 |
| Sample30 near-dup | not blocked (max_sim≈0.61) |
| Sample30 empty copy fields | 0 |

## Why still NO_GO (concrete blockers)

1. **No live EMAIL_SEND_READY cohort of 50** — fail-closed left all 50 as non-send-ready; cannot claim pilot-ready send queue without real COMPANY_OWNED verified contacts + populated target_fit_send_tier on Warmbly.
2. **2 borderline names** in import sample need RESEARCH disposition before any send path.
3. **Full DSN universe rebuild (3.6M)** not re-run under construction v2 (offline rescore of existing eligibles only).
4. **Operator merge/deploy** of fix branches + human review of new-30/new-10 still required.
5. **Production Warmbly/VPS** not the local import target — local `warmbly_dev` only.

## Safety invariants verified this session

- Kill switch ENGAGED
- No dispatch / no auto-send
- No email to real leads (`.invalid` contacts only)
- Contaminated COPY-SAMPLE drafts not reused
- REAJUSTE monoculture absent in clean import

## Next for a future GO_FOR_CONTROLLED_PILOT

1. Merge `fix/confenge-pilot-target-service-integrity` (extra-cli) + `fix/confenge-pilot-service-copy-integrity` (warmbly)
2. Optional full DSN rebuild
3. Resolve real contacts only for TARGET_CONFIRMED
4. Warmbly import on staging/prod with dispatch PAUSED + kill switch
5. Human audit of any EMAIL_SEND_READY until 50 with 0 hard FP
6. Operator explicit enable for controlled pilot morning
