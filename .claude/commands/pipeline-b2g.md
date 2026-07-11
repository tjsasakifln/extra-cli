# /pipeline-b2g — Dashboard de Pipeline Comercial B2G

## Purpose

Consolida TODOS os leads de todos os setores em um pipeline comercial unificado com estagios, metricas de conversao, alertas de follow-up, e forecast de receita. A visao 360 do consultor sobre a operacao comercial.

**Output primario:** `docs/pipeline/pipeline-{YYYY-MM-DD}.xlsx` (planilha master)
**Output secundario:** `docs/pipeline/pipeline-{YYYY-MM-DD}.md` (dashboard markdown)

---

## Usage

```
/pipeline-b2g                                    # gera dashboard completo
/pipeline-b2g --update                           # atualiza pipeline existente com novos dados
/pipeline-b2g --setor medicamentos               # filtra por setor
/pipeline-b2g --estagio proposta                 # filtra por estagio
/pipeline-b2g --alerta                           # so mostra leads com alertas pendentes
/pipeline-b2g --forecast                         # foco no forecast de receita
```

## What It Does

### Phase 1: Consolidacao de Dados (@data-engineer)

1. **Varrer outputs existentes** — Buscar TODOS os arquivos em:
   - `docs/intel-b2g/leads-*.xlsx` (leads brutos)
   - `docs/intel-b2g/qualified-*.xlsx` (leads qualificados)
   - `docs/cadencias/cadencia-*.xlsx` (cadencias em execucao)
   - `docs/propostas/proposta-*.pdf` (propostas enviadas)
   - `docs/reports/report-*.pdf` (reports entregues)
   - `docs/pipeline/pipeline-*.xlsx` (pipeline anterior, se existir)

2. **Dedup por CNPJ** — Mesmo lead pode aparecer em multiplos setores. Manter o registro mais recente/completo. Preservar historico de interacoes.

3. **Enriquecer status** — Para cada lead, inferir estagio baseado nos artefatos encontrados:
   - Tem leads-*.xlsx? → "Mapeado"
   - Tem qualified-*.xlsx? → "Qualificado"
   - Tem cadencia-*.xlsx com status "Enviado"? → "Abordado"
   - Tem cadencia-*.xlsx com status "Respondeu"? → "Engajado"
   - Tem proposta-*.pdf? → "Proposta Enviada"
   - Tracking manual? → Ler notas

### Phase 2: Pipeline por Estagios (@analyst)

**7 estagios do funil comercial:**

```
MAPEADO → QUALIFICADO → ABORDADO → ENGAJADO → PROPOSTA → NEGOCIANDO → FECHADO
  [1]        [2]          [3]        [4]        [5]         [6]         [7]
                                                                     ↘ PERDIDO [X]
```

| Estagio | Definicao | Probabilidade de Fechamento |
|---------|-----------|:--:|
| **1. Mapeado** | Lead identificado pelo `/intel-b2g`, sem contato | 5% |
| **2. Qualificado** | Scoring feito pelo `/qualify-b2g`, tier atribuido | 10% |
| **3. Abordado** | Primeira mensagem enviada (D0 da cadencia) | 15% |
| **4. Engajado** | Lead respondeu positivamente (interesse demonstrado) | 30% |
| **5. Proposta** | Proposta comercial enviada (`/proposta-b2g`) | 50% |
| **6. Negociando** | Lead em negociacao ativa (pediu desconto, prazo, etc) | 75% |
| **7. Fechado** | Contrato assinado, pagamento confirmado | 100% |
| **X. Perdido** | Lead disse nao, sumiu, ou desqualificado | 0% |

### Phase 3: Metricas e KPIs (@analyst)

**Metricas de Volume:**
| Metrica | Calculo |
|---------|---------|
| Total de leads no pipeline | COUNT(todos os leads ativos) |
| Leads por estagio | COUNT por estagio |
| Leads por setor | COUNT por setor |
| Leads por tier | COUNT por tier (1/2/3) |
| Novos leads/semana | COUNT(mapeados esta semana) |
| Velocidade do pipeline | Media de dias entre estagios |

**Metricas de Conversao:**
| Transicao | Formula | Benchmark |
|-----------|---------|-----------|
| Mapeado → Qualificado | Qualificados / Mapeados | >80% (automatico) |
| Qualificado → Abordado | Abordados / Qualificados | >60% |
| Abordado → Engajado | Engajados / Abordados | 15-25% |
| Engajado → Proposta | Propostas / Engajados | 40-60% |
| Proposta → Fechado | Fechados / Propostas | 20-35% |
| **Overall: Mapeado → Fechado** | Fechados / Mapeados | 2-5% |

