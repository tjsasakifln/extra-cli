# Contracting Agencies — Intelligence Questions

**Product:** P4 Inteligência de órgãos + inputs a P2/P7/C  
**Primary modules:** `deliverable_a_org_ranking.py`, `scripts/buyer_intel/*`, `v_expiring_contracts`, `v_contract_historical`, `sc_public_entities`  
**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  

Labels: **FACT** | **INDICATOR** | **INFERENCE** | **NOT_READY**

---

## 1. Purpose

Priorizar órgãos públicos para prospecção e preparação de propostas com base em **histórico contratual observável**, sem confundir lacuna de coleta com “órgão sem licitações”.

---

## 2. Universe definitions (must be stated on every report)

| Universo | Definição operacional | Fonte |
|----------|----------------------|--------|
| **Raio 200 km** | Entidades com distância Haversine ≤ 200 km de Florianópolis e coordenadas | `contract_intel.target_universe`, `sc_public_entities.raio_200km` |
| **SC amplo** | Contratos com `uf = 'SC'` | `pncp_supplier_contracts.uf` |
| **Nacional disponível** | Linhas PNCP ingeridas (não = cobertura nacional completa) | volume de tabela |
| **Perfil AEC** | Objeto matcha regex/dicionário versionado de engenharia/construção | buyer_intel |

**Regra:** nunca usar volume nacional como prova de cobertura SC (P8).

---

## 3. Core business questions

### A-Q1 — Quais órgãos mais contratam (valor e quantidade) no período?

| | |
|--|--|
| **FACT** | Contratos por `orgao_cnpj` / `orgao_nome` com `valor_total`, datas. |
| **INDICATOR** | Ranking por valor_total e por qtd; ticket_medio = valor/qtd (fórmula explícita). |
| **INFERENCE** | “Melhor cliente potencial”. |
| **Reuse** | Deliverable A `OrgRankRow`. |
| **Riscos** | Viés de qualidade de dados (`data_quality_limitation`); órgãos com melhor crawl sobem no ranking. |
| **Decisão** | Top-N para pipeline comercial + deep dive. |

```sql
-- A-Q1 sketch
SELECT
  orgao_cnpj,
  MAX(orgao_nome) AS orgao,
  uf,
  COUNT(*) AS qtd_contratacoes,              -- INDICATOR
  SUM(valor_total) AS valor_total,           -- INDICATOR (semântica CONTRATADO)
  SUM(valor_total) / NULLIF(COUNT(*), 0) AS ticket_medio
FROM pncp_supplier_contracts
WHERE is_active
  AND data_inicio >= :period_start
  AND data_inicio < :period_end
GROUP BY orgao_cnpj, uf
ORDER BY valor_total DESC NULLS LAST
LIMIT 50;
```

---

### A-Q2 — Zero resultado vs não consultado

| | |
|--|--|
| **FACT** | Flag de consulta no run (`consultado`) vs qtd=0. |
| **INDICATOR** | `resultado_zero = consultado AND qtd=0`. |
| **INFERENCE** | “Órgão não licita” — **proibido** se não consultado. |
| **Reuse** | Deliverable A claims_forbidden: not_consulted ≠ no licitation. |
| **Decisão** | Backlog de cobertura de fontes, não descarte comercial cego. |

---

### A-Q3 — Frequência temporal de contratações

| | |
|--|--|
| **FACT** | Eventos datados no período. |
| **INDICATOR** | N eventos / dias do período; contratos por trimestre. |
| **INFERENCE** | “Ciclo orçamentário previsível”. |
| **Decisão** | Timing de abordagem pré-pico histórico. |

---

### A-Q4 — Quem fornece para este órgão (ecossistema de vencedores)?

| | |
|--|--|
| **FACT** | Fornecedores com contrato no `orgao_cnpj`. |
| **INDICATOR** | Share por valor; HHI de fornecedores no órgão; top-5. |
| **INFERENCE** | “Mercado fechado” / “espaço para novo entrante”. |
| **Proibido** | Inferir conluio ou parceria entre fornecedores só por coocorrência. |
| **Decisão** | Cruzar com P1; se HHI alto + vigência curta → preparação antecipada. |

```sql
-- A-Q4 sketch: supplier shares inside one agency
SELECT fornecedor_cnpj, MAX(fornecedor_nome) AS nome,
       COUNT(*) AS n,
       SUM(valor_total) AS v,
       SUM(valor_total) / SUM(SUM(valor_total)) OVER () AS share  -- INDICATOR
FROM pncp_supplier_contracts
WHERE orgao_cnpj = :orgao AND is_active AND valor_total > 0
GROUP BY fornecedor_cnpj
ORDER BY v DESC;
```

---

### A-Q5 — Há contratos vincendos na janela 90–180 dias?

| | |
|--|--|
| **FACT** | `data_fim` presente e fonte/verificação quando exigido pelo deliverable C. |
| **INDICATOR** | `dias_ate_fim`; lista na janela. |
| **INFERENCE** | Probabilidade de relicitação **sem** modelo validado → só evidence class (C). |
| **Reuse** | `v_expiring_contracts`, deliverable C. |
| **Proibido** | Incluir sem vigência; fabricar % de relicitação. |
| **Decisão** | Fila de oportunidades de renovação/rebid (não promessa de vitória). |

