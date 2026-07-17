# UX Specialist Review

**Versão:** 3.0  
**Data:** 2026-07-17  
**Revisor:** Uma (@ux-design-expert)  
**Documento base:** `docs/prd/technical-debt-DRAFT.md` v3.0 — §3 Débitos de Frontend/UX  
**Fonte Phase 3:** `docs/frontend/frontend-spec.md` v3.0  
**Continuidade:** `docs/reviews/ux-specialist-review.md` v2 (2026-07-13)  
**Status:** Revisão completa — Brownfield Discovery Phase 6  
**Produto:** CLI-first B2G — **não** empurrar Web UI como P0

---

## 0. Metodologia e continuidade v2 → v3

### 0.1 Critérios de priorização UX (inalterados)

| Fator | Peso |
|-------|------|
| Impacto direto no usuário (consultor / operador / cliente via relatório) | 40% |
| Frequência de uso (journeys afetadas) | 25% |
| Tempo perdido / atrito por incidente | 20% |
| Esforço de resolução (horas) | 15% |

**Princípio de marca (2026-07-17):** *honesty UX* — fail-closed messaging, sem “verde falso”, sem inventar GO, sem confundir cobertura operacional com sinal comercial.

### 0.2 Renumeração de IDs (importante)

O catálogo v3 **redefiniu** UX-13…UX-18. Os IDs do review v2 **não** significam o mesmo:

| ID v2 (2026-07-13) | Significado v2 | Destino em v3 |
|--------------------|----------------|---------------|
| UX-13 | Onboarding / help contextual | **Não no catálogo v3** → reintroduzido como **UX-19** |
| UX-14 | Confirmação ops destrutivas | **Não no catálogo v3** → reintroduzido como **UX-20** |
| UX-15 | Formatação monetária duplicada | Absorvido por **UX-03** (display compartilhado) |
| UX-16 | Tracebacks crus | Absorvido por **UX-08** (mensagens de erro) |
| UX-17 | Radar JSON bruto sem sumário | Reintroduzido como **UX-21** (≠ UX-17 v3 = ops health) |
| — | — | **UX-13…18 v3** são débitos **novos** (a11y, M1≠M2, fragmentação, idioma, health humano, TOC HTML) |

### 0.3 Verdade de produto (não negociável nesta revisão)

- Superfície primária: **CLI + relatórios** (PDF/Excel/HTML estático).
- Web UI interativa: **inexistente** → UX-01 permanece **DEFERRED** (pós-VPS).
- `LOCAL_RESILIENCE_READY` **≠** cobertura 95% **≠** `VPS_OPERATIONAL`.
- Preset AIOX `nextjs-react` **não** dita stack de produto.

---

## 1. Débitos Validados

18 débitos do DRAFT §3 revisados. Severidade ajustada em **2** casos (UX-02, UX-04); demais alinhadas à spec v3 ou reafirmadas.

