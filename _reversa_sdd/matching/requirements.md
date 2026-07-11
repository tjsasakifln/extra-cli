# Matching — Entity Matching

> Gerado pelo Writer em 2026-07-11T22:30:00Z
> doc_level: completo
> Base: commit e9729e1

## Visão Geral

Módulo independente de entity matching que vincula licitações (`pncp_raw_bids`) a entes públicos catarinenses (`sc_public_entities`) usando cascade de 3 níveis com fallback fuzzy.

## Responsabilidades

- Matching exato por CNPJ (8 dígitos base → 14 prefixo)
- Matching por nome normalizado + constraint de município
- Matching fuzzy com rapidfuzz (threshold 0.85)
- Batch processing em transação única
- Tracking de match_method, match_score e match_confidence

## Regras de Negócio

- R8: Cascade 3 níveis — CNPJ exato (score=1.0) → nome+município (score=1.0) → fuzzy (score≥0.85) 🟢
- R13: Schema unificado — todos os bids sem match são processados em batch 🟢

## Requisitos Funcionais

| ID | Requisito | Prioridade | Critério de Aceite |
|----|-----------|-----------|-------------------|
| RF-M01 | Match exato por CNPJ de 8 dígitos (base) | Must | cnpj_index encontra entidade com mesmo cnpj_8 |
| RF-M02 | Match por nome normalizado + constraint IBGE | Must | name_muni_index encontra tupla (nome, ibge) |
| RF-M03 | Fallback fuzzy com rapidfuzz (threshold 0.85) | Should | Score ≥ 0.95 → high, ≥ 0.85 → medium |
| RF-M04 | Processar todos os bids unmatched em batch | Must | Uma transação, commit único no final |
| RF-M05 | Atualizar matched_entity_id + metadados de match | Must | Campos match_method, match_score, match_confidence |
| RF-M06 | Bids sem match ficam com match_method='unmatched' | Must | score=0.0, matched_entity_id=NULL |

## Requisitos Não Funcionais

| Tipo | Requisito | Evidência | Confiança |
|------|----------|----------|-----------|
| Performance | Índices in-memory para O(1) lookup nos níveis 1-2 | `entity_matcher.py:45-80` | 🟢 |
| Disponibilidade | Fallback difflib se rapidfuzz não disponível | `entity_matcher.py:try/except ImportError` | 🟢 |

## Critérios de Aceitação

```gherkin
Cenário: Match exato por CNPJ
Dado que um bid tem orgao_cnpj = "12345678000199"
E sc_public_entities tem entidade com cnpj_8 = "12345678"
Quando match_entities_cascade é executado
Então matched_entity_id = entity.id
E match_method = 'cnpj'
E match_score = 1.0

Cenário: Match fuzzy com threshold configurável
Dado que ENTITY_MATCH_FUZZY_THRESHOLD = 0.85
E um bid tem orgao_razao_social = "PREFEITURA MUNICIPAL DE JOINVILLE"
E sc_public_entities tem "MUNICIPIO DE JOINVILLE" (normalizado)
Quando fuzzy matching é executado
Então fuzz_ratio ≥ 0.85 → match_method = 'fuzzy'
E fuzz_ratio < 0.85 → match_method = 'unmatched'
```
