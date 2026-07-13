---
epic: EPIC-MASTER-B2G-READINESS
story_id: FIX-UNIVERSE
title: "Definicao canonica unica do universo de entes"
status: ready
priority: P0
effort: M
agent: @dev
depends_on: []
---

# Story FIX-UNIVERSE: Definicao Canonica Unica do Universo de Entes

## Problem Statement

A auditoria Fase 0 (2026-07-12) identificou **6 valores diferentes de denominador** de universo sendo usados em modulos distintos: **1.093, 1.448, 1.481, 1.697, 2.085, 1.000**. Nenhum modulo compartilha a mesma definicao. Isto viola a Regra Nao-Negociavel #1 — "Definicao canonica unica do universo".

**Consequencias:**

- Manifestos contradizem uns aos outros (ex: opportunity-coverage-manifest.json usa 1.448, coverage_manifest.json usa 1.093)
- Cobertura reportada varia de 39.4% a 265.95% dependendo de qual modulo consulta
- Impossivel ter um unico numero de verdade para o business
- CNPJ8 nao normalizado consistentemente: `manifest.py` usa `orgao_cnpj` bruto, `target_universe.py` usa `LEFT(orgao_cnpj, 8)`
- Decisoes de negocio baseadas em numeros incorretos

**Root cause:** Cada modulo define seu proprio universo hardcoded ou com query propria sem compartilhamento. Nao existe um modulo central de definicao do universo.

## Acceptance Criteria

- [ ] **AC1: Modulo `scripts/lib/universe.py` criado** — Contem constante `CANONICAL_UNIVERSE = 1093` e funcao `get_canonical_universe()` que executa `SELECT COUNT(*) FROM sc_public_entities WHERE raio_200km = TRUE`
- [ ] **AC2: CNPJ8 normalizado** — Funcao `normalize_cnpj8(cnpj: str) -> str` implementada no mesmo modulo: `"".join(c for c in cnpj if c.isdigit())[:8]`. Utilizada em todos os joins de CNPJ entre entidades e fontes.
- [ ] **AC3: Todos os modulos existentes importam do `universe.py`** — `manifest.py`, `consulting_readiness.py`, `coverage_truth.py`, `monitor.py`, `datalake_helper.py`, `contract_intel`, `target_universe.py` passam a usar `CANONICAL_UNIVERSE` e/ou `get_canonical_universe()` em vez de definicoes proprias
- [ ] **AC4: Valores hardcoded removidos** — Nenhum modulo contem constante numerica de universo diferente de 1.093. Todo valor hardcoded 1.448, 1.481, 1.697, 2.085, 1.000 e substituido por referencia ao modulo central.
- [ ] **AC5: Testes de validacao** — `pytest tests/test_universe.py -v` inclui: `0 <= numerator <= denominator` para qualquer par numerador/denominador, percentual de cobertura sempre entre 0 e 100, sem valores negativos em nenhuma metrica, mesma contagem de entes em todos os modulos que reportam universo
- [ ] **AC6: Documentos atualizados** — PRD (`docs/prd/`), epic master (`EPIC-MASTER-B2G-READINESS.md`), READMEs, e qualquer documento que mencione denominador de universo passam a usar 1.093 como valor canonico
- [ ] **AC7: Ruff check** — `ruff check scripts/lib/universe.py` retorna 0 erros
- [ ] **AC8: Mypy** — `mypy scripts/lib/universe.py` retorna 0 erros

## Technical Design

### Arquivos a criar

- `scripts/lib/__init__.py` — Pacote lib (se nao existir)
- `scripts/lib/universe.py` — Modulo central de definicao do universo

### Arquivos a modificar

- `scripts/manifest.py` — Substituir definicao propria de universo por import de `scripts.lib.universe`
- `scripts/coverage_truth/consulting_readiness.py` — Idem
- `scripts/coverage_truth/coverage_truth.py` — Idem
- `scripts/crawl/monitor.py` — Idem (se aplicavel)
- `scripts/local_datalake.py` — Idem (se aplicavel)
- `scripts/opportunity_intel/manifest.py` — Idem
- `scripts/contract_intel/` — Idem
- `scripts/target_universe.py` — Idem
- `docs/stories/epics/EPIC-MASTER-B2G-READINESS.md` — Atualizar tabela de universo
- `docs/prd/` — Atualizar documentos relevantes

