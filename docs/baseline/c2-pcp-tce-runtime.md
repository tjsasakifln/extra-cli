# C2.4 — PCP + TCE-SC runtime (fechamento janela 30d)

**Date:** 2026-07-16  
**Task:** C2.4

## PCP

- Registry: `pcp` · capabilities `open_tenders` · público
- Golden path / monitor: runs com fetched>0 (ex. 181 records em runs anteriores)
- Status: **OK**

## TCE-SC

```text
tce_crawl_n 65970
sample_keys: Numero, Modalidade, Objeto, Data_Abertura, Valor_Estimado, Status, Ano, _tipo
```

- Module: `scripts/crawl/tce_sc_crawler.py` · `crawl` + `transform` presentes
- Credentials: nenhuma (público)
- Nota: `pipeline_runs` ausente no DB operacional foi **corrigido** aplicando migrations 045–049; re-runs de provenance passam a ter tabela

## Validação por município

- Crawl incremental retornou dezenas de milhares de registros com objeto/modalidade/município implícito no payload SCMWeb
- Matching a universo 1093 é etapa de coverage (C2.10+); esta task prova **ativação em escala** da fonte TCE-SC

**Status task:** DONE com evidência runtime
