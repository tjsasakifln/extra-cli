---
name: Regra-9-Competitive-Intelligence
description: Competitive Intelligence (market share, award share, HHI, supplier ranking) implemented in consulting_readiness.py (Regra #9)
metadata:
  type: project
---

Competitive Intelligence — Regra #9 implementada em `scripts/consulting_readiness.py`.

"Contratos vencidos/total de licitações não é win rate. Sem participações, publicar market share, award share, ranking e HHI. Win rate real exige proposal_tracking."

Funções adicionadas:
- `_compute_market_share(conn, entity_cnpj8_list)` — market share por fornecedor no universo canônico (raio_200km), ordenado por valor total de contratos
- `_compute_award_share(conn, entity_cnpj8_list)` — concentração de awards por entidade pública (top suppliers por entidade)
- `_classify_hhi(hhi_value)` — classificação HHI (<1500 não concentrado, 1500-2500 moderado, >2500 altamente concentrado)
- `_compute_hhi(conn, entity_cnpj8_list)` — HHI global + por entidade
- `_compute_supplier_ranking(conn, entity_cnpj8_list, top_n=20)` — ranking por contratos, valor, entidades atendidas

Dict `commercial_metrics` atualizado com chave `competitive_intelligence` contendo `win_rate` (NOT_READY), `market_share`, `award_share`, `hhi`, `supplier_ranking`.

Print summary atualizado com seção dedicada "COMPETITIVE INTELIIGENCE (Regra #9)".

**Why:** Win rate real exige proposal_tracking (propostas enviadas vs vencidas). PNCP não expõe propostas perdedoras. As métricas de concentração (market share, HHI, ranking, award share) são alternativa válida usando apenas dados PNCP.

**How to apply:** Todas as queries usam `_safe_metric_query()` com per-query timeout e rollback. Usam conexão separada para não contaminar transações de cobertura. Rodam apenas no universo canônico (`e.raio_200km = TRUE`).
