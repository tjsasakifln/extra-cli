# Competitors — Business Questions & Hypotheses

**Product:** P1 Mapa de concorrentes + P2 Radar de entrantes  
**Primary data:** `pncp_supplier_contracts` / `v_supplier_winners` / deliverable B  
**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  

Labels: **FACT** | **INDICATOR** | **INFERENCE** | **NOT_READY**

---

## 0. Framing honesto

- Observamos **vencedores históricos com contrato registrado** (fornecedor no contrato PNCP).  
- **Não** observamos todos os licitantes nem quem perdeu → **win rate = NOT_READY** (ADR-016).  
- `valor_total` / `valor_global` = **valor contratado**, **não** “preço unitário praticado”.  
- Capacidade operacional do concorrente = **INFERENCE/HYPOTHESIS** (deliverable B).

---

## Q1 — Quem são os maiores fornecedores no universo-alvo?

| | |
|--|--|
| **Hipótese de negócio** | Poucos CNPJs concentram a maior parte do valor contratado no recorte (SC / 200 km / perfil objeto). |
| **Pergunta** | Qual o ranking top-N por valor e por quantidade de contratos? |
| **FACT** | Por `fornecedor_cnpj`: lista de `contrato_id`, `valor_total`, `orgao_cnpj`, datas, `uf`. |
| **INDICATOR** | `valor_contratado_total`, `n_contratos`, ticket = valor/n, `qtd_orgaos_distintos`. |
| **INFERENCE** | “Líder de mercado SC em engenharia” (só se filtro de objeto + recorte forem explícitos). |
| **Dados necessários** | `fornecedor_cnpj`, `fornecedor_nome`, `valor_total`, `is_active`, join opcional a `sc_public_entities` para raio. |
| **Query sketch** | Ver bloco SQL abaixo (Q1). |
| **Riscos** | CNPJ filial vs matriz; nomes divergentes; filtro de objeto por regex falso-positivo; recorte incompleto. |
| **Decisão suportada** | Shortlist de 10–15 concorrentes para brief; alocação de effort de inteligência. |

```sql
-- Q1 sketch: top suppliers by contracted value in SC (example filter)
SELECT
  fornecedor_cnpj,
  MAX(fornecedor_nome) AS nome,
  COUNT(*) AS n_contratos,                          -- INDICATOR
  SUM(valor_total) AS valor_contratado_total,       -- INDICATOR over FACT
  COUNT(DISTINCT orgao_cnpj) AS qtd_orgaos,         -- INDICATOR
  SUM(valor_total) / NULLIF(COUNT(*), 0) AS ticket  -- INDICATOR
FROM pncp_supplier_contracts
WHERE is_active IS TRUE
  AND fornecedor_cnpj IS NOT NULL
  AND uf = 'SC'   -- replace with raio_200km join when that is the universe
GROUP BY fornecedor_cnpj
ORDER BY valor_contratado_total DESC
LIMIT 15;
```

**Reuse:** `deliverable_b_competitors.select_competitors`, `v_supplier_winners`.

---

## Q2 — Em quais órgãos cada concorrente “vence” de forma recorrente?

| | |
|--|--|
| **Hipótese** | Alguns fornecedores dominam órgãos específicos (alto award share local). |
| **FACT** | Pares (fornecedor, órgão, contrato, valor). |
| **INDICATOR** | Share do fornecedor no órgão = valor_f / valor_órgão; #contratos no órgão; ranking por órgão. |
| **INFERENCE** | “Órgão capturado”; “relacionamento privilegiado” — **sem prova de conluio**. |
| **Dados** | `fornecedor_cnpj`, `orgao_cnpj`, `valor_total`. |
| **Query sketch** | Window `SUM(valor) OVER (PARTITION BY orgao)` + ratio. |
| **Riscos** | Órgãos com 1–2 contratos → share instável; confundir sede/secretaria. |
| **Decisão** | Priorizar órgãos com HHI alto e vigências próximas (cruzar P4/C). |

