---
name: entity-name-matching-cascade
description: "Entity matching usa 3-level cascade (CNPJ > nome+municipio > fuzzy) em _match_entities_cascade() no monitor.py"
metadata:
  type: project
---

Entity matching no pipeline de crawl usa 3-level cascade implementado em `_match_entities_cascade()` em `scripts/crawl/monitor.py`:

- **Level 1 (CNPJ)**: Match exato por 8-digit CNPJ base. Confidence: high.
- **Level 2 (name+municipio)**: Nome normalizado + constraint codigo_ibge. Confidence: high.
- **Level 3 (fuzzy)**: fuzzy matching com threshold configuravel (ENTITY_MATCH_FUZZY_THRESHOLD, default 0.85). Usa rapidfuzz se disponivel, fallback difflib. Confidence: high/medium/low.

**Why:** Nomes inconsistentes nas fontes (acentos, abreviacoes) e entes homonimos em municipios diferentes exigiam estrategia em cascata com constraint geografica.

**How to apply:** Para estender matching, modificar `_match_entities_cascade()` em monitor.py. Normalizacao de nomes vive em `scripts/lib/name_normalizer.py` com dicionario de abreviacoes em `config/abbreviations.yaml`. Migracoes 010 e 011 adicionam colunas de logging (match_method, match_score, match_confidence) e view v_unmatched_bids.
