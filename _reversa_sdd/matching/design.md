# Matching — Design

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

## Arquitetura do Cascade

```python
match_entities_cascade(conn, source, entities) → dict[str, int]
# Retorna: {"cnpj": N, "name_normalized": N, "fuzzy": N, "unmatched": N, "total": N}
```

## Índices In-Memory

```python
cnpj_index: dict[str, dict]        # key = cnpj_8 (8 digitos)
name_exact_index: dict[str, dict]  # key = normalize_name(razao_social)
name_muni_index: dict[tuple[str,str], dict]  # key = (norm_name, codigo_ibge)
```

## Algoritmo de Matching

```
Para cada bid WHERE matched_entity_id IS NULL:
  1. CNPJ: limpa orgao_cnpj → busca 8-digit base → busca 14-digit prefix
     Match → method='cnpj', score=1.0, confidence='high'
  
  2. Nome: normalize_name(orgao_razao_social) → busca (name, ibge) no name_muni_index
     → fallback: busca name no name_exact_index
     Match → method='name_normalized', score=1.0, confidence='high'
  
  3. Fuzzy: filtra all_entities_norm por codigo_ibge (se disponível)
     → calcula fuzz_ratio(name, candidate) para todos
     → seleciona max(score) acima de ENTITY_MATCH_FUZZY_THRESHOLD (0.85)
     score ≥ 0.95 → method='fuzzy', confidence='high'
     score ≥ 0.85 → method='fuzzy', confidence='medium'
     score < 0.85 → method='unmatched', score=0.0

COMMIT único no final
```

## Name Normalizer

```python
normalize_name(name) → str:
  1. NFKD normalize (remove acentos)
  2. Uppercase
  3. Remove pontuação [^\w\s]
  4. Remove CNPJ numbers (8-14 dígitos)
  5. Collapse whitespace
  6. Expand 18 abbreviations (word-boundary regex, longest-first)
```

## Fuzzy Library Selection

```python
try:
    from rapidfuzz import fuzz as _rapidfuzz
    _fuzz_ratio = lambda a, b: _rapidfuzz.ratio(a, b) / 100.0
except ImportError:
    from difflib import SequenceMatcher
    _fuzz_ratio = lambda a, b: SequenceMatcher(None, a, b).ratio()
```

## Batch Processing

- Busca todos os bids unmatched para o source
- Constrói índices in-memory uma vez
- Itera sobre todos os bids, aplica cascade
- UPDATE individual por bid
- COMMIT único no final da transação
- Retorna estatísticas por método

## Confiança

🟢 CONFIRMADO — Algoritmo verificado em `entity_matcher.py:1-297`. Testes em `test_entity_matcher.py:1-402`.
