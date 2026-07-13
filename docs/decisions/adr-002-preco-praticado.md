# ADR-002: Preço Praticado — Semântica Multi-source de Valores

**Status:** Proposto (2026-07-12)
**Decision:** Abordagem multi-source para distinguir valor_estimado, valor_homologado, valor_contratado, valor_pago.
**Author:** Morgan (PM) / Dara (Data Engineer) — Synkra AIOX
**PRD:** `docs/prd/PRD-consultoria-extra.md` v2.0

---

## 1. Contexto

O PRD v2.0 define 4 momentos de valor em uma licitação:

| Termo | Definição | Fonte Atual | Status |
|-------|-----------|-------------|--------|
| **Valor Estimado** | Valor estimado da licitação, publicado no edital | PNCP (edital), DOM-SC | NOT_READY |
| **Valor Homologado** | Valor da proposta vencedora, homologado no resultado | PNCP (resultado), DOM-SC | NOT_READY |
| **Valor Contratado** | Valor global do contrato assinado | `pncp_supplier_contracts.valor_global` | DISPONIVEL |
| **Valor Pago** | Valor efetivamente empenhado/pago | Portais de transparência, TCE-SC | NOT_READY |

O campo `valor_global` atualmente disponível em `pncp_supplier_contracts` é o campo `valorGlobal` da API PNCP. Análise do ADR-001 (Contract Intelligence Truth v1) já documentava:

> "valor_global é o campo valorGlobal do PNCP. Não é preço praticado, não é valor homologado, não é deságio. Quando o PNCP não distingue as semânticas de valor, marcamos como 'valor_global — semântica não desambiguada pela origem' e bloqueamos métricas que dependem de semântica precisa de valor."

Precisamos de uma decisão arquitetônica para desambiguar esses 4 momentos de valor e viabilizar métricas como deságio, ticket médio real, e preço praticado por órgão.

## 2. Fontes Disponíveis

### 2.1 PNCP API — Contratos

- **Campo:** `valorGlobal`
- **Semântica:** Valor global do contrato assinado
- **Cobertura:** 404 entes com contratos (37% do universo confirmado)
- **Limitação:** Não distingue estimado vs homologado vs pago
- **Endpoint:** `/api/consulta/contratos`

### 2.2 PNCP API — Licitações (editais)

- **Campos disponíveis:** `valorEstimado` (em alguns endpoints de item)
- **Semântica:** Valor estimado da licitação
- **Cobertura:** Parcial — nem toda licitação publica valor estimado item a item
- **Limitação:** API pública não expõe valor homologado por item
- **Endpoint:** `/api/consulta/editais`

### 2.3 DOM-SC — Resultados de Licitação

- **Tipo:** HTML scraping (adapter pattern)
- **Semântica:** Resultados de licitação com valores homologados
- **Cobertura:** ~280 municípios SC
- **Potencial:** Fonte principal para deságio (estimado vs homologado) se o HTML estruturar valores de proposta
- **Risco:** HTML scraping frágil, mudanças de layout quebram parser

### 2.4 TCE-SC e-Sfinge — Empenhos

- **Tipo:** JSON API (SCMWeb)
- **Semântica:** Dados de execução financeira (valor efetivamente pago)
- **Cobertura:** 295 municípios SC (teoricamente)
- **Potencial:** Fonte para `valor_pago` e comparação contrato vs execução
- **Limitação:** Crawler TCE-SC existe mas tem desafios de acesso (ICP-Brasil mencionado no EPIC-COVERAGE-100PCT como inviável, mas crawler SCMWeb JSON API está ativo)

### 2.5 Portais de Transparência Municipais

- **Tipo:** Multi-plataforma (Betha, Ipam, E-gov, Fiorilli, etc.)
- **Semântica:** Dados de execução financeira (empenhos, pagamentos)
- **Cobertura:** Potencialmente 295 municípios
- **Potencial:** Fonte complementar para `valor_pago`
- **Risco:** 8+ plataformas diferentes, scraping complexo

