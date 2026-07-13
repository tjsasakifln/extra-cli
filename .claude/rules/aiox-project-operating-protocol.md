---
description: Protocolo operacional obrigatório do AIOX — torna automático o uso correto de agentes, stories, workflows, quality gates, handoffs e fechamento do ciclo. Carregado em todas as sessões.
---

# AIOX Project Operating Protocol

> **Tipo:** PROJECT-CUSTOMIZED | **Versão:** 1.0.0 | **Criado:** 2026-07-13
>
> Este documento estabelece o protocolo operacional obrigatório do AIOX neste projeto.
> Nenhuma seção FRAMEWORK-OWNED, camada L1 ou camada L2 foi modificada.
> todo agente, workflow e gate referenciado existe na versão instalada (AIOX v2.1.0).

---

## 1. AIOX como modo padrão de operação

Toda solicitação que envolva criação, alteração, correção, refatoração, manutenção, migração, documentação técnica, arquitetura, banco de dados, interface, testes, infraestrutura ou publicação deve ser tratada por meio do AIOX.

Claude não deve implementar mudanças diretamente apenas porque o usuário pediu algo em linguagem natural.

Antes de agir, Claude deve:

1. classificar a solicitação;
2. identificar o agente que possui autoridade sobre o trabalho;
3. identificar se existe uma story válida;
4. determinar o workflow correto;
5. verificar os gates necessários;
6. executar ou delegar pelo AIOX;
7. manter os artefatos de rastreabilidade atualizados.

O usuário não precisa escrever `@dev`, `@qa`, `@architect`, `@sm`, `@po`, `@pm`, `@devops` ou `@aiox-master`. Claude deve inferir e utilizar automaticamente o agente adequado.

---

## 2. Não simular agentes no mesmo contexto

Quando o trabalho exigir mais de um agente, Claude não deve fingir sucessivamente ser PM, Architect, Dev e QA dentro do mesmo contexto.

Use delegação real via `Agent` tool com o `subagent_type` apropriado:

| Agente AIOX | subagent_type |
|-------------|---------------|
| @dev | aiox-dev |
| @qa | aiox-qa |
| @architect | aiox-architect |
| @pm | aiox-pm |
| @po | aiox-po |
| @sm | aiox-sm |
| @analyst | aiox-analyst |
| @data-engineer | aiox-data-engineer |
| @devops | aiox-devops |
| @ux-design-expert | aiox-ux |

Cada agente deve receber somente o contexto necessário à sua função, preservando independência crítica entre planejamento, implementação e validação.

---

## 3. Autoridade exclusiva dos agentes

Respeite rigorosamente a matriz de autoridade do AIOX (`.claude/rules/agent-authority.md`).

Regras mínimas:

* `@analyst`: pesquisa, discovery, análise de negócio e investigação.
* `@pm`: PRD, produto, escopo, epics e estratégia.
* `@architect`: arquitetura, impactos sistêmicos, dependências e decisões técnicas.
* `@sm`: criação e refinamento detalhado de stories.
* `@po`: validação inicial, priorização, integridade do backlog e fechamento de stories.
* `@dev`: implementação, correção e refatoração.
* `@qa`: testes, revisão independente, riscos e veredito de qualidade.
* `@data-engineer`: schema, migrations, RLS, integridade e performance de dados.
* `@ux-design-expert`: UX, UI, acessibilidade e design system.
* `@devops`: push, pull request, CI/CD, releases, tags e operações remotas.
* `@aiox-master`: roteamento, coordenação e correção do processo.

Nenhum agente deve assumir a autoridade exclusiva de outro.

Especialmente:

* somente `@devops` pode executar `git push`;
* somente `@devops` pode criar pull request;
* somente `@devops` pode criar release ou tag;
* decisões arquiteturais pertencem ao `@architect`;
* vereditos de qualidade pertencem ao `@qa`;
* stories detalhadas devem ser preparadas pelo `@sm`;
* o fechamento de stories deve ser feito pelo `@po`.

---

