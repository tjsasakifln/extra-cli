# Perguntas para Validação — Extra Consultoria

> Gerado pelo Reviewer em 2026-07-11T17:00:00Z
> Respondido por Tiago em 2026-07-11

---

## Q1: Cobertura de Testes ✅
**Arquivo:** `domain.md` (L2)
**Confiança anterior:** 🔴 → **Nova:** 🟡
**Pergunta:** A cobertura de testes atual é estimada em <30%. Existe um plano para aumentar a cobertura? Quais módulos são prioridade?

**Resposta:** Cobertura total agora — Claude gera suíte de testes automatizada para todos os módulos críticos (crawl, intel, reports, lib).

---

## Q2: Crawler SICAF ✅
**Arquivo:** `domain.md` (L3), `crawl/requirements.md`
**Confiança anterior:** 🔴 → **Nova:** 🟡
**Pergunta:** O crawler SICAF (sanctions.py) requer Playwright, que está comentado no requirements.txt. Pretende ativá-lo? Se sim, qual a prioridade?

**Resposta:** Sim, ativar — instalar Playwright e ativar sanctions.py.

---

## Q3: Features Não Implementadas (PRD Could Have) ✅
**Arquivo:** `domain.md` (L7)
**Confiança anterior:** 🔴 → **Nova:** 🟡
**Pergunta:** Das features Could Have do PRD (Alertas Telegram, Dashboard TUI, Integração DOE-SC), alguma deve ser priorizada no próximo ciclo?

**Resposta:** Integração DOE-SC e Dashboard TUI — priorizar ambos. Alertas Telegram: não priorizar agora.

---

## Q4: Monitoramento de Health dos Crawlers ✅
**Arquivo:** `domain.md` (L7)
**Confiança anterior:** 🔴 → **Nova:** 🟡
**Pergunta:** Além do template `onfailure@.service`, há planos para um dashboard de health dos 13 crawlers? (ex: métricas de uptime, taxas de erro, latência)

**Resposta:** Dashboard completo — web ou TUI com status em tempo real de todos os crawlers.

---

## Q5: Relatório de Sazonalidade ✅
**Arquivo:** `domain.md` (L6)
**Confiança anterior:** 🔴 → **Nova:** 🟡
**Pergunta:** O PRD lista o relatório de sazonalidade (S2) como parcialmente implementado. O que falta para considerá-lo completo? (heatmap mensal já existe em panorama.py)

**Resposta:** Completar heatmap/previsão — heatmap por setor, picos mensais e previsão de volume.

---

## Resumo das Reclassificações

| ID | 🔴→🟡 | Impacto |
|----|--------|---------|
| Q1 (L2) | ✅ | Plano de testes definido: cobertura total, todos os módulos críticos |
| Q2 (L3) | ✅ | SICAF ativado: Playwright descomentado, sanctions.py ativo |
| Q3 (L7) | ✅ | DOE-SC + Dashboard TUI priorizados; Alertas Telegram postergado |
| Q4 (L7) | ✅ | Dashboard completo de health dos crawlers planejado |
| Q5 (L6) | ✅ | Sazonalidade: heatmap por setor + previsão de volume definidos |

**Novo percentual de confiança: 🟢 91.7% | 🟡 8.3% | 🔴 0%**
