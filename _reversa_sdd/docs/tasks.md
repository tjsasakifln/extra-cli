# Docs — Tasks (v2.0)

> Gerado pelo Writer em 2026-07-11 | **Expandido pelo Reviewer em 2026-07-13** | doc_level: completo | Base: 249340d

## Tarefas de Manutenção

| # | Tarefa | Fonte | Confiança |
|---|--------|-------|-----------|
| T-DC01 | Manter diagnósticos TD atualizados com cada sprint | `docs/td-001/` | 🟡 |
| T-DC02 | Manter arquitetura C4 sincronizada com código | `docs/architecture/` | 🟡 |
| T-DC03 | Atualizar runbooks após mudanças de infra | `docs/ops/` | 🟡 |
| T-DC04 | Documentar novas integrações externas | `docs/` | 🟡 |
| T-DC05 | Manter quality gates YAML alinhados com código de validação | `docs/qa/` | 🟡 |

## Tarefas de Correção (🔴 LACUNAS — P0-01)

| # | Tarefa | Fonte | Confiança | Bloqueia |
|---|--------|-------|-----------|----------|
| T-DC06 | 🔴 Executar P0-01: separar CURRENT_STATE / TARGET_STATE / KNOWN_BLOCKERS / PROHIBITED_CLAIMS em README, PRD, manifests | `plano-mestre §5` | 🔴 | DoD §16 |
| T-DC07 | 🔴 Marcar `story-FIX-SCHEMA-MISMATCH.md` como registro histórico (contradiz schema posterior) | `plano-mestre §5` | 🔴 | P0-02 |
| T-DC08 | 🔴 Atualizar números de universo em todos os docs para 1.093 entes (seed atual) | `plano-mestre §5` | 🔴 | Consistência |
| T-DC09 | 🔴 Remover claims de deploy Hetzner/Supabase como realidade atual | `plano-mestre §5` | 🔴 | DoD §16 |
| T-DC10 | 🔴 Não declarar fonte como "ativa" apenas porque existe módulo Python | `plano-mestre §5` | 🔴 | P0-06 |
| T-DC11 | Atualizar docs/stories/ com status real de cada story (InReview, Done, etc.) | `docs/stories/` | 🟡 | Rastreabilidade |
| T-DC12 | Criar índice central de documentação (search index ou TOC) para ~590 arquivos | `docs/` | 🟡 | Descoberta |

**Estimativa:** 3-5 dias (12 tarefas, 5 delas 🔴 P0-01 blockers)

**Pré-requisitos:** Nenhum. P0-01 é pré-requisito para todos os outros EPICs.
