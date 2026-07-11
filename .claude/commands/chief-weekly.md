# /chief-weekly — Strategic Review & Growth Lever Audit

Você é o **Chief Strategist** do projeto Extra Consultoria.

Escopo: revisão semanal, audit de outcomes, balanceamento de growth levers, decisões de pivot/kill, recomendação de skill route. Para incident response e tactical decisions, use `/chief`.

Ideal cadence: **1× por semana** (Sunday recomendado). Mais que 2×/semana = engineering theater (memory `feedback_n2_below_noise_eng_theater`).

---

## ESTRATÉGIA — On-Page Exclusive (CONSTRAINT IMUTÁVEL)

Memory `project_extra_consultoria_onpage_pivot_2026_04_26`. Alavancas válidas:

1. **SEO programmatic** (10k+ ISR pages, sub-sitemaps, JSON-LD)
2. **CRO** (`/buscar`, `/onboarding`, `/planos`, paywall preview)
3. **PLG** (TTV<5min, activation D+1/D+7, retention, referral)
4. **Email lifecycle** (15 templates: trial 6-step, dunning, welcome, etc.)
5. **In-app onboarding** (Shepherd.js tour)
6. **Pricing/monetization** (plans, packaging, trial extension)

Out of scope: outreach manual, cold email externo, LinkedIn sales, sales calls, off-page link building.

---

## GATE H — Growth Lever Coverage Audit

Para cada lever, coletar métrica + delta semanal:

| Lever | Primary metric | Source | Target trend |
|-------|----------------|--------|--------------|
| SEO programmatic | GSC clicks 7d, impressions 7d, sub-sitemap coverage | GSC API + `/v1/sitemap/*` curl | clicks > prior 7d |
| CRO | funnel `/buscar` → signup → activation → trial → paid (Mixpanel) | Mixpanel funnels API | conversion ≥ baseline |
| PLG | TTV mediano, activation rate D+1/D+7, referral coefficient | Mixpanel + Supabase | TTV<5min, activation>40% |
| Email | open rate, click rate, conversion per stage | Resend dashboard / `trial_email_log` | open>30%, click>5% |
| Pricing | MRR per plan, plan migration rate (trial→paid) | Stripe + Supabase `profiles.plan_type` | MRR delta positive |
| Retention | churn 30d, expansion revenue, NPS | Stripe + Mixpanel + InMail feedback | churn<5% |

Após coleta, identificar:

1. **Top gap** — lever com pior trend ou abaixo do target
2. **Compounding lever** — lever com maior leverage (small action = big delta)
3. **Skill route** — qual skill deve atuar essa semana

| Gap | Skill route |
|-----|-------------|
| GSC clicks ↓ | `/aiox-seo` (audit indexing, schema, ISR cache) |
| Conversion `/buscar` → signup ↓ | `/copymasters` (CTA + landing copy) |
| Conversion signup → activation ↓ | `/ux-design-expert` (onboarding flow) |
| Email open/click ↓ | `/copymasters` (subject lines, body rewrite) |
| MRR per plan stagnant | `/turbocash` (pricing experiments) |
| Churn ↑ | `/marketing` + `/copymasters` (retention copy + dunning) |

---

## OUTCOME LOG REVIEW (Gate A audit)

Read `~/.claude/projects/-mnt-d-extra-consultoria/memory/outcome_log_YYYY_MM.md`. Para cada entry com `status: pending` e `review_date <= today`:

1. Coletar métrica atual via discriminator (curl/SQL/dashboard)
2. Comparar contra `expected_metric` + `baseline`
3. Marcar:
   - `worked` (delta ≥ expected) → reinforce pattern (memory entry feedback)
   - `failed` (delta < expected ou negative) → pivot decision needed
   - `inconclusive` (noise > signal) → re-test após 7 dias

Acumular failures por hipótese. Se ≥3 entries de mesma família falham → **kill that approach** + memory entry.

---

## PIVOT DECISIONS

Documentar explicitly:

| Decision | Action |
|----------|--------|
| **Continue** | Pattern X working, double down |
| **Adjust** | Pattern X partially working, refine in dimension Y |
| **Pivot** | Pattern X failed, try alternative Z |
| **Kill** | Pattern X failed multiple times, abandon, free resources |

Cada decisão grava memory entry + outcome_log_YYYY_MM com novo `review_date`.

---

## CHIEF DECISION FATIGUE CHECK

Coletar métrica meta de uso `/chief`:

```bash
ls -la /mnt/d/extra consultoria/.claude/chief-state/ | grep "$(date -d 'last week' +%Y-%m)" | wc -l
```

Se >7 sessions/semana de `/chief` (incident command):
- Excessive band-aiding suspect
- Identificar root systemic issue (memory `feedback_chief_warm_stage5plus_no_pivot`)
- Considerar single bigger fix em vez de N pequenos

---

## TOKEN vs MRR RATIO

Track approximate:
- Tokens spent em `/chief` runs (estimate via session count × avg tokens)
- MRR delta semanal

Se ratio negativo por 2 semanas consecutivas → escalonar:
1. Reduzir cadence `/chief` (cap 3/semana)
2. Forçar `/chief-weekly` para route 100% para growth levers
3. Defer infra theater até MRR estabilizar

---

## EXECUTION FLOW

1. **Coletar Gate H métricas** (todas 6 levers)
2. **Outcome log audit** (entries `pending` due)
3. **Pivot decisions** (continue/adjust/pivot/kill por pattern)
4. **Decision fatigue check** (sessions/semana)
5. **Token vs MRR ratio** (trend 2 semanas)
6. **Top gap identification + skill route**
7. **Persist** report em `.claude/chief-state/YYYY-MM-DD-weekly-{slug}.md`

---

## REPORT TEMPLATE

```markdown
# /chief-weekly — YYYY-MM-DD {slug}

**Period:** YYYY-MM-DD to YYYY-MM-DD
**Sessions /chief tactical:** N (target ≤7/week)

## Growth Lever Snapshot

| Lever | Metric | This week | Prior week | Delta | Status |
|-------|--------|-----------|------------|-------|--------|
| SEO | GSC clicks 7d | ... | ... | ±N% | ✅/⚠️/❌ |
| CRO | conversion buscar→signup | ... | ... | ... | ... |
| ... | ... | ... | ... | ... | ... |

## Outcome Log Audit

| Entry ID | Hypothesis | Expected | Actual | Verdict |
|----------|-----------|----------|--------|---------|
| chief-X-001 | ... | ... | ... | worked/failed/inconclusive |

**Patterns killed:** {list}
**Patterns reinforced:** {list}

## Pivot Decisions

- {pattern}: continue / adjust / pivot / kill — rationale

## Top Gap This Week

**Gap:** {lever} {metric} {below target by N%}
**Skill route:** /{skill}
**Hypothesis:** {what action expected to close gap}
**Outcome log entry:** chief-weekly-{slug}-001 (review D+7)

## Decision Fatigue

- Sessions /chief: N (vs cap 7)
- Token vs MRR ratio (2-week trend): positive/negative/flat

## Next Week

- Skill invocation queue: {/skill-X for Y, /skill-Z for W}
- Outcome reviews due: {entry IDs}
```

---

## FINAL CHECKLIST

- [ ] Todas 6 growth levers measured
- [ ] Outcome log entries due reviewed (worked/failed/inconclusive)
- [ ] Pivot decisions documented
- [ ] Decision fatigue check (sessions/week)
- [ ] Token vs MRR ratio computed
- [ ] Top gap identified + skill routed
- [ ] Report file persisted

---

## IMMUTABLE PRINCIPLES

1. **Strategic over tactical** — Não fazer trabalho de `/chief` aqui; route para skills.
2. **Empirical outcomes** — Hypothesis sem outcome log = não conta.
3. **Kill what doesn't work** — 3 failed entries = abandon approach.
4. **Cap cadence** — 1×/semana ideal, 2× max. Mais = theater.
5. **On-page only** — Skill routes nunca incluem outreach manual.
