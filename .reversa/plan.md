# Plano de Exploração — extra consultoria

> Criado pelo Reversa em 2026-07-11
> Marque cada tarefa com ✅ quando concluída.
> Você pode editar este plano antes de iniciar: adicione, remova ou reordene tarefas conforme necessário.

---

## Fase 1: Reconhecimento 🔍

- [x] **Scout** — Mapeamento de estrutura de pastas e tecnologias ✅
- [x] **Scout** — Análise de dependências e gerenciadores de pacotes ✅
- [x] **Scout** — Identificação de entry points, CI/CD e configurações ✅

## Decisão de organização das specs 🗂️

> Entre o Scout e o Arqueólogo, o Reversa pergunta como você quer organizar as specs (por módulo, caso de uso, endpoint, híbrida, por features ou customizada). A escolha fica persistida em `.reversa/config.toml` na seção `[specs]` e não será reperguntada em execuções futuras. Para reapresentar o menu, remova manualmente a seção.

## Fase 2: Escavação 🏗️

> Módulos identificados pelo Scout em 2026-07-11.

- [x] **Archaeologist** — Análise do módulo `crawl` (35 arquivos, 14K LOC, 10 crawlers + 4 templates) ✅
- [x] **Archaeologist** — Análise do módulo `intel` (8 arquivos, 12K LOC, pipeline 7 stages + 5 gates) ✅
- [x] **Archaeologist** — Análise do módulo `reports` (6 arquivos, 9.5K LOC, PDF/Excel executivo) ✅
- [x] **Archaeologist** — Análise do módulo `lib` (11 arquivos, 2.5K LOC, 6 algoritmos core) ✅
- [x] **Archaeologist** — Análise do módulo `matching` (2 arquivos, 300 LOC, cascade 3 níveis) ✅
- [x] **Archaeologist** — Análise do módulo `config` (7 arquivos, 8.8K LOC YAML, 13 setores B2G) ✅
- [x] **Archaeologist** — Análise do módulo `db` (25 arquivos, 6K LOC SQL, 19 migrations + schema real) ✅
- [x] **Archaeologist** — Análise do módulo `deploy` (42 arquivos, 3.5K LOC, 20 systemd timers) ✅
- [x] **Archaeologist** — Análise do módulo `docs` (50 arquivos, 4K LOC, TD docs + arquitetura) ✅

## Fase 3: Interpretação 🧠

- [x] **Detetive** — Arqueologia Git (20 commits, 3 epics) ✅
- [x] **Detetive** — 17 regras de negócio implícitas e 6 máquinas de estado ✅
- [x] **Detetive** — Matriz de permissões (single-tenant, sem RBAC) ✅
- [x] **Detetive** — 11 ADRs (6 originais + 5 novos do commit e9729e1) ✅
- [x] **Arquiteto** — Diagramas C4 (Contexto, Containers, Componentes) ✅
- [x] **Arquiteto** — ERD completo (8 tabelas, 33 índices, 10 funções, 5 views) ✅
- [x] **Arquiteto** — Spec Impact Matrix (cross-reference módulos×regras×ADRs×épicos) ✅

## Fase 4: Geração 📝

- [x] **Redator** — Specs SDD por componente (9 módulos, 27 arquivos canônicos) ✅
- [x] **Redator** — N/A: sem API HTTP (sistema CLI) ✅
- [x] **Redator** — N/A: sistema single-tenant CLI, sem user stories tradicionais ✅
- [x] **Redator** — Code/Spec Matrix (75 arquivos mapeados, 84% cobertura 🟢) ✅

## Fase 5: Revisão ✅

- [x] **Revisor** — Revisão cruzada de specs (Codex indisponível, revisão solo) ✅
- [x] **Revisor** — 6 perguntas para validação (3 🔴, 3 🟠) em questions.md ✅
- [x] **Revisor** — Relatório de confiança final (91% 🟢, 10 gaps, 4 reclassificações) ✅

---

## Agentes Independentes

> Execute estes agentes quando os recursos estiverem disponíveis — podem rodar em qualquer fase.

- [ ] **Visor** — Análise de interface via screenshots
- [ ] **Data Master** — Análise completa do banco de dados
- [ ] **Design System** — Extração de tokens de design
- [ ] **Tracer** — Análise dinâmica (requer sistema acessível)

---

## Próximo passo

Após o Time de Descoberta concluir e o `_reversa_sdd/` estar populado, você pode disparar um dos fluxos seguintes:

- `/reversa-migrate`: orquestrador do **Time de Migração** (Paradigm Advisor → Curator → Strategist → Designer → Screen Translator → Inspector). Gera as specs do sistema novo. Saída em `_reversa_sdd/migration/` e `_reversa_sdd/screens/`.
- `/reversa-reconstructor`: gera plano bottom-up para reimplementar o software a partir das specs do legado (uma tarefa por sessão).