```sql
-- Q2 sketch: award concentration per agency
WITH base AS (
  SELECT orgao_cnpj, fornecedor_cnpj,
         SUM(valor_total) AS v, COUNT(*) AS n
  FROM pncp_supplier_contracts
  WHERE is_active AND valor_total > 0
  GROUP BY 1, 2
),
tot AS (
  SELECT orgao_cnpj, SUM(v) AS v_org FROM base GROUP BY 1
)
SELECT b.orgao_cnpj, b.fornecedor_cnpj, b.v, b.n,
       b.v / NULLIF(t.v_org, 0) AS share_valor  -- INDICATOR
FROM base b
JOIN tot t USING (orgao_cnpj)
WHERE b.v / NULLIF(t.v_org, 0) >= 0.25
ORDER BY share_valor DESC;
```

---

## Q3 — O concorrente está ativo agora ou só tem histórico antigo?

| | |
|--|--|
| **Hipótese** | Ranking por volume histórico superestima players inativos. |
| **FACT** | `data_fim`, `data_inicio`, `is_active` (flag de ingestão ≠ vigência jurídica). |
| **INDICATOR** | Contagem de contratos com `data_fim >= as_of` **e** evidência de status se existir. |
| **INFERENCE** | “Operando em SC agora”. |
| **Regra deliverable B** | Claim “ativo” só com vigencia + status + status_as_of → senão não afirmar. |
| **Riscos** | `is_active` de linha ≠ contrato vigente; aditivos não modelados na tabela base. |
| **Decisão** | Separar “histórico total” vs “carteira vigente estimada”. |

---

## Q4 — Qual o deságio típico do concorrente?

| | |
|--|--|
| **Hipótese** | Alguns players competem com deságio sistemático. |
| **FACT** | Par `valor_estimado` + `valor_homologado` no **mesmo** certame/lote/item. |
| **INDICATOR** | deságio% = (est − hom) / est * 100. |
| **INFERENCE** | “Estratégia de preço agressiva”. |
| **NOT_READY / INSUFFICIENT_PAIR** | Sem vínculo certame-lote-item; só `valor_total` contratado. |
| **Reuse** | `desagio_from_pair` em deliverable B. |
| **Decisão** | Só citar deságio quando status = PRESENTED; caso contrário omitir. |

---

## Q5 — Quem é entrante recente no recorte?

| | |
|--|--|
| **Hipótese** | Novos CNPJs no universo SC/200km aumentam pressão em órgãos-alvo. |
| **FACT** | `MIN(data_inicio)` por fornecedor no recorte. |
| **INDICATOR** | Entrante se `first_seen >= as_of - N months` e n≥1. |
| **INFERENCE** | “Entrante nacional expandindo para SC”. |
| **Riscos** | Lacuna de backfill → falso entrante; mudança de CNPJ filial. |
| **Decisão** | Watchlist + cruzamento com editais abertos (deliverable E). |

```sql
-- Q5 sketch
WITH firsts AS (
  SELECT fornecedor_cnpj,
         MIN(data_inicio) AS first_contract,   -- FACT aggregate
         COUNT(*) AS n,
         SUM(valor_total) AS valor
  FROM pncp_supplier_contracts
  WHERE is_active AND uf = 'SC'
  GROUP BY 1
)
SELECT *,
  (first_contract >= CURRENT_DATE - INTERVAL '12 months') AS is_entrant_flag  -- INDICATOR
FROM firsts
WHERE first_contract >= CURRENT_DATE - INTERVAL '12 months'
ORDER BY valor DESC NULLS LAST;
```

---

## Q6 — Distribuição geográfica do concorrente

| | |
|--|--|
| **Hipótese** | Concorrente forte nacionalmente pode ser fraco em SC (e vice-versa). |
| **FACT** | `uf`, `municipio`, `codigo_municipio_ibge`, `municipio_inferido`. |
| **INDICATOR** | Share de contratos/valor por UF; presença em raio 200 km. |
| **INFERENCE** | “Prioriza Sul”; “não cobre interior SC”. |
| **Riscos** | UF do contrato ≠ local da obra; município inferido. |
| **Decisão** | Dual lens P8 antes de classificar “concorrente local”. |

---

## Q7 — Especialização por tipo de objeto

