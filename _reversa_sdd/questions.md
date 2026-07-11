# Perguntas para Validação — Extra Consultoria

> Gerado pelo Reviewer em 2026-07-11T23:00:00Z | Respondido: 2026-07-11
> doc_level: completo

---

## Q1: Orquestrador Canônico ✅
**Resposta:** Migrar para `orchestrator.py`. Atualizar systemd timers para usar orchestrator como entry point. Deprecar `monitor.py` gradualmente (strangler fig pattern).

**Ação:** Atualizar `_reversa_sdd/crawl/design.md` — declarar `orchestrator.py` como canônico, `monitor.py` como legacy.
**Impacto nos GAPs:** GAP-02 resolve com migração planejada.

---

## Q2: Estratégia de Migração do Schema ✅
**Resposta:** Aplicar baseline v2 limpa (`001-v2_initial_schema.sql`) + migrações v2 (002-005). Abandonar migrations v1 como histórico.

**Ação:** Atualizar `_reversa_sdd/db/design.md` — declarar v2 como canônica. Adicionar tarefa no `db/tasks.md`: T-D16 (migração v1→v2).
**Impacto nos GAPs:** GAP-01 resolve com baseline v2 aplicada.

---

## Q3: Mapeamento de Portais de Transparência ✅
**Resposta:** Mapear via `detect_platform` em lote para todos os 295 municípios SC. Popular `transparencia_config.yaml` automaticamente.

**Ação:** Adicionar tarefa no `crawl/tasks.md`: T-C21 (batch platform detection para 295 municípios).
**Impacto nos GAPs:** GAP-04 resolve com script de detecção em lote.

---

## Q4: SICAF — Confiabilidade ✅
**Resposta:** Pipeline prossegue em degraded mode sem SICAF. Plano: migrar de Playwright para Selenium para maior confiabilidade.

**Ação:** Atualizar `intel/tasks.md`: T-I09 revisado para incluir migração Playwright→Selenium.
**Impacto nos GAPs:** GAP-05 reduz severidade (degraded mode existe). Selenium mitiga fragilidade.

---

## Q5: Estratégia de Testes ✅
**Resposta:** TDD no ciclo forward. Cada nova feature com teste obrigatório. Cobertura do legado aumenta organicamente.

**Ação:** Registrar como requisito não funcional no `architecture.md`.
**Impacto nos GAPs:** GAP-06 endereçado por política (não por esforço retroativo).

---

## Q6: ARP/PCA Crawlers ✅
**Resposta:** Manter async. Executar separadamente na VPS (fora do pipeline sync principal) quando dados estiverem validados.

**Ação:** Adicionar tarefa no `deploy/tasks.md`: T-DP09 (systemd timer para ARP/PCA async).
**Impacto nos GAPs:** GAP-07 resolvido — async é intencional, não débito.
