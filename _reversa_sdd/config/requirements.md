# Config — Requirements

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1

Configuração centralizada: settings via env vars, 13 setores B2G com keywords context-gated, abbreviations, transparencia CSS selectors, logging JSON estruturado.

## Requisitos Funcionais

| ID | Descrição | Prioridade | Fonte |
|----|----------|-----------|-------|
| RF-CF01 | Settings centralizado via env vars: DB, APIs, ingestion, coverage, alerts | Must | `settings.py:1-159` |
| RF-CF02 | 13 setores B2G: CNAEs, keywords, heurísticas, exclusion rules, thresholds | Must | `sectors_config.yaml:1-2116` |
| RF-CF03 | Keywords context-gated: trigger requer co-occurrence signals | Must | `sectors_data.yaml:1-6338` |
| RF-CF04 | 4 hard-incompatible patterns CNAE+regex | Must | `intel-validate.py:98-120` |
| RF-CF05 | Abbreviations: 18 siglas administração pública, YAML extensível | Should | `abbreviations.yaml:1-23` |
| RF-CF06 | Transparencia CSS selectors: 4 templates configuráveis | Should | `transparencia_config.yaml:1-61` |
| RF-CF07 | Logging JSON: correlation_id contextvar, rotação 10MB×5 | Must | `logging_config.py:1-199` |

🟢 CONFIRMADO — 7/7 arquivos de config lidos.
