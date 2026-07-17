# QA Review - Technical Debt Assessment

**Versão:** 3.0  
**Data:** 2026-07-17  
**Revisor:** Quinn (@qa)  
**Documentos de referência:**
- `docs/prd/technical-debt-DRAFT.md` v3.0 DRAFT (Aria)
- `docs/reviews/db-specialist-review.md` v3.0 (Dara)
- `docs/reviews/ux-specialist-review.md` v3.0 (Uma)
- `docs/reviews/qa-review.md` v2.0 (2026-07-13) — continuidade
- Fontes cruzadas: `system-architecture.md` v3 · `DB-AUDIT.md` v3 · `frontend-spec.md` v3 · Stories 1.1–1.5

**Postura:** adversarial independente — não rubber-stamp. Débitos abertos **não** impedem aprovação se a estrutura permite planejamento.

---

## Gate Status: APPROVED WITH CONDITIONS

**Veredicto:** **APPROVED WITH CONDITIONS**

O DRAFT v3.0 **fecha os gaps estruturais CRITICAL** que bloquearam a v2 (GAP-001 Segurança, GAP-002 Testes/QA) e adiciona categorias que a v2 pediu (OBS, DEP, DOC/ENV). Pre-VPS blockers estão **explícitos** (SYS-001…006 + SEC-02 + schema truth + TQ-07). Especialistas DB e UX validaram o inventário com ajustes rastreáveis. Muitos débitos permanecem abertos — isso é o **propósito** do assessment, não falha de gate.

**Condições obrigatórias para o assessment FINAL (Phase 8 @architect):**

| # | Condição | Owner | Severidade |
|---|----------|-------|------------|
| C1 | Incorporar ajustes de horas/fusões DB (DT-24+33, DT-23→6h, DT-21 reintro, DT-35 residual secrets deploy, DT-28+34) | @architect + @data-engineer | **MUST** |
| C2 | Incorporar re-elevações UX (UX-02 CRITICAL *ops*, UX-04 HIGH) + IDs UX-19…22 | @architect + @ux | **MUST** |
| C3 | Manter SEC-02 / TD-029 como **P0 STILL OPEN** até arquivo ausente + gitignore + rotação se exposto (Story 1.1 Done **não** fecha residual) | @architect / @dev story | **MUST** |
| C4 | Registrar **dívida residual de verificação live**: DB offline 2026-07-17 → nenhum RESOLVED de integridade de *dados* é claim de produção | @architect | **MUST** |
| C5 | Responder formalmente as 6 perguntas @qa (§11 DRAFT) no FINAL (respostas desta review §“Respostas QA”) | @architect | **SHOULD** |
| C6 | Não habilitar claim `VPS_OPERATIONAL` / timers oficiais enquanto SYS-001/002 + TQ-07 abertos | @devops / @pm | **MUST** (processo) |

**NEEDS WORK seria exigido se:** faltassem categorias SEC/TQ, pre-VPS implícitos, contradições irreconciliáveis de prioridade, ou claims CRITICAL sem evidência. **Nada disso permanece.**

---

## 1. Critérios de gate (checklist)

| Critério | Status | Evidência |
|----------|--------|-----------|
| Categoria **Segurança** presente | ✅ | DRAFT §4 SEC-01…08 |
| Categoria **Testes/QA** presente | ✅ | DRAFT §5 TQ-01…07 |
| Cross-risks identificados | ✅ | DRAFT §12 + esta review §3 |
| Dependências entre débitos fazem sentido | ✅ | DRAFT §10 grupos; Dara/Uma validam; ajustes menores abaixo |
| Pre-VPS blockers explícitos | ✅ | DRAFT §1.1 + §9.1 (SYS-001…006, SEC-02, DT-23/24/33, TQ-02/07, UX ops) |
| Inputs de especialistas incorporados ou pending claros | ✅ | Reviews v3 completas; pending = merge no FINAL (C1/C2) |
| Gaps v2 CRITICAL (GAP-001/002) endereçados | ✅ | Ver §5 Coverage of previous v2 QA gaps |
| Métricas honestas (M1 ≠ M2) | ✅ | SYS-008 M2=0%; UX-14; OBS-03; honesty principle |
| Dual runtime / split-brain como risco de sistema | ✅ | SYS-001/002 P0 CRITICAL |
| SEC-02 residual trackeado | ✅ | STILL OPEN ⚠ + verificação 2026-07-17: arquivo **presente** |
| Live DB offline → residual verification | ✅ | Dara disclaimer + DT-25/33 + ENV-01 |

