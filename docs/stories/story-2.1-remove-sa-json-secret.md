# Story 2.1: Remover SA JSON residual e defaults fracos de deploy

**Epic:** Resolução de Débitos Técnicos v3 / Pre-VPS Truth  
**EPIC focado:** Pre-VPS Truth — Wave 1 (Security + Integrity)  
**Status:** Draft  
**Prioridade:** P0 — Imediata  
**Risk level:** **HIGH-RISK**  
**Estimativa:** ~**3h** (SEC-02 1h + DT-35 1.5h + re-scan 0.5h)  
**Executor planejado:** @dev  
**Quality Gate:** @qa  
**Autor draft:** Morgan (@pm) — 2026-07-17

---

## Story

As a **operador e responsável de segurança da plataforma Extra Consultoria**,  
I want **que o service account JSON da GCP e defaults fracos de senha de deploy não existam no repositório nem em scripts de provisionamento**,  
so that **nenhum clone, CI ou provisionamento VPS exponha credenciais compostas e o path de deploy falhe fechado sem senha forte**.

---

## Problem / Value

### Problema

- Story **1.1 Done** tratou SEC-02, mas a verificação **2026-07-17** confirma: `config/mides-bigquery-sa.json` (**2370 bytes**) **ainda está presente** no tree.  
- Assessment v3: **Nunca listar SEC-02 como RESOLVED** enquanto o arquivo existir.  
- Defaults `smartlic_local` ainda aparecem em caminhos de **deploy/seed** (DT-35) — residual de SEC-03/DT-07.  
- Risco composto **CR-v3-003**: SA JSON + senha fraca + histórico git = incidente de credencial (R$ 50k–500k+).

### Valor

- Fecha o único P0 de segurança **STILL OPEN** da reassessment.  
- Desbloqueia provisionamento seguro (sem defaults fracos).  
- Investimento mínimo (~3h) com ROI de sobrevivência operacional.  
- **Proibido tratar como FAST** — é HIGH-RISK (secrets + deploy).

### Root cause

1. Story 1.1 fechou o **caso principal** de settings/senha, mas a remoção efetiva do SA JSON **não foi concluída ou foi reintroduzida**.  
2. Scripts de install/provision/seed mantêm fallback `smartlic_local` em vez de fail-closed `${PG_PASSWORD:?}`.  
3. Ausência de gate CI que **falhe** se o arquivo SA ou pattern de senha fraca reaparecer.

---

## Scope

### IN

- Remover `config/mides-bigquery-sa.json` do working tree e do tracking git  
- Garantir pattern no `.gitignore` (e paths equivalentes)  
- Documentar/acionar **rotação** da chave se ela foi commitada (assumir exposta)  
- Substituir defaults `smartlic_local` em `install.sh`, `provision-vps.sh`, `db/seed/*` (e greps relacionados) por fail-closed  
- Prova automatizável: `test ! -f config/mides-bigquery-sa.json`; greps limpos de SA path e `smartlic_local` em paths de deploy  
- Atualizar `.env.example` / docs de setup se necessário (sem inventar secrets)

### OUT

- BFG / rewrite completo de git history (pode ser follow-up DevOps se ainda houver blob no histórico — documentar residual)  
- SEC-05 secrets management strategy (P2)  
- SEC-06 threat modeling (P2)  
- SEC-01 residual f-strings SQL (P1 separado)  
- Conta GCP / Workload Identity full (MIDES continua PULADO sem conta — DEP-01)  
- Qualquer claim `VPS_OPERATIONAL`

---

## Debt IDs covered

| ID | Descrição | Sev | Horas | Status assessment |
|----|-----------|-----|-------|-------------------|
| **SEC-02** | Service account JSON no repo | HIGH P0 | 1h | STILL OPEN ⚠ |
| **TD-029** | Alias canônico de SEC-02 | — | 0 (alias) | STILL OPEN |
| **DT-35** | Defaults `smartlic_local` em deploy/seed | MEDIUM P1 pré-VPS | 1.5h | NEW OPEN |
| **DT-07 residual** | Senha hardcoded residual | — | 0* (via DT-35) | PARTIAL |
| **ENV-04 / re-scan** (fatia) | Re-scan git patterns | — | 0.5h | Wave 1.7 |

---

## Acceptance Criteria

### AC-1 — SA JSON ausente

**Given** o repositório no HEAD da branch de implementação  
**When** executamos `test ! -f config/mides-bigquery-sa.json`  
**Then** o comando retorna exit 0 (arquivo **não** existe)

### AC-2 — Gitignore e tracking

**Given** o arquivo foi removido  
**When** inspecionamos `.gitignore` e `git ls-files`  
**Then** o pattern cobre `config/mides-bigquery-sa.json` (ou `*-sa.json` / path documentado) **e** o path **não** está tracked

