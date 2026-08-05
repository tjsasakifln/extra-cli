# Metodologia — Reajuste em sentido estrito (Lei nº 14.133/2021)

**Módulo:** `2.0.0`
**Campanha:** reajuste periódico por índice contratual
**NÃO cobre:** reequilíbrio econômico-financeiro, repactuação de mão de obra, atualização monetária por atraso de pagamento, aditivo quantitativo.

## Fundamento jurídico mínimo

- Lei nº 14.133/2021, art. 6º, LVIII (reajustamento)
- art. 25, § 7º (índice e data-base do orçamento estimado)
- art. 92, V e § 3º (cláusulas necessárias)
- art. 123 e art. 136, I (apostila)
- Lei nº 10.192/2001 (periodicidade mínima anual)
- Orientação TCU sobre reajuste em sentido estrito

## Premissas operacionais

1. Data-base vinculada à data do **orçamento estimado**.
2. Primeiro reajuste somente após interregno anual.
3. Assinatura, publicação, OS e início de execução **não** são data-base automática.
4. Índice deve constar do edital/contrato — nunca inventado (IPCA/INCC/SINAPI por “plausibilidade” é proibido).
5. Reajuste ordinário pode ser registrado por **apostila**.
6. Ausência de apostila no PNCP **não prova** que o reajuste não foi concedido.
7. Ausência de cláusula é inconsistência documental — o sistema **não inventa** índice/data-base.
8. Ferramenta **qualifica oportunidades**; não emite conclusão jurídica definitiva.

## Funil de classificação

| Status | Significado |
|--------|-------------|
| HOT_VERIFIED | 10 gates documentais atendidos |
| STRONG_CANDIDATE | Forte probabilidade; falta confirmação pontual |
| REVIEW_REQUIRED | Indício relevante com lacunas |
| RESEARCH_REQUIRED | Dados insuficientes para abordagem responsável |
| ALREADY_ADJUSTED | Evidência de reajuste do período |
| NOT_ELIGIBLE | Fora das regras materiais/temporais |
| LEGAL_REGIME_UNKNOWN | Regime 14.133 não comprovado |
| CLOSED_OR_FINANCIALLY_EXHAUSTED | Encerrado / sem saldo |

**Regra dura:** nenhum `HOT_VERIFIED` pode depender apenas de datas de `pncp_supplier_contracts`.

## Scoring comercial

- 25% confiança jurídica/documental
- 20% atratividade financeira
- 15% urgência temporal
- 15% saldo reajustável provável
- 10% aderência ICP CONFENGE
- 10% contatabilidade empresarial
- 5% qualidade das fontes

Penalidades: regime não confirmado, data-base ausente, índice ausente, encerramento próximo sem docs, execução concluída, reajuste já publicado, contradições, fornecedor gigante, micro vs ticket, contato apenas pessoal.

## Finanças

- `valor_potencial`: só com índice contratual + série oficial + base reajustável conhecida.
- `teto_teorico` / `UPPER_BOUND_NOT_CLAIM_VALUE`: envelope sobre valor total **sem** pretensão de valor devido.

## Limitações honestas

- Schema PNCP estruturado **não** traz data-base de orçamento, índice nem regime legal nativos.
- `process_documents` pode estar vazio no snapshot; fetches HTML/PDF são parciais.
- Classificação de obra é híbrida (regras + vocabulário negativo), sem LLM operacional em massa.
- Contatos apenas de fontes empresariais públicas (LGPD).