---

## 2. Gaps Identificados

Lacunas **não estruturais** (não bloqueiam APPROVED; devem constar no FINAL ou backlog).

| # | Gap | Área | Severidade | Recomendação |
|---|-----|------|------------|--------------|
| **GAP-v3-001** | Especialistas ainda **não mesclados** no DRAFT (marcadores ⚠️ PENDENTE nas §2 e §3) | Processo | **HIGH** (processo) | Phase 8: assessment FINAL absorve Dara/Uma; remover “PENDENTE” |
| **GAP-v3-002** | Contagem de IDs ~133 com **cross-refs** (OBS≈SYS, TQ-06≈DT-28, DOC≈DT) — risco de double-count em roadmap de horas | Gestão | MEDIUM | FINAL: tabela “IDs canônicos vs aliases” + esforço **sem** somar aliases |
| **GAP-v3-003** | Métricas de sucesso pós-resolução **por débito P0** ainda implícitas (ondas sim; DoD mensurável parcial) | Qualidade | MEDIUM | Para cada P0 da §9.1: 1 métrica binária de “fechado” (ex.: SYS-001 = 0 writers FS-only em path oficial) |
| **GAP-v3-004** | Threat model (SEC-06) e secrets strategy (SEC-05) abertos — aceitável pré-VPS, mas **SEC-02 aberto + defaults deploy** (DT-35) eleva risco composto | Segurança | HIGH (item), não gap estrutural | Onda 0: SEC-02 + DT-35 antes de qualquer provisionamento |
| **GAP-v3-005** | Baseline de cobertura real (`pytest --cov`) **não impressa** no DRAFT — só threshold 10% | Testes | MEDIUM | FINAL: 1 tabela com % atual por pacote crítico (`crawl/`, `opportunity_intel/`, `ops/`, `schema/`) se medível offline |
| **GAP-v3-006** | TQ-02 “P0 pré-VPS” vs esforço 2h: subir threshold **sem** testes novos pode falhar CI de forma cega | Testes | MEDIUM | Progressivo 10→30→45→60 **com** allowlist de pacotes; ver respostas QA |
| **GAP-v3-007** | DT-07 marcado RESOLVED* no DRAFT enquanto residual **ativo** em deploy/seed (Dara DT-35) | Database / Sec | MEDIUM | FINAL: DT-07 = PARTIAL; DT-35 explícito |
| **GAP-v3-008** | Sem inventário de **falsos verdes F1–F7** como checklist versionado no assessment (existe no audit pré-VPS) | Ops / QA | LOW→MED | Anexar ou linkar F1–F7 no FINAL + TQ-07 |

**Nenhum gap CRITICAL estrutural novo** no sentido v2 (categoria ausente / planning impossível).

---

## 3. Riscos Cruzados

| Risco | Áreas Afetadas | Severidade | Mitigação |
|-------|----------------|------------|-----------|
| **CR-v3-001** Split-brain FS vs PostgreSQL (SYS-001) + dual systemd (SYS-002) | Sistema, DB, Obs, Deploy | **CRITICAL** | Onda 0: writer único (preferência Dara **B** — monitor único writer); freeze timers `extra-crawl-*` até fechamento; TQ-07 fail-closed |
| **CR-v3-002** Health “healthy” com fixtures (SYS-003) + SLA hardcoded (SYS-004) + UX-17 humano cego | Sistema, Obs, UX | **CRITICAL** | OBS-01/02 + claim/mode/environment; fixture **nunca** pinta live; UX-17 `--human` com mesmos exit codes |
| **CR-v3-003** Credenciais compostas: SEC-02 SA JSON **presente** + DT-35/`smartlic_local` em deploy + residual git | Segurança, Deploy, DB | **CRITICAL** | SEC-02 P0 imediato (não FAST); DT-35 fail-closed `${PG_PASSWORD:?}`; re-scan `git grep` / history |
| **CR-v3-004** Schema dump 07-14 ≠ HEAD 043–054 (DT-24/33) + dual track (DT-23) + diagnostics mentirosos (DT-28) | Database, Docs, CI | **HIGH** | Story P0 única: verify `_migrations` + regen dump/SHA + política `db/setup_db.sh` only |
| **CR-v3-005** M1 (sinal comercial) lido como M2 (cobertura) ou como GO | Produto, UX, Comercial | **HIGH** | UX-14 P0 ops + OBS-03; M2=0% honesto (SYS-008); disclaimer fixo no workspace |
| **CR-v3-006** Refactor TD-010/monitor sem TQ-04 | Sistema, Crawl prod | **HIGH** | Integração mínima por fonte **antes** de fatiar monitor; SYS-001 primeiro |
| **CR-v3-007** Interpretar `LOCAL_RESILIENCE_READY` = VPS operacional / 95% coverage | Gestão, Ops | **HIGH** | TQ-07 + docs honesty; claim separado no health |
| **CR-v3-008** Onda 0 multi-área sem sequenciamento (SEC + SYS + DT + TQ) | Gestão | MEDIUM | Sequência DRAFT §10: secrets/checkpoint → health → writer único → schema → gates; UX Onda 1 em paralelo seguro (UX-02) |
| **CR-v3-009** Live DB offline → RESOLVED de dados superestimados | Database, QA | MEDIUM | Dívida residual explícita; smoke obrigatório ao subir Postgres (DT-25/33) |

