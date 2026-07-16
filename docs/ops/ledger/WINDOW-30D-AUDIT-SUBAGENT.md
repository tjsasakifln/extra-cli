# Auditoria independente — Janela 30 dias úteis (ES &lt; 30)

**Auditor:** subagent (read-only evidence + parse `ep-data`)  
**Date:** 2026-07-16  
**Plano:** `extra-consultoria-plano-executivo.html` (`#ep-data`)  
**Comparado com:** `docs/ops/ledger/WINDOW-30D-COMPLETE.md`  
**Regra anti-fake:** path existe, não-vazio, conteúdo substantivo; claim no COMPLETE deve bater com artefato real  

---

## 1. Método

### 1.1 Parse de `ep-data`

- Extraído o array `tasks` do JSON embutido em `extra-consultoria-plano-executivo.html` (`#ep-data`).
- Campos usados por task: `id`, `title`, `o`, `m`, `p`, `deps`, `status`, `evidence`.

### 1.2 Duração PERT e ES (fórmula do HTML)

Código do plano (PERT P50):

```js
// durationFor (cenário pert)
Math.ceil((o + 4*m + p) / 6)
// schedule
es = deps.length ? Math.max(...deps.map(d => byId[d].ef)) : 0
ef = es + dur
```

Também calculado **PERT float** (sem `Math.ceil`) porque a lista de 24 do COMPLETE só fecha com essa variante.

### 1.3 Verificação de evidência

Para cada task da janela:

1. Path declarado no campo `evidence` do HTML (quando path-like).
2. Path canônico em `docs/baseline/*`, `docs/ops/ledger/*`, `docs/architecture/adr/*`, `config/*`, `output/*`.
3. Checagem: arquivo/dir existe; size &gt; 0; conteúdo não é placeholder vazio.
4. Flags: `STALE` (índice desatualizado), `PARTIAL` (runtime incompleto), `BLOCKED_EXTERNAL`, `CLAIM_MISMATCH`.

---

## 2. Resultado do CPM — quem entra em ES &lt; 30?

| Variante | Critério | # tasks | IDs |
|----------|----------|---------|-----|
| **HTML fiel** (`Math.ceil`) | `ES < 30` | **17** | G0.1–G0.5, L1.1–L1.7, C2.1–C2.2, V6.1–V6.2, I4.1 |
| **PERT float** (sem ceil) | `ES < 30` | **24** | + L1.8, C2.3–C2.6, K3.1, Q5.1 |
| **COMPLETE.md (claim)** | “24 tasks” | **24** | mesma lista float |

### 2.1 Tabela ES (HTML `Math.ceil` — fonte de verdade do plano)

