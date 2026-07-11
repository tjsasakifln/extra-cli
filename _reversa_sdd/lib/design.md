# Design — Módulo `lib`

> 🟢 CONFIRMADO

## Name Normalizer (7-step)

```
normalize_name(name, expand_abbreviations=True, remove_irrelevant=False)
  1. NFKD normalize → ASCII
  2. UPPERCASE
  3. re.sub(r'[^\w\s]', ' ', name)  # remove pontuação
  4. re.sub(r'\b\d{8,14}\b', '', name)  # remove CNPJ
  5. ' '.join(name.split())  # collapse whitespace
  6. (opcional) expand abbreviations (SEC→SECRETARIA, MUN→MUNICIPIO...)
  7. (opcional) remove irrelevant terms (CNPJ, CPF, END, TELEFONE...)
```

## Bid Simulator

```
simulate_bid(edital, competitive_intel, benchmark, sector) → BidSimulation
  1. Load sector margins (margem_minima, margem_alvo, bdi_referencia)
  2. Calculate HHI from competitive_intel → expected_competitors
  3. Load historical discount distribution from benchmark
  4. For discount in 0..30%:
     a. P(win) = f(discount, expected_competitors, historical_distribution)
     b. margin = (1 - discount) - sector_cost
     c. EV = P(win) × margin × valor_estimado
  5. Select discount with max EV → lance_sugerido
  6. Calculate aggressive (P(win) >= 50%) and conservative (margin >= target)
```

## Victory Profile

```
build_victory_profile(contracts, company_capital) → VictoryProfile
  - Valores → mean, std, q25, q75, min, max
  - Modalidades → Counter → normalize to 0-1
  - Municípios → map to POP_BRACKETS → normalize
  - Objetos → extract keywords → frequency
  - Distâncias → mean_km, max_km
  - UFs → Counter → normalize

score_edital_fit(edital, profile) → float (0.0-1.0)
  - value_fit × modalidade_fit × geo_fit × keyword_fit
  - Ponderado pelos pesos do setor
```