## 3. Opções Consideradas

### Opção A: Single-source (PNCP apenas)

**Descrição:** Usar apenas PNCP, aceitar que `valor_global` é o único valor disponível.

**Prós:**
- Simples, sem integração cross-source
- Mantém stack atual
- Dados já disponíveis

**Contras:**
- Não resolve NOT_READY — deságio e preço praticado continuam indisponíveis
- `valor_global` não é preço praticado
- Perde oportunidade de diferenciar estimado vs homologado

**Veredito:** REJEITADA. Não atende requisito de negócio.

### Opção B: Multi-source com prioridade

**Descrição:** Combinar múltiplas fontes com regras de prioridade. Para cada contrato/licitação, buscar valor na melhor fonte disponível:

1. PNCP contratos → `valor_contratado` (default)
2. DOM-SC resultados → `valor_homologado` (quando disponível)
3. TCE-SC empenhos → `valor_pago` (quando disponível)
4. PNCP editais → `valor_estimado` (quando disponível)

**Prós:**
- Aproveita fontes já implementadas
- Cada fonte contribui com sua semântica específica
- Degradação graciosa: se uma fonte falha, as demais continuam
- Permite calcular deságio onde estimado + homologado estão disponíveis

**Contras:**
- Complexidade de matching cross-source (mesma licitação em fontes diferentes)
- Sincronia de dados entre fontes (DOM-SC pode publicar antes do PNCP)
- Necessidade de parser específico para cada fonte
- Cobertura depende da fonte mais fraca

**Veredito:** SELECIONADA.

### Opção C: Enriquecimento via LLM

**Descrição:** Usar LLM (GPT-4.1-nano) para extrair valores de documentos (editais em PDF, resultados em HTML) e classificar semântica.

**Prós:**
- Flexível para formatos não estruturados
- Pode extrair valores mesmo de HTML mal formatado
- LLM já está no pipeline (LLM gate)

**Contras:**
- Custo por licitação (cada parse gasta token)
- Latência (LLM é mais lento que parser estruturado)
- Risco de alucinação em valores numéricos
- Difícil de testar deterministicamente

**Veredito:** REJEITADA como fonte primária. Pode ser usada como fallback para casos onde parser estruturado falha, mas não como estratégia principal.

## 4. Decisão

**Adotar Opção B: Multi-source com prioridade.**

### Arquitetura

```
                    ┌──────────────────┐
                    │   Valor Estimado │ ← PNCP Editais (valorEstimado)
                    │                  │ ← DOM-SC (quando edital publicado)
                    └──────┬───────────┘
                           │
                    ┌──────▼───────────┐
                    │ Valor Homologado │ ← DOM-SC Resultados
                    │                  │ ← PNCP (se disponível)
                    └──────┬───────────┘
                           │
                    ┌──────▼───────────┐
                    │ Valor Contratado │ ← PNCP Contracts (valor_global)
                    │                  │   JÁ DISPONÍVEL
                    └──────┬───────────┘
                           │
                    ┌──────▼───────────┐
                    │    Valor Pago    │ ← TCE-SC Empenhos
                    │                  │ ← Portais Transparência
                    └──────────────────┘
```

### Regras de Prioridade

Para cada licitação/contrato:

1. **Valor Estimado**: PNCP API item (`valorEstimado`) > DOM-SC edital (quando parseável)
2. **Valor Homologado**: DOM-SC resultado > PNCP (se disponível)
3. **Valor Contratado**: `pncp_supplier_contracts.valor_global` (default, sempre disponível)
4. **Valor Pago**: TCE-SC empenho > Portal Transparência

### Matching Cross-source

O matching entre fontes é feito por:
1. **CNPJ do órgão** (todas as fontes têm)
2. **Número da licitação/contrato** (quando disponível)
3. **Objeto + valor aproximado** (fallback fuzzy)

### Tabela de Desambiguação