| ID | o | m | p | dur=ceil((o+4m+p)/6) | deps | ES | EF | ES&lt;30? |
|----|---|---|---|----------------------|------|----|----|---------|
| G0.1 | 1 | 1 | 2 | 2 | — | 0 | 2 | **Y** |
| G0.2 | 2 | 3 | 5 | 4 | G0.1 | 2 | 6 | **Y** |
| G0.3 | 1 | 2 | 4 | 3 | G0.1 | 2 | 5 | **Y** |
| G0.4 | 1 | 2 | 4 | 3 | G0.2,G0.3 | 6 | 9 | **Y** |
| G0.5 | 1 | 1 | 2 | 2 | G0.4 | 9 | 11 | **Y** |
| L1.1 | 1 | 2 | 4 | 3 | G0.5 | 11 | 14 | **Y** |
| L1.2 | 3 | 4 | 7 | 5 | G0.5 | 11 | 16 | **Y** |
| V6.1 | 2 | 3 | 5 | 4 | G0.5 | 11 | 15 | **Y** |
| L1.3 | 3 | 4 | 7 | 5 | L1.1 | 14 | 19 | **Y** |
| V6.2 | 4 | 5 | 8 | 6 | V6.1 | 15 | 21 | **Y** |
| L1.4 | 3 | 4 | 7 | 5 | L1.2 | 16 | 21 | **Y** |
| I4.1 | 2 | 3 | 5 | 4 | G0.5,L1.2 | 16 | 20 | **Y** |
| L1.5 | 2 | 3 | 5 | 4 | L1.3,L1.4 | 21 | 25 | **Y** |
| C2.1 | 2 | 3 | 5 | 4 | L1.4 | 21 | 25 | **Y** |
| L1.6 | 4 | 5 | 8 | 6 | L1.5 | 25 | 31 | **Y** |
| L1.7 | 2 | 3 | 5 | 4 | L1.5 | 25 | 29 | **Y** |
| C2.2 | 3 | 4 | 7 | 5 | C2.1 | 25 | 30 | **Y** |
| L1.8 | 1 | 2 | 4 | 3 | L1.6,L1.7 | **31** | 34 | **N** |
| C2.3 | 6 | 8 | 13 | 9 | L1.8,C2.2 | **34** | 43 | **N** |
| C2.4 | 5 | 7 | 11 | 8 | L1.8,C2.2 | **34** | 42 | **N** |
| C2.5 | 5 | 7 | 11 | 8 | L1.8,C2.2 | **34** | 42 | **N** |
| C2.6 | 4 | 6 | 10 | 7 | L1.8,C2.2 | **34** | 41 | **N** |
| K3.1 | 3 | 4 | 7 | 5 | L1.8 | **34** | 39 | **N** |
| Q5.1 | 4 | 5 | 8 | 6 | L1.8 | **34** | 40 | **N** |

### 2.2 Discrepância metodológica (flag)

| Item | Status |
|------|--------|
| COMPLETE afirma **24** tasks com ES&lt;30 | **CLAIM_MISMATCH** vs algoritmo do próprio HTML (`Math.ceil`) que produz **17** |
| Lista de 24 = ES&lt;30 só se usar PERT **sem** `ceil` | Documentar no COMPLETE qual fórmula foi usada |
| Auditoria de evidência abaixo cobre as **24** do COMPLETE (wave claim) **e** marca as 7 com ES≥30 sob HTML | Transparência total |

---

## 3. Scorecard de evidência (24 do COMPLETE)

Legenda de `audit_status`:

| Status | Significado |
|--------|-------------|
| **DONE** | Artefato real, não-vazio, substantivo; claim de engenharia sustentado |
| **DONE_PARTIAL** | Artefato real, mas runtime/AC incompleto (documentado honestamente) |
| **BLOCKED_EXTERNAL** | Pacote eng. pronto; bloqueio humano/financeiro legítimo |
| **STALE_INDEX** | Evidência existe, mas índice/ledger agregador desatualizado |
| **GAP** | Sem evidência verificável |

