---
name: Story COVERAGE-1.1 Entity Matching Enhancement
description: 4-level cascade (CNPJ, nome, alias, fuzzy) com alias matching, adaptive threshold e baseline. monitor.py delegado para entity_matcher.py.
metadata:
  type: project
---

Story COVERAGE-1.1 implementada — entity matching enhancement.

**O que foi feito:**
- `scripts/crawl/monitor.py` atualizado para delegar `_match_entities_cascade()` a `scripts/matching/entity_matcher.match_entities_cascade()`
- `entity_matcher.py` (pre-existente) ja implementava: Level 2b alias matching, threshold fuzzy ajustavel por porte de municipio, log de abreviaturas nao reconhecidas
- `scripts/matching/measure_baseline.py` (criado) — script de baseline/revalidate/regression com `--before`, `--after`, `--regression` flags
- `tests/test_entity_matcher.py` corrigido para incluir key "alias" no retorno esperado (22/22 testes passando)
- `config/abbreviations.yaml` ja contem as 10 siglas SC listadas no AC2: PMF, FMS, FUS, CMDCA, FMAS, FME, IPUF, CASAN, CELESC, DEINFRA
- `config/municipio_population.yaml` (pre-existente) com populacao dos municipios SC para threshold ajustavel

**Por que:** Unificar toda a logica de entity matching em `entity_matcher.py` como fonte canonica, eliminando duplicacao com o codigo inline em `monitor.py`.

**Como aplicar:** Para medir baseline: `python scripts/matching/measure_baseline.py`. Para regression check: `python scripts/matching/measure_baseline.py --regression`.
