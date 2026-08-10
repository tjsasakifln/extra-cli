# SERVICE-ROUTING-AUDIT

## Confirmed primary distribution (universe rescore)

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

## Gestão adversarial split (required buckets)

```
{
  "GESTAO_SUPPORTED": 3483,
  "GESTAO_GENERIC_FALLBACK": 310
}
```

- **GESTAO_SUPPORTED**: multi_contract with diversity (órgãos/UFs) or structure_robust / n≥5
- **GESTAO_GENERIC_FALLBACK**: multi_contract_thin / fallback signals (NOT SERVICE_FIT_SUPPORTED)
- **GESTAO_NEEDS_RESEARCH**: residual non-supported (if any)

## Family SERVICE_FIT counts (sample)

```
{
  "gestao_monitoramento_contratual:FIT": 3483,
  "reforco_temporario_backoffice:FIT": 825,
  "apoio_licitacoes_propostas:FIT": 681,
  "gestao_monitoramento_contratual:NO_FIT": 310,
  "auditoria_orcamento_bdi:FIT": 86,
  "aditivos_extracontratuais:FIT": 41,
  "medicoes_glosas_memoria:FIT": 3,
  "reequilibrio_economico_financeiro:FIT": 2
}
```

Unknown → REAJUSTE: fail-closed (unit + warmbly playbook).