| id | html_status | ES (ceil) | evidence_path_exists | audit_status | notes | residual_action |
|----|-------------|-----------|----------------------|--------------|-------|-----------------|
| G0.1 | evidence | 0 | **Y** | **DONE** | `DOD.md` (raiz, §1 com 2 `[x]`); HTML versionado; GATE-0 | Atualizar `evidence-index.md` Snapshot G0 (ainda diz PARTIAL/InProgress) |
| G0.2 | evidence | 2 | **Y** | **DONE** | `docs/baseline/rebaseline-2026-07-16.md` substantivo (HEAD, métricas, gaps) | Sync `evidence-index.md` (ainda OPEN) |
| G0.3 | evidence | 2 | **Y** | **DONE** | `docs/baseline/scope-freeze-95.md` (meta 95% canônica + claims proibidos) | Sync `evidence-index.md` (ainda OPEN) |
| G0.4 | evidence | 6 | **Y** | **DONE_PARTIAL** | Ledger existe (`docs/ops/ledger/*`); índice **stale** (G0.2/G0.3 OPEN) | Refresh `evidence-index.md` + README snapshot |
| G0.5 | evidence | 9 | **Y** | **DONE** | `docs/ops/ledger/raci-kickoff.md` com RACI/WIP | Ata formal Tiago = opcional (não bloqueia eng.) |
| L1.1 | evidence | 11 | **Y** | **DONE** | `docs/baseline/l1-env-prereqs.md` com comandos/resultados reais (python3/docker) | — |
| L1.2 | evidence | 11 | **Y** | **DONE** | `docs/baseline/l1-universe-reconciliation.md` — 2085/1093/992 | — |
| V6.1 | evidence | 11 | **Y** | **DONE** | ADR-007-v6.1 + `docs/baseline/v6.1-provider-decision.md` | — |
| L1.3 | evidence | 14 | **Y** | **DONE** | `docs/baseline/l1-fresh-migrations.md` — 54/54 + fix 049 documentado | Capturas `gate1-fresh-migrations.log` não versionadas (scratch) |
| V6.2 | blocked | 15 | **Y** | **BLOCKED_EXTERNAL** | Pacote `docs/ops/v6.2-procurement-credentials-package.md` + status baseline; HTML `blocked` correto | Tiago: conta/pagamento Netcup|Hetzner + credenciais SSH/backup |
| L1.4 | evidence | 16 | **Y** | **DONE_PARTIAL** | `docs/baseline/l1-source-capability-registry.md` — 11 fontes; matriz ente×fonte **PARTIAL** | Completar aplicabilidade por ente (fora janela 95%) |
| I4.1 | evidence | 16 | **Y** | **DONE** | `config/client_profiles/extra.yaml` v2 + baseline I4.1 | Preencher priority_organs/competitors (input comercial) |
| L1.5 | evidence | 21 | **Y** | **DONE** | Baseline + `crawl-*-gp-20260716-200904.json` (pcp fetched=181, compras_gov=2); Excel `output/excels/panorama-SC-2026-07-16.xlsx` | `gp-20260716-200904.log` **vazio/ilegível** — preferir JSON crawl+ledger como prova; regenerar log se quiser paridade |
| C2.1 | evidence | 21 | **Y** | **DONE_PARTIAL** | `docs/baseline/c2-coverage-formulas.md` — auditoria fórmulas vs código; gaps de implementação HIGH-RISK listados | Story de implementação split capability + freshness no numerador |
| L1.6 | evidence | 25 | **Y** | **DONE** | `docs/baseline/l1-resume-dlq-smoke.md` — 8+5 tests pass | — |
| L1.7 | evidence | 25 | **Y** | **DONE** | `docs/baseline/l1-backup-restore.md` — restore_drill 60 tables / 2085 universe | Storage Box remoto fora do escopo |
| C2.2 | evidence | 25 | **Y** | **DONE_PARTIAL** | `docs/baseline/c2-success-zero-freshness.md` — código/constraints/testes; SLA gaps documentados | Alinhar SLA contracts 24h vs 7d se DoD exigir |
| L1.8 | evidence | **31** | **Y** | **DONE_PARTIAL** | `GATE-1-LOCAL-FOUNDATION.md` — “PARTIAL → majoritariamente PASS”; **não** LOCAL_READY | Não declarar LOCAL_READY; refresh manifesto se HEAD mudar |
| C2.3 | evidence | **34** | **Y** | **DONE_PARTIAL** | `docs/baseline/c2-pncp-runtime.md` — código+049 OK; **API timeout** documentado | Rerun quando PNCP estável; não fingir e2e online |
| C2.4 | evidence | **34** | **Y** | **DONE** | `docs/baseline/c2-pcp-tce-runtime.md` — TCE n=65970; PCP OK em golden path | Matching 1093 = C2.10+ |
| C2.5 | evidence | **34** | **Y** | **DONE** | CIGA público unblocked + runtime JSON `output/ciga-ckan/runtime-domsc-publicacoes-de-12-2025.json` (533 pubs, status OK) | Path legado `dom_sc` auth continua BLOCKED (esperado) |
| C2.6 | evidence | **34** | **Y** | **DONE** | `docs/baseline/c2-comprasgov-runtime.md` + crawl compras_gov no GP | — |
| K3.1 | evidence | **34** | **Y** | **DONE** | `docs/baseline/k3-contract-schema-semantics.md` — inventário schema/semântica | K3.2+ (backfill 3y) fora da janela |
| Q5.1 | evidence | **34** | **Y** | **DONE** | `docs/baseline/q5-critical-tests.md` — **82 PASS** (suite expandida); lint paths críticos OK | **CLAIM_MISMATCH** COMPLETE/HTML dizem “21 PASS” — atualizar claims para 82 |

