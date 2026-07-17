# Relatório de Débito Técnico
**Projeto:** Extra Consultoria  
**Data:** 2026-07-17  
**Versão:** 3.0  
**Fonte:** `docs/prd/technical-debt-assessment.md` v3.0 FINAL  
**Elaborado por:** Alex (@analyst) — Brownfield Discovery Phase 9  
**Gate QA (Phase 7):** APPROVED WITH CONDITIONS (C1–C6 fechadas no FINAL)

---

## Executive Summary (1 página)

### Situação Atual

A Extra Consultoria concluiu, em 17 de julho de 2026, a reavaliação completa de débito técnico da Plataforma de Inteligência B2G (Brownfield Discovery Phases 1–8). O inventário passou de **79 débitos (v2, 13/jul)** para cerca de **118 IDs canônicos ativos** (≈140 com aliases), com **~22 itens resolvidos ou mitigados** desde a v2.

O sistema **avança** em resiliência local, CI fail-closed e unificação de matching — mas a mensagem central para a liderança é inequívoca:

| Claim | Status | Significado para o negócio |
|-------|--------|----------------------------|
| **`LOCAL_RESILIENCE_READY`** | ✅ Pronto | Mecânicas locais de resiliência, health JSON e CI existem e são auditáveis |
| **`VPS_OPERATIONAL`** | ❌ **NÃO** | **Proibido** habilitar timers oficiais ou declarar VPS “em produção” enquanto a Onda de verdade (split-brain, dual runtime, secrets, schema, gate de verdade) estiver aberta |
| Cobertura operacional (M2) | **0%** (0 de 1.093) | Meta 95% é **alvo de produto**, não conquista atual |
| Sinal comercial (M1) | **10,6%** (116 de 1.093) | Ranking comercial — **não** é cobertura operacional |

Em linguagem de negócio: **a casa tem alarme e checklist de segurança; ainda não está pronta para ser a loja aberta 24h.** Declarar o contrário (VPS “operacional” ou “95% de cobertura”) gera risco de **confiança do consultor e do cliente** — o pior tipo de dívida, porque corrói a marca.

### Números Chave

| Métrica | Valor |
|---------|-------|
| IDs canônicos ativos | ~118 |
| Resolvidos / mitigados desde v2 | ~22 |
| P0 (pre-VPS + segurança + honesty) | ~16 itens · **72–80h** · **R$ 10.800–12.000** |
| Total ativo (sem Web UI, sem elevação M2 full) | **~310–360h** · **R$ 46.500–54.000** (mid **~335h / R$ 50.250**) |
| Total com Web UI completo (diferido) | **~390–440h** · **R$ 58.500–66.000** (mid **~415h / R$ 62.250**) |
| Pre-VPS only (cenário mínimo obrigatório) | **~76h** · **R$ 11.400** |
| Taxa horária base | **R$ 150/h** |
| Status operacional honesto | **`LOCAL_RESILIENCE_READY` · NÃO `VPS_OPERATIONAL`** |
| Credencial sensível residual (SA JSON) | **Ainda presente no repositório** (SEC-02 P0) |
| Banco live verificado em 17/07 | **Offline** — RESOLVED de schema = confiança em código/dump, não em dados de produção |

### Recomendação

1. **Autorizar imediatamente a Onda Pre-VPS (Waves 1–3, ~72–80h / ≈ R$ 11.400)** como investimento mínimo não negociável.  
2. **Não habilitar timers oficiais nem claim VPS** até SYS-001/002 + TQ-07 + SEC-02 + schema truth fechados com evidência.  
3. **Tratar métricas com honestidade comercial:** M1 (sinal) ≠ M2 (cobertura) ≠ “GO” de operação.  
4. **Diferir Web UI** até CLI estável e VPS com claim legítimo.  
5. Encaminhar ao **@pm / @sm** a geração de epics com Wave 1 (segurança + integridade) em primeiro lugar.

---

## Análise de Custos

### Custo de RESOLVER (R$ 150/h)