### Continuidade riscos v2

| Risco v2 | Estado em v3 |
|----------|--------------|
| CR-001 monitor.py quebra crawlers | **Mitigado em prioridade** (TD-010 após SYS-001; estimativa 20h); risco residual = CR-v3-006 |
| CR-002 credenciais compostas | **Ainda ativo** como CR-v3-003 (SEC-02 **confirmado presente** nesta sessão) |
| CR-003 DT-02 migration v3 sem rollback | **Resolvido no eixo** (DT-02 RESOLVED); residual vira DT-32 rollback 043–054 (P2) |
| CR-004 UX-01 bloqueado por ORM/CI | **CI resolvido (TD-028)**; UX-01 DEFERRED pós-VPS — risco rebaixado |
| CR-005 Sprint 0 sem coordenação | Substituído por **Ondas 0–4** — melhor; ainda exige disciplina de freeze VPS |

---

## 4. Dependências Validadas

### 4.1 Grupos do DRAFT §10 — veredito QA

| Grupo | Cadeia | Veredito | Notas |
|-------|--------|----------|-------|
| Pre-VPS Truth | SYS-005/006 → SYS-003/004 → SYS-001/002 → TQ-07 → ENV-02 | ✅ **CONFIRMADO** | Ordem correta: não unificar runtime com checkpoint/success mentirosos |
| Schema | DT-33 → DT-24 → DT-23/DOC-01 → DT-28/29 → DT-25 | ✅ **CONFIRMADO** | Dara: fundir DT-24+33 em **uma** story; DT-23 **6h** |
| Segurança | SEC-02 → SEC-05 → SEC-06; SEC-01 ∥ SEC-04 | ✅ **CONFIRMADO** | SEC-02 **não** depende de schema; pode ser #1 absoluto |
| Runtime unificado | SYS-001/002 → TD-010 → TD-011/001 → SYS-008 | ✅ **CONFIRMADO** | Alinha preferência Dara (B) writer único |
| UX ops | UX-02 ∥ UX-17 ∥ UX-14 → UX-04 → UX-03/15 → UX-01 | ✅ **CONFIRMADO** + **fortalecido** por Uma | UX-17 depende de honesty health (SYS-003/004) para não greenwash; UX-02 **independente** |

### 4.2 Ajustes exigidos no FINAL

| Relação | Ajuste | Fonte |
|---------|--------|-------|
| DT-24 + DT-33 | **Uma story** “verify HEAD + regen dump” (2–2.5h), não 1+1 isolados | Dara |
| DT-28 + DT-29 + DT-34 | Um PR tooling schema (4–5h) | Dara |
| DT-07 residual + DT-35 | Uma story higiene DSN defaults deploy/seed | Dara |
| SYS-001 desenho | Target **(B)** monitor único writer; (C) dual-write só ≤1 sprint | Dara |
| UX-02 | Prioridade execução P0 ops #1 UX; tag CRITICAL ops vs HIGH inventário — documentar dual-label se necessário | Uma |
| UX-17 | **Depende** de claims honestos (SYS-003/004); implementação UI pode paralelizar, mas DoD inclui “sem verde de fixture” | Uma + QA |
| TQ-06 = DT-28 | Alias explícito — **não** somar horas duas vezes | QA |
| OBS-01/02 ≈ SYS-003/004 | Alias ou “work package” único health honesty | QA |

