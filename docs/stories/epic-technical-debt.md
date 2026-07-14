# Epic: Resolucao de Debitos Tecnicos -- Extra Consultoria

**Versao:** 2.0
**Data:** 2026-07-13
**Base:** technical-debt-assessment.md (79 de modoos, 5 categorias, ~353.5h) + plano-mestre-fechamento-gaps-extra-consultoria.md (9 Epics P0, DoD Section 22)
**Autor:** Morgan (@pm), com base na brownfield assessment de Aria (@architect) e plano mestre
**Status:** Complete (5/5 stories done) — Stories 1.1, 1.2, 1.3, 1.4, 1.5 Done. Epic completo.

---

## Objetivo

Resolver os debitos tecnicos criticos e implementar os EPICs P0 do plano mestre de fechamento de gaps, habilitando o sistema a produzir dados confiaveis para a consultoria. O epic consolida as 79 dividas tecnicas identificadas na brownfield assessment (v2.0 FINAL) e os 9 Epics P0 do plano mestre (Seccoes 5-14), priorizando a ordem de execucao obrigatoria definida na Secao 4 do plano mestre.

O sistema so sera considerado apto a apoiar a consultoria quando todos os 17 criterios da Definition of Done (Secao 22 do plano mestre) forem atendidos no mesmo run.

---

## Escopo

### In Scope

1. **Correcoes de seguranca emergenciais** -- SEC-01, SEC-02, SEC-03, TD-001 (P0 brownfield)
2. **P0-01: Congelar escopo e limpar documentacao** -- TD-031, documentacao desatualizada, remover claims contraditorios (Secao 5 do plano mestre)
3. **P0-02: Unificar schema de banco** -- DT-01 a DT-06, DT-18 a DT-23, auditoria automatica, views canonicas, migrations 030-036, baseline reproduzivel (Secao 6)
4. **P0-03: Planilha como unica autoridade do universo** -- TD-001, TD-005, TD-034, tabela de snapshots, ledger de divergencia, bloqueio por seed change (Secao 7)
5. **P0-04: Reconciliar snapshots de editais abertos** -- TD-002, TD-006, algoritmo de reconciliacao de snapshot, active_snapshot_integrity (Secao 8)
6. **P0-05: Modelo de cobertura por fonte, ente e capacidade** -- TD-003, coverage_evidence, registry de fontes, matriz de aplicabilidade (Secao 9)
7. **P0-06: Provar fontes de editais alem do PNCP** -- 8 fontes implementadas, adapter contract, fixtures, reconciliação (Secao 10)
8. **P0-07: Perfil comercial real da EXTRA** -- config completa, taxonomia de engenharia, calibracao com 230+ casos (Secao 11)
9. **P0-08: Contratos historicos completos e atualizaveis** -- backfill 3 anos, versionamento, correcao de checkpoint parcial (Secao 12)
10. **P0-09: Inteligencia de concorrentes correta** -- identidade de fornecedor, metricas em v_contracts_canonical, top 15 reproduzivel (Secao 13)

### Out of Scope (neste epic)

- Acompanhamento fisico, financeiro ou documental de obras em execucao (Secao 1 do plano mestre)
- Deploy Hetzner/Supabase self-hosted (Epic P2, Secao 20 do plano mestre)
- UX-01 (Web UI FastAPI+HTMX, ~40-80h) -- backlog P3
- P3 debts (CHECK constraints, GIN indexes, UX-05, UX-06, UX-11, etc.)
- Preco praticado com semantica correta (Epic P1-01, Secao 14) -- fase posterior
- Contratos vincendos e relicitacao (Epic P1-02, Secao 15)
- Relatorio e planilhas da consultoria (Epic P1-03, Secao 16)
- QA e gates avancados (Epic P1-05, Secao 18) -- parte executada em paralelo

---

## Ordem de Execucao (do plano-mestre, Secao 4)

1. Corrigir schema e autoridade do universo (Stories 1.2 + 1.3)
2. Corrigir reconciliacao de editais PNCP (Story 1.4)
3. Provar um fluxo completo local, do crawl ao relatorio (Story 1.5 + fontes)
4. Fechar contratos historicos e atualizacao
5. Fechar concorrentes
6. Implementar preco praticado
7. Provar cobertura multicanal
8. Gerar relatorio final
9. Somente entao desenhar deploy Hetzner/Supabase

Nenhuma tarefa posterior pode mascarar blocker de uma tarefa anterior.

### Sequencia pratica recomendada (Sprints 0-3)

| Sprint | Foco | Stories |
|--------|------|---------|
| Sprint 0 (Semana 1) | Seguranca + Quick Wins | 1.1 (Done) + documentacao |
| Sprint 1 (Semana 2) | Schema + Universo | 1.2 + 1.3 |
| Sprint 2 (Semana 3) | Reconciliacao + Cobertura | 1.4 + 1.5 |
| Sprint 3 (Semana 4+) | Fontes + Contratos + Concorrentes | P0-06, P0-07, P0-08, P0-09 |

---

## Stories

