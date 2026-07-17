# Story 2.5: CLI ops UX honesty (pack Pre-VPS)

**Epic:** Resolução de Débitos Técnicos v3 / Pre-VPS Truth  
**EPIC focado:** Pre-VPS Truth — Pack UX ops (paralelo Waves 1–3)  
**Status:** Draft  
**Prioridade:** P0 ops (honesty)  
**Risk level:** **STANDARD**  
**Estimativa:** ~**20h** (UX-02 8h + UX-17 2h + UX-14 3h + UX-04 4h + UX-21 3h)  
**Executor planejado:** @dev (+ @ux-design-expert se design de labels)  
**Quality Gate:** @qa  
**Autor draft:** Morgan (@pm) — 2026-07-17

---

## Story

As a **consultor e operador CLI da Extra Consultoria**,  
I want **progresso visível, health legível por humanos, labels honestos M1≠M2 e tabelas/sumários utilizáveis**,  
so that **eu não confunda sinal comercial com cobertura operacional, não fique com terminal morto em jobs longos e enxergue a verdade no dia a dia**.

---

## Problem / Value

### Problema

| ID | Sintoma | Sev |
|----|---------|-----|
| **UX-02** | Sem progress em comandos longos (update/radar/crawl/PDF/golden_path) | CRITICAL ops / P0 |
| **UX-17** | Ops health só JSON — operador cego | P0 ops |
| **UX-14** | Confusão cobertura vs sinal comercial (M1 vs M2) | HIGH / P0 ops |
| **UX-04** | Truncamento agressivo opp_intel (20c/10 cols) | HIGH P1 pack |
| **UX-21** | Sem sumário human-readable pós-comando | MEDIUM pack pré-VPS |

- **CR-v3-005:** M1 (10,6%) lido como M2 (0%) ou como “GO” de operação.  
- Web UI (**UX-01**) está **DEFERRED** — o pack CLI é o caminho honesto pré-VPS.

### Valor

- Score UX alvo pack: **7/10** (assessment).  
- Proteção de marca e decisão do consultor (~R$ 3.000 do pack).  
- Paralelo seguro a Wave 1 (exceto DoD completo de UX-17 após health honesty 2.3).

### Root cause

1. CLIs longas sem `rich.progress` / etapas.  
2. Health nascido JSON-first sem view humana.  
3. Um único label “cobertura” para duas métricas (M1 ranking comercial vs M2 evidência operacional).  
4. `list` truncando campos canônicos decisórios.  
5. Comandos terminam sem contagens/path/próximo passo.

---

## Scope

### IN — Pack pré-VPS UX (Onda honesty)

| # | ID | Horas | Critério honesty |
|---|----|-------|------------------|
| 1 | **UX-02** | 8h | etapa + ETA; zero terminal morto nos 4 alvos: update, radar, crawl, PDF/golden_path |
| 2 | **UX-17** | 2h | `ops/health --human` ASCII; exit code = mesmo do JSON; **sem verde fixture** |
| 3 | **UX-14** | 3h | 2 seções M1/M2; disclaimer; cor de GO ≠ cor de coverage |
| 4 | **UX-04** | 4h | never-truncate: id, ranking, decisao, orgao_nome, status; max_col ~60 |
| 5 | **UX-21** | 3h | sumário pós-comando: contagens + path artefato + próximo passo |

### OUT

- **UX-01** Web UI (DEFERRED pós-VPS)  
- UX-03 display lib full unificação (P1 residual Wave 6)  
- UX-08/15/19 polish amplo  
- Implementar SYS-003/004 (story **2.3**) — UX-17 **consome** health honesto  
- Elevação M2 real (SYS-008) — só labels honestos sobre o valor atual (0%)  

---

## Debt IDs covered

| ID | Descrição | Horas | Prioridade |
|----|-----------|-------|------------|
| **UX-02** | Progress indicadores | 8h | P0 ops |
| **UX-17** | Health `--human` | 2h | P0 ops |
| **UX-14** | Labels M1≠M2 | 3h | P0 ops |
| **UX-04** | Truncamento opp_intel | 4h | P1 pack pré-VPS |
| **UX-21** | Sumário pós-comando | 3h | P1 pack pré-VPS |
| **OBS-03** | Alias UX-14 | 0 | — |

---

## Acceptance Criteria

### AC-1 — Progress nos alvos (UX-02)

**Given** execução de `update` / `radar` / `crawl` / PDF ou `golden_path` (comandos canônicos do projeto)  
**When** o job roda por tempo material  
**Then** o terminal mostra progresso por etapa (e ETA quando factível) e **não** fica sem output por todo o job