| Cenário | Horas (aprox.) | Custo |
|---------|----------------|-------|
| **Pre-VPS only** (must-fix + honesty pack) | 72–80 (mid **76**) | **R$ 10.800 – 12.000** (mid **R$ 11.400**) |
| Ativo sem Web UI e sem M2 full | 310–360 (mid **335**) | **R$ 46.500 – 54.000** (mid **R$ 50.250**) |
| + Web UI MVP (40h) | ~375 | **R$ 56.250** |
| + Web UI completo (80h) | ~415 | **R$ 62.250** |
| Elevação de cobertura M2 (produto, pós-truth) | 40h+ | **R$ 6.000+** (adicional) |

#### Distribuição por prioridade (canônico)

| Prioridade | Qtd aprox. | Horas | Custo (R$150/h) | Ação de negócio |
|------------|------------|-------|-----------------|-----------------|
| **P0** Pre-VPS + segurança + honesty | ~16 | 72–80h | R$ 10.800–12.000 | Gate de sobrevivência operacional |
| **P1** Curto prazo | ~28 | ~95h | **R$ 14.250** | Fundação e unificação de runtime |
| **P2** Médio prazo | ~40 | ~120h | **R$ 18.000** | Integridade, performance residual, UX CLI |
| **P3** Longo prazo / diferido | ~34 | ~90h+ | **R$ 13.500+** | Polish + Web UI quando reabrir |

#### Fatias críticas dentro do Pre-VPS

| Fatia | Horas | Custo | Por quê importa |
|-------|-------|-------|-----------------|
| Segurança + defaults de deploy (SEC-02, DT-35, residual SQL) | ~5–7h | R$ 750–1.050 | Credencial e senha fraca fora do path de deploy |
| Truth chain (checkpoint → health → writer único → dual systemd) | ~33h | **R$ 4.950** | Fim do “parece que funciona” |
| Schema truth (migrations únicas + dump HEAD) | ~12–14h | R$ 1.800–2.100 | Uma verdade de banco |
| Gates de teste / claim VPS (TQ-02, TQ-07) | ~6h | **R$ 900** | Impede declaração falsa de produção |
| Pack UX honesty (progresso, health humano, M1≠M2, tabelas, sumário) | ~20h | **R$ 3.000** | Operador e consultor enxergam a verdade |

**Nota de leitura:** o salto de ~R$ 53k (v2 total) para ~R$ 50k mid (v3 sem web) **não** significa que “ficou barato demais”. A v3 **reescreveu a prioridade**: ~22 débitos caíram (resolvidos), mas surgiram bloqueadores de produção (split-brain, dual runtime, health mentiroso) que a v2 ainda subestimava. O dinheiro “certo” a autorizar **agora** é o Pre-VPS (~R$ 11.400), não o backlog completo de uma vez.

### Custo de NÃO RESOLVER (riscos)

Não resolver — ou pior, **declarar VPS pronta sem fechar a Onda de verdade** — materializa riscos financeiros e reputacionais:

| Risco | Impacto no negócio | Probabilidade | Custo esperado (ordem de grandeza) |
|-------|--------------------|---------------|-------------------------------------|
| **Credenciais compostas** (SA JSON no repo + defaults fracos de deploy) | Comprometimento de conta cloud / banco; exposição de dados de fornecedores e órgãos; exposição regulatória (LGPD) | **Alta** enquanto SEC-02 aberto | **R$ 50.000 – 500.000+** por incidente |
| **Split-brain FS vs PostgreSQL + dual systemd** | Coleta “verde” no disco e “vazia” no banco (ou o inverso); decisões de consultoria em cima de evidência errada; timers oficiais competindo entre si | **Alta** se VPS for ligada cedo | **R$ 10.000 – 100.000** por semana de operação cega |
| **Health “saudável” com fixture / SLA inventado** | Operador e gestão confiam em status falso; atraso em incidentes reais | **Alta** sem Wave 2 | **R$ 5.000 – 40.000** por incidente de confiança |
| **M1 lido como M2 ou como “GO”** | Cliente ou consultor acredita em 10,6% de “cobertura” como se fosse operação plena; ou confunde ranking comercial com pronta-entrega | **Alta** sem UX honesty | **R$ 5.000 – 50.000** por ocorrência comercial + risco de churn |
| **Schema dump ≠ HEAD / dual track de migrations** | Ambiente “sobe” com schema errado; regressões silenciosas de pipeline | **Média–Alta** | **R$ 10.000 – 80.000** em retrabalho e downtime |
| **Refatorar monólito sem testes / sem writer único** | Quebra de crawlers em produção; perda de oportunidades | **Alta** se ordem for invertida | **R$ 10.000 – 100.000** por semana |

