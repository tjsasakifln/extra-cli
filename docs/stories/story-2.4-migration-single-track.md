# Story 2.4: Migrations single-track e schema truth (dump = HEAD)

**Epic:** Resolução de Débitos Técnicos v3 / Pre-VPS Truth  
**EPIC focado:** Pre-VPS Truth — Wave 1 (Security + Integrity · schema)  
**Status:** Draft  
**Prioridade:** P0 — Pre-VPS blocker  
**Risk level:** **HIGH-RISK**  
**Estimativa:** ~**12–14h** (DT-23 6h + DT-24/33 2.5h + DT-28/34 fatia 2.5–4h + docs)  
**Executor planejado:** @dev + @data-engineer (schema/migrations)  
**Quality Gate:** @qa  
**Autor draft:** Morgan (@pm) — 2026-07-17

---

## Story

As a **engenheiro de dados e operador da plataforma Extra Consultoria**,  
I want **um único track de migrations canônico, dump regenerado igual ao HEAD e diagnostics que não mintam FKs fantasma**,  
so that **todo ambiente (local, CI, VPS futura) suba o mesmo schema verdadeiro e não haja dual track `db/` vs `supabase/` competindo**.

---

## Problem / Value

### Problema

- **DT-23:** dual migration track (`db/migrations/*` vs `supabase/migrations/*`) + apply legado ainda invocável.  
- **DT-24 + DT-33 (fusão):** dump `db/current-schema.sql` desatualizado (corte 07-14) vs migrations **043–054+** não verificadas no apply; live DB **offline** em 2026-07-17 (confiança estática).  
- **DT-28 + DT-34:** diagnostics `EXPECTED_*` incompleto / exige FKs dropadas → ferramenta mentirosa.  
- **DOC-01** = alias de DT-23.  
- Ambiente “sobe” com schema errado → regressões silenciosas de pipeline (**CR-v3-004**).

### Valor

- Uma verdade de banco pré-VPS (must-fix DB ≈ 12–14h).  
- Fresh-install reproduzível via `db/setup_db.sh`.  
- Diagnostics confiáveis para CI e operadores.

### Root cause

1. Coexistência histórica Supabase CLI track + track `db/` canônico sem fail-closed no legado.  
2. Dump não regenerado após migrations 043–054.  
3. Live DB offline impede verificação `_migrations` real (residual C4) — story deve incluir smoke **quando DB up** e gates estáticos enquanto offline.  
4. EXPECTED_* no diagnostics não acompanhou DROP de FKs (050).

---

## Scope

### IN

**Política canônica (Dara — formal):**

```text
CANÔNICO:     db/migrations/*  via db/setup_db.sh
HISTÓRICO:    supabase/migrations/*  (somente leitura)
PROIBIDO:     scripts/apply-migrations.sh em host/CI sem ALLOW_LEGACY_SUPABASE_MIG=1
DoD ≥055:     dump regen + SHA se objetos públicos mudarem
```

- **DT-23:** fail-closed no apply legado; `ARCHIVED.md` (ou equivalente) no track histórico; CI que falha se path proibido for usado; docs apontam só `db/`  
- **DT-24+33:** verificar `_migrations` max == HEAD quando DB up; regenerar `db/current-schema.sql` + SHA em DB-AUDIT; dump contém objetos 043–054+  
- **DT-28/34 fatia:** diagnostics exit 0 em HEAD; **não** exigir FKs dropadas; EXPECTED_* alinhado  
- Fresh-install path documentado e testável (compose ou script)  
- Registrar residual se live DB continuar offline: checklist obrigatório ao subir  

### OUT

- DT-25 smoke schema CI completo com Postgres service (P1 residual — pode iniciar, não obrigar se infra faltar)  
- DT-26 VALIDATE NOT VALID off-peak  
- DT-27 view de orfandade contracts  
- DT-29 full audit_sql_references (além do necessário para exit 0)  
- DT-32 rollback pack 043–054 (P2)  
- DT-35 (defaults senha) — **story 2.1**  
- Mudanças de lógica de crawlers  

---

## Debt IDs covered

| ID | Descrição | Sev | Horas | Status |
|----|-----------|-----|-------|--------|
| **DT-23** / DOC-01 | Dual migration track | HIGH P0 | 6h | NEW OPEN |
| **DT-24 + DT-33** | Dump desatualizado + apply 043–054 não verificado | HIGH P0 | 2.5h | NEW OPEN (fusão) |
| **DT-28 + DT-34** | diagnostics EXPECTED_* + FKs fantasmas | MEDIUM P1 fatia pré-VPS | 2.5–4h | NEW OPEN (fusão) |
| **DT-03** | Ordem 003-v2/005-v2 | ACCEPTED | 0 | residual coberto por política DT-23 |

---

## Acceptance Criteria

