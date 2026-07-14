---
name: transparencia-specs-deepened
description: 3 spec files do modulo transparencia reescritos com conteudo profundo (16 RFs, design completo, 14 tasks)
metadata:
  type: reference
---

# Transparencia Specs Deepened

Em 2026-07-13, os 3 specs do modulo transparencia foram reescritos com profundidade:

## requirements.md (421 linhas)
- 15 RFs (vs 2 anteriores) + 6 RNs
- Gherkin scenarios para cada RF
- ADR-011 como base arquitetural
- Documentacao de 10 plataformas de portal (9 padroes + fallback proprio)
- 3 estrategias do template generico (keyword scoring, div, any-table)
- 14 keywords de licitacao para scoring

## design.md (429 linhas)
- Diagrama arquitetural em ASCII
- Pipeline detect -> match -> configure -> crawl
- Cada template documentado com estrategia de parsing, seletores, ordem de fallback
- Schema do config YAML completo
- Fluxo de dados detalhado (monitor -> crawler -> templates -> transform -> pncp)
- 11 riscos com mitigacoes
- 8 configuracoes por env var documentadas

## tasks.md (313 linhas)
- 14 tasks (vs 5 anteriores) com estimativas e dependencias
- Roadmap curto/medio/longo prazo (51h total)
- Temas pendentes: Google fallback, CAPTCHA, upsert PNCP
- Identificados 216 municipios restantes sem mapeamento (73%)

Referencias: `_reversa_sdd/transparencia/`
