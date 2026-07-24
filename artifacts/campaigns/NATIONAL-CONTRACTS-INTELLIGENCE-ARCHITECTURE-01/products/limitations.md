# Data Limitations — Market & Competitive Intelligence Products

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Applies to:** products P1–P9 under `products/`  
**Schema anchor:** `pncp_supplier_contracts` (+ views de contract_intel / canonical)

Este documento é **normativo** para linguagem de produto e relatórios. Violações = claims_forbidden.

---

## 1. What the core table is (and is not)

### 1.1 Columns available (FACT layer)

| Column | Role | Caveat |
|--------|------|--------|
| `contrato_id` | Identity / dedup | Unique; upsert ON CONFLICT |
| `orgao_cnpj`, `orgao_nome` | Contracting body | Nome pode variar; usar CNPJ |
| `fornecedor_cnpj`, `fornecedor_nome` | Supplier on contract | Filial vs matriz; nome sujo |
| `objeto_contrato` | Free text object | **Not** technical equivalence key |
| `valor_total` | Contracted amount | **Not** unit price; **not** “preço praticado” |
| `data_inicio`, `data_fim`, `data_publicacao` | Dates | Fim pode faltar; aditivos podem não estar modelados na linha |
| `uf`, `municipio` | Geography | May not equal work site |
| `codigo_municipio_ibge` | IBGE code | Backfill quality varies |
| `municipio_inferido` | Quality flag | TRUE → lower geo confidence |
| `source`, `source_id` | Provenance | Mostly `pncp` |
| `ingested_at`, `is_active` | Pipeline | `is_active` ≠ “contrato juridicamente vigente” |
| `orgao_cnpj_8`, `fornecedor_cnpj_8` | Generated base-8 | For joins to entities |

### 1.2 Not in this table (common false assumptions)

| Desired field | Status | Product impact |
|---------------|--------|----------------|
| Participantes / perdedores da licitação | **Absent** | Win rate **NOT_READY** |
| Posição / deságio no certame | **Absent** unless joined to bid outcomes | Deságio só com par validado |
| Consórcio (membros) | **Absent** | Proibido afirmar consórcio |
| Subcontratação | **Absent** | Proibido afirmar subcontrato |
| Parceria comercial entre empresas | **Absent** | Só coocorrência = sinal |
| Preço unitário / quantitativos | **Absent** na linha global | Benchmark unitário NOT_READY |
| CNAE / capital social do fornecedor | **Not** here (other tables may partial) | Capacidade = hipótese |
| Modalidade sempre preenchida | Often via other entities | A-Q7 may be incomplete |
| Status jurídico de vigência + as_of | Not first-class on all rows | Active claim fail-closed (B/C) |

---

## 2. Partnership / consortium / subcontract — absolute rules

### 2.1 Forbidden without proof fields

Never publish as FACT or client headline:

- “X e Y são parceiros”
- “X e Y formam consórcio”
- “X subcontrata Y” / “Y é braço de X”
- “Grupo econômico” (sem QSA/quadro societário de fonte oficial)

### 2.2 What *is* allowed

| Statement | Label | Basis |
|-----------|-------|-------|
| “X e Y ambos têm contratos com o órgão O no período P” | FACT | Dois conjuntos de contratos |
| “Sobreposição de órgãos atendidos = J%” | INDICATOR | Jaccard etc. |
| “Sinal de adjacência / possível complementaridade” | INFERENCE | Explicit hypothesis |
| “Edital E permite consórcio (texto do edital)” | FACT | Campo/anexo do edital, não da tabela de contratos |
| “Empresa pediu consórcio por regra 10× capital” | INFERENCE/process | Regra de negócio Extra em domínio Reversa — não prova de consórcio histórico |

### 2.3 Proof bar (when future data exists)

Consórcio/subcontrato só vira FACT se existir **ao menos um**:

- Campo estruturado na fonte oficial (PNCP/edital/contrato) listando membros; ou  
- Documento oficial linkado com extrato auditável; ou  
- Tabela de participação com tipo de vínculo ∈ {CONSORCIO, SUBCONTRATO, …} preenchido na ingestão.

Até lá: produto P5 permanece **radar de coocorrência**, não mapa de parcerias.

---

## 3. Text similarity ≠ technical equivalence

| Use of `objeto_contrato` | Allowed? |
|--------------------------|----------|
| Busca / filtros / buckets keyword versionados | Sim, como **INDICATOR fraco** |
| Contar frequência de menções a “pavimentação” | Sim |
| Afirmar mesmo serviço técnico / mesmo escopo / mesmo padrão de qualidade | **Não** |
| Unir para mediana de “preço unitário” sem unidade e quantitativo | **Não** |
| Substituir engenharia de edital | **Não** |

