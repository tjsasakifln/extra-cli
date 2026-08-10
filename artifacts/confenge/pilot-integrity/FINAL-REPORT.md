# FINAL-REPORT — CONFENGE pilot integrity recovery 02

## Verdict

**NO_GO** — pilot is safer in code than before this round, but **not** commercially send-ready under the written acceptance criteria.

## National rescore (live gates on 48,748 universe rows)

- TARGET_CONFIRMED: 5431
- TARGET_PROBABLE_RESEARCH: 38548
- TARGET_OUT_OF_SCOPE: 4769
- Service distribution (confirmed): {"gestao_monitoramento_contratual": 3793, "reforco_temporario_backoffice": 825, "apoio_licitacoes_propostas": 681, "auditoria_orcamento_bdi": 86, "aditivos_extracontratuais": 41, "medicoes_glosas_memoria": 3, "reequilibrio_economico_financeiro": 2}
- Gestão split: {"GESTAO_SUPPORTED": 3793}
- Structural ready (no contact): 46
- EMAIL_SEND_READY (prior feed revalidated): 0

## Code changes (this round)

### extra-cli
- Semantic template near-dup + blind template audit
- MessageSpine commercial why_you/why_now (no hollow meta)
- COPY_CONTEXT bans pipeline language
- Gestão fit evidence rules
- ruff clean confenge paths

### warmbly
- `StructuralApproveBlockers` reconstructible from account/strategy
- `ReviewDraft(approve)` fail-closed
- gofmt + tests

## Residual risks

1. EMAIL_SEND_READY volume collapse under honest copy quality (0 from prior 50 feed).
2. Gestão concentration still high among CONFIRMED (3793/5431) even when multi_contract-supported.
3. Production SHA mismatch until deploy.
4. Blind template still detects serial template reuse when feed bags lack strong diversifying facts.

## Honesty statement

No criterion was relaxed after observing results. NO_GO is intentional and correct.
