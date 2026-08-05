# Metodologia — Reajuste em sentido estrito (Lei nº 14.133/2021)

**Módulo:** `2.0.0`
**Unidade comercial:** fornecedor (CNPJ) com contratos vinculados
**Campanha:** reajuste periódico por índice contratual
**NÃO cobre:** reequilíbrio econômico-financeiro, repactuação de mão de obra, atualização monetária por atraso de pagamento, aditivo quantitativo.

## Fundamento jurídico mínimo

- Lei nº 14.133/2021, art. 6º, LVIII (reajustamento)
- art. 25, § 7º (índice e data-base do orçamento estimado)
- art. 92, V e § 3º (cláusulas necessárias)
- art. 123 e art. 136, I (apostila)
- Lei nº 10.192/2001 (periodicidade mínima anual)

## Premissas operacionais (v2)

1. Data-base = **orçamento estimado** (CONFIRMED). Assinatura/publicação/OS são apenas `TEMPORAL_CANDIDATE_BY_PROXY`.
2. Assinatura &lt; 12 meses **não** exclui o contrato se a data-base documental já completou o interregno.
3. Índice só é atribuído se semanticamente vinculado à **cláusula de reajuste** (não bastam menções a SINAPI/IPCA no memorial).
4. PDF binário localizado ≠ texto extraído ≠ gate documental.
5. Ausência de apostila no PNCP **não prova** que o reajuste não foi concedido e **não** autoriza `OUTREACH_READY`.
6. Valores `VALUE_OUTLIER_REQUIRES_REVIEW` não elevam score financeiro nem honorários.
7. Varredura integral do pré-filtro com paginação **keyset**; sem limite silencioso de 25k.
8. Ferramenta **qualifica**; não emite parecer jurídico nem envia mensagens.

## Gates comerciais (distintos da classificação jurídica)

| Status | Significado |
|--------|-------------|
| OUTREACH_READY | 13 gates (empresa privada, obra, 14.133 comprovado, cláusula, data-base, índice, interregno, obrigação aberta, valor plausível, contato, revisão humana, argumento não enganoso) + base financeira |
| OUTREACH_READY_WITHOUT_VALUE_ESTIMATE | Idem sem cifra de valor potencial |
| DOCUMENT_REQUEST_CANDIDATE | Forte sinal; abordagem só exploratória pedindo documentos |
| NOT_READY_FOR_OUTREACH | Fora da fila operacional (inclui todo `LEGAL_REGIME_UNKNOWN`) |

## Funil jurídico/documental

| Status | Significado |
|--------|-------------|
| HOT_VERIFIED | 10 gates documentais |
| STRONG_CANDIDATE / REVIEW_REQUIRED / RESEARCH_REQUIRED | Lacunas |
| LEGAL_REGIME_UNKNOWN / LEGAL_REGIME_CONFLICT | Regime não comprovado / contraditório |
| ALREADY_ADJUSTED / CLOSED / NOT_ELIGIBLE | Fora do claim aberto |

## Scoring

Pesos v1 mantidos; atratividade financeira zera se valor não validado/outlier.

## Limitações honestas

- PNCP estruturado sem data-base/índice/regime nativos.
- HTML do portal raramente contém cláusula integral.
- Séries oficiais de índice exigem fonte externa licenciada (não inventar).
- `NO_PRIOR_ADJUSTMENT_LOCATED` ≠ prova de inexistência de reajuste.
