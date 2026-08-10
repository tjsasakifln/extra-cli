# SERVICE-ROUTING-AUDIT

## Structural-ready primary distribution (post MessageSpine + SERVICE_FIT)

```
{
  "gestao_monitoramento_contratual": 2943,
  "apoio_licitacoes_propostas": 594,
  "medicoes_glosas_memoria": 3,
  "aditivos_extracontratuais": 33,
  "auditoria_orcamento_bdi": 80,
  "reequilibrio_economico_financeiro": 1,
  "reforco_temporario_backoffice": 549
}
```

## Gestão among structural-ready (post-filter)

```
{
  "GESTAO_SUPPORTED": 2943
}
```

Note: `GESTAO_GENERIC_FALLBACK excluded from structural-ready by service_fit gate; structural list is post-filter`

GESTAO_GENERIC_FALLBACK is excluded from SERVICE_FIT_SUPPORTED / structural-ready by design.
Unknown → REAJUSTE remains fail-closed (unit + warmbly).

## ESR service dist (n=49)

```
{
  "gestao_monitoramento_contratual": 38,
  "apoio_licitacoes_propostas": 9,
  "auditoria_orcamento_bdi": 1,
  "reforco_temporario_backoffice": 1
}
```
