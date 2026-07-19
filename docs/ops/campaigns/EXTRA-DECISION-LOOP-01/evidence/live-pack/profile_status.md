# Profile status — extra_construtora

- **Hash:** `db621d0de72e523f…`
- **Versão:** 2
- **Resolvido em:** 2026-07-19T21:53:22Z
- **Override local:** não
- **Pendentes críticos:** 11

## Pendentes críticos

- `capital_giro` — Sem capital de giro → REVIEW (não PARTICIPAR automático)
- `capacidade_simultanea` — Sem capacidade simultânea → REVIEW comercial
- `cats_atestados` — Sem CATs → REVIEW técnico (habilitação)
- `equipe` — Sem equipe declarada → REVIEW operacional
- `equipamentos` — Sem equipamentos → REVIEW operacional
- `certidoes` — Sem certidões → REVIEW de habilitação
- `margem_minima` — Sem margem mínima → REVIEW comercial
- `risco_aceitavel` — Sem apetite de risco → REVIEW comercial
- `contratos_atuais` — Sem contratos atuais → REVIEW de capacidade
- `apetite_consorcios` — Sem política de consórcio → REVIEW quando consórcio for opção
- `capacidade_garantia` — Sem capacidade de garantia → REVIEW comercial

## Perguntas mínimas

- Capital de giro disponível para garantias e capital de obra (R$)?
- Quantas obras/contratos a Extra consegue executar em paralelo?
- Listar CATs/atestados técnicos principais (objeto, valor, ano, órgão).
- Preencher campo `equipe` (Sem equipe declarada → REVIEW operacional)
- Preencher campo `equipamentos` (Sem equipamentos → REVIEW operacional)
- Preencher campo `certidoes` (Sem certidões → REVIEW de habilitação)
- Preencher campo `margem_minima` (Sem margem mínima → REVIEW comercial)
- Preencher campo `risco_aceitavel` (Sem apetite de risco → REVIEW comercial)
- Preencher campo `contratos_atuais` (Sem contratos atuais → REVIEW de capacidade)
- Preencher campo `apetite_consorcios` (Sem política de consórcio → REVIEW quando consórcio for opção)
- Capacidade máxima de garantia contratual (R$)?

## Política

- Ausência material → **REVIEW**, não auto-NÃO_PARTICIPAR.
- Dados sensíveis reais ficam só em `extra.local.yaml` (gitignored).
