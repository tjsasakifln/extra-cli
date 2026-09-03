# Story: CONFENGE Live Intelligence — Outbound Equivalence Gate (Protocolo de Dois Braços)

**Status:** Draft

**Criado por:** @sm (River), em resposta à ação bloqueante AR-5 do gate sistêmico de arquitetura
registrado em `docs/architecture/adr/ADR-040-confenge-live-intelligence-foundation.md`
(§"Gate HIGH-RISK de arquitetura sobre o reescopo do AC2"). Este arquivo é o stub mínimo
exigido para que a story exista de fato no backlog — ainda **não** validado pelo @po, ainda
**não** implementado pelo @dev. Apenas registro de existência real do artefato.

## Referências cruzadas

- Story de origem: `docs/stories/story-confenge-live-intelligence-01.md`
  (§"Follow-up bloqueante — `confenge-live-intelligence-outbound-equivalence-gate`",
  RULING-LI-02 v1.6, RULING-LI-03 v1.8)
- ADR: `docs/architecture/adr/ADR-040-confenge-live-intelligence-foundation.md`
  (item AR-5 da tabela do gate sistêmico)

## Problema

O AC2 da `story-confenge-live-intelligence-01` foi reescopado (decisão do @po em RULING-LI-02
v1.6, ratificada com condição pelo @architect no gate de arquitetura registrado no ADR-040)
para provar **apenas ausência estrutural de escrita outbound** — nenhum módulo outbound
referencia o motor `confenge_live_intelligence`, e nenhuma ACL de objeto outbound muda com a
migration 104. Essa prova **não** é equivalência byte-idêntica real de artefatos outbound
(`queue_counts()`, o payload do feed exportado por `scripts/warmbly_bridge/export.py`, e o
veredito de `scripts/confenge_contact_resolution/send_readiness.py`) rodando com/sem o motor
Live Intelligence presente, sob execução real de `run_pipeline()` e com dados reais. Essa
prova mais forte permanece pendente e foi deslocada para esta story.

## Causa raiz do adiamento

Falta um **2º DSN de banco descartável/isolado**, fora do banco de teste compartilhado
(`postgresql://test:test@127.0.0.1:5433/extra_test`), para rodar o protocolo de dois braços
sem poluir ou ser poluído por outras suítes (`golden_path_*`, `crawl_runtime_queue`,
`entity_*` deixam linhas residuais no banco compartilhado). Provisionar esse DSN é decisão de
infraestrutura de responsabilidade exclusiva do @devops — nenhum agente do ciclo atual da
story-01 tinha autoridade para produzi-lo, o que motivou o reescopo em vez do bloqueio
indefinido do fechamento daquela story.

## Escopo (IN)

Implementar o protocolo de dois braços completo, preservado na íntegra a partir da formulação
original do AC2 v1.5 da story-01:

1. Banco A: migrations aplicadas até a 102 (sem o motor Live Intelligence).
2. Banco B: migrations aplicadas até a 104+ (com o motor Live Intelligence presente, mas não
   invocado por nenhum caminho outbound).
3. Mesmo snapshot de dataset de input para `run_pipeline()`
   (`scripts/confenge_outreach_pipeline/pipeline.py`) rodando contra os dois bancos.
4. Comparação byte-a-byte dos artefatos outbound: `queue_counts()`, payload do feed exportado
   por `scripts/warmbly_bridge/export.py`, veredito de
   `scripts/confenge_contact_resolution/send_readiness.py`.
5. `Then`: os três artefatos são byte-idênticos entre as duas execuções.

## Escopo (OUT)

- Reabertura do reescopo do AC2 da story-01 (RULING-LI-02 é definitivo; esta story não
  contesta a decisão, apenas executa a prova que ficou pendente).
- Qualquer operacionalização do motor (cron/systemd, integração com `message_spine.py`,
  personalização de outbound) — esta story é pré-requisito bloqueante dessas, não o contrário.
- Correção de TD-LI-2, TD-LI-3, TD-LI-4, TD-LI-5 (tratados/registrados em outro lugar).

## Dependências

- **@devops** precisa provisionar o 2º DSN descartável antes que o @dev possa iniciar
  qualquer implementação nesta story. Esta é uma dependência bloqueante e sequencial, não
  paralelizável.
- Dataset de seed que exercite as 5 etapas do protocolo de dois braços.
- Autorização escopada de escrita outbound no banco descartável (não no banco compartilhado
  de testes).

## Débitos técnicos absorvidos

| Débito | Origem | Como é absorvido aqui |
|--------|--------|------------------------|
| TD-LI-1 | AC2 original (v1.5) da story-01, promovido a esta story de follow-up bloqueante pelo @po em RULING-LI-02 (v1.6) | Escopo IN completo desta story substitui a linha de dívida — deixa de existir como débito solto |
| TD-LI-6 | Não-determinismo de `test_blocked_when_watermark_is_missing` por poluição do banco de teste compartilhado, aceito como dívida não-bloqueadora pelo @po em RULING-LI-03 (v1.8) por identidade de causa raiz (mesmo owner: @devops, mesmo insumo: 2º DSN) | O 2º DSN provisionado para o protocolo de dois braços desta story resolve, como efeito colateral, o isolamento de banco que TD-LI-6 também precisa |

## Owners

@sm (criação da story, este stub) + @po (validação subsequente) + @architect (protocolo
normativo de dois braços, já preservado do AC2 v1.5) + @devops (provisionamento do 2º DSN).

## Próximo passo

Esta story permanece em **Draft**. Não avança para `Ready` até validação formal pelo @po
(`*validate-story-draft`), que por sua vez depende do @devops confirmar a viabilidade do 2º
DSN. Nenhuma implementação deve começar antes disso.

## Change Log

| Data | Versão | Descrição | Autor |
|------|--------|-----------|-------|
| 2026-09-02 | 1.0 | Criação do stub em resposta a AR-5 (gate sistêmico de arquitetura, ADR-040). Story existe agora de fato no backlog, absorvendo TD-LI-1 e TD-LI-6. Status Draft — sem validação do @po, sem implementação. | @sm |
