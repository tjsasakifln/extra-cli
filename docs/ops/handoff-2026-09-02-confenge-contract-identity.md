# Handoff — identidade contratual CONFENGE / #468

Data: 2026-09-02

## Estado

`IMPLEMENTED`, não aceito. O candidato local parte de `main` no
`1b9db789b968b483d507ee26ab0fd3fa662ad302` (#529) e corrige a precedência que
antes publicava o BIGSERIAL técnico `id` como contrato público.

O feed histórico `full-national-2026-08-07` contém 1.214 referências de
contrato, todas numéricas curtas. O manifest do universo daquele run registra
que `contrato_id` não existia na tabela consultada. A origem PNCP, por sua vez,
produz `numeroControlePNCP` como `contrato_id` canônico.

## Contrato implementado

- `contrato_id`, `numero_controle_pncp` e `contract_id` são as únicas formas
  públicas aceitáveis, nesta ordem.
- `id` é cursor técnico; só é aceito por chamador com opt-in explícito para
  legado (`allow_legacy_surrogate_contract_id`).
- O universo e o loader de target-fit recusam uma linha cujo ID oficial esteja
  ausente ou em branco.
- A projeção de portfolio, target-fit, inteligência, bridge e party-role usa o
  mesmo resolvedor de identidade.

## Evidência local

- Teste adversarial com `id=25394409` e
  `numero_controle_pncp=00028986000108-1-000123/2026` prova cursor por `id` e
  identidade emitida PNCP.
- Loader de target-fit seleciona e prefere `numero_controle_pncp`.
- IDs oficiais nulos/em branco causam recusa fail-closed.
- Regressão focal: 48 testes verdes; ruff verde.

## Próximos gates — estritamente ordenados

1. Publicar o commit isolado e obter CI verde no SHA exato.
2. Integrar em `main`.
3. Executar `confenge_code_freeze mark-final-integrity-freeze` no tip integrado;
   não editar artefatos de freeze manualmente nem reutilizar #533.
4. Executar os verificadores de binding e a prova live pós-deploy.
5. Manter #468 fail-closed até a prova contemporânea de Sistema S/parafiscais
   fora de `TARGET_CONFIRMED`, sem perda não explicada de construtoras.