| | |
|--|--|
| **Hipótese** | Concorrentes se concentram em famílias de objeto (reforma, pavimentação, etc.). |
| **FACT** | Texto `objeto_contrato`. |
| **INDICATOR** | Contagem por bucket de keywords **versionado** (mesmo dicionário que buyer_intel AEC regex). |
| **INFERENCE** | “Especialista em X”. |
| **Proibido** | Equivalência técnica entre contratos só por similaridade de texto. |
| **Decisão** | Comparar apples-to-apples em P3; em P1 só “frequência de menções em buckets”. |

---

## Q8 — Market share e HHI no mercado filtrado

| | |
|--|--|
| **Hipótese** | Mercado de contratos no recorte é concentrado (poucos players). |
| **FACT** | Valores por fornecedor no filtro. |
| **INDICATOR** | share_i, HHI = Σ(share%²); classificação de concentração (documentar escala). |
| **INFERENCE** | Barreiras de entrada. |
| **NOT_READY** | Win rate. |
| **Reuse** | ADR-016, `competitive_intel_validation`, consulting_readiness. |
| **Decisão** | Se HHI alto em órgão-alvo + contrato vencendo → prioridade comercial (com C). |

---

## Q9 — Coocorrência com outros fornecedores no mesmo órgão (não parceria)

| | |
|--|--|
| **Hipótese** | Fornecedores que se alternam no mesmo órgão podem ser rivais ou (INFERENCE) complementares. |
| **FACT** | Múltiplos `fornecedor_cnpj` distintos com contratos no mesmo `orgao_cnpj`. |
| **INDICATOR** | Grafo de coocorrência; Jaccard de conjuntos de órgãos. |
| **INFERENCE** | Parceria/consórcio — **somente se houver campo de prova externo**. |
| **Proibido** | Rotular aresta do grafo como “parceiro”. |
| **Decisão** | Input para P5 com label de sinal. |

---

## Q10 — Ticket e porte aparente

| | |
|--|--|
| **Hipótese** | Concorrentes de ticket alto vs pulverizado exigem estratégias distintas. |
| **FACT** | `valor_total` por contrato. |
| **INDICATOR** | ticket médio, mediana, p90; #contratos > limiar. |
| **INFERENCE** | “Capacidade para obras grandes” (sem balanço/capital social = hipótese). |
| **Decisão** | Match de editais por faixa de valor no scoring (E/ranking). |

---

## Matriz hipótese → prova mínima

| Hipótese | Mínimo para FACT | Senão |
|----------|------------------|-------|
| Top-N vencedores | CNPJ + contratos + valor no recorte | Lista vazia / INSUFFICIENT |
| Deságio médio | Pares estimado+homologado same item | NOT_APPLICABLE |
| Ativo agora | Vigência + status datado | “histórico apenas” |
| Entrante | first_seen no recorte completo | “aparenta entrante (cobertura parcial)” |
| Parceiro de Y | Campo consórcio/subcontrato em fonte | Proibido |
| Win rate 40% | Participações + resultados | NOT_READY |
| Especialista técnico em X | Catálogo/CNAE/atestados + objeto | Só bucket textual (INDICATOR fraco) |

---

## Claims policy (espelho deliverable B)

**Allowed**

- “No recorte R e período P, CNPJ Z tem N contratos somando V (valor contratado).”  
- “Lista apresenta K≤15 defensáveis; não completamos com ruído.”  
- “Deságio X% no par certame C (quando PRESENTED).”  

**Forbidden**

- Completar lista até 15 com ruído.  
- Deságio sem par comparável.  
- Ativo sem vigência+status.  
- Capacidade como fato.  
- ESTIMADO como CONTRATADO.  
- “Parceiro/consórcio/subcontratado de…” sem prova.  
- Win rate.  

---

## Prioridade de implementação analítica

1. Q1 + Q6 + Q8 com recortes P8 (reuso B + HHI).  
2. Q2 + Q3 (órgão e vigência).  
3. Q5 (entrantes).  
4. Q7 buckets versionados.  
5. Q4 só se pipeline de pares bid↔contract maduro.  
6. Q9 como produto de sinais (P5).
