# /turbocash — Revenue & Monetization Advisory Board

**Squad:** `squad-revenue-advisory-board`
**Workflow:** `revenue-advisory-deliberation.yaml`
**Mode:** Advisory (read-only, never modifies code)

## Activation

```
/turbocash <sua pergunta ou solicitacao>
```

## What This Does

Convoca o Conselho Consultivo de 53 especialistas em monetizacao, pricing e revenue das maiores empresas de SaaS, marketplaces e B2B do mundo, organizados em 8 clusters de perspectiva:

1. **SaaS Pricing & Packaging** (7) — ProfitWell, OpenView, Simon-Kucher, MercadoLibre, Sixteen Ventures
2. **Distribution & Licensing Models** (7) — HubSpot, Canalys, Winning by Design, Coupa, Nubank
3. **B2B & GovTech Revenue** (7) — Predictable Revenue, Outreach, Olist, VTEX, Gainsight, GTM Partners
4. **Marketplace & API Monetization** (7) — Twilio, Benchmark, ContaAzul, Foursquare, OpenAI, Senzing
5. **Revenue Operations** (6) — Drift, Theory Ventures, SaaStr, Apollo.io, Craft Ventures
6. **VC & Unit Economics** (6) — Nubank, Loft/Canary, Launch, Calm Fund, 20VC
7. **Partnerships & Channel Sales** (7) — Crossbeam, PartnerHacker, Matrix Partners, HubSpot
8. **Bootstrap & Rapid Revenue** (6) — TinySeed, Nomadlist, 37signals, ConvertKit, Geocodio

**Zero bias:** Nenhum modelo de monetizacao e favorecido a priori. Todos competem igualmente na deliberacao (SaaS direto, white-label, API, marketplace, servicos, parcerias, etc.).

## Scoring Framework

Cada modelo e pontuado em 3 dimensoes (1-10):

| Dimensao | Peso | O que mede |
|----------|:----:|------------|
| Retorno Potencial | 40% | Revenue ceiling em 12 meses |
| Probabilidade de Conversao | 35% | Taxa realista de fechar negocio |
| Rentabilidade | 25% | Margem liquida apos custos |

**Score Final** = (Retorno x 0.40) + (Conversao x 0.35) + (Rentabilidade x 0.25)

O modelo com maior Score Final vence a deliberacao.

## Deliberation Protocol

```
Phase 1: Product, Market & Lead Evidence (product + web search + lead research)
Phase 2: Monetization Strategy Proposals + Scoring (8 models, each scored)
Phase 3: Revenue Confrontation (4 pairs challenge scores with evidence)
Phase 4: Revenue Synthesis, Lead Mapping & Prioritization (adjusted scores + lead list)
Phase 5: Unanimous Consensus (8/8 required)
```

**Output:** Playbook unanime + tabela de scores + pipeline de leads com contatos e scripts de rapport.

## Confrontation Pairs

- **SaaS Pricing** vs **Bootstrap Revenue** — scalable vs quick cash
- **Distribution & Licensing** vs **Marketplace & API** — B2B distribution vs platform model
- **B2B/GovTech Revenue** vs **VC & Unit Economics** — organic vs funded growth
- **Revenue Operations** vs **Partnerships & Channel** — direct vs indirect revenue

## Execution

When the user invokes `/turbocash`, execute this protocol:

1. **Parse the question** from args
2. **Launch parallel evidence agents:**
   - `Explore` agent: Analyze Extra Consultoria product (pricing, billing code, features, trial flow, current plans, sectors, pipeline, export capabilities)
   - `general-purpose` agent: Web search for 2026 B2G SaaS monetization models, competitor pricing in licitacoes market, SaaS trial-to-paid benchmarks Brazil, consultorias de licitacao (leads reais com nomes, sites, LinkedIn, contatos)
3. **Launch deliberation agent** (Opus deep-executor) with all evidence:
   - Simulates 8 cluster perspectives
   - Each cluster proposes monetization strategy with: model, target customer, suggested pricing (BRL), timeline to first revenue, effort, primary risk, **SCORE (3 dimensions)**
   - Runs revenue confrontation across 4 pairs — each pair MUST challenge opponent's scores with evidence
   - Scores are recalculated post-confrontation
   - Synthesizes and ranks by Score Final
   - MUST include Quick Cash (0-30 days) actions
   - MUST include revenue targets in BRL (monthly milestones)
   - MUST include consolidated lead pipeline with contacts and rapport scripts
   - Outputs ONLY the final consensus playbook + lead list