---

## 4. Totais honestos

| Métrica | Valor |
|---------|-------|
| Tasks no COMPLETE (claim janela) | 24 |
| Tasks com ES&lt;30 sob HTML `Math.ceil` | **17** |
| Tasks com path de evidência existente e não-vazio | **24/24** |
| **DONE** (engenharia fechada, sem partial material) | **14** |
| **DONE_PARTIAL** (evidência real, limitação honesta) | **9** |
| **BLOCKED_EXTERNAL** | **1** (V6.2) |
| **GAP** (zero evidência) | **0** |
| Fake evidence (path inventado / arquivo vazio como única prova) | **0** (exceto log GP vazio, compensado por JSON crawl) |
| Stale aggregator | **1** (`evidence-index.md` Snapshot GATE-0 desatualizado) |

### Interpretação “truly DONE”

Se “truly DONE” = claim de fechamento de engenharia **sem** partial material e **sem** bloqueio externo:

- **14/24** estritamente DONE  
- **+9** DONE_PARTIAL (ainda fechados para a janela de campanha, com ressalvas)  
- **+1** BLOCKED_EXTERNAL (V6.2)  

Se “fechado na janela” = COMPLETE (23 eng + 1 blocked externo): **aceito com ressalvas**, **não** “grande parte sem prova” — há artefatos reais. O risco é **overclaim** (ES fórmula, Q5 21 vs 82, índice stale, C2.1/C2.2 documentais ≠ implementados end-to-end).

---

## 5. COMPLETE.md vs realidade

| Claim em `WINDOW-30D-COMPLETE.md` | Realidade auditada |
|-----------------------------------|--------------------|
| 24 tasks na janela ES&lt;30 | **Parcialmente falso** sob fórmula do HTML (`ceil` → 17). Verdadeiro sob PERT float. |
| 23/24 engenharia completa | **Sustentável** se DONE+DONE_PARTIAL contam; **não** se só DONE estrito (14) |
| V6.2 blocked_external + pacote READY | **Confirmado** |
| Q5.1 “21 PASS” | **STALE** — baseline atual: **82 PASS** |
| L1.5 `gp-20260716-200904` | Crawl JSON OK; log `.log` vazio; Excel existe |
| C2.3 “API timeout residual” | **Confirmado** no baseline |
| C2.4 TCE n=65970 | **Confirmado** no baseline |
| “Planned residual na janela: 0” | **OK** para eng; residual é V6.2 humano + follow-ups partial |
| “Não declara LOCAL_READY / 95% / PROJECT_DONE” | **Correto e importante** |

### Artefatos stale / incoerentes (não são fake de task, mas poluem fechamento)

1. **`docs/ops/ledger/evidence-index.md`** — Snapshot GATE-0 ainda OPEN/PARTIAL para G0.2–G0.5 apesar dos baselines existirem.  
2. **COMPLETE / HTML evidence text Q5.1** — “21 PASS” vs `q5-critical-tests.md` 82 PASS.  
3. **Definição ES&lt;30** — COMPLETE não documenta se usou `ceil` ou float.  
4. **L1.5 log file** — `output/golden-path/gp-20260716-200904.log` vazio; usar JSON de crawl como evidência primária.  
5. **State AIOX** — várias stories PE-* `Done` com `qa_verdict: CONCERNS` (ok se documentado; não confundir com PASS limpo).

