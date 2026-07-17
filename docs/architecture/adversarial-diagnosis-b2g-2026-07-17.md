# Diagnóstico Adversarial de Arquitetura — B2G Operational Platform

| Campo | Valor |
|-------|-------|
| **Data** | 2026-07-17 |
| **Autor** | Morgan (PM) + lente Architect |
| **Branch** | `epic/b2g-operational-platform-2026-07-17` |
| **Baseline comercial** | 116/1.093 entities_with_recent_commercial_signal (10,61%) |
| **Universo** | 1.093 (raio 200 km, imutável como denominador) |
| **Entradas** | audit-b2g-readiness, adversarial-coverage-qa, session 2026-07-17, L1 registry, EPIC-MASTER |

---

## 1. Tese adversarial

O sistema **parece** uma plataforma de inteligência B2G (137k+ LOC, 14 crawlers, 41 migrations, dezenas de stories “Done”). Na prática, a operação comercial depende de **execuções manuais**, **artefatos atestados**, **métricas conflituosas** e **fontes sem contrato de cobertura por entidade**. O gap principal não é “mais features de relatório” — é **fechamento do loop operacional com prova**.

```
PROMESSA COMERCIAL          REALIDADE OPERACIONAL
─────────────────           ─────────────────────
95% cobertura        →      ~10,6% sinal comercial; cobertura operacional não canônica
Rotina diária        →      N CLIs + scripts ad-hoc + JSON em output/
Scheduler 24/7       →      timers no repo; prova de permanente em VPS incompleta
Histórico 3 anos     →      pilot path 1d GO; 90d/3y NO-GO
Preço / win-rate     →      NOT_READY / capability sem fonte
```

---

## 2. Impedimentos confirmados

Para cada impedimento: **causa raiz**, **precisa ADR?**, **epic dono**, **status do componente habilitador**.

### I-01 — Execução majoritariamente manual

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Crawls, reconciliação, coverage e relatórios disparam via sessão humana; “sessão comercial” gera artefatos one-shot. |
| **Causa raiz** | Orquestração (`monitor.py` / `orchestrator.py`) e systemd units existem no repo, mas o **caminho feliz diário do consultor** não está codificado como um job idempotente com SLA. Dois orquestradores coexistem. |
| **ADR?** | Não exclusivo — depende de ADR-017 (workspace) + E3 (scheduled collection). |
| **Epic** | E3 Resilient scheduled collection · E4 Daily workspace |
| **Enabler status** | **PARCIAL** — código de crawl e units; **sem prova de operação contínua permanente** no baseline atual. |

### I-02 — Artefatos operacionais versionados / misturados ao git

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | `output/`, checkpoints, JSONL de crawl e dumps aparecem no working tree; confusão entre evidência de sessão e source of truth. |
| **Causa raiz** | Ausência de política explícita: o que é evidência auditável (docs/ops stamp) vs dado operacional (gitignore + object storage/local path). |
| **ADR?** | **Sim — ADR-020** Operational data not in git |
| **Epic** | E3 (política + paths) · transversal |
| **Enabler status** | **FALTA** política enforced; raw dumps já poluem árvore. |

### I-03 — Sem prova de scheduler permanente

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | 20 timer pairs no repo; auditoria 2026-07-14: 0 crawlers em operação contínua comprovada; VPS provision scripts nunca executados de ponta a ponta no readiness audit. |
| **Causa raiz** | Infra e app desacoplados no backlog; stories INFRA/OPS “ready” sem gate de evidência runtime (journalctl + last_success). |
| **ADR?** | Não (runbook + DoD de E3); complementa ADR-020. |
| **Epic** | E3 |
| **Enabler status** | **PARCIAL** — units existem; **prova permanente ausente**. |

### I-04 — Sem registry de fontes por entidade

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Registry de **fonte** (`scripts/crawl/registry.py`, 11 sources) existe; matriz **fonte × entidade × capability** não reconciliada (L1: PARTIAL/unknown). Impossível provar 95% operacional. |
| **Causa raiz** | Cobertura tratada como “fonte ativa global” em vez de “cada órgão tem canal de aquisição declarado”. |
| **ADR?** | **Sim — ADR-019** Entity source registry canonical |
| **Epic** | E2 Source registry & discovery |
| **Enabler status** | Schema/hints existem em stories DB-04; **dados por entidade não canônicos**. |

### I-05 — Provenance frágil / inconsistente

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Relatórios comerciais com `live_fetch: false` + attestation; content-hash checkpoint binding recente; dois hashes de conteúdo (adapter vs transformer) no adversarial QA. |
| **Causa raiz** | Provenance tratada como afterthought de relatório, não como first-class no pipeline raw→canonical. |
| **ADR?** | Parcialmente ADR-021 (adapter contract); schema DB-02. |
| **Epic** | E3 · E1 (coverage evidence) |
| **Enabler status** | **PARCIAL** — evidence ledger migration existe; uso inconsistente. |

