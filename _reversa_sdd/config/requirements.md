# Requirements — Módulo `config`

> 🟢 CONFIRMADO — `config/settings.py`, `sectors_config.yaml`, `abbreviations.yaml`, `transparencia_config.yaml`

## Funcionais

| ID | Requisito | Fonte | Confiança |
|----|-----------|-------|-----------|
| FR-CF1 | Configuração centralizada via env vars com defaults (12-factor) | `settings.py` | 🟢 |
| FR-CF2 | 13 setores configurados com CNAEs, heurísticas, perfis de peso, habilitações, timeline rules | `sectors_config.yaml` | 🟢 |
| FR-CF3 | Classificação setorial: strong_compat, strong_incompat, weak_compat, cross_sector_exclusions | `sectors_config.yaml` | 🟢 |
| FR-CF4 | Dicionário de abreviações PT-BR extensível via YAML | `abbreviations.yaml` | 🟢 |
| FR-CF5 | Config de portais de transparência (Betha, Ipam, E-gov) template-driven | `transparencia_config.yaml` | 🟢 |
| FR-CF6 | Fallback LLM configurável: modelo, timeout, threshold, on_failure | `sectors_config.yaml:2097-2115` | 🟢 |

## MoSCoW

- **Must:** FR-CF1, FR-CF2
- **Should:** FR-CF3, FR-CF4, FR-CF5, FR-CF6
