# UX Specialist Review

**Data:** 2026-07-13
**Revisor:** Uma (UX Design Expert)
**Documento Base:** `docs/prd/technical-debt-DRAFT.md` (Secao 3 — Debites de Frontend/UX)
**Fonte Original:** `docs/frontend/frontend-spec.md`
**Status:** Revisao Completa

---

## 1. Valores de Referencia (Metodologia)

| Fator | Peso na Priorizacao UX |
|-------|------------------------|
| Impacto direto no usuario final | 40% |
| Frequencia de uso (quantas journeys afetadas) | 25% |
| Tempo perdido/atrito por incidente | 20% |
| Esforco de resolucao (horas) | 15% |

Prioridade UX resultante = combinacao ponderada dos fatores acima. Independe da prioridade tecnica (P0-P3) da matriz consolidada.

---

## 2. Debites Validados

12 debites originais revisados. Severidade ajustada em 3 casos, mantida em 9.

| ID | Debito | Severidade Original | Severidade Revisada | Horas | Prioridade UX | Impacto UX | Notas |
|----|--------|---------------------|---------------------|-------|---------------|------------|-------|
| UX-01 | No web UI — toda interacao requer SSH/VPS | HIGH | HIGH | 80h+ | P3 (estrategico) | Extremo — limita base a usuarios com acesso VPS. Nao ha portal client-facing, nem dashboard rapido. Toda consulta exige terminal + SSH. | Debito real, mas ESTRATEGICO. Nao deve competir com melhorias CLI de curto prazo. Web UI MVP (FastAPI+HTMX) resolveria 60% dos casos de uso com ~40h, nao 80h. Ver recomendacao de design. |
| UX-02 | No progress indicators — comandos longos sem feedback | HIGH | **CRITICAL** | 8h | **P0** | Critico — Journey 4 (Data Ingestion & Radar) documenta usuarios olhando terminal vazio por minutos. Risco real de abortarem comandos prematuramente. 3 comandos afetados: `update`, `radar`, geracao de PDF. | **SEVERIDADE AUMENTADA.** De HIGH para CRITICAL. E a dor de UX mais frequente e de menor esforco para resolver. 8h e realista para `rich.progress.Progress` nos 3 comandos principais. |
| UX-03 | Dual display paradigm — `rich` vs raw `print()` sem componente compartilhado | MEDIUM | MEDIUM | 12h | P2 | Medio — inconsistencia visual entre ferramentas. Usuario nota a diferenca de qualidade ao alternar entre `local_datalake` (rich) e `opportunity_intel` (raw). | Severidade correta. O `rich` ja e dependencia do projeto. A migracao e custo baixo para ganho alto de consistencia. |
| UX-04 | Table truncation — `_print_table()` trunca em 20 chars / 10 cols | MEDIUM | **HIGH** | 4h | **P1** | Alto — colunas como `objeto` e `orgao_nome` sao truncadas a 20 chars, tornando a listagem inutil para analise. Usuario obrigado a usar `--json` ou `show` em cada ID. | **SEVERIDADE AUMENTADA.** De MEDIUM para HIGH. 20 chars e agressivo demais. Colunas de identificacao (objeto, orgao) precisam de no minimo 60 chars. Debito de 4h que afeta diretamente a Journey 2 (Finding Bidding Opportunities). |
| UX-05 | Exit codes inconsistentes — 0/1 vs 0/1/2 entre ferramentas | LOW | LOW | 2h | P3 | Baixo — impacto maior em automacao/scripting que em uso interativo. Usuario final raramente ve exit codes. | Severidade correta para UX interativa. Para DevOps/automacao, seria MEDIUM. |
| UX-06 | Output flags inconsistentes — `--format table|json` vs `--json` booleano | LOW | LOW | 2h | P3 | Baixo — carga cognitiva ao alternar ferramentas, mas usuarios regulares aprendem o padrao de cada uma. | Severidade correta. Resolver como parte do UX-03 (unificacao display paradigm). |
| UX-07 | No pagination para grandes result sets (500+ linhas) | LOW | **MEDIUM** | 6h | P2 | Medio — terminal overflow com 500+ linhas. Usuario perde o inicio da listagem. Ferramentas de busca (`list`, `search`) sao as mais afetadas. | **SEVERIDADE AUMENTADA.** De LOW para MEDIUM. 500 linhas e facil de alcancar em `list --limit 500` ou `supplier` com muitos contratos. Solucao: `--pager` flag usando `less` ou `rich.pager`. |
| UX-08 | Empty output on errors — algumas ferramentas printam nada em falha | MEDIUM | MEDIUM | 3h | P1 | Alto — usuario nao sabe se o comando falhou, esta processando, ou o resultado e vazio. Leva a retentativas desnecessarias. | Severidade correta. Afeta todas as journeys. 3h e pouco para implementar formato padrao de erro. |
| UX-09 | Coverage dashboard duplicado em dois CLIs | MEDIUM | MEDIUM | 6h | P2 | Medio — usuario tem dois entry points com UX diferente para mesma funcionalidade. Qual usar? Ambos funcionam? | Severidade correta. Consolidar em unico comando sob `local_datalake` (que ja tem a melhor UX com rich). |
| UX-10 | Gerador de relatorio monolitico — `generate-report-b2g.py` com 287KB | MEDIUM | MEDIUM | 16h | P2 | Medio para usuario final (relatorios ainda geram). Alto para desenvolvedor (manutencao, startup lento). | Severidade correta. Impacto UX indireto (manutencao lenta → bugs demoram mais para corrigir). |
| UX-11 | No terminal hyperlinks — URLs impressas como texto puro | LOW | LOW | 2h | P3 | Baixo — conveniencia, nao blocker. Usuario pode copiar/colar a URL. | Severidade correta. `rich` ja suporta hyperlinks com `console.print("[link]...[/link]")`. Custo quase zero. |
| UX-12 | No input validation messages — args validados so na query DB | LOW | MEDIUM | 4h | P2 | Medio — usuario recebe erro SQL em vez de "UF invalida. Use siglas: SC, PR, RS...". Confuso para nao-tecnicos. | **SEVERIDADE MANTIDA COMO MEDIUM** (arquiteto marcou LOW, revisor propoe MEDIUM). Erros SQL a usuarios nao-tecnicos e falha de UX. Afeta Journey 2 e Journey 3. 4h para adicionar validacao com `argparse` type checkers + `choices`. |

