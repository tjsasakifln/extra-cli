# /qualify-b2g — Qualificacao Inteligente de Leads B2G

## Purpose

Pega a planilha bruta do `/intel-b2g` e transforma em inteligencia acionavel: scoring multi-dimensional, tier ranking, e recomendacao de abordagem por lead. Separa ouro de cascalho.

**Input obrigatorio:** Planilha do `/intel-b2g` (`docs/intel-b2g/leads-{setor}-{data}.xlsx`) OU dados em memoria da sessao
**Output primario:** `docs/intel-b2g/qualified-{setor}-{data}.xlsx` (planilha qualificada)
**Output secundario:** `docs/intel-b2g/qualified-{setor}-{data}.md` (relatorio markdown)

---

## Usage

```
/qualify-b2g docs/intel-b2g/leads-medicamentos-2026-03-10.xlsx
/qualify-b2g medicamentos                    # usa ultimo arquivo do setor
/qualify-b2g medicamentos --tier 1           # so mostra Tier 1
/qualify-b2g medicamentos --min-score 70     # filtro por score minimo
```

## What It Does

### Phase 1: Carga e Validacao dos Dados (@data-engineer)

1. **Carregar planilha** — Ler aba "Leads" do Excel gerado pelo `/intel-b2g`
2. **Validar completude** — Checar campos criticos por lead:
   - CNPJ (obrigatorio)
   - Faturamento Gov Mensal (obrigatorio para scoring)
   - Decisor nome (importante para abordagem)
   - Telefone ou Email (minimo 1 canal de contato)
3. **Flag incompletude** — Leads com dados faltantes recebem penalidade no score, mas nao sao descartados

### Phase 2: Scoring Multi-Dimensional (@analyst)

Para CADA lead, calcular score em 7 dimensoes (0-100 cada):

#### D1. Volume Governamental (peso 25%)
Baseado no faturamento gov mensal calculado pelo `/intel-b2g`:
| Faturamento Gov Mensal | Score |
|------------------------|-------|
| > R$500k/mes | 100 |
| R$200k-500k/mes | 85 |
| R$100k-200k/mes | 70 |
| R$50k-100k/mes | 55 |
| R$20k-50k/mes | 40 |
| R$5k-20k/mes | 25 |
| < R$5k/mes | 10 |

#### D2. Frequencia de Participacao (peso 20%)
Quantos contratos PNCP nos ultimos 12 meses:
| Contratos/ano | Score | Interpretacao |
|---------------|-------|---------------|
| 20+ | 100 | Player pesado — ja tem estrutura |
| 10-19 | 85 | Ativo — participa regularmente |
| 5-9 | 70 | Moderado — potencial de crescimento |
| 3-4 | 55 | Iniciante ativo — precisa de ajuda |
| 1-2 | 40 | Esporadico — precisa ser convencido |
| 0 | 15 | Nunca participou (pode ser lead frio) |

#### D3. Porte e Capacidade (peso 15%)
Cruzamento de capital social + porte OpenCNPJ:
| Porte | Score |
|-------|-------|
| Medio/Grande + Capital > R$1M | 100 |
| Medio + Capital R$500k-1M | 80 |
| Pequeno + Capital R$100k-500k | 60 |
| MEI/Micro + Capital < R$100k | 30 |

#### D4. Acessibilidade do Decisor (peso 15%)
Qualidade do canal de contato disponivel:
| Canal | Score |
|-------|-------|
| Celular (WhatsApp flag) + Email + Decisor nomeado | 100 |
| Celular + Decisor nomeado | 85 |
| Email + Decisor nomeado | 70 |
| Celular sem decisor | 50 |
| So telefone fixo | 30 |
| Nenhum contato direto | 10 |

#### D5. Saude Juridica (peso 10%)
Baseado em sancoes do Portal da Transparencia:
| Situacao | Score |
|----------|-------|
| Zero sancoes + situacao ativa | 100 |
| Situacao ativa + historico de sancao resolvida | 70 |
| Sancao ativa (CEIS/CNEP) | 10 |
| Situacao cadastral irregular | 0 (DESQUALIFICA) |

#### D6. Diversificacao Geografica (peso 10%)
Numero de UFs onde a empresa tem contratos:
| UFs de atuacao | Score | Interpretacao |
|----------------|-------|---------------|
| 5+ UFs | 100 | Opera nacionalmente — escala |
| 3-4 UFs | 75 | Regional forte |
| 2 UFs | 50 | Expandindo |
| 1 UF | 30 | Local — menor escopo |

