# Tasks — Módulo `intel`

> 🟢 CONFIRMADO — baseado em `intel_pipeline.py` e scripts relacionados

## Tarefas de Reimplementação

### T1: Orquestrador de Pipeline
- **Arquivo legado:** `scripts/intel_pipeline.py`
- **Confiança:** 🟢
- **Descrição:** Implementar `run_pipeline(cnpj, ufs, dias, top)` com 7 stages sequenciais via `subprocess.run()`. Timeout por stage. Capturar exit code. Pular stages com `--from-step`. Suporte a `--no-cache`.
- **Critério de pronto:** Pipeline executa 7 stages em sequência. Timeout respeitado. Resume de stage funcional.

### T2: Intel Collect (Stage 1)
- **Arquivo legado:** `scripts/intel_collect.py`
- **Confiança:** 🟢
- **Descrição:** Query DataLake por licitações do CNPJ nas UFs. Cruzar com PNCP API para editais recentes. Merge + dedup. Output JSON em `data/intel/`.
- **Critério de pronto:** Coleta funcional. Dedup correto. Output JSON válido.

### T3: Intel Enrich (Stage 2)
- **Arquivo legado:** `scripts/intel_enrich.py`
- **Confiança:** 🟢
- **Descrição:** Chamar BrasilAPI `/cnpj/v1/{cnpj}` para cada CNPJ único. Cache em `enriched_entities`. Complementar com IBGE API.
- **Critério de pronto:** CNPJs enriquecidos. Cache funcional. Dados normalizados.

### T4: LLM Gate (Stage 3)
- **Arquivo legado:** `scripts/intel_llm_gate.py`
- **Confiança:** 🟢
- **Descrição:** Construir prompt com objeto da licitação + CNAEs da empresa. Chamar OpenAI GPT-4.1-nano. Classificação binária SIM/NAO. Zero-noise: erro = REJECT. Timeout 10s.
- **Critério de pronto:** Classificação funcional. Zero-noise implementado. Timeout respeitado.

### T5: Intel Analyze (Stage 5)
- **Arquivo legado:** `scripts/intel_analyze.py`
- **Confiança:** 🟢
- **Descrição:** Analisar edital em 5 dimensões (HAB, FIN, GEO, PRAZO, COMP). Usar weight_profile do setor. Gerar score final e recomendação.
- **Critério de pronto:** 5 dimensões computadas. Scores normalizados 0-1. Recomendação gerada.

### T6: Intel Report (Stage 7)
- **Arquivo legado:** `scripts/intel_report.py`, `scripts/intel_excel.py`
- **Confiança:** 🟢
- **Descrição:** Gerar PDF (ReportLab) com capa, sumário, análise por edital, scores, recomendação. Gerar Excel (openpyxl) com 4 abas: resumo, editais, concorrentes, preços.
- **Critério de pronto:** PDF e Excel gerados. Dados corretos. Formatação profissional.