| ID | Débito | Severidade | Horas | Prioridade | Impacto UX | Veredito | Notas |
|----|--------|------------|-------|------------|------------|----------|-------|
| **UX-01** | Web UI interativa (FastAPI+HTMX / portal) | HIGH | 80h+ (MVP ~40h) | **P3 pós-VPS** | Extremo se medido como “portal”; **zero** no caminho pré-VPS | **DEFERRED — CONFIRMADO** | Débito real e estratégico. **Não** compete com CLI honesty. Sem spike SPA no caminho crítico. Stack candidata futura: FastAPI+HTMX+tokens Big Four — **não** Next.js por default. |
| **UX-02** | Sem progress indicators em comandos longos | **CRITICAL** ↑ | 8h | **P0 ops** | Abort prematuro de `update` / `radar` / crawls / PDF; terminal “morto” | **RE-ELEVAR** | Spec v3 manteve HIGH; assessment v2 e esta revisão re-elevam a **CRITICAL**. Esforço baixo, frequência alta, risco operacional pré-VPS. Usar `rich.progress.Progress` (já dependência). |
| **UX-03** | Dual display: `rich` vs raw `print` | MEDIUM | 12h | P1 | Inconsistência visual; atrito ao alternar tools | **VALIDADO (PARTIAL)** | rich em `local_datalake` + `golden_path`; workspace/opp_intel ainda ASCII. Meta: `scripts/lib/display/` compartilhado. |
| **UX-04** | Truncamento agressivo opp_intel (20c / 10 cols) | **HIGH** ↑ | 4h | **P1** | Listagem inútil para triagem; força `--json` / `show` por ID | **RE-ELEVAR** | Spec v3 MEDIUM subestima impacto comercial. Workspace cap 48c mitiga parcialmente; **opp_intel inalterado**. Colunas nunca truncáveis: ver §3 Q5. |
| **UX-05** | Exit codes inconsistentes | LOW | 2h | P2 | Baixo em uso interativo; médio em automação/CI | **VALIDADO (PARTIAL)** | Referências boas: `ops/health` 0/1/2, `golden_path` 0–5. opp_intel/workspace ainda 0/1 genérico. Padronizar **semântica** documentada, não forçar um único range. |
| **UX-06** | Flags output inconsistentes (`--format` vs `--json`) | LOW | 2h | P2 | Carga cognitiva ao alternar CLIs | **VALIDADO (OPEN)** | Alvo: `--format table\|json\|csv` + `--json` como alias deprecado. |
| **UX-07** | Sem paginação interativa | LOW | 6h | P3 | Overflow de terminal em 500+ linhas | **VALIDADO (OPEN)** | `--pager` / rich pager; não bloqueia pré-VPS. |
| **UX-08** | Erros silenciosos / pouca mensagem | MEDIUM | 3h | **P1** | Usuário não distingue vazio × falha × processando | **VALIDADO (PARTIAL)** | workspace/opp_intel melhoraram; legado + tracebacks ocasionais (ex-v2 UX-16). Formato: `[ERROR]` + ação + `--debug`. |
| **UX-09** | Coverage duplicado (opp_intel vs datalake vs contract) | MEDIUM | 6h | P2 | “Qual comando é a verdade?” | **VALIDADO (PARTIAL)** | `coverage_contract_cli` + workspace ajudam; ainda múltiplas entradas. Consolidar **entry documentado** + deprecation nos legados. |
| **UX-10** | Monólito `generate-report-b2g.py` (~7.4k LOC) | MEDIUM | 16h | P2 | UX cliente OK; manutenção lenta → bugs demoram | **VALIDADO (OPEN)** | Impacto UX **indireto**. `executive_report` modular é o caminho; monólito permanece. |
| **UX-11** | URLs não clicáveis no terminal | LOW | 2h | P3 | Conveniência (copy/paste) | **VALIDADO (OPEN)** | rich hyperlinks; custo quase zero pós-UX-03. |
| **UX-12** | Validação de input pouco amigável | LOW→**MEDIUM** * | 4h | P2 | Erro SQL vs “UF inválida” | **AJUSTE LEVE** | DRAFT LOW mantido como baseline técnico; **prioridade UX = P2/MEDIUM** para persona consultor. `argparse` choices + mensagens PT-BR. |
| **UX-13** | A11y incompleta em charts HTML executivos | LOW | 3h | P3 | Charts OK/responsivos; WCAG não auditado | **VALIDADO (NEW)** | Commits `fdaf792`/`d3e82ba` restauraram charts; ~22 `aria-*` = baseline parcial. Não bloqueia pré-VPS. |
| **UX-14** | Confusão cobertura vs sinal comercial (M1≠M2) | **HIGH** | 3h | **P0 ops** | Decisão comercial errada se “coverage alto” lido como GO | **VALIDADO (PARTIAL)** — **crítico** | Guide documenta; CLI **sem** separação visual forte. Honesty principle #1 do produto. Ver padrão visual §3 Q2. |
| **UX-15** | Fragmentação de CLIs (~86 parsers) | MEDIUM | 8h | P1 | Carga cognitiva; “home screen” inexistente sem guide | **VALIDADO (PARTIAL)** | Facade `workspace` + `workspace-guide` são a resposta certa. Legados = power user, não deprecar com big-bang. |
| **UX-16** | Mistura PT/EN em mensagens CLI | LOW | 4h | P3 | Legibilidade do consultor | **VALIDADO (NEW)** | Política: PT-BR user-facing; EN em códigos/IDs/JSON keys estáveis. |
| **UX-17** | Ops health JSON-only (sem vista humana) | MEDIUM | 2h | **P0 ops** | Operador cego ou forçado a `jq`; risco de mal-ler status | **VALIDADO (NEW)** | JSON always permanece canônico para CI/máquina. Adicionar `--human` / default TTY summary. Ver §3 Q3. |
| **UX-18** | HTML comercial sem TOC sticky / multi-página | LOW | 3h | P3 | Aceitável sessão única | **VALIDADO (NEW)** | Polish; não bloqueia. |