#### D7. Potencial de Upsell (peso 5%)
Indicadores de que a empresa pode comprar servicos adicionais:
| Indicador | Bonus |
|-----------|-------|
| Tem website profissional | +20 |
| Capital social > R$500k | +20 |
| CNAEs secundarios em setores adjacentes | +20 |
| Participa de modalidades complexas (Concorrencia, T+P) | +20 |
| Historico de contratos federais (Portal Transparencia) | +20 |

**Score Final = (D1×0.25) + (D2×0.20) + (D3×0.15) + (D4×0.15) + (D5×0.10) + (D6×0.10) + (D7×0.05)**

### Phase 3: Classificacao em Tiers (@analyst)

| Tier | Score | Cor | Acao Recomendada |
|------|-------|-----|------------------|
| **Tier 1 — Hot** | 75-100 | Verde | Abordar em 48h — alta probabilidade de conversao |
| **Tier 2 — Warm** | 50-74 | Amarelo | Abordar em 1 semana — nutrir antes de proposta |
| **Tier 3 — Cold** | 25-49 | Laranja | Incluir em cadencia automatizada — baixa prioridade |
| **Tier 4 — Descartado** | 0-24 | Vermelho | Nao abordar — ROI negativo |

### Phase 4: Recomendacao de Abordagem (@analyst)

Para cada Tier, gerar recomendacao especifica:

**Tier 1 (Hot):**
- Canal: WhatsApp direto para decisor
- Tom: Consultivo, "vi que voce participa de licitacoes de {setor}..."
- Oferta: Consultoria completa (R$1.500-3.000/mes)
- Urgencia: Alta — concorrentes podem abordar primeiro

**Tier 2 (Warm):**
- Canal: WhatsApp + Email follow-up
- Tom: Educativo, "muitas empresas do seu setor estao perdendo editais por..."
- Oferta: Diagnostico gratuito → Consultoria basica (R$1.500/mes)
- Urgencia: Media — nutrir por 7-14 dias

**Tier 3 (Cold):**
- Canal: Email cadencia automatizada
- Tom: Informativo, "compilamos X oportunidades no seu setor..."
- Oferta: Report gratuito → Trial Extra Consultoria → Upgrade
- Urgencia: Baixa — cadencia de 30 dias

### Phase 5: Identificacao de Low-Hanging Fruit (@analyst)

Alem do score, identificar padroes especiais:

1. **"Ganha mas nao otimiza"** — Empresa com 10+ contratos mas sem website/presenca digital. Sinal: ja participa ativamente mas nao usa tecnologia. Abordagem: "posso te mostrar como ganhar 30% mais editais com automacao"

2. **"Grande demais pra perder tempo"** — Empresa com faturamento gov > R$500k/mes e poucos contratos. Sinal: participa pouco dado o potencial. Abordagem: "sua empresa poderia estar em 3x mais editais sem aumentar equipe"

3. **"Crescendo rapido"** — Empresa com contratos recentes concentrados nos ultimos 3 meses. Sinal: acelerando participacao. Abordagem: "vi que voces estao expandindo em licitacoes — posso ajudar a escalar isso"

4. **"Multi-setor inexplorado"** — Empresa com CNAEs em 3+ setores mas contratos em apenas 1. Sinal: potencial cross-sell. Abordagem: "alem de {setor_atual}, tem X oportunidades abertas em {setor_adjacente}"

## Output Excel

A planilha `.xlsx` qualificada tem 4 abas:

| Aba | Conteudo |
|-----|----------|
| **Dashboard** | Distribuicao por tier (grafico), metricas agregadas, top 10 hot leads |
| **Leads Qualificados** | Todos os leads + 7 scores + tier + recomendacao + flag low-hanging |
| **Low-Hanging Fruit** | Apenas leads com padroes especiais identificados |
| **Metodologia** | Pesos, criterios, fontes, data de qualificacao |

**Colunas adicionais na aba "Leads Qualificados":**
- Score D1-D7 (cada dimensao)
- Score Final (ponderado)
- Tier (1/2/3/4)
- Recomendacao (texto curto)
- Canal Sugerido (WhatsApp/Email/Cadencia)
- Tom Sugerido (Consultivo/Educativo/Informativo)
- Oferta Sugerida (pacote + preco)
- Flag Low-Hanging (tipo ou vazio)
- Prioridade (1-N dentro do tier)

## Downstream

```
/intel-b2g leads de medicamentos         → 200 leads brutos
/qualify-b2g medicamentos                → 40 Tier1, 60 Tier2, 70 Tier3, 30 descartados
/cadencia-b2g medicamentos --tier 1      → cadencia WhatsApp para os 40 hot
/proposta-b2g {CNPJ_do_tier1}            → proposta comercial personalizada
```

## Params

$ARGUMENTS