### Resumo de Ajustes de Severidade

| ID | Original | Revisada | Diferenca |
|----|----------|----------|-----------|
| UX-02 | HIGH | **CRITICAL** | +1 nivel |
| UX-04 | MEDIUM | **HIGH** | +1 nivel |
| UX-07 | LOW | **MEDIUM** | +1 nivel |
| UX-12 | LOW | **MEDIUM** (revisor discorda do LOW) | +1 nivel (vs draft original) |
| Demais | — | — | Mantidas |

---

## 3. Debites Adicionados

5 novos debites UX identificados apos revisao holistica das user journeys e da especificacao.

| ID | Debito | Severidade | Horas | Prioridade UX | Justificativa |
|----|--------|------------|-------|---------------|---------------|
| UX-13 | **Ausencia de onboarding / help contextual** — primeiro uso sem guia. `--help` de alguns comandos e minimalista (ex: `radar` tem 8+ parametros sem exemplo de uso). Sem `--examples` flag. | MEDIUM | 6h | P2 | Journey 2 (Finding Opportunities) exige conhecimento previo dos parametros. Usuario novo precisa consultar documentacao externa. 6h para adicionar `--examples` e melhorar help text nos 5 comandos principais (radar, list, show, update, search). |
| UX-14 | **Sem confirmacao antes de operacoes destrutivas** — `export` sobrescreve arquivo existente sem aviso. Geracao de report nao pergunta se pode sobrescrever `output/pdfs/`. | LOW | 2h | P3 | Impacto baixo (arquivos podem ser regenerados), mas frustrante quando usuario perde trabalho. 2h para adicionar `--force` flag + confirmacao interativa. |
| UX-15 | **Formatacao monetaria divergente entre ferramentas** — `_fmt_money()` em opportunity_intel vs `f"R$ {v:,.2f}"` em local_datalake. Mesma funcao, duas implementacoes, possibilidade de divergencia de formato. | LOW | 2h | P3 | Inconsistencia de baixo impacto (ambas produzem `R$ X.xxx,xx`), mas representa duplicacao de codigo e risco de divergencia futura. Resolver como parte do UX-03 (criar `scripts/lib/format.py` compartilhado). |
| UX-16 | **Tracebacks crus expostos ao usuario em erros** — algumas ferramentas nao interceptam excecoes. Usuario ve `Traceback (most recent call last):` em vez de mensagem amigavel. | MEDIUM | 4h | P1 | Journey 2 e Journey 4. Usuario nao-tecnico nao sabe interpretar traceback. Erro SQL ou de rede aparece como paredao de texto. 4h para adicionar `try/except` com `--debug` flag para traceback completo. |
| UX-17 | **Radar output como JSON bruto no stdout** — comando `radar` termina com dump JSON completo no terminal. Sem sumario human-readable. Usuario precisa garimpar o JSON para entender o resultado. | MEDIUM | 3h | P1 | Journey 4. Documentado na frontend-spec: "wall of JSON, no progress". 3h para adicionar sumario pos-execucao (ex: "Radar concluido: 12 oportunidades encontradas, 3 com ranking GO, salvo em output/qw-01/"). |