---

## 6. Fake / anti-padrões checados

| Anti-padrão | Resultado |
|-------------|-----------|
| Path no COMPLETE sem arquivo no HEAD | **Não encontrado** para as 24 |
| Arquivo 0 bytes como única prova | Só log GP vazio; **não** única prova (JSON+baseline) |
| “Código no HEAD” sem doc/run | C2.3 declara timeout em vez de fake green — **honesto** |
| Claim 95% / LOCAL_READY na janela | **Não** no COMPLETE — bom |
| evidence-index como se fosse DONE de seção DoD | Ainda OPEN em seções ROL1 — **não promove DoD indevidamente** (bom), mas snapshot G0 stale |

---

## 7. Residual actions (priorizadas)

| # | Ação | Owner sugerido | Bloqueia eng. da janela? |
|---|------|----------------|--------------------------|
| 1 | Documentar no COMPLETE a fórmula ES usada (ceil vs float) e alinhar contagem 17 vs 24 | PO | Não (clareza) |
| 2 | Atualizar `evidence-index.md` Snapshot GATE-0 com paths DONE | Dev/PO | Não |
| 3 | Atualizar claim Q5.1 para 82 PASS (HTML + COMPLETE) | Dev | Não |
| 4 | Tiago: V6.2 contratação/credenciais | Tiago | Sim para VPS |
| 5 | Regenerar/remover log GP vazio; apontar JSON crawl | Dev | Não |
| 6 | Follow-ups C2.1/C2.2 implementação (HIGH-RISK) | Data Eng | Sim para 95% / LOCAL_READY |
| 7 | PNCP e2e quando API estável (C2.3 residual) | Data Eng | Sim para editais 95% |

---

## 8. Veredito final do subagent

| Pergunta | Resposta |
|----------|----------|
| Todas as 24 têm evidência real no HEAD? | **SIM** (paths existem e são substantivos) |
| Todas “truly DONE” sem ressalva? | **NÃO** — 14 DONE + 9 DONE_PARTIAL + 1 BLOCKED_EXTERNAL |
| COMPLETE é fake / “grande parte”? | **NÃO fake** — overclaim de contagem ES e de “21 PASS”; engenharia majoritariamente real |
| Pode fechar a janela 30d em engenharia? | **SIM com ressalvas documentadas** (igual espírito do COMPLETE) |
| Pode declarar LOCAL_READY / 95% / PROJECT_DONE? | **NÃO** |

**Score resumido:** `14 DONE strict · 9 DONE_PARTIAL · 1 BLOCKED_EXTERNAL · 0 GAP` sobre as 24 do COMPLETE; `17` estritamente ES&lt;30 sob fórmula HTML com `Math.ceil`.

---

## 9. Arquivos consultados (amostra)

- `extra-consultoria-plano-executivo.html` (`#ep-data` tasks G0–Q5/V6)
- `docs/ops/ledger/WINDOW-30D-COMPLETE.md`
- `docs/ops/ledger/GATE-0-BASELINE-LOCKED.md`, `GATE-1-LOCAL-FOUNDATION.md`, `evidence-index.md`, `raci-kickoff.md`
- `docs/baseline/{rebaseline,scope-freeze-95,l1-*,c2-*,i4.1-*,k3-*,q5-*,v6.*}`
- `docs/architecture/adr/ADR-007-v6.1-provider-decision.md`
- `docs/ops/v6.2-procurement-credentials-package.md`
- `config/client_profiles/extra.yaml`
- `output/golden-path/crawl-*-gp-20260716-200904.json`, `output/ciga-ckan/runtime-*.json`, `output/excels/panorama-SC-2026-07-16.xlsx`
- `.aiox/state/stories/PE-*.json` (amostra)

**Sem git push.** Este arquivo é o único deliverable obrigatório da auditoria.
