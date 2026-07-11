# Lib — Design

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

## Name Normalizer Pipeline
```
normalize_name(name) → NFKD → upper → strip_punct → strip_cnpj → collapse_ws → expand_abbrev → return
```
18 abbreviations (word-boundary regex, sorted by length descending). Abbrev dictionary merge: built-in + YAML file.

## Bid Simulator
```python
@dataclass
class BidSimulation:
    lance_sugerido: float; desconto_sugerido_pct: float
    p_vitoria_pct: float; margem_liquida_pct: float; valor_esperado: float
    lance_agressivo: float; lance_conservador: float
    competidores_esperados: int; historico_contratos: int
    confianca: str  # ALTA|MEDIA|BAIXA|INSUFICIENTE
    racional: str
```
6 sector profiles (engenharia 25% BDI, TI 30%, consultoria 35%, etc.)

## Cost Estimator
```python
@dataclass
class CostParams:
    custo_km=0.80; diaria_hospedagem_capital=280; diaria_hospedagem_interior=180
    per_diem_alimentacao=80; custo_hora_tecnico=150; horas_sessao=4.0
    limiar_hospedagem_km=200; limiar_duas_diarias_km=500
    pedagio_por_faixa: dict[int,float]  # 5 tiers
```
Electronic: min R$600. Site visit: +R$2/km if >200km.

## Victory Profile
```python
@dataclass
class VictoryProfile:
    valor_mean, valor_std, valor_q25, valor_q75, valor_min, valor_max
    modalidade_weights: dict[int, float]; pop_bracket_weights: dict[str, float]
    keyword_freq: dict[str, float]; dist_mean_km, dist_max_km
    uf_weights: dict[str, float]; total_contracts, period_months, company_capital
```
Fit score: weighted 5-dimension (30/25/15/15/15). Requires ≥3 historical contracts.

## Doc Templates
```python
class DocType(Enum): EDITAL, TERMO_REFERENCIA, PLANILHA, UNKNOWN
@dataclass
class StructuredExtraction:
    doc_type: DocType; fields: dict[str, ExtractedField]
    total_fields: int; found_fields: int; completeness_pct: float
```
13 fields (edital), 6 (termo), 4 (planilha). Confidence decay: 1.0→0.85→0.7→... floor 0.3.

🟢 CONFIRMADO — Todos os 11 módulos verificados.