### Total de Debites Adicionados

| ID | Horas |
|----|-------|
| UX-13 | 6h |
| UX-14 | 2h |
| UX-15 | 2h |
| UX-16 | 4h |
| UX-17 | 3h |
| **Total** | **17h** |

---

## 4. Respostas ao Architect

### Pergunta 1: Unificacao de display paradigm (UX-03) — Migrar TODOS os CLIs para `rich` ou manter dois paradigmas deliberadamente?

**Resposta:** Migrar TODOS os CLIs para `rich`. Nao ha justificativa tecnica para manter dois paradigmas:

- O `rich` ja e dependencia do projeto (instalado via `requirements.txt` / `pyproject.toml`)
- O `local_datalake.py` ja demonstra o padrao desejado (Panels, Tables, colors, boxes)
- O custo de migracao e baixo (~12h) e o ganho de consistencia visual e alto
- `rich` e biblioteca madura (9K+ stars), nao e risco de abandono
- Casos de uso como ANSI colors manuais (TD-006) sao automaticamente eliminados

**Unico cenario para manter raw print:** scripts utilitarios internos de uma unica funcao (< 50 linhas) que nunca serao vistos por clientes.

---

### Pergunta 2: Output flag pattern (UX-06) — `--format table|json|csv` ou `--json` booleano?

**Resposta:** `--format table|json|csv`. Razoes:

1. **Extensibilidade:** `--json` booleano nao escala para 3+ formatos. Se amanha precisar de `--format csv`, `--format markdown`, `--format html`, o `--format` string aceita sem breaking change.
2. **Consistencia com POSIX:** ferramentas padrao (`ps`, `ls`, `jq`) usam `--format` ou `-o` para formato de output.
3. **Descobribilidade:** `--help` mostra `--format {table,json,csv}`, usuario sabe as opcoes. `--json` nao comunica que existem alternativas.

**Recomendacao concreta:** Adotar `--format {table,json,csv}` como padrao unico. Manter `--json` como alias/deprecation warning durante periodo de transicao.

---

### Pergunta 3: Exit code strategy (UX-05) — Padronizar em `sys.exit(0/1/2)` como health-dashboard?

**Resposta:** Sim, adotar o padrao do health-dashboard (`sys.exit(0/1/2)`). Este e o padrao mais expressivo do projeto e atende aos usos:

| Codigo | Significado | Quando Usar |
|--------|-------------|-------------|
| 0 | OK / Success | Comando executou com sucesso |
| 1 | Warning / Partial | Sucesso com alertas (ex: `source-health` com fonte atrasada) |
| 2 | Error / Critical | Falha na execucao (ex: conexao DB falhou, args invalidos) |

**Implementacao:** Criar `scripts/lib/exit_codes.py` com constantes `EXIT_OK=0`, `EXIT_WARN=1`, `EXIT_ERROR=2` para evitar numeros magicos.

---

### Pergunta 4: Progress indicators (UX-02) — `rich.progress.Progress` (ja disponivel) ou `tqdm`?

**Resposta:** `rich.progress.Progress`. Razoes:

1. **Zero dependencia adicional** — `rich` ja esta no projeto. `tqdm` exigiria nova entrada em `requirements.txt`.
2. **Consistencia visual** — se todos os CLIs usarao `rich`, o progress bar deve seguir o mesmo ecossistema.
3. **Funcionalidade equivalente** — `rich.progress.Progress` suporta barras, spinners, tasks multiplas, estimativa de tempo restante. Nao perde para `tqdm` em nada relevante.
4. **Design consistente** — a barra de progresso usara o mesmo schema de cores do resto do CLI (verde=sucesso, amarelo=em andamento, vermelho=erro).

**Casos de uso prioritarios:**
1. `opportunity_intel/cli.py update --source pncp` — loop de paginacao da API PNCP
2. `opportunity_intel/cli.py radar` — processamento multi-etapa (coleta, matching, ranking)
3. `generate-report-b2g.py` — geracao de PDF multi-secao

---

### Pergunta 5: Web UI requirement (UX-01) — Requisito real de curto prazo ou estrategico? Qual perfil de usuario e funcionalidades prioritarias?

**Resposta:** Requisito ESTRATEGICO, nao de curto prazo. Recomendacao:

**Horizonte:** 6-12 meses. Nao tentar no Sprint 0-5.

**Perfil de usuario prioritario:**
1. **Gestor/Consultor Senior** — quer dashboard rapido sem SSH. Precisa de visao geral de oportunidades, coverage status, alertas.
2. **Cliente final** — quer acesso a relatorios e dados sem depender do time Extra Consultoria. Perfil de mais longo prazo.

**Funcionalidades prioritarias (MVP de ~40h, nao 80h):**

| Prioridade | Funcionalidade | Stack Sugerida | Esforco |
|------------|---------------|----------------|---------|
| P0 | Dashboard de coverage + saude do sistema | FastAPI + Jinja2 + Tailwind (HTML estatico gerado) | 15h |
| P1 | Listagem de oportunidades com filtros | FastAPI + HTMX (Tabela com paginacao) | 15h |
| P2 | Visualizacao de detalhe de oportunidade | FastAPI + HTMX | 10h |
| P3 | Autenticacao basica + multi-usuario | FastAPI + Supabase Auth | 20h+ |

**Recomendacao:** Nao desenvolver SPA (Next.js/React). O perfil de uso e interno/consultivo — FastAPI + HTMX + Tailwind oferece o melhor custo-beneficio. Se no futuro houver demanda client-facing com requisitos de UI complexos, ai sim avaliar React/Next.js.

---

### Pergunta 6: Coverage consolidation (UX-09) — Consolidar coverage dashboard em unico entry point?

**Resposta:** Sim, consolidar. Recomendacao:

1. **Entry point unico:** `local_datalake.py coverage` (ou `scripts/coverage/cli.py coverage` se criar pacote separado)
2. **Remover:** `opportunity_intel/cli.py coverage` — redirecionar com deprecation warning por 2 sprints
3. **Manter a implementacao `rich`** de `local_datalake.py` que e superior (Panels, Tables, cores)
4. **Adicionar:** `--export` flag para CSV/JSON (ja existe em local_datalake, manter)

**Dependencia:** DT-02 (migration v3) precisa estar aplicada para que os dados de coverage estejam completos.

---

### Pergunta 7: Table component (UX-04) — Criar componente compartilhado `scripts/lib/rich_table.py` para todos os CLIs?

**Resposta:** SIM, fortemente recomendado. Especificacao do componente:

```python
# scripts/lib/rich_table.py
# Componente compartilhado de tabela para todos os CLIs

def render_table(
    data: list[dict],
    title: str | None = None,
    max_col_width: int = 60,     # ← 60 chars, nao 20
    max_cols: int | None = None, # ← sem limite padrao
    currency_cols: list[str] = [],
    date_cols: list[str] = [],
    pager: bool = False,         # ← paginacao integrada
    format: str = "table",       # ← table, json, csv
) -> str:
    ...
```

**Beneficios:**
- Elimina UX-04 (truncation excessiva), UX-11 (hyperlinks), e contribui para UX-07 (pagination)
- Coluna de URLs vira clickavel automaticamente
- Formato monetario consistente (`R$ X.xxx,xx`)
- Formato de data consistente (`dd/mm/YYYY`)

**Localizacao:** `scripts/lib/` (diretorio que ja existe para modulos compartilhados)

---

### Pergunta 8: Error handling pattern (UX-08) — Formato padrao `[ERROR] Human-readable message` com ou sem sugestao de acao?