### 4.3 Ciclos

**Nenhum ciclo de dependência** identificado. Topologia das Ondas 0–4 é viável.

### 4.4 Bloqueios não mapeados (leves)

1. **DT-35** deve entrar na Onda 0 ao lado de SEC-02 (DRAFT lista SEC-02 mas subestima defaults de **deploy/**).  
2. **UX-21** (sumário pós-comando, add Uma) não está no DRAFT §9.1 — incluir Onda 1.  
3. **TQ-04 antes de TD-010** está no risco, mas não como aresta formal na matriz — formalizar.

---

## 5. Coverage of previous v2 QA gaps (GAP-001…)

| Gap v2 | Severidade v2 | Status em v3 | Evidência | Residual |
|--------|---------------|--------------|-----------|----------|
| **GAP-001** Segurança como categoria | CRITICAL | ✅ **FECHADO** | DRAFT §4 SEC-01…08; CI bandit+pip-audit (SEC-04 PARTIAL) | SEC-02 STILL OPEN; SEC-05/06 OPEN; DT-35 residual |
| **GAP-002** Testes/QA como categoria | CRITICAL | ✅ **FECHADO** | DRAFT §5 TQ-01…07; TQ-07 truth gate | Baseline % real não impressa (GAP-v3-005); threshold 10% |
| **GAP-003** Documentação | HIGH | ✅ **FECHADO** (estrutura) | DRAFT §8 DOC-01…05 | Conteúdo ainda OPEN — esperado |
| **GAP-004** Performance / observabilidade | HIGH | ✅ **FECHADO** (estrutura) | DRAFT §6 OBS-01…07 | Perf live N/A (DB offline) |
| **GAP-005** Dependências externas | HIGH | ✅ **FECHADO** | DRAFT §7 DEP-01…07 | BLOCKED DEP-02 ICP-Brasil documentado |
| **GAP-006** Ambientes | MEDIUM | ✅ **FECHADO** | ENV-01…04 + SYS-002/009 | VPS não provisionada (ENV-02) |
| **GAP-007** Métricas pós-resolução | MEDIUM | ⚠️ **PARCIAL** | Ondas + critérios Uma/Dara; não 1:1 por P0 | GAP-v3-003 |
| **GAP-008** TD-010 8h subestimado | MEDIUM | ✅ **FECHADO** | TD-010 = **20h**; após unificar runtime | — |
| **GAP-009** TD-025 ORM sem análise | MEDIUM | ⚠️ **ACEITO como P3** | 20h+ P3; “só se multi-app/web” | Suficiente para planning; não reabrir como CRITICAL |

**Conclusão de continuidade:** os **2 CRITICAL** que geraram NEEDS WORK na v2 estão **estruturalmente resolvidos**. Gate v2 → v3 evolui de **NEEDS WORK** para **APPROVED WITH CONDITIONS**.

---

## 6. Validações específicas da missão

### 6.1 Residual SEC-02 / SA JSON apesar de Story 1.1 Done

| Check | Resultado |
|-------|-----------|
| Tracked no DRAFT? | ✅ **SEC-02 / TD-029 STILL OPEN ⚠ P0** |
| Story 1.1 Done implica fechado? | ❌ **Não** — regressão de claim vs working tree |
| Verificação 2026-07-17 | ✅ `config/mides-bigquery-sa.json` **PRESENTE** (2370 bytes) |
| Ação recomendada | **Nova story HIGH-RISK** (ou reabrir 1.1 residual): remove arquivo + `.gitignore` + rotação se chave foi commitada + prova `git grep` limpo. **Proibido FAST** (secrets). |

### 6.2 Live DB offline → residual verification debt

| Check | Resultado |
|-------|-----------|
| Declarado por Dara? | ✅ Disclaimer forte no review DB |
| Tracked? | ✅ DT-25, DT-33, ENV-01, OBS-05 (perf live N/A) |
| Impacto em RESOLVED DT-* | RESOLVED de **DDL/dump/código** OK com confiança alta; integridade de **dados** e `_migrations` real = **hipótese HIGH** até smoke |
| Condição de gate | C4 — FINAL deve dizer explicitamente: “verify when DB up” |

### 6.3 Dual runtime / split-brain como system risk

| Check | Resultado |
|-------|-----------|
| Inventário | ✅ SYS-001, SYS-002 **P0 CRITICAL NEW** |
| Cross-risk | ✅ CR-v3-001 |
| Preferência de desenho | Dara: **(B)** writer único via monitor |
| Bloqueio VPS | ✅ ENV-02 / timers oficiais **após** Onda 0 |

### 6.4 Métricas honestas (M1 vs M2)

| Métrica | Claim v3 | Honesty |
|---------|----------|---------|
| M1 sinal comercial | 116/1.093 (10,61%) | ✅ número de ranking, não “coverage” |
| M2 cobertura operacional estrita | **0/1.093 (0%)** | ✅ **honesto** — meta 95% é alvo, não claim |
| LOCAL_RESILIENCE_READY | READY mecânica local | ✅ separado de VPS e de 95% |
| UX-14 / OBS-03 | PARTIAL — docs sim, CLI fraco | ✅ tracked P0 ops |

**Veredito:** inventário **não** infla cobertura. Isso é progresso metodológico vs v2.

---

## 7. Testes Requeridos (pós-resolução de débitos P0)

| Débito P0 | Tipo de teste | Critério de aceite (binário) |
|-----------|---------------|------------------------------|
| **SYS-001** | Integração path de persistência | Path oficial grava evidência em PostgreSQL (não só FS); 0 “success” sem row/evidence esperada |
| **SYS-002** | Inventário systemd + smoke | Uma família de units “oficial”; legados disabled ou documentados non-prod; health reporta runtime |
| **SYS-003 / OBS-01** | Unit + CLI health | Fixture mode **nunca** overall=healthy com `claim=operational_live`; campos mode/environment/fixture presentes |
| **SYS-004 / OBS-02** | Unit SLA | Freshness thresholds lidos de registry/`coverage_slas.yaml`; divergência hardcoded removida ou fail-closed |
| **SYS-005** | Unit checkpoint | Schema inválido → erro (não `pass`); TypeError não engolido |
| **SYS-006** | Unit adapter CIGA | Adapter **não** marca success de pipeline; só orquestrador/writer |
| **SEC-02 / TD-029** | Security grep + CI | `test ! -f config/mides-bigquery-sa.json`; pattern SA JSON em `.gitignore`; pipeline limpa |
| **DT-23** | Fresh-install doc test | Apply **somente** via `db/setup_db.sh`; legacy script fail-closed sem `ALLOW_LEGACY` |
| **DT-24 + DT-33** | Schema smoke | `_migrations` max version == HEAD; dump contém objetos 043–054; diagnostics exit 0 |
| **TQ-02** | CI gate | Threshold progressivo documentado; CI vermelho se abaixo do patamar da branch policy |
| **TQ-07** | Gate Makefile/CI | `pre-vps-final-gate` **FAIL** (não warn) se SYS-001/002 abertos **quando** claim VPS/timers |
| **UX-02** | CLI manual + smoke | update/radar/crawl/PDF exibem progresso; overhead &lt; 1s perceptível |
| **UX-14** | CLI snapshot | Seções M1 e M2 distintas; disclaimer; GO color ≠ coverage % |
| **UX-17** | CLI | `--human` tabela + exit codes idênticos ao JSON |

### 7.1 Cobertura mínima antes de TD-010 (resposta TQ-04)

| Fonte | Mínimo de integração | Notas |
|-------|----------------------|-------|
| PNCP | 1 happy path insert/upsert + 1 failure mode | Caminho canônico pós-SYS-001 |
| CIGA | 1 adapter contract test (sem success prematuro) | Cobre SYS-006 |
| SC Compras | 1 snapshot/hash ou skip explícito se SYS-007 aberto | Não bloquear se fora do writer unificado |
| Regressão monitor | Suite existente 100% verde + snapshot contagens se DB up | CR-v3-006 |

---

## 8. Respostas QA às perguntas do Architect (§11)

### Q1 — TQ-02: threshold progressivo e denominator

**Resposta:** progressivo **10% → 30% → 45% → 60%** em PRs separados (não big-bang).

| Etapa | Threshold | Denominator | Pré-condição |
|-------|-----------|-------------|--------------|
| Agora | 10% | status quo CI | — |
| +1 | **30%** | preferencialmente `scripts/` (omitir testes de fixtures pesados se necessário) | baseline medido |
| +2 | **45%** | `scripts/` | TQ-03 gaps buyer/contract parcialmente fechados |
| Alvo | **≥60%** | `scripts/` crítico (`crawl`, `opportunity_intel`, `ops`, `schema`, `coverage`) | pós Onda 2 |

**Não** incluir monólitos legados top-level `generate-report-b2g.py` no denominator inicial (distorce). Documentar omit list.

### Q2 — TQ-07: fail vs warn se SYS-001/002 abertos

**Resposta: FAIL** quando o gate é usado para autorizar **claim VPS / enable de timers oficiais**.  
**WARN** apenas em modo `offline developer convenience` se explicitamente `ALLOW_PRE_VPS_WARN=1` (fail-open **nunca** default).

`LOCAL_RESILIENCE_READY` pode permanecer true com dual runtime **somente** se o claim name **não** for `VPS_OPERATIONAL`.

### Q3 — SEC-02: Story 1.1 Done vs arquivo presente

**Resposta: nova story HIGH-RISK** (ou “1.1 residual security”) — **não FAST**, **não** só doc.  
Story 1.1 Done com residual é **débito de processo**; o inventário já marca STILL OPEN corretamente. DoD: arquivo ausente + gitignore + evidência de não-uso em CI + rotação se aplicável.

### Q4 — TQ-04 antes de TD-010

**Resposta: sim** — ver §7.1. Mínimo: PNCP + CIGA contract + suite verde. Sem isso, TD-010 = **FAIL gate** se tentado.

### Q5 — Falsos verdes F1–F7

**Resposta:** checklist adversarial F1–F7 vira **gate de release pré-VPS** (subset CRITICAL = SYS-001…006), não só doc.  
Modo: job/make target que falha em regressão de falso verde; LOW items (F7 etc.) podem ser warn.

### Q6 — Re-extração Reversa após SYS-001/002

**Resposta: SIM, recomendar** re-extração `_reversa_sdd` de crawl/resilience/ops **após Done** da unificação de runtime — não automático; follow-up de story (protocolo AIOX-Reversa §9). Motivo: contratos de persistência e C4 containers mudam de verdade.

---

## 9. Cobertura do Assessment (v3)

| Área | Cobertura | Notas |
|------|-----------|-------|
| Sistema / Pre-VPS | **95%** | SYS-001…015 + TD legado; honestidade pré-VPS excelente |
| Database | **90%** | Dara valida; +DT-21/35; live offline residual |
| Frontend/UX | **95%** | Uma completa; CLI-first correto; UX-19…22 adds |
| Segurança | **80%** | Categoria existe; SEC-02 ainda aberto; threat model futuro |
| Testes/QA | **75%** | Categoria existe; falta baseline % impresso |
| Observabilidade | **80%** | OBS cobrem health/SLA/M1M2; perf live N/A |
| Dependências externas | **85%** | DEP + gotchas alinhados |
| Docs / Ambientes | **80%** | DOC/ENV presentes e linkados a DT/SYS |
| DevOps/CI | **70%** | TD-028 RESOLVED; freeze timers e secrets VPS ainda perguntas @devops |

**vs v2:** Segurança 15%→**80%**; Testes 20%→**75%**. Mudança **estrutural** suficiente para gate.

---

## 10. Incorporação dos especialistas (resumo QA)

### Dara (DB) — aceitar no FINAL

- Horas abertas DB ≈ **46h** (não 30–35h)  
- Must-fix pré-VPS DB ≈ **12–14h**  
- Fusão DT-24+33; DT-23=6h; DT-21 reintro; DT-35  
- Writer único **(B)**  
- Veredito Dara: **APROVADO COM AJUSTES** → alinhado a este gate

### Uma (UX) — aceitar no FINAL

- UX-02 **CRITICAL ops** / UX-04 **HIGH**  
- UX-01 **DEFERRED** confirmado  
- UX-19…22 adds (~13h)  
- Pack pré-VPS UX ~**20h**  
- Honesty / M1≠M2 como design law  
- Veredito Uma: inventário validado → alinhado

### Conflitos especialistas × DRAFT

| Tema | DRAFT | Especialista | Decisão QA |
|------|-------|--------------|------------|
| UX-02 sev | HIGH | CRITICAL | **Dual-label OK**: inventário HIGH classe UI; **prioridade P0 ops CRITICAL** no roadmap |
| DT-07 | RESOLVED* | residual deploy | **PARTIAL** + DT-35 |
| DT-23 hours | 4h | 6h | **6h** |
| Live RESOLVED | forte | residual | Manter RESOLVED DDL; disclaimer dados |

---

## 11. Parecer Final

### O que está sólido

1. **Audit trail honesto** — resoluções Stories 1.1–1.5, matching unificado, CI, schema v3, set-based upserts **não** apagados; residual explícito.  
2. **Pre-VPS como eixo de verdade** — SYS-001…006 elevam o problema certo (falso verde) acima de polish.  
3. **Categorias que a v2 exigiu** — SEC, TQ, OBS, DEP, DOC/ENV.  
4. **M2 = 0%** declarado — anti-greenwash de produto.  
5. **Especialistas adversarial** — Dara e Uma não carimbaram; ajustaram horas e severidades.  
6. **SEC-02 não silenciado** apesar de Story Done — postura correta de inventário.

### O que permanece como risco residual (aceitável no assessment)

- Centenas de horas de backlog ativo (~280–350h ordem de grandeza).  
- SEC-02 **arquivo ainda no tree** (débito real, não de documentação).  
- DB offline na data da review.  
- Merge FINAL ainda pendente (condições C1–C2).

### O que **não** é NEEDS WORK

- Quantidade de débitos abertos.  
- Estimativas ainda a calibrar em ±20%.  
- UX-01 deferred.  
- M2 zero.  
- Preferências de desenho SYS-001 ainda a implementar (estão **trackeadas**).

### Decisão

```text
Gate Phase 7 (Brownfield Discovery): APPROVED WITH CONDITIONS
Próximo: @architect → docs/prd/technical-debt-assessment.md v3 FINAL
          incorporando C1–C6 + reviews Dara/Uma + este parecer
Depois:  @analyst relatório executivo → @pm/@sm epics pre-VPS wave
```

**Bloqueio explícito de processo:** nenhum enable de timers oficiais / claim VPS até Onda 0 (SYS-001…006 + SEC-02 + schema truth + TQ-07) com evidência.

---

## 12. YAML Gate (machine-readable)

```yaml
qa_gate:
  document: docs/reviews/qa-review.md
  version: "3.0"
  date: "2026-07-17"
  reviewer: "Quinn (@qa)"
  phase: "Brownfield Discovery Phase 7"
  subject: "docs/prd/technical-debt-DRAFT.md v3.0"
  specialist_reviews:
    db: "docs/reviews/db-specialist-review.md v3.0"
    ux: "docs/reviews/ux-specialist-review.md v3.0"
  previous_gate:
    version: "2.0"
    date: "2026-07-13"
    status: "NEEDS WORK"
  gate_status: "APPROVED WITH CONDITIONS"
  gate_status_enum: APPROVED_WITH_CONDITIONS
  structural_gaps_v2_closed:
    GAP-001_security_category: true
    GAP-002_tests_qa_category: true
  conditions:
    - id: C1
      must: true
      summary: "Merge DB specialist adjustments (hours, DT-21/35, fusions)"
    - id: C2
      must: true
      summary: "Merge UX re-elevations and UX-19..22"
    - id: C3
      must: true
      summary: "SEC-02 remains P0 until SA JSON gone + gitignore + rotate"
    - id: C4
      must: true
      summary: "Live DB offline residual verification debt explicit in FINAL"
    - id: C5
      must: false
      summary: "Publish QA answers to architect questions in FINAL"
    - id: C6
      must: true
      summary: "No VPS_OPERATIONAL / official timers until SYS-001/002 + TQ-07 closed"
  validations:
    sec_02_sa_json_tracked: true
    sec_02_file_present_2026_07_17: true
    live_db_offline_residual: true
    dual_runtime_split_brain_tracked: true
    m1_m2_honest_metrics: true
  cross_risks_critical:
    - CR-v3-001
    - CR-v3-002
    - CR-v3-003
  dependency_cycles: 0
  recommendation_next: "architect-final-assessment-v3"
  blocked_for_planning: false
```

---

*Revisão gerada por Quinn (@qa) em 2026-07-17 — Brownfield Discovery Phase 7.*  
*Postura adversarial; APPROVED WITH CONDITIONS porque v3 eliminou gaps estruturais da v2, não porque o backlog está limpo.*  
*Próxima etapa: @architect → `technical-debt-assessment.md` v3 FINAL.*
