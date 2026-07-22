# Product Catalog — Market & Competitive Intelligence

**Campaign:** `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Audience:** Extra Consultoria (direção comercial + analistas)  
**As-of design:** 2026-07-22  
**Primary fact table:** `pncp_supplier_contracts`  
**Supporting layers:** `v_supplier_winners`, `v_contract_historical`, `v_expiring_contracts`, `v_contracts_canonical`, deliverables A–E, `scripts/contract_intel`, `scripts/buyer_intel`, `scripts/opportunity_intel`, `consulting_readiness` competitive block  

---

## Epistemic labels (obrigatório em todo produto)

| Label | Meaning | Client-facing language |
|-------|---------|------------------------|
| **FACT** | Observável no registro (campo presente, chave, valor, data, CNPJ) | "constatado no PNCP/DataLake" |
| **INDICATOR** | Agregação/derivação matemática sobre FACTS com fórmula explícita | "indicador calculado" |
| **INFERENCE** | Hipótese de negócio; nunca como certeza sem prova | "hipótese / sinal / indício" |
| **NOT_READY** | Métrica desejada sem dados de suporte | "indisponível nesta base" |

**Regras de ouro**

1. Parceria / consórcio / subcontratação → **FACT só com campo de prova**; senão **proibido**.
2. Similaridade de texto em `objeto_contrato` ≠ equivalência técnica.
3. Volume nacional de linhas ≠ cobertura SC / raio 200 km.
4. Preferir reutilizar deliverables A–E + CLIs existentes a novas plataformas.

---

## Priorização (P0 = entrega consultiva imediata)

| Pri | ID | Produto | Persona principal | Recorte padrão | Maturidade de dados |
|-----|----|---------|-------------------|----------------|---------------------|
| P0 | P1 | Mapa de concorrentes observáveis | Direção / BD | SC + raio 200 km (extensível nacional) | Alta (deliverable B + `v_supplier_winners`) |
| P0 | P2 | Radar de entrantes e recorrentes | Comercial | Janelas temporais + órgão/UF | Média (fatos de 1º contrato; classificação INFERENCE) |
| P0 | P3 | Benchmarks de valor (comparáveis) | Precificação / propostas | Dimensões do deliverable D | Média (exige comparabilidade) |
| P0 | P4 | Inteligência de órgãos contratantes | BD / pré-venda | Órgãos SC / 200 km | Alta (deliverable A + buyer_intel) |
| P1 | P5 | Sinais de parceiros potenciais (não “parcerias”) | Estratégia | Coocorrência em órgãos/objetos | Baixa–média (só sinais) |
| P1 | P6 | Expansão geográfica / de objeto | Planejamento | SC vs nacional / categorias | Média |
| P1 | P7 | Concentração de mercado (HHI / award share) | Estratégia | Por órgão / mercado filtrado | Alta (ADR-016 + consulting_readiness) |
| P1 | P8 | SC vs Nacional (dual lens) | Direção | Dois universos explícitos | Alta se recortes isolados |
| P2 | P9 | Relatório executivo unificado | Tiago / cliente | Pacote A–E + metas | Alta (package final) |

---

## P1 — Mapa de concorrentes observáveis

**Pergunta de negócio:** Quem são os fornecedores com histórico de contratos no universo-alvo, e o que é defensável dizer sobre eles?

| Camada | Conteúdo |
|--------|----------|
| **FACT** | `fornecedor_cnpj`, `fornecedor_nome`, `contrato_id`, `orgao_cnpj`, `valor_total`/`valor_global`, `data_inicio`/`data_fim`, `uf`, `objeto_contrato`, `is_active` |
| **INDICATOR** | `n_contratos`, `valor_contratado_total`, ticket médio (`valor/n`), # órgãos distintos, distribuição UF, HHI *intra-fornecedor* (concentração de receita por órgão) |
| **INFERENCE** | “capacidade operacional”, “especialização em X”, “ameaça competitiva” |
| **NOT_READY** | win rate, lista de perdedores, deságio sem par estimado+homologado no mesmo certame/lote/item |

**Fontes de reuso**

- `scripts/ops/deliverable_b_competitors.py` (seleção top-N sem padding)
- `v_supplier_winners` / `scripts/contract_intel/cli.py competitor_winners`
- `consulting_readiness._compute_market_share` / supplier ranking

**Decisões suportadas:** shortlist de 10–15 nomes para brief comercial; priorizar monitoramento; não afirmar “somos nº1 do mercado SC” sem recorte e semântica de valor.

**Saída:** ranking tabulado + claims_allowed/forbidden + regra de seleção versionada.

---

## P2 — Radar de entrantes e recorrentes

**Pergunta de negócio:** Quem apareceu recentemente como contratado no recorte, e quem é recorrente nos mesmos órgãos?

| Camada | Conteúdo |
|--------|----------|
| **FACT** | Primeira e última `data_inicio`/`data_publicacao` por `fornecedor_cnpj` no recorte; órgãos onde venceu |
| **INDICATOR** | `meses_desde_primeira_aparicao`, `contratos_ultimos_12m`, taxa de recorrência em órgão (contratos ≥2 no mesmo `orgao_cnpj`) |
| **INFERENCE** | “entrante agressivo”, “migrante de outra UF”, “especialista em renovação” |
| **NOT_READY** | intenção estratégica do entrante; se foi subcontratado de outrem |

**Definições operacionais (fixas)**

- **Entrante (INDICATOR class):** primeiro contrato no universo/recorte nos últimos N meses (default 12), com ≥1 contrato FACT.
- **Recorrente:** ≥K contratos no mesmo órgão em janela W (default K=2, W=36m).
- **Não confundir** com “novo no Brasil”: pode ser nacional antigo e entrante só em SC.

**Decisões:** alerta comercial; watchlist; cruzar com editais abertos (P9/E).

---

## P3 — Benchmarks de valor (comparáveis)

**Pergunta de negócio:** Qual faixa de valor contratado/estimado/homologado é defensável para objetos comparáveis?

| Camada | Conteúdo |
|--------|----------|
| **FACT** | Observações unitárias com semântica de valor explícita (`contratado` = `valor_total` PNCP; estimado/homologado de bids quando houver par) |
| **INDICATOR** | n, mediana, p25, p75, min, max, evolução por período; flags de outlier (IQR) |
| **INFERENCE** | “preço de mercado justo”, “desconto esperado” |
| **Proibido** | “preço real praticado” em globais heterogêneos; misturar semânticas |

**Reuso:** `deliverable_d_prices.py` (dimensões: tipo, unidade, lote, porte, região, período).  
**Gate:** `INSUFFICIENT_SAMPLE` se n < threshold (default 5).  
Ver `benchmarks/questions.md`.

---

## P4 — Inteligência de órgãos contratantes

**Pergunta de negócio:** Quais órgãos mais contratam no perfil da Extra, com que frequência, ticket e fornecedores dominantes?

| Camada | Conteúdo |
|--------|----------|
| **FACT** | `orgao_cnpj`, `orgao_nome`, contratos, valores, modalidades (quando houver), vigências |
| **INDICATOR** | ranking por valor/qtd, ticket médio, frequência temporal, HHI de fornecedores no órgão, share AEC por regex de objeto (buyer_intel) |
| **INFERENCE** | “órgão fácil”, “capturado por fornecedor X”, “vai relançar” |
| **Cuidado** | ranking enviesado por qualidade de dados (`data_quality_limitation`); zero ≠ não consultado |

**Reuso:** `deliverable_a_org_ranking.py`, `scripts/buyer_intel/*`, `v_expiring_contracts` / deliverable C.  
Ver `agencies/questions.md`.

---

## P5 — Sinais de parceiros potenciais (não “mapa de parcerias”)

**Pergunta de negócio:** Quem *poderia* complementar capacidade em objetos/órgãos adjacentes — **sem** afirmar parceria existente?

| Camada | Conteúdo |
|--------|----------|
| **FACT** | Fornecedores distintos com contratos em mesmo órgão; sobreposição de órgãos; categorias de objeto (texto) |
| **INDICATOR** | Jaccard de órgãos atendidos; coocorrência temporal (mesmo trimestre no mesmo órgão) |
| **INFERENCE** | “candidato a consórcio”, “possível subcontratado histórico”, “rede” |
| **PROIBIDO como FACT** | “são parceiros”, “formam consórcio”, “X subcontrata Y” sem campo de prova em edital/contrato |

**Dados de prova ausentes hoje:** não há coluna de consórcio/subcontratação em `pncp_supplier_contracts`.  
**Produto honestamente rotulado:** “radar de adjacência / coocorrência”, nunca “parcerias comprovadas”.

---

## P6 — Expansão geográfica e de objeto

**Pergunta de negócio:** Onde há volume contratado alinhado ao perfil Extra fora do core SC/200 km, e em quais famílias de objeto?

| Camada | Conteúdo |
|--------|----------|
| **FACT** | Contagens e somas por `uf`, `municipio`, `codigo_municipio_ibge`, buckets de objeto (keywords versionadas) |
| **INDICATOR** | CAGR de valor por UF (se série temporal completa), share UF, densidade de órgãos com ≥1 contrato no perfil |
| **INFERENCE** | “mercado endereçável”, “prioridade de abertura de filial” |
| **Limitação** | Série nacional incompleta ≠ ausência de mercado; `municipio_inferido=TRUE` degrada confiança geográfica |

**Decisões:** roadmap de cobertura de fontes; não “vamos para UF X porque volume nacional é alto” sem recorte de objeto e qualidade.

---

## P7 — Concentração de mercado

**Pergunta de negócio:** O quão concentrado está o valor contratado entre fornecedores (global e por órgão)?

| Camada | Conteúdo |
|--------|----------|
| **FACT** | Contratos e valores por fornecedor no universo filtrado |
| **INDICATOR** | Market share (valor_i / valor_total), award share (#contratos), HHI = Σ(share%²) |
| **INFERENCE** | “monopólio de fato”, “barreira de entrada” |
| **NOT_READY** | win rate (ADR-016: sem participantes perdedores) |

**Reuso:** ADR-016, `competitive_intel_validation.py`, `consulting_readiness` competitive block.  
**Classificação HHI:** documentar escala usada (código atual vs DOJ) e não misturar escalas.

---

## P8 — SC vs Nacional (dual lens)

**Pergunta de negócio:** O que muda se olharmos só SC/raio 200 km versus base nacional PNCP disponível?

| Camada | Conteúdo |
|--------|----------|
| **FACT** | Dois recortes com filtros explícitos (`uf='SC'`, `sc_public_entities.raio_200km`, vs sem filtro geográfico) |
| **INDICATOR** | Top fornecedores em cada lente; overlap %; valores e n |
| **INFERENCE** | “concorrente nacional irrelevante em SC” |
| **Proibido** | Usar volume nacional como proxy de cobertura SC; selo “95% SC” a partir de contagem nacional |

**Produto:** painel lado a lado + disclaimer de cobertura. Alimenta P1/P6/P9.

---

## P9 — Relatório executivo unificado

**Pergunta de negócio:** O que entregar em reunião com narrativa única, números reconciliáveis e limitações explícitas?

| Camada | Conteúdo |
|--------|----------|
| **FACT/INDICATOR** | Apenas o que passou nos deliverables A–E + P7/P8 com mesmo `run_id`, cut date, profile |
| **INFERENCE** | Seção “implicações” claramente marcada |
| **Gate humano** | Aceite Tiago (package final) |

**Reuso:** `deliverable_package_final.py` (PDF+Excel same-run, seções obrigatórias, claims reconciliáveis).

---

## Mapa produto → dados mínimos

| Produto | Tabelas/views | Colunas críticas | CLI / script |
|---------|---------------|------------------|--------------|
| P1 | `pncp_supplier_contracts`, `v_supplier_winners` | fornecedor_*, orgao_*, valor_total, data_*, uf | deliverable_b, contract_intel |
| P2 | contracts | fornecedor_cnpj, data_inicio, orgao_cnpj | agregação SQL / extensão B |
| P3 | contracts + bids (pares) | valor + semântica + dimensões | deliverable_d |
| P4 | contracts + `sc_public_entities` | orgao_*, valor, objeto | deliverable_a, buyer_intel |
| P5 | contracts | orgao × fornecedor | novo *query product* sobre fatos existentes |
| P6 | contracts | uf, municipio, objeto, ibge | SQL + relatórios |
| P7 | contracts / `v_contracts_canonical` | fornecedor, valor | consulting_readiness, competitive_intel_validation |
| P8 | contracts + entities flags | uf, raio_200km | dual filter reports |
| P9 | outputs A–E | run_id meta | deliverable_package_final |

---

## Ordem de construção recomendada (sem nova plataforma)

1. **Congelar recortes** SC / 200 km / nacional (P8) como parâmetros de todos os produtos.  
2. **P1 + P4 + P7** a partir de B, A, HHI existentes.  
3. **P3** com gate de comparabilidade (D).  
4. **P2** como extensão temporal de P1.  
5. **P5** só com rótulo de sinal.  
6. **P6** com série e gaps de cobertura honestos.  
7. **P9** empacota tudo com package final.

---

## Non-goals deste catálogo

- Implementar código ou backfill nacional.  
- Substituir análise jurídica de edital.  
- Afirmar parcerias/consórcios/subcontratos sem prova.  
- Tratar win rate como disponível.  
- Usar similaridade textual como prova de mesmo serviço técnico.
