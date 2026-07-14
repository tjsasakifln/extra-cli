---
description: Integração AIOX-Reversa — matriz de autoridade, roteamento, precedência, bridge, QA, hooks, estados. Carregado em todas as sessões.
---

# AIOX-Reversa Integration Protocol v1.0

> Project-customized. Não modifica arquivos L1, L2 ou installer-owned.

## 1. Divisão Formal de Autoridade

### Reversa — Autoridade para Conhecimento do Legado

- Reconhecimento da estrutura do sistema
- Mapeamento de módulos, dependências, entry points
- Extração de regras de negócio implícitas
- Documentação de fluxos, estados, contratos
- Levantamento da arquitetura atual (C4, ERD, ADRs)
- Análise de banco de dados existente
- Geração de specs retroativas (SDD)
- Produção de artefatos em `_reversa_sdd/`
- Preparação de requisitos, roadmap, actions em `_reversa_forward/`
- Geração de `legacy-impact.md` e `regression-watch.md`
- Re-extração e atualização da documentação após mudanças
- Geração de documentação visual (`_reversa_docs/`)

### AIOX — Autoridade para Mudança do Sistema

- Priorização de trabalho
- Definição da arquitetura-alvo
- Criação e gestão de epics
- Criação e refinamento de stories
- Validação de stories (PO)
- Implementação de código (Dev)
- Refatoração
- Migrations de banco
- QA e veredito de qualidade
- Fechamento de stories (PO)
- Gestão da dívida técnica
- Gates sistêmicos
- Push, pull request, release, deploy (DevOps)

### Princípio Obrigatório

```
Reversa descreve o que o sistema é e o que precisa permanecer verdadeiro.

AIOX decide como o sistema será alterado e controla toda alteração
de código, banco, infraestrutura e produção.
```

## 2. Não Destrutividade — Escopo Corrigido

**Durante workflows Reversa** (descoberta, extração, documentação, preparação de specs),
os agentes Reversa operam de forma não destrutiva e escrevem somente em:
`.reversa/`, `_reversa_sdd/`, `_reversa_docs/`, `_reversa_forward/`.

**Essa restrição NÃO se aplica ao AIOX Dev** quando houver:
- Story AIOX válida com status Ready/InProgress/InReview
- Aprovação do PO (po_validated: true)
- Escopo definido (scope_files no state)
- Nível de risco definido (risk_level no state)
- Implementação autorizada (status != Draft)
- Gates aplicáveis conforme risk_level

**Nenhum agente Reversa pode usar essa exceção para modificar código.**

## 3. Matriz de Roteamento

### Usar Reversa como framework principal quando:

- Entender o legado, documentar o sistema
- Descobrir regras implícitas, mapear arquitetura existente
- Extrair contratos, identificar fluxos de negócio
- Gerar specs retroativas, comparar documentação com código
- Atualizar documentação após mudanças (pós-Done)
- Gerar documentação visual (`/reversa-docs`)
- Calcular impacto com base no legado
- `/reversa`, `/reversa-new`, `/reversa-migrate`, `/reversa-docs`

### Usar AIOX como framework principal quando:

- Corrigir bug, implementar feature, refatorar
- Alterar comportamento, criar migration, alterar banco
- Alterar arquitetura, modificar integração
- Alterar autenticação ou autorização
- Modificar infraestrutura
- Executar QA, publicar, criar PR, realizar deploy

### Usar Bridge (AIOX-Reversa), em sequência, quando:

- Feature baseada em specs Reversa (`_reversa_forward/` com actions.md)
- `/reversa-coding` for invocado
- QA precisar validar regras extraídas pelo Reversa
- Story concluída exigir atualização das specs Reversa

Sequência:
```
Reversa (extrai/atualiza contexto)
→ AIOX Architect (avalia impacto)
→ AIOX SM (cria/refina story)
→ AIOX PO (valida)
→ AIOX Dev (implementa)
→ AIOX QA (valida com contexto Reversa)
→ AIOX PO (fecha)
→ AIOX DevOps (publica)
→ Reversa (atualiza specs, se aplicável)
```