**Custo total esperado da NÃO ação (12 meses, faixa conservadora a severa):**  
**R$ 90.000 – 900.000+**, contra **R$ 11.400** para fechar o Pre-VPS e **~R$ 50.250** para o backlog ativo sem Web UI.

Mesmo no cenário mais conservador, **pagar a Onda Pre-VPS se paga com a prevenção de um único incidente de credencial ou de uma semana de operação cega**.

---

## Impacto no Negócio

### Cobertura operacional 0% vs sinal comercial 10,6%

- **M2 (cobertura operacional) = 0/1.093 (0%)** — o sistema **não** pode ser vendido ou gerido como “quase 95%”.  
- **M1 (sinal comercial) = 116/1.093 (10,61%)** — útil para **ranking e priorização comercial**, mas **não** substitui cobertura operacional.  
- Confundir as duas métricas é um **risco de produto e de reputação**, não um detalhe de UI.

### Bloqueio de claim VPS

Enquanto permanecerem abertos:

- **SYS-001** — path oficial grava em filesystem, não no PostgreSQL (split-brain)  
- **SYS-002** — duas famílias de timers systemd competindo  
- **TQ-07** — gate que ainda não **falha** (FAIL) se dual runtime ao autorizar VPS  
- **SEC-02** — service account JSON ainda no tree  
- **Schema truth** — dump e migrations HEAD não fechados  

…a organização **não deve** ligar timers oficiais nem comunicar “VPS operacional”.  
**`LOCAL_RESILIENCE_READY` ≠ loja aberta.**

### Risco de confiança do consultor / cliente (métricas falsas)

O pior custo não é só técnico: é **perder a confiança de quem decide com o radar**.  
Health verde com fixture, progresso zero em comandos longos, tabela truncada e label de “cobertura” ambíguo produzem o mesmo efeito: **decisão errada com aparência de rigor**.

### Velocidade de entrega

- ~22 débitos resolvidos desde a v2 (CI, matching unificado, schema v3 base, upserts set-based) **aumentam** a capacidade de entrega.  
- Porém, o monólito `monitor.py`, dual path PNCP e ausência de suite de integração residual **ainda freiam** features de receita (elevação M2, novas fontes, multi-cliente).  
- Cada sprint que ignora a Onda de verdade **compõe juros** sobre o débito de produção.

---

## Timeline Recomendado

### Fase Pre-VPS (Wave crítica · ~72–80h · ≈ R$ 11.400)

**Objetivo de negócio:** uma verdade de dados + saúde honesta + secrets limpos + gate que impede claim falso.

| Wave | Foco | Horas | Custo | Saída para o negócio |
|------|------|-------|-------|----------------------|
| **Wave 1** | Segurança + integridade de schema | ~18h | **R$ 2.700** | SA JSON fora; deploy sem senha fraca; migrations únicas; dump = HEAD |
| **Wave 2** | Build, testes, observabilidade honesta | ~25h | **R$ 3.750** | Health não mente; coverage sobe de forma controlada; truth gate existe |
| **Wave 3** | Runtime único (writer PostgreSQL + uma família systemd) | ~20h | **R$ 3.000** | Fim do split-brain; **pré-condição** para claim VPS |
| **Pack UX ops (∥)** | Progresso, health humano, M1≠M2, tabelas, sumário | ~20h | **R$ 3.000** | Operador enxerga a verdade no dia a dia |