```sql
contract_values_disambiguated (
    id,
    source_contract_id,      -- FK pncp_supplier_contracts (se aplicável)
    source_bid_id,           -- FK pncp_raw_bids (se aplicável)
    orgao_cnpj,              -- CNPJ do órgão
    orgao_nome,              -- Nome do órgão
    cnpj_8,                  -- CNPJ 8 dígitos do órgão
    modalidade,              -- Modalidade da licitação
    objeto,                  -- Objeto resumido
    valor_estimado,          -- NUMERIC(18,2), nullable
    valor_homologado,        -- NUMERIC(18,2), nullable
    valor_contratado,        -- NUMERIC(18,2), nullable
    valor_pago,              -- NUMERIC(18,2), nullable
    fonte_estimado,          -- VARCHAR(50): 'pncp', 'dom-sc', NULL
    fonte_homologado,        -- VARCHAR(50)
    fonte_contratado,        -- VARCHAR(50)
    fonte_pago,              -- VARCHAR(50)
    data_publicacao,         -- Data do edital/resultado
    data_assinatura,         -- Data do contrato
    created_at
);
```

### Métricas Derivadas

- **Deságio**: `(valor_estimado - valor_homologado) / valor_estimado * 100`
  - Disponível apenas quando estimado + homologado não-nulos
  - Confiança ALTA se ambas as fontes são estruturadas
  - Confiança MÉDIA se uma fonte é estimativa

- **Execução vs Contrato**: `(valor_pago - valor_contratado) / valor_contratado * 100`
  - Disponível apenas quando pago + contratado não-nulos
  - Indica aditivos (positivo) ou economia (negativo)

- **Preço Praticado**: Média ponderada de `valor_homologado` por órgão/modalidade/objeto
  - Disponível apenas onde homologado está populado

## 5. Consequências

### Positivas

- Desbloqueia métrica de deságio (diferencial competitivo)
- Aproveita fontes já implementadas (PNCP, DOM-SC, TCE-SC)
- Degradação graciosa: métricas disponíveis parcialmente conforme dados existem
- Tabela de desambiguação permite rastrear origem de cada valor

### Negativas

- Complexidade operacional: matching cross-source entre PNCP, DOM-SC e TCE-SC
- Cobertura parcial até que todas as fontes estejam populadas
- DOM-SC scraping frágil — se DOM-SC quebrar, perde fonte de valor homologado
- Necessidade de manutenção de múltiplos parsers

### Neutras

- Tabela `contract_values_disambiguated` adiciona ~1-2 GB ao banco (estimado)
- Pipeline de desambiguação adiciona ~5-10 min ao crawl full

## 6. Implementação

1. **Story B2G-2**: Implementa schema, parser DOM-SC para valor homologado, view `v_preco_praticado`, CLI `precos`
2. **DOM-SC parser enhancement**: Adicionar extração de valor homologado ao DOM-SC crawler existente
3. **TCE-SC enhancement**: Se TCE-SC tiver dados de empenho, adicionar parser para `valor_pago`
4. **Pipeline de desambiguação**: Script `scripts/precos/pipeline.py` que popula `contract_values_disambiguated`

### Timeline

| Fase | Escopo | Previsão |
|------|--------|----------|
| 1 | Schema + PNCP valor_contratado | Week 1 (já disponível) |
| 2 | DOM-SC valor_homologado | Week 2 |
| 3 | Cálculo deságio + CLI | Week 3 |
| 4 | TCE-SC valor_pago | Week 4-5 |
| 5 | Portais Transparência valor_pago | Week 6+ |

## 7. Referências

- ADR-001: `docs/decisions/contract-intelligence-truth-v1.md` — Documenta limitação de `valor_global`
- PRD v2.0: `docs/prd/PRD-consultoria-extra.md` — Seção "Comercial Readiness"
- Story B2G-2: `docs/stories/epics/epic-master-b2g/story-B2G-2-preco-praticado.md`
- PNCP Swagger: `https://pncp.gov.br/api/consulta/swagger-ui/index.html`