\* UX-12: severidade de inventário permanece LOW no DRAFT se architect preferir matriz técnica; **impacto UX** tratado como MEDIUM nesta revisão.

### Resumo de ajustes de severidade (v3)

| ID | DRAFT / Spec v3 | Revisada Uma | Delta |
|----|-----------------|--------------|-------|
| UX-02 | HIGH | **CRITICAL** | +1 — abort prematuro + P0 ops |
| UX-04 | MEDIUM | **HIGH** | +1 — risco de leitura comercial |
| UX-12 | LOW | MEDIUM *(impacto UX)* | +0.5 — persona não-técnica |
| UX-01 | HIGH | HIGH (DEFERRED) | prioridade **P3** reafirmada |
| Demais | — | alinhadas | — |

### Contagem validada

| Status DRAFT | Qtd | Notas Uma |
|--------------|-----|-----------|
| OPEN | 6 | + severidades re-elevadas em 2 |
| PARTIAL | 6 | progresso real desde v2 (workspace, health, commercial HTML) |
| NEW | 4 | UX-13,16,17,18 aceitos |
| DEFERRED | 1 | UX-01 **confirmado** |
| RESOLVED 100% | 0 | correto — nenhum UX-xx fechado de ponta a ponta |

---

## 2. Débitos Adicionados

Lacunas do review v2 **ainda válidas** e **não cobertas** pelo catálogo v3 (IDs novos para não colidir).

| ID | Débito | Severidade | Horas | Prioridade | Impacto UX | Veredito | Notas |
|----|--------|------------|-------|------------|------------|----------|-------|
| **UX-19** | Onboarding / help contextual fraco — sem `--examples`; help minimalista em comandos densos | MEDIUM | 6h | P2 | Barreira de entrada; guide externo obrigatório | **ADD** | Continuação do UX-13 v2. Priorizar: `workspace`, `radar`/`update`, `ops.health`. Epilog com exemplos em `--help`. |
| **UX-20** | Sem confirmação antes de sobrescrever artefatos (`export`, PDFs em `output/`) | LOW | 2h | P3 | Frustração baixa (regenerável) | **ADD** | Continuação do UX-14 v2. Padrão: prompt interativo + `--force`. |
| **UX-21** | Comandos longos sem **sumário human-readable** pós-execução (radar/update dumpam JSON ou silenciam) | MEDIUM | 3h | **P1** | “Wall of JSON” / sem next-step | **ADD** | Continuação do UX-17 v2 (**≠** UX-17 v3). Complementa UX-02 (progress *durante*) com fechamento *após*. |
| **UX-22** | Tokens de marca PDF/HTML **duplicados** (sem arquivo canônico) | LOW | 2h | P3 | Drift visual entre geradores | **ADD** | Spec §9. Extrair `docs/frontend/brand-tokens.md` (ou YAML) consumido por PDF/HTML. Não é design system web. |

### Total adicionados

| IDs | Horas |
|-----|-------|
| UX-19…22 | **13h** |

---

## 3. Respostas ao Architect

### Q1 — UX-02 severidade: HIGH (spec v3) ou CRITICAL (assessment v2)?

**Resposta: re-elevar a CRITICAL.**

| Critério | Avaliação |
|----------|-----------|
| Frequência | Diária (crawl/update/radar/PDF) |
| Custo do erro | Abort + re-run + dúvida se “travou” vs “trabalhando” |
| Esforço | 8h com `rich` já no projeto |
| Pré-VPS | P0 ops na Onda 1 do DRAFT |