**Sequência não negociável:** secrets/checkpoint → health → writer único → schema → gates.  
UX de progresso pode correr em paralelo seguro; **Web UI não**.

### Fundação (pós Pre-VPS · Waves 4–5 · ~60h · ≈ R$ 9.000)

| Wave | Foco | Horas | Custo |
|------|------|-------|-------|
| **Wave 4** Coupling | Testes de integração de crawlers → fatiar monólito → unificar PNCP | ~40h | **R$ 6.000** |
| **Wave 5** Integridade residual | Constraints, reconciliação real, retenção, rollback pack | ~20h | **R$ 3.000** |

**Resultado de negócio:** base estável para evoluir cobertura M2 e novas fontes sem medo de regressão.

### Otimização (Wave 6 residual + P1/P2 · ~45–95h · ≈ R$ 6.750–14.250)

- Completar honesty de CLI (display unificado, erros claros, onboarding).  
- Continuidade de segurança (processo CVE, secrets strategy).  
- Documentação operacional mínima.

### Diferido (Wave 7 + Web UI)

| Item | Quando reabrir | Custo |
|------|----------------|-------|
| **Elevação M2** (SYS-008, 40h+) | Após Onda de verdade fechada | **R$ 6.000+** |
| **Web UI** (UX-01, MVP 40h / full 80h+) | Após VPS com claim legítimo + CLI diário estável + demanda multi-user | **R$ 6.000 – 12.000+** |
| Polish, deps externas (ICP-Brasil, APIs), ORM | Backlog contínuo | conforme contrato/orçamento |

---

## ROI

### Cenário mínimo obrigatório (só Pre-VPS)

| Componente | Valor |
|------------|-------|
| Investimento | **R$ 11.400** (~76h) |
| Riscos evitados (conservador, 12 meses) | **R$ 50.000 – 150.000** |
| **ROI (12 meses, conservador)** | **≈ 340% – 1.200%** |
| **Payback** | **&lt; 1–2 meses** se evitar um único incidente material |

### Cenário backlog ativo sem Web UI

| Componente | Valor |
|------------|-------|
| Investimento mid | **R$ 50.250** (~335h) |
| Economia operacional + riscos evitados (conservador 12m) | **R$ 100.000 – 250.000** |
| **ROI (12 meses, conservador)** | **≈ 100% – 400%** |
| **Payback** | **≈ 3–6 meses** |

### Cenário com Web UI completo (estratégico, não urgente)

| Componente | Valor |
|------------|-------|
| Investimento mid | **R$ 62.250** (~415h) |
| Retorno adicional | escala multi-user / self-service (depende de demanda) |
| **Recomendação** | **Não competir** com Pre-VPS; decidir após claim VPS legítimo |

### Fatores de alavancagem

1. **Custo de oportunidade:** hora gasta contornando dual runtime e health mentiroso é hora **não** gasta em novas fontes e receita de consultoria.  
2. **Custo de atraso:** M2 em 0% só sobe de forma confiável **depois** do writer único — pular essa etapa multiplica retrabalho.  
3. **Proteção de ativos:** SEC-02 + defaults de deploy fecham risco existencial por **poucas horas** e **centenas de reais**.  
4. **Proteção de marca:** honesty de métricas (M1 ≠ M2) evita o pior ROI negativo — **cliente desacreditado**.

---

## Próximos Passos