| ID | Story | EPIC Mestre | Debitos Brownfield | Prioridade | Status |
|----|-------|-------------|-------------------|------------|--------|
| 1.1 | Fix Critical Security | (Pre-requisito P0 -- seguranca e infra) | SEC-01, SEC-02, SEC-03, TD-001, TD-019, TD-021 | P0 | Done |
| 1.2 | Unify Schema | P0-02 -- Schema de Banco | DT-01, DT-02, DT-03, DT-04, DT-05, DT-06, DT-18, DT-19, DT-20, DT-22 | P0 | Done |
| 1.3 | Universe Authority | P0-03 -- Autoridade do Universo | TD-001 (universo), TD-005, TD-034 | P0 | Done |
| 1.4 | Reconcile Open Tenders | P0-04 -- Reconciliacao de Editais | TD-002, TD-006, DT-14, DT-21, DT-23 | P0 | Done |
| 1.5 | Coverage Model | P0-05 -- Cobertura por Fonte | TD-003, TD-027, TD-033 | P0 | Done |
| -- | P0-01: Documentacao | P0-01 -- Documentacao e Escopo | TD-031 | P0 | |
| -- | P0-06: Multi-fontes | P0-06 -- Fontes alem do PNCP | TD-011, TD-020 | P0 | |
| -- | P0-07: Perfil EXTRA | P0-07 -- Perfil Comercial | -- | P0 | |
| -- | P0-08: Contratos | P0-08 -- Contratos Historicos | DT-05, DT-11, DT-16, DT-22 | P0 | |
| -- | P0-09: Concorrentes | P0-09 -- Inteligencia de Concorrentes | TD-003, TD-027 | P0 | |

**Estimativa total Stories 1.1-1.5:** ~65h
**Estimativa Epic completo (P0 todo):** ~180h distribuidos em ~10 stories

---

## Criterios de Sucesso (da Definition of Done, Secao 22 do plano mestre)

O projeto estara apto a apoiar a consultoria quando, no mesmo run:

1. A seed tiver resolucao de 100%
2. A cobertura de investigacao de cada capability essencial for >= 95%
3. Todos os editais exibidos estiverem no snapshot mais recente ou reconfirmados
4. 95% dos editais acionaveis tiverem campos criticos e URL oficial
5. O historico contratual de tres anos tiver janelas completas
6. Zero janela parcial estiver marcada como concluida
7. Top 15 concorrentes executar no schema real e tiver rastreabilidade
8. Preco praticado estiver claramente separado de ticket contratual
9. Percentis tiverem unidade, categoria e N minimo
10. Desagio for calculado apenas no mesmo item/lote
11. Contratos vincendos tiverem vigencia confiavel
12. PDF e Excel compartilharem run_id
13. Migrations passarem em banco vazio e upgrade
14. Gates tecnicos passarem (ruff, mypy, bandit, pytest)
15. QA humana aprovar amostra
16. Manifest nao contiver claim proibido
17. Exit code for 0

**Status atual:** PARTIAL / NOT CLIENT-READY

---

## Matriz de Dependencias entre Stories

```
Story 1.1 (seguranca)
  ├── desbloqueia: qualquer deploy seguro
  └── prereq para: tudo

Story 1.2 (schema)
  ├── depende de: 1.1 (seguranca basica)
  ├── desbloqueia: 1.3, 1.4, 1.5 (views canonicas)
  └── prereq para: P0-06, P0-07, P0-08, P0-09

Story 1.3 (universo)
  ├── depende de: 1.1, 1.2 (schema estavel)
  └── desbloqueia: metricas consistentes em todo o sistema

Story 1.4 (reconciliacao)
  ├── depende de: 1.2 (schema com colunas de snapshot)
  └── desbloqueia: radar confiavel

Story 1.5 (cobertura)
  ├── depende de: 1.2 (tabela coverage_evidence)
  └── desbloqueia: metricas de qualidade auditaveis
```

---

## Riscos

| # | Risco | Probabilidade | Impacto | Mitigacao |
|---|-------|---------------|---------|-----------|
| CR-001 | Refatoracao de schema (1.2) quebrar queries existentes | ALTA | CRITICO | Views canonicas como abstracao; testes de regression em staging |
| CR-002 | Exposicao composta de credenciais (SEC-02 + SEC-03) | ALTA | CRITICO | Story 1.1 como P0 imediato; BFG cleanup + rotacao |
| CR-003 | DT-02 (v3 migration) sem rollback testado | MEDIA | ALTO | Dry-run + rollback script antes da execucao |
| CR-004 | Story 1.1 nao priorizada vs urgencia dos blockers | BAIXA | ALTO | Ja e Story #1; SEC-03, SEC-02 sao P0 inegociaveis |
| CR-005 | Escopo crescendo durante execucao (scope creep) | ALTA | MEDIO | Congelamento via P0-01; decisao por新增 stories, nao alteracao |

---

## Referencias

- `docs/prd/technical-debt-assessment.md` -- Brownfield assessment FINAL (79 itens, ~353.5h)
- `plano-mestre-fechamento-gaps-extra-consultoria.md` -- Plano mestre (9 Epics P0, Secao 22 DoD)
- `docs/architecture/system-architecture.md` -- Fase 1 Brownfield
- `supabase/docs/DB-AUDIT.md` -- Fase 2 Brownfield
- `docs/frontend/frontend-spec.md` -- Fase 3 Brownfield
- `.aiox/gotchas.json` -- Riscos operacionais conhecidos
- `.aiox-core/core-config.yaml` -- Configuracao do framework AIOX

---

## Change Log

| Data | Versao | Descricao | Autor |
|------|--------|-----------|-------|
| 2026-07-13 | 1.0 | Criacao do epic com 5 stories iniciais (P0) + mapeamento dos 9 Epics do plano mestre | Morgan (@pm) |
| 2026-07-13 | 2.0 | Epic completo (5/5 stories done). Stories 1.1-1.5 passaram pelo fluxo completo: sm -> po -> dev -> qa -> close. TD-003, TD-027, TD-033, SEC-01/02/03, DT-01/02/03/04/05/06/18/19/20/21/22/23, TD-001/002/005/006/019/021/034 resolvidos. Proximos: P0-06 a P0-09. | Pax (@po) |
