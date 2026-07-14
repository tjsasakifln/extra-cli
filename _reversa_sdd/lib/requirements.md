# Lib — Shared Utilities

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1
> **Atualizado em:** 2026-07-13T16:30:00Z — Adicionados 4 sub-specs para modulos criticos ausentes

## Sub-Specs (modulos criticos)

Os 4 modulos abaixo foram identificados como ausentes na revisao (.review-group-a, C1 CRITICAL) e possuem sub-specs dedicadas:

| Modulo | Arquivo | Dependencia | Prioridade |
|--------|---------|-------------|-----------|
| `universe.py` | [`universe.md`](universe.md) | HARD — opportunity_intel, contract_intel, QW-01 | CRITICAL |
| `geocode.py` | [`geocode.md`](geocode.md) | HARD — opportunity_intel, contract_intel | CRITICAL |
| `entity_hierarchy.py` | [`entity_hierarchy.md`](entity_hierarchy.md) | HARD — entity matching coverage | HIGH |
| `value_semantics.py` | [`value_semantics.md`](value_semantics.md) | HARD — contract_intel, P1-01 preco praticado | CRITICAL |

> **Nota:** Estes 4 modulos existiam em codigo mas estavam completamente ausentes do SDD. As sub-specs preenchem essa lacuna documentando interface, fluxo, regras de negocio, dependencias e riscos de cada um.

## Visao Geral

11 modulos de utilidades compartilhadas + 4 modulos criticos documentados em sub-specs. Usados pelos pipelines de crawl e intel: normalizacao de nomes, simulacao financeira de licitacoes, estimativa de custos, victory profile, extracao de documentos, tracking de win/loss, validacao CLI, universo canonico, geocoding, hierarquia de entidades e semantica de valores.

## Modulos

| Modulo | Linhas | Funcao principal |
|--------|--------|-----------------|
| `name_normalizer.py` | 188 | `normalize_name(name)->str`: NFKD + 18 abbreviations |
| `bid_simulator.py` | 345 | `simulate_bid(edital, intel, benchmark, cnae)->BidSimulation` |
| `cost_estimator.py` | 290 | `estimate_proposal_cost(dist, dur, capital, eletronico)->dict` |
| `victory_profile.py` | 373 | `build_victory_profile(contracts, capital, ufs)->VictoryProfile` |
| `win_loss_tracker.py` | 145 | `record_outcome(cnpj, edital_id, outcome)->dict` |
| `doc_templates.py` | 405 | `extract_structured(text, doc_type)->StructuredExtraction` |
| `constants.py` | 24 | VALID_UFS, VALID_MODELS, MAX_DIAS=365 |
| `intel_logging.py` | 36 | `setup_intel_logging(script_name, level)->Logger` |
| `cli_validation.py` | 186 | 8 validators (CNPJ, UF, dias, model, etc) |
| `retry.py` | 82 | `retry_on_failure` decorator com exponential backoff |

## Requisitos Funcionais Chave

| ID | Requisito | Modulo | Prioridade |
|----|-----------|--------|-----------|
| RF-L01 | Normalizar nomes: NFKD->upper->strip->18 abbreviations | name_normalizer | Must |
| RF-L02 | Simular lance otimo: median+0.3s, P(vitoria) via logistic CDF^(N-1) | bid_simulator | Must |
| RF-L03 | Estimar custo proposta: parametrico por distancia, capital/interior, eletronico/presencial | cost_estimator | Must |
| RF-L04 | Construir victory profile: 5 dimensoes (valor 30%, keyword 25%, modalidade 15%, geo 15%, pop 15%) | victory_profile | Should |
| RF-L05 | Extrair campos de documentos: regex patterns com confidence decay (-0.15/pattern) | doc_templates | Should |
| RF-L06 | Rastrear win/loss para calibrar modelos: JSON local | win_loss_tracker | Could |
| RF-L07 | Validar inputs CLI com exit code 1 em falha | cli_validation | Must |
| RF-L08 | Retry com exponential backoff configuravel | retry | Must |

## Requisitos Nao Funcionais

| Tipo | Requisito | Evidencia | Confianca |
|------|----------|----------|-----------|
| Precisao | Fuzzy matching com fallback difflib se rapidfuzz indisponivel | `name_normalizer.py` | |
| Performance | Logistic CDF analitico (O(1)) vs simulacao numerica | `bid_simulator.py` | |
| Manutenibilidade | Parametros de custo extraiveis para config | `cost_estimator.py:CostParams` | |

## Criterios de Aceitacao

```gherkin
Cenario: Normalizacao de nome de orgao publico
Dado "Prefeitura Municipal de Florianopolis"
Quando normalize_name e chamado
Entao retorna "PREFEITURA MUNICIPAL FLORIANOPOLIS"
E "MUN" foi expandido para "MUNICIPAL"
E acentos foram removidos

Cenario: Simulacao de lance com dados historicos
Dado 10 contratos historicos do mesmo orgao com desconto mediano 15% e s=5%
E modalidade = Pregao Eletronico (5)
Quando simulate_bid e executado
Entao desconto_sugerido = 16.5% (median + 0.3s)
E p_vitoria > 0 e < 1
```