**Resposta:** Com sugestao de acao sempre que possivel. Formato padrao:

```
[ERROR] Falha ao conectar no banco de dados.
        → Verifique se o VPS esta online: ssh ec-prod "systemctl status postgresql"
        → Ou use --dsn para especificar conexao alternativa.
        → (use --debug para traceback completo)
```

**Niveis de mensagem:**

| Nivel | Formato | Cor | Acao Sugerida |
|-------|---------|-----|---------------|
| `[ERROR]` | Vermelho (`rich.markup`) | Sempre | Sim, acao concreta |
| `[WARN]` | Amarelo | Quando possivel | Opcional |
| `[INFO]` | Ciano | Nao | Nao |

**Regras:**
1. `ERROR` sempre comeca com `[ERROR]` + mensagem em portugues + sugestao
2. `WARN` comeca com `[WARN]` + mensagem
3. Traceback NUNCA aparece por padrao — apenas com `--debug`
4. Sugestao de acao deve ser executavel (copiar e colar), nao generica ("tente novamente")

---

## 5. Recomendacoes de Design

### 5.1 Arquitetura de Componentes Compartilhados (Grupo UX-03/04/05/06/11)

Criar camada `scripts/lib/display/` com 3 modulos:

```
scripts/lib/
  display/
    __init__.py           # re-export public API
    console.py            # Console configurado (rich.Console com tema)
    table.py              # Tabela compartilhada (render_table)
    format.py             # formatadores: dinheiro, data, cnpj, cep
    errors.py             # Error handler padrao com sugestoes
    progress.py           # Progress bar factory (rich.progress.Progress)
    pager.py              # Paginador (less -R via subprocess ou rich pager)
```

**Dependencias entre modulos:**
```
table.py → console.py, format.py
errors.py → console.py
progress.py → console.py
pager.py → console.py
```

**Tema Compartilhado (design tokens):**

| Token | Valor | Uso |
|-------|-------|-----|
| `color.success` | green | Operacoes bem-sucedidas |
| `color.error` | red | Erros e falhas |
| `color.warning` | yellow | Alertas e warnings |
| `color.info` | cyan | Informacao e destaques |
| `color.muted` | dim | Metadados e detalhes secundarios |
| `color.highlight` | magenta | Valores numericos importantes |
| `money.prefix` | `R$ ` | Prefixo monetario |
| `money.decimal` | `,` | Separador decimal |
| `money.thousands` | `.` | Separador de milhar |
| `date.format` | `dd/mm/YYYY` | Formato de data brasileiro |
| `table.max_col_width` | `60` | Largura maxima de coluna (chars) |
| `table.box` | `box.SIMPLE` | Estilo de borda de tabela |

### 5.2 Fluxo de Error Handling (Solucao para UX-08 e UX-16)

```
Comando CLI
  → try:
      → executa logica
  → except DatabaseError as e:
      → print [ERROR] Falha no banco: {e.mensagem_amigavel}
      → print sugestao acao
      → sys.exit(EXIT_ERROR)
  → except ValidationError as e:
      → print [ERROR] Dado invalido: {e.mensagem}
      → print "Use --help para ver parametros aceitos"
      → sys.exit(EXIT_ERROR)
  → except Exception as e:
      → if args.debug:
      →     print traceback
      → else:
      →     print [ERROR] Erro inesperado: {str(e)[:200]}
      →     print "Use --debug para detalhes"
  → finally:
      → sys.exit(exit_code)
```

### 5.3 Radar Human-Readable Summary (Solucao para UX-17)

Apos execucao do radar, exibir:

```
╭──────────────────────────────────────────────────╮
│ Radar concluido com sucesso                      │
│                                                  │
│   Oportunidades encontradas:  12                 │
│   Ranking GO:                   3                 │
│   Ranking CAUTION:              5                 │
│   Ranking NO-GO:                4                 │
│   Fontes consultadas:           2 (PNCP, BEC)    │
│   Duracao:                      42.3s            │
│                                                  │
│   Salvo em: output/qw-01/radar-2026-07-13/       │
│   Relatorio PDF: output/qw-01/radar-2026-07-13/  │
│                  relatorio.pdf                    │
│                                                  │
│   Proximo passo: python scripts/opportunity_intel │
│                  /cli.py list --status open       │
╰──────────────────────────────────────────────────╯
```

