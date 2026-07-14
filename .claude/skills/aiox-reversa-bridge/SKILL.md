---
name: aiox-reversa-bridge
description: >
  Bridge AIOX-Reversa. Conecta artefatos Reversa (_reversa_sdd/, _reversa_forward/)
  ao pipeline AIOX. Acionada quando há alteração baseada em specs Reversa,
  actions.md pronto para implementação, /reversa-coding invocado,
  ou QA precisa validar regras extraídas. NUNCA implementa código diretamente.
  Sempre redireciona implementação para o AIOX Dev com story validada.
---

# AIOX-Reversa Bridge

## Quando esta skill é acionada

- Pedido de alteração baseado em specs Reversa
- `_reversa_forward/` com feature ativa e `actions.md` pronto
- `/reversa-coding` invocado (explícito ou via smart-router)
- Usuário pede para "executar actions.md" ou "implementar roadmap Reversa"
- QA precisa validar regras extraídas pelo Reversa
- Story concluída exige atualização das specs Reversa

## Comportamento por gatilho

### Gatilho: `/reversa-coding` ou "executar actions.md"

1. Ler `.reversa/state.json` → resolver `output_folder`, `forward_folder`
2. Ler `.reversa/active-requirements.json` → localizar `feature-dir`
3. Se `feature-dir/actions.md` não existir → abortar: "Nenhum actions.md encontrado. Execute `/reversa-forward` primeiro."
4. Se `_reversa_sdd/` não contiver `architecture.md` + `domain.md` → modo greenfield (sem âncora de legado)
5. **NÃO executar ações diretamente.** Converter actions em stories AIOX.
6. Para cada fase do `actions.md` com ações `[ ]`:
   - Agrupar ações independentes
   - Criar uma story AIOX por grupo coeso (via @sm)
   - Incluir `reversa_context` no state file de cada story
7. Informar usuário: stories criadas, próximo passo é validação pelo PO.

### Gatilho: feature Reversa ativa + pedido de implementação

1. Localizar `requirements.md`, `roadmap.md`, `actions.md` da feature
2. Verificar versão da extração em `.reversa/state.json`
3. Identificar regras 🟢 (CONFIRMADO) em `_reversa_sdd/domain.md` impactadas
4. Identificar contratos documentados que não podem quebrar
5. Fornecer contexto ao AIOX Architect para avaliação de impacto
6. AIOX SM cria ou localiza stories
7. AIOX PO valida
8. AIOX Dev implementa (com story validada)
9. AIOX QA valida (com contexto Reversa)
10. AIOX PO fecha
11. AIOX DevOps publica
12. Recomendar re-extração Reversa se aplicável

### Gatilho: QA com contexto Reversa

1. Coletar `regression-watch.md` da feature
2. Coletar regras 🟢 do `_reversa_sdd/domain.md`
3. Coletar contratos de `_reversa_sdd/*/contracts.md`
4. Fornecer ao AIOX QA como checklist adicional
5. QA classifica divergências (preservada/alterada/regressão/desatualizada/ambígua)

### Gatilho: story concluída + possível re-extração

1. Verificar se story alterou: regra de negócio, schema, contrato, fluxo, arquitetura
2. Se sim → recomendar re-extração como follow-up
3. NÃO executar re-extração automaticamente
4. Registrar recomendação no state file da story

## Contexto Reversa no State AIOX

Para cada story criada a partir de artefatos Reversa, preencher no state file:

```json
{
  "reversa_context": {
    "extraction_version": "<.reversa/state.json → version>",
    "architecture": ["_reversa_sdd/architecture.md"],
    "domain": ["_reversa_sdd/domain.md"],
    "specifications": ["_reversa_sdd/<module>/design.md"],
    "requirements": "_reversa_forward/<feature>/requirements.md",
    "roadmap": "_reversa_forward/<feature>/roadmap.md",
    "actions": "_reversa_forward/<feature>/actions.md",
    "regression_watch": "_reversa_forward/<feature>/regression-watch.md",
    "legacy_impact": null
  }
}
```

Preencher apenas campos com artefatos existentes. Usar referências, não copiar conteúdo.

## Regras de documentação na story

Quando há extração Reversa, a story AIOX deve incluir:

- **Regras preservadas:** quais regras 🟢 do domínio DEVEM continuar verdadeiras
- **Regras alteradas:** quais regras 🟢 serão INTENCIONALMENTE modificadas
- **Contratos invioláveis:** quais contratos NÃO podem quebrar
- **Componentes afetados:** quais componentes de `architecture.md` serão tocados
- **Evidências:** quais arquivos Reversa servem como baseline
- **Regressão:** quais itens de `regression-watch.md` o QA deve validar

## O que esta bridge NUNCA faz

- Implementar código (delegar ao @dev)
- Alterar arquivos em `src/`, `scripts/`, `config/`
- Autorizar push ou PR (exclusivo do @devops)
- Fechar story (exclusivo do @po)
- Emitir veredito de QA (exclusivo do @qa)
- Executar `/reversa-coding` original (redireciona para AIOX)
- Modificar artefatos Reversa (`.reversa/`, `_reversa_sdd/`)
- Criar stories sem validação do PO
- Burlar o protocolo AIOX

## Referências

- Integração AIOX-Reversa: `.claude/rules/aiox-reversa-integration.md`
- Protocolo AIOX: `.claude/rules/aiox-project-operating-protocol.md`
- Agent authority: `.claude/rules/agent-authority.md`
- Story cycle: `.claude/skills/aiox-story-cycle/SKILL.md`
- Reversa forward: `.claude/skills/reversa-forward/SKILL.md`
- Reversa coding (original): `.claude/skills/reversa-coding/SKILL.md`
