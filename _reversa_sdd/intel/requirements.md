# Requirements — Módulo `intel`

> 🟢 CONFIRMADO — extraído de `intel_pipeline.py`, `intel_collect.py`, `intel_llm_gate.py`, `intel_analyze.py`, `intel_report.py`, `intel_excel.py`

## Funcionais (FR)

| ID | Requisito | Fonte | Confiança |
|----|-----------|-------|-----------|
| FR-I1 | Pipeline 7 stages: collect → enrich → llm_gate → extract_docs → analyze → validate → report | `intel_pipeline.py:8-11` | 🟢 |
| FR-I2 | 5 quality gates entre stages com vereditos PASS/FAIL/WARN | `intel_pipeline.py` | 🟢 |
| FR-I3 | GATE 1 (Cobertura): >= 80% das entidades no raio devem ter licitações | `intel_pipeline.py` | 🟡 |
| FR-I4 | GATE 2 (Cadastral): CNPJ válido, CNAEs compatíveis com setor da empresa | `intel_pipeline.py` | 🟡 |
| FR-I5 | GATE 3 (Ruído): Classificação LLM — edital é relevante para o setor? (SIM/NAO) | `intel_llm_gate.py` | 🟢 |
| FR-I6 | GATE 4 (Conteúdo): Editais contêm keywords de engenharia | `intel_pipeline.py` | 🟡 |
| FR-I7 | GATE 5 (Recomendação): Score ponderado (HAB+FIN+GEO+PRAZO+COMP) >= threshold | `intel_analyze.py` | 🟢 |
| FR-I8 | Classificação setorial em 2 camadas: heurísticas (YAML) → LLM fallback | `intel_llm_gate.py`, `sectors_config.yaml` | 🟢 |
| FR-I9 | Zero-noise: erro na API OpenAI = REJECT | `intel_llm_gate.py` | 🟢 |
| FR-I10 | 5 dimensões de scoring com pesos configuráveis por setor | `sectors_config.yaml` | 🟢 |
| FR-I11 | Output: PDF (ReportLab) + Excel (openpyxl) estilizado | `intel_report.py`, `intel_excel.py` | 🟢 |
| FR-I12 | Suporte a --from-step N para retomar pipeline de stage específico | `intel_pipeline.py:17` | 🟢 |
| FR-I13 | Suporte a --no-cache para forçar re-coleta | `intel_pipeline.py:18` | 🟢 |

## Não Funcionais (NFR)

| ID | Requisito | Evidência | Confiança |
|----|-----------|-----------|-----------|
| NFR-I1 | Timeout coleta: 600s, enriquecimento: 300s, LLM gate: 120s, extração: 600s | `intel_pipeline.py:57-62` | 🟢 |
| NFR-I2 | LLM: GPT-4.1-nano, timeout 10s, fallback = REJECT | `config/settings.py:44-45`, `sectors_config.yaml:2101-2103` | 🟢 |
| NFR-I3 | Max 5 chamadas concorrentes à OpenAI | `config/settings.py:46` | 🟢 |

## Critérios de Aceitação

**AC-I1: Pipeline executa até o fim**
- Dado um CNPJ válido e UFs
- Quando executo `intel_pipeline.py --cnpj <CNPJ> --ufs SC`
- Então os 7 stages são executados em sequência e PDF + Excel são gerados em `output/`

**AC-I2: Gate bloqueia edital irrelevante**
- Dado que um edital é classificado como NAO pelo LLM
- Quando o GATE 3 é executado
- Então o edital é rejeitado e não avança para stages seguintes

**AC-I3: Resume de stage específico**
- Dado que o pipeline foi interrompido no stage 4
- Quando executo `--from-step 5`
- Então stages 1-4 são pulados e pipeline retoma do stage 5

## MoSCoW

| Prioridade | Requisitos |
|-----------|-----------|
| **Must** | FR-I1, FR-I2, FR-I5, FR-I7, FR-I8, FR-I11 |
| **Should** | FR-I3, FR-I4, FR-I6, FR-I9, FR-I10, FR-I12 |
| **Could** | FR-I13 |
