# EMAIL-SEND-READY-50-AUDIT

## Counts

| Metric | Value |
|--------|------:|
| EMAIL_SEND_READY (natural join) | **54** |
| Threshold | 50 |
| Meets gate | **YES** |
| FALSE_TARGET | **0** |
| WRONG_CONTACT | **0** |
| UNSUPPORTED_SERVICE | **0** |
| HOLLOW_COPY_CONTEXT | **0** |
| UNSAFE_CLAIM | **0** |

## Policy (no gaming)

- TARGET_CONFIRMED only (reclassified live)
- SERVICE_FIT_SUPPORTED (gestão requires multi_contract + diversity / robust)
- MessageSpine complete with **dated** why_now (WEAK ⇒ excluded)
- COPY_CONTEXT_READY (hollow language banned)
- Contacts: preexisting public COMPANY_OWNED emails only; free-mail domains excluded
- No PROBABLE→CONFIRMED promotion; no manual lead stuffing; no threshold move

## Lineage

universe TARGET_CONFIRMED + MessageSpine complete + SERVICE_FIT + COPY_CONTEXT + preexisting public company emails (enrichment/VPS index), not invented

## Service distribution (full ready set)

```
{
  "gestao_monitoramento_contratual": 42,
  "apoio_licitacoes_propostas": 11,
  "reforco_temporario_backoffice": 1
}
```