### 5.4 Web UI — Proposta de Arquitetura Minimalista

Para quando UX-01 for priorizado, sugiro:

```
web/
  app.py                    # FastAPI app
  templates/
    base.html               # Layout base (Tailwind CSS)
    dashboard.html          # Coverage + health overview
    opportunities/
      list.html             # Listagem com filtros
      detail.html           # Detalhe da oportunidade
    reports/
      list.html             # Relatorios gerados
  static/
    css/
      style.css             # Custom styles (minimo)
  api/
    routes/
      opportunities.py      # GET /api/opportunities
      coverage.py           # GET /api/coverage
      health.py             # GET /api/health
```

**Stack:** FastAPI + Jinja2 + HTMX + Tailwind CSS (CDN)
**Nao usar:** React, Vue, SPA — overkill para este perfil de uso
**Autenticacao:** Supabase Auth (ja existe conexao Supabase no projeto)

---

## 6. Ordem de Resolucao Recomendada (UX)

Priorizada por impacto no usuario final, nao por facilidade tecnica.

### Sprint 0 (Imediato — ~15h)

| Ordem | ID | Debito | Horas | Criterio de Sucesso |
|-------|----|--------|-------|---------------------|
| 1 | **UX-02** | Progress indicators nos 3 comandos longos | 8h | `update`, `radar`, `generate-report-b2g` mostram barra de progresso |
| 2 | **UX-04** | Table truncation — aumentar para 60 chars + rich.Table | 4h | Colunas `objeto`, `orgao_nome` legiveis em `list` |
| 3 | **UX-17** | Radar summary human-readable | 3h | Radar exibe sumario pos-execucao ao inves de JSON bruto |

**Justificativa:** As 3 maiores dores de UX identificadas nas journeys. Resolvem em 15h com `rich` ja disponivel. Usuario percebe melhoria no primeiro uso.

### Sprint 1 (Curto Prazo — ~15h)

| Ordem | ID | Debito | Horas | Criterio de Sucesso |
|-------|----|--------|-------|---------------------|
| 4 | **UX-08** | Error handling padrao com `[ERROR]` + sugestao | 3h | Todos os CLIs mostram mensagem amigavel em falha |
| 5 | **UX-16** | Esconder tracebacks, mostrar erro amigavel, `--debug` flag | 3h | Erro SQL nao aparece como traceback para usuario final |
| 6 | **UX-13** | Onboarding — `--examples` flag + help melhorado | 6h | `radar --examples`, `list --examples` funcionam |
| 7 | **UX-12** | Input validation com mensagens amigaveis | 4h | "UF invalida: ZZ. Use SC, PR, RS, SP, ..." |

**Justificativa:** Erros que usuarios veem diariamente. Onboarding para novos usuarios. 15h de investimento.

### Sprint 2-3 (Medio Prazo — ~28h)

| Ordem | ID | Debito | Horas | Criterio de Sucesso |
|-------|----|--------|-------|---------------------|
| 8 | **UX-03** | Migrar todos os CLIs para `rich` | 12h | Nenhum `print()` raw em CLI user-facing |
| 9 | **UX-09** | Consolidar coverage dashboard | 6h | Unico entry point com deprecation warning |
| 10 | **UX-07** | Paginacao para result sets grandes | 6h | `list --limit 500` usa pager automatico |
| 11 | **UX-15** | Formatacao monetaria centralizada | 1h | `scripts/lib/display/format.py` com `fmt_money()` |
| 12 | **UX-20** | Formatacao de data centralizada | 1h | `scripts/lib/display/format.py` com `fmt_date()` |
| 13 | **UX-14** | Confirmacao antes de sobrescrever | 2h | `export` pergunta antes de sobrescrever |

### Backlog (Longo Prazo — ~86h)

| Ordem | ID | Debito | Horas |
|-------|----|--------|-------|
| 14 | **UX-10** | Refatorar gerador de relatorio monolitico | 16h |
| 15 | **UX-05** | Padronizar exit codes | 2h |
| 16 | **UX-06** | Padronizar output flags | 2h |
| 17 | **UX-11** | Terminal hyperlinks | 2h |
| 18 | **UX-01** | Web UI (MVP) | 40h+ |

### Roadmap Visual

