# Lib — Tasks

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

| # | Tarefa | Fonte | Confiança |
|---|--------|-------|-----------|
| T-L01 | Implementar `normalize_name()`: NFKD + uppercase + strip + 18 abbreviations | `name_normalizer.py:1-188` | 🟢 |
| T-L02 | Implementar `simulate_bid()`: logistic CDF, median+0.3σ, 6 setores | `bid_simulator.py:1-345` | 🟢 |
| T-L03 | Implementar `estimate_proposal_cost()`: paramétrico, CostParams | `cost_estimator.py:1-290` | 🟢 |
| T-L04 | Implementar `build_victory_profile()` + `score_edital_fit()`: 5 dimensões | `victory_profile.py:1-373` | 🟢 |
| T-L05 | Implementar `extract_structured()`: regex patterns, confidence decay | `doc_templates.py:1-405` | 🟢 |
| T-L06 | Implementar `record_outcome()` + `calibration_report()`: JSON tracker | `win_loss_tracker.py:1-145` | 🟢 |
| T-L07 | Implementar CLI validators: CNPJ, UF, dias, model, input file, JSON | `cli_validation.py:1-186` | 🟢 |
| T-L08 | Implementar `retry_on_failure` decorator: exponential backoff | `retry.py:1-82` | 🟢 |
| T-L09 | Implementar `setup_intel_logging()`: stderr handler | `intel_logging.py:1-36` | 🟢 |
| T-L10 | Definir constants: VALID_UFS, VALID_MODELS, MAX_DIAS=365 | `constants.py:1-24` | 🟢 |

**Estimativa:** 3-5 dias (10 tarefas)