### Regras de Precedência

1. `/reversa` explícito → respeitar workflow Reversa
2. `/reversa-coding` → bridge redireciona para AIOX
3. Pedido normal em linguagem natural → matriz acima
4. Nunca dois orquestradores simultâneos para a mesma etapa
5. Na dúvida entre documentar (Reversa) e alterar (AIOX): AIOX se houver intenção de mudança

## 4. Bridge AIOX-Reversa

Skill: `.claude/skills/aiox-reversa-bridge/SKILL.md`

### Quando acionar

- Pedido de alteração baseado em specs Reversa
- `_reversa_forward/` com feature ativa e `actions.md` pronto
- Usuário pede para implementar algo identificado durante `/reversa`
- QA precisa validar regras extraídas pelo Reversa
- Story concluída exige atualização das specs
- `/reversa-coding` invocado

### O que a bridge faz

1. Localiza artefatos Reversa relevantes
2. Verifica versão e atualidade da extração
3. Identifica regras e contratos impactados
4. Fornece contexto ao AIOX Architect
5. Gera ou localiza story AIOX
6. Registra referências Reversa no estado AIOX
7. Encaminha implementação ao AIOX Dev
8. Encaminha `regression-watch.md` ao QA
9. Determina se re-extração é necessária após a mudança

### O que a bridge NUNCA faz

- Implementar código
- Alterar arquivos fora dos diretórios autorizados
- Autorizar push ou PR
- Fechar story
- Emitir veredito de QA

## 5. `/reversa-coding` — Política de Redirecionamento

`/reversa-coding` NÃO atua como executor independente de código.

Quando invocado:
1. A bridge intercepta
2. Localiza `actions.md` da feature ativa
3. Converte ações em uma ou mais stories AIOX
4. Stories seguem o ciclo normal: @sm → @po → @dev → @qa → @po → @devops
5. `legacy-impact.md` e `regression-watch.md` são gerados como artefatos complementares

**Proibido:** `/reversa-coding` modificar código diretamente sem story AIOX validada.

## 6. Integração QA AIOX ↔ Reversa

Quando há contexto Reversa na story, o QA verifica adicionalmente:

- Regras de domínio 🟢 (CONFIRMADO) — devem ser preservadas ou intencionalmente alteradas
- Contratos documentados em `_reversa_sdd/`
- Estados e fluxos existentes
- Compatibilidade de dados
- `regression-watch.md` da feature
- Alterações registradas em `legacy-impact.md`
- Divergências entre código novo e specs Reversa
- Necessidade de atualizar a documentação Reversa

### Classificação de Divergências pelo QA

| Classificação | Significado | Ação |
|---------------|-------------|------|
| Regra preservada | Código novo mantém a regra | ✅ OK |
| Regra alterada intencionalmente | Story autorizava a alteração | ✅ OK se documentado |
| Regra quebrada por regressão | Story NÃO autorizava | 🔴 FAIL |
| Spec Reversa desatualizada | Extração anterior à mudança | 🟡 CONCERNS — recomendar re-extração |
| Intenção ambígua | Requer decisão humana | 🟡 CONCERNS — escalar ao PO |

**Divergência não é automaticamente bug.** Verificar se a story autorizava a alteração.

## 7. Contexto Reversa nas Stories AIOX

Bloco padronizado no state file da story:

```json
{
  "reversa_context": {
    "extraction_version": null,
    "architecture": [],
    "domain": [],
    "specifications": [],
    "requirements": null,
    "roadmap": null,
    "actions": null,
    "regression_watch": null,
    "legacy_impact": null
  }
}
```

Preencher apenas campos aplicáveis. Não copiar documentos Reversa integralmente — usar referências.

### O que a story deve indicar quando há extração Reversa

