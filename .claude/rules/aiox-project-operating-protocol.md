---
description: Protocolo operacional obrigatório do AIOX — invariantes de alto valor. Procedimentos detalhados nas skills sob demanda. Carregado em todas as sessões.
---

# AIOX Project Operating Protocol v2.0

> **PROJECT-CUSTOMIZED** | AIOX v2.1.0 | 2026-07-13
> Regra completa: `.claude/rules/aiox-project-operating-protocol.md`
> Skills detalhadas: `.claude/skills/aiox-*/SKILL.md`
> Hooks de enforcement: `.claude/settings.local.json` + `.claude/hooks/*.cjs`

---

## 1. Modo padrão — AIOX automático

Toda solicitação de desenvolvimento é processada via AIOX. Claude infere agente, workflow e gates automaticamente. Usuário NÃO digita `@agente`.

Antes de agir: (1) classificar solicitação, (2) identificar agente com autoridade, (3) verificar story, (4) selecionar workflow, (5) verificar gates, (6) executar/delegar, (7) manter rastreabilidade.

---

## 2. Níveis de risco — processo proporcional

| Nível | Aplica-se a | Fluxo mínimo |
|-------|------------|-------------|
| **FAST** | Typo, doc não-operacional, cosmético isolado, mudança trivial sem efeito funcional | Registro leve + diff revisado + testes aplicáveis. Sem push automático. |
| **STANDARD** | Bugs, features localizadas, refatorações limitadas | @sm → @po → @dev → @qa → @po → @devops |
| **HIGH-RISK** | Segurança, auth, dados, migrations, pagamentos, arquitetura, infra, produção, refatorações amplas | @architect + @data-engineer (se DB) + @sm → @po → @dev → @qa (aprofundado) → gate sistêmico → @po → @devops |

**Default: STANDARD.** Na dúvida, subir para o nível mais rigoroso.

---

## 3. Autoridade exclusiva dos agentes

| Agente | Autoridade exclusiva |
|--------|---------------------|
| @devops | `git push`, PR, release, tag, MCP management |
| @architect | Decisões de arquitetura, tecnologia, impacto sistêmico |
| @qa | Veredito de qualidade (PASS/CONCERNS/FAIL/WAIVED) |
| @po | Validação e fechamento de story |
| @sm | Criação e refinamento de story |
| @dev | Implementação (git add/commit local, nunca push) |
| @data-engineer | Schema, migrations, RLS, integridade de dados |
| @pm | PRD, epics, escopo, estratégia |
| @analyst | Pesquisa, discovery, análise |
| @ux-design-expert | UX, UI, acessibilidade, design system |

**Nenhum agente assume autoridade de outro. @dev NUNCA autoaprova QA ou fecha story.**

---

## 4. Story obrigatória antes de código

Proibido alterar código sem story validada. Exceções: FAST, investigação read-only, spike descartável (registrar justificativa).

Fluxo: procurar story ativa → não existe? @sm cria → @po valida → @dev implementa.

Story deve conter: problema, valor, causa raiz, escopo IN/OUT, dependências, riscos, baseline, estado-alvo, AC testáveis (Given/When/Then), testes requeridos, arquivos afetados, DoD, rollback, restrição de nova dívida.

---

## 5. Ciclo obrigatório

```
@sm → @po → @dev → @qa → @dev (corrige) → @qa (veredito) → @po (fecha) → @devops (push)
```

Story concluída somente quando: AC atendidos, testes passam, lint/typecheck/build passam, QA veredito aceitável, PO fechou, backlog/epic reconciliados, DevOps executou gates.

---

## 6. QA independente — nunca o implementador

QA verifica conforme risco: rastreabilidade, regressão, segurança, integridade, erros, observabilidade, performance, edge cases, concorrência, migrations, compatibilidade, dívida introduzida.

Veredito: PASS | CONCERNS | FAIL | WAIVED. Incluir evidências e riscos residuais. FAIL → retorna ao @dev. CONCERNS → itens de backlog com owner e prazo.

**Proibido: mesmo agente implementar e ser única fonte de validação.**

---

## 7. Fechamento pelo PO — obrigatório

Após QA PASS: @po executa po-close-story.md. Verifica veredito, reconcilia checkboxes, atualiza epic/backlog, registra follow-ups, confirma DoD.

**Sem fechamento do PO, story NÃO está finalizada.**

---

## 8. Publicação — somente @devops após gates

Pré-condições para push: story fechada pelo PO, QA veredito aceitável, lint/typecheck/testes/build passam.

**@devops é o único que executa `git push`, cria PR, release ou tag.** Hook `enforce-git-push-authority.cjs` bloqueia qualquer outro.

---

## 9. Correção automática de desvio

Desvios: código sem story, agente fora de autoridade, QA pelo implementador, push sem gates, dívida não registrada, story não fechada.

Ação: interromper, declarar desvio, corrigir curso. Usar Agent tool para delegar ao agente correto.

---

## 10. Skills sob demanda

Procedimentos detalhados em skills acionadas automaticamente:

| Skill | Quando aciona | Arquivo |
|-------|--------------|---------|
| aiox-route | Classificar solicitação e selecionar workflow | `.claude/skills/aiox-route/SKILL.md` |
| aiox-story-cycle | Ciclo completo de uma story | `.claude/skills/aiox-story-cycle/SKILL.md` |
| aiox-brownfield | Discovery e saneamento de legado | `.claude/skills/aiox-brownfield/SKILL.md` |
| aiox-wave-gate | Gate sistêmico ao final de wave | `.claude/skills/aiox-wave-gate/SKILL.md` |
| aiox-publish | Publicação segura via @devops | `.claude/skills/aiox-publish/SKILL.md` |

---

## Referências

- Constitution: `.aiox-core/constitution.md`
- Agent authority: `.claude/rules/agent-authority.md`
- Story lifecycle: `.claude/rules/story-lifecycle.md`
- Workflow execution: `.claude/rules/workflow-execution.md`
- Agent handoff: `.claude/rules/agent-handoff.md`
- Hooks: `.claude/settings.local.json`, `.claude/hooks/`
- Stories: `docs/stories/`
- PRD: `docs/prd/`

---

*PROJECT-CUSTOMIZED. Não modifica camadas L1, L2 ou seções FRAMEWORK-OWNED.*