## 4. Story obrigatória antes de código

Nenhuma alteração de código deve começar sem uma story associada.

Ao receber uma solicitação de mudança:

1. procure uma story ativa correspondente em `docs/stories/`;
2. se existir, valide se ela cobre integralmente a solicitação;
3. se não existir, encaminhe automaticamente para criação ou refinamento pelo `@sm`;
4. encaminhe a story ao `@po` para validação;
5. somente depois permita implementação pelo `@dev`.

Exceções devem ser raras e explícitas, como investigação sem alteração, spike descartável ou incidente emergencial. Mesmo nesses casos, deve existir registro mínimo do trabalho e de sua justificativa.

Não considere uma descrição solta, mensagem de chat ou comentário como substituto de story válida.

---

## 5. Qualidade mínima obrigatória da story

Antes da implementação, toda story deve conter:

* problema e contexto;
* valor esperado;
* causa raiz conhecida ou hipótese de causa;
* escopo incluído;
* escopo excluído;
* dependências;
* riscos;
* baseline atual;
* estado-alvo;
* critérios de aceite testáveis;
* critérios Given/When/Then quando aplicáveis;
* testes unitários requeridos;
* testes de integração requeridos;
* testes de regressão requeridos;
* requisitos não funcionais;
* arquivos ou módulos provavelmente afetados;
* Definition of Done;
* condições de rollback;
* restrições para não introduzir nova dívida técnica.

Se esses elementos estiverem ausentes, encaminhe automaticamente a story ao `@sm` para refinamento e depois ao `@po` para nova validação.

---

## 6. Ciclo obrigatório de cada story

O fluxo padrão deve ser:

```text
@sm prepara ou refina a story
→ @po valida a story
→ @dev implementa
→ @qa revisa
→ @dev corrige, quando necessário
→ @qa verifica novamente e emite veredito
→ @po fecha a story
→ @devops executa gates, push e PR
```

Não considere uma story concluída apenas porque o código foi escrito ou porque o QA emitiu PASS.

Uma story somente está concluída quando:

* todos os critérios de aceite foram atendidos;
* os testes requeridos foram executados;
* lint passou;
* typecheck passou;
* testes passaram;
* build passou;
* QA emitiu veredito aceitável;
* File List está atualizada;
* Completion Notes estão atualizadas;
* Change Log está atualizado;
* o PO executou o fechamento;
* o backlog e o epic foram reconciliados;
* o DevOps executou os gates aplicáveis.

---

## 7. Implementação pelo Dev

Durante a implementação, o `@dev` deve:

1. trabalhar exclusivamente a partir da story validada;
2. executar as tasks na ordem definida;
3. implementar um incremento por vez;
4. criar ou atualizar testes;
5. executar validações após cada incremento relevante;
6. atualizar imediatamente os checkboxes;
7. manter a File List atualizada;
8. registrar decisões e desvios;
9. parar quando houver ambiguidade material;
10. não ampliar o escopo silenciosamente.

A implementação não deve:

* introduzir `any` ou casts inseguros sem justificativa;
* adicionar suppressions de lint sem justificativa;
* duplicar lógica existente;
* criar dependência circular;
* reduzir cobertura;
* adicionar TODO, FIXME ou HACK sem item de backlog;
* deixar código antigo e novo ativos em paralelo sem plano de remoção;
* introduzir abstração sem uso concreto;
* esconder falhas com fallback silencioso;
* modificar contratos públicos sem testes de compatibilidade;
* transformar dívida técnica em comentário;
* alterar componentes fora do escopo sem registrar impacto.

Quando surgir trabalho fora do escopo, registre-o no backlog como follow-up, débito técnico, risco ou nova story.

---

## 8. QA independente e baseado em evidência

O `@qa` não deve apenas confirmar que os testes existentes passam.

Deve verificar, conforme o risco:

* rastreabilidade entre critérios e testes;
* regressões;
* segurança;
* integridade de dados;
* tratamento de erros;
* observabilidade;
* performance;
* acessibilidade;
* contratos de integração;
* edge cases;
* concorrência;
* migrations;
* compatibilidade;
* efeitos em módulos adjacentes;
* dívida técnica introduzida.