### Modulo `scripts/lib/universe.py`

```python
"""
Modulo central de definicao do universo canonico de entes.
TODOS os modulos devem importar daqui — nunca definir universo propriamente.
"""

CANONICAL_UNIVERSE = 1093  # Entes dentro do raio 200km de Florianopolis


def get_canonical_universe() -> int:
    """
    Retorna a contagem canonica de entes no banco.
    Equivale a: SELECT COUNT(*) FROM sc_public_entities WHERE raio_200km = TRUE
    """
    ...


def normalize_cnpj8(cnpj: str) -> str:
    """
    Normaliza CNPJ para 8 digitos (CNPJ raiz).
    Remove todos os caracteres nao-numericos e trunca para 8 digitos.
    
    >>> normalize_cnpj8("12.345.678/0001-90")
    '12345678'
    >>> normalize_cnpj8("123456")
    '123456'
    """
    return "".join(c for c in cnpj if c.isdigit())[:8]
```

### Testes

Arquivo: `tests/test_universe.py`

| Teste | Descricao |
|-------|-----------|
| `test_canonical_constant_matches_db` | `get_canonical_universe()` retorna mesma contagem que `SELECT COUNT(*) WHERE raio_200km = TRUE` |
| `test_coverage_percent_range` | Qualquer cobertura calculada esta entre 0.0 e 100.0 |
| `test_numerator_not_exceed_denominator` | Numerador nunca excede denominador |
| `test_no_negative_metrics` | Nenhuma metrica de cobertura e negativa |
| `test_consistent_count_across_modules` | Todos os modulos que importam universo reportam a mesma contagem |
| `test_normalize_cnpj8_clean` | CNPJ formatado → 8 digitos limpos |
| `test_normalize_cnpj8_already_clean` | CNPJ ja limpo → mantem |
| `test_normalize_cnpj8_short` | CNPJ com menos de 8 digitos → mantem como esta |
| `test_normalize_cnpj8_empty` | String vazia → string vazia |

## File List

- **CREATE** `scripts/lib/__init__.py`
- **CREATE** `scripts/lib/universe.py`
- **CREATE** `tests/test_universe.py`
- **MODIFY** `scripts/manifest.py`
- **MODIFY** `scripts/coverage_truth/consulting_readiness.py`
- **MODIFY** `scripts/coverage_truth/coverage_truth.py`
- **MODIFY** `scripts/crawl/monitor.py`
- **MODIFY** `scripts/local_datalake.py`
- **MODIFY** `scripts/opportunity_intel/manifest.py`
- **MODIFY** `scripts/contract_intel/*.py`
- **MODIFY** `scripts/target_universe.py`
- **MODIFY** `docs/stories/epics/EPIC-MASTER-B2G-READINESS.md`

## Dependencies

- Nenhuma — esta story e prerequisito para FIX-MANIFEST e FIX-FRESHNESS
- Deve ser implementada antes de qualquer story que corrija metricas de cobertura

## Security Considerations

- Sem autenticacao ou dados sensiveis — apenas acesso ao banco de dados local
- `get_canonical_universe()` usa conexao com PostgreSQL local (pool existente)

## Tests

- `tests/test_universe.py` conforme tabela acima (AC5)
- `ruff check scripts/lib/universe.py` — 0 erros
- `mypy scripts/lib/universe.py` — 0 erros
- Validacao manual: executar `get_canonical_universe()` e comparar com `SELECT COUNT(*) WHERE raio_200km = TRUE`

## Definition of Done

- [ ] Codigo implementado (AC1-AC4)
- [ ] ruff check passa em scripts/lib/ e scripts modificados
- [ ] mypy passa (scoped) em scripts/lib/universe.py
- [ ] Testes unitarios passam (`pytest tests/test_universe.py -v`)
- [ ] Testes de integracao passam (consulta real ao banco)
- [ ] Documentos atualizados com valor canonico 1.093 (AC6)
- [ ] QA gate PASS
