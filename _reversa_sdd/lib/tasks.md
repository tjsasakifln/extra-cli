# Tasks — Módulo `lib`

> 🟢 CONFIRMADO

### T1: Name Normalizer
- **Arquivo legado:** `scripts/lib/name_normalizer.py`
- **Confiança:** 🟢
- **Descrição:** Implementar `normalize_name()` com 7-step pipeline. Dicionário de 18 abreviações. Suporte a YAML externo. Fallback difflib/rapidfuzz.
- **Critério de pronto:** Normalização funcional para nomes com e sem acentos. Abreviações expandidas corretamente.

### T2: Bid Simulator
- **Arquivo legado:** `scripts/lib/bid_simulator.py`
- **Confiança:** 🟢
- **Descrição:** `simulate_bid()` com HHI, margens setoriais, distribuição de descontos. Retornar `BidSimulation` dataclass.
- **Critério de pronto:** Simulação retorna lance sugerido, agressivo, conservador. EV calculado.

### T3: Victory Profile
- **Arquivo legado:** `scripts/lib/victory_profile.py`
- **Confiança:** 🟢
- **Descrição:** `build_victory_profile()` e `score_edital_fit()`. 5 faixas populacionais. Normalização de frequências.
- **Critério de pronto:** Perfil construído de contratos. Fit score 0-1 funcional.

### T4: Cost Estimator + Win/Loss Tracker
- **Arquivo legado:** `scripts/lib/cost_estimator.py`, `scripts/lib/win_loss_tracker.py`
- **Confiança:** 🟢
- **Descrição:** Estimativa de custos diretos + BDI. Tracking de propostas enviadas, ganhas e perdidas com razões.
- **Critério de pronto:** Estimativa funcional. Tracking persiste dados.
