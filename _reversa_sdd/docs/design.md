# Docs — Design Técnico (v2.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d
> **Fontes brownfield:** plano-mestre-fechamento-gaps-extra-consultoria.md §5 (P0-01), epic-technical-debt.md

## Interface

A documentação não expõe interface programática. É consumida por:
- Agentes AIOX (via `Read` tool, context injection)
- Desenvolvedores humanos (via editor Markdown)
- Pipeline Reversa (`.reversa/`, `_reversa_sdd/`)
- Orquestrador de execução (`plano-mestre-*.md`, `epic-*.md`)

## Estrutura de Conhecimento (18 segmentos)

```
docs/
├── architecture/     (3)  — C4 L1-L3, system-architecture.md
├── assessment/       (1)  — Avaliações de baseline
├── coverage-truth/   (3)  — Modelo semântico de cobertura
├── decisions/        (4)  — ADRs de negócio (preço, contract-intel, contrato)
├── epic-coverage/    (8)  — Métricas e manifestos de cobertura por epic
├── frontend/         (1)  — Frontend spec (Fase 3 Brownfield)
├── guides/           (1)  — Guias de uso interno
├── ops/              (8)  — Runbooks: backup, monitoring, troubleshooting, onboarding
├── prd/              (3)  — PRD principal, technical-debt DRAFT + assessment
├── qa/               (2)  — QA review reports
├── reports/          (3)  — TECHNICAL-DEBT-REPORT.md, outros relatórios
├── research/         (10) — Pesquisas de mercado, concorrentes, fontes
├── reviews/          (3)  — DB specialist review, UX review, QA review
├── sessions/         (1)  — Logs de sessão
├── stories/          (9)  — Epic technical-debt + 5 stories + QW-01 + TD stories
├── td-001/           (18) — Diagnósticos técnicos detalhados (maior segmento)
├── td-003/           (1)  — Diagnóstico de cobertura
└── workplans/        (1)  — Planos de trabalho
```

## Fluxo Principal

1. **Descoberta (Brownfield):** Fases 1-10 produzem `architecture.md` → `SCHEMA.md` + `DB-AUDIT.md` → `frontend-spec.md` → `technical-debt-DRAFT.md` → reviews → `technical-debt-assessment.md` → `TECHNICAL-DEBT-REPORT.md` → epic + stories
2. **Planejamento estratégico:** `plano-mestre-fechamento-gaps-extra-consultoria.md` define 9 EPICs P0, ordem de execução, métricas de cobertura (§3), e Definition of Done (§22)
3. **Execução tática:** `epic-technical-debt.md` consolida 79 dívidas + 9 EPICs → 5 stories imediatas (1.1-1.5)
4. **Engenharia reversa (Reversa):** `_reversa_sdd/` contém specs extraídas do código; `.reversa/` controla estado da extração
5. **Diagnóstico contínuo:** `docs/td-001/` mantém 18 análises detalhadas de problemas específicos

## Fluxos Alternativos

- **Documentação autogerada:** `_reversa_sdd/adrs/` (16 ADRs extraídos do código pelo Detective)
- **Manifestos de cobertura:** `docs/epic-coverage/` e `docs/coverage-truth/` documentam o estado real vs desejado
- **Correção de documentação (P0-01):** `plano-mestre §5` define regras para eliminar claims contraditórios, separar CURRENT_STATE/TARGET_STATE/KNOWN_BLOCKERS/PROHIBITED_CLAIMS

## Dependências

| Componente | Relação | Como usa |
|------------|--------|----------|
| Código em `scripts/` | Fonte de verdade primária | Docs devem refletir código, não o contrário |
| `.reversa/` | Framework de extração | Estado, plano, checkpoints da engenharia reversa |
| `_reversa_sdd/` | Artefatos extraídos | 16 ADRs, 6 flowcharts, code-analysis, ERD, C4 |
| `plano-mestre-*.md` | Orquestração | Define o que existe, o que falta, e em que ordem fazer |
| Agentes AIOX | Consumidores | Lêm docs via context injection para tomar decisões |
| Git history | Versionamento | Commits documentam evolução; docs referenciam SHAs |

## Decisões de Design Identificadas

| Decisão | Evidência no código | Confiança |
|---------|---------------------|-----------|
| Docs são fonte de verdade para planejamento, não para implementação | `CLAUDE.md`, `plano-mestre §2` | 🟢 |
| Documentação brownfield segue workflow de 10 fases | `docs/prd/technical-debt-assessment.md`, workflow-execution.md | 🟢 |
| Stories usam template padronizado com checkboxes, AC, File List | `docs/stories/story-1.1*.md` a `story-1.5*.md` | 🟢 |
| P0-01 exige separação CURRENT_STATE / TARGET_STATE / KNOWN_BLOCKERS / PROHIBITED_CLAIMS | `plano-mestre §5` | 🟢 |
| Nenhum documento deve declarar PostgreSQL Hetzner, Supabase ou timers como realidade atual | `plano-mestre §5` | 🟢 |
| Manifestos de cobertura diferenciam data presence de operational coverage | `plano-mestre §3.4` | 🟢 |

## Estado Interno

Documentação é estática (Markdown no repo). Não mantém estado runtime. Versionada via git. Atualização é manual ou via agentes AIOX (Write/Edit tools).

## Observabilidade

| Sinal | Método | Frequência |
|-------|--------|------------|
| Consistência com código | `grep` por números antigos, claims proibidos | Manual / P0-01 |
| Cobertura de docs | Contagem de arquivos por diretório | Snapshots do Reversa |
| Docs desatualizados | Comparação de data de commit vs data do doc | Manual |
| Claims contraditórios | Busca por afirmações conflitantes entre docs | P0-01 gate |

## Riscos e Lacunas

- 🔴 **LACUNA (plano-mestre §5):** P0-01 (Congelar escopo e limpar documentação) não executado. Há claims contraditórios entre docs (ex: números antigos de cobertura, declarações de fontes como "ativas" sem prova, referências a deploy Hetzner como realidade atual).
- 🔴 **LACUNA (plano-mestre §5):** `docs/stories/epics/epic-master-b2g/story-FIX-SCHEMA-MISMATCH.md` contradiz o schema operacional posterior — precisa ser transformada em registro histórico ou reescrita.
- 🔴 **LACUNA:** PRD e README podem conter números de universo/cobertura desatualizados que divergem da seed atual (1.093 entes no raio).
- 🟡 `docs/td-001/` (18 arquivos) é o maior segmento de documentação. Cobertura e atualidade desses diagnósticos não foram verificadas contra o código atual (30 novos commits).
- 🟡 A distinção entre `docs/stories/` (execução atual) e `docs/stories/epics/` (histórico) não está formalmente documentada.
- 🟡 ~590 arquivos Markdown no total. Não há índice central ou search index — descoberta depende de `grep` e conhecimento tribal.
