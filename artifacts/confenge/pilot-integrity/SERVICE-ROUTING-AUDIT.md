# SERVICE-ROUTING-AUDIT

## Confirmed primary distribution (rescore)

```
{
  "gestao_monitoramento_contratual": 3793,
  "reforco_temporario_backoffice": 825,
  "apoio_licitacoes_propostas": 681,
  "auditoria_orcamento_bdi": 86,
  "aditivos_extracontratuais": 41,
  "medicoes_glosas_memoria": 3,
  "reequilibrio_economico_financeiro": 2
}
```

## Gestão adversarial split

```
{
  "GESTAO_SUPPORTED": 3793
}
```

Interpretation: all gestão primaries carried multi_contract/structure signals (GESTAO_SUPPORTED).
Still **not** permission for GO while EMAIL_SEND_READY < 50 and template gates fail.

## Unknown → REAJUSTE

Fail-closed unit tests + warmbly playbook: unknown never maps to REAJUSTE.
