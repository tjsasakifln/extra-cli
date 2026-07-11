# Lib — Shared Utilities

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1

## Visão Geral

11 módulos de utilidades compartilhadas usados pelos pipelines de crawl e intel: normalização de nomes, simulação financeira de licitações, estimativa de custos, victory profile, extração de documentos, tracking de win/loss e validação CLI.

## Módulos

| Módulo | Linhas | Função principal |
|--------|--------|-----------------|
| `name_normalizer.py` | 188 | `normalize_name(name)→str`: NFKD + 18 abbreviations |
| `bid_simulator.py` | 345 | `simulate_bid(edital, intel, benchmark, cnae)→BidSimulation` |
| `cost_estimator.py` | 290 | `estimate_proposal_cost(dist, dur, capital, eletronico)→dict` |
| `victory_profile.py` | 373 | `build_victory_profile(contracts, capital, ufs)→VictoryProfile` |
| `win_loss_tracker.py` | 145 | `record_outcome(cnpj, edital_id, outcome)→dict` |
| `doc_templates.py` | 405 | `extract_structured(text, doc_type)→StructuredExtraction` |
| `constants.py` | 24 | VALID_UFS, VALID_MODELS, MAX_DIAS=365 |
| `intel_logging.py` | 36 | `setup_intel_logging(script_name, level)→Logger` |
| `cli_validation.py` | 186 | 8 validators (CNPJ, UF, dias, model, etc) |
| `retry.py` | 82 | `retry_on_failure` decorator com exponential backoff |

## Requisitos Funcionais Chave

| ID | Requisito | Módulo | Prioridade |
|----|-----------|--------|-----------|
| RF-L01 | Normalizar nomes: NFKD→upper→strip→18 abbreviations | name_normalizer | Must |
| RF-L02 | Simular lance ótimo: median+0.3σ, P(vitória) via logistic CDF^(N-1) | bid_simulator | Must |
| RF-L03 | Estimar custo proposta: paramétrico por distância, capital/interior, eletrônico/presencial | cost_estimator | Must |
| RF-L04 | Construir victory profile: 5 dimensões (valor 30%, keyword 25%, modalidade 15%, geo 15%, pop 15%) | victory_profile | Should |
| RF-L05 | Extrair campos de documentos: regex patterns com confidence decay (-0.15/pattern) | doc_templates | Should |
| RF-L06 | Rastrear win/loss para calibrar modelos: JSON local | win_loss_tracker | Could |
| RF-L07 | Validar inputs CLI com exit code 1 em falha | cli_validation | Must |
| RF-L08 | Retry com exponential backoff configurável | retry | Must |

## Requisitos Não Funcionais

| Tipo | Requisito | Evidência | Confiança |
|------|----------|----------|-----------|
| Precisão | Fuzzy matching com fallback difflib se rapidfuzz indisponível | `name_normalizer.py` | 🟢 |
| Performance | Logistic CDF analítico (O(1)) vs simulação numérica | `bid_simulator.py` | 🟢 |
| Manutenibilidade | Parâmetros de custo extraíveis para config | `cost_estimator.py:CostParams` | 🟡 |

## Critérios de Aceitação

```gherkin
Cenário: Normalização de nome de órgão público
Dado "Prefeitura Municipal de Florianópolis"
Quando normalize_name é chamado
Então retorna "PREFEITURA MUNICIPAL FLORIANOPOLIS"
E "MUN" foi expandido para "MUNICIPAL"
E acentos foram removidos

Cenário: Simulação de lance com dados históricos
Dado 10 contratos históricos do mesmo órgão com desconto mediano 15% e σ=5%
E modalidade = Pregão Eletrônico (5)
Quando simulate_bid é executado
Então desconto_sugerido ≈ 16.5% (median + 0.3σ)
E p_vitoria > 0 e < 1
```
