# ADR-038 — Autoridade comercial durável da CONFENGE

**Status:** Accepted by founder decision (2026-08-31)

**Capability:** CONFENGE first-touch outbound

## Decisão canônica

Um fornecedor é lead comercial quando existe em `public.v_contracts_canonical_v2`
um contrato no qual ele é a parte fornecedora, a parte compradora é distinta, o
objeto passa no classificador canônico de obra ou serviço de engenharia e a data
do ato contratual permanece na janela móvel de três anos.

Essa verdade vem do contrato persistido no datalake. Ela não depende de uma
consulta ao PNCP durante a qualificação, publicação, importação ou transporte.
Freshness, atraso, indisponibilidade ou falha do PNCP são telemetria do plano de
ingestão: jamais revogam, congelam ou bloqueiam um lead já comprovado no
datalake.

## Contrato operacional

- `COMMERCIAL_AUTHORITY/2.0` é a autoridade populacional e cada lead carrega
  sua `commercial_qualification` reproduzível por CNPJ raiz.
- A precedência da data é `data_assinatura`, `data_inicio`, `data_publicacao`,
  `data_publicacao_fonte`; `data_fim` não qualifica.
- `qualified_until` é exatamente a data qualificadora + 3 anos, com a mesma
  normalização de `time.AddDate` do consumidor. No dia da expiração o fato já
  não autoriza transporte.
- Registro inativo/revogado, objeto não aderente, fornecedor=comprador,
  evidência/hash inválido, janela vencida ou datalake indisponível bloqueiam a
  reconstrução/publicação de forma fechada.
- DNC, supressões, ausência de contato apto e demais controles do transporte
  continuam independentes e obrigatórios.
- `extra-confenge-feed-cycle.timer` executa a reconstrução/publicação em cadence
  própria e usa `flock`. `pncp-contracts.timer` apenas ingere; não existe
  `OnSuccess` entre PNCP e o ciclo comercial.

## Consequências

Target-fit permanece disponível para pesquisa e priorização, mas não define a
população comercial e nenhuma tabela `*_target_fit_*` participa da reconstrução
V2. O wire mantém `TARGET_CONFIRMED` somente como compatibilidade do contrato de
feed; sua origem declarada é `COMMERCIAL_AUTHORITY_POLICY/2.0`.
