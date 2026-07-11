# Design — Módulo `intel`

> 🟢 CONFIRMADO — extraído de `intel_pipeline.py`, `sectors_config.yaml`

## Arquitetura de Pipeline

```
intel_pipeline.py (orquestrador, 7 stages via subprocess.run)
  │
  ├── Stage 1: intel_collect.py → DataLake + PNCP API
  │   └── Busca licitações ativas para CNPJ nas UFs, dedup
  │
  ├── [GATE 1: Cobertura] >= 80% entidades?
  │
  ├── Stage 2: intel_enrich.py → BrasilAPI + IBGE
  │   └── Enriquece CNPJ com razão social, CNAEs, município
  │
  ├── [GATE 2: Cadastral] CNPJ válido? CNAEs compatíveis?
  │
  ├── Stage 3: intel_llm_gate.py → OpenAI GPT-4.1-nano
  │   └── Classificação binária (SIM/NAO) + zero-noise (REJECT on fail)
  │
  ├── [GATE 3: Ruído] Edital relevante?
  │
  ├── Stage 4: intel_extract_docs.py → PNCP Files API
  │   └── Download de editais (PDF/HTML), extração de keywords
  │
  ├── [GATE 4: Conteúdo] Contém keywords engenharia?
  │
  ├── Stage 5: intel_analyze.py → OpenAI GPT-4.1-nano
  │   └── Análise 5 dimensões: HAB, FIN, GEO, PRAZO, COMP
  │
  ├── Stage 6: intel_validate.py
  │   └── Cross-check scores, valida integridade
  │
  ├── [GATE 5: Recomendação] Score >= threshold?
  │
  └── Stage 7: intel_report.py + intel_excel.py
      └── PDF (ReportLab) + Excel (openpyxl)
```

## Sistema de Scoring (5 Dimensões)

Cada edital recebe score de 0.0 a 1.0 em:

| Dimensão | Peso (engenharia) | O que avalia |
|----------|-------------------|--------------|
| **HAB** (habilitação) | 0.25 | Capital mínimo, atestados técnicos, certidões fiscais |
| **FIN** (financeiro) | 0.30 | Valor do edital vs capital social, margem esperada |
| **GEO** (geográfico) | 0.25 | Distância da obra, raio de atuação, logística |
| **PRAZO** (timeline) | 0.15 | Tempo até abertura, compatibilidade com cronograma |
| **COMP** (competitivo) | 0.05 | Nº esperado de concorrentes (HHI), win rate do setor |

Score final = Σ(dimensão × peso). Threshold: >= 0.55 (cnae_gate_threshold).

## Classificação Setorial

```
1. Heurísticas (Camada 1) — sectors_config.yaml
   ├── strong_compat patterns → MATCH direto (confidence alta)
   ├── strong_incompat patterns → REJECT direto
   ├── weak_compat patterns → BAIXA confiança → aciona Camada 2
   └── cross_sector_exclusions → REJECT

2. LLM Fallback (Camada 2) — acionado se confiança < cnae_gate_threshold
   └── OpenAI GPT-4.1-nano com prompt: "SIM" ou "NAO"
```

## Decisões de Design

| Decisão | Escolha | Razão |
|---------|---------|-------|
| Orquestração | `subprocess.run()` por stage | Isolamento de falhas, timeout por stage, independência |
| LLM | GPT-4.1-nano (mais barato) | Custo ~$0.0001/edital, qualidade suficiente para classificação binária |
| Zero-noise | REJECT on API error | Falso positivo é pior que falso negativo |
| Fallback | Heurísticas YAML → LLM | 80%+ resolvido por regras, LLM só em casos ambíguos |
