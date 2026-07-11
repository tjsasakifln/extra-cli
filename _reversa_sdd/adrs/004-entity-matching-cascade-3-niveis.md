# ADR-004: Entity Matching em Cascade de 3 Níveis

**Status:** Aceito
**Data:** 2026-07-10
**Decisor:** Claude (via Story 001.3)
**Fonte:** commit `5359cdb`, `monitor.py:_match_entities_cascade`

---

## Contexto

Licitações de fontes diferentes (PNCP, DOM-SC, PCP, ComprasGov) precisam ser associadas aos 2.085 órgãos públicos de SC. Fontes variam na qualidade dos dados: algumas têm CNPJ, outras só nome do órgão, outras só município. O sistema anterior usava apenas match exato por CNPJ.

## Decisão

**Implementar cascade de matching em 3 níveis progressivos: CNPJ → nome normalizado + município → fuzzy.**

## Justificativa

- CNPJ (Level 1) é o match mais confiável, mas nem toda fonte provê CNPJ
- Nome normalizado + IBGE (Level 2) cobre fontes sem CNPJ com alta confiança
- Fuzzy (Level 3) é fallback para casos com erros de digitação ou variações de nome
- Ordem importa: níveis mais confiáveis primeiro, fuzzy só como último recurso
- `rapidfuzz` é 10x mais rápido que `difflib` (fallback se não instalado)
- Threshold 0.85 balanceia recall vs precisão

## Consequências

- ✅ Cobertura de matching aumentou significativamente (CNPJ + nome + fuzzy)
- ✅ Cada match tem `match_method`, `match_score` e `match_confidence` para auditoria
- ✅ View `v_unmatched_bids` facilita debugging de unmatched
- ❌ Fuzzy matching pode gerar falsos positivos (mitigado por threshold alto + filtro IBGE)
- ❌ Performance O(N×M) no pior caso para fuzzy (mitigado por filtro de candidatos por IBGE)