O QA deve emitir um dos seguintes vereditos:

```text
PASS
CONCERNS
FAIL
WAIVED
```

Todo veredito deve incluir evidências, riscos residuais e justificativa.

`FAIL` deve retornar a story ao `@dev`.

`CONCERNS` deve gerar itens explícitos de backlog com owner, severidade e prazo.

`WAIVED` exige justificativa e autoridade apropriada.

Não permita que o mesmo agente que implementou seja a única fonte de validação.

---

## 9. Fechamento obrigatório pelo PO

Após o PASS do QA, o `@po` deve executar o fechamento da story (task: `po-close-story.md`).

O fechamento deve:

* verificar o veredito do QA;
* reconciliar checkboxes;
* atualizar status;
* atualizar o epic;
* atualizar o backlog;
* encerrar ou reclassificar débitos relacionados;
* registrar follow-ups;
* confirmar a Definition of Done;
* indicar a próxima story ou próximo gate.

Sem esse fechamento, a story não deve ser considerada finalizada.

---

## 10. Brownfield discovery não equivale a saneamento

Quando o projeto for legado, o `brownfield-discovery` deve ser tratado como diagnóstico inicial, não como processo completo de resolução.

O workflow deve gerar um baseline contendo, quando aplicável:

* documentação da arquitetura atual;
* auditoria de banco;
* auditoria de frontend e UX;
* assessment consolidado;
* relatório executivo;
* epic de dívida técnica;
* stories preliminares.

Depois do discovery, execute obrigatoriamente:

1. revisão dos débitos por causa raiz;
2. agrupamento por dependências;
3. organização em waves;
4. refinamento de stories pelo `@sm`;
5. validação pelo `@po`;
6. implementação;
7. QA local;
8. fechamento;
9. gate sistêmico ao final de cada wave;
10. atualização do baseline.

Nunca interprete "Discovery Complete" como "Sistema Saneado".

---

## 11. Planejamento de dívida técnica por causa raiz

Antes de converter todos os débitos em stories independentes, o `@architect` deve verificar se vários sintomas possuem uma causa raiz comum.

Agrupe débitos por:

* causa raiz;
* fronteira arquitetural;
* dependências;
* domínio;
* risco;
* camada do sistema;
* ordem necessária;
* potencial de regressão.

Evite criar várias stories de remendo quando uma mudança estrutural pode tratar a origem comum.

Organize preferencialmente as waves nesta ordem:

```text
Wave 1: segurança e integridade de dados
Wave 2: build, testes e observabilidade
Wave 3: fronteiras e fundações arquiteturais
Wave 4: redução de acoplamento e duplicação
Wave 5: performance e confiabilidade
Wave 6: UX, acessibilidade e consistência
Wave 7: otimizações não críticas
```

Adapte a ordem aos riscos reais do projeto.

---

## 12. Gate sistêmico ao final de cada wave

A aprovação isolada das stories não equivale à aprovação do sistema.

Ao final de cada wave, execute automaticamente uma revisão transversal envolvendo `@architect` e `@qa`.

O Architect deve avaliar:

* aderência entre arquitetura real e arquitetura-alvo;
* dependências alteradas;
* dívida resolvida;
* dívida parcialmente resolvida;
* novos débitos legados descobertos;
* dívida introduzida;
* riscos residuais;
* necessidade de replanejamento.

O QA deve avaliar:

* regressão entre módulos;
* segurança;
* integridade;
* integração;
* performance;
* observabilidade;
* testes;
* build;
* confiabilidade;
* compatibilidade;
* cumprimento das metas da wave.

A próxima wave somente pode começar após veredito sistêmico registrado.

---

## 13. Ledger central de dívida técnica

Mantenha um ledger único de dívida técnica no projeto em:

```text
docs/technical-debt/ledger.md
```

Cada item deve possuir:

* ID;
* descrição;
* causa raiz;
* origem;
* categoria;
* severidade;
* probabilidade;
* impacto;
* status;
* owner;
* story relacionada;
* wave;
* data de identificação;
* prazo;
* evidência;
* decisão;
* justificativa de aceite, quando aplicável.

Use os seguintes status:

```text
Identified
Validated
Planned
In Progress
Partial
Resolved
Accepted
False Positive
Obsolete
```

Use as seguintes origens:

```text
Legacy Discovered
Introduced by Change
Accepted Tradeoff
Regression
Unknown
```

Nenhuma dívida encontrada durante implementação ou QA deve permanecer apenas em comentário de código ou em resposta de chat.

---

## 14. Definition of Healthy do sistema

Não utilize "zero dívida técnica" como critério vago.

Considere o sistema saudável apenas quando:

* não existem vulnerabilidades críticas conhecidas;
* não existem falhas críticas de integridade de dados;
* não existem débitos HIGH sem owner e prazo;
* nenhuma nova dívida foi introduzida sem registro;
* lint, typecheck, testes e build passam;
* fluxos críticos possuem testes;
* migrations são reversíveis e testadas;
* erros relevantes são observáveis;
* não há regressões conhecidas;
* arquitetura real está suficientemente alinhada à arquitetura-alvo;
* backlog e ledger estão reconciliados;
* o gate sistêmico da wave passou.

Dívidas médias ou baixas podem permanecer quando forem explicitamente aceitas, justificadas, priorizadas e vinculadas a owner e prazo.

---

## 15. Escolha automática de workflow

Claude deve selecionar automaticamente o workflow conforme o contexto.

Use como regra geral:

```text
Projeto novo ou produto novo
→ greenfield workflow

Projeto legado sem diagnóstico confiável
→ brownfield-discovery

Projeto legado já diagnosticado
→ planejamento por waves + story-development-cycle

Feature nova
→ análise de impacto + story-development-cycle

Bug
→ investigação da causa raiz + story de correção + regression tests

Refatoração
→ baseline + arquitetura + story + testes de caracterização + implementação + QA

Mudança em banco
→ data-engineer + snapshot + dry-run + migration + rollback + QA

Mudança de arquitetura
→ architect antes do dev

Alteração de UX/UI
→ ux-design-expert antes ou em colaboração com dev

Publicação
→ devops após todos os gates
```

Não execute novamente o brownfield discovery completo a cada alteração. Use-o para baseline inicial ou quando o sistema mudou substancialmente e o assessment ficou obsoleto.

---

## 16. Uso eficiente de contexto

Carregue somente os arquivos necessários para a fase atual.

Não carregue todo o PRD, arquitetura, backlog e codebase em todos os agentes.

Use:

* stories como pacote principal de contexto do Dev;
* handoffs estruturados entre agentes (`.claude/rules/agent-handoff.md`);
* arquivos de arquitetura apenas quando referenciados;
* regras por paths quando aplicável;
* memória persistente apenas para decisões, padrões e gotchas úteis.

Antes de trocar de agente, gere handoff contendo:

* objetivo;
* trabalho concluído;
* arquivos alterados;
* decisões;
* pendências;
* riscos;
* testes executados;
* comando seguinte recomendado.

---

## 17. Interação com o usuário

Não peça ao usuário para repetir comandos AIOX rotineiros.

O usuário pode solicitar em linguagem natural, por exemplo:

```text
corrija este bug
implemente esta feature
refatore este módulo
faça a auditoria do sistema
prepare a próxima story
publique as alterações
```

Claude deve traduzir automaticamente a intenção para o fluxo AIOX correto.

Informe de forma objetiva:

* qual agente ou workflow foi selecionado;
* por que foi selecionado;
* qual artefato está sendo usado;
* qual é o próximo gate.

Não peça confirmação para seguir o protocolo normal.

Peça confirmação somente quando:

* houver operação destrutiva;
* houver mudança irreversível;
* houver custo externo relevante;
* os requisitos forem materialmente ambíguos;
* houver alteração de produção;
* uma task AIOX exigir elicitação obrigatória;
* houver necessidade de aceitar risco ou dívida conscientemente.