Similarity scores (trigram, embedding) são **INFERENCE aids** para triagem, nunca prova de comparabilidade D.

---

## 4. National volume ≠ SC coverage

| Claim | Verdict |
|-------|---------|
| “Temos 2M+ linhas nacionais, logo SC está coberto” | **False** |
| “Volume nacional descreve o mercado SC da Extra” | **False** without dual lens filter |
| “Contagem de contratos SC no DataLake = universo de licitações SC” | **False** (cobertura de fonte incompleta) |
| “Dois rankings: SC/200km vs nacional disponível” | **True** product pattern (P8) |
| Selos LOCAL_READY / 95% / VPS sem evidência de gate | **Forbidden** (project DOD/Agents) |

---

## 5. Value semantics traps

| Mistake | Correction |
|---------|------------|
| Chamar `valor_total` de preço praticado unitário | Semântica **CONTRATADO** total |
| Somar estimado + contratado | Separar painéis |
| Ticket médio sem fórmula | Sempre `total/n` com n>0 |
| Mediana com n=2 como “mercado” | `INSUFFICIENT_SAMPLE` |
| Deságio de totais de contratos diferentes | `INSUFFICIENT_PAIR` |

---

## 6. Temporal & lifecycle traps

| Issue | Impact |
|-------|--------|
| `data_fim` NULL | Excluir de expiring; não inventar fim |
| Aditivos estendem vigência | Base table may lag; C tenta amendments quando fornecidos |
| `is_active` pipeline | Soft-delete/ingest flag ≠ vigência |
| Backfill parcial | Falso “entrante”; série temporal furada |
| Janela 3y da view histórica | Fora da janela ≠ inexistência |

---

## 7. Identity traps

| Issue | Mitigation |
|-------|------------|
| Mesmo grupo com vários CNPJ14 | Preferir análise por `fornecedor_cnpj_8` **só** se regra documentada; senão listar CNPJs |
| Nome fantasia vs razão | Ranking por CNPJ |
| Órgão secretaria vs prefeitura | Não colapsar sem hierarquia `entity_hierarchy` |
| Fornecedor sem CNPJ | Deliverable B `require_cnpj=true` dropa |

---

## 8. Competitive metrics readiness

| Metric | Status | Reason |
|--------|--------|--------|
| Market share (valor) | INDICATOR ready | Contratos com valor |
| Award share (contagem) | INDICATOR ready | Contratos |
| HHI | INDICATOR ready | ADR-016; declarar escala |
| Supplier ranking | INDICATOR ready | B / v_supplier_winners |
| Win rate | **NOT_READY** | Sem perdedores |
| Capacity | **HYPOTHESIS** | Sem evidência operacional |
| Partnership graph as fact | **NOT_READY** | Sem proof fields |
| Unit price benchmark | Conditional | Só com unidade+comparabilidade D |

---

## 9. Coverage & sampling bias

1. Ranking de órgãos favorece entes com melhor ingestão (`data_quality_limitation`).  
2. Regex AEC pode enviesar “fit” comercial.  
3. Universo 200 km exclui sem coordenadas (flag; nunca incluir silenciosamente).  
4. Fontes não-PNCP / portais locais podem faltar → dual capability coverage é outro problema.  
5. Job skipped ou ausência de run ≠ sucesso de cobertura.

---

## 10. Product language cheat-sheet

| Prefer | Avoid |
|--------|--------|
| “Vencedores históricos com contrato no recorte R” | “Todos os concorrentes do mercado” |
| “Valor contratado (PNCP)” | “Preço real praticado” |
| “Indicador de concentração (HHI)” | “Monopólio ilegal” |
| “Sinal de coocorrência” | “Parceiros” |
| “INSUFFICIENT_SAMPLE / NOT_READY” | Preencher com chute |
| “Hipótese de capacidade” | “Capacidade instalada de X” |
| “Recorte SC filtrado” | “Brasil como proxy de SC” |

---

## 11. Residual risks for executive report (P9)

- Completude de backfill nacional em andamento em **outro** processo/DB não prova estado deste worktree.  
- Package final exige mesmo `run_id` e aceite humano Tiago.  
- Recomendações de edital (E) não substituem jurídico/contábil/técnico e não prometem vitória.

---

## 12. Change control

Qualquer novo claim de parceria, win rate, preço unitário ou cobertura % exige:

1. Campo/fonte de prova identificado;  
2. Atualização deste `limitations.md`;  
3. Atualização de claims_allowed/forbidden nos deliverables reutilizados;  
4. Teste/gate que falhe se o claim for emitido sem prova.
