# PNCP v3 Coverage Expansion Report

**Data:** 2026-07-11T20:56:00-03:00
**Baseline:** 771 entes cobertos PNCP
**Resultado:** 983 entes cobertos PNCP
**Ganho:** +212 entidades (+27.5%)

## Summary

A expansao de cobertura PNCP v3 foi um sucesso, superando significativamente o target de +30 a +50 novas entidades.

### Alteracoes Realizadas

| Parametro | Antes | Depois |
|-----------|-------|--------|
| Modalidades | 4,5,6,7,8,12 | 1,2,3,4,5,6,7 |
| Date Range (dias) | 30 | 90 |
| Request Delay (s) | 0.5 | 0.3 |
| Keyword Filter | `_ENGINEERING_KEYWORDS` presente | Removido completamente |

### Resultados do Crawl

| Metrica | Antes | Depois | Delta |
|---------|-------|--------|-------|
| Total PNCP bids | ~24K | 202.858 | +178K |
| PNCP coverage (all) | 771 | 983 | **+212** |
| PNCP coverage (200km) | 376 | 455 | **+79** |
| Overall coverage | 813 (39.0%) | 1.020 (48.9%) | **+9.9pp** |
| Modalidade 1 records | 0 | 16 | +16 |
| Matched bids | - | 110.786 | - |

### Modalidades Ativas

| Modalidade | Records |
|-----------|---------|
| 1 (Pregao Presencial) | 16 |
| 4 (Concorrencia) | 14.024 |
| 5 (Pregao Eletronico) | 775 |
| 6 (Concurso) | 65.343 |
| 7 (Dispensa) | 1.664 |
| 8 (Inexigibilidade) | 116.682 |
| 12 (Dialogo Competitivo) | 4.354 |

### Cobertura por Fonte (raio 200km)

| Fonte | Cobertas | Total | % |
|-------|----------|-------|---|
| pncp | 455 | 1.093 | 41.6% |
| ciga_ckan | 152 | 1.093 | 13.9% |
| compras_gov | 57 | 1.093 | 5.2% |
| pcp | 26 | 1.093 | 2.4% |
| demais fontes | 0 | 1.093 | 0.0% |

### Observacoes

1. **API Rate Limiting:** O delay de 0.3s configurado (AC4) mostrou-se agressivo demais para o volume de requests (7 modalidades * 90 dias). Durante a execucao, foi necessario aumentar para 1.0-1.5s para evitar erros 429 (Too Many Requests) e conexoes fechadas pelo servidor.

2. **Modalidades 2 e 3:** Nao retornaram registros para SC no periodo. Modalidade 1 (Pregao Presencial) retornou 16 registros. O ganho principal veio da janela expandida de 90 dias (vs 30), que capturou mais bids nas modalidades 4-7.

3. **Rapidfuzz:** A instalacao do `rapidfuzz` reduziu drasticamente o tempo de entity matching de ~30min+ para ~2min.

4. **Logging Issue:** `config/logging_config.py` linha 88 usa `datetime.UTC` que nao funciona no Python 3.12. Causa erros de logging mas nao interrompe a execucao.

### Crawl Details
- Crawl exit code: 0
- Entity matching: 178.101 registros processados (2.348 CNPJ, 7.017 nome, 76.664 fuzzy)
- Rate limits: 0 apos ajuste do delay