**Metricas de Receita:**
| Metrica | Calculo |
|---------|---------|
| MRR Atual | SUM(receita mensal dos fechados) |
| MRR Pipeline | SUM(valor_pacote × probabilidade por estagio) |
| MRR Forecast 30d | Pipeline ponderado dos estagios 4-6 |
| MRR Forecast 90d | Pipeline ponderado dos estagios 2-6 |
| Ticket Medio | MRR / Clientes fechados |
| Receita Perdida | SUM(valor dos leads perdidos) |

### Phase 4: Sistema de Alertas (@analyst)

**Alertas automaticos:**

| Alerta | Condicao | Urgencia |
|--------|----------|----------|
| **Follow-up atrasado** | Lead abordado ha >3 dias sem resposta e sem follow-up | ALTA |
| **Proposta sem retorno** | Proposta enviada ha >7 dias sem resposta | ALTA |
| **Lead esfriando** | Lead engajado sem interacao ha >14 dias | MEDIA |
| **Cadencia pausada** | Lead no meio da cadencia sem envio ha >2 dias | MEDIA |
| **Tier 1 nao abordado** | Lead Tier 1 qualificado ha >48h sem D0 | CRITICA |
| **Oportunidade expirando** | Edital relevante para lead engajado encerra em <5 dias | CRITICA |
| **Win rate caindo** | Taxa de conversao abaixo do benchmark por 2+ semanas | BAIXA |

### Phase 5: Geracao do Dashboard (@dev)

**Planilha Excel — 6 abas:**

#### Aba "Dashboard"
- Metricas de volume (cards visuais)
- Funil de conversao (percentuais por estagio)
- MRR atual + forecast
- Grafico: leads por estagio (barras horizontais)
- Grafico: MRR por mes (linha de tendencia)

#### Aba "Pipeline"
Tabela master com TODOS os leads:

| Coluna | Descricao |
|--------|-----------|
| CNPJ | CNPJ formatado |
| Empresa | Nome fantasia |
| Setor | Setor de atuacao |
| Decisor | Nome do decisor |
| Tier | 1/2/3/4 |
| Score | Score do qualify |
| Estagio | 1-7 ou X |
| Estagio Nome | Mapeado/Qualificado/.../Perdido |
| Prob. Fechamento | % por estagio |
| Pacote | Basico/Premium/Enterprise |
| Valor Mensal | R$ do pacote |
| Valor Ponderado | Valor × Probabilidade |
| Ultimo Contato | Data |
| Proximo Passo | Acao necessaria |
| Alerta | Flag de alerta (se houver) |
| Notas | Observacoes |

#### Aba "Alertas"
- Todos os alertas ativos ordenados por urgencia
- Acao recomendada para cada alerta
- Link para o lead no pipeline

#### Aba "Forecast"
- MRR projetado por mes (proximos 6 meses)
- Cenarios: conservador (50% do ponderado), base (100%), otimista (150%)
- Break-even analysis: "Precisa de {N} clientes {pacote} para cobrir custos"
- Meta vs realizado (se dados historicos disponiveis)

#### Aba "Conversao"
- Taxas de conversao por estagio
- Comparacao com benchmarks
- Gargalos identificados: "O maior drop-off esta em Abordado → Engajado (apenas {X}%)"
- Recomendacoes para melhorar cada transicao

#### Aba "Historico"
- Log de mudancas de estagio
- Leads perdidos com motivo (se disponivel)
- Timeline de atividades por lead

## Markdown Dashboard

O output `.md` gera um dashboard textual para visualizacao rapida:

```markdown
# Pipeline Comercial B2G — {data}

## Resumo
- **Leads ativos:** {N}
- **MRR atual:** R${valor}
- **MRR forecast 30d:** R${valor}
- **Alertas pendentes:** {N}

## Funil
Mapeado: {N} → Qualificado: {N} → Abordado: {N} → Engajado: {N} → Proposta: {N} → Negociando: {N} → Fechado: {N}

## Alertas Criticos
1. {alerta}
2. {alerta}

## Top 5 Leads (maior valor ponderado)
1. {empresa} — R${valor} — {estagio} — {proximo_passo}
```

## Downstream

```
/intel-b2g leads de {setor}              → alimenta estagio 1
/qualify-b2g {setor}                     → alimenta estagio 2
/cadencia-b2g {setor}                    → alimenta estagios 3-4
/proposta-b2g {CNPJ}                     → alimenta estagio 5
/pipeline-b2g                            → visao consolidada
/pipeline-b2g --alerta                   → acao imediata
/retention-b2g {CNPJ}                    → pos-fechamento (estagio 7+)
```

## Params

$ARGUMENTS
