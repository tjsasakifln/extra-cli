# Intel Pipeline — Design (v1.5)

> Gerado pelo Writer em 2026-07-11T22:30:00Z | **Corrigido:** 2026-07-11 (snake_case canônico)
> doc_level: completo

## ⚠️ Nomenclatura: snake_case = canônico v1.5

Scripts intel em DUAS convenções. `intel_pipeline.py` referencia snake_case: `intel_collect.py`, `intel_enrich.py`, etc. Kebab-case é legado.

## Arquitetura Real do Pipeline

```
main() → [S1] intel_collect.py → [G1 inline] → [S2] intel_enrich.py → [G2 inline]
→ [S3] intel_llm_gate.py → [G3 inline] → [S4] intel_extract_docs.py → [G4 inline]
→ [S5] intel-analyze.py --prepare (manual, kebab!) → [S6] intel_excel.py → [G5 inline] → [S7] intel_report.py
```

Gates G1-G5 são funções inline em `intel_pipeline.py`. `intel_validate.py` é validador standalone (não parte do pipeline).

## Estágios (snake_case, v1.5)

### S1: intel_collect.py (138KB, 3420 linhas)
- **v1.5:** `_RATE_LIMIT_MAX_S=30.0` (was 2.0s), 429-specific backoff, chunked mode, per-combo 429 counters, sector-filtered benchmark, TCU_INDISPONIVEL
- 12 sub-etapas, AdaptiveRateLimiter, CNAE gate (threshold 35%), semantic dedup, HHI

### S2: intel_enrich.py
- SICAF, sanctions, OSRM, IBGE, cost estimation, bid simulation, victory profile

### S3: intel_llm_gate.py (13KB) — **não descoberto pelo Scout original**
- `_load_sectors_yaml()`, `_build_pos_kw_from_sectors()`
- Reclassifica ambíguos via GPT-4.1-nano

### S4: intel_extract_docs.py
- PDF cascade, ZIP/RAR, XLSX. Seleção top20 5-pass.

### S5: intel-analyze.py (kebab — inconsistência na linha 801)
- 3 modos, bid score 7D, 21 campos, adversarial review

### S6: intel_excel.py — 4 sheets, 31 colunas

### S7: intel_report.py — 9 seções, Big Four

## Quality Gates (inline em intel_pipeline.py)

| Gate | Função | Linhas | Lógica |
|------|--------|--------|--------|
| G1: Cobertura | `gate1_cobertura()` | 215-284 | API status, total > 0, UF coverage |
| G2: Cadastral | `gate2_cadastral()` | 286-360 | Sanctions, SICAF, enrichment ≥ 50% |
| G3: Ruído | `gate3_ruido()` | 362-444 | Compat ratio 5-80%, zero needs_llm_review |
| G4: Conteúdo | `gate4_conteudo()` | 446-550 | Doc coverage ≥ 50%, watermark, dedup |
| G5: Recomendação | `gate5_recomendacao()` | 549-720 | Remove NAO PARTICIPAR, 10× capacity |

**Timeout v1.5:** `TIMEOUT_COLLECT = 1800` (30 min, was 600s)

## Scripts Snake-Only (não analisados em profundidade)

| Script | Tamanho | Função |
|--------|---------|--------|
| `intel_llm_gate.py` | 13KB | S3: LLM reclassification |
| `intel_sector_loader.py` | 19KB | 20+ funções de config setorial |

🟡 INFERIDO — Pipeline verificado em `intel_pipeline.py` (49KB). Scripts snake_case analisados parcialmente.
🔴 LACUNA — `intel_llm_gate.py` e `intel_sector_loader.py` sem análise profunda.
