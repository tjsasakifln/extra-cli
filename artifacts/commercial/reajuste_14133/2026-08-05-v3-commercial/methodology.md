# Metodologia — Reajuste em sentido estrito (Lei nº 14.133/2021)

**Módulo:** `3.0.0`
**Unidade comercial:** fornecedor (CNPJ) com contratos vinculados
**Campanha:** reajuste periódico por índice contratual
**NÃO cobre:** reequilíbrio econômico-financeiro, repactuação de mão de obra, atualização monetária por atraso de pagamento, aditivo quantitativo.

## Fundamento jurídico mínimo

- Lei nº 14.133/2021, art. 6º, LVIII (reajustamento)
- art. 25, § 7º (índice e data-base do orçamento estimado)
- art. 92, V e § 3º (cláusulas necessárias)
- art. 123 e art. 136, I (apostila)
- Lei nº 10.192/2001 (periodicidade mínima anual)

## Premissa temporal conservadora (v3)

Para obras regidas ou **provavelmente** regidas pela Lei 14.133/2021:

1. A data-base do reajuste vincula-se à data do **orçamento estimado**.
2. O orçamento estimado **necessariamente antecede** a contratação/assinatura.
3. Se a assinatura ocorreu há **mais de doze meses**, o primeiro interregno anual já
   transcorreu de forma **conservadora** (`minimum_interregnum_elapsed=true`),
   mesmo sem data-base exata.
4. A ausência da data-base exata **bloqueia cálculo e afirmação conclusiva**, mas
   **não** impede classificar o contrato como `LIKELY_ADJUSTMENT_OPPORTUNITY`
   nem autorizar abordagem **diagnóstica**.
5. Proxy (publicação/início) **nunca** é apresentado como data-base legal.
6. Ausência de apostila = **incerteza**, não prova positiva nem exclusão automática.
7. Ausência de contato bloqueia só `DIAGNOSTIC_OUTREACH_READY`, não a fila de leads.

## Estados comerciais (v3)

| Estado | Significado |
|--------|-------------|
| POTENTIAL_ADJUSTMENT_SIGNAL | Sinais mínimos de maturidade anual em obra |
| LIKELY_ADJUSTMENT_OPPORTUNITY | Oportunidade provável (sem exigir data-base/índice/contato/humano) |
| DIAGNOSTIC_OUTREACH_READY | Abordagem diagnóstica prudente (exige contato verificável) |
| DOCUMENT_REQUEST_READY | Ação comercial válida: pedir documentos (pode coexistir) |
| VERIFIED_ADJUSTMENT_OPPORTUNITY | Pack documental + revisão humana; ainda sem valor |
| CALCULABLE_ADJUSTMENT_CLAIM | Único estado com `valor_potencial` |

## Dimensões independentes

`signal_status`, `legal_confidence`, `temporal_confidence`, `documentary_confidence`,
`execution_confidence`, `adjustment_history_confidence`, `contact_readiness`,
`human_review_status`, `commercial_action`, `claim_readiness`.

## Hierarquia temporal A–D

| Nível | Evidência | Cálculo | Diagnóstico |
|-------|-----------|---------|-------------|
| A | Data-base exata do orçamento | se interregno OK | sim |
| B | Assinatura &gt; 12 meses | bloqueado | sim |
| C | Proxy (publicação/início) antigo | bloqueado | não (menor confiança) |
| D | Insuficiente | bloqueado | não |

## Pipeline em duas fases

1. **Triagem nacional barata** — dados estruturados; consolidação por fornecedor.
2. **Aprofundamento orientado a valor** — documentos e contatos só dos prioritários
   (Sul/SC, ICP, valor, idade &gt;12m, multi-contrato, não-gigante).

## Scoring v3

| Score | O que mede |
|-------|------------|
| opportunity_score | Probabilidade de dor comercial relevante |
| verification_score | Qualidade das evidências |
| commercial_fit_score | Aderência ICP CONFENGE |
| priority_score | Ordenação do trabalho humano |

Falta de documento ↓ verification, **não** zera opportunity.
Falta de contato ↓ contact_readiness, **não** remove da fila.

## Fail-closed (apenas claims)

- Somente `CALCULABLE_ADJUSTMENT_CLAIM` pode exibir `valor_potencial`.
- Nenhuma mensagem afirma crédito devido sem verificação documental + revisão humana.
- `human_review_completed` só via `--human-review-file` (nunca automático).

## Premissas operacionais legadas (ainda válidas)

1. Data-base legal = **orçamento estimado** (CONFIRMED). Assinatura/publicação/OS são proxy.
2. Índice só se semanticamente vinculado à **cláusula de reajuste**.
3. PDF binário ≠ texto extraído ≠ gate documental de claim.
4. Varredura integral keyset; sem limite silencioso de 25k.
5. Ferramenta **qualifica**; não envia mensagens automaticamente.

## Gates de claim (legado, fail-closed)

| Status | Significado |
|--------|-------------|
| OUTREACH_READY | Pack claim completo + humano + valor |
| OUTREACH_READY_WITHOUT_VALUE_ESTIMATE | Pack claim sem cifra |
| TECHNICALLY_VERIFIED_PENDING_TIAGO | Técnico completo, aguarda humano |
| DOCUMENT_REQUEST_CANDIDATE | Legado; preferir estados v3 |

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
