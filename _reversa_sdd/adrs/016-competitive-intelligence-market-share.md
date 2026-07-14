# ADR-016: Competitive Intelligence — Market Share e HHI (Regra #9)

**Data:** 2026-07-12
**Status:** Aceito
**Autor:** Regra #9 — Competitive Intelligence (commit 77265b5)
**Stakeholders:** Extra Consultoria

---

## Contexto

O sistema precisava fornecer inteligência competitiva para a Extra Consultoria:

1. Quem são os maiores fornecedores por valor de contrato?
2. Qual a concentração de mercado (HHI) por entidade e global?
3. Como cada fornecedor se posiciona em número de contratos, valor e entidades atendidas?
4. Qual a taxa de vitória (win rate) de cada fornecedor?

Os dados disponíveis são contratos PNCP (`pncp_supplier_contracts`), que contêm `cnpj_fornecedor`, `valor_global`, e `orgao_cnpj`. Não há dados de resultado de licitação (quem competiu e perdeu).

## Decisão

Implementar camada de competitive intelligence com 4 métricas, usando apenas dados contratuais confirmados:

1. **Market Share:** `share = valor_fornecedor / valor_total_entidade` — TOP 20 fornecedores
2. **Award Share:** concentração de awards por entidade (quem domina cada órgão)
3. **HHI (Herfindahl-Hirschman Index):** `Σ(share²)` — global + por entidade
4. **Supplier Ranking:** ordenado por (1) número de contratos, (2) valor total, (3) entidades distintas

**Ordenação:** `ORDER BY total_value DESC` — corrigido de `total_contracts` (commit 8f55fd6).

**Win rate:** permanece `NOT_READY`. Métricas alternativas disponíveis (market share, award share, supplier ranking) enquanto dados de resultado de licitação não estão disponíveis.

**Segurança:** todas as queries usam `_safe_metric_query()` com per-query timeout para evitar locks no banco de produção.

## Consequências

- Competitive intelligence funciona apenas com dados PNCP contracts (fonte única atual)
- HHI classifica concentração: ≤2=BAIXA, ≤5=MEDIA, ≤10=ALTA, >10=MUITO_ALTA
- Win rate requer dados de resultado de licitação — lacuna conhecida, documentada
- Duplicate `win_rate` key removido do output (commit 8f55fd6)