### I-06 — Entity resolution incompleta

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Histórico de 604 unresolved; matching CNPJ8; fundos vs prefeitura; múltiplos denominadores (1.093 / 1.448 / 2.085) já mitigados em parte (FIX-UNIVERSE) mas matching cross-source ainda gera órfãos. |
| **Causa raiz** | Universo planilha ≠ identidade de publicação nas fontes; falta hierarquia de entidades e aliases canônicos em escala. |
| **ADR?** | Não novo (universe decisions existentes); enforcement via E2/E6. |
| **Epic** | E2 · E6 |
| **Enabler status** | **PARCIAL** — matcher + seed; gaps residuais. |

### I-07 — Rate limits (PNCP 429) sem fail-closed global

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | PNCP sob carga gera 429; risco de janelas marcadas vazias ou parciais sem alerta bloqueante. |
| **Causa raiz** | Pacing/circuit breaker existem em partes; política **fail-closed** (não reportar sucesso com perda) não é contrato único de adapter. |
| **ADR?** | **Sim — ADR-021** Adapter architecture + PNCP 429 fail-closed |
| **Epic** | E3 |
| **Enabler status** | **PARCIAL** — pacing/cb código; política não unificada. |

### I-08 — Checkpoints incompletos / não unificados

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Checkpoints por fonte (`data/*_checkpoints/`) heterogêneos; resume nem sempre testado; DLQ parcial. |
| **Causa raiz** | Cada crawler evoluiu checkpoint local; B2G-DB-05/BACKFILL-03 não consolidaram runtime. |
| **ADR?** | Não (design em E3); alinha ADR-021. |
| **Epic** | E3 |
| **Enabler status** | **PARCIAL** |

### I-09 — Histórico de contratos insuficiente para 3 anos

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | `go_no_go_3y: NO-GO`; pilot 90d national incomplete; ~63k contracts cumulativos de runs parciais. |
| **Causa raiz** | Backfill nacional caro + rate limit + falta de plano por fatia (UF/órgão/janela) com prova de completude. |
| **ADR?** | Não (plano de backfill E6); depende ADR-021. |
| **Epic** | E6 Org history |
| **Enabler status** | **PARCIAL** — crawler + tabela; completude **não**. |

### I-10 — Supplier intelligence fraca

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Vencedores agregáveis; win-rate e “concorrência real” NOT_READY; resolução de CNPJ fornecedor inconsistente. |
| **Causa raiz** | Dados públicos = vencedores, não propostas; falta modelo honesto de limitação + entity resolution de suppliers. |
| **ADR?** | Não (produto E7); honestidade via capability matrix. |
| **Epic** | E7 |
| **Enabler status** | **PARCIAL / FALTA** métricas honestas. |

### I-11 — Modelos de preço ausentes

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Capability `prices` com **zero fontes** no L1 registry; ADR-002 existe como decisão, não como pipeline. |
| **Causa raiz** | Itens unitários não coletados em escala; objeto não normalizado. |
| **ADR?** | ADR-002 já cobre decisão de produto; execução E9. |
| **Epic** | E9 |
| **Enabler status** | **FALTA** |

### I-12 — Workspace / UX operacional inexistente como facade

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Consultor navega `local_datalake`, `opportunity_intel`, `monitor`, `contract_intel`, scripts avulsos. |
| **Causa raiz** | Crescimento bottom-up de CLIs sem contrato de “dia de trabalho”. |
| **ADR?** | **Sim — ADR-017** Workspace CLI facade |
| **Epic** | E4 |
| **Enabler status** | **FALTA** facade; módulos existem. |

### I-13 — Human feedback loop ausente

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Ranking/regras não aprendem com GO/NO-GO humano do Tiago; perfil cliente não é “lei” única. |
| **Causa raiz** | Scoring determinístico sem store de feedback; múltiplos perfis/configs implícitos. |
| **ADR?** | **Sim — ADR-022** Client profile as sole commercial law |
| **Epic** | E5 · E4 |
| **Enabler status** | **FALTA** |

### I-14 — Recall benchmark ausente

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Não há gold set de editais “que deveriam ter sido detectados” para medir recall real vs 95% claim. |
| **Causa raiz** | Cobertura definida por evidence ledger / presença de bid, não por amostragem adversarial de verdade de campo. |
| **ADR?** | Não — método em E1 (coverage contract inclui recall sample). |
| **Epic** | E1 |
| **Enabler status** | **FALTA** |

### I-15 — Failure recovery incompleto

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | OnFailure templates duplicados; DLQ parcial; restore nunca testado com Storage Box real (audit). |
| **Causa raiz** | Observabilidade e DR tratados como stories futuras; sem game-day. |
| **ADR?** | Não — E3 ops gate. |
| **Epic** | E3 |
| **Enabler status** | **PARCIAL** scripts; **não provado**. |

