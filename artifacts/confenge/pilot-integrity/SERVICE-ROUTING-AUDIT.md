# SERVICE-ROUTING-AUDIT

Timestamp: 2026-08-10T03:06:34.314899+00:00
Universe: 48748 · TARGET_CONFIRMED: 5431

## Confirmed primary distribution

```
{
  "gestao_monitoramento_contratual": 3793,
  "apoio_licitacoes_propostas": 681,
  "reforco_temporario_backoffice": 825,
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

- **GESTAO_SUPPORTED**: multi_contract with diversity (órgãos/UFs) or n≥5
- **GESTAO_GENERIC_FALLBACK**: thin multi_contract / fallback signals — **NOT SERVICE_FIT_SUPPORTED**
- **GESTAO_NEEDS_RESEARCH**: residual non-supported

## Family SERVICE_FIT counts

```
{
  "gestao_monitoramento_contratual:FIT": 3483,
  "apoio_licitacoes_propostas:FIT": 681,
  "gestao_monitoramento_contratual:NO_FIT": 310,
  "reforco_temporario_backoffice:FIT": 825,
  "auditoria_orcamento_bdi:FIT": 86,
  "aditivos_extracontratuais:FIT": 41,
  "medicoes_glosas_memoria:FIT": 3,
  "reequilibrio_economico_financeiro:FIT": 2
}
```

## Ten-family coverage (CONFIRMED primaries)

```
{
  "estruturacao_pleito_reajuste": 0,
  "reequilibrio_economico_financeiro": 2,
  "aditivos_extracontratuais": 41,
  "medicoes_glosas_memoria": 3,
  "auditoria_orcamento_bdi": 86,
  "gestao_monitoramento_contratual": 3793,
  "apoio_licitacoes_propostas": 681,
  "inteligencia_pncp_mercado": 0,
  "diagnostico_contratual_b2g": 0,
  "reforco_temporario_backoffice": 825
}
```

Unknown → REAJUSTE: fail-closed (unit + warmbly playbook).
