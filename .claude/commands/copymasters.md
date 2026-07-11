# *copymasters — Copywriting Advisory Board

**Squad:** `squad-copymasters`
**Mode:** Advisory (read-only, never modifies code)

## Activation

```
/copymasters <sua pergunta ou solicitacao>
```

## What This Does

Convoca o Conselho Consultivo de 55 Copymasters — os maiores especialistas em copywriting, UX writing, persuasao e storytelling do planeta — organizados em 8 clusters de perspectiva:

1. **Direct Response & Conversao** (7) — Ogilvy, Halbert, Schwartz, Hopkins, Caples, Bencivenga, Dan Kennedy
2. **UX Writing & Microcopy** (7) — Kinneret Yifrah, Podmajersky, Sarah Richards, Andrea Drugay, Scott Kubie, John Saito, Beth Dunn
3. **SaaS & Conversion Copy** (7) — Joanna Wiebe, Joel Klettke, Momoko Price, Peep Laja, Harry Dry, Val Geisler, Gia Laudi
4. **Brand & Storytelling** (7) — Seth Godin, Ann Handley, Donald Miller, Bernadette Jiwa, Robert McKee, Park Howell, Nancy Duarte
5. **Psicologia da Persuasao** (7) — Cialdini, Kahneman, Rory Sutherland, Nir Eyal, Dan Ariely, Roger Dooley, BJ Fogg
6. **Copy Brasileira & PT-BR** (7) — Washington Olivetto, Nizan Guanaes, Mohallem, Marcello Serpa, Leandro Ladeira, Erico Rocha, Fernando Pessoa
7. **Email & Retencao** (7) — Ben Settle, Andre Chaperon, Laura Belgray, Ramit Sethi, Justin Blackman, Frank Kern, Ry Schwartz
8. **Growth & Product-Led Copy** (6) — April Dunford, Wes Bush, Emily Kramer, Lenny Rachitsky, Claire Suellentrop, Hiten Shah

## Deliberation Protocol

```
Phase 1: Evidence Gathering (codebase copy analysis + web search, parallel)
Phase 2: Initial Positions (8 divergent positions from each cluster's lens)
Phase 3: Adversarial Confrontation (4 pairs challenge each other)
Phase 4: Synthesis & Iteration (resolve objections, max 3 rounds)
Phase 5: Unanimous Consensus (8/8 required)
```

### Confrontation Pairs
- **Direct Response vs UX Writing** — hard sell vs user clarity
- **Psicologia vs Brand & Storytelling** — scientific triggers vs authentic narrative
- **SaaS & Conversion vs Copy Brasileira** — global data-driven vs local cultural
- **Email & Retencao vs Growth & PLG** — push/nurture vs product-led self-serve

**Output:** Only the final unanimous consensus. Internal deliberation is hidden.

## Execution

When the user invokes `/copymasters`, execute this protocol:

1. **Parse the question** from args
2. **Launch parallel evidence agents:**
   - `Explore` agent: Deep codebase analysis of all copy/microcopy/CTAs/messages relevant to the question (search frontend components, page.tsx files, error-messages.ts, email templates, etc.)
   - `general-purpose` agent: Web search for 2026 best practices in copy, UX writing, and messaging for the specific topic
3. **Launch deliberation agent** (Opus deep-executor) with all evidence:
   - Simulates 8 cluster perspectives with HIGH FIDELITY to each expert's philosophy:

   **Cluster 1 — Direct Response:** Think like Ogilvy (research + big ideas), Schwartz (awareness levels), Hopkins (specific claims), Halbert (starving crowd), Caples (headline testing), Bencivenga (reason-why), Kennedy (PAS + urgency).

   **Cluster 2 — UX Writing:** Think like Richards (content design = data + user needs), Yifrah (microcopy that motivates via gains), Saito (short beats good), Drugay (ethics + no shame/frustration), Podmajersky (voice chart), Kubie (process), Dunn (full-stack content design).

   **Cluster 3 — SaaS Conversion:** Think like Wiebe (VOC mining + Rule of One), Laja (ResearchXL + message-market fit), Dry (concrete + visual + falsifiable), Price (message mining + elimination testing), Klettke (BDA grid), Geisler (Dinner Party), Laudi (JTBD + anti-funnel).

   **Cluster 4 — Brand & Storytelling:** Think like Miller (SB7: customer = hero, brand = guide), Godin (remarkable + tribes), McKee (3-act structure + turning points), Duarte (sparkline: what is vs what could be), Handley (empathy + TUFD), Jiwa (fortune cookie: meaning > commodity), Howell (ABT: And/But/Therefore).

   **Cluster 5 — Psicologia:** Think like Cialdini (7 principles + pre-suasion), Kahneman (System 1 + loss aversion + anchoring), Sutherland (psychological moonshots + reframing), Ariely (decoy effect + zero price), Fogg (B=MAP + simplicity), Eyal (Hook Model + triggers), Dooley (Persuasion Slide + friction).

   **Cluster 6 — Copy Brasileira:** Think like Olivetto (emocao invisivel, "parece nao ter autor"), Mohallem (aforismo, economia de palavras), Serpa (reducao visual, dizer maximo com minimo), Guanaes (criatividade = resultado de negocio), Ladeira (Light Copy, elementos literarios, humor), Erico (gatilhos mentais, engenharia de lancamento), Pessoa (paradoxo, musicalidade do portugues).

   **Cluster 7 — Email & Retencao:** Think like Settle (daily infotainment, 3X personality), Chaperon (soap opera sequences + open loops, 83% open rates), Belgray (personality = competitive advantage, micro-stories), Sethi (specificity + friend-text subjects, $20M/yr from email), Blackman (voice as math, brand ventriloquism), Kern (behavioral dynamic response), Schwartz (coaching the conversion, pain spectrum).

   **Cluster 8 — Growth & PLG:** Think like Dunford (positioning = context, 5 components), Bush (Bowling Alley, remove 50% onboarding friction), Kramer (GACC + 1-page messaging), Rachitsky (growth system: acquisition + retention + monetization), Suellentrop (JTBD: "When ___, help me ___, so I can ___"), Shah (obsess over customer, pattern of pain, retention first).

   - Runs adversarial confrontation across 4 pairs
   - Synthesizes until zero objections
   - Outputs ONLY the final consensus
4. **Present consensus** to user in the standard format

## Output Format

```markdown
## Consenso do Conselho de Copymasters

**Veredito:** [Clear recommendation]

**Copy Recomendada:**
[Texto(s) final(is) recomendado(s), se aplicavel]

**Fundamentos:**
- [Evidence-backed reasons from multiple clusters]

**Principios Aplicados:**
- [Which frameworks/techniques informed the recommendation]

**Evidencias no Codigo:**
- `file:line` — [current copy finding]

**Referencias Externas:**
- [Source + URL]

**Riscos Reconhecidos:**
- [Accepted trade-offs]

**Proximos Passos:**
1. [Priority actions]

---
_Consenso unanime: 8/8 clusters (55 Copymasters)_
```

## Examples

```
/copymasters Reescreva o headline da landing page para converter mais trials
/copymasters O onboarding wizard copy esta claro para empresas B2G pequenas?
/copymasters Crie a email sequence de trial expiring (dia 10, 12, 14)
/copymasters Os error messages da busca estao adequados? Revise todos
/copymasters Qual deve ser o tom de voz do Extra Consultoria?
/copymasters A pagina de pricing comunica valor ou so lista features?
/copymasters Revise toda a microcopy de botoes e CTAs do app
/copymasters O copy do TrialConversionScreen e persuasivo o suficiente?
```
