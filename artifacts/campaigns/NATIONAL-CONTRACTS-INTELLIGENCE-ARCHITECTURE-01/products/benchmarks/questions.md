# Benchmarks — Comparability Rules & Business Questions

**Product:** P3 Benchmarks de valor  
**Primary modules:** `scripts/ops/deliverable_d_prices.py`, value semantics (`valor_total` contratado vs estimado/homologado/pago)  
**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  

Labels: **FACT** | **INDICATOR** | **INFERENCE** | **NOT_READY**

---

## 1. Purpose

Produzir faixas de referência de valor **defensáveis** para apoiar propostas e revisão de preços — sem rotular valores globais heterogêneos como “preço de mercado” ou “preço real praticado”.

---

## 2. Value semantics (never mix in one panel)

| Semântica | Origem típica | Uso legítimo | Uso ilegítimo |
|-----------|---------------|--------------|---------------|
| **contratado** | `pncp_supplier_contracts.valor_total` | Totais e tickets de contratos assinados | “preço unitário de mercado” |
| **estimado** | `pncp_raw_bids.valor_total_estimado` (ou item) | Teto/referência do edital | Misturar com contratado sem label |
| **homologado** | Resultado de certame (quando existir) | Preço vencedor do item | Deságio sem mesmo item |
| **pago** | Execução financeira (se existir) | Realizado | Assumir = contratado |

Cada painel declara **uma** semântica dominante; multi-semântica só lado a lado, nunca na mesma mediana.

---

## 3. Comparability dimensions (deliverable D)

Dimensões documentadas:

| Dimensão | Papel | Se divergir |
|----------|-------|-------------|
| `tipo_obra_servico` | Família de objeto (taxonomia versionada) | **NÃO COMPARÁVEL** |
| `unidade` | m², m, un, global, vb… | **NÃO COMPARÁVEL** se unidades diferentes |
| `lote` | Escopo/lote do certame | Separar grupos |
| `porte` | Faixa de valor ou porte da obra | Separar ou bandas explícitas |
| `regiao` | UF / mesorregião / raio | Separar |
| `periodo` | Ano/trimestre | Mesmo grupo base; evolução temporal à parte |

**Group key (D):** `tipo + unidade + lote + porte + regiao`  
**Period:** rastreado para evolução, não para misturar anos sem aviso.

---

## 4. When observations are NOT comparable

Publicar esta checklist em todo output de benchmark.

### 4.1 Hard non-comparability (must split or discard from panel)

1. **Semânticas de valor diferentes** no mesmo painel (estimado vs contratado vs homologado vs pago).  
2. **Unidades físicas diferentes** (m² vs global vs “verba”).  
3. **Objetos em famílias distintas** da taxonomia (ex.: pavimentação vs limpeza predial).  
4. **Escopos globais heterogêneos** (`is_global_heterogeneous=true`): múltiplos itens embutidos sem rateio → **não** entram como “preço unitário”; no máximo painel separado “globais brutos” com disclaimer.  
5. **Regiões incomparáveis para o uso** (ex.: mediana nacional para proposta municipal SC sem painel SC).  
6. **Períodos com choque de regra/ inflação não ajustado** quando o cliente pede “preço atual” — ou ajustar com índice explícito (INDICATOR) ou separar período.  
7. **Porte muito diferente** (contrato R$ 50k vs R$ 50M) na mesma mediana sem bandas.  
8. **Par deságio** entre estimado e homologado de **certames/lotes/itens diferentes**.

### 4.2 Soft non-comparability (panel OK only with caveats)

| Condição | Tratamento |
|----------|------------|
| `municipio_inferido = TRUE` | Flag de qualidade; não usar para micro-benchmark municipal |
| n < `min_sample` (default 5) | Status `INSUFFICIENT_SAMPLE` — **não** publicar mediana como referência |
| Outliers IQR | Flag; default **não** dropar silenciosamente (`drop_outliers=false`) |
| Texto de objeto similar, unidade global | INDICATOR de “texto parecido” ≠ equivalência técnica → manter fora de unit price |
| Só valor contratado total sem quantitativo | Painel de **ticket de contrato**, nunca “R$/m²” |

### 4.3 Explicit ban list (claims_forbidden)

- “Preço real praticado” para globais heterogêneos.  
- Cruzar tipo/unidade/região/período como se fosse um único mercado.  
- Esconder outliers sem registrar regra.  
- Fabricar referências com DSN vazio.  
- Usar similaridade de `objeto_contrato` como prova de mesmo serviço técnico.  
- Converter `valor_total` em unitário sem quantidade FACT.

