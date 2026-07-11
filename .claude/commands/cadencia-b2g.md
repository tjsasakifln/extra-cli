# /cadencia-b2g — Cadencia de Prospeccao B2G

## Purpose

Transforma leads qualificados em sequencias de abordagem prontas para executar. Gera mensagens personalizadas por lead, com timing exato, multi-canal (WhatsApp → Email → LinkedIn → Follow-up), e tracking integrado. O consultor so precisa copiar, colar, e enviar.

**Input:** Planilha do `/qualify-b2g` OU lista de CNPJs OU setor
**Output primario:** `docs/cadencias/cadencia-{setor}-{data}.xlsx` (planilha executavel)
**Output secundario:** `docs/cadencias/cadencia-{setor}-{data}.md` (calendario markdown)

---

## Usage

```
/cadencia-b2g medicamentos                           # todos os tiers do setor
/cadencia-b2g medicamentos --tier 1                  # so Tier 1 (hot)
/cadencia-b2g medicamentos --tier 1,2                # Tier 1 e 2
/cadencia-b2g 12345678000190,98765432000199          # CNPJs especificos
/cadencia-b2g medicamentos --inicio 2026-03-15       # define data de inicio
/cadencia-b2g medicamentos --dias 21                 # cadencia de 21 dias (padrao: 14)
```

## What It Does

### Phase 1: Carga dos Leads (@data-engineer)

1. **Se setor informado** — Buscar ultimo arquivo `/qualify-b2g` do setor em `docs/intel-b2g/qualified-{setor}-*.xlsx`
   - Se nao existir, buscar `/intel-b2g` bruto e avisar: "Leads nao qualificados — recomendo rodar /qualify-b2g primeiro"
2. **Se CNPJs informados** — Buscar dados de cada CNPJ via OpenCNPJ (enriquecimento rapido)
3. **Filtrar por tier** se `--tier` informado
4. **Ordenar por prioridade** — Score desc dentro de cada tier

### Phase 2: Desenho da Cadencia (@analyst)

**Cadencia padrao: 14 dias, 7 touchpoints, 3 canais**

| Dia | Canal | Tipo | Objetivo |
|-----|-------|------|----------|
| **D0** | WhatsApp | Abertura | Primeiro contato — personalizado, curto, gerar curiosidade |
| **D1** | Email | Valor | Enviar mini-report com 3 oportunidades abertas do setor do lead |
| **D3** | WhatsApp | Follow-up | "Viu o email? Achei {N} editais que podem interessar" |
| **D5** | LinkedIn | Conexao | Adicionar decisor + nota personalizada (se perfil encontrado) |
| **D7** | Email | Caso | Case de sucesso / ROI de empresa similar do setor |
| **D10** | WhatsApp | Urgencia | "Edital de R${valor} encerra em {X} dias — quer que eu analise?" |
| **D14** | Email | Ultima | "Ultimo contato — fico a disposicao quando fizer sentido" |

**Variantes por Tier:**

| Tier | Cadencia | Tom | Touchpoints |
|------|----------|-----|-------------|
| **Tier 1** | 14 dias | Consultivo + Urgencia | 7 (completa) |
| **Tier 2** | 21 dias | Educativo + Valor | 5 (sem D5 LinkedIn, sem D10 urgencia) |
| **Tier 3** | 30 dias | Informativo | 3 (D0 email, D14 email, D30 email) |

### Phase 3: Personalizacao por Lead (@analyst)

Para CADA lead, personalizar CADA mensagem usando dados reais:

**Variaveis de personalizacao:**
- `{nome_decisor}` — Nome do socio-administrador (QSA)
- `{nome_fantasia}` — Nome fantasia da empresa
- `{setor}` — Setor de atuacao
- `{cidade}` — Cidade sede
- `{n_contratos}` — Contratos PNCP nos ultimos 12 meses
- `{faturamento_gov}` — Faturamento gov mensal formatado
- `{n_oportunidades}` — Editais abertos AGORA no setor
- `{valor_oportunidades}` — Valor total dos editais abertos
- `{edital_destaque}` — O edital mais relevante para este lead (objeto resumido + valor)
- `{orgao_top}` — Orgao com mais contratos deste lead
- `{ufs_atuacao}` — UFs onde o lead ja atua

**Templates por touchpoint:**

#### D0 — WhatsApp Abertura
```
Oi {nome_decisor}, tudo bem? Me chamo Tiago, trabalho com inteligencia em licitacoes.

Vi que a {nome_fantasia} atua no setor de {setor} em {cidade}. Identifiquei {n_oportunidades} editais abertos agora que podem ser relevantes pra voces.

Posso te mandar um resumo rapido?
```
- Max 3 paragrafos, max 280 caracteres no primeiro
- Sem mencionar Extra Consultoria
- Tom: pessoal, direto, sem floreio

#### D1 — Email Valor
```
Assunto: {n_oportunidades} oportunidades abertas em {setor} — {nome_fantasia}

{nome_decisor},

Trabalho com monitoramento de licitacoes e identifiquei oportunidades que podem interessar a {nome_fantasia}:

1. {edital_1_orgao} — {edital_1_objeto_resumido} — R${valor} — Encerra {data}
2. {edital_2_orgao} — {edital_2_objeto_resumido} — R${valor} — Encerra {data}
3. {edital_3_orgao} — {edital_3_objeto_resumido} — R${valor} — Encerra {data}

Sao {n_oportunidades} editais totalizando R${valor_total} so neste mes.

Se quiser, posso preparar uma analise mais detalhada sem custo.

Abs,
Tiago Sasaki
Consultor de Licitacoes
(48)9 8834-4559
```

