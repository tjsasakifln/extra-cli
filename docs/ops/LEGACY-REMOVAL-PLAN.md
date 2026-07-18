# Plano de remoção de código legado (DoD §27)

**Status:** active  
**Owner:** delivery + architect  
**Updated:** 2026-07-18  
**Story:** ROI-cand-dyn-slice-e845e4e64aba

## Princípio

Código legado permanece **apenas** enquanto tiver consumidor ou fallback documentado.  
Cada item abaixo tem: path, motivo de legado, substituto, critério de remoção, risco.

| ID | Path / símbolo | Motivo | Substituto | Critério de remoção | Risco |
|----|----------------|--------|------------|---------------------|-------|
| L1 | `scripts/crawl/orchestrator.py` | Deprecado (DeprecationWarning nos testes) | `scripts/crawl/monitor.py` | Zero imports externos + testes sem orchestrator | Médio |
| L2 | CLI hyphen scripts em `scripts/*-*.py` | Naming legado (CLI top-level) | módulos snake_case sob `scripts/` packages | Wrapper thin → módulo novo; sem callers diretos | Baixo |
| L3 | `dom_sc` crawler autenticado | Preferir CIGA público | `ciga_ckan` | Coverage/ops usa só ciga_ckan; dom_sc `gap_fill` | Médio |
| L4 | Selenium crawlers | Método de crawl, não fonte | adapters ADR-021 / HTTP | Sem jobs timers em selenium | Alto (fragilidade) |
| L5 | `LEGACY_ALIAS_*` em coverage_contract | Aliases de métricas renomeadas | `METRIC_DEFINITIONS` canônico | Aliases só em leitura histórica; zero writers | Baixo |
| L6 | `sys.path` inserts disallowed (gate) | Bootstrap ad-hoc | package install / `_PROJECT_ROOT` | n_disallowed → 0 no gate | Médio |

## Processo

1. Não apagar sem story AIOX.  
2. Marcar `deprecated` + warning por ≥1 ciclo.  
3. Remover testes que só exercitam o legado.  
4. Atualizar `docs/DEVELOPMENT.md` e registry se a fonte/path sumir.

## Evidência

- Gate: `python3 -m scripts.ops.code_hygiene_gate --json`  
- Registry roles: `python3 -m scripts.crawl.registry --export --json`