### AC-3 — Grep limpo de material de SA no tree

**Given** um scan `git grep` / busca de conteúdo por paths de SA JSON e private_key típicos  
**When** o scan roda no tree versionado  
**Then** zero matches de conteúdo de service account JSON em paths de config versionados

### AC-4 — Rotação / exposição

**Given** a chave esteve no repositório  
**When** a story é fechada  
**Then** há evidência documentada de: (a) rotação solicitada/executada **ou** (b) justificativa se a chave nunca foi válida/já revogada — **sem** reintroduzir o JSON

### AC-5 — Deploy fail-closed (DT-35)

**Given** scripts de install/provision/seed  
**When** `PG_PASSWORD` / DSN de deploy **não** está definido  
**Then** o script **falha** (exit ≠ 0) e **não** usa `smartlic_local` como default silencioso

### AC-6 — Re-scan smartlic_local

**Given** grep por `smartlic_local` no repositório  
**When** o scan roda  
**Then** não há defaults ativos em paths de deploy/seed; ocorrências legítimas (docs de “não use”, testes de detecção) estão documentadas

---

## Tests required

| Tipo | O quê |
|------|-------|
| Automatizado / shell | `test ! -f config/mides-bigquery-sa.json` |
| Automatizado / CI (preferível) | Job ou step que falha se o arquivo reaparecer |
| Grep / audit | `git grep -n smartlic_local` + scan SA patterns |
| Manual / DevOps | Confirmação de rotação da chave (checklist) |
| Negativo | Script de provision sem env → deve falhar |

---

## Files likely affected

| Path | Motivo |
|------|--------|
| `config/mides-bigquery-sa.json` | **Remoção** |
| `.gitignore` | Pattern de exclusão |
| `install.sh` / scripts de provision (`*provision*vps*`) | DT-35 fail-closed |
| `db/seed/*` | Defaults de senha |
| `.env.example` | Variáveis sem secrets reais |
| Docs de setup / runbook (se existirem) | Instruções de auth alternativa |
| CI workflow (`.github/workflows/*`) | Gate anti-reintrodução (se aplicável) |

---

## Dependencies

| Depende de | Relação |
|------------|---------|
| — | **Nenhuma story 2.x** — pode iniciar imediatamente |
| Story 1.1 Done | Contexto histórico; **não** reabre 1.1; residual é esta story |

| Desbloqueia | Relação |
|-------------|---------|
| 2.3 / 2.2 / ENV-02 | Secrets limpos antes de health/runtime/VPS |
| SEC-05 (futuro) | Estratégia de secrets após limpeza |

**Paralelo seguro:** Story **2.4** (schema) e início de **2.5** (UX progress).

---

## Definition of Done

- [ ] Todos os ACs Given/When/Then atendidos com evidência  
- [ ] Arquivo SA JSON ausente no tree e untracked  
- [ ] `.gitignore` atualizado  
- [ ] Deploy/seed fail-closed sem `smartlic_local` default  
- [ ] Rotação/exposição documentada  
- [ ] Testes/greps da seção Tests required passam  
- [ ] Lint/typecheck/build dos paths tocados (se código)  
- [ ] Nenhuma nova dívida de secret sem registro  
- [ ] Story status → InReview → QA → PO close (ciclo SDC)  
- [ ] **Proibido** marcar SEC-02 RESOLVED no assessment sem AC-1 verdadeiro  

---

## Rollback notes

| Cenário | Ação |
|---------|------|
| Remoção quebra job local que lia o JSON | Restaurar via secret manager / env var / path **fora** do git; **não** recommitar o JSON |
| Script de deploy falha em ambiente legado | Fornecer env explícito; não reintroduzir default fraco |
| Chave rotacionada sem atualizar consumidores | Documentar env var necessária; falha explícita > fallback silencioso |

**Rollback de secret no git:** se o blob permanecer no histórico, abrir follow-up @devops (BFG/filter-repo) — **não** reverter a remoção do working tree.

---

## Risks

| Risco | Mitigação |
|-------|-----------|
| Tratar como FAST / doc-only | Risk level HIGH-RISK; SDC completo |
| Arquivo removido mas ainda no histórico | Documentar residual; follow-up history rewrite |
| Quebra de MIDES local | MIDES já PULADO sem conta GCP — aceitável fail-closed |
| Reintrodução acidental | CI grep + gitignore |

---

## Referências

- Assessment §4 Segurança — SEC-02 STILL OPEN  
- Assessment Wave 1.1 / 1.2 / 1.7  
- Report: CR-v3-003, fatia segurança 5–7h  
- Story 1.1 (Done) — residual explícito  

---

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (@pm) | Draft criado — Brownfield Phase 10 |
