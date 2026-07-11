# Intel Pipeline — Tasks

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

## Tarefas de Reimplementação

| # | Tarefa | Fonte | Critério de Pronto | Confiança |
|---|--------|-------|-------------------|-----------|
| T-I01 | Implementar pipeline orchestrator: CLI, 7 stages como subprocess, timeouts | `intel_pipeline.py:739-1184` | 7 stages executam sequencialmente com timeouts | 🟢 |
| T-I02 | Implementar 5 quality gates: cobertura, cadastral, ruído, conteúdo, recomendação | `intel_pipeline.py:200-700` | Gates com PASS/FAIL + auto-fix | 🟢 |
| T-I03 | Implementar coleta exaustiva PNCP: 12 sub-etapas, adaptive rate limiter | `intel-collect.py:1-3193` | Rate limiter: 150ms base, 2s max, growth/decay | 🟢 |
| T-I04 | Implementar CNAE keyword gate: densidade, bônus/penalidade, threshold 35% | `intel-collect.py:1186-1464` | Compatível se confidence ≥ 35% | 🟢 |
| T-I05 | Implementar LLM fallback: GPT-4.1-nano, max 5 tokens, SIM/NAO | `intel-collect.py:1465` | Classifica ambíguos (confidence < 40%) | 🟡 |
| T-I06 | Implementar semantic dedup: Jaccard token overlap + valor + órgão | `intel-collect.py:407-488` | Duplicatas removidas com 3 condições | 🟢 |
| T-I07 | Implementar competitive intel: HHI, concorrência, price benchmarks | `intel-collect.py:1685-2066` | HHI ≤2=BAIXA, ≤5=MEDIA, ≤10=ALTA | 🟢 |
| T-I08 | Implementar delta detection: NOVO/ATUALIZADO/VENCENDO/INALTERADO | `intel-collect.py:2673` | Compara com JSON anterior | 🟢 |
| T-I09 | Implementar enrichment empresa: SICAF(Playwright) + CEIS/CNEP/CEPIM/CEAF | `intel-enrich.py:195-250` | is_sanctioned flag, SICAF status | 🟢 |
| T-I10 | Implementar enrichment editais: OSRM, IBGE, custo, simulação, victory | `intel-enrich.py:252-400` | Só enriquece dentro de 10× capital | 🟢 |
| T-I11 | Implementar gate2 validator: 4 hard-incompatible patterns | `intel-validate.py:98-120` | software+construção → INCOMPATIVEL (e outros 3) | 🟢 |
| T-I12 | Implementar gate4 validator: forbidden words, enums, embedded "Nao consta" | `intel-validate.py:338-450` | 5 forbidden words detectadas | 🟢 |
| T-I13 | Implementar gate5 validator: 6 override rules, expired removal | `intel-validate.py:499-579` | EXPIRADO → NAO PARTICIPAR (e outros 5) | 🟢 |
| T-I14 | Implementar análise LLM: 21 campos, temperatura=0, JSON response | `intel-analyze.py:750-795` | 21 campos válidos por edital | 🟢 |
| T-I15 | Implementar bid score 7 dimensões: pesos e piecewise functions | `intel-analyze.py:279-378` | Score 0-1, threshold 0.45 | 🟢 |
| T-I16 | Implementar programmatic override: CNAE 0%, score < 0.20 → NAO PARTICIPAR | `intel-analyze.py:883-928` | Força sem gastar tokens LLM | 🟢 |
| T-I17 | Implementar adversarial review: modelo diferente do primário | `intel-analyze.py:945` | Cross-model audit | 🟡 |
| T-I18 | Implementar extração PDF: pymupdf4llm → PyMuPDF → OCR (pt-br) | `intel-extract-docs.py:117-185` | OCR trigger se avg_chars < 100/página | 🟢 |
| T-I19 | Implementar seleção top20: filtro 5-pass + opportunity score | `intel-extract-docs.py:636-683` | Top 20 ordenados por score | 🟢 |
| T-I20 | Implementar Excel generator: 4 sheets, 31 colunas, write-only | `intel-excel.py:1-1031` | 4 planilhas com design tokens Big Four | 🟢 |
| T-I21 | Implementar PDF generator: 9 seções, 17 ParagraphStyles | `intel-report.py:1-2178` | PDF A4 com INK#1B2A3D, ACCENT#8B7355 | 🟢 |

## Dependências

```
T-I03 (coleta) → T-I04..T-I08 (features coleta)
T-I03 → T-I09..T-I10 (enrichment)
T-I09..T-I10 → T-I11..T-I13 (validação)
T-I13 → T-I14..T-I17 (análise LLM)
T-I14 → T-I18..T-I19 (extração docs)
T-I19 → T-I20..T-I21 (relatórios)
T-I01..T-I02 (orchestrator) integra todos
```

## Estimativa

| Categoria | Tarefas | Esforço |
|-----------|---------|---------|
| Coleta | T-I03..T-I08 | 4-6 dias |
| Enriquecimento | T-I09..T-I10 | 2-3 dias |
| Validação | T-I11..T-I13 | 2-3 dias |
| Análise LLM | T-I14..T-I17 | 3-4 dias |
| Extração Docs | T-I18..T-I19 | 2-3 dias |
| Relatórios | T-I20..T-I21 | 3-4 dias |
| Orquestrador | T-I01..T-I02 | 2 dias |
| **Total** | 21 tarefas | **18-25 dias** |