- Quais regras de domínio devem ser preservadas
- Quais regras serão alteradas intencionalmente
- Quais contratos não podem quebrar
- Quais componentes serão afetados
- Quais arquivos Reversa servem como evidência
- Quais itens de regressão o QA deve validar

## 8. Compatibilidade de Hooks

### Hooks AIOX e diretórios Reversa

- `_reversa_sdd/` → permitido (output_folder configurável)
- `_reversa_forward/` → permitido (forward_folder configurável)
- `_reversa_docs/` → permitido
- `.reversa/` → permitido (estado e contexto)
- Esses diretórios NÃO qualificam como "código da aplicação"
- Escrita neles NÃO requer story AIOX ativa
- Mas NÃO permitem bypass do `no-story-no-edit` para `src/`, `scripts/`, etc.

### Regras de Hook

- `/reversa-coding` NÃO contorna `no-story-no-edit`
- Story Reversa NÃO substitui story AIOX
- Feature Reversa NÃO autoriza push
- Push depende exclusivamente dos gates AIOX
- Artefatos Reversa não são confundidos com story AIOX

## 9. Re-extração Após Implementação

Critérios para recomendar nova execução do Reversa:

- Alteração de regra de negócio
- Novo módulo ou remoção de módulo
- Mudança arquitetural
- Alteração de contrato
- Mudança de schema
- Nova integração ou alteração de fluxo
- Divergência detectada pelo QA

**NÃO executar automaticamente.** Registrar como follow-up da story.
Re-extração requer interação do usuário (workflow Reversa tem checkpoints bloqueantes).

## 10. Estados Interoperáveis (Sem Misturar)

```
.reversa/state.json          → estado do workflow Reversa (extração, fases, checkpoints)
.aiox/state/stories/*.json   → estado operacional AIOX (story, gates, QA, publicação)
```

- Estado Reversa NÃO marca story AIOX como Done
- Estado AIOX NÃO declara extração Reversa concluída
- Referências cruzadas via `reversa_context` no state AIOX
- Nenhuma fusão das fontes de verdade

## 11. Arquivos Protegidos

### Framework-owned (NUNCA modificar)

- `.aiox-core/core/**`
- `.aiox-core/constitution.md`
- `.aiox-core/development/tasks/**`
- `.aiox-core/development/templates/**`
- `.aiox-core/development/checklists/**`
- `.aiox-core/development/workflows/**`
- `.aiox-core/infrastructure/**`

### Installer-owned (não modificar diretamente)

- `.reversa/config.toml` (usar `config.user.toml` para overrides)
- `.reversa/hooks.yml`
- `.reversa/_config/**`
- `.claude/skills/reversa*/**` (instaladas pelo pacote Reversa)
- `.agents/skills/reversa*/**` (instaladas pelo pacote Reversa)

### Protocol-protected (requer sessão de manutenção)

- `CLAUDE.md`, `.claude/CLAUDE.md`
- `.claude/settings*.json`
- `.claude/hooks/**`
- `.claude/rules/**`
- `.claude/skills/aiox-*/**`
- `.claude/skills/aiox-reversa-bridge/**`

### Project-customized (modificável com cautela)

- `.claude/skills/aiox-reversa-bridge/SKILL.md`
- `.claude/rules/aiox-reversa-integration.md` (este arquivo)
- `.reversa/config.user.toml`

### Runtime state (gerado, não editar manualmente)

- `.reversa/state.json`
- `.aiox/state/stories/*.json`
- `.reversa/context/**`

### Generated output (regenerável)

- `_reversa_sdd/**`
- `_reversa_docs/**`
- `_reversa_forward/**`

## 12. Referências

- Protocolo AIOX: `.claude/rules/aiox-project-operating-protocol.md`
- Agent authority: `.claude/rules/agent-authority.md`
- Constitution: `.aiox-core/constitution.md`
- Bridge skill: `.claude/skills/aiox-reversa-bridge/SKILL.md`
- Reversa state: `.reversa/state.json`
- AIOX state schema: `.aiox/state/stories/schema.json`