### I-16 — Divergência banco / arquivo / relatório

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | Manifest 265% histórico; covered_200km 52 vs commercial 116 vs combined 133; relatórios com attestation vs live_fetch. |
| **Causa raiz** | Múltiplas definições de numerador; relatórios leem artefatos stale; ausência de **contrato multi-métrica**. |
| **ADR?** | **Sim — ADR-018** Coverage contract multi-metric |
| **Epic** | E1 |
| **Enabler status** | Session 2026-07-17 **corrigiu headline 116** e list identity; contrato formal ainda a codificar. |

### I-17 — Backup / observabilidade não confiáveis

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | backup/restore scripts longos, sem teste real; health_check existe; métricas não alimentam alerta de negócio. |
| **Causa raiz** | Ops before product pressure; DR não no caminho crítico do consultor. |
| **ADR?** | Não (ops E3 / legado INFRA-04). |
| **Epic** | E3 |
| **Enabler status** | **PARCIAL** |

### I-18 — Dados locais stale como se fossem produção

| Campo | Detalhe |
|-------|---------|
| **Sintoma** | JSON em `output/` e DB local tratados como “a verdade” em briefings sem freshness gate bloqueante. |
| **Causa raiz** | Freshness gate existe mas não é hard-gate do workspace/relatório cliente. |
| **ADR?** | ADR-018 (métricas com as_of) + ADR-020 (paths) + E4 (workspace recusa stale). |
| **Epic** | E1 · E4 |
| **Enabler status** | **PARCIAL** — gate existe; não é UX default. |

---

## 3. Mapa impedimento → ADR → Epic

| Impedimento | ADR | Epic primário |
|-------------|-----|---------------|
| I-12 Workspace | **ADR-017** | E4 |
| I-16 / I-18 Métricas e stale | **ADR-018** | E1 |
| I-04 Registry entidade | **ADR-019** | E2 |
| I-02 Git pollution | **ADR-020** | E3 |
| I-07 / I-05 Adapter+429+provenance | **ADR-021** | E3 |
| I-13 Feedback / ranking law | **ADR-022** | E5 |
| I-01 Manual / I-03 Scheduler / I-08 CP / I-15 DR | (ADR-017/020/021) | E3 |
| I-06 Entity resolution | (existentes) | E2/E6 |
| I-09 Contract history | — | E6 |
| I-10 Suppliers | — | E7 |
| I-11 Prices | ADR-002 | E9 |
| I-14 Recall | ADR-018 | E1 |

---

## 4. Ordem de desbloqueio (adversarial)

```
E1 Coverage contract (ADR-018)     ───┐
E2 Entity source registry (ADR-019) ──┼──► desbloqueia prova de 95% e discovery
E3 Scheduled resilient collection  ───┤    (ADR-020, ADR-021)
       (fail-closed, checkpoints)     │
E4 Workspace facade (ADR-017)      ───┴──► torna operável para Tiago
E5 Opportunities + profile law (ADR-022)
E6…E13 capacidades comerciais derivadas
```

**Regra:** nenhuma capacidade C5–C9 é “pronta para proposta fechada” antes de E1–E4 fecharem o loop de verdade operacional.

---

## 5. Riscos residuais após E1–E5

| Risco | Residual se E1–E5 Done? |
|-------|-------------------------|
| Overselling 95% | **Baixo** se dual-metric enforced |
| PNCP rate limit | **Médio** — mitigado fail-closed, não eliminado |
| Histórico 3y | **Alto** até E6 |
| Preço/win-rate | **Alto** até E7/E9 |
| VPS/DR | **Médio** até game-day E3 |
| PDF/OCR edital | **Alto** até E10 |

---

## 6. Decisão arquitetural resumida

1. **Separar** `entities_with_recent_commercial_signal` de `operational_source_coverage`.
2. **Canonicizar** registry entidade→fonte antes de escalar crawls cegos.
3. **Fail-closed** em 429/zero-result ambíguo.
4. **Workspace** como única porta do consultor.
5. **Perfil cliente** como única lei de ranking.
6. **Dados operacionais fora do git**; evidências de sessão carimbadas em `docs/ops/` com hash, não dumps brutos.

---

## 7. Referências

- `docs/audits/audit-b2g-readiness-2026-07-14.md`
- `docs/audits/adversarial-coverage-qa-2026-07.md`
- `docs/ops/session-2026-07-17/coverage_canonical.json`
- `docs/baseline/l1-source-capability-registry.md`
- `docs/prd/capability-matrix-b2g-proposta.md`
- `docs/architecture/b2g-operational-target-architecture.md`
- ADRs 017–022 em `docs/architecture/adr/`