#### D3 — WhatsApp Follow-up
```
{nome_decisor}, enviei um email ontem com {n_oportunidades} oportunidades do setor de {setor}.

Destaque: {edital_destaque} — R${valor} — encerra em {dias} dias.

Quer que eu analise a viabilidade desse pra {nome_fantasia}?
```

#### D5 — LinkedIn (nota de conexao)
```
{nome_decisor}, acompanho o setor de {setor} em licitacoes publicas. Vi que a {nome_fantasia} tem presenca forte em {ufs_atuacao}. Gostaria de conectar para trocar ideias sobre oportunidades no setor.
```
- Max 300 caracteres (limite LinkedIn)

#### D7 — Email Caso
```
Assunto: Como empresas de {setor} estao ganhando mais editais em 2026

{nome_decisor},

Empresas do setor de {setor} com perfil similar ao da {nome_fantasia} estao, em media, participando de {media_setorial} editais/mes.

Com monitoramento inteligente de fontes como PNCP, Portal de Compras e ComprasGov, consigo:
- Mapear TODOS os editais relevantes em tempo real
- Analisar viabilidade antes de voce investir tempo na proposta
- Alertar sobre prazos criticos

Uma empresa de {cidade_exemplo} no mesmo setor aumentou a taxa de participacao em 40% com esse tipo de suporte.

Posso te mostrar como isso funcionaria para a {nome_fantasia}?

Abs,
Tiago Sasaki
(48)9 8834-4559
```

#### D10 — WhatsApp Urgencia
```
{nome_decisor}, edital de {edital_urgente_orgao} no valor de R${valor} encerra em {dias} dias.

Objeto: {objeto_resumido}

Analisei e a aderencia ao perfil da {nome_fantasia} e alta. Quer que eu prepare um brief da oportunidade?
```

#### D14 — Email Ultima
```
Assunto: Ultimo contato — oportunidades em {setor}

{nome_decisor},

Sei que o dia a dia e corrido. Vou parar de enviar mensagens, mas fico a disposicao caso no futuro precise de:

- Monitoramento de editais do seu setor
- Analise de viabilidade de licitacoes especificas
- Relatorio de oportunidades sob demanda

Meu WhatsApp: (48)9 8834-4559

Sucesso nas proximas licitacoes!

Tiago Sasaki
```

### Phase 4: Geracao da Planilha (@dev)

**Aba "Calendario" (aba principal):**

| Coluna | Descricao |
|--------|-----------|
| Lead | Nome fantasia |
| CNPJ | CNPJ formatado |
| Decisor | Nome do decisor |
| Tier | 1/2/3 |
| Score | Score do qualify |
| Touchpoint | D0/D1/D3/D5/D7/D10/D14 |
| Data Prevista | Data calculada a partir do inicio |
| Canal | WhatsApp/Email/LinkedIn |
| Mensagem | Texto completo personalizado (copiar e colar) |
| Link wa.me | Link clicavel (apenas WhatsApp) |
| Status | Pendente/Enviado/Respondeu/Ignorou |
| Data Enviado | (manual) |
| Resposta | (manual) |
| Notas | (manual) |

**Aba "Resumo":**
- Total de leads na cadencia
- Distribuicao por tier
- Total de touchpoints programados
- Calendario: semana 1, semana 2 (quantos envios por dia)
- Metricas-alvo: open rate esperado, reply rate esperado

**Aba "Templates":**
- Todos os templates com variaveis explicadas
- Versao editavel para o consultor customizar

**Aba "LinkedIn Targets":**
- Leads com perfil LinkedIn provavel (nome decisor + empresa)
- URL de busca LinkedIn sugerida: `linkedin.com/search/results/people/?keywords={nome}+{empresa}`
- Nota de conexao personalizada

## Regras de Ouro

1. **NUNCA mencionar Extra Consultoria** nas mensagens — o consultor e "Tiago Sasaki, consultor independente"
2. **NUNCA soar como template** — cada mensagem deve parecer escrita manualmente
3. **Dados reais obrigatorios** — toda mensagem deve conter pelo menos 1 dado real (edital, valor, orgao)
4. **WhatsApp curto** — max 3 paragrafos, tom de conversa, sem formalidades excessivas
5. **Email estruturado** — assunto com gancho numerico, corpo com bullet points, CTA claro
6. **Respeitar LGPD** — dados usados sao todos publicos (PNCP, OpenCNPJ, Portal da Transparencia)
7. **Opt-out facil** — ultima mensagem (D14) e de encerramento gracioso

## Downstream

```
/intel-b2g leads de engenharia           → 150 leads
/qualify-b2g engenharia                  → 35 Tier1, 50 Tier2
/cadencia-b2g engenharia --tier 1        → cadencia 14 dias para 35 leads
/proposta-b2g {CNPJ}                     → proposta para leads que responderam
/pipeline-b2g                            → dashboard de pipeline comercial
```

## Params

$ARGUMENTS
