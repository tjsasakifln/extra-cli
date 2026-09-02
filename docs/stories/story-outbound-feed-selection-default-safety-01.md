# Story: Tornar explícita a seleção ampla do feed de outbound (`target_confirmed_only` com default inseguro)

## Status

**Draft**

## Risk Level

**A CLASSIFICAR NA VALIDAÇÃO** — candidato a HIGH-RISK. Motivo: o parâmetro governa **quais empresas entram no feed de outbound comercial**, isto é, quem pode receber e-mail real. É a mesma superfície do incidente SEBRAE-ES de 2026-09-01.

## Story-mãe (origem desta dívida)

`docs/stories/story-outbound-sector-classifier-false-positive-01.md` — dívida `MNT-003-REVISED`, aberta pelo @architect (D.9), promovida pelo @po a verificação obrigatória do @qa (Ratificação nº 5) e **parcialmente falsificada pelo @qa (Quinn) na iteração 2 do QA loop**, com medição própria em produção.

## Story

**Como** founder responsável pela ativação do outbound B2G da CONFENGE,
**quero** que nenhuma função de seleção de população para o feed de outbound possa selecionar a coorte ampla (`sector_class`) por **omissão de argumento**,
**para que** um gate de exclusão validado na camada `target_fit` não possa ser contornado silenciosamente por um default de assinatura.

## Contexto — medição do @qa (2026-09-01), não hipótese

`continuous_from_target_fit.py:69` declara `target_confirmed_only: bool = False`. Existem **5 call sites**, não 2:

| Call site | Alcançável por | Valor |
|---|---|---|
| `scripts/confenge_outreach_pipeline/pipeline.py:217` | `confenge_feed_cycle` (constrói feed) | `True` |
| `scripts/decision_unit_intelligence/batch_population.py:299` | `confenge_contact_cycle` (constrói feed) | `True` |
| `scripts/confenge_outreach_pipeline/continuous_from_target_fit.py:338` (`run_continuous_enrichment`) | CLI `enrich-continuous` (`confenge_contact_resolution/cli.py:447`) | **omitido → `False`** |
| `scripts/confenge_process_enrichment/national_confirmed.py:93` | CLI `national-confirmed` (`confenge_process_enrichment/cli.py:195`) | **omitido → `False`** |
| `scripts/confenge_outreach_pipeline/continuous_from_target_fit.py:286` (`load_confirmed_jobs_from_dsn`) | sem chamadores (código morto) | **omitido → `False`** — nome promete "confirmed", corpo passa `False` |

**Impacto medido em produção pelo @qa:** as 4 raízes Sistema S estão em `confenge_company_sector_current` como `CONSTRUCTION_PROBABLE` conf 0.4, e **67 das 68** raízes suprimidas pelo gate parafiscal da story-mãe seriam reselecionadas pelo ramo `sector_class IN ('CONSTRUCTION_CONFIRMED','CONSTRUCTION_PROBABLE')`.

**Por que não bloqueou a story-mãe (decisão do @po no fechamento, 2026-09-01):** o discriminante **não** é "agendado vs. manual" — o @qa verificou que `extra-confenge-contact-cycle.timer` e `extra-confenge-feed-cycle.timer` estão **disabled** em `ec-prod`. O discriminante é **qual comando constrói o feed**: os dois que constroem passam `True` ponta a ponta; os que herdam `False` apenas **enriquecem contato** — não publicam feed nem disparam e-mail. O dano do incidente só se materializa pelo caminho de construção do feed, e esse está protegido nos dois pontos de entrada.

## Scope

**IN:**
- Inverter o default para `target_confirmed_only: bool = True`, **ou** torná-lo keyword-only sem default (`*, target_confirmed_only: bool`), de modo que a seleção ampla passe a ser escolha explícita e auditável no call site.
- Corrigir `load_confirmed_jobs_from_dsn` (`continuous_from_target_fit.py:286`), cujo nome promete "confirmed" e cujo corpo passa `False`. Avaliar remoção se confirmado como código morto.
- Revalidar os 5 call sites após a mudança de assinatura.
- Teste que falha se um novo call site omitir o argumento (ex.: AST/`inspect.signature` sobre os call sites, ou assinatura keyword-only, que já falha em import time).

**OUT:**
- Alterar o gate parafiscal ou a taxonomia (já entregue pela story-mãe).
- Mexer em `sector_class` / `confenge_company_sector_current`.

## Acceptance Criteria (rascunho — a refinar pelo @sm/@po)

1. **Given** um call site novo que omita `target_confirmed_only`, **when** o módulo é importado/testado, **then** a seleção ampla **não** é o comportamento resultante (default seguro ou erro explícito).
2. **Given** os comandos `enrich-continuous` e `national-confirmed`, **when** executados sem flags, **then** não selecionam a coorte ampla por `sector_class`.
3. **Given** as 68 raízes suprimidas pelo gate parafiscal, **when** qualquer um dos 5 call sites é exercitado, **then** nenhuma delas é reselecionada.

## Owner e prazo

| Campo | Valor |
|---|---|
| Owner | @po (Pax) — refinar com @sm antes de implementar |
| Origem | `MNT-003-REVISED` (severidade medium) — gate `docs/qa/gates/outbound-sector-classifier-false-positive-01.yml` |
| Prazo de refinamento | até 2026-09-08 (7 dias do fechamento da story-mãe) |
| Bloqueada por | Publicação da story-mãe (PR 1 + PR 2). Não alargar o diff HIGH-RISK já medido. |

## Change Log

| Date | Version | Description | Author |
|---|---|---|---|
| 2026-09-01 | 0.1.0 | Draft criado no fechamento da story-mãe para materializar `MNT-003-REVISED` como item rastreável com owner e prazo | Pax (@po) |
