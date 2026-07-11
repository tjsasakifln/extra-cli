# Requirements — Módulo `lib`

> 🟢 CONFIRMADO — `name_normalizer.py`, `bid_simulator.py`, `victory_profile.py`, `cost_estimator.py`, `win_loss_tracker.py`

## Funcionais

| ID | Requisito | Fonte | Confiança |
|----|-----------|-------|-----------|
| FR-L1 | Normalizar nomes de entes públicos (7-step pipeline: NFKD → uppercase → remove pontuação → remove CNPJ → collapse → expand abreviações → remove irrelevantes) | `name_normalizer.py:100-152` | 🟢 |
| FR-L2 | Dicionário de 18 abreviações da administração pública BR (extensível via YAML) | `name_normalizer.py:29-49` | 🟢 |
| FR-L3 | Simular lance ótimo: maximizar P(vitória) × margem usando HHI e distribuição de descontos | `bid_simulator.py` | 🟢 |
| FR-L4 | 5 perfis de margem setorial: engenharia_obras, ti_software, consultoria, avaliacao, default | `bid_simulator.py:63-80` | 🟢 |
| FR-L5 | Construir perfil de vitória a partir de contratos ganhos (valor, modalidade, município, keywords, distância) | `victory_profile.py:build_victory_profile` | 🟢 |
| FR-L6 | Scoring de fit edital-empresa (0.0-1.0) baseado no perfil de vitória | `victory_profile.py:score_edital_fit` | 🟢 |
| FR-L7 | 5 faixas populacionais: micro (<5k), pequeno (5-20k), medio (20-100k), grande (100-500k), metropole (>500k) | `victory_profile.py:74-80` | 🟢 |
| FR-L8 | Estimativa de custos e tracking de win/loss | `cost_estimator.py`, `win_loss_tracker.py` | 🟢 |

## Não Funcionais

| ID | Requisito | Evidência | Confiança |
|----|-----------|-----------|-----------|
| NFR-L1 | Fallback difflib se rapidfuzz não instalado | `name_normalizer.py:218-221`, `requirements.txt:22` | 🟢 |
| NFR-L2 | Tipagem estática com `from __future__ import annotations` | Todos os arquivos | 🟢 |

## MoSCoW

- **Must:** FR-L1, FR-L3, FR-L5, FR-L6
- **Should:** FR-L2, FR-L4, FR-L7, FR-L8