HIGH descreve bem a *classe* de débito de interface; CRITICAL descreve o *risco operacional* atual. Inventário pode manter tag HIGH se a matriz global reservar CRITICAL só para segurança/dados — nesse caso, **prioridade de execução permanece P0 ops #1 do grupo UX**, acima de qualquer polish.

**Biblioteca:** `rich.progress.Progress` — **não** `tqdm` (zero dep nova; alinhado a UX-03).

**Alvos mínimos:**
1. `opportunity_intel` `update` / `radar`
2. `crawl/monitor.py` loops longos
3. Geração PDF (`generate-report-b2g` / `executive_report`)
4. Etapas visíveis do `golden_path`

---

### Q2 — UX-14: padrão visual mínimo M1 (sinal comercial) vs M2 (cobertura operacional)

**Resposta: separação visual obrigatória no `workspace` (e em qualquer coverage print).**

#### Tokens de status (CLI)

| Sinal | Badge | Cor rich | Uso |
|-------|-------|----------|-----|
| GO | `[GO]` | green | Ranking comercial / decisão HITL |
| REVIEW | `[REVIEW]` | yellow | Triagem humana |
| NO_GO | `[NO_GO]` | red | Não abordar |
| M2 coverage | `[COBERTURA]` | cyan | Operacional — **nunca** verde de GO |
| Fresh / stale | `[FRESH]` / `[STALE]` | green / yellow | Freshness operacional |
| Degraded / empty | `[DEGRADED]` / `[EMPTY]` | yellow / dim | Fail-closed sections |
| Blocked | `[BLOCKED]` | red | Sem evidência live |

#### Regras de layout

1. **Duas seções nomeadas** em `workspace today` e `workspace opportunities`:
   - `## Sinal comercial (M1)` — ranking, score, decisão
   - `## Cobertura operacional (M2)` — fontes, freshness, % coverage
2. **Proibido** usar a mesma cor verde de GO para “coverage 80%+”.
3. **Linha de disclaimer** fixa no rodapé de coverage:
   ```
   [INFO] Cobertura operacional ≠ recomendação comercial. Não inventar GO.
   ```
4. **Colunas obrigatórias** quando ambas as métricas aparecem na mesma tela:  
   `ranking` | `decisao` | `confidence` | `coverage_label` | `freshness` — com `coverage_label` textual (`operacional`) e `ranking` textual (`comercial`).
5. Alinhar copy ao `workspace-guide` e a OBS-03 / coverage contract (M1≠M2).

---

### Q3 — UX-17: formato de `--human` para `ops/health`

**Resposta: ASCII tabela fixa como default humano; `rich` opcional se TTY.**

| Contexto | Formato | Motivo |
|----------|--------|--------|
| CI / pipes / Makefile | **JSON always** (comportamento atual) | Máquina-first, estável |
| Operador em terminal | `--human` → **ASCII tabela fixa** + exit code | Funciona em SSH sem TTY rico, logs copiáveis |
| TTY colorido opcional | `--human --rich` se `sys.stdout.isatty()` | Progressive enhancement |

**Não** substituir JSON por rich como único modo — quebra automação.

#### Mock mínimo `--human`

```text
ops/health  env=development  mode=live  claim=operational_live
────────────────────────────────────────────────────────────
Check              Status      Detail
DB                 OK          latency 12ms
Crawl freshness    DEGRADED    pncp content stale 36h
Fixtures           IGNORED     not counted toward live
Evidence           OK          last_success 2026-07-17T…
────────────────────────────────────────────────────────────
Overall: DEGRADED   exit=1
[WARN] LOCAL_RESILIENCE_READY ≠ VPS_OPERATIONAL ≠ coverage 95%
```

**Regras honesty:**
- Fixture **nunca** pinta live de verde.
- `claim` explícito na primeira linha.
- Exit codes **idênticos** ao modo JSON (0 healthy / 1 degraded / 2 blocked|no_live).

---

### Q4 — UX-03/15: workspace como única facade — legados power-user ou deprecar?

**Resposta: workspace = única facade *documentada*; legados = power-user **sem** prazo de remoção no pré-VPS.**