4. **Present consensus** to user in the standard format

## Output Format

```markdown
## Consenso do Conselho de Revenue — Monetizacao Extra Consultoria

**Modelo Vencedor:** [Formato que venceu a deliberacao — sem bias pre-definido]

**Score Final:**
| Modelo | Retorno (40%) | Conversao (35%) | Rentabilidade (25%) | Score |
|--------|:---:|:---:|:---:|:---:|
| [Vencedor] | X/10 | X/10 | X/10 | X.X |
| [2o lugar] | X/10 | X/10 | X/10 | X.X |
| ... | | | | |

**Revenue Playbook Priorizado:**
[Estrategias rankeadas pelo Score Final]

**Quick Cash (0-30 dias):**
- [Acoes que geram receita imediata com esforco minimo]

**Short-Term Revenue (30-90 dias):**
- [Modelos de receita que escalam no trimestre]

**Scalable Revenue (90-180 dias):**
- [Modelos de receita escalavel e recorrente]

**Fundamentos:**
- [Por que o modelo vencedor venceu — evidence-backed]

**Evidencias de Mercado:**
- [Benchmarks, pricing competidores, cases — com fontes/URLs]

**Unit Economics Projetados:**
- [LTV, CAC, payback, break-even, MRR targets]

**Metas de Receita:**
- Mes 1: R$ ___
- Mes 3: R$ ___
- Mes 6: R$ ___
- Mes 12: R$ ___

---

## Pipeline de Leads para Abordagem Imediata

**Leads Tier 1 (alta probabilidade):**
| Empresa | Segmento | Contato | Cargo | LinkedIn | Canal | Potencial MRR |
|---------|----------|---------|-------|----------|-------|:---:|
| [Nome] | [Tipo] | [Nome] | [Cargo] | [URL] | [Email/LinkedIn/WhatsApp] | R$ ___ |

**Leads Tier 2 (media probabilidade):**
[Mesma estrutura]

**Script de Rapport (Tier 1):**
[Mensagem personalizada para primeira abordagem — por segmento]

**Script de Follow-up (D+3):**
[Mensagem de follow-up caso nao responda]

**Canais de Prospeccao Recomendados:**
[Onde encontrar mais leads deste perfil]

---

**Riscos Reconhecidos:**
- [Trade-offs aceitos conscientemente]

**O que NAO fazer:**
- [Anti-patterns e armadilhas]

**Proximo Passo Imediato:**
- [A UNICA acao mais importante para fazer HOJE]

---
_Consenso unanime: 8/8 clusters (53 especialistas em revenue)_
```

## Examples

```
/turbocash Como monetizar Extra Consultoria nos proximos 30 dias?
/turbocash Qual formato gera receita mais rapido: SaaS, servico ou parceria?
/turbocash Qual o modelo de pricing ideal para B2G SaaS?
/turbocash Devo vender API de dados de licitacao?
/turbocash Como chegar a R$10k MRR em 90 dias?
/turbocash Playbook completo de monetizacao rapida 2026
/turbocash Qual canal de vendas priorizar: direto ou parceiro?
/turbocash Vale criar marketplace de licitacoes?
/turbocash Como monetizar os 15 setores de classificacao IA?
/turbocash Modelo de receita para consultorias que atendem empresas B2G
/turbocash Quem sao os leads mais quentes para abordar esta semana?
```

## Constraints

- **Pre-revenue** — todas as estrategias devem considerar budget limitado
- **Founder-led sales** — sem equipe de vendas, priorizar modelos self-serve ou low-touch
- **Contexto Brasil** — mercado B2G brasileiro, licitacoes publicas, valores em BRL
- **2026** — praticas atualizadas, modelos de monetizacao correntes
- **Zero bias** — nenhum modelo e favorecido; a deliberacao decide baseada em evidencias e scores
- **Scoring obrigatorio** — cada modelo recebe score em 3 dimensoes (retorno 40%, conversao 35%, rentabilidade 25%)
- **Leads obrigatorio** — sempre incluir pipeline de leads com contatos reais e scripts de rapport
- **Quick Cash obrigatorio** — sempre incluir acoes para receita nos primeiros 30 dias
- **Unit economics realistas** — conservadores, baseados em benchmarks reais
- **Metricas gratuitas** — Stripe Dashboard, GA4, Mixpanel free tier
