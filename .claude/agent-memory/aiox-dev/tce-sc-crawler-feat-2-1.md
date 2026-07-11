---
name: tce-sc-crawler-feat-2-1
description: TCE-SC SCMWeb crawler findings — pagination fix, viability research, API behavior
metadata:
  type: reference
---

## TCE-SC SCMWeb Crawler (FEAT-2.1)

**Key findings documented during implementation:**

1. **SCMWeb API confirmed functional** (HTTP 200) at `https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285`
   - Licitações endpoint: `page=licitacoes&export=json&type=licitacoes` — returns list of dicts with keys: Numero, Modalidade, Objeto, Data_Abertura, Valor_Estimado, Status, Ano
   - Contratos endpoint: `page=contratos&export=json&type=contratos` — returns list of dicts with keys: Numero, Contratado, CNPJ, Objeto, Valor, Status

2. **API peculiarity**: SCMWeb IGNORES the `pn` (page number) parameter and always returns the full dataset regardless of page number. The original crawler had infinite pagination as a result. **Fix**: Changed to single-page fetch (page 1 only) with client-side date filtering via `Data_Abertura` field.

3. **e-Sfinge portal not accessible**: `https://e-sfinge.tce.sc.gov.br` is offline (connection timeout). Not viable.

4. **TCE-SC dados abertos migrated**: Redirects from `tce.sc.gov.br` to `tcesc.tc.br` but `/dados-abertos` returns 404.

5. **Viability decision**: SCMWeb is the only viable source — documented in `docs/research/tce-sc-viability.md`.

6. **Coverage estimate**: 890 records (16 licitações + 874 contratos) in a 30-day window. Contracts represent majority of data volume.

7. **Crawler already existed** at `scripts/crawl/tce_sc_crawler.py` with full crawl/transform/feature flag implementation. Monitor.py already maps `tce_sc` → `tce_sc_crawler`.