| Camada | Política |
|--------|----------|
| `python -m scripts.workspace` | **Home screen** do consultor; guide + `--help` epilog |
| `opportunity_intel`, `local_datalake`, `ops.*` | Power user / automação; permanecem |
| Deprecation com prazo | **Não** no pré-VPS — risco de quebrar rituais e scripts |
| Deprecation soft | Warnings só quando houver **substituto 1:1** (ex.: coverage entry unificado UX-09) |

**Não** big-bang de deprecar ~86 parsers. O ganho de UX-15 é **descoberta** (workspace + guide), não exclusão.

---

### Q5 — UX-04: colunas nunca truncáveis

**Resposta: lista canônica (opp_intel + workspace):**

| Prioridade | Coluna | Truncamento |
|------------|--------|-------------|
| **P0 never** | `id` | Nunca |
| **P0 never** | `ranking` / `decisao` | Nunca |
| **P0 never** | `orgao_nome` | Mín. 40c; preferir 48–60 |
| **P0 never** | `status` (open/closed) | Nunca |
| **P1 soft** | `objeto` | Mín. 40c (hoje 20c é inaceitável) |
| **P1 soft** | `municipio` / `uf` | `uf` nunca; município ≥ 20c |
| **P2** | valores monetários | Nunca truncar dígitos; formatar `R$` |
| **P2** | URLs | Truncar display OK se hyperlink/full em `show` |
| **P3** | timestamps ISO | Pode encurtar para `dd/mm HH:MM` em table |

**Defaults de componente compartilhado:**
- `max_col_width` default **60** (não 20)
- Sem hard cap de 10 colunas — usar perfil `--cols compact|full`
- `id`, `ranking`, `uf` em `no_truncate=True` sempre

---

### Q6 — UX-01: confirma DEFERRED pós-VPS (sem spike SPA)?

**Resposta: CONFIRMADO DEFERRED.**

- **Sem** spike SPA/Next.js no caminho crítico pré-VPS.
- **Sem** competir com Onda 0/1 (truth, health, progress, M1≠M2).
- Critérios para **reabrir** UX-01:
  1. VPS estável + timers honestos  
  2. Fluxo CLI diário (`workspace today`) consolidado  
  3. Pedido explícito de portal multi-usuário / cliente  
- MVP futuro (~40h): FastAPI + HTMX + tokens Big Four — **não** preset `nextjs-react`.
- Estimativa 80h+ permanece para portal com auth multi-tenant.

---

### Q7 — UX-16: política de idioma

**Resposta: PT-BR user-facing; EN só em códigos/IDs/chaves estáveis.**

| Superfície | Idioma |
|------------|--------|
| Mensagens `[ERROR]`/`[WARN]`/`[INFO]`, help text, disclaimers | **pt-BR** (acentos corretos) |
| Badges de ranking `GO`/`REVIEW`/`NO_GO` | EN estável (já no domínio + PDF) **ou** par `GO (aprovar)` na 1ª ocorrência |
| Keys JSON, exit claim fields, flags CLI | EN |
| Docs ops / workspace-guide | pt-BR |
| Relatórios cliente (PDF/HTML) | pt-BR comercial |
| Logs internos / exception class names | EN OK |

**Não** traduzir chaves JSON (`claim`, `mode`, `environment`) — quebra contratos máquina.

---

## 4. Recomendações de Design

### 4.1 Pre-VPS operator UX (prioridade máxima)

Ordem alinhada ao **Grupo UX ops** do DRAFT e à honesty:

```text
UX-02 (progress)  ∥  UX-17 (--human health)  ∥  UX-14 (M1≠M2 labels)
        → UX-04 (colunas never-truncate)
        → UX-21 (sumário pós-comando)
        → UX-03 + UX-15 (rich compartilhado + workspace home)
        → UX-01 (último, pós-VPS)
```

