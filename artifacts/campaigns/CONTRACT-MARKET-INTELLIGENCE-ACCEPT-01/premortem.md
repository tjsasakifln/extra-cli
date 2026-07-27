# Pré-mortem — CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01

**Baseline**

| Campo | Valor |
|-------|-------|
| MAIN_BASELINE_SHA | `c5b4cdb91b0727b5e7a537c8eb47daf001b74552` |
| DOD_BASELINE_HASH | `df2388b7fc3887558c17efe2bd6318c8ce73b2a8` |
| N_TOTAL | 1462 |
| N_ACCEPTED | 354 |
| N_OPEN_INITIAL | 1107 |
| N_BLOCKED_INITIAL | 1 |
| acceptance_pct auditado | 2.87% |
| claimed_pct | 24.35% |
| W_OPEN_INITIAL (prior peso=3) | 3321 |
| TARGET_RAW | 47 (4.25% ≥ 3%) |
| TARGET_WEIGHTED | 197 (5.93% ≥ 5%) |

**CONVERGENCE_FAILURE_DETECTED:** sim — sequência #141–#150 em hardening/política/recall foundation sem delta DOD material no pacote de concorrentes/valores.

**PRs abertas:** #133 bid-readiness (fora), #139 recall (fora). Nenhuma PR aberta implementa CMI.

**IDs:** 47 itens §10.1+§10.2+§11.1 mapeados em `freeze.json` (prefixo `DOD-rol-1-definition-of-done-*`). Reserva §12.2 **não** necessária (pisos atingidos).

**Inventário baseline**

| Componente | Estado |
|------------|--------|
| deliverable_b_competitors | OK (audit-fixture PASS) |
| deliverable_d_prices | OK (audit-fixture PASS) |
| value_semantics | OK (4 tipos) |
| concorrentes_report / operational_reports | parcial — fallback órgão→concorrente **reproduzido e removido** |
| PostgreSQL :5433 | disponível; migrations aplicadas |
| Dados elegíveis | 0 antes do seed isolado CMI |

**Ataques residuais conhecidos**

| # | Ataque | Resultado |
|---|--------|-----------|
| 1 | query fornecedor → lista vazia silenciosa | REPRO — `_error` propagado; CMI levanta RuntimeError |
| 2 | órgão como concorrente | REPRO — fallback removido em `report_concorrentes` |
| 3 | fallback linhas vazias n_contratos | N/A após remoção do fallback |
| 4 | header-only | CMI exige population_count≥1 e CSV material |
| 5 | nomes reais tabelas/colunas | `require_table_columns` + information_schema |
| 6 | concorrentes ≠ contratos-por-fornecedor | competitor-review + reliability distinct roles |
| 7–15 | evidência/CI | cobertos no pacote de promoção |

**Decisão:** PREMORTEM_PASS — pacote elegível; lacuna predominante EVIDÊNCIA+EXECUÇÃO+reparo localizado (sem foundation).