### AC-1 — Track canônico único

**Given** um operador ou CI  
**When** aplica migrations no fluxo oficial  
**Then** o único path suportado é `db/setup_db.sh` + `db/migrations/*`

### AC-2 — Legacy fail-closed

**Given** invocação de `scripts/apply-migrations.sh` (ou path Supabase apply em host/CI) **sem** `ALLOW_LEGACY_SUPABASE_MIG=1`  
**When** o script executa  
**Then** exit code **≠ 0** e mensagem clara de política

### AC-3 — Histórico somente leitura

**Given** `supabase/migrations/*`  
**When** consultamos documentação no repo  
**Then** está marcado como histórico/ARCHIVED; proibido como apply de produção

### AC-4 — Dump = HEAD

**Given** migrations até HEAD (043–054+)  
**When** regeneramos o dump canônico  
**Then** `db/current-schema.sql` (ou path canônico) reflete HEAD e SHA/hash está em `supabase/docs/DB-AUDIT.md` (ou doc de schema acordado)

### AC-5 — `_migrations` (quando DB up)

**Given** banco live ou de smoke disponível  
**When** `SELECT max(version) FROM _migrations` (ou equivalente)  
**Then** max == HEAD documentado; se DB offline, checklist residual C4 permanece aberto e **explícito** no handoff (não marcar RESOLVED de dados)

### AC-6 — Diagnostics honestos

**Given** schema HEAD aplicado  
**When** `python -m scripts.schema.diagnostics` (ou comando canônico)  
**Then** exit 0 e **não** falha por FKs intencionalmente dropadas (050)

### AC-7 — Fresh install

**Given** banco vazio  
**When** `db/setup_db.sh` (ou fluxo documentado)  
**Then** schema sobe sem intervenção manual de track dual

---

## Tests required

| Tipo | O quê |
|------|-------|
| Script / CI | Legacy apply sem ALLOW → exit 1 |
| Integração DB | Fresh install vazio → HEAD |
| Smoke | diagnostics exit 0 em HEAD |
| Diff / hash | SHA dump documentado |
| Manual se DB offline | Checklist RESIDUAL-VERIFY-2026-07-17 registrado |

---

## Files likely affected

| Path | Motivo |
|------|--------|
| `db/setup_db.sh` | Apply canônico |
| `db/migrations/*` | Track canônico |
| `db/current-schema.sql` | Regen dump |
| `supabase/migrations/*` | ARCHIVED / read-only policy |
| `scripts/apply-migrations.sh` | Fail-closed legado |
| `scripts/schema/diagnostics*` | EXPECTED_* |
| `supabase/docs/DB-AUDIT.md` / `SCHEMA.md` | SHA + política |
| CI workflows | Gate de path proibido |
| Docs ops | Fresh install |

---

## Dependencies

| Depende de | Relação |
|------------|---------|
| — | Pode iniciar em paralelo a **2.1** |
| DB up | AC-5 pleno; senão residual C4 |

| Desbloqueia | Relação |
|-------------|---------|
| 2.2 evidence rows | Schema estável |
| 2.3 diagnostics no health | Ferramenta não mentirosa |
| DT-25/26/27 futuros | Base |

**HIGH-RISK:** migrations e schema — ciclo com @data-engineer; sem FAST.

---

## Definition of Done

- [ ] ACs 1–7 (AC-5 com DB up **ou** residual C4 explícito não mascarado)  
- [ ] Política canônica em doc + fail-closed no código  
- [ ] Dump regenerado + SHA  
- [ ] diagnostics exit 0 sem FKs fantasmas  
- [ ] Testes/CI do legacy path  
- [ ] QA + PO close  
- [ ] Nenhuma migration nova em `supabase/` como track ativo  

---

## Rollback notes

| Cenário | Ação |
|---------|------|
| Dump regenerado incorreto | Restaurar dump anterior do git; re-rodar regen após fix |
| Fail-closed bloqueia pipeline legado interno | `ALLOW_LEGACY_SUPABASE_MIG=1` **temporário** e documentado; ticket para migrar |
| Fresh install quebra | Corrigir migration HEAD; não reabrir dual track como default |

---

## Risks

| Risco | Mitigação |
|-------|-----------|
| CR-v3-004 schema dual | Esta story |
| CR-v3-009 DB offline superestima RESOLVED | Residual C4 explícito |
| Aplicar migrations em produção sem backup | HIGH-RISK; backup antes de smoke live |
| Double-count DOC-01 horas | Alias — horas só em DT-23 |

---

## Referências

- Assessment §2 Database; Wave 1.3–1.5; política Dara  
- `docs/reviews/db-specialist-review.md` v3.0  
- RESIDUAL-VERIFY-2026-07-17  

---

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (@pm) | Draft criado — Brownfield Phase 10 |