| # | Entrega | Horas | Critério de sucesso (honesty) |
|---|---------|-------|--------------------------------|
| 1 | Progress em update/radar/crawl/PDF | 8h | Operador vê etapa + ETA; zero “terminal morto” |
| 2 | `ops/health --human` ASCII | 2h | Humano lê overall + claim; exit = JSON; **sem verde de fixture** |
| 3 | Labels M1≠M2 no workspace | 3h | Duas seções; disclaimer; GO ≠ coverage color |
| 4 | Never-truncate id/ranking/órgão | 4h | `list` legível sem `--json` |
| 5 | Sumário pós-radar/update (UX-21) | 3h | Contagens + path de artefato + próximo passo |

**Coverage labels honesty (obrigatório):**
- Preferir `COBERTURA_OPERACIONAL` / `SINAL_COMERCIAL` a labels ambíguos `coverage` / `score` sozinhos na mesma linha.
- Nunca mapear percentual de cobertura para badge verde de GO.
- `LOCAL_RESILIENCE_READY` sempre acompanhado de o que **não** implica (VPS, 95%).

### 4.2 UX-01 Web UI — DEFERRED com racional

| Argumento | Detalhe |
|-----------|---------|
| Persona atual | Tiago + operador em terminal; cliente recebe PDF/HTML |
| Caminho crítico | Truth gates, health, crawl, workspace |
| ROI pré-VPS | CLI legível > portal |
| Risco | SPA puxa preset Next.js, auth, deploy — fora do produto real |
| Reabrir quando | VPS + CLI estável + demanda multi-user explícita |
| Stack candidata | FastAPI + HTMX + tokens Big Four (não Next default) |

### 4.3 Consistência de relatórios (cliente + comercial)

| Superfície | Estado | Ação UX |
|------------|--------|---------|
| PDF Big Four (`executive_report`) | Alta qualidade | Manter tokens; extrair canônico (UX-22) |
| Excel executivo | Bom | Espelhar seções do PDF |
| HTML sessão comercial | Forte (honesty flags, confidence) | Propagar badges para CLI (UX-14) |
| HTML plano executivo | Charts OK pós-fix | UX-13 a11y residual P3 |
| `generate-report-b2g` monólito | Dívida | UX-10 médio prazo — não bloquear pré-VPS |

**Princípio:** o HTML comercial já é referência de *honesty UX* (`live_fetch`, confidence, não inventar GO). O CLI deve **copiar a ética**, não só as cores.

### 4.4 Camada compartilhada CLI (alvo UX-03)

```text
scripts/lib/display/
  console.py     # tema rich (success/error/warn/info)
  table.py       # max_col_width=60, no_truncate set
  format.py      # fmt_money, fmt_date, fmt_cnpj (pt-BR)
  errors.py      # [ERROR] + ação + --debug
  progress.py    # factory Progress
  exit_codes.py  # EXIT_OK / WARN / ERROR (+ doc golden_path 0–5)
```

### 4.5 Formato de erro (UX-08 + honesty)

```text
[ERROR] Falha ao conectar no banco de dados.
        → Verifique se o Postgres local está up: pg_isready -h localhost
        → Ou use --dsn para conexão alternativa.
        → (use --debug para traceback completo)
```

- Traceback **nunca** default.
- Sugestão **executável** (copiar/colar).
- Fail-closed: status `DEGRADED` / `EMPTY` / `UNAVAILABLE` explícitos — não silêncio.

### 4.6 Score de consistência UX

| Versão | Score | Notas |
|--------|-------|-------|
| v1.0 (2026-07-13) | 4/10 | Fragmentação total |
| v3.0 spec | 5/10 | workspace + health + commercial HTML + charts |
| **Alvo pós Onda 1 UX** | **7/10** | progress + human health + M1≠M2 + tabelas legíveis |

---

## 5. Estimativa consolidada

### 5.1 Por prioridade (catálogo v3 + adds)

| Prioridade | IDs | Horas (soma) |
|------------|-----|--------------|
| **P0 ops** | UX-02 (8), UX-14 (3), UX-17 (2) | **13h** |
| **P1** | UX-03 (12), UX-04 (4), UX-08 (3), UX-15 (8), UX-21 (3) | **30h** |
| **P2** | UX-05 (2), UX-06 (2), UX-09 (6), UX-10 (16), UX-12 (4), UX-19 (6) | **36h** |
| **P3** | UX-07 (6), UX-11 (2), UX-13 (3), UX-16 (4), UX-18 (3), UX-20 (2), UX-22 (2) | **22h** |
| **DEFERRED** | UX-01 | **80h+** (fora do total ativo) |
| **Total ativo (sem UX-01)** | UX-02…22 | **~101h** |
| **Pré-VPS pack (Onda 1 UX)** | UX-02+17+14+04+21 | **~20h** |