```
Sprint 0 (15h)     Sprint 1 (16h)      Sprint 2-3 (28h)       Backlog (62h+)
┌────────────┐    ┌────────────┐      ┌────────────┐        ┌────────────┐
│ UX-02 (8h) │    │ UX-08 (3h) │      │ UX-03 (12h)│        │ UX-10 (16h)│
│ UX-04 (4h) │ →  │ UX-16 (3h) │  →   │ UX-09 (6h) │   →    │ UX-05 (2h) │
│ UX-17 (3h) │    │ UX-13 (6h) │      │ UX-07 (6h) │        │ UX-06 (2h) │
│            │    │ UX-12 (4h) │      │ UX-15 (1h) │        │ UX-11 (2h) │
│            │    │            │      │ UX-20 (1h) │        │ UX-14 (2h) │
│            │    │            │      │ UX-14 (2h) │        │ UX-01 (40h+)│
└────────────┘    └────────────┘      └────────────┘        └────────────┘
```

---

## 7. Dependencias entre Debites UX e Outras Areas

| Debito UX | Depende de | Bloqueia | Nota |
|-----------|------------|----------|------|
| UX-03 (unificacao rich) | — | UX-04, UX-05, UX-06, UX-08, UX-11, UX-12, UX-15, UX-20 | Grupo 6 da matriz (UX CLI Standardization) |
| UX-04 (table component) | UX-03 | — | Criar `scripts/lib/display/table.py` |
| UX-09 (coverage consolidation) | DT-02 (v3 tables) | — | Dados de coverage dependem do schema v3 |
| UX-01 (web UI) | TD-025 (ORM), TD-028 (CI/CD) | — | Grupo 7 da matriz |
| UX-17 (radar summary) | — | — | Independente, resolvivel imediatamente |
| UX-16 (error handling) | UX-03 (parcial) | — | Mensagens de erro com `rich.Console` ideal, mas funcional sem |

**Observacao:** O Grupo 6 (UX CLI Standardization) e o maior multiplicador de impacto. Resolver UX-03 (migrar para `rich`) desbloqueia 7 outros debites UX automaticamente ou com esforco reduzido. Por isso, embora UX-02 e UX-04 tenham prioridade maior no Sprint 0, o UX-03 deve comecar no Sprint 1 para maximizar o efeito cascata.

---

## 8. Resumo Executivo

| Metrica | Valor |
|---------|-------|
| Debites validados (originais) | 12 |
| Debites com severidade ajustada | 4 (UX-02↑, UX-04↑, UX-07↑, UX-12↑) |
| Debites adicionados | 5 (UX-13 a UX-17) |
| **Total de debites UX revisados** | **17** |
| Esforco total estimado (sem UX-01) | 64h (original 65h → revisado 64h + 17h novos = 81h) |
| Esforco UX-01 (web UI MVP) | ~40h (estimativa revisada para baixo: 80h → 40h MVP) |
| Esforco total com Web UI | ~121h |
| **Resolvivel em Sprints 0-1** | **31h** (maior impacto, menor esforco) |

### Top 5 Recomendacoes (Ordem de Execucao)

1. **UX-02 (8h)** — Adicionar `rich.progress.Progress` nos comandos `update`, `radar` e geracao de PDF. Impacto imediato na maior dor de UX do projeto.
2. **UX-04 (4h)** — Aumentar limite de truncamento de 20 para 60 chars + usar `rich.Table`. Usuario volta a ler dados sem precisar de `--json`.
3. **UX-17 (3h)** — Adicionar sumario human-readable ao final do radar. Elimina "wall of JSON".
4. **UX-08 + UX-16 (6h)** — Implementar tratamento de erros padrao com `[ERROR]` + sugestao de acao + `--debug` para traceback.
5. **UX-13 (6h)** — Adicionar `--examples` flag e melhorar help texts. Reduz barreira de entrada para novos usuarios.

---

*Revisao gerada por Uma (UX Design Expert Agent) em 2026-07-13.*
*Documento base: `docs/prd/technical-debt-DRAFT.md` (Secao 3 — Debites de Frontend/UX)*
*Fonte complementar: `docs/frontend/frontend-spec.md`*
*Status: Revisao completa com 17 debites analisados (12 validados + 5 adicionados), 8 perguntas respondidas.*