- [ ] **@pm (Morgan):** aprovar investimento **Pre-VPS (~R$ 11.400 / 72–80h)** como wave obrigatória  
- [ ] **@pm / @sm:** criar epic **“Pre-VPS Truth”** (Waves 1–3) com stories HIGH-RISK para SEC-02 e schema  
- [ ] **@sm:** story **SEC-02 residual** (remover SA JSON + gitignore + rotação) — **proibido tratar como FAST**  
- [ ] **@devops / @pm:** manter **freeze** de timers oficiais e de claim `VPS_OPERATIONAL` até TQ-07 + SYS-001/002 verdes  
- [ ] **@po:** validar stories da Wave 1 antes de qualquer implementação  
- [ ] **@dev → @qa:** executar Wave 1 com evidências binárias (arquivo ausente, dump = HEAD, etc.)  
- [ ] **Liderança de produto:** comunicar internamente **M2 = 0%** e **M1 = 10,6%** com glossário fixo (evitar linguagem de “quase 95%”)  
- [ ] **Decisão diferida:** Web UI e elevação M2 full **somente** após claim VPS legítimo  
- [ ] **Quando DB live subir:** smoke obrigatório (`_migrations` == HEAD, diagnostics exit 0) — residual de verificação 17/07  
- [ ] **Pós-Done das waves de verdade:** recomendar re-extração Reversa (crawl/resilience/ops) como follow-up, não automático  

---

## Anexos (links internos)

| Documento | Papel |
|-----------|-------|
| [`docs/prd/technical-debt-assessment.md`](../prd/technical-debt-assessment.md) | **Fonte definitiva** v3.0 FINAL (inventário, waves, riscos) |
| [`docs/reviews/qa-review.md`](../reviews/qa-review.md) | Gate QA Phase 7 — APPROVED WITH CONDITIONS |
| [`docs/reviews/db-specialist-review.md`](../reviews/db-specialist-review.md) | Revisão Dara (DB ≈ 46h abertas) |
| [`docs/reviews/ux-specialist-review.md`](../reviews/ux-specialist-review.md) | Revisão Uma (UX ≈ 101h sem Web) |
| [`docs/architecture/system-architecture.md`](../architecture/system-architecture.md) | Arquitetura v3 |
| [`supabase/docs/DB-AUDIT.md`](../../supabase/docs/DB-AUDIT.md) | Auditoria de schema |
| [`docs/frontend/frontend-spec.md`](../frontend/frontend-spec.md) | Spec frontend/CLI v3 |
| [`docs/prd/technical-debt-DRAFT.md`](../prd/technical-debt-DRAFT.md) | DRAFT predecessor v3.0 |
| Relatório v2 (histórico) | Este arquivo em versão 2.0 (2026-07-13) — substituído por esta v3.0 |

### Glossário rápido para stakeholders

| Termo | Significado simples |
|-------|---------------------|
| **M1 — Sinal comercial** | Quantos órgãos/entidades “aparecem” no radar comercial (~10,6% hoje) |
| **M2 — Cobertura operacional** | Quantos estão de fato cobertos com evidência operacional **no banco** (0% hoje) |
| **`LOCAL_RESILIENCE_READY`** | Resiliência e checks locais prontos — **não** é produção VPS |
| **`VPS_OPERATIONAL`** | Claim de produção; **bloqueado** até Onda de verdade |
| **Split-brain** | Sistema grava em dois mundos (arquivo vs banco) e ninguém sabe qual é a verdade |
| **Honesty pack** | Mudanças de UX/ops que **impedem verde falso** e confusão de métricas |

### Totais de custo (síntese para aprovação)

```text
Taxa base:                    R$ 150/h
Pre-VPS (mid 76h):            R$ 11.400     ← autorizar agora
P1 curto prazo (~95h):        R$ 14.250
P2 médio prazo (~120h):       R$ 18.000
P3 / diferido (~90h+):        R$ 13.500+
Ativo sem Web / sem M2 full:  R$ 50.250 mid (310–360h)
+ Web UI MVP:                 R$ 56.250
+ Web UI full:                R$ 62.250
```

---

*Relatório gerado por Alex (@analyst) em 2026-07-17 a partir do Technical Debt Assessment FINAL v3.0.*  
*Posição operacional: **`LOCAL_RESILIENCE_READY` · NÃO `VPS_OPERATIONAL`**.*  
*Próxima etapa de processo: @pm / @sm — epics e stories da Wave 1 (Pre-VPS Truth).*