### 5.2 Comparativo com DRAFT

| Fonte | Escopo UX | Horas |
|-------|-----------|-------|
| DRAFT v3 §3 | 18 IDs (sem adds) | ~86h + 80h web |
| Esta revisão | 18 validados + 4 adds | **~101h** + 80h web DEFERRED |
| Onda 1 recomendada | honesty + legibilidade | **~20h** |

### 5.3 Ordem de resolução recomendada (somente UX)

```text
Pré-VPS (~20h)          Curto (~30h)              Médio (~36h)           Backlog
─────────────────       ──────────────────        ────────────────       ────────
UX-02 progress          UX-03 display shared      UX-09 coverage one     UX-07 pager
UX-17 health --human    UX-15 workspace home      UX-10 modular PDF      UX-11 links
UX-14 M1≠M2 labels      UX-08 error standard      UX-05/06 codes/flags   UX-13 a11y
UX-04 never-truncate    UX-21 post-run summary    UX-12 validation       UX-16 idioma
                        UX-19 --examples          UX-19 cont.            UX-18 TOC
                                                                          UX-20 --force
                                                                          UX-22 tokens
                                                                          UX-01 web ★
```

★ UX-01 só após VPS + CLI diário estável.

### 5.4 Dependências cruzadas (UX ↔ outras áreas)

| Débito UX | Depende de | Nota |
|-----------|------------|------|
| UX-14 / labels | coverage contract M1≠M2, OBS-03 | Copy alinhada a docs de domínio |
| UX-17 --human | SYS-003/004 health honesty | Mesmos claims; sem greenwash |
| UX-09 coverage entry | DT coverage tables / contract CLI | Dados completos |
| UX-02 progress | — | Independente; pode paralelizar Onda 0 |
| UX-01 web | VPS + SEC auth + CLI estável | Explicitamente último |

---

## 6. Veredito da revisão Phase 6

| Item | Resultado |
|------|-----------|
| DRAFT §3 Frontend/UX | **Validado** com 2 re-elevações (UX-02, UX-04) |
| UX-01 | **DEFERRED** confirmado — não P0 |
| Honesty / fail-closed | **Reforçado** como princípio de design pré-VPS |
| Débitos adicionados | **4** (UX-19…22) — continuidade v2 sem colidir IDs |
| Perguntas do Architect (7) | **Todas respondidas** |
| Product direction | **CLI-first** — Web UI fora do caminho crítico |
| Estimativa ativa UX | **~101h** (sem web); pack pré-VPS **~20h** |

**Recomendação ao Architect / PM:** incorporar re-elevações UX-02/UX-04 e IDs UX-19…22 no assessment final; manter Onda 1 UX paralelizável com residual de Onda 0; **não** abrir épico de Web UI antes de health humano + progress + M1≠M2 no workspace.

---

## 7. Changelog desta revisão

| Data | Versão | Mudança |
|------|--------|---------|
| 2026-07-13 | 2.0 | 12 validados + 5 adds (IDs antigos UX-13…17); 8 perguntas respondidas |
| 2026-07-17 | **3.0** | Alinhado a frontend-spec v3 + DRAFT v3; renumeração documentada; UX-02 CRITICAL / UX-04 HIGH; UX-01 DEFERRED reafirmado; 4 adds (UX-19…22); foco pré-VPS honesty |

---

*Revisão gerada por Uma (@ux-design-expert) em 2026-07-17 — Brownfield Discovery Phase 6.*  
*Fontes: `docs/prd/technical-debt-DRAFT.md` v3.0 · `docs/frontend/frontend-spec.md` v3.0 · review v2 2026-07-13.*  
*Próxima etapa do pipeline: @qa → `docs/reviews/qa-review.md` (Phase 7).*
