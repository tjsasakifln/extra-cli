# Story 415 — Engine inbound de comparáveis (canário pavimentação)

Status: InReview
Risk: HIGH-RISK (contratos públicos, contrato de saída versionado)
Issue: #415
Branch: feat/inbound-comparables-415

## Problema

Não há no `origin/main` um producer fail-closed que responda, de forma reproduzível, como o valor integral nominal de um contrato de pavimentação se posiciona frente a pares comparáveis — e que saiba recusar a comparação com reason codes nominais.

## Escopo IN

- Engine + CLI em `scripts/contract_comparables`
- Schema `comparable-contracts/1.0` + serializer + hash
- Corpus golden de 7 casos
- Testes no código enviado
- README, INTEGRATION_NOTES, relatório de observabilidade

## Escopo OUT

- Migration
- Edição de publication/adapters/national-claims
- Custo/km, sobrepreço, ranking nacional, API, páginas
- Fechar #415 sem live/integração comprovados

## AC

Given um corpus fixture e um focal de pavimentação comparável, when o CLI `build` roda duas vezes, then status é COMPARABLE e peer_group_id/métricas/content_hash são idênticos.

Given recortes incompatíveis (regime, geo/período, n, valores UNKNOWN, duplicata, unidade), when o engine avalia, then o estado é HOLD_FOR_DATA ou NOT_COMPARABLE com reason code nominal.

Given um outlier estatístico em amostra válida, when o documento é emitido, then não há linguagem de sobrepreço/irregularidade.