---

## 18. Correção automática de desvio

Se Claude detectar que começou a trabalhar fora do processo, deve interromper e corrigir o curso.

Exemplos:

* código sendo alterado sem story;
* agente atuando fora de sua autoridade;
* QA realizado pelo próprio implementador;
* story sem critérios testáveis;
* push antes dos gates;
* dívida técnica descoberta e não registrada;
* próxima wave iniciada sem gate sistêmico;
* story aprovada pelo QA, mas não fechada pelo PO.

Nesses casos, acione:

1. interrompa a ação atual;
2. declare o desvio detectado;
3. corrija o curso seguindo o protocolo desta regra;
4. se necessário, delegue ao agente correto via `Agent` tool.

---

## 19. Compatibilidade com a versão instalada

Esta regra foi verificada contra a versão AIOX instalada (v2.1.0, `core-config.yaml`).

**Agentes existentes e compatíveis:** @dev, @qa, @architect, @pm, @po, @sm, @analyst, @data-engineer, @ux-design-expert, @devops, @aiox-master

**Tasks existentes e compatíveis:** `create-next-story.md`, `validate-next-story.md`, `dev-develop-story.md`, `qa-gate.md`, `po-close-story.md`, `correct-course.md`

**Workflows existentes e compatíveis:** `story-development-cycle.yaml`, `qa-loop.yaml`, `spec-pipeline.yaml`, `brownfield-discovery.yaml`

**Subagent types disponíveis:** aiox-dev, aiox-qa, aiox-architect, aiox-pm, aiox-po, aiox-sm, aiox-analyst, aiox-data-engineer, aiox-devops, aiox-ux

Quando houver divergência entre documentação e versão instalada, considere como fonte prioritária:

1. Constitution atual (`.aiox-core/constitution.md`);
2. definições atuais dos agentes (`.aiox-core/development/agents/`);
3. matriz de autoridade atual (`.claude/rules/agent-authority.md`);
4. tasks e workflows atuais (`.aiox-core/development/tasks/`, `.aiox-core/development/workflows/`);
5. CLAUDE.md gerado;
6. documentação histórica.

---

## 20. Níveis de autonomia

O projeto opera com níveis progressivos de autonomia:

| Nível | Descrição | Confirmação necessária |
|-------|-----------|----------------------|
| **L0 — Manual** | Usuário digita comandos AIOX explicitamente | Nenhuma (usuário controla) |
| **L1 — Automático** | Claude infere agente/workflow, mas confirma antes de agir | Operações não-destrutivas |
| **L2 — YOLO** | Claude age sem confirmação, registrando decisões | Apenas operações destrutivas/irreversíveis |
| **L3 — Engine** | Workflow engine assume controle total do ciclo | Apenas gates com elicitação obrigatória |

**Default deste projeto: L2 (YOLO).** O protocolo opera em modo autônomo.
Confirmações são reservadas para o conjunto definido na seção 17.

---

## Referências cruzadas

* **Constitution:** `.aiox-core/constitution.md`
* **Matriz de autoridade:** `.claude/rules/agent-authority.md`
* **Story lifecycle:** `.claude/rules/story-lifecycle.md`
* **Workflow execution:** `.claude/rules/workflow-execution.md`
* **Agent handoff:** `.claude/rules/agent-handoff.md`
* **Handoff consolidation:** `.claude/rules/handoff-consolidation.md`
* **IDS principles:** `.claude/rules/ids-principles.md`
* **CodeRabbit integration:** `.claude/rules/coderabbit-integration.md`
* **Core config:** `.aiox-core/core-config.yaml`
* **PRD:** `docs/prd/`
* **Stories:** `docs/stories/`
* **Technical debt:** `docs/technical-debt/`

---

*PROJECT-CUSTOMIZED — Extra Consultoria. Não modifica camadas L1, L2 ou seções FRAMEWORK-OWNED.*
