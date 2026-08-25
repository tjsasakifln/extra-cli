# ADR-037 — Papel da contratada e primeiro toque delegado da CONFENGE

**Status:** Accepted by founder decision

**Date:** 2026-08-25
**Capability:** CONFENGE commercial activation

## Context

A presença de um CNPJ em um registro contratual não prova que a pessoa jurídica
é fornecedora do Poder Público. O mesmo registro contém a parte privada
contratada e a parte pública contratante. Além disso, a revisão humana
individual de cada mensagem deixou de ser o gate da campanha específica de
primeiro toque de roteamento.

## Decision

1. `v_contracts_canonical_v2` e `contract_role_links` são a autoridade de papel.
   O feed projeta `contractor_role` com policy `contract-party-role.v1`.
2. `CONTRACTOR_ROLE_CONFIRMED` exige correspondência do CNPJ de 14 dígitos do
   lead com o CNPJ da parte fornecedora, diferença em relação ao CNPJ ou raiz da
   compradora e papéis semânticos explícitos. Correspondência apenas por raiz
   preserva evidência para auditoria, mas permanece `UNKNOWN` até existir vínculo
   específico da filial. Rótulo ausente nunca recebe default.
3. Correspondência com a compradora domina qualquer evidência positiva e vira
   `PARTY_ROLE_CONFLICT`. Ausência ou ambiguidade vira `UNKNOWN`. Ambos bloqueiam
   o primeiro toque.
4. A projeção preserva CNPJs, papéis, IDs de contrato, source run, observado em,
   versão, reason codes e SHA-256 da evidência. Warmbly não reclassifica papel.
5. O agente CLI cruza essa evidência com fonte web original atual e escolhe uma
   única mailbox observada por CNPJ-raiz. Snippet, MX e email sintetizado não
   provam associação.
6. Somente o primeiro email curto de roteamento pode usar
   `CFG-FIRST-TOUCH-ROUTING-v1`. A decisão é `DELEGATED_POLICY_APPROVE`, com
   `approved_by_type=delegated_agent`, autoridade
   `founder-approved-first-touch-policy` e `approved_by` humano vazio.
7. O agente pode reparar copy e repetir QA até três vezes. Falha factual, de
   identidade, papel ou provenance permanece `HOLD`.
8. Warmbly continua como única autoridade de suppression, policy, fila,
   scheduling, cadência e outcomes. `QUEUED` exige readback da fila canônica.
   Kill switch, pausas, limites e janela comercial permanecem fail-closed.
9. A decisão altera os itens de aprovação humana de ADR-036 e DOD §2.7 apenas
   para esta finalidade. Follow-up, resposta, WhatsApp e mudança material de
   copy ou finalidade exigem nova policy ou autoridade humana.

## Consequences

- Órgãos contratantes não podem entrar na campanha como leads.
- O feed permanece snapshot integral de decisão e não autoriza envio sozinho.
- Não existe fila, CRM, scheduler ou geração por LLM em runtime adicional.
- Dados reais, emails e dumps permanecem fora do Git conforme ADR-020.
- A decisão está aceita; implementação em branch, CI, deploy e execução live
  conservam seus tiers honestos e não são inferidos deste documento.

## Verification

- Testes adversariais cobrem inversão, `UNKNOWN`, raiz de fornecedor e ausência
  de rótulo de papel.
- O schema `confenge.outreach.v1` aceita a projeção aditiva.
- A prova operacional final deve reconciliar contratadas confirmadas, contatos,
  QA, holds, aprovações delegadas, queue readback, duplicatas, envios e replies.