---

### A-Q6 — Perfil AEC vs total do órgão

| | |
|--|--|
| **FACT** | `objeto_contrato` texto. |
| **INDICATOR** | `contratos_aec`, `valor_total_aec`, share AEC (buyer_intel regex). |
| **INFERENCE** | “Órgão alinhado ao core Extra”. |
| **Risco** | Falso positivo/negativo de regex; versionar dicionário. |
| **Decisão** | Ranking comprador ponderado por fit AEC, não só volume total. |

---

### A-Q7 — Modalidades e forma de contratar

| | |
|--|--|
| **FACT** | Modalidade quando disponível na fonte de bids/atos (pode faltar em contracts-only). |
| **INDICATOR** | Distribuição de modalidades no período. |
| **NOT_READY** | Se só `pncp_supplier_contracts` sem join a bids/atos → modalidade incompleta. |
| **Decisão** | Preparar equipes para pregão vs concorrência vs dispensa. |

---

### A-Q8 — Geografia e esfera do ente

| | |
|--|--|
| **FACT** | `municipio`, IBGE, natureza jurídica em `sc_public_entities` / enriched. |
| **INDICATOR** | Densidade de valor por município; distância a Floripa. |
| **INFERENCE** | “Cluster Litoral vs Oeste”. |
| **Riscos** | `municipio_inferido`; consórcios/SEM com esfera unknown (cobertura specs). |
| **Decisão** | Rotas de visita / cobertura de portais locais. |

---

### A-Q9 — Ticket e porte de contratação do órgão

| | |
|--|--|
| **FACT** | Valores por contrato. |
| **INDICATOR** | ticket médio/mediano; % contratos acima de faixas (ex. 1M, 10M). |
| **INFERENCE** | “Órgão de grandes obras” (sem validar objeto). |
| **Decisão** | Filtro de apetite (capital social / consórcio **de edital**, não de histórico inventado). |

---

### A-Q10 — Histórico 3 anos no universo-alvo

| | |
|--|--|
| **FACT** | Linhas em `v_contract_historical` (join raio 200 km). |
| **INDICATOR** | Série anual de valor e n. |
| **Limitação** | Janela e completude dependem de ingestão; buraco ≠ zero de mercado. |
| **Reuse** | `contract_intel` historical_contracts. |

---

## 4. Agency profile card (minimum fields)

| Campo | Label | Source |
|-------|-------|--------|
| orgao_cnpj / nome | FACT | contracts / entities |
| uf, municipio, ibge | FACT / quality flag | contracts |
| within_200km / distancia_km | FACT/INDICATOR | entities / target universe |
| qtd_contratos, valor_total, ticket | INDICATOR | contracts |
| share_aec | INDICATOR | buyer_intel |
| top_fornecedores[] | FACT list + share INDICATOR | contracts |
| hhi_fornecedores | INDICATOR | derived |
| contratos_vincendos_90_180 | FACT list | expiring view |
| data_quality_limitation | meta | deliverable A |
| claims_forbidden note | meta | zero vs not consulted |

---

## 5. Hypotheses that remain INFERENCE only

| Hipótese | Por que não é FACT |
|----------|-------------------|
| “Órgão prefere fornecedor local” | Exige cruzar sede do fornecedor × município do órgão com regra explícita; ainda correlacional |
| “Vai relançar em 6 meses” | Sem modelo de relicitação validado |
| “Difícil entrar” | HHI alto é INDICATOR de concentração, não barreira legal |
| “Bom relacionamento com Y” | Sem dados de rede/visitas |
| “Consórcio X+Y atende o órgão” | Sem campo de prova de consórcio |

---

## 6. Decision playbooks (agency-centric)

| Sinal (INDICATOR/FACT) | Ação comercial | Produto cruzado |
|------------------------|----------------|------------------|
| Top valor AEC + raio 200 km | Conta prioritária | P4+P1 |
| HHI fornecedor alto + data_fim em 90–180d | Prep rebid cedo | P4+C+P1 |
| qtd alta / ticket baixo | Operação de volume / pregão | P4+E |
| consultado=false | Não classificar como frio de mercado | Cobertura |
| Entrante novo no órgão | Alert watchlist | P2 |
| Estimado edital vs benchmark local | REVIEW preço | P3+E |

---

## 7. Claims policy (agency)

**Allowed**

- Ranking no período P com semântica CONTRATADO e fontes listadas.  
- Distinguir zero consultado vs não consultado.  
- Listar vincendos só com vigência válida.  
- Share AEC com versão do dicionário.  

**Forbidden**

- ESTIMADO como CONTRATADO.  
- “Sem licitações” para não consultado.  
- % de relicitação fabricada.  
- Parceria entre fornecedores do órgão sem prova.  
- Cobertura SC 95% a partir de ranking parcial.
