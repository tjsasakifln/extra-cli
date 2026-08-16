# Observabilidade — contract comparables inbound (#415)

- grupos avaliados: 7
- COMPARABLE: 2
- HOLD_FOR_DATA: 1
- NOT_COMPARABLE: 4
- taxa de rejeição: 0.7143
- custo/latência total (ms): 1265.329
- recomendação: manter

## Grupos

- `comparable_clear` status=COMPARABLE n=8 usable=8/8 reasons=['fixture_not_official_live']
- `regime_incompatible` status=NOT_COMPARABLE n=None usable=0/5 reasons=['incompatible_regime', 'fixture_not_official_live']
- `geo_period_inadequate` status=NOT_COMPARABLE n=None usable=0/5 reasons=['geography_not_comparable', 'period_not_comparable', 'fixture_not_official_live']
- `insufficient_sample` status=NOT_COMPARABLE n=None usable=2/2 reasons=['insufficient_n', 'fixture_not_official_live']
- `missing_values` status=HOLD_FOR_DATA n=None usable=0/5 reasons=['unknown_excluded_from_denominator', 'missing_value', 'fixture_not_official_live']
- `duplicate_rectification` status=NOT_COMPARABLE n=None usable=4/4 reasons=['duplicate_or_rectification', 'fixture_not_official_live']
- `statistical_outlier` status=COMPARABLE n=8 usable=8/8 reasons=['statistical_difference_only', 'fixture_not_official_live']

## Reason codes

- `duplicate_or_rectification`: 1
- `fixture_not_official_live`: 7
- `geography_not_comparable`: 1
- `incompatible_regime`: 1
- `insufficient_n`: 1
- `missing_value`: 1
- `period_not_comparable`: 1
- `statistical_difference_only`: 1
- `unknown_excluded_from_denominator`: 1

## Late arrivals

A late arrival or rectification invalidates only groups that include the affected contract_id.

## Recomendação

Canary has at least one COMPARABLE group and explicit refusals; keep the engine.