---

## 5. Business questions

### BQ-1 — Qual a mediana contratada para família F na região R?

| | |
|--|--|
| **FACT** | Observações com valor + dimensões preenchidas. |
| **INDICATOR** | n, mediana, p25, p75, min, max. |
| **INFERENCE** | “Devemos precificar em torno de M”. |
| **Gate** | Comparabilidade §4 + n≥min_sample. |
| **Decisão** | Faixa de proposta; alerta se edital << p25 ou >> p75. |

### BQ-2 — O valor estimado do edital está acima/abaixo do histórico comparável?

| | |
|--|--|
| **FACT** | Estimado do edital (bid) + painel histórico **mesma** semântica e dimensões. |
| **INDICATOR** | vs_estimado ∈ {ABAIXO, DENTRO, ACIMA} vs banda p25–p75 (auditor C13 pattern). |
| **INFERENCE** | “Edital inchado/apertado”. |
| **Risco** | Estimado de edital atual vs contratos antigos sem ajuste temporal. |

### BQ-3 — Como evoluiu a mediana no tempo?

| | |
|--|--|
| **FACT** | Valores por `periodo`. |
| **INDICATOR** | Série de medianas por período (mesmo group key). |
| **INFERENCE** | Inflação setorial / aquecimento. |
| **Gate** | Só se cada ponto de série respeita min_sample **ou** marca LOW_N. |

### BQ-4 — Deságio homologado vs estimado no item

| | |
|--|--|
| **FACT** | Par same certame/lote/item. |
| **INDICATOR** | deságio%. |
| **NOT_READY** | Sem par → não imputar via ticket contratado. |

### BQ-5 — Ticket médio de contratos “globais” em família F

| | |
|--|--|
| **Uso** | Quando não há unitário. |
| **Label** | “Ticket contratado (escopo global)” — **não** preço unitário. |
| **INDICATOR** | mediana de `valor_total` no bucket textual **fraco** + disclaimer de não-equivalência técnica. |

---

## 6. Query sketches

```sql
-- BQ-1 sketch: contracted totals by coarse region/year (NOT unit price)
-- Application layer must assign tipo_obra_servico / unidade before grouping.
SELECT
  uf AS regiao,                                    -- FACT
  date_trunc('quarter', data_inicio) AS periodo,   -- FACT
  COUNT(*) AS n,                                   -- INDICATOR
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY valor_total) AS mediana, -- INDICATOR
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor_total) AS p25,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor_total) AS p75,
  MIN(valor_total) AS min_v,
  MAX(valor_total) AS max_v
FROM pncp_supplier_contracts
WHERE is_active
  AND valor_total > 0
  AND uf = 'SC'
  -- AND <object family filter versioned>
GROUP BY 1, 2
HAVING COUNT(*) >= 5;   -- else INSUFFICIENT_SAMPLE
```

```sql
-- Non-comparability diagnostic: share of contracts missing dates/values
SELECT
  COUNT(*) AS n,
  COUNT(*) FILTER (WHERE valor_total IS NULL OR valor_total <= 0) AS sem_valor,
  COUNT(*) FILTER (WHERE data_inicio IS NULL) AS sem_inicio,
  COUNT(*) FILTER (WHERE municipio_inferido IS TRUE) AS municipio_inferido
FROM pncp_supplier_contracts
WHERE is_active;
```

---

## 7. Outlier policy

| Rule | Default |
|------|---------|
| Método | IQR, k=1.5 (deliverable D) |
| Ação | **Flag**, não drop |
| Se drop | Exigir `drop_outliers=true` + lista dos valores removidos no relatório |
| Comunicação | min/max sempre visíveis; mediana não esconde extremos |

---

## 8. Decision support matrix

| Situação | Ação do analista |
|----------|------------------|
| n≥5, dimensões alinhadas, 1 semântica | Publicar banda p25–p75 + mediana |
| n<5 | `INSUFFICIENT_SAMPLE`; ampliar região/período **com label** ou recusar referência |
| Só globais misturados | Painel ticket; ban unitário e “preço real” |
| Edital sem unidade clara | REVIEW; não forçar benchmark unitário |
| Concorrente com ticket outlier | Não usar 1 contrato como “preço de mercado” |

---

## 9. Links to other products

- **P1:** tickets de concorrentes usam mesma semântica CONTRATADO.  
- **P4:** órgãos com muitos contratos alimentam amostras locais.  
- **P8:** painel SC vs nacional separados.  
- **P9:** números de benchmark no PDF devem reconciliar com Excel do mesmo run_id.