### AC-2 — Health humano (UX-17)

**Given** `ops/health` (ou CLI canônica) com flag `--human`  
**When** o comando executa  
**Then** imprime tabela/ASCII legível com claim/mode; **exit code idêntico** ao modo JSON; fixture **não** aparece como verde operacional live

### AC-3 — M1 ≠ M2 (UX-14)

**Given** outputs de coverage/workspace que exibem métricas  
**When** o usuário lê o terminal (ou relatório CLI)  
**Then** existem **duas seções** nomeadas (sinal comercial M1 vs cobertura operacional M2), disclaimer de que M1 ≠ M2 ≠ GO, e cor/estilo de “GO” **não** reutiliza a de coverage

### AC-4 — Never-truncate canônico (UX-04)

**Given** `opportunity_intel` list (ou CLI list equivalente) sem `--json`  
**When** a tabela é renderizada  
**Then** campos `id`, `ranking`, `decisao`, `orgao_nome`, `status` **não** truncam abaixo do utilizável; demais cols respeitam max ~60 ou wrap documentado

### AC-5 — Sumário pós-comando (UX-21)

**Given** fim de `radar` / `update` (e alvos acordados)  
**When** o comando termina com sucesso ou falha controlada  
**Then** imprime sumário: contagens relevantes + path de artefato (se houver) + próximo passo sugerido

### AC-6 — Glossário honesto

**Given** qualquer string user-facing de “cobertura” no pack  
**When** auditamos copy  
**Then** não há claim de “95%” ou “VPS operacional” como estado atual; M2 baseline **0%** permanece honesto

---

## Tests required

| Tipo | O quê |
|------|-------|
| Unit / snapshot | Labels M1/M2 e disclaimer presentes |
| Unit | Truncation policy never-truncate nos campos canônicos |
| Integration / CLI | `--human` exit code == JSON mode |
| Manual / UX | Progress visível nos 4 alvos (checklist) |
| Regressão | Health fixture não healthy live (depende 2.3) |
| Golden / fixture | Sumário contém chaves esperadas |

---

## Files likely affected

| Path | Motivo |
|------|--------|
| CLIs de update/radar/crawl/report | UX-02, UX-21 |
| `scripts/ops/health.py` + CLI entry | UX-17 |
| Workspace / coverage CLI | UX-14 |
| `scripts/opportunity_intel/*` list/display | UX-04 |
| `scripts/lib/display/` (se existir ou criar mínimo) | Progress/tabelas |
| Docs help / epilog | Disclaimer M1/M2 |

---

## Dependencies

| Depende de | Relação |
|------------|---------|
| **2.3** (para DoD completo UX-17) | Health JSON honesto (SYS-003/004); UX-17 não deve pintar verde se 2.3 incompleto |
| — | UX-02, UX-14, UX-04, UX-21 podem iniciar em paralelo a 2.1/2.4 |

| Desbloqueia | Relação |
|-------------|---------|
| Confiança operacional diária | Pré-VPS |
| Wave 6 residual CLI | Base de honesty |
| UX-01 (futuro) | Só após VPS + este pack estável |

---

## Definition of Done

- [ ] ACs 1–6 com evidência (screenshots/logs CLI ok)  
- [ ] Pack 5 IDs fechados ou residual mínimo documentado  
- [ ] Testes automatizados onde couber + checklist manual dos 4 alvos progress  
- [ ] Copy sem claim proibido (95% / VPS_OPERATIONAL como fato)  
- [ ] QA + PO close  
- [ ] **Proibido** spike SPA/Next nesta story  

---

## Rollback notes

| Cenário | Ação |
|---------|------|
| Progress quebra pipe/CI não-TTY | Detectar TTY; fallback silencioso ou log periódico |
| `--human` diverge de JSON | Exit code unificado; campos derivados só na view |
| Tabela larga quebra terminal estreito | max_col 60 + wrap; never-truncate só nos campos canônicos |

---

## Risks

| Risco | Mitigação |
|-------|-----------|
| CR-v3-005 M1 como M2 | AC-3 + glossário |
| UX-17 com health ainda mentiroso | Dependência 2.3 no DoD |
| Scope creep UX-03 monólito display | OUT; mínimo viável |
| Progress só em 1 comando | AC-1 lista 4 alvos |

---

## Referências

- Assessment §3.3 Pack pré-VPS UX; Wave 6.1–6.5  
- `docs/reviews/ux-specialist-review.md` v3.0  
- Report: pack UX honesty ~20h / R$ 3.000  
- Frontend spec v3 — CLI-first  

---

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (@pm) | Draft criado — Brownfield Phase 10 |
