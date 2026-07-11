# Matching — Tasks

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

| # | Tarefa | Fonte | Critério de Pronto | Confiança |
|---|--------|-------|-------------------|-----------|
| T-M01 | Implementar normalize_name(): NFKD + uppercase + strip + 18 abbreviations | `name_normalizer.py:1-188` | Nomes normalizados deterministicamente | 🟢 |
| T-M02 | Construir índices in-memory: cnpj_index, name_exact_index, name_muni_index | `entity_matcher.py:45-80` | O(1) lookup nos níveis 1-2 | 🟢 |
| T-M03 | Implementar cascade nível 1: CNPJ exact match (8-digit base → 14 prefix) | `entity_matcher.py:match_entity()` | match_method='cnpj', score=1.0 | 🟢 |
| T-M04 | Implementar cascade nível 2: nome normalizado + constraint IBGE | `entity_matcher.py:match_entities_cascade()` | match_method='name_normalized', score=1.0 | 🟢 |
| T-M05 | Implementar cascade nível 3: fuzzy rapidfuzz/difflib com threshold 0.85 | `entity_matcher.py:fuzzy section` | ≥0.95=high, ≥0.85=medium, <0.85=unmatched | 🟢 |
| T-M06 | Implementar batch processing: transaction única, UPDATE por bid | `entity_matcher.py:batch loop` | COMMIT único, stats por método | 🟢 |
| T-M07 | Integrar com orchestrator.py: chamada pós-upsert | `orchestrator.py:crawl_source()` | matched_entity_id preenchido | 🟢 |
| T-M08 | Escrever testes unitários: 3 níveis de match + unmatched | `test_entity_matcher.py:1-402` | Cobertura dos 4 cenários | 🟢 |

**Estimativa:** 3-5 dias (8 tarefas)
