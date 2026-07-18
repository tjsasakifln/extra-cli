# Política: mudanças de métrica exigem atualização da definição (DoD §27)

**Canônico:** `scripts/coverage/coverage_contract.py` → `METRIC_DEFINITIONS` / `MetricDefinition`  
**Gate:** `python3 -m scripts.ops.code_hygiene_gate` (bloco `metric_definitions`)

## Regra

Qualquer alteração de:

- `metric_id` ou fórmula;
- denominador / `denominator_policy`;
- semântica de readiness (`READY` / `NOT_READY`);
- label usado em relatórios comerciais;

**DEVE** atualizar no **mesmo commit**:

1. `MetricDefinition.definition`  
2. `MetricDefinition.formula`  
3. `denominator_policy`, `as_of_policy`, `source_policy`  
4. testes em `tests/test_indicator_catalog.py` (ou equivalente)  
5. se o label mudou: menções em `DOD.md` / runbooks

## Proibições

- Renomear métrica sem `legacy_aliases` de leitura.  
- Usar a palavra **coverage** para signal comercial.  
- Reduzir denominador para inflar %.  
- Marcar `READY` sem execução validada.

## Checklist de PR (métrica)

- [ ] `required_fields_present()` == True para todas as métricas  
- [ ] `export_indicator_catalog` / `validate_indicator_catalog` verdes  
- [ ] Nenhum claim 95% sem medição estrita
