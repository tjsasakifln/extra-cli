---
name: story-COVERAGE-1.1-qa-gate
description: "FAIL (original) -> FAIL (RE-QA). Implementacao permanece em stash@{1} sem aplicacao ao working tree. 7 ACs FAIL, 22/22 testes pre-COVERAGE-1.1."
metadata:
  type: reference
---

# Story COVERAGE-1.1 QA Gate — FAIL (original) -> FAIL (RE-QA)

**Date:** 2026-07-11
**Story:** COVERAGE-1.1 (Entity Matching Enhancement)
**Epic:** EPIC-COVERAGE-100PCT
**Verdict:** FAIL (original) -> FAIL (RE-QA)

## QA Original (Primeira Tentativa)

5/8 ACs nao implementados no working tree (AC2, AC3, AC4, AC5, AC6). Implementacao existe em `stash@{1}` mas nunca foi aplicada. 3 testes falhando. Checkboxes [x] marcados sem implementacao.

## RE-QA (Segunda Tentativa) — 2026-07-11

**Veredito: FAIL** — Mesmo problema do QA anterior. Implementacao permanece em `stash@{1}`, nao no working tree.

### Re-Validation por AC

| AC | Status | Evidencia |
|----|--------|-----------|
| AC2 (Siglas SC) | FAIL | `abbreviations.yaml` tem 10 siglas inline (HEAD), mas ABBREVIATIONS dict Python nao inclui 8/10. `load_abbreviations_from_yaml()` nunca chamada na normalizacao. |
| AC3 (Level 2b Alias) | FAIL | `entity_matcher.py` (HEAD, commit e9729e1) tem 3 niveis, sem alias matching |
| AC4 (Threshold populacao) | FAIL | Sem `_load_population_map()` ou `_get_threshold_for_city()` no working tree |
| AC5 (Log abreviacoes) | FAIL | `name_normalizer.py` sem `find_unknown_abbreviations()` |
| AC6 (100 amostras) | FAIL | Nao implementado |
| AC7 (Ganho cobertura) | FAIL | Nao verificavel sem codigo |
| AC8 (Regressao zero) | FAIL | Nao verificavel sem codigo |
| Testes | 22/22 (codigo HEAD) | 8 falhas pre-existentes (ciga_ckan, selenium, transparencia) |
| Ruff | 3 erros | N806 + 2xF821 em name_normalizer.py (codigo morto) |

### Root Cause

O dev fez a implementacao completa em `stash@{1}` (abbreviations.yaml com secao `siglas:`, _expand_siglas() em name_normalizer.py, Level 2b + _load_population_data() + _generate_name_aliases() em entity_matcher.py) mas **nao aplicou ao working tree**. git diff HEAD mostra ZERO alteracoes nos arquivos afetados.

### Stash vs Working Tree

| Arquivo | Working Tree (HEAD) | Stash@{1} |
|---------|---------------------|-----------|
| `config/abbreviations.yaml` | 10 siglas inline | secao `siglas:` |
| `scripts/lib/name_normalizer.py` | `load_abbreviations_from_yaml()` | + `_expand_siglas()`, `_load_siglas()`, `find_unknown_abbreviations()` |
| `scripts/matching/entity_matcher.py` | 3 niveis, sem alias | + Level 2b, `_generate_name_aliases()`, `_load_population_data()` |
| `config/municipio_population.yaml` | Presente (102 entries) | Usado por _load_population_data() |

### Issues (RE-QA)

| ID | Severidade | Descricao |
|----|-----------|-----------|
| REQ-001 | high | AC2: 8/10 siglas nao no ABBREVIATIONS dict; load_abbreviations_from_yaml() nunca chamada |
| REQ-002 | high | AC3: Level 2b alias matching NAO no working tree |
| REQ-003 | high | AC4: Threshold fuzzy por populacao NAO implementado |
| REQ-004 | high | AC5: find_unknown_abbreviations() NAO implementado |
| REQ-005 | high | AC6-AC8: Nao implementados/verificaveis |
| MNT-001 | medium | load_abbreviations_from_yaml() definida mas nunca chamada (codigo orfao) |
| MNT-002 | low | Ruff: 3 erros em name_normalizer.py (N806, F821 x2) |
| PROC-001 | high | Checkboxes [x] sem implementacao — mesma violacao do QA anterior |

### Acao Necessaria

1. Aplicar `stash@{1}` ao working tree
2. Corrigir `name_normalizer.py`: codigo morto apos `return` em find_unknown_abbreviations()
3. Re-rodar: `python3 -m pytest tests/test_entity_matcher.py -v && ruff check scripts/`
4. Submeter para RE-QA
